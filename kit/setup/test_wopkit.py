"""Tests for wopkit.py helpers (run: uv run --no-project --with pytest python -m pytest kit/setup)."""

import hashlib
import http.server
import json
import threading
import zipfile
from pathlib import Path

import pytest

import wopkit


@pytest.fixture
def http_file(tmp_path):
    """Serve a 3 MB file over HTTP with Range support."""
    data = bytes(range(256)) * (3 * 1024 * 1024 // 256)
    (tmp_path / "big.bin").write_bytes(data)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(tmp_path), **kw)

        def log_message(self, *a):
            pass

        def send_head(self):
            rng = self.headers.get("Range")
            if not rng:
                return super().send_head()
            start = int(rng.split("=")[1].split("-")[0])
            body = data[start:]
            self.send_response(206)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
            self.end_headers()
            import io
            return io.BytesIO(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/big.bin", data
    server.shutdown()


def test_download_resumes(http_file, tmp_path):
    url, data = http_file
    dest = tmp_path / "out" / "big.bin"
    dest.parent.mkdir()
    dest.write_bytes(data[:1_000_000])                  # a download that was cut off
    wopkit.download(url, dest, len(data))
    assert dest.read_bytes() == data
    assert wopkit.sha256(dest) == hashlib.sha256(data).hexdigest()
    wopkit.download(url, dest, len(data))               # already complete: nothing to do
    assert dest.stat().st_size == len(data)


@pytest.mark.parametrize("name,win,mac", [
    ("wopded.x86_64.exe", True, False),
    ("SDL2.dll", True, False),
    ("renderer_opengl1_x86_64.dylib", False, True),
    ("wop/wop_maps_1.7.0.pk3", True, True),
    ("wop/qagame_x86_64.dll", True, False),
    ("wop/qagame_x86_64.so", False, False),
    ("wopded.x86_64", False, False),                    # Linux server
    ("wopded.x86_64.app/Contents/MacOS/wopded.x86_64", False, True),
    ("XTRAS/Windows32.zip", False, False),
    ("wop/", False, False),
])
def test_extract_filter(monkeypatch, name, win, mac):
    monkeypatch.setattr(wopkit, "IS_WIN", True)
    monkeypatch.setattr(wopkit, "IS_MAC", False)
    assert wopkit._wanted(name) is win
    monkeypatch.setattr(wopkit, "IS_WIN", False)
    monkeypatch.setattr(wopkit, "IS_MAC", True)
    assert wopkit._wanted(name) is mac


def test_version_compare():
    assert wopkit._version_tuple("1.0.10") > wopkit._version_tuple("1.0.9")
    assert wopkit._version_tuple("1.1") > wopkit._version_tuple("1.0.5")


def test_clean_name():
    assert wopkit.clean_name('﻿Bros "LAN"; party\n') == "Bros LAN party"


def test_claude_entry_add_and_remove(tmp_path, monkeypatch):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"preferences": {"x": [1]}, "mcpServers": {"other": {"command": "a"}}}))
    monkeypatch.setenv("WOP_CLAUDE_CONFIG", str(cfg))
    entry = wopkit.mcp_entry()
    assert wopkit.set_claude_entry(entry) is True
    assert wopkit.set_claude_entry(entry) is False          # unchanged the second time
    data = json.loads(cfg.read_text())
    assert data["preferences"] == {"x": [1]} and data["mcpServers"]["other"] == {"command": "a"}
    assert data["mcpServers"]["wop-server"]["env"]["WOP_HOME"].endswith("home")
    assert (tmp_path / "claude_desktop_config.json.before-wop-kit").exists()
    assert wopkit.set_claude_entry(None) is True
    assert "wop-server" not in json.loads(cfg.read_text())["mcpServers"]


