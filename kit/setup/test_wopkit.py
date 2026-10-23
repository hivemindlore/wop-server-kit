"""Tests for wopkit.py helpers (run: uv run --no-project --with pytest python -m pytest kit/setup)."""

import hashlib
import http.server
import json
import threading
import zipfile
from pathlib import Path

import pytest

import wopkit
from wop.platforms import for_name, linux, mac, windows

WIN, MAC, LINUX = for_name("windows"), for_name("mac"), for_name("linux")


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


@pytest.mark.parametrize("name,win,mac,lin", [
    ("wopded.x86_64.exe", True, False, False),
    ("SDL2.dll", True, False, False),
    ("renderer_opengl1_x86_64.dylib", False, True, False),
    ("renderer_opengl1_x86_64.so", False, False, True),
    ("wop/wop_maps_1.7.0.pk3", True, True, True),
    ("wop/qagame_x86_64.dll", True, False, False),
    ("wop/qagame_x86_64.so", False, False, True),
    ("wopded.x86_64", False, False, True),                    # Linux server
    ("wop.x86_64", False, False, True),
    ("wopded.x86_64.app/Contents/MacOS/wopded.x86_64", False, True, False),
    ("README.md", True, True, True),
    ("XTRAS/Windows32.zip", False, False, False),
    ("wop/", False, False, False),
])
def test_extract_filter(name, win, mac, lin):
    assert WIN.wanted_in_game_zip(name) is win
    assert MAC.wanted_in_game_zip(name) is mac
    assert LINUX.wanted_in_game_zip(name) is lin


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


@pytest.mark.parametrize("platform", ["windows", "mac", "linux"])
def test_generated_scripts(tmp_path, monkeypatch, platform):
    """The run-server / wopkit launchers for every OS; Mac and Linux ones must be valid bash."""
    import shutil
    import subprocess
    behavior = for_name(platform)
    root = tmp_path / "Wo P root"                       # a space, like "Application Support"
    monkeypatch.setattr(wopkit, "OS", behavior)
    monkeypatch.setattr(wopkit, "ROOT", root)
    monkeypatch.setattr(wopkit, "HOME", root / "home")
    monkeypatch.setattr(wopkit, "CFG", root / "home" / "wop")
    root.mkdir()
    wopkit.ensure_server_files({"server_name": "Kim's server", "port": 27961}, root / "game")

    cfg = (root / "home" / "wop" / "server-friends.cfg").read_text(encoding="utf-8")
    assert 'set sv_hostname "Kim\'s server"' in cfg and "__RCON_PASSWORD__" not in cfg
    assert (root / "home" / "wop" / "teams.cfg").exists()
    run = wopkit.run_server_script().read_bytes().decode()
    home = root / "home"
    assert "net_port" in run and "27961" in run and f'fs_homepath "{home}"' in run
    assert f'"{root / "game" / behavior.server_bin}"' in run
    assert wopkit.launcher_script().exists()
    if platform == "windows":
        assert 0 < run.index("joininfo") < run.index("net_port")  # the "how to join" window opens first
        assert "\r\r\n" not in run and run.count("\r\n") == run.count("\n")
        return
    join_script = root / ("join-info.command" if platform == "mac" else "join-info.sh")
    assert "joininfo" in join_script.read_text() and 0 < run.index(str(join_script)) < run.index("net_port")
    assert "\r" not in run
    if platform == "mac":
        assert f'open -a Terminal "{join_script}"' in run
    bash = shutil.which("bash")
    if bash:
        for script in (wopkit.run_server_script(), wopkit.launcher_script(), join_script):
            assert subprocess.run([bash, "-n", str(script)]).returncode == 0


def test_launcher_args_match_script(tmp_path):
    from wop import launcher
    game, home = tmp_path / "game", tmp_path / "home"
    args = launcher.server_args(game, home, 27961)
    assert args[args.index("net_port") + 1] == "27961" and args[-2:] == ["+exec", "server-friends.cfg"]
    line = launcher.script_line(WIN, game, home, "%PORT%")
    assert line.startswith(f'"{game / "wopded.x86_64.exe"}" +set fs_basepath "{game}"') and "net_port %PORT%" in line


def test_shortcuts_in_folder(tmp_path, monkeypatch):
    """Play in Desktop/World of PADMAN, the rest in its WOP-server subfolder; old loose shortcuts go."""
    monkeypatch.setattr(wopkit, "OS", MAC)
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


