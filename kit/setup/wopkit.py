# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""WoP Server Kit: installs, updates, starts and stops a World of PADMAN LAN server,
and connects Claude Desktop to it.

    wopkit.py start       first time: set everything up; every time: update, then run the server
    wopkit.py stop        stop the server
    wopkit.py banner      the "how to join" text shown when the server window opens
    wopkit.py uninstall   remove everything again

Started by start-wop-server.bat / start-wop-server.sh (first time) and by the desktop shortcuts.
Only uses the Python standard library; uv provides Python.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]          # <root>/kit
ROOT = KIT.parent
sys.path.insert(0, str(KIT / "mcp"))

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
SETTINGS = json.loads((KIT / "kit.json").read_text(encoding="utf-8"))

HOME = ROOT / "home"
CFG = HOME / "wop"
TOOLS = ROOT / "tools"
UV = TOOLS / ("uv.exe" if IS_WIN else "uv")
INSTALL_JSON = ROOT / "install.json"
RUN_SERVER = ROOT / ("run-server.cmd" if IS_WIN else "run-server.command")
LAUNCHER = ROOT / ("wopkit.cmd" if IS_WIN else "wopkit.sh")
WOPKIT = KIT / "setup" / "wopkit.py"
SERVER_BIN = Path("wopded.x86_64.exe") if IS_WIN else Path("wopded.x86_64.app/Contents/MacOS/wopded.x86_64")
CLIENT_BIN = Path("wop.x86_64.exe") if IS_WIN else Path("wop.x86_64.app")
FIREWALL_RULE = "WoP Server Kit"
NEED_FREE_GB = 3

# uv keeps its Python and packages inside the kit folder, so uninstalling removes everything
UV_ENV = {
    "UV_CACHE_DIR": str(ROOT / "cache" / "uv"),
    "UV_PYTHON_INSTALL_DIR": str(ROOT / "python"),
    "UV_PYTHON_PREFERENCE": "only-managed",
}
os.environ.update(UV_ENV)
os.environ["WOP_HOME"] = str(HOME)
os.environ["WOP_START_SCRIPT"] = str(RUN_SERVER)


# --------------------------------------------------------------------------- talking to the user

def say(text: str = "") -> None:
    print(text, flush=True)


def step(text: str) -> None:
    say(f"\n>> {text}")


def _tty_input(prompt: str) -> str:
    """input() that also works under `curl ... | bash`, where stdin is the script itself."""
    if IS_WIN or (sys.stdin and sys.stdin.isatty()):
        try:
            return input(prompt).lstrip("﻿")  # piped input from PowerShell starts with a BOM
        except EOFError:
            return ""
    try:
        with open("/dev/tty", "r+") as tty:
            tty.write(prompt)
            tty.flush()
            return tty.readline().rstrip("\n")
    except OSError:
        return ""


def ask(question: str, default: str) -> str:
    answer = _tty_input(f"{question} [{default}]: ").strip()
    return answer or default


def yes(question: str, default: bool = True) -> bool:
    if os.environ.get("WOP_ASSUME_YES"):
        return default
    hint = "Y/n" if default else "y/N"
    answer = _tty_input(f"{question} ({hint}): ").strip().lower()
    return default if not answer else answer.startswith(("y", "j"))


def pause(seconds: float | None = None) -> None:
    if seconds is not None:
        time.sleep(seconds)
    elif not os.environ.get("WOP_ASSUME_YES"):
        _tty_input("Press Enter to close this window...")


# --------------------------------------------------------------------------- small helpers

