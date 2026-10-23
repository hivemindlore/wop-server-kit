"""Tests for appbridge.py (run: uv run --no-project --with pytest python -m pytest kit/setup)."""

import io
import json

import pytest

import appbridge
import wopkit
from wop.platforms import FirewallCheck, NetworkProblem
from wop.platforms.linux import LinuxBehavior


class FakeBehavior(LinuxBehavior):
    def __init__(self):
        self.elevated = []
        self.checks = [FirewallCheck([NetworkProblem("The firewall doesn't let the players in.", "allow it")])]

    def firewall_check(self, program, port, inst):
        return self.checks[0] if len(self.checks) == 1 else self.checks.pop(0)

    def run_elevated(self, commands, terminal):
        self.elevated.append((commands, terminal))
        return True

    def claude_config_paths(self):
        return []


class FakeRcon:
    port = 27961

    def __init__(self, running=False):
        self.running = running
        self.sent = []

    def is_running(self, retry=False):
        return self.running

    def command(self, cmd, timeout=2.0, quiet=0.3, retry=True):
        from wop.rcon import ServerOffline
        if not self.running:
            raise ServerOffline("The WoP server isn't answering.")
        self.sent.append(cmd)
        return ""


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "WoPServer"
    (root / "home" / "wop").mkdir(parents=True)
    monkeypatch.setattr(wopkit, "ROOT", root)
    monkeypatch.setattr(wopkit, "HOME", root / "home")
    monkeypatch.setattr(wopkit, "CFG", root / "home" / "wop")
    monkeypatch.setattr(wopkit, "INSTALL_JSON", root / "install.json")
    monkeypatch.setenv("WOP_HOME", str(root / "home"))
    monkeypatch.delenv("WOP_SKIP_FIREWALL", raising=False)
    monkeypatch.setattr(wopkit, "OS", FakeBehavior())
    monkeypatch.setattr(wopkit, "UI", wopkit.UI)  # the bridge swaps it; put it back afterwards
    return root


@pytest.fixture
def bridge(root):
    b = appbridge.Bridge(io.StringIO())
    b.game.rcon = FakeRcon()
    return b


def ask(bridge, method, **params):
    bridge.out.seek(0)
    bridge.out.truncate()
    bridge._answer({"id": 1, "method": method, "params": params})
    lines = [json.loads(line) for line in bridge.out.getvalue().splitlines()]
    return next(line for line in lines if line.get("id") == 1)


def install_game(root, **extra):
    game = root / "game"
    (game / "wop").mkdir(parents=True)
    (game / "wopded.x86_64").write_text("")
    (game / "wop" / "wop_maps_1.7.0.pk3").write_text("")
    (root / "home" / "wop" / "server-friends.cfg").write_text('set sv_hostname "Kim\'s server"\nset rconpassword "x"\n')
    inst = {"port": 27961, "server_name": "Kim's server", "game_dir": str(game), **extra}
    (root / "install.json").write_text(json.dumps(inst))
    return game


def test_hello_before_setup(bridge):
    result = ask(bridge, "hello")["result"]
    assert result["protocol"] == appbridge.PROTOCOL and result["installed"] is False
    assert result["platform"] == "linux" and result["default_server_name"].endswith("WoP server")


def test_hello_after_setup_switches_to_hidden_server(bridge, root):
    install_game(root)
    result = ask(bridge, "hello")["result"]
    assert result["installed"] and result["server_name"] == "Kim's server" and result["port"] == 27961
    assert json.loads((root / "install.json").read_text())["hidden_server"] is True
    assert (root / "run-server.sh").exists()


def test_unknown_and_failing_requests_answer_with_a_message(bridge):
    assert "Unknown request" in ask(bridge, "nope")["error"]["message"]
    assert ask(bridge, "network.check")["error"]["message"] == "The server isn't set up yet."


def test_status_when_off_is_cheap(bridge, root):
    install_game(root)
    status = ask(bridge, "server.status")["result"]
    assert status["running"] is False and status["port"] == 27961 and status["server_name"] == "Kim's server"


def test_console_blocks_quit(bridge):
    bridge.game.rcon.running = True
    assert "isn't allowed" in ask(bridge, "console.run", command="quit")["error"]["message"]
    assert bridge.game.rcon.sent == []


def test_network_check_and_fix(bridge, root):
    install_game(root)
    behavior = wopkit.OS
    check = ask(bridge, "network.check")["result"]
    assert check["checked"] and not check["ok"] and check["can_fix"]
    assert check["problems"] == [{"text": "The firewall doesn't let the players in.", "fixable": True}]
    behavior.checks = [behavior.checks[0], FirewallCheck([])]
    fixed = ask(bridge, "network.fix")["result"]
    assert fixed["ok"] and fixed["accepted"]
    assert behavior.elevated == [(["allow it"], False)]  # asked in a dialog, not in a text window


