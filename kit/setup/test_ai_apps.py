"""Tests for ai_apps.py (run: uv run --no-project --with pytest python -m pytest kit/setup)."""

import json

import pytest

import ai_apps
import wopkit  # noqa: F401 (puts kit/mcp on the path)
from wop.platforms import for_name

ENTRY = {"command": "/k/tools/uv", "args": ["run", "--script", "/k/kit/mcp/server.py"], "env": {"WOP_HOME": "/k/home"}}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_apps.Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_every_app_is_described(home):
    linux = for_name("linux")
    for app in ai_apps.APPS:
        card = ai_apps.describe(app, linux, "wop-server")
        assert card["name"] and card["blurb"] and card["download_url"].startswith("https://")
        assert card["connectable"] or card["advice"]
        assert not card["connected"]
    # no jargon on the cards
    text = json.dumps([ai_apps.describe(app, linux, "wop-server") for app in ai_apps.APPS]).lower()
    for word in ("mcp", "rcon", "stdio", "json", "udp"):
        assert word not in text.replace("mcp.json", "")


def test_claude_desktop_only_where_it_exists(home, monkeypatch):
    app = ai_apps.find("claude-desktop")
    assert not app.available(for_name("linux"))
    mac = for_name("mac")
    assert app.available(mac)
    assert app.installable(mac) and app.installable(for_name("windows")) and not app.installable(for_name("linux"))
    assert not ai_apps.find("lm-studio").installable(mac)
    assert ai_apps.describe(app, for_name("linux"), "wop-server")["installable"] is False


def test_connect_lm_studio_keeps_other_entries(home):
    app = ai_apps.find("lm-studio")
    cfg = home / ".lmstudio" / "mcp.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    linux = for_name("linux")
    assert ai_apps.describe(app, linux, "wop-server")["installed"]
    assert ai_apps.connect(app, linux, "wop-server", ENTRY) is True
    assert ai_apps.connect(app, linux, "wop-server", ENTRY) is False        # nothing to change the second time
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["other"] == {"command": "x"} and data["mcpServers"]["wop-server"] == ENTRY
    assert (home / ".lmstudio" / "mcp.json.before-wop-kit").exists()
    assert ai_apps.is_connected(app, linux, "wop-server")
    assert ai_apps.disconnect(app, linux, "wop-server") is True
    assert "wop-server" not in json.loads(cfg.read_text())["mcpServers"]


def test_vscode_uses_its_own_format(home, monkeypatch):
    linux = for_name("linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    app = ai_apps.find("vscode")
    ai_apps.connect(app, linux, "wop-server", ENTRY)
    data = json.loads((home / "config" / "Code" / "User" / "mcp.json").read_text())
    assert data["servers"]["wop-server"] == {"type": "stdio", **ENTRY}


def test_broken_settings_file_is_left_alone(home):
    cfg = home / ".cursor" / "mcp.json"
    cfg.parent.mkdir()
    cfg.write_text("{ not json")
    assert ai_apps.connect(ai_apps.find("cursor"), for_name("linux"), "wop-server", ENTRY) is False
    assert cfg.read_text() == "{ not json"


class OpeningBehavior(type(for_name("linux"))):
    """Linux, with the apps and Claude Desktop's window faked."""

    def __init__(self, installed=(), running=False):
        self.installed, self.running, self.calls = set(installed), running, []

    def find_app(self, name):
        return f"app:{name}" if name in self.installed else None

    def open_found_app(self, handle):
        self.calls.append(("open", handle))

    def open_terminal(self, command, title):
        self.calls.append(("terminal", command, title))

    def claude_app(self):
        return "app:Claude" if "Claude" in self.installed else None

    def claude_running(self):
        return self.running

    def quit_claude(self):
        self.calls.append(("quit",))

    def open_claude(self, app):
        self.calls.append(("open", app))


def test_open_installed_apps(home):
    os_ = OpeningBehavior(installed={"LM Studio"})
    lm = ai_apps.find("lm-studio")
    assert ai_apps.describe(lm, os_, "wop-server")["openable"] is True
    ai_apps.open_app(lm, os_)
    assert os_.calls == [("open", "app:LM Studio")]
    cursor = ai_apps.find("cursor")
    assert ai_apps.describe(cursor, os_, "wop-server")["openable"] is False
    with pytest.raises(ValueError, match="Couldn't find Cursor"):
        ai_apps.open_app(cursor, os_)
    assert ai_apps.describe(ai_apps.find("chatgpt"), os_, "wop-server")["openable"] is False


def test_claude_code_opens_in_a_terminal(home, monkeypatch):
    os_ = OpeningBehavior()
    code = ai_apps.find("claude-code")
    monkeypatch.setattr(ai_apps.shutil, "which", lambda program: "/usr/bin/claude" if program == "claude" else None)
    assert ai_apps.describe(code, os_, "wop-server")["openable"] is True
    ai_apps.open_app(code, os_)
    assert os_.calls == [("terminal", ["claude"], "Claude Code")]
    monkeypatch.setattr(ai_apps.shutil, "which", lambda program: None)
    with pytest.raises(ValueError, match="isn't installed"):
        ai_apps.open_app(code, os_)


def test_restart_claude_desktop_only(home):
    os_ = OpeningBehavior(installed={"Claude"}, running=True)
    claude = ai_apps.find("claude-desktop")
    card = ai_apps.describe(claude, os_, "wop-server")
    assert card["running"] is True and card["can_restart"] is True
    ai_apps.restart_app(claude, os_)
    assert os_.calls == [("quit",), ("open", "app:Claude")]
    with pytest.raises(ValueError, match="can't be restarted"):
        ai_apps.restart_app(ai_apps.find("lm-studio"), os_)
    assert ai_apps.describe(ai_apps.find("lm-studio"), os_, "wop-server")["running"] is False


def test_advice_only_apps_cannot_connect(home):
    with pytest.raises(ValueError):
        ai_apps.connect(ai_apps.find("chatgpt"), for_name("linux"), "wop-server", ENTRY)
    assert ai_apps.disconnect(ai_apps.find("ollama"), for_name("linux"), "wop-server") is False
