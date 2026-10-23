"""What differs between Windows, Mac and Linux, behind one interface (the Strategy pattern).

detect() picks the behavior for this computer once; the setup, the app bridge and the Claude connection
get it passed in and only call its methods, so no other file asks which OS it runs on.
Commands that need admin rights are collected as strings in the OS's own language (PowerShell on
Windows, sh elsewhere) and run together by run_elevated, so the user is asked for permission once.
"""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NetworkProblem:
    text: str              # what's wrong, in plain words
    fix: str | None        # a command for run_elevated, or None when the kit can't fix it


@dataclass
class FirewallCheck:
    problems: list[NetworkProblem] | None = None   # None: the firewall settings couldn't be read
    others: list[str] = field(default_factory=list)  # other security software that may block players


@dataclass
class Shortcut:
    name: str              # "Start WoP Server" (the OS adds its own extension)
    target: Path           # program or script to run
    args: list[str] = field(default_factory=list)
    workdir: Path | None = None
    icon: Path | None = None
    app: bool = False      # a link to the game itself (Play) instead of a kit command


class PlatformBehavior(ABC):
    name: str = ""                 # windows / mac / linux
    firewall_name: str = "the firewall"
    elevation_hint: str = ""       # said just before the OS asks for permission to let the players in
    elevation_short: str = ""      # the same for anything else ("You may be asked for your Mac password.")
    server_bin: Path = Path()      # relative to the game folder
    client_bin: Path = Path()
    uv_name: str = "uv"
    run_script_name: str = ""      # the script that runs the server in a window
    launcher_name: str = "wopkit.sh"
    keyboard_is_stdin: bool = False  # Windows: questions are always read from stdin, even when it's piped

    # ------------------------------------------------------------------ files and game

    @abstractmethod
    def default_root(self) -> Path:
        """Where the kit installs itself."""

    @abstractmethod
    def wanted_in_game_zip(self, name: str) -> bool:
        """Which files of the official WoP zip this OS needs."""

    def prepare_game(self, game: Path) -> None:
        """After unpacking: e.g. make the programs executable."""

    def find_existing_game(self) -> Path | None:
        """A World of PADMAN 1.7.0 the user installed themselves, if the kit can reuse it."""
        return None

    def needs_rosetta(self) -> bool:
        return False

    def rosetta_command(self) -> str | None:
        return None

    @abstractmethod
    def run_scripts(self, root: Path, port: int, env: dict[str, str], uv: Path, wopkit: Path, game: Path,
                    server_cmd: Callable[[str], str]) -> dict[Path, str]:
        """The run-server script that shows the server in a window, the wopkit launcher and helpers.
        server_cmd(port_variable) is the line that runs the server. Returns {path: text} to write."""

    def make_executable(self, path: Path) -> None:
        path.chmod(0o755)

    # ------------------------------------------------------------------ running things

    @abstractmethod
    def launch_hidden(self, argv: list[str], cwd: Path) -> None:
        """Start the game server without a window, detached so it outlives whoever started it."""

    @abstractmethod
    def open_in_window(self, script: Path) -> None:
        """Run a kit script in its own visible window, like double-clicking it."""

    @abstractmethod
    def run_script_here(self, script: Path) -> int:
        """Run a kit script in this text window (the setup hands over to run-server this way)."""

    @abstractmethod
    def remove_folder_after_exit(self, folder: Path) -> None:
        """Delete the kit folder (uninstall), even though the running uv/Python live in it."""

    @abstractmethod
    def open_url(self, url: str) -> None: ...

    @abstractmethod
    def open_path(self, path: Path) -> None:
        """Open a file, folder or app with the OS (Explorer / Finder / the file manager)."""

    def play_game(self, game: Path) -> None:
        subprocess.Popen([str(game / self.client_bin)], cwd=str(game), start_new_session=True)

    @abstractmethod
    def run_elevated(self, commands: list[str], terminal: bool) -> bool:
        """Run commands as administrator, asking once. terminal: ask in the text window instead of a
        dialog (Mac/Linux sudo). False if the user said no or it failed."""

    # ------------------------------------------------------------------ network

    @abstractmethod
    def firewall_check(self, program: str, port: int, inst: dict) -> FirewallCheck:
        """What stops other computers from reaching the server. Records in inst["firewall"] what
        uninstall has to undo."""

    def after_fix(self, problems: list[NetworkProblem], port: int, inst: dict) -> None:
        """Called when run_elevated applied the fixes for these problems."""

    def firewall_removal(self, inst: dict) -> list[str]:
        """Commands for run_elevated that undo what the kit allowed (uninstall)."""
        return []

    def network_adapters(self) -> list[tuple[str, str]]:
        """(address, connection name) of the networks with a router; [] if the OS can't say."""
        return []

    # ------------------------------------------------------------------ playing over the internet (playit.gg)

    playit_asset: str | None = None   # which of kit.json's playit downloads runs here; None: not available here
    exe_suffix: str = ""              # added to program file names (.exe)

    def playit_socket(self, folder: Path, port: int) -> str:
        """Where the playit program listens for its own commands: one per install, so it never meets another
        playit on this computer."""
        return str(folder / "playitd.sock")

    @abstractmethod
    def start_child_hidden(self, argv: list[str], cwd: Path) -> subprocess.Popen:
        """Start a helper program without a window, as a child that ends with whoever started it."""

    @abstractmethod
    def try_lock(self, path: Path) -> object | None:
        """Lock a file so only one process at a time does a job; None if another process holds it.
        The lock goes away with the process, also when it crashes."""

    @abstractmethod
    def release_lock(self, handle: object) -> None: ...

    # ------------------------------------------------------------------ desktop

    def desktop_dir(self) -> Path:
        return Path.home() / "Desktop"

    @abstractmethod
    def user_config_dir(self) -> Path:
        """Where apps keep their settings (AppData/Roaming, Library/Application Support, ~/.config)."""

    @abstractmethod
    def make_shortcuts(self, folder: Path, shortcuts: list[Shortcut], web_links: dict[str, str]) -> list[Path]:
        """Write the shortcuts and web links into folder; return the files made."""

    # ------------------------------------------------------------------ other apps (the AI tab's Open button)

    @abstractmethod
    def find_app(self, name: str) -> str | None:
        """An installed app by the name people know it by ("LM Studio"): a handle for open_found_app, or None."""

    @abstractmethod
    def open_found_app(self, handle: str) -> None: ...

    @abstractmethod
    def open_terminal(self, command: list[str], title: str) -> None:
        """A terminal window that runs command and stays open (for programs like Claude Code)."""

    # ------------------------------------------------------------------ Claude Desktop

    def claude_config_paths(self) -> list[Path]:
        return []

    def claude_app(self) -> str | None:
        """How to open Claude Desktop, or None if it isn't installed (or doesn't exist for this OS)."""
        return None

    def claude_running(self) -> bool:
        return False

    def open_claude(self, app: str) -> None:
        pass

    def quit_claude(self) -> None:
        pass

    claude_asset: str | None = None   # which of kit.json's "claude_desktop" downloads installs it here

    def install_claude(self, download: Path) -> None:
        """Install Claude Desktop from its downloaded claude_asset, without asking anything; returns when done."""

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def env_path(name: str, default: Path) -> Path:
        value = os.environ.get(name)
        return Path(value) if value else default
