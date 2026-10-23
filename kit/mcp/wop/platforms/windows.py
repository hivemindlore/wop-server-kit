"""Windows: PowerShell for the firewall, shortcuts and network names; cmd scripts for the server window."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .base import FirewallCheck, NetworkProblem, PlatformBehavior, Shortcut

FIREWALL_RULE = "WoP Server Kit"

CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def powershell(script: str, check: bool = False) -> subprocess.CompletedProcess:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, text=True, check=check, creationflags=CREATE_NO_WINDOW)


def ps_quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


# Prints, as JSON: the kit's rule, the enabled inbound block rules that could hit the server, the firewall
# profiles in effect (group policy included), the active network categories and any other firewall product.
# The filters are fetched once for all rules: asking per rule takes ~0.4 s each. Without admin rights Windows
# leaves part of them out ("Access is denied" halfway), so the rules we look at are asked for one by one when missing.
NETWORK_REPORT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$apps = @{}; Get-NetFirewallApplicationFilter | ForEach-Object { $apps[$_.InstanceID] = "$($_.Program)" }
$ports = @{}; Get-NetFirewallPortFilter | ForEach-Object { $ports[$_.InstanceID] = $_ }
function Filters($r) {
  $app = if ($apps.ContainsKey($r.Name)) { $apps[$r.Name] } else { "$(($r | Get-NetFirewallApplicationFilter).Program)" }
  $pf = $ports[$r.Name]; if (-not $pf) { $pf = $r | Get-NetFirewallPortFilter }
  return $app, $pf
}
$rule = $null; $blocks = @()
foreach ($r in Get-NetFirewallRule) {
  if ($r.DisplayName -eq $ruleName -and -not $rule) {
    $app, $pf = Filters $r
    $rule = [ordered]@{ enabled = "$($r.Enabled)"; action = "$($r.Action)"; direction = "$($r.Direction)"
      profile = "$($r.Profile)"; program = $app; protocol = "$($pf.Protocol)"
      remote = @(($r | Get-NetFirewallAddressFilter).RemoteAddress | ForEach-Object { "$_" }) }
  } elseif ("$($r.Direction)" -eq 'Inbound' -and "$($r.Action)" -eq 'Block' -and "$($r.Enabled)" -eq 'True') {
    $app, $pf = Filters $r
    $local = @($pf.LocalPort | ForEach-Object { "$_" })
    if ($app -like '*wopded*' -or $local -contains $port) {
      $blocks += [ordered]@{ name = $r.Name; display = $r.DisplayName; program = $app
        protocol = "$($pf.Protocol)"; ports = $local }
    }
  }
}
$profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore | ForEach-Object {
  [ordered]@{ name = "$($_.Name)"; enabled = "$($_.Enabled)"; allow_inbound = "$($_.AllowInboundRules)"
    local_rules = "$($_.AllowLocalFirewallRules)" } })
$active = @(Get-NetConnectionProfile | ForEach-Object { "$($_.NetworkCategory)" -replace 'DomainAuthenticated', 'Domain' })
$others = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct | ForEach-Object { "$($_.displayName)" })
ConvertTo-Json -Compress -Depth 5 -InputObject ([ordered]@{
  rule = $rule; blocks = $blocks; profiles = $profiles; active = $active; others = $others })
"""

# This computer's IPv4 addresses on networks with a router. Virtual adapters (WSL, Hyper-V, VirtualBox) have none,
# so their addresses, which would only confuse the players, are left out.
ADDRESSES = r"""
Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
  ForEach-Object { foreach ($a in $_.IPv4Address) { "$($a.IPAddress)`t$($_.InterfaceAlias)" } }
"""


def network_report(port: int) -> dict | None:
    """What the Windows Firewall does with the server's traffic (no admin needed). None if it can't be read."""
    out = powershell(f"$ruleName = {ps_quote(FIREWALL_RULE)}; $port = '{port}'\n{NETWORK_REPORT}").stdout
    try:
        report = json.loads(out.strip())
    except ValueError:
        return None
    return report if isinstance(report, dict) and report.get("profiles") else None


