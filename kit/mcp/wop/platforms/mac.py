"""Mac: the application firewall (socketfilterfw), Rosetta on Apple silicon, Terminal windows."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .base import FirewallCheck, NetworkProblem, Shortcut
from .posix import PosixBehavior

SOCKETFILTERFW = "/usr/libexec/ApplicationFirewall/socketfilterfw"


def socketfilterfw(*args: str) -> str:
    """Ask the macOS application firewall something (no admin needed); its answer in lower case."""
    try:
        out = subprocess.run([SOCKETFILTERFW, *args], capture_output=True, text=True, check=False).stdout
    except OSError:
        return ""
    return (out or "").lower()


def applescript_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class MacBehavior(PosixBehavior):
    name = "mac"
    firewall_name = "your Mac's firewall"
    elevation_hint = "You may be asked for your Mac password (typing it shows nothing; press Enter after)."
    elevation_short = "You may be asked for your Mac password (typing it shows nothing; press Enter after)."
    server_bin = Path("wopded.x86_64.app/Contents/MacOS/wopded.x86_64")
    client_bin = Path("wop.x86_64.app")
    run_script_name = "run-server.command"

    def default_root(self) -> Path:
        return Path.home() / "Library" / "Application Support" / "WoPServer"

    def wanted_in_game_zip(self, name: str) -> bool:
        if name.endswith("/") or name.startswith("XTRAS/"):
            return False
        top, _, rest = name.partition("/")
        if not rest:
            return name.endswith((".dylib", ".md"))
        if top == "wop":
            return name.endswith((".pk3", ".cfg", ".dylib"))
        return top in ("wop.x86_64.app", "wopded.x86_64.app")

    def prepare_game(self, game: Path) -> None:
        for app in ("wop.x86_64.app", "wopded.x86_64.app"):
            for binary in (game / app / "Contents" / "MacOS").glob("*"):
                binary.chmod(0o755)

    def needs_rosetta(self) -> bool:
        if os.uname().machine != "arm64":
            return False
        return subprocess.run(["/usr/bin/arch", "-x86_64", "/usr/bin/true"], capture_output=True).returncode != 0

    def rosetta_command(self) -> str | None:
        return "/usr/sbin/softwareupdate --install-rosetta --agree-to-license"

    def run_scripts(self, root: Path, port: int, env: dict[str, str], uv: Path, wopkit: Path, game: Path,
                    server_cmd: Callable[[str], str]) -> dict[Path, str]:
        env_lines = self.env_lines(env)
        join_script = root / "join-info.command"  # opened in its own Terminal window
        join = f'#!/bin/bash\n{env_lines}\n"{uv}" run --offline --quiet --script "{wopkit}" joininfo\n'
        run = ("#!/bin/bash\n# Made by the WoP Server Kit (rewritten on every start). Runs the game server.\n"
               f"PORT={port}\n{env_lines}\n"
               f'"{uv}" run --offline --quiet --script "{wopkit}" banner\n'
               f'open -a Terminal "{join_script}"\n'
               f'cd "{game}"\n'
               f"{server_cmd('$PORT')}\n")
        launcher = f'#!/bin/bash\n{env_lines}\nexec "{uv}" run --script "{wopkit}" "$@"\n'
        return {join_script: join, root / self.run_script_name: run, root / self.launcher_name: launcher}

    def user_config_dir(self) -> Path:
        return Path.home() / "Library" / "Application Support"

    def open_in_window(self, script: Path) -> None:
        subprocess.run(["open", "-a", "Terminal", str(script)], check=False)

    def open_url(self, url: str) -> None:
        subprocess.run(["open", url], check=False)

    def open_path(self, path: Path) -> None:
        subprocess.run(["open", str(path)], check=False)

    def play_game(self, game: Path) -> None:
        subprocess.run(["open", str(game / self.client_bin)], check=False)

    def _elevate_gui(self, script: str) -> bool:
        # The Mac's own password dialog, as installers show it
        apple = f"do shell script {applescript_quote(script)} with administrator privileges"
        return subprocess.run(["osascript", "-e", apple], capture_output=True, check=False).returncode == 0

    def firewall_check(self, program: str, port: int, inst: dict) -> FirewallCheck:
        """The Mac firewall is off by default. When it's on, it would block (or ask about) the server every time."""
        if "enabled" not in socketfilterfw("--getglobalstate"):
            return FirewallCheck([])
        problems = []
        permitted = "permitted" in socketfilterfw("--getappblocked", program)
        if permitted:
            inst["firewall"] = program  # so uninstall removes the permission
        else:
            q = self.quote(program)
            problems.append(NetworkProblem("Your Mac's firewall doesn't let the server in.",
                                           f"{SOCKETFILTERFW} --add {q}; {SOCKETFILTERFW} --unblockapp {q}"))
        if "enabled" in socketfilterfw("--getblockall"):
            problems.append(NetworkProblem("Your Mac's firewall blocks ALL incoming connections.",
                                           f"{SOCKETFILTERFW} --setblockall off"))
        return FirewallCheck(problems)

    def firewall_removal(self, inst: dict) -> list[str]:
        return [f"{SOCKETFILTERFW} --remove {self.quote(inst['firewall'])}"] if inst.get("firewall") else []

    def make_shortcuts(self, folder: Path, shortcuts: list[Shortcut], web_links: dict[str, str]) -> list[Path]:
        made = []
        for sc in shortcuts:
            if sc.app:  # Finder opens a link to an .app like the app itself
                path = folder / f"{sc.name}.app"
                if path.is_symlink() or path.exists():
                    path.unlink()
                path.symlink_to(sc.target)
            else:
                path = folder / f"{sc.name}.command"
                args = " ".join(self.quote(a) for a in sc.args)
                path.write_text(f'#!/bin/bash\nexec "{sc.target}" {args}\n', encoding="utf-8", newline="\n")
                path.chmod(0o755)
            made.append(path)
        for name, url in web_links.items():  # a .webloc opens in the browser
            link = folder / f"{name}.webloc"
            link.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict><key>URL</key>'
                f"<string>{url}</string></dict></plist>\n", encoding="utf-8", newline="\n")
            made.append(link)
        return made

    # ------------------------------------------------------------------ Claude Desktop

    def claude_config_paths(self) -> list[Path]:
        return [Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"]

    def claude_app(self) -> str | None:
        for app in (Path("/Applications/Claude.app"), Path.home() / "Applications" / "Claude.app"):
            if app.exists():
                return str(app)
        return None

    def claude_running(self) -> bool:
        return subprocess.run(["pgrep", "-x", "Claude"], capture_output=True).returncode == 0

    def open_claude(self, app: str) -> None:
        subprocess.run(["open", app], check=False)

    def quit_claude(self) -> None:
        subprocess.run(["osascript", "-e", 'tell application "Claude" to quit'], check=False)
        for _ in range(20):
            time.sleep(0.5)
            if not self.claude_running():
                return

    def can_install_claude(self) -> bool:
        return bool(shutil.which("brew"))

    def install_claude(self) -> None:
        subprocess.run(["brew", "install", "--cask", "claude"], check=False)
