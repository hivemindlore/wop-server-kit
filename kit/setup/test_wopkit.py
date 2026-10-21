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


def test_settings_pins():
    assert len(wopkit.SETTINGS["wop_zip_sha256"]) == 64
    assert wopkit.SETTINGS["wop_zip_url"].startswith("https://github.com/PadWorld-Entertainment/")
    assert Path(wopkit.KIT / "server" / "server-friends.cfg").exists()