def _same_program(a: str | None, b: str | None) -> bool:
    def norm(path: str | None) -> str:
        return os.path.expandvars(path or "").replace("/", "\\").lower()
    return norm(a) == norm(b)


def _port_listed(port: int, ports: list[str]) -> bool:
    for entry in ports:
        low, _, high = entry.partition("-")
        if low.isdigit() and int(low) <= port <= int(high if high.isdigit() else low):
            return True
    return False


def kit_rule_script(program: str) -> str:
    return (f"Remove-NetFirewallRule -DisplayName {ps_quote(FIREWALL_RULE)} -ErrorAction SilentlyContinue; "
            f"New-NetFirewallRule -DisplayName {ps_quote(FIREWALL_RULE)} -Direction Inbound -Action Allow "
            f"-Protocol UDP -Program {ps_quote(program)} -RemoteAddress LocalSubnet -Profile Any | Out-Null")


def network_problems(report: dict, program: str, port: int) -> list[NetworkProblem]:
    """What stops other computers from reaching the server, with the PowerShell that fixes it."""
    profiles = report.get("profiles") or []
    active = set(report.get("active") or [])
    watched = [p for p in profiles if p.get("enabled") == "True" and (not active or p.get("name") in active)]
    if not watched:  # the firewall is off for this network
        return []
    problems: list[NetworkProblem] = []

    rule = report.get("rule")
    if not rule:
        problems.append(NetworkProblem("Windows Firewall has no rule that lets the players in.",
                                       kit_rule_script(program)))
    elif rule.get("enabled") != "True":
        problems.append(NetworkProblem(f'The firewall rule "{FIREWALL_RULE}" is turned off.', kit_rule_script(program)))
    # an empty value is one Windows wouldn't show without admin rights: unknown, so not counted as changed
    elif not (rule.get("action") == "Allow" and rule.get("direction") == "Inbound"
              and rule.get("protocol") in ("UDP", "Any", "")
              and (not rule.get("program") or _same_program(rule.get("program"), program))
              and (rule.get("profile") == "Any" or all(p["name"] in rule.get("profile", "") for p in watched))
              and (not rule.get("remote") or {"LocalSubnet", "Any"} & set(rule["remote"]))):
        problems.append(NetworkProblem(
            f'The firewall rule "{FIREWALL_RULE}" was changed and no longer lets the players in.',
            kit_rule_script(program)))

    for block in report.get("blocks") or []:
        name = block.get("display") or block.get("name")
        if _same_program(block.get("program"), program):
            message = (f'Windows Firewall blocks the server (rule "{name}", usually made by clicking Cancel '
                       "when Windows asked to allow it).")
            problems.append(NetworkProblem(message, f"Remove-NetFirewallRule -Name {ps_quote(block['name'])}"))
        elif (block.get("protocol") in ("UDP", "Any") and block.get("program") in (None, "", "Any")
              and _port_listed(port, block.get("ports") or [])):
            problems.append(NetworkProblem(f'Windows Firewall rule "{name}" blocks port {port}.',
                                           f"Disable-NetFirewallRule -Name {ps_quote(block['name'])}"))

    shut = [p["name"] for p in watched if p.get("allow_inbound") == "False"]
    if shut:
        problems.append(NetworkProblem(
            f"Windows Firewall blocks ALL incoming connections on this network ({', '.join(shut)}).",
            f"Set-NetFirewallProfile -Profile {','.join(shut)} -AllowInboundRules True"))
    if any(p.get("local_rules") == "False" for p in watched):
        message = ("This computer's firewall is managed by an organization, which ignores the kit's rule. "
                   f"Ask whoever manages it to allow port {port} for World of PADMAN.")
        problems.append(NetworkProblem(message, None))
    return problems


START_APPS_CACHE = 10.0  # seconds; asking Windows takes about a second, and the AI tab asks for several apps
_start_apps: tuple[float, dict[str, str]] = (0.0, {})


