"""Where the server files are, and how to reach the server.

The kit installs everything in one folder (Windows: %LOCALAPPDATA%\\WoPServer, Mac:
~/Library/Application Support/WoPServer):

    <root>/kit/mcp/...            this MCP server
    <root>/home/wop/              server-friends.cfg, teams.cfg, logs
    <root>/Start WoP Server.cmd   (Mac: .command) starts the game server

Claude Desktop passes WOP_HOME and WOP_START_SCRIPT, so nothing is guessed. Without them the
paths are worked out from this file's location. The port is read from the start script and the
rcon password from server-friends.cfg, so they're never stored twice.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PORT = 27960
IS_MAC = sys.platform == "darwin"


def home_dir() -> Path:
    return Path(os.environ.get("WOP_HOME") or ROOT / "home")


def cfg_dir() -> Path:
    """home/wop: server-friends.cfg, teams.cfg, mode.cfg and the logs."""
    return home_dir() / "wop"


def server_cfg() -> Path:
    return cfg_dir() / "server-friends.cfg"


def teams_cfg() -> Path:
    return cfg_dir() / "teams.cfg"


def start_script() -> Path:
    if os.environ.get("WOP_START_SCRIPT"):
        return Path(os.environ["WOP_START_SCRIPT"])
    return ROOT / ("Start WoP Server.command" if IS_MAC else "Start WoP Server.cmd")


def port() -> int:
    if os.environ.get("WOP_PORT"):
        return int(os.environ["WOP_PORT"])
    try:
        text = start_script().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return DEFAULT_PORT
    match = (re.search(r'(?im)^\s*(?:set\s+)?"?PORT=(\d+)', text)
             or re.search(r"net_port\s+(\d+)", text))
    return int(match.group(1)) if match else DEFAULT_PORT


def _cfg_value(name: str) -> str | None:
    """Last `set <name> "<value>"` in server-friends.cfg that isn't commented out."""
    text = server_cfg().read_text(encoding="utf-8", errors="replace")
    found = None
    for line in text.splitlines():
        line = line.split("//", 1)[0]
        match = re.match(rf'\s*seta?\s+{re.escape(name)}\s+(?:"([^"]*)"|(\S+))', line, re.IGNORECASE)
        if match:
            found = match.group(1) if match.group(1) is not None else match.group(2)
    return found


def rcon_password() -> str:
    if os.environ.get("WOP_RCON_PASSWORD"):
        return os.environ["WOP_RCON_PASSWORD"]
    found = _cfg_value("rconpassword")
    if not found:
        raise RuntimeError(f"No rconpassword set in {server_cfg()}")
    return found


def server_name() -> str:
    return _cfg_value("sv_hostname") or "WoP server"


def join_password() -> str:
    return _cfg_value("g_password") or ""