def test_claude_config_left_alone_when_broken(tmp_path, monkeypatch):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{ not json")
    monkeypatch.setenv("WOP_CLAUDE_CONFIG", str(cfg))
    assert wopkit.set_claude_entry(wopkit.mcp_entry()) is False
    assert cfg.read_text() == "{ not json"


def test_install_kit_zip_keeps_everything_else(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "kit").mkdir(parents=True)
    (root / "kit" / "old.txt").write_text("old")
    (root / "home").mkdir()
    (root / "home" / "keep.cfg").write_text("mine")
    monkeypatch.setattr(wopkit, "ROOT", root)
    monkeypatch.setattr(wopkit, "KIT", root / "kit")
    zip_path = tmp_path / "kit.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("wop-server-kit-main/kit/VERSION", "2.0.0\n")
        z.writestr("wop-server-kit-main/kit/setup/wopkit.py", "# new")
        z.writestr("wop-server-kit-main/README.md", "not part of the kit")
    wopkit.install_kit_zip(zip_path)
    assert (root / "kit" / "VERSION").read_text() == "2.0.0\n"
    assert not (root / "kit" / "old.txt").exists() and not (root / "kit" / "README.md").exists()
    assert (root / "home" / "keep.cfg").read_text() == "mine"
    assert not (root / "kit.new").exists() and not (root / "kit.old").exists()


@pytest.mark.parametrize("platform", ["win", "mac"])
def test_generated_scripts(tmp_path, monkeypatch, platform):
    """The run-server / wopkit launchers for both platforms; Mac ones must be valid bash."""
    import shutil
    import subprocess
    mac = platform == "mac"
    root = tmp_path / "Wo P root"                       # a space, like "Application Support"
    monkeypatch.setattr(wopkit, "IS_WIN", not mac)
    monkeypatch.setattr(wopkit, "IS_MAC", mac)
    monkeypatch.setattr(wopkit, "HOME", root / "home")
    monkeypatch.setattr(wopkit, "CFG", root / "home" / "wop")
    monkeypatch.setattr(wopkit, "UV", root / "tools" / ("uv" if mac else "uv.exe"))
    monkeypatch.setattr(wopkit, "RUN_SERVER", root / ("run-server.command" if mac else "run-server.cmd"))
    monkeypatch.setattr(wopkit, "LAUNCHER", root / ("wopkit.sh" if mac else "wopkit.cmd"))
    monkeypatch.setattr(wopkit, "SERVER_BIN", Path("wopded.x86_64.app/Contents/MacOS/wopded.x86_64") if mac
                        else Path("wopded.x86_64.exe"))
    root.mkdir()
    wopkit.ensure_server_files({"server_name": "Kim's server", "port": 27961}, root / "game")

    cfg = (root / "home" / "wop" / "server-friends.cfg").read_text(encoding="utf-8")
    assert 'set sv_hostname "Kim\'s server"' in cfg and "__RCON_PASSWORD__" not in cfg
    assert (root / "home" / "wop" / "teams.cfg").exists()
    run = wopkit.RUN_SERVER.read_bytes().decode()
    assert "net_port" in run and "27961" in run and "fs_homepath" in run
    if mac:
        assert "\r" not in run
        bash = shutil.which("bash")
        if bash:
            for script in (wopkit.RUN_SERVER, wopkit.LAUNCHER):
                assert subprocess.run([bash, "-n", str(script)]).returncode == 0
    else:
        assert "\r\r\n" not in run and run.count("\r\n") == run.count("\n")


def test_shortcuts_in_folder(tmp_path, monkeypatch):
    """Play in Desktop/World of PADMAN, the rest in its WOP-server subfolder; old loose shortcuts go."""
    monkeypatch.setattr(wopkit, "IS_WIN", False)
    monkeypatch.setattr(wopkit, "IS_MAC", True)
    monkeypatch.setattr(wopkit, "CLIENT_BIN", Path("wop.x86_64.app"))
    desk = tmp_path / "Desktop"
    desk.mkdir()
    monkeypatch.setenv("WOP_DESKTOP", str(desk))
    game = tmp_path / "game"
    (game / "wop.x86_64.app").mkdir(parents=True)
    old = desk / "Start WoP Server.command"
    old.write_text("old")
    inst = {"shortcuts": [str(old)]}
    try:
        wopkit._make_shortcuts(inst, game)
    except OSError as e:  # Windows without the right to make symlinks
        pytest.skip(f"no symlinks here: {e}")

    folder = desk / "World of PADMAN"
    assert (folder / "Play World of PADMAN.app").is_symlink()
    assert {p.name for p in (folder / "WOP-server").iterdir()} == {
        "Start WoP Server.command", "Stop WoP Server.command", "WoP Server Help.webloc",
        "WoP Server Troubleshooting.webloc"}
    assert not old.exists()
    assert sorted(p.name for p in desk.iterdir()) == ["World of PADMAN"]

    wopkit.remove_shortcuts(inst)
    assert list(desk.iterdir()) == []


def test_remove_shortcuts_keeps_users_files(tmp_path):
    folder = tmp_path / "World of PADMAN"
    (folder / "WOP-server").mkdir(parents=True)
    (folder / "my notes.txt").write_text("mine")
    wopkit.remove_shortcuts({"shortcuts": [], "shortcut_dirs": [str(folder / "WOP-server"), str(folder)]})
    assert not (folder / "WOP-server").exists() and (folder / "my notes.txt").exists()


@pytest.mark.parametrize("state,blocked,block_all,answer,expect_sudo", [
    ("Firewall is disabled. (State = 0)", "", False, "y", []),
    ("Firewall is enabled. (State = 1)", "The application is permitted", False, "y", []),
    ("Firewall is enabled. (State = 1)", "The application is blocked", False, "y", ["--add", "--unblockapp"]),
    ("Firewall is enabled. (State = 1)", "The application is blocked", False, "n", []),
    ("Firewall is enabled. (State = 1)", "The application is permitted", True, "y", ["--setblockall"]),
])
def test_mac_firewall(monkeypatch, tmp_path, state, blocked, block_all, answer, expect_sudo):
    monkeypatch.setattr(wopkit, "IS_WIN", False)
    monkeypatch.setattr(wopkit, "IS_MAC", True)
    monkeypatch.delenv("WOP_SKIP_FIREWALL", raising=False)
    monkeypatch.delenv("WOP_ASSUME_YES", raising=False)
    monkeypatch.setattr(wopkit, "_tty_input", lambda prompt: answer)
    monkeypatch.setattr(wopkit, "network_notes", lambda port: None)
    calls, allowed, open_all = [], [], [block_all]

    def fake(*args, sudo=False):
        calls.append((args, sudo))
        if sudo and args[0] == "--unblockapp":
            allowed.append(args[1])
        if sudo and args == ("--setblockall", "off"):
            open_all[0] = False
        if args[0] == "--getglobalstate":
            return state.lower()
        if args[0] == "--getappblocked":
            return "the application is permitted" if allowed else blocked.lower()
        if args[0] == "--getblockall":
            return "block all enabled!" if open_all[0] else "block all disabled!"
        return ""

    monkeypatch.setattr(wopkit, "socketfilterfw", fake)
    inst = {}
    wopkit.ensure_firewall(inst, tmp_path / "game", 27960)
    program = str(tmp_path / "game" / wopkit.SERVER_BIN)
    assert [args[0] for args, sudo in calls if sudo] == expect_sudo
    if "--add" in expect_sudo:
        assert ("--add", program) in [args for args, _ in calls]
    permitted = "disabled" not in state and ("permitted" in blocked or answer == "y")
    assert inst.get("firewall") == (program if permitted else None)


WIN_PROGRAM = r"C:\Users\Kim\AppData\Local\WoPServer\game\wopded.x86_64.exe"
KIT_RULE = {"enabled": "True", "action": "Allow", "direction": "Inbound", "profile": "Any",
            "program": WIN_PROGRAM, "protocol": "UDP", "remote": ["LocalSubnet"]}


def win_report(rule=KIT_RULE, blocks=(), allow_inbound="True", local_rules="True", enabled="True",
               active=("Private",)):
    return {"rule": rule, "blocks": list(blocks), "active": list(active), "others": [],
            "profiles": [{"name": name, "enabled": enabled, "allow_inbound": allow_inbound, "local_rules": local_rules}
                         for name in ("Domain", "Private", "Public")]}


@pytest.mark.parametrize("report,expected", [
    (win_report(), []),
    (win_report(rule={**KIT_RULE, "program": WIN_PROGRAM.upper()}), []),  # paths compare without case
    # without admin rights Windows may not show some of the rule's settings: unknown is not "changed"
    (win_report(rule={**KIT_RULE, "protocol": "", "program": "", "remote": []}), []),
    (win_report(rule={**KIT_RULE, "protocol": "TCP"}), ["New-NetFirewallRule"]),
    (win_report(rule={**KIT_RULE, "remote": ["Internet"]}), ["New-NetFirewallRule"]),
    (win_report(rule=None), ["New-NetFirewallRule"]),
    (win_report(rule={**KIT_RULE, "enabled": "False"}), ["New-NetFirewallRule"]),
    (win_report(rule={**KIT_RULE, "program": r"C:\old\wopded.x86_64.exe"}), ["New-NetFirewallRule"]),
    (win_report(rule={**KIT_RULE, "profile": "Private"}, active=["Public"]), ["New-NetFirewallRule"]),
    (win_report(rule={**KIT_RULE, "profile": "Private"}, active=["Private"]), []),
    (win_report(blocks=[{"name": "{abc}", "display": "wopded.x86_64.exe", "program": WIN_PROGRAM,
                         "protocol": "UDP", "ports": ["Any"]}]), ["Remove-NetFirewallRule -Name '{abc}'"]),
    (win_report(blocks=[{"name": "{x}", "display": "Old copy", "program": r"D:\Games\WoP\wopded.x86_64.exe",
                         "protocol": "UDP", "ports": ["Any"]}]), []),  # another copy of the game: not ours
    (win_report(blocks=[{"name": "{p}", "display": "No games", "program": "Any", "protocol": "UDP",
                         "ports": ["27950-27970"]}]), ["Disable-NetFirewallRule -Name '{p}'"]),
    (win_report(blocks=[{"name": "{t}", "display": "TCP only", "program": "Any", "protocol": "TCP",
                         "ports": ["27960"]}]), []),
    (win_report(allow_inbound="False"), ["Set-NetFirewallProfile -Profile Private -AllowInboundRules True"]),
    (win_report(allow_inbound="False", enabled="False"), []),  # firewall off: nothing is blocked
    (win_report(rule=None, local_rules="False"), ["New-NetFirewallRule", None]),
])
def test_windows_network_problems(report, expected):
    problems = wopkit.windows_network_problems(report, WIN_PROGRAM, 27960)
    assert len(problems) == len(expected)
    for (message, fix), want in zip(problems, expected):
        assert message
        assert fix == want if want is None else want in fix


@pytest.mark.parametrize("answer,elevated_ok,fixed,expect_elevated,expect_text", [
    ("", True, True, True, "Done."),                       # Enter means yes
    ("n", True, True, False, "nothing changed"),
    ("y", False, False, True, "nothing changed"),          # "No" on Windows' own permission question
    ("y", True, False, True, "Not everything could be fixed"),
])
def test_windows_firewall_flow(monkeypatch, tmp_path, capsys, answer, elevated_ok, fixed, expect_elevated,
                               expect_text):
    monkeypatch.delenv("WOP_ASSUME_YES", raising=False)
    monkeypatch.setattr(wopkit, "_tty_input", lambda prompt: answer)
    program = str(tmp_path / "game" / wopkit.SERVER_BIN)
    broken = win_report(rule=None, allow_inbound="False")
    reports = [broken, win_report(rule={**KIT_RULE, "program": program}) if fixed else broken]
    monkeypatch.setattr(wopkit, "windows_network_report", lambda port: reports.pop(0) if len(reports) > 1 else reports[0])
    elevated = []
    monkeypatch.setattr(wopkit, "run_elevated", lambda script: elevated.append(script) or elevated_ok)
    inst = {}
    wopkit._firewall_windows(inst, tmp_path / "game", 27960)
    out = capsys.readouterr().out
    assert "can't join your server yet" in out and expect_text in out
    if expect_elevated:
        assert len(elevated) == 1  # one permission question for every fix together
        assert "New-NetFirewallRule" in elevated[0] and "-AllowInboundRules True" in elevated[0]
    else:
        assert elevated == []
    assert inst.get("firewall") == (program if fixed and expect_elevated else None)


def test_windows_firewall_all_good(monkeypatch, tmp_path, capsys):
    program = str(tmp_path / "game" / wopkit.SERVER_BIN)
    report = win_report(rule={**KIT_RULE, "program": program})
    report["others"] = ["Norton Firewall"]
    monkeypatch.setattr(wopkit, "windows_network_report", lambda port: report)
    monkeypatch.setattr(wopkit, "run_elevated", lambda script: pytest.fail("asked for admin"))
    inst = {}
    wopkit._firewall_windows(inst, tmp_path / "game", 27960)
    assert "OK." in capsys.readouterr().out and inst["firewall"] == program
    wopkit._firewall_windows(inst, tmp_path / "game", 27960)
    assert "Norton" not in capsys.readouterr().out  # the note about another firewall shows once


def test_network_notes(monkeypatch, capsys):
    from wop.actions import Game
    monkeypatch.setattr(Game, "lan_addresses", staticmethod(lambda: []))
    wopkit.network_notes(27970)
    out = capsys.readouterr().out
    assert "connected to a network" in out and "/connect <address>:27970" in out
    monkeypatch.setattr(Game, "lan_addresses", staticmethod(lambda: ["192.168.1.20"]))
    wopkit.network_notes(27961)
    assert capsys.readouterr().out == ""


def test_settings_pins():
    assert len(wopkit.SETTINGS["wop_zip_sha256"]) == 64
    assert wopkit.SETTINGS["wop_zip_url"].startswith("https://github.com/PadWorld-Entertainment/")
    assert Path(wopkit.KIT / "server" / "server-friends.cfg").exists()
