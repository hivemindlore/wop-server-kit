"""Linux: ufw or firewalld, pkexec for the password dialog, .desktop shortcuts, the desktop's own terminal."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .base import FirewallCheck, NetworkProblem, Shortcut
from .posix import PosixBehavior

# Terminal programs and how each is told to run a command, most generic first
TERMINALS = [("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]),
             ("xfce4-terminal", ["-x"]), ("mate-terminal", ["-x"]), ("kgx", ["-e"]), ("xterm", ["-e"])]
UFW_CONF = Path("/etc/ufw/ufw.conf")
UFW_RULES = Path("/etc/ufw/user.rules")
RULE_COMMENT = "WoP Server Kit"


def _run(*cmd: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None


def terminal_command(argv: list[str]) -> list[str] | None:
    for program, flag in TERMINALS:
        if shutil.which(program):
            return [program, *flag, *argv]
    return None


def ufw_enabled() -> bool:
    if not shutil.which("ufw") and not Path("/usr/sbin/ufw").exists():
        return False
    try:
        return bool(re.search(r"(?m)^\s*ENABLED\s*=\s*yes", UFW_CONF.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def ufw_allows(port: int) -> bool | None:
    """Whether ufw's own rules let the port in; None when they can only be read as administrator."""
    try:
        text = UFW_RULES.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return bool(re.search(rf"-A ufw-user-input -p udp .*--dport {port}\b.*-j ACCEPT", text)
                or re.search(rf"-A ufw-user-input .*--dport {port}\b.*-j ACCEPT", text))


def firewalld_running() -> bool:
    out = _run("firewall-cmd", "--state")
    return bool(out and out.stdout.strip() == "running")