def test_join_password_is_kept(bridge, root):
    install_game(root)
    result = ask(bridge, "server.set_join_password", password='pad "123"')["result"]
    assert "pad123" in result["result"]
    assert 'set g_password "pad123"' in (root / "home" / "wop" / "server-friends.cfg").read_text()


def test_log_history_and_follow(bridge, root):
    log = root / "home" / "wop" / "qconsole.log"
    log.write_bytes(b"old line\n^1Pad^4King^7: hi\n")
    history = ask(bridge, "log.history", lines=10)["result"]["lines"]
    assert history[-1] == [{"text": "Pad", "color": "red"}, {"text": "King", "color": "blue"},
                           {"text": ": hi", "color": None}]
    with open(log, "ab") as f:
        f.write(b"new line\nhalf")
    assert bridge.tail.new_lines() == (False, ["new line"])
    log.write_bytes(b"fresh\n")                       # a new server started a new log
    assert bridge.tail.new_lines() == (True, ["fresh"])


def test_ai_list_and_connect(bridge, root, tmp_path, monkeypatch):
    monkeypatch.setattr(appbridge.ai_apps.Path, "home", classmethod(lambda cls: tmp_path))
    apps = ask(bridge, "ai.list")["result"]["apps"]
    ids = [app["id"] for app in apps]
    assert "claude-desktop" not in ids and "lm-studio" in ids and "chatgpt" in ids
    card = ask(bridge, "ai.connect", app_id="lm-studio")["result"]
    assert card["connected"] is True
    entry = json.loads((tmp_path / ".lmstudio" / "mcp.json").read_text())["mcpServers"]["wop-server"]
    assert entry["args"][-1].endswith("server.py") and entry["env"]["WOP_HOME"] == str(root / "home")
    assert ask(bridge, "ai.disconnect", app_id="lm-studio")["result"]["connected"] is False


def test_protocol_round_trip(bridge):
    out = bridge.out
    bridge.run(io.StringIO('{"id": 5, "method": "hello"}\nnot json\n\n'))
    bridge.pool.shutdown(wait=True)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert any(r.get("id") == 5 and "result" in r for r in replies)


def test_settings_with_the_server_off_are_saved_for_the_next_start(bridge, root):
    install_game(root)
    cfg = root / "home" / "wop" / "server-friends.cfg"
    cfg.write_text(cfg.read_text() + 'set g_instaPad "0"\nset g_spawnProtect "0"\n// >>> startup game\n'
                   'set g_instaPad "0"\n// <<< startup game\n')
    settings = ask(bridge, "settings.get")["result"]
    assert settings == {"running": False, "instapad": False, "spawn_protection": False,
                        "spawn_protection_seconds": 0, "spawn_protection_changeable": False}
    assert "next start" in ask(bridge, "settings.set_weapons", instapad=True)["result"]["result"]
    assert "next start" in ask(bridge, "settings.set_spawn_protection", on=True)["result"]["result"]
    text = cfg.read_text()
    assert text.count('set g_instaPad "1"') == 2 and 'set g_spawnProtect "3"' in text  # startup block too
    assert ask(bridge, "settings.get")["result"]["spawn_protection_seconds"] == 3


def test_settings_change_the_running_server(bridge, root, monkeypatch):
    from types import SimpleNamespace
    install_game(root)
    bridge.game.rcon.running = True
    calls = []
    monkeypatch.setattr(bridge.game, "state", lambda: SimpleNamespace(instapad=True, spawn_protect=6))
    monkeypatch.setattr(bridge.game, "set_weapons", lambda w: calls.append(("weapons", w)))
    monkeypatch.setattr(bridge.game, "set_spawn_protection", lambda on: calls.append(("protect", on)))
    assert ask(bridge, "settings.get")["result"]["spawn_protection_changeable"] is True
    ask(bridge, "settings.set_weapons", instapad=False)
    ask(bridge, "settings.set_spawn_protection", on=False)
    assert calls == [("weapons", "regular"), ("protect", False)]
    # a server started before the kit had its game code: saved, applies after a restart
    monkeypatch.setattr(bridge.game, "state", lambda: SimpleNamespace(instapad=True, spawn_protect=None))
    assert "restarts" in ask(bridge, "settings.set_spawn_protection", on=True)["result"]["result"]
    assert calls[-1] == ("protect", False)


def test_ai_open_and_restart(bridge, monkeypatch):
    opened = []
    monkeypatch.setattr(wopkit.OS, "find_app", lambda name: f"app:{name}" if name == "LM Studio" else None, raising=False)
    monkeypatch.setattr(wopkit.OS, "open_found_app", lambda handle: opened.append(handle), raising=False)
    card = ask(bridge, "ai.open", app_id="lm-studio")["result"]
    assert opened == ["app:LM Studio"] and card["openable"] is True
    assert "Couldn't find Cursor" in ask(bridge, "ai.open", app_id="cursor")["error"]["message"]
    assert "can't be restarted" in ask(bridge, "ai.restart", app_id="lm-studio")["error"]["message"]


