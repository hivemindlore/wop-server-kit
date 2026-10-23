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


def test_advice_only_apps_cannot_connect(home):
    with pytest.raises(ValueError):
        ai_apps.connect(ai_apps.find("chatgpt"), for_name("linux"), "wop-server", ENTRY)
    assert ai_apps.disconnect(ai_apps.find("ollama"), for_name("linux"), "wop-server") is False