@pytest.mark.parametrize("state,blocked,block_all,expect_fixes", [
    ("Firewall is disabled. (State = 0)", "", False, []),
    ("Firewall is enabled. (State = 1)", "The application is permitted", False, []),
    ("Firewall is enabled. (State = 1)", "The application is blocked", False, ["--add", "--unblockapp"]),
    ("Firewall is enabled. (State = 1)", "The application is permitted", True, ["--setblockall off"]),
])
def test_mac_firewall_check(monkeypatch, state, blocked, block_all, expect_fixes):
    def fake(*args):
        return {"--getglobalstate": state, "--getappblocked": blocked,
                "--getblockall": "block all enabled!" if block_all else "block all disabled!"}[args[0]].lower()

    monkeypatch.setattr(mac, "socketfilterfw", fake)
    inst = {}
    check = MAC.firewall_check("/Games/wopded", 27960, inst)
    fixes = " ".join(p.fix for p in check.problems)
    assert all(part in fixes for part in expect_fixes) and bool(fixes) == bool(expect_fixes)
    if "--add" in expect_fixes:
        assert "--add /Games/wopded" in fixes
    assert inst.get("firewall") == ("/Games/wopded" if "permitted" in blocked and "enabled" in state else None)


@pytest.mark.parametrize("terminal,expect", [
    (True, ["sudo", "/bin/sh", "-c", "a; b"]),
    (False, ["osascript", "-e", 'do shell script "a; b" with administrator privileges']),
])
def test_mac_elevation(monkeypatch, terminal, expect):
    from types import SimpleNamespace
    ran = []
    monkeypatch.setattr(mac.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or SimpleNamespace(returncode=0))
    assert MAC.run_elevated(["a", "b"], terminal=terminal) is True
    assert ran == [expect]


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
    problems = windows.network_problems(report, WIN_PROGRAM, 27960)
    assert len(problems) == len(expected)
    for problem, want in zip(problems, expected):
        assert problem.text
        assert problem.fix == want if want is None else want in problem.fix


@pytest.mark.parametrize("answer,elevated_ok,fixed,expect_elevated,expect_text", [
    ("", True, True, True, "Done."),                       # Enter means yes
    ("n", True, True, False, "nothing changed"),
    ("y", False, False, True, "nothing changed"),          # "No" on Windows' own permission question
    ("y", True, False, True, "Not everything could be fixed"),
])
def test_windows_firewall_flow(monkeypatch, tmp_path, capsys, answer, elevated_ok, fixed, expect_elevated,
                               expect_text):
    monkeypatch.delenv("WOP_ASSUME_YES", raising=False)
    monkeypatch.delenv("WOP_SKIP_FIREWALL", raising=False)
    monkeypatch.setattr(wopkit, "OS", WIN)
    monkeypatch.setattr(wopkit, "_tty_input", lambda prompt: answer)
    program = str(tmp_path / "game" / WIN.server_bin)
    broken = win_report(rule=None, allow_inbound="False")
    reports = [broken, win_report(rule={**KIT_RULE, "program": program}) if fixed else broken]
    monkeypatch.setattr(windows, "network_report", lambda port: reports.pop(0) if len(reports) > 1 else reports[0])
    elevated = []
    monkeypatch.setattr(WIN, "run_elevated", lambda commands, terminal: elevated.append("; ".join(commands))
                        or elevated_ok)
    inst = {}
    wopkit._firewall_console(inst, tmp_path / "game", 27960)
    out = capsys.readouterr().out
    assert "can't join your server yet" in out and expect_text in out
    if expect_elevated:
        assert len(elevated) == 1  # one permission question for every fix together
        assert "New-NetFirewallRule" in elevated[0] and "-AllowInboundRules True" in elevated[0]
    else:
        assert elevated == []
    assert inst.get("firewall") == (program if fixed and expect_elevated else None)