class ClaudeBehavior(FakeBehavior):
    """A computer that can get Claude Desktop (like a Mac), with installing and opening it faked."""
    claude_asset = "mac"

    def __init__(self, config):
        super().__init__()
        self.config, self.app, self.calls = config, None, []

    def claude_config_paths(self):
        return [self.config]

    def claude_app(self):
        return self.app

    def claude_running(self):
        return False

    def install_claude(self, download):
        self.calls.append(("install", download.read_bytes()))
        self.app = "Claude.app"

    def open_claude(self, app):
        self.calls.append(("open", app))


@pytest.fixture
def claude(bridge, tmp_path, monkeypatch):
    os_ = ClaudeBehavior(tmp_path / "claude_desktop_config.json")
    monkeypatch.setattr(wopkit, "OS", os_)
    bridge.os = os_
    monkeypatch.delenv("WOP_NO_CLAUDE_LAUNCH", raising=False)
    monkeypatch.delenv("WOP_CLAUDE_APP", raising=False)
    monkeypatch.delenv("WOP_CLAUDE_CONFIG", raising=False)
    return os_


def fake_download(dest_bytes=b"the app"):
    def download(url, dest, expected_size=None, progress=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dest_bytes)
    return download


def test_ai_install_gets_claude_desktop_connects_and_opens_it(bridge, root, claude, monkeypatch):
    monkeypatch.setattr(wopkit.downloads, "download", fake_download())
    card = ask(bridge, "ai.install", app_id="claude-desktop")["result"]
    assert card["installed"] and card["connected"] and card["installable"]
    assert claude.calls == [("install", b"the app"), ("open", "Claude.app")]
    assert "wop-server" in json.loads(claude.config.read_text())["mcpServers"]
    assert not (root / "downloads" / "Claude.zip").exists()   # the installer isn't kept


def test_ai_install_says_when_it_did_not_work(bridge, claude, monkeypatch):
    def offline(url, dest, expected_size=None, progress=None):
        raise OSError("no internet")
    monkeypatch.setattr(wopkit.downloads, "download", offline)
    message = ask(bridge, "ai.install", app_id="claude-desktop")["error"]["message"]
    assert "couldn't be installed" in message and "https://claude.ai/download" in message
    assert claude.calls == [] and not claude.config.exists()


def test_only_claude_desktop_can_be_installed(bridge):
    assert "can't be installed" in ask(bridge, "ai.install", app_id="lm-studio")["error"]["message"]


def test_setup_messages_become_events(bridge):
    wopkit.step("Downloading World of PADMAN")
    wopkit.say("   Unpacking...")
    wopkit.UI.progress(50, 100)
    events = [json.loads(line) for line in bridge.out.getvalue().splitlines()]
    assert events == [{"event": "setup.step", "data": {"text": "Downloading World of PADMAN"}},
                      {"event": "setup.message", "data": {"text": "Unpacking..."}},
                      {"event": "setup.progress", "data": {"done": 50, "total": 100, "percent": 50}}]


class StubOnline:
    def __init__(self):
        self.calls = []

    def status(self, running=None):
        self.calls.append(("status", running))
        return {"phase": "off"}

    def enable(self):
        self.calls.append(("enable",))
        return {"phase": "approving", "approve_url": "https://playit.gg/claim/abc"}

    def advance(self):
        self.calls.append(("advance",))
        return {"phase": "starting"}

    def disable(self):
        self.calls.append(("disable",))
        return {"phase": "off", "result": "Only players on your network can join now."}

    def manage(self):
        self.calls.append(("manage",))
        return {"result": "playit.gg opened in your browser."}


def test_online_methods(bridge, root):
    stub = StubOnline()
    bridge.game._online = stub
    assert "isn't set up" in ask(bridge, "online.enable")["error"]["message"]
    install_game(root)
    assert ask(bridge, "online.enable")["result"]["phase"] == "approving"
    assert ask(bridge, "online.advance")["result"]["phase"] == "starting"
    assert ask(bridge, "online.status")["result"] == {"phase": "off"}
    assert "network" in ask(bridge, "online.disable")["result"]["result"]
    assert "opened" in ask(bridge, "online.manage")["result"]["result"]
    assert stub.calls == [("enable",), ("advance",), ("status", None), ("disable",), ("manage",)]


def test_online_status_on_this_computer(bridge, root):
    status = ask(bridge, "online.status")["result"]
    assert status["phase"] == "off" and status["enabled"] is False and status["available"] is True