def load_install() -> dict:
    try:
        return json.loads(INSTALL_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_install(inst: dict) -> None:
    INSTALL_JSON.write_text(json.dumps(inst, indent=2), encoding="utf-8")


def kit_version() -> str:
    try:
        return (KIT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def _version_tuple(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in v.strip().split("."))


def powershell(script: str, check: bool = False) -> subprocess.CompletedProcess:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, text=True, check=check)


def ps_quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def open_url(url: str) -> None:
    if IS_WIN:
        os.startfile(url)  # noqa: S606
    else:
        subprocess.run(["open", url], check=False)


def fetch(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "wop-server-kit"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(url: str, dest: Path, expected_size: int | None = None) -> None:
    """Download with a progress line; continues a half-finished download."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = dest.stat().st_size if dest.exists() else 0
    if expected_size and have == expected_size:
        return
    headers = {"User-Agent": "wop-server-kit"}
    if have:
        headers["Range"] = f"bytes={have}-"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        if have and r.status != 206:      # server ignored the range: start over
            have = 0
        total = expected_size or (have + int(r.headers.get("Content-Length") or 0))
        last = -1
        with open(dest, "ab" if have else "wb") as f:
            while chunk := r.read(1024 * 1024):
                f.write(chunk)
                have += len(chunk)
                if total:
                    pct = int(have * 100 / total)
                    if pct != last:
                        last = pct
                        print(f"\r   {pct:3d}%  ({have / 1e9:.2f} of {total / 1e9:.2f} GB)", end="", flush=True)
    print(flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def clean_name(text: str) -> str:
    return "".join(c for c in text if c.isprintable() and c not in '"\\;\ufeff').strip()[:40]


def server_running(port: int) -> bool:
    from wop.rcon import Rcon
    try:
        return Rcon(port=port).is_running(retry=True)
    except Exception:  # noqa: BLE001 (no config yet, ...)
        return False


def desktop_dir() -> Path:
    if os.environ.get("WOP_DESKTOP"):
        return Path(os.environ["WOP_DESKTOP"])
    if IS_WIN:
        out = powershell("[Environment]::GetFolderPath('Desktop')").stdout.strip()
        if out:
            return Path(out)
    return Path.home() / "Desktop"


# --------------------------------------------------------------------------- update

def remote_version_and_zip() -> tuple[str, str] | None:
    """(version, zip url) of the newest kit, or None when offline."""
    override = os.environ.get("WOP_KIT_URL")
    if override:  # a local zip, for testing updates
        path = Path(override.removeprefix("file:///").removeprefix("file://"))
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith("kit/VERSION"))
            return z.read(name).decode().strip(), str(path)
    repo, branch = SETTINGS["repo"], SETTINGS["branch"]
    try:
        version = fetch(f"https://raw.githubusercontent.com/{repo}/{branch}/kit/VERSION", timeout=5).decode().strip()
    except OSError:
        return None
    return version, f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"


def install_kit_zip(zip_path: Path) -> None:
    """Replace <root>/kit with the kit/ folder from a repo zip. home/, game/ etc. stay untouched."""
    new, old = ROOT / "kit.new", ROOT / "kit.old"
    shutil.rmtree(new, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            parts = info.filename.split("/", 1)
            if len(parts) < 2 or not parts[1].startswith("kit/") or info.is_dir():
                continue
            target = new / parts[1][len("kit/"):]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    KIT.rename(old)
    new.rename(KIT)
    shutil.rmtree(old, ignore_errors=True)


def maybe_update() -> None:
    found = remote_version_and_zip()
    if not found:
        return
    version, url = found
    if _version_tuple(version) <= _version_tuple(kit_version()):
        return
    step(f"Updating the WoP Server Kit from {kit_version()} to {version}...")
    if Path(url).exists():
        zip_path = Path(url)
    else:
        zip_path = Path(tempfile.gettempdir()) / "wop-server-kit-update.zip"
        zip_path.write_bytes(fetch(url, timeout=60))
    install_kit_zip(zip_path)
    say("   Updated. Restarting with the new version...")
    sys.exit(subprocess.call([str(UV), "run", "--script", str(WOPKIT), *sys.argv[1:], "--no-update"]))


# --------------------------------------------------------------------------- game

def game_ok(game: Path) -> bool:
    return (game / SERVER_BIN).exists() and (game / "wop" / "wop_maps_1.7.0.pk3").exists()


def find_existing_wop() -> Path | None:
    if not IS_WIN:
        return None
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base and game_ok(Path(base) / "World of PADMAN 1.7.0"):
            return Path(base) / "World of PADMAN 1.7.0"
    return None


def _wanted(name: str) -> bool:
    if name.endswith("/") or name.startswith("XTRAS/"):
        return False
    top, _, rest = name.partition("/")
    if not rest:                                   # files next to the game binaries
        if IS_WIN:
            return name.endswith((".exe", ".dll", ".md"))
        return name.endswith((".dylib", ".md"))
    if top == "wop":
        return name.endswith((".pk3", ".cfg", ".dll" if IS_WIN else ".dylib"))
    return IS_MAC and top in ("wop.x86_64.app", "wopded.x86_64.app")


def ensure_game(inst: dict) -> Path:
    if inst.get("game_dir") and game_ok(Path(inst["game_dir"])):
        return Path(inst["game_dir"])
    existing = None if os.environ.get("WOP_FORCE_DOWNLOAD") else find_existing_wop()
    if existing:
        step(f"Found World of PADMAN already installed in {existing}; using that.")
        inst["game_dir"], inst["game_reused"] = str(existing), True
        return existing

    game = ROOT / "game"
    step("Downloading World of PADMAN 1.7.0 (1.2 GB, from the official WoP website on GitHub).")
    say("   This only happens once. It can take a while on slow internet; you can leave it running.")
    free = shutil.disk_usage(ROOT).free / 1e9
    if free < NEED_FREE_GB:
        raise SystemExit(f"   Not enough disk space: {free:.1f} GB free, about {NEED_FREE_GB} GB needed.")
    zip_path = ROOT / "downloads" / "wop-1.7.0-unified.zip"
    local = os.environ.get("WOP_GAME_ZIP")  # testing: use an already downloaded copy
    if local:
        zip_path = Path(local)
    else:
        download(SETTINGS["wop_zip_url"], zip_path, SETTINGS["wop_zip_size"])
    say("   Checking the download...")
    if sha256(zip_path) != SETTINGS["wop_zip_sha256"]:
        if not local:
            zip_path.unlink(missing_ok=True)
        raise SystemExit("   The download is damaged. Run the kit again to download it again.")

    say("   Unpacking...")
    partial = ROOT / "game.partial"
    shutil.rmtree(partial, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if _wanted(info.filename):
                z.extract(info, partial)
    if IS_MAC:
        for app in ("wop.x86_64.app", "wopded.x86_64.app"):
            for binary in (partial / app / "Contents" / "MacOS").glob("*"):
                binary.chmod(0o755)
    shutil.rmtree(game, ignore_errors=True)
    partial.rename(game)
    if not local:
        shutil.rmtree(ROOT / "downloads", ignore_errors=True)
    inst["game_dir"], inst["game_reused"] = str(game), False
    say("   World of PADMAN is ready.")
    return game


# --------------------------------------------------------------------------- server files

def ensure_server_files(inst: dict, game: Path) -> None:
    CFG.mkdir(parents=True, exist_ok=True)
    cfg = CFG / "server-friends.cfg"
    if not cfg.exists():
        template = (KIT / "server" / "server-friends.cfg").read_text(encoding="utf-8")
        password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
        text = template.replace("__SERVER_NAME__", inst["server_name"]).replace("__RCON_PASSWORD__", password)
        cfg.write_text(text, encoding="utf-8")
    for name in ("teams.cfg", "mode.cfg"):
        if not (CFG / name).exists():
            shutil.copyfile(KIT / "server" / name, CFG / name)

    port = inst["port"]
    server = game / SERVER_BIN

    def server_args(port_var: str) -> str:
        return (f'+set fs_basepath "{game}" +set fs_homepath "{HOME}" +set logfile 2 +set dedicated 1 '
                f'+set net_port {port_var} +set com_hunkMegs 128 +exec server-friends.cfg')

    if IS_WIN:
        env = "\r\n".join(f'set "{k}={v}"' for k, v in UV_ENV.items())
        RUN_SERVER.write_text(
            "@echo off\r\n"
            "rem Made by the WoP Server Kit (rewritten on every start). Runs the game server.\r\n"
            "title World of PADMAN server\r\n"
            f'set "PORT={port}"\r\n{env}\r\n'
            f'"{UV}" run --offline --quiet --script "{WOPKIT}" banner\r\n'
            f'cd /d "{game}"\r\n'
            f'"{server}" {server_args("%PORT%")}\r\n'
            "if errorlevel 1 (echo. & echo The server stopped with an error. & pause) else (timeout /t 3 >nul)\r\n",
            encoding="utf-8", newline="")
        LAUNCHER.write_text(
            "@echo off\r\nrem Made by the WoP Server Kit. Usage: wopkit.cmd start^|stop^|uninstall\r\n"
            f'{env}\r\n"{UV}" run --script "{WOPKIT}" %*\r\n', encoding="utf-8", newline="")
    else:
        env = "\n".join(f'export {k}="{v}"' for k, v in UV_ENV.items())
        RUN_SERVER.write_text(
            "#!/bin/bash\n# Made by the WoP Server Kit (rewritten on every start). Runs the game server.\n"
            f"PORT={port}\n{env}\n"
            f'"{UV}" run --offline --quiet --script "{WOPKIT}" banner\n'
            f'cd "{game}"\n'
            f'"{server}" {server_args("$PORT")}\n',
            encoding="utf-8", newline="\n")
        LAUNCHER.write_text(f'#!/bin/bash\n{env}\nexec "{UV}" run --script "{WOPKIT}" "$@"\n', encoding="utf-8",
                            newline="\n")
        RUN_SERVER.chmod(0o755)
        LAUNCHER.chmod(0o755)


# --------------------------------------------------------------------------- firewall / Rosetta

def firewall_rule_program() -> str | None:
    out = powershell(f"$r = Get-NetFirewallRule -DisplayName {ps_quote(FIREWALL_RULE)} -ErrorAction SilentlyContinue;"
                     " if ($r) { ($r | Get-NetFirewallApplicationFilter).Program }").stdout.strip()
    return out.splitlines()[0] if out else None


def run_elevated(script: str) -> bool:
    """Run PowerShell as administrator (Windows shows its permission prompt). False if declined."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    outer = (f"try {{ $p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
             f"-ArgumentList '-NoProfile','-EncodedCommand','{encoded}'; exit $p.ExitCode }} catch {{ exit 1223 }}")
    return powershell(outer).returncode == 0


def ensure_firewall(inst: dict, game: Path) -> None:
    if os.environ.get("WOP_SKIP_FIREWALL"):
        return
    program = str(game / SERVER_BIN)
    if (firewall_rule_program() or "").lower() == program.lower():
        return
    step("Letting the players on your network connect.")
    say("   Windows will now ask for permission (\"Do you want to allow this app to make changes?\").")
    say("   Click YES. This only allows World of PADMAN players on your own network, nothing from the internet.")
    rule = (f"Remove-NetFirewallRule -DisplayName {ps_quote(FIREWALL_RULE)} -ErrorAction SilentlyContinue; "
            f"New-NetFirewallRule -DisplayName {ps_quote(FIREWALL_RULE)} -Direction Inbound -Action Allow "
            f"-Protocol UDP -Program {ps_quote(program)} -RemoteAddress LocalSubnet -Profile Any | Out-Null")
    if run_elevated(rule) and (firewall_rule_program() or "").lower() == program.lower():
        say("   Done.")
        inst["firewall"] = program
    else:
        say("   Skipped. The server still works, but other computers may not be able to connect.")
        say("   Run Start WoP Server again to retry.")


def ensure_rosetta() -> None:
    if not IS_MAC or os.uname().machine != "arm64":
        return
    if subprocess.run(["/usr/bin/arch", "-x86_64", "/usr/bin/true"], capture_output=True).returncode == 0:
        return
    step("World of PADMAN is made for Intel Macs; your Mac needs Apple's free \"Rosetta\" to run it.")
    say("   You may be asked for your Mac password (typing it shows nothing; press Enter after).")
    subprocess.run(["sudo", "/usr/sbin/softwareupdate", "--install-rosetta", "--agree-to-license"], check=False)


# --------------------------------------------------------------------------- Claude Desktop

def claude_config_paths() -> list[Path]:
    if os.environ.get("WOP_CLAUDE_CONFIG"):
        return [Path(os.environ["WOP_CLAUDE_CONFIG"])]
    if IS_MAC:
        return [Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"]
    paths = [Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"]
    # The Store version may keep its settings in its own package folder
    for pkg in (Path(os.environ["LOCALAPPDATA"]) / "Packages").glob("Claude_*"):
        virtual = pkg / "LocalCache" / "Roaming" / "Claude"
        if virtual.is_dir():
            paths.append(virtual / "claude_desktop_config.json")
    return paths


def claude_control() -> bool:
    """False in tests (WOP_NO_CLAUDE_LAUNCH): never look at, quit or open the real Claude Desktop."""
    return not os.environ.get("WOP_NO_CLAUDE_LAUNCH")


def claude_app() -> str | None:
    """How to open Claude Desktop, or None if it isn't installed."""
    if "WOP_CLAUDE_APP" in os.environ:
        return os.environ["WOP_CLAUDE_APP"] or None
    if IS_MAC:
        for app in (Path("/Applications/Claude.app"), Path.home() / "Applications" / "Claude.app"):
            if app.exists():
                return str(app)
        return None
    out = powershell("(Get-StartApps | Where-Object { $_.Name -eq 'Claude' } | Select-Object -First 1).AppID").stdout
    if out.strip():
        return "shell:AppsFolder\\" + out.strip()
    squirrel = Path(os.environ["LOCALAPPDATA"]) / "AnthropicClaude" / "claude.exe"
    return str(squirrel) if squirrel.exists() else None


def claude_running() -> bool:
    if not claude_control():
        return False
    if IS_MAC:
        return subprocess.run(["pgrep", "-x", "Claude"], capture_output=True).returncode == 0
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq claude.exe", "/NH"], capture_output=True, text=True).stdout
    return "claude.exe" in out.lower()


def open_claude(app: str) -> None:
    if not claude_control():
        return
    if IS_MAC:
        subprocess.run(["open", app], check=False)
    elif app.startswith("shell:"):
        subprocess.run(["explorer.exe", app], check=False)
    else:
        subprocess.Popen([app], creationflags=subprocess.DETACHED_PROCESS)


def quit_claude() -> None:
    if not claude_control():
        return
    if IS_MAC:
        subprocess.run(["osascript", "-e", 'tell application "Claude" to quit'], check=False)
    else:
        subprocess.run(["taskkill", "/IM", "claude.exe", "/F"], capture_output=True)
    for _ in range(20):
        time.sleep(0.5)
        if not claude_running():
            return


def install_claude() -> None:
    page = SETTINGS["claude_download_page"]
    if not claude_control():
        return
    if IS_WIN and shutil.which("winget"):
        say("   Installing Claude Desktop (this can take a minute)...")
        subprocess.run(["winget", "install", "--id", "Anthropic.Claude", "-e", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements"], check=False)
        return
    if IS_MAC and shutil.which("brew"):
        subprocess.run(["brew", "install", "--cask", "claude"], check=False)
        return
    say(f"   Opening {page}. Download and install Claude Desktop, then come back here.")
    open_url(page)
    _tty_input("   Press Enter when Claude Desktop is installed...")


def mcp_entry() -> dict:
    return {
        "command": str(UV),
        "args": ["run", "--script", str(KIT / "mcp" / "server.py")],
        "env": {"WOP_HOME": str(HOME), "WOP_START_SCRIPT": str(RUN_SERVER), **UV_ENV},
    }


def set_claude_entry(entry: dict | None) -> bool:
    """Add (or with None remove) our server in Claude's config. True if a file changed."""
    name, changed = SETTINGS["mcp_name"], False
    for path in claude_config_paths():
        try:
            config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            say(f"   Couldn't read {path} (not valid JSON); left it alone.")
            continue
        servers = config.setdefault("mcpServers", {})
        if (servers.get(name) == entry) or (entry is None and name not in servers):
            continue
        if path.exists() and not path.with_name(path.name + ".before-wop-kit").exists():
            shutil.copyfile(path, path.with_name(path.name + ".before-wop-kit"))
        if entry is None:
            servers.pop(name, None)
        else:
            servers[name] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        changed = True
    return changed


def ensure_mcp_ready() -> bool:
    step("Preparing the Claude connection (downloads a few small parts the first time)...")
    for attempt in range(3):
        # Antivirus scanning fresh downloads can make the first try fail ("failed to persist temporary file")
        proc = subprocess.run([str(UV), "run", "--quiet", "--script", str(KIT / "mcp" / "server.py"), "--selftest"],
                              capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.startswith("ok"):
            say("   Ready.")
            return True
        time.sleep(2 * (attempt + 1))
    say("   That didn't work, so Claude can't manage the server yet. The server itself works fine.")
    say("   Check your internet connection and run Start WoP Server again.")
    details = (proc.stderr or proc.stdout).strip().splitlines()
    if details:
        say(f"   (details: {details[-1][:200]})")
    return False


def ensure_claude(inst: dict, first_run: bool) -> None:
    app = claude_app()
    if not app and not inst.get("claude_declined"):
        step("Claude Desktop lets you change the game by just asking (\"switch to Capture The Lolly\").")
        if yes("   Claude Desktop isn't installed. Install it now?"):
            install_claude()
            app = claude_app()
            if not app:
                say("   Claude Desktop still isn't found. You can install it later from "
                    f"{SETTINGS['claude_download_page']} and run Start WoP Server again.")
        else:
            inst["claude_declined"] = True
            say(f"   OK. You can install it later from {SETTINGS['claude_download_page']}.")

    changed = set_claude_entry(mcp_entry())
    if not app:
        return
    if changed and claude_running():
        say("\n   Claude Desktop needs a restart to connect to your server.")
        if yes("   Restart Claude Desktop now?"):
            quit_claude()
            open_claude(app)
    elif not claude_running() and (changed or first_run or inst.get("open_claude", True)):
        open_claude(app)
    if changed:
        say("   Claude Desktop is connected to your server. In Claude, try: \"What's running on my WoP server?\"")


# --------------------------------------------------------------------------- shortcuts

def ensure_shortcuts(inst: dict, game: Path) -> None:
    if os.environ.get("WOP_SKIP_SHORTCUTS"):
        return
    try:
        _make_shortcuts(inst, game)
    except OSError as e:  # e.g. the Mac asked "allow access to Desktop?" and the answer was no
        say(f"   Couldn't put the shortcuts on your desktop ({e.strerror or e}).")
        say(f"   Start the server later by running this kit again, or with {LAUNCHER} start")


def _make_shortcuts(inst: dict, game: Path) -> None:
    desk = desktop_dir()
    help_url = f"https://github.com/{SETTINGS['repo']}#readme"
    made = []
    if IS_WIN:
        icon = f"{game / CLIENT_BIN},0"
        links = [("Start WoP Server", LAUNCHER, "start", ROOT),
                 ("Stop WoP Server", LAUNCHER, "stop", ROOT)]
        if not inst.get("game_reused"):
            links.append(("Play World of PADMAN", game / CLIENT_BIN, "", game))
        lines = ["$s = New-Object -ComObject WScript.Shell"]
        for name, target, args, workdir in links:
            lines += [f"$l = $s.CreateShortcut({ps_quote(desk / (name + '.lnk'))})",
                      f"$l.TargetPath = {ps_quote(target)}", f"$l.Arguments = {ps_quote(args)}",
                      f"$l.WorkingDirectory = {ps_quote(workdir)}", f"$l.IconLocation = {ps_quote(icon)}",
                      "$l.Save()"]
            made.append(desk / (name + ".lnk"))
        powershell("\n".join(lines))
        help_link = desk / "WoP Server Help.url"
        help_link.write_text(f"[InternetShortcut]\r\nURL={help_url}\r\n", encoding="utf-8", newline="")
        made.append(help_link)
    else:
        for name, body in {"Start WoP Server.command": f'exec "{LAUNCHER}" start\n',
                           "Stop WoP Server.command": f'"{LAUNCHER}" stop\n'}.items():
            path = desk / name
            path.write_text("#!/bin/bash\n" + body, encoding="utf-8", newline="\n")
            path.chmod(0o755)
            made.append(path)
        # Finder opens a link to an .app like the app itself, and a .webloc in the browser
        play = desk / "Play World of PADMAN.app"
        if play.is_symlink() or play.exists():
            play.unlink()
        play.symlink_to(game / CLIENT_BIN)
        made.append(play)
        help_link = desk / "WoP Server Help.webloc"
        help_link.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict><key>URL</key>'
            f"<string>{help_url}</string></dict></plist>\n", encoding="utf-8", newline="\n")
        made.append(help_link)
    inst["shortcuts"] = [str(p) for p in made if p.exists() or p.is_symlink()]


# --------------------------------------------------------------------------- commands

def cmd_banner(_args) -> None:
    from wop import config
    from wop.actions import Game
    inst = load_install()
    port = inst.get("port", SETTINGS["default_port"])
    ips = Game.lan_addresses()
    suffix = "" if port == 27960 else f":{port}"
    line = "=" * 74
    say(line)
    say(f'  World of PADMAN server "{config.server_name()}" is starting.')
    say("")
    say("  Players on your network: World of PADMAN -> Multiplayer -> LAN -> Join.")
    if ips:
        say(f"  Not in the list? Press ~ in the game and type:  /connect {ips[0]}{suffix}")
    say(f"  Players need World of PADMAN 1.7.0 (free): {SETTINGS['wop_download_page']}")
    say("")
    say("  Want another map, game mode, bots or weapons? Just ask Claude, for example:")
    say('     "Switch to Capture The Lolly with 4 bots on each team"')
    say("")
    say("  Keep this window open while you play. Close it (or use Stop WoP Server) to stop.")
    say(line)


def cmd_start(args) -> None:
    say("WoP Server Kit " + kit_version())
    if not args.no_update:
        maybe_update()
    inst = load_install()
    first_run = not inst
    if first_run:
        say("\nHi! This sets up a World of PADMAN server for the players on your network,")
        say("and connects it to Claude so you can change the game by just asking.")
    inst.setdefault("port", int(os.environ.get("WOP_PORT") or SETTINGS["default_port"]))
    if not inst.get("server_name"):
        default = f"{getpass.getuser()}'s WoP server"
        inst["server_name"] = clean_name(ask("\nWhat should your server be called?", default)) or default
    save_install(inst)

    game = ensure_game(inst)
    save_install(inst)
    ensure_server_files(inst, game)
    if IS_WIN:
        ensure_firewall(inst, game)
    ensure_rosetta()
    if ensure_mcp_ready():
        ensure_claude(inst, first_run)
    ensure_shortcuts(inst, game)
    inst["version"] = kit_version()
    save_install(inst)

    if server_running(inst["port"]):
        say("\nThe server is already running (in its own window).")
        pause(8)
        return
    if first_run:
        say("\nAll set! From now on, start the server with \"Start WoP Server\" on your desktop.")
    say("\nStarting the server...\n")
    if os.environ.get("WOP_NO_SERVER"):
        return
    if IS_WIN:
        sys.exit(subprocess.call(["cmd.exe", "/c", str(RUN_SERVER)]))
    os.execv("/bin/bash", ["bash", str(RUN_SERVER)])


def cmd_stop(_args) -> None:
    from wop.rcon import Rcon, ServerOffline
    port = load_install().get("port", SETTINGS["default_port"])
    if not server_running(port):
        say("The WoP server isn't running.")
        pause(3)
        return
    try:
        Rcon(port=port).command("quit", timeout=1.0)
    except ServerOffline:
        pass
    say("The WoP server is stopping.")
    pause(3)


def cmd_uninstall(_args) -> None:
    inst = load_install()
    say("This removes the WoP server, its settings and the desktop shortcuts from this computer.")
    if inst.get("game_reused"):
        say(f"(Your World of PADMAN game in {inst['game_dir']} stays.)")
    if _tty_input('Type "yes" to remove everything: ').strip().lower() != "yes":
        say("Nothing removed.")
        pause()
        return
    port = inst.get("port", SETTINGS["default_port"])
    if server_running(port):
        cmd_stop(None)
    if IS_WIN and inst.get("firewall"):
        say("Windows will ask for permission to remove the firewall rule; click Yes.")
        run_elevated(f"Remove-NetFirewallRule -DisplayName {ps_quote(FIREWALL_RULE)} -ErrorAction SilentlyContinue")
    set_claude_entry(None)
    for shortcut in inst.get("shortcuts", []):
        Path(shortcut).unlink(missing_ok=True)
    say("Removed. The WoP Server folder is deleted after this window closes.")
    if IS_WIN:
        # uv.exe (running this script) is inside the folder, so delete it once we've exited
        subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{ROOT}"',
                         creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        shutil.rmtree(ROOT, ignore_errors=True)
    pause(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="WoP Server Kit")
    parser.add_argument("command", choices=["start", "stop", "banner", "uninstall"])
    parser.add_argument("--no-update", action="store_true")
    args = parser.parse_args()
    try:
        {"start": cmd_start, "stop": cmd_stop, "banner": cmd_banner, "uninstall": cmd_uninstall}[args.command](args)
    except KeyboardInterrupt:
        say("\nStopped.")
    except SystemExit as e:
        if e.code not in (None, 0) and isinstance(e.code, str):
            say(e.code)
            pause()
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