def parse_start_apps(text: str) -> dict[str, str]:
    """Get-StartApps as JSON -> {app name: AppID} (the first one wins when a name is listed twice)."""
    try:
        data = json.loads(text.strip() or "[]")
    except ValueError:
        return {}
    apps: dict[str, str] = {}
    for entry in data if isinstance(data, list) else [data]:
        if isinstance(entry, dict) and entry.get("Name") and entry.get("AppID"):
            apps.setdefault(str(entry["Name"]), str(entry["AppID"]))
    return apps


def start_apps() -> dict[str, str]:
    """The Start menu's apps, as Windows opens them."""
    global _start_apps
    read_at, apps = _start_apps
    if time.monotonic() - read_at > START_APPS_CACHE:
        apps = parse_start_apps(powershell("Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress").stdout)
        _start_apps = (time.monotonic(), apps)
    return apps


class WindowsBehavior(PlatformBehavior):
    name = "windows"
    firewall_name = "Windows Firewall"
    elevation_hint = ('Windows will now ask for permission ("Do you want to allow this app to make changes?").\n'
                      "Click YES. This only lets World of PADMAN players on your own network in, nothing from the internet.")
    elevation_short = "Windows will ask for permission; click Yes."
    server_bin = Path("wopded.x86_64.exe")
    client_bin = Path("wop.x86_64.exe")
    uv_name = "uv.exe"
    playit_asset = "windows-x64"
    exe_suffix = ".exe"
    run_script_name = "run-server.cmd"
    launcher_name = "wopkit.cmd"
    keyboard_is_stdin = True

    def default_root(self) -> Path:
        return Path(os.environ["LOCALAPPDATA"]) / "WoPServer"

    def wanted_in_game_zip(self, name: str) -> bool:
        if name.endswith("/") or name.startswith("XTRAS/"):
            return False
        top, _, rest = name.partition("/")
        if not rest:                                   # files next to the game binaries
            return name.endswith((".exe", ".dll", ".md"))
        return top == "wop" and name.endswith((".pk3", ".cfg", ".dll"))

    def find_existing_game(self) -> Path | None:
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            game = Path(base) / "World of PADMAN 1.7.0" if base else None
            if game and (game / self.server_bin).exists() and (game / "wop" / "wop_maps_1.7.0.pk3").exists():
                return game
        return None

    def run_scripts(self, root: Path, port: int, env: dict[str, str], uv: Path, wopkit: Path, game: Path,
                    server_cmd: Callable[[str], str]) -> dict[Path, str]:
        env_lines = "\r\n".join(f'set "{k}={v}"' for k, v in env.items())
        join_info = f'"{uv}" run --offline --quiet --script "{wopkit}" joininfo'
        run = ("@echo off\r\n"
               "rem Made by the WoP Server Kit (rewritten on every start). Runs the game server.\r\n"
               "title World of PADMAN server\r\n"
               f'set "PORT={port}"\r\n{env_lines}\r\n'
               f'"{uv}" run --offline --quiet --script "{wopkit}" banner\r\n'
               f'start "World of PADMAN - how to join" {join_info}\r\n'
               f'cd /d "{game}"\r\n'
               f"{server_cmd('%PORT%')}\r\n"
               "if errorlevel 1 (echo. & echo The server stopped with an error. & pause) else (timeout /t 3 >nul)\r\n")
        launcher = ("@echo off\r\nrem Made by the WoP Server Kit. Usage: wopkit.cmd start^|stop^|uninstall\r\n"
                    f'{env_lines}\r\n"{uv}" run --script "{wopkit}" %*\r\n')
        return {root / self.run_script_name: run, root / self.launcher_name: launcher}

    def make_executable(self, path: Path) -> None:
        pass

    def launch_hidden(self, argv: list[str], cwd: Path) -> None:
        # The server gets an invisible console of its own. It has to outlive whoever started it, but uv runs
        # Python (and so the app's helper and the Claude connection) in a job that ends all its children with
        # it. Breaking away from that job is the quick way; when the job doesn't allow it, Windows' own process
        # service (WMI) starts the server, so it isn't a child of ours at all.
        # Its input and output must stay that console: the server crashes (access violation) when they're
        # redirected to a file, a pipe or nothing.
        try:
            subprocess.Popen(argv, cwd=str(cwd), close_fds=True,
                             creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB)
            return
        except PermissionError:
            pass
        command = subprocess.list2cmdline(argv)
        script = ("$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow = 0}\n"
                  "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{"
                  f"CommandLine = {ps_quote(command)}; CurrentDirectory = {ps_quote(cwd)}; "
                  "ProcessStartupInformation = $startup}\n"
                  "exit $r.ReturnValue")
        if powershell(script).returncode != 0:
            raise OSError("Windows didn't start the server.")

    def find_processes(self, *markers: str) -> list[int]:
        # The query runs encoded, so this PowerShell's own command line never matches it
        script = ("$m = @(" + ", ".join(ps_quote(m) for m in markers) + ")\n"
                  "Get-CimInstance Win32_Process | Where-Object { $c = $_.CommandLine; $c -and -not ($m | "
                  "Where-Object { $c.IndexOf($_, [StringComparison]::OrdinalIgnoreCase) -lt 0 }) } | "
                  "ForEach-Object { $_.ProcessId }")
        out = powershell(script).stdout
        return [int(line) for line in out.split() if line.isdigit() and int(line) != os.getpid()]

    def end_process(self, pid: int) -> None:
        # /T: what it started goes too (the internet-play keeper's playit program)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True,
                       creationflags=CREATE_NO_WINDOW)

    def start_child_hidden(self, argv: list[str], cwd: Path) -> subprocess.Popen:
        return subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, close_fds=True, creationflags=CREATE_NO_WINDOW)

    def try_lock(self, path: Path) -> object | None:
        import msvcrt
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+")  # noqa: SIM115 (kept open while the lock is held)
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return None
        return handle

    def release_lock(self, handle: object) -> None:
        import msvcrt
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()

    def playit_socket(self, folder: Path, port: int) -> str:
        return rf"\\.\pipe\wop-server-playit-{port}"

    def open_in_window(self, script: Path) -> None:
        # Hand the script to the running Explorer instead of starting it ourselves: AI apps can put
        # MCP servers in a job object that kills every child when the app closes, and Explorer's
        # child is outside that job (and runs with normal rights, like a double-click).
        subprocess.run(["explorer.exe", str(script)], check=False)

    def run_script_here(self, script: Path) -> int:
        return subprocess.call(["cmd.exe", "/c", str(script)])

    def remove_folder_after_exit(self, folder: Path) -> None:
        # uv.exe (running this script) is inside the folder, so delete it once we've exited
        subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{folder}"', creationflags=CREATE_NO_WINDOW)

    def open_url(self, url: str) -> None:
        os.startfile(url)  # noqa: S606

    def open_path(self, path: Path) -> None:
        os.startfile(str(path))  # noqa: S606

    def play_game(self, game: Path) -> None:
        subprocess.Popen([str(game / self.client_bin)], cwd=str(game),
                         creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)

    def run_elevated(self, commands: list[str], terminal: bool) -> bool:
        """Windows shows its own permission dialog either way."""
        encoded = base64.b64encode("; ".join(commands).encode("utf-16-le")).decode()
        outer = (f"try {{ $p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
                 f"-ArgumentList '-NoProfile','-EncodedCommand','{encoded}'; exit $p.ExitCode }} catch {{ exit 1223 }}")
        return powershell(outer).returncode == 0

    def firewall_check(self, program: str, port: int, inst: dict) -> FirewallCheck:
        report = network_report(port)
        if report is None:
            return FirewallCheck(None)
        if report.get("rule"):
            inst["firewall"] = program  # so uninstall removes the rule
        return FirewallCheck(network_problems(report, program, port), report.get("others") or [])

    def firewall_removal(self, inst: dict) -> list[str]:
        if not inst.get("firewall"):
            return []
        return [f"Remove-NetFirewallRule -DisplayName {ps_quote(FIREWALL_RULE)} -ErrorAction SilentlyContinue"]

    def network_adapters(self) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for line in powershell(ADDRESSES).stdout.splitlines():
            ip, _, name = line.strip().partition("\t")
            if ip and not ip.startswith("169.254.") and ip not in [a for a, _ in found]:
                found.append((ip, name))
        return found

    def user_config_dir(self) -> Path:
        return Path(os.environ["APPDATA"])

    def desktop_dir(self) -> Path:
        out = powershell("[Environment]::GetFolderPath('Desktop')").stdout.strip()
        return Path(out) if out else Path.home() / "Desktop"

    def make_shortcuts(self, folder: Path, shortcuts: list[Shortcut], web_links: dict[str, str]) -> list[Path]:
        made = []
        lines = ["$s = New-Object -ComObject WScript.Shell"]
        for sc in shortcuts:
            path = folder / f"{sc.name}.lnk"
            lines += [f"$l = $s.CreateShortcut({ps_quote(path)})",
                      f"$l.TargetPath = {ps_quote(sc.target)}", f"$l.Arguments = {ps_quote(' '.join(sc.args))}",
                      f"$l.WorkingDirectory = {ps_quote(sc.workdir or sc.target.parent)}"]
            if sc.icon:
                lines.append(f"$l.IconLocation = {ps_quote(f'{sc.icon},0')}")
            lines.append("$l.Save()")
            made.append(path)
        powershell("\n".join(lines))
        for name, url in web_links.items():
            link = folder / f"{name}.url"
            link.write_text(f"[InternetShortcut]\r\nURL={url}\r\n", encoding="utf-8", newline="")
            made.append(link)
        return made

    # ------------------------------------------------------------------ other apps

    def find_app(self, name: str) -> str | None:
        app_id = start_apps().get(name)
        return "shell:AppsFolder\\" + app_id if app_id else None

    def open_found_app(self, handle: str) -> None:
        subprocess.Popen(["explorer.exe", handle])

    def open_terminal(self, command: list[str], title: str) -> None:
        # start gives the command a console window of its own; cmd /k keeps it open afterwards
        subprocess.Popen(["cmd.exe", "/c", "start", title, "cmd.exe", "/k", subprocess.list2cmdline(command)],
                         creationflags=CREATE_NO_WINDOW)

    # ------------------------------------------------------------------ Claude Desktop

    def claude_config_paths(self) -> list[Path]:
        paths = [Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"]
        # The Store version may keep its settings in its own package folder
        for pkg in (Path(os.environ["LOCALAPPDATA"]) / "Packages").glob("Claude_*"):
            virtual = pkg / "LocalCache" / "Roaming" / "Claude"
            if virtual.is_dir():
                paths.append(virtual / "claude_desktop_config.json")
        return paths

    def claude_app(self) -> str | None:
        found = self.find_app("Claude")
        if found:
            return found
        squirrel = Path(os.environ["LOCALAPPDATA"]) / "AnthropicClaude" / "claude.exe"
        return str(squirrel) if squirrel.exists() else None

    def claude_running(self) -> bool:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq claude.exe", "/NH"], capture_output=True, text=True,
                             creationflags=CREATE_NO_WINDOW).stdout
        return "claude.exe" in out.lower()

    def open_claude(self, app: str) -> None:
        if app.startswith("shell:"):
            subprocess.run(["explorer.exe", app], check=False)
        else:
            subprocess.Popen([app], creationflags=DETACHED_PROCESS)

    def quit_claude(self) -> None:
        subprocess.run(["taskkill", "/IM", "claude.exe", "/F"], capture_output=True, creationflags=CREATE_NO_WINDOW)
        for _ in range(20):
            time.sleep(0.5)
            if not self.claude_running():
                return

    claude_asset = "windows"

    def install_claude(self, download: Path) -> None:
        # Claude's own installer, just for this user. It shows its progress and opens Claude when it's done.
        # It takes no "quiet" option (an unknown option makes it stop right away).
        subprocess.run([str(download)], check=False)