class LinuxBehavior(PosixBehavior):
    name = "linux"
    firewall_name = "the firewall"
    elevation_hint = "Your computer will ask for your password, so the players on your network can connect."
    elevation_short = "You may be asked for your password."
    server_bin = Path("wopded.x86_64")
    client_bin = Path("wop.x86_64")
    run_script_name = "run-server.sh"
    gui_elevation = ["pkexec"]

    def default_root(self) -> Path:
        data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(data) / "WoPServer"

    def wanted_in_game_zip(self, name: str) -> bool:
        if name.endswith("/") or name.startswith("XTRAS/"):
            return False
        top, _, rest = name.partition("/")
        if not rest:
            return name in ("wop.x86_64", "wopded.x86_64") or name.endswith((".so", ".md"))
        return top == "wop" and name.endswith((".pk3", ".cfg", ".so"))

    def prepare_game(self, game: Path) -> None:
        for binary in (self.server_bin, self.client_bin):
            if (game / binary).exists():
                (game / binary).chmod(0o755)

    def run_scripts(self, root: Path, port: int, env: dict[str, str], uv: Path, wopkit: Path, game: Path,
                    server_cmd: Callable[[str], str]) -> dict[Path, str]:
        env_lines = self.env_lines(env)
        join_script = root / "join-info.sh"
        join = f'#!/bin/bash\n{env_lines}\n"{uv}" run --offline --quiet --script "{wopkit}" joininfo\n'
        # The "how to join" text gets its own terminal window if there's a terminal program to open one with
        terminals = " ".join(f"{program}:{flag[0]}" for program, flag in TERMINALS)
        run = ("#!/bin/bash\n# Made by the WoP Server Kit (rewritten on every start). Runs the game server.\n"
               f"PORT={port}\n{env_lines}\n"
               f'"{uv}" run --offline --quiet --script "{wopkit}" banner\n'
               f"for t in {terminals}; do\n"
               '    if command -v "${t%%:*}" >/dev/null 2>&1; then\n'
               f'        "${{t%%:*}}" "${{t#*:}}" "{join_script}" >/dev/null 2>&1 &\n'
               "        break\n"
               "    fi\n"
               "done\n"
               f'cd "{game}"\n'
               f"{server_cmd('$PORT')}\n")
        launcher = f'#!/bin/bash\n{env_lines}\nexec "{uv}" run --script "{wopkit}" "$@"\n'
        return {join_script: join, root / self.run_script_name: run, root / self.launcher_name: launcher}

    def user_config_dir(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")

    def open_in_window(self, script: Path) -> None:
        cmd = terminal_command([str(script)])
        if cmd:
            subprocess.Popen(cmd, start_new_session=True)
        else:  # no terminal program: run it without a window
            subprocess.Popen(["/bin/bash", str(script)], start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def open_url(self, url: str) -> None:
        subprocess.Popen(["xdg-open", url], start_new_session=True)

    def open_path(self, path: Path) -> None:
        subprocess.Popen(["xdg-open", str(path)], start_new_session=True)

    def firewall_check(self, program: str, port: int, inst: dict) -> FirewallCheck:
        if firewalld_running():
            out = _run("firewall-cmd", f"--query-port={port}/udp")
            if out and out.returncode == 0:
                inst["firewall"] = f"firewalld:{port}"
                return FirewallCheck([])
            return FirewallCheck([NetworkProblem(
                "The firewall doesn't let the players in.",
                f"firewall-cmd --add-port={port}/udp; firewall-cmd --permanent --add-port={port}/udp")])
        if ufw_enabled():
            allowed = ufw_allows(port)
            if allowed is None:  # only the administrator can read ufw's rules: trust what the kit did before
                allowed = inst.get("firewall") == f"ufw:{port}"
            if allowed:
                return FirewallCheck([])
            return FirewallCheck([NetworkProblem(
                "The firewall (ufw) doesn't let the players in.",
                f"ufw allow {port}/udp comment '{RULE_COMMENT}'")])
        return FirewallCheck([])

    def after_fix(self, problems: list[NetworkProblem], port: int, inst: dict) -> None:
        if any(p.fix and p.fix.startswith("ufw ") for p in problems):
            inst["firewall"] = f"ufw:{port}"

    def firewall_removal(self, inst: dict) -> list[str]:
        tool, _, port = str(inst.get("firewall") or "").partition(":")
        if tool == "ufw":
            return [f"ufw delete allow {port}/udp"]
        if tool == "firewalld":
            return [f"firewall-cmd --remove-port={port}/udp; firewall-cmd --permanent --remove-port={port}/udp"]
        return []

    def network_adapters(self) -> list[tuple[str, str]]:
        """Addresses of the connections that have a router (default route), with their names."""
        routes = _run("ip", "-4", "route", "show", "default")
        addrs = _run("ip", "-4", "-o", "addr", "show")
        if not routes or not addrs:
            return []
        devices = re.findall(r"\bdev (\S+)", routes.stdout)
        found = []
        for line in addrs.stdout.splitlines():
            match = re.match(r"\d+:\s+(\S+)\s+inet (\d+\.\d+\.\d+\.\d+)/", line)
            if match and match.group(1) in devices and not match.group(2).startswith(("127.", "169.254.")):
                found.append((match.group(2), match.group(1)))
        return found

    def desktop_dir(self) -> Path:
        out = _run("xdg-user-dir", "DESKTOP")
        if out and out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
        return Path.home() / "Desktop"

    def make_shortcuts(self, folder: Path, shortcuts: list[Shortcut], web_links: dict[str, str]) -> list[Path]:
        made = []
        for sc in shortcuts:
            path = folder / f"{sc.name}.desktop"
            exec_line = " ".join(f'"{part}"' for part in [str(sc.target), *sc.args])
            lines = ["[Desktop Entry]", "Type=Application", f"Name={sc.name}", f"Exec={exec_line}",
                     f"Terminal={'false' if sc.app else 'true'}"]
            if sc.workdir:
                lines.append(f"Path={sc.workdir}")
            if sc.icon:
                lines.append(f"Icon={sc.icon}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            made.append(path)
        for name, url in web_links.items():
            path = folder / f"{name}.desktop"
            path.write_text(f"[Desktop Entry]\nType=Link\nName={name}\nURL={url}\nIcon=help-browser\n",
                            encoding="utf-8", newline="\n")
            made.append(path)
        for path in made:
            path.chmod(0o755)
            _run("gio", "set", str(path), "metadata::trusted", "true")  # GNOME: allow launching without asking
        return made
