"""How the game server is started: the same arguments for the run-server window and the hidden start.

The server writes everything it prints to home/wop/qconsole.log (logfile 2), so a server started
without a window can still be followed (the app's Logs tab) and checked (actions.Game).
"""

from __future__ import annotations

from pathlib import Path

from .platforms import PlatformBehavior


def server_args(game: Path, home: Path, port: int | str) -> list[str]:
    return ["+set", "fs_basepath", str(game), "+set", "fs_homepath", str(home), "+set", "logfile", "2",
            "+set", "dedicated", "1", "+set", "net_port", str(port), "+set", "com_hunkMegs", "128",
            "+exec", "server-friends.cfg"]


def script_line(behavior: PlatformBehavior, game: Path, home: Path, port_var: str) -> str:
    """The line in run-server.* that runs the server; port_var is %PORT% or $PORT."""
    paths = {str(game), str(home)}
    args = " ".join(f'"{a}"' if a in paths else a for a in server_args(game, home, port_var))
    return f'"{game / behavior.server_bin}" {args}'


def launch_server(behavior: PlatformBehavior, game: Path, home: Path, port: int) -> None:
    """Start the server without a window. It keeps running when whoever started it closes."""
    behavior.launch_hidden([str(game / behavior.server_bin), *server_args(game, home, port)], cwd=game)
