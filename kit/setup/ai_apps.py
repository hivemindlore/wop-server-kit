"""The AI apps the kit can connect to the server, and how each one is told about it.

Each app that can use the server keeps a list of helper programs in a settings file; connecting adds the
kit's entry (the Claude connection in kit/mcp) to that list. The user only sees "Connect" / "Connected".
Apps that can't use a server on the home network get a card with advice instead (connectable=False).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from wop.platforms import PlatformBehavior

BACKUP_SUFFIX = ".before-wop-kit"

EXAMPLES = ["What's running on my server?", "Switch to Capture The Lolly with 4 bots on each team.",
            "How do my friends join?"]


@dataclass
class AiApp:
    id: str
    name: str
    blurb: str
    cost: str                                     # "free" (runs on this computer) or "account"
    download_url: str
    config_paths: Callable[[PlatformBehavior], list[Path]] = lambda os_: []
    installed: Callable[[PlatformBehavior], bool] = lambda os_: False
    key: str = "mcpServers"                       # where the app keeps its list of helper programs
    entry_type: str | None = None                 # some apps want "type": "stdio" in the entry
    finish_hint: str = ""                         # what to do after connecting
    connectable: bool = True
    advice: str = ""                              # for apps that can't connect
    examples: list[str] = field(default_factory=lambda: list(EXAMPLES))
    launch_name: str | None = None                # the app's name in the Start menu / Applications / app menu
    terminal: list[str] | None = None             # or: a program that runs in a terminal window
    can_restart: bool = False                     # the kit can close and reopen it (so a new connection applies)
    installable: Callable[[PlatformBehavior], bool] = lambda os_: False  # the kit can download and install it

    def available(self, os_: PlatformBehavior) -> bool:
        return not self.connectable or bool(self.config_paths(os_))


def _home(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _claude_desktop_paths(os_: PlatformBehavior) -> list[Path]:
    if os.environ.get("WOP_CLAUDE_CONFIG"):  # testing: a copy of the Claude config
        return [Path(os.environ["WOP_CLAUDE_CONFIG"])]
    return os_.claude_config_paths()


APPS: list[AiApp] = [
    AiApp(
        id="claude-desktop", name="Claude Desktop",
        blurb="The Claude app for your computer. Chat with Claude and let it run your server.",
        cost="account", download_url="https://claude.ai/download",
        config_paths=lambda os_: _claude_desktop_paths(os_),
        installed=lambda os_: os_.claude_app() is not None,
        finish_hint="Quit Claude Desktop completely and open it again, then ask it something about your server.",
        launch_name="Claude", can_restart=True,
        installable=lambda os_: bool(os_.claude_asset),
    ),
    AiApp(
        id="lm-studio", name="LM Studio",
        blurb="Runs AI models on your own computer: free, private, no account. Pick a model that can use tools "
              "(for example Qwen or Llama), then ask it about your server.",
        cost="free", download_url="https://lmstudio.ai/download",
        config_paths=lambda os_: [_home(".lmstudio", "mcp.json")],
        installed=lambda os_: _exists(_home(".lmstudio")),
        finish_hint="Restart LM Studio. In a chat, turn on \"wop-server\" in the tools (plug icon) list.",
        launch_name="LM Studio",
    ),
    AiApp(
        id="claude-code", name="Claude Code",
        blurb="Claude for people who like to tinker. Also used by the Code tab in Claude Desktop.",
        cost="account", download_url="https://claude.com/product/claude-code",
        config_paths=lambda os_: [_home(".claude.json")],
        installed=lambda os_: bool(shutil.which("claude")) or _exists(_home(".claude.json")),
        entry_type="stdio",
        finish_hint="Start a new Claude Code session to use your server.",
        terminal=["claude"],
    ),
    AiApp(
        id="cursor", name="Cursor",
        blurb="A code editor with AI built in.",
        cost="account", download_url="https://cursor.com/download",
        config_paths=lambda os_: [_home(".cursor", "mcp.json")],
        installed=lambda os_: _exists(_home(".cursor")),
        finish_hint="Restart Cursor.",
        launch_name="Cursor",
    ),
    AiApp(
        id="vscode", name="VS Code",
        blurb="Visual Studio Code with GitHub Copilot chat.",
        cost="account", download_url="https://code.visualstudio.com/download",
        config_paths=lambda os_: [os_.user_config_dir() / "Code" / "User" / "mcp.json"],
        installed=lambda os_: _exists(os_.user_config_dir() / "Code" / "User"),
        key="servers", entry_type="stdio",
        finish_hint="Restart VS Code and use Copilot chat in Agent mode.",
        launch_name="Visual Studio Code",
    ),
    AiApp(
        id="ollama", name="Ollama", cost="free", download_url="https://ollama.com/download",
        blurb="Runs AI models on your own computer.",
        installed=lambda os_: bool(shutil.which("ollama")),
        connectable=False,
        advice="Ollama runs AI models, but it can't control programs like your server on its own. "
               "For the same kind of free, private models that can run your server, use LM Studio (above).",
    ),
    AiApp(
        id="chatgpt", name="ChatGPT", cost="account", download_url="https://chatgpt.com/download",
        blurb="OpenAI's chat app.",
        connectable=False,
        advice="ChatGPT can only connect to services on the internet, not to a server on your home network. "
               "Use Claude Desktop (free account) or LM Studio (free, no account) instead.",
    ),
]


def find(app_id: str) -> AiApp:
    for app in APPS:
        if app.id == app_id:
            return app
    raise KeyError(app_id)


def _read(path: Path) -> dict | None:
    """The settings file as a dict; {} if it doesn't exist yet, None if it isn't valid (then it's left alone)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def set_entry(paths: list[Path], key: str, name: str, entry: dict | None) -> bool:
    """Add (or with None remove) our entry under data[key][name] in each settings file.
    Keeps one backup of the file as it was before the kit first touched it. True if a file changed."""
    changed = False
    for path in paths:
        config = _read(path)
        if config is None:
            continue
        servers = config.setdefault(key, {})
        if not isinstance(servers, dict) or servers.get(name) == entry or (entry is None and name not in servers):
            continue
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if path.exists() and not backup.exists():
            shutil.copyfile(path, backup)
        if entry is None:
            servers.pop(name, None)
        else:
            servers[name] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        changed = True
    return changed


def app_entry(app: AiApp, entry: dict) -> dict:
    return {"type": app.entry_type, **entry} if app.entry_type else dict(entry)


def is_connected(app: AiApp, os_: PlatformBehavior, name: str) -> bool:
    for path in app.config_paths(os_) if app.connectable else []:
        config = _read(path) or {}
        servers = config.get(app.key)
        if isinstance(servers, dict) and name in servers:
            return True
    return False


def connect(app: AiApp, os_: PlatformBehavior, name: str, entry: dict) -> bool:
    if not app.connectable or not app.available(os_):
        raise ValueError(f"{app.name} can't be connected on this computer.")
    return set_entry(app.config_paths(os_), app.key, name, app_entry(app, entry))


def disconnect(app: AiApp, os_: PlatformBehavior, name: str) -> bool:
    return set_entry(app.config_paths(os_), app.key, name, None) if app.connectable else False


def openable(app: AiApp, os_: PlatformBehavior) -> bool:
    if app.terminal:
        return bool(shutil.which(app.terminal[0]))
    return bool(app.launch_name and os_.find_app(app.launch_name))


def running(app: AiApp, os_: PlatformBehavior) -> bool:
    """Whether the app is open right now (only known for the apps the kit can restart)."""
    return app.can_restart and os_.claude_running()


def open_app(app: AiApp, os_: PlatformBehavior) -> None:
    if app.terminal:
        if not shutil.which(app.terminal[0]):
            raise ValueError(f"{app.name} isn't installed on this computer.")
        os_.open_terminal(app.terminal, app.name)
        return
    handle = os_.find_app(app.launch_name) if app.launch_name else None
    if not handle:
        raise ValueError(f"Couldn't find {app.name} on this computer. Is it installed?")
    os_.open_found_app(handle)


def restart_app(app: AiApp, os_: PlatformBehavior) -> None:
    """Close and reopen the app, so it reads its settings (and the new connection) again."""
    if not app.can_restart:
        raise ValueError(f"{app.name} can't be restarted from here; close it and open it again.")
    handle = os_.claude_app()
    if not handle:
        raise ValueError(f"Couldn't find {app.name} on this computer. Is it installed?")
    os_.quit_claude()
    os_.open_claude(handle)


def describe(app: AiApp, os_: PlatformBehavior, name: str) -> dict:
    """Everything the AI tab shows for one app."""
    return {"id": app.id, "name": app.name, "blurb": app.blurb, "free": app.cost == "free",
            "download_url": app.download_url, "connectable": app.connectable, "available": app.available(os_),
            "installed": app.installed(os_), "connected": is_connected(app, os_, name),
            "finish_hint": app.finish_hint, "advice": app.advice, "examples": app.examples,
            "openable": app.connectable and openable(app, os_), "running": running(app, os_),
            "can_restart": app.can_restart, "installable": app.installable(os_)}