def test_windows_firewall_all_good(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("WOP_SKIP_FIREWALL", raising=False)
    monkeypatch.setattr(wopkit, "OS", WIN)
    program = str(tmp_path / "game" / WIN.server_bin)
    report = win_report(rule={**KIT_RULE, "program": program})
    report["others"] = ["Norton Firewall"]
    monkeypatch.setattr(windows, "network_report", lambda port: report)
    monkeypatch.setattr(WIN, "run_elevated", lambda commands, terminal: pytest.fail("asked for admin"))
    inst = {}
    wopkit._firewall_console(inst, tmp_path / "game", 27960)
    assert "OK." in capsys.readouterr().out and inst["firewall"] == program
    wopkit._firewall_console(inst, tmp_path / "game", 27960)
    assert "Norton" not in capsys.readouterr().out  # the note about another firewall shows once


def test_network_notes(monkeypatch):
    from wop.actions import Game
    monkeypatch.setattr(Game, "lan_addresses", staticmethod(lambda: []))
    notes = " ".join(wopkit.network_notes(27970))
    assert "connected to a network" in notes and "/connect <address>:27970" in notes
    monkeypatch.setattr(Game, "lan_addresses", staticmethod(lambda: ["192.168.1.20"]))
    assert wopkit.network_notes(27961) == []


def test_join_addresses(monkeypatch):
    from types import SimpleNamespace

    from wop.actions import Game
    monkeypatch.setattr(Game, "lan_addresses", staticmethod(lambda: ["10.0.1.71", "172.20.112.1"]))
    monkeypatch.setattr(wopkit, "OS", WIN)
    out = "192.168.0.237\tEthernet\r\n10.0.1.71\tWi-Fi\r\n169.254.7.7\tBluetooth\r\n10.0.1.71\tWi-Fi\r\n"
    monkeypatch.setattr(windows, "powershell", lambda script: SimpleNamespace(stdout=out))
    # the default route's network first; no self-assigned or duplicate addresses
    assert wopkit.join_addresses() == [("10.0.1.71", "Wi-Fi"), ("192.168.0.237", "Ethernet")]
    monkeypatch.setattr(wopkit, "OS", MAC)  # Mac: just the default route's address
    assert wopkit.join_addresses() == [("10.0.1.71", "")]


@pytest.mark.parametrize("addresses,port,password,expected,unexpected", [
    ([("10.0.1.71", "Wi-Fi")], 27960, "",
     ["SPECIFY", "Address:  10.0.1.71        (Wi-Fi)", "Port:     27960", "/connect 10.0.1.71\n"],
     ["other network", "password", "seem to be connected"]),
    ([("10.0.1.71", "Wi-Fi")], 27961, "",
     ["Port:     27961", "/connect 10.0.1.71:27961"], []),
    ([("10.0.1.71", "Wi-Fi"), ("192.168.0.237", "Ethernet")], 27960, "",
     ["Address:  10.0.1.71", "other network (Ethernet) use address 192.168.0.237"], []),
    ([("10.0.1.71", "")], 27960, "pad123",
     ["Address:  10.0.1.71\n", "Join password: pad123", "/password pad123"], []),
    ([], 27960, "", ["doesn't seem to be connected to a network"], ["SPECIFY", "Address:"]),
])
def test_joininfo(monkeypatch, capsys, addresses, port, password, expected, unexpected):
    from wop import config
    monkeypatch.setenv("WOP_ASSUME_YES", "1")  # no "Press Enter" wait
    monkeypatch.setattr(wopkit, "join_addresses", lambda: addresses)
    monkeypatch.setattr(wopkit, "load_install", lambda: {"port": port})
    monkeypatch.setattr(config, "server_name", lambda: "Kim's server")
    monkeypatch.setattr(config, "join_password", lambda: password)
    wopkit.cmd_joininfo(None)
    out = capsys.readouterr().out
    assert "Kim's server" in out and "SAME network" in out
    for text in expected:
        assert text in out
    for text in unexpected:
        assert text not in out


def test_settings_pins():
    assert len(wopkit.SETTINGS["wop_zip_sha256"]) == 64
    assert wopkit.SETTINGS["wop_zip_url"].startswith("https://github.com/PadWorld-Entertainment/")
    assert Path(wopkit.KIT / "server" / "server-friends.cfg").exists()


# --------------------------------------------------------------------------- Linux

@pytest.mark.parametrize("firewalld,query_ok,ufw_on,ufw_rules,recorded,expect_fix", [
    (False, False, False, None, None, None),                       # no firewall
    (True, True, False, None, None, None),                         # firewalld already allows the port
    (True, False, False, None, None, "firewall-cmd --add-port=27960/udp"),
    (False, False, True, "", None, "ufw allow 27960/udp"),        # ufw rules readable, port missing
    (False, False, True, "-A ufw-user-input -p udp --dport 27960 -j ACCEPT", None, None),
    (False, False, True, None, None, "ufw allow 27960/udp"),       # rules only readable as admin
    (False, False, True, None, "ufw:27960", None),                 # ... but the kit allowed it before
])
def test_linux_firewall_check(monkeypatch, firewalld, query_ok, ufw_on, ufw_rules, recorded, expect_fix):
    from types import SimpleNamespace
    monkeypatch.setattr(linux, "firewalld_running", lambda: firewalld)
    monkeypatch.setattr(linux, "_run", lambda *cmd: SimpleNamespace(returncode=0 if query_ok else 1, stdout=""))
    monkeypatch.setattr(linux, "ufw_enabled", lambda: ufw_on)
    monkeypatch.setattr(linux, "ufw_allows", lambda port: None if ufw_rules is None else "27960" in ufw_rules)
    inst = {"firewall": recorded} if recorded else {}
    check = LINUX.firewall_check("/g/wopded.x86_64", 27960, inst)
    fixes = [p.fix for p in check.problems]
    assert (expect_fix is None and fixes == []) or (len(fixes) == 1 and expect_fix in fixes[0])


def test_linux_ufw_fix_is_remembered_and_undone():
    from wop.platforms import NetworkProblem
    inst = {}
    LINUX.after_fix([NetworkProblem("x", "ufw allow 27961/udp comment 'WoP Server Kit'")], 27961, inst)
    assert inst["firewall"] == "ufw:27961"
    assert LINUX.firewall_removal(inst) == ["ufw delete allow 27961/udp"]
    assert "--remove-port=27960/udp" in LINUX.firewall_removal({"firewall": "firewalld:27960"})[0]


def test_linux_network_adapters(monkeypatch):
    from types import SimpleNamespace
    outputs = {"route": "default via 192.168.1.1 dev wlp2s0 proto dhcp metric 600\n",
               "addr": "1: lo    inet 127.0.0.1/8 scope host lo\n"
                       "3: wlp2s0    inet 192.168.1.42/24 brd 192.168.1.255 scope global wlp2s0\n"
                       "4: docker0    inet 172.17.0.1/16 scope global docker0\n"}
    monkeypatch.setattr(linux, "_run", lambda *cmd: SimpleNamespace(returncode=0, stdout=outputs["route" if "route" in cmd else "addr"]))
    assert LINUX.network_adapters() == [("192.168.1.42", "wlp2s0")]


def test_linux_shortcuts(tmp_path, monkeypatch):
    monkeypatch.setattr(linux, "_run", lambda *cmd: None)
    from wop.platforms import Shortcut
    made = LINUX.make_shortcuts(tmp_path, [Shortcut("Start WoP Server", Path("/k/wopkit.sh"), ["start"], Path("/k"))],
                                {"WoP Server Help": "https://example.org"})
    assert [p.name for p in made] == ["Start WoP Server.desktop", "WoP Server Help.desktop"]
    text = made[0].read_text()
    assert f'Exec="{Path("/k/wopkit.sh")}" "start"' in text and "Terminal=true" in text
    assert "Type=Link" in made[1].read_text()


def test_fix_firewall_asks_once_and_rechecks(monkeypatch, tmp_path):
    from wop.platforms import FirewallCheck, NetworkProblem
    monkeypatch.delenv("WOP_SKIP_FIREWALL", raising=False)
    monkeypatch.setattr(wopkit, "OS", LINUX)
    checks = [FirewallCheck([])]
    monkeypatch.setattr(LINUX, "firewall_check", lambda program, port, inst: checks.pop(0))
    asked = []
    monkeypatch.setattr(LINUX, "run_elevated", lambda commands, terminal: asked.append(commands) or True)
    before = FirewallCheck([NetworkProblem("a", "ufw allow 27960/udp"), NetworkProblem("b", None)])
    inst = {}
    accepted, after = wopkit.fix_firewall(inst, tmp_path, 27960, before)
    assert accepted and after.problems == [] and asked == [["ufw allow 27960/udp"]]
    assert inst["firewall"] == "ufw:27960"


def test_detect_picks_this_os():
    import sys
    from wop.platforms import detect
    assert detect().name == {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")
    with pytest.raises(RuntimeError):
        for_name("amiga")


# --------------------------------------------------------------------------- the kit's game code (spawn protection)

def test_patched_game_module_matches_kit_json():
    """The committed qagame.qvm is the one kit.json pins (rebuild with kit/server/game/build-qvm.sh)."""
    module = wopkit.KIT / "server" / "vm" / "qagame.qvm"
    assert wopkit.sha256(module) == wopkit.SETTINGS["patched_qagame_sha256"]


def test_game_module_only_for_wop_1_7_0(tmp_path, monkeypatch):
    monkeypatch.setattr(wopkit, "CFG", tmp_path / "home" / "wop")
    target = tmp_path / "home" / "wop" / "vm" / "qagame.qvm"
    game = tmp_path / "game"
    (game / "wop").mkdir(parents=True)

    wopkit.ensure_game_module(game)                      # not WoP 1.7.0: nothing
    assert not target.exists()

    (game / "wop" / "wop_vm_1.7.0.pk3").write_text("")
    wopkit.ensure_game_module(game)
    assert wopkit.sha256(target) == wopkit.SETTINGS["patched_qagame_sha256"]

    target.write_bytes(b"old")                           # an older kit's copy is replaced
    wopkit.ensure_game_module(game)
    assert wopkit.sha256(target) == wopkit.SETTINGS["patched_qagame_sha256"]

    (game / "wop" / "wop_vm_1.7.0.pk3").unlink()        # a newer WoP: our 1.7.0 code goes
    wopkit.ensure_game_module(game)
    assert not target.exists()

    target.write_bytes(b"someone else's")               # never removes a file we didn't put there
    wopkit.ensure_game_module(game)
    assert target.read_bytes() == b"someone else's"


# --------------------------------------------------------------------------- opening other apps (AI tab)

def test_windows_finds_apps_in_the_start_menu(monkeypatch):
    from types import SimpleNamespace
    out = ('[{"Name":"Claude","AppID":"com.squirrel.AnthropicClaude.claude"},'
           '{"Name":"LM Studio","AppID":"ai.elementlabs.lmstudio"},{"Name":"Claude","AppID":"other"}]')
    asked = []
    monkeypatch.setattr(windows, "powershell", lambda script: asked.append(script) or SimpleNamespace(stdout=out))
    monkeypatch.setattr(windows, "_start_apps", (0.0, {}))
    assert WIN.find_app("Claude") == "shell:AppsFolder\\com.squirrel.AnthropicClaude.claude"
    assert WIN.find_app("LM Studio") == "shell:AppsFolder\\ai.elementlabs.lmstudio"
    assert WIN.find_app("Cursor") is None
    assert len(asked) == 1  # Windows is asked once for all of them
    assert windows.parse_start_apps('{"Name":"Solo","AppID":"x"}') == {"Solo": "x"}
    assert windows.parse_start_apps("") == {} and windows.parse_start_apps("oops") == {}


def test_mac_finds_apps_in_applications(tmp_path, monkeypatch):
    monkeypatch.setattr(mac.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Applications" / "LM Studio.app").mkdir(parents=True)
    assert MAC.find_app("LM Studio") == str(tmp_path / "Applications" / "LM Studio.app")
    assert MAC.find_app("Nope") is None


def test_linux_finds_apps_by_their_menu_name(tmp_path):
    user, system = tmp_path / "user", tmp_path / "system"
    user.mkdir()
    system.mkdir()
    (system / "code.desktop").write_text("[Desktop Entry]\nName=Visual Studio Code\nExec=code\n"
                                         "[Desktop Action new-window]\nName=New Empty Window\n")
    (user / "lmstudio.desktop").write_text("[Desktop Entry]\nType=Application\nName=LM Studio\n")
    dirs = [user, tmp_path / "missing", system]
    assert linux.find_desktop_entry("Visual Studio Code", dirs) == system / "code.desktop"
    assert linux.find_desktop_entry("LM Studio", dirs) == user / "lmstudio.desktop"
    assert linux.find_desktop_entry("New Empty Window", dirs) is None  # an action, not the app


@pytest.mark.parametrize("behavior,module,expect", [
    (WIN, windows, ["cmd.exe", "/c", "start", "Claude Code", "cmd.exe", "/k", "claude"]),
    (MAC, mac, ["osascript", "-e", 'tell application "Terminal" to do script "claude"',
                "-e", 'tell application "Terminal" to activate']),
])
def test_open_terminal(monkeypatch, behavior, module, expect):
    from types import SimpleNamespace
    ran = []
    monkeypatch.setattr(module.subprocess, "Popen", lambda cmd, **kw: ran.append(cmd))
    monkeypatch.setattr(module.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or SimpleNamespace(returncode=0))
    behavior.open_terminal(["claude"], "Claude Code")
    assert ran == [expect]


def test_linux_open_terminal_keeps_the_window_open(monkeypatch):
    ran = []
    monkeypatch.setattr(linux.shutil, "which", lambda program: program == "gnome-terminal")
    monkeypatch.setattr(linux.subprocess, "Popen", lambda cmd, **kw: ran.append(cmd))
    LINUX.open_terminal(["claude"], "Claude Code")
    assert ran == [["gnome-terminal", "--", "bash", "-c", "claude; exec bash"]]
    monkeypatch.setattr(linux.shutil, "which", lambda program: False)
    with pytest.raises(OSError):
        LINUX.open_terminal(["claude"], "Claude Code")
