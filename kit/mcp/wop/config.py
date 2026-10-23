"""Where the server files are, and how to reach the server.

The kit installs everything in one folder (Windows: %LOCALAPPDATA%\\WoPServer, Mac:
~/Library/Application Support/WoPServer):

    <root>/kit/mcp/...            this MCP server
    <root>/home/wop/              server-friends.cfg, teams.cfg, logs
    <root>/install.json           port, game folder, server name (written by the setup)
    <root>/run-server.cmd         (Mac: .command, Linux: .sh) runs the game server in a window

Claude Desktop passes WOP_HOME and WOP_START_SCRIPT, so nothing is guessed. Without them the
paths are worked out from this file's location. The port is read from install.json (or the start
script) and the rcon password from server-friends.cfg, so they're never stored twice.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PORT = 27960


def home_dir() -> Path:
    return Path(os.environ.get("WOP_HOME") or ROOT / "home")


def cfg_dir() -> Path:
    """home/wop: server-friends.cfg, teams.cfg, mode.cfg and the logs."""
    return home_dir() / "wop"


def server_cfg() -> Path:
    return cfg_dir() / "server-friends.cfg"


def teams_cfg() -> Path:
    return cfg_dir() / "teams.cfg"


def root_dir() -> Path:
    """The kit's install folder (home/ is inside it)."""
    return home_dir().parent


def install() -> dict:
    """install.json: port, game_dir, server_name, ... ({} before the first setup)."""
    try:
        data = json.loads((root_dir() / "install.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def start_script(name: str) -> Path:
    """The script that runs the server in a window; name is the OS's file name for it (run-server.cmd...)."""
    if os.environ.get("WOP_START_SCRIPT"):
        return Path(os.environ["WOP_START_SCRIPT"])
    return root_dir() / name


def port() -> int:
    if os.environ.get("WOP_PORT"):
        return int(os.environ["WOP_PORT"])
    if isinstance(install().get("port"), int):
        return install()["port"]
    if not os.environ.get("WOP_START_SCRIPT"):
        return DEFAULT_PORT
    try:
        text = Path(os.environ["WOP_START_SCRIPT"]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return DEFAULT_PORT
    match = (re.search(r'(?im)^\s*(?:set\s+)?"?PORT=(\d+)', text)
             or re.search(r"net_port\s+(\d+)", text))
    return int(match.group(1)) if match else DEFAULT_PORT


def cfg_value(name: str, path: Path | None = None) -> str | None:
    """Last `set <name> "<value>"` in server-friends.cfg (or path) that isn't commented out."""
    text = (path or server_cfg()).read_text(encoding="utf-8", errors="replace")
    found = None
    for line in text.splitlines():
        line = line.split("//", 1)[0]
        match = re.match(rf'\s*seta?\s+{re.escape(name)}\s+(?:"([^"]*)"|(\S+))', line, re.IGNORECASE)
        if match:
            found = match.group(1) if match.group(1) is not None else match.group(2)
    return found


def setting(name: str) -> str | None:
    """A setting as server-friends.cfg leaves it when the server starts (None if it isn't set there)."""
    try:
        return cfg_value(name)
    except OSError:
        return None


def rcon_password() -> str:
    if os.environ.get("WOP_RCON_PASSWORD"):
        return os.environ["WOP_RCON_PASSWORD"]
    found = cfg_value("rconpassword")
    if not found:
        raise RuntimeError(f"No rconpassword set in {server_cfg()}")
    return found


def server_name() -> str:
    return cfg_value("sv_hostname") or "WoP server"


def join_password() -> str:
    return cfg_value("g_password") or ""
