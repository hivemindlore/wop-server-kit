from pathlib import Path

import pytest
from conftest import FakeRcon

from wop import config, config_files
from wop.catalog import WopError
from wop.server_state import read_state

TEMPLATE = Path(__file__).resolve().parents[2] / "server" / "server-friends.cfg"


@pytest.fixture
def cfg_dir(tmp_path):
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace("__SERVER_NAME__", "Kim's WoP server").replace("__RCON_PASSWORD__", "s3cret")
    (tmp_path / "server-friends.cfg").write_text(text, encoding="utf-8")
    (tmp_path / "teams.cfg").write_text("old\n", encoding="utf-8")
    return tmp_path


def test_template_values_are_read(cfg_dir, monkeypatch):
    monkeypatch.setenv("WOP_HOME", str(cfg_dir.parent))
    monkeypatch.setattr(config, "cfg_dir", lambda: cfg_dir)
    assert config.rcon_password() == "s3cret"
    assert config.server_name() == "Kim's WoP server"
    assert config.join_password() == ""


def test_set_cfg_value(cfg_dir):
    path = cfg_dir / "server-friends.cfg"
    config_files.set_cfg_value(path, "sv_hostname", "Bros LAN")
    config_files.set_cfg_value(path, "g_gravity", "400")
    text = path.read_text(encoding="utf-8")
    assert 'set sv_hostname "Bros LAN"' in text and "Kim's" not in text
    assert text.index('set g_gravity "400"') < text.index(config_files.START_MARK)


def test_save_as_startup(cfg_dir):
    before = (cfg_dir / "server-friends.cfg").read_text(encoding="utf-8")
    info = FakeRcon().serverinfo.replace("g_gametype           6", "g_gametype           7").replace(
        "g_instaPad           0", "g_instaPad           1")
    config_files.save_as_startup(read_state(FakeRcon(serverinfo=info)), cfg_dir)

    after = (cfg_dir / "server-friends.cfg").read_text(encoding="utf-8")
    start = before.index(config_files.START_MARK)
    assert after[:start] == before[:start]                      # everything above the block untouched
    assert after.endswith(before[before.index(config_files.END_MARK) + len(config_files.END_MARK):])
    assert 'set g_gametype     "7"' in after and 'set g_instaPad     "1"' in after
    assert after.count(config_files.START_MARK) == 1

    teams = (cfg_dir / "teams.cfg").read_text(encoding="utf-8")
    assert "addbot PADMAN      3 red" in teams
    assert 'addbot FatPad      3 blue 0 "FatPad2"' in teams
    assert "addbot FATTY       3 blue" in teams and "dikan" not in teams
    assert (cfg_dir / "teams.cfg.bak").read_text(encoding="utf-8") == "old\n"


def test_save_as_startup_solo_mode(cfg_dir):
    info = FakeRcon().serverinfo.replace("g_gametype           6", "g_gametype           0")
    config_files.save_as_startup(read_state(FakeRcon(serverinfo=info)), cfg_dir)
    teams = (cfg_dir / "teams.cfg").read_text(encoding="utf-8")
    assert "addbot PADMAN      3 free" in teams and "3 red" not in teams and "3 blue" not in teams


def test_save_as_startup_needs_markers(cfg_dir):
    (cfg_dir / "server-friends.cfg").write_text("map wop_padgarden\n", encoding="utf-8")
    with pytest.raises(WopError, match="startup game"):
        config_files.save_as_startup(read_state(FakeRcon()), cfg_dir)


def test_reset_to_defaults_keeps_name_and_admin_password(cfg_dir):
    server_cfg = cfg_dir / "server-friends.cfg"
    config_files.set_cfg_value(server_cfg, "sv_hostname", "Bros LAN")
    config_files.set_cfg_value(server_cfg, "g_password", "pizza")
    config_files.set_cfg_value(server_cfg, "g_instaPad", "1")
    changed = server_cfg.read_text(encoding="utf-8")
    config_files.reset_to_defaults(cfg_dir)
    text = server_cfg.read_text(encoding="utf-8")
    assert text == config_files.server_cfg_text("Bros LAN", "s3cret")
    assert 'set g_password   ""' in text and "pizza" not in text
    assert (cfg_dir / "teams.cfg").read_text(encoding="utf-8") == (config_files.TEMPLATES / "teams.cfg").read_text(
        encoding="utf-8")
    assert (cfg_dir / "mode.cfg").exists()
    assert (cfg_dir / "server-friends.cfg.bak").read_text(encoding="utf-8") == changed
    assert (cfg_dir / "teams.cfg.bak").read_text(encoding="utf-8") == "old\n"


def test_reset_needs_the_admin_password(cfg_dir):
    (cfg_dir / "server-friends.cfg").write_text('set sv_hostname "x"\n', encoding="utf-8")
    with pytest.raises(WopError, match="admin password"):
        config_files.reset_to_defaults(cfg_dir)


def test_save_as_startup_with_a_map_loop(cfg_dir):
    config_files.save_as_startup(read_state(FakeRcon()), cfg_dir, maps=["wop_padkitchen", "wop_padship"])
    text = (cfg_dir / "server-friends.cfg").read_text(encoding="utf-8")
    block = text[text.index(config_files.START_MARK):text.index(config_files.END_MARK)]
    lines = block.splitlines()
    assert lines.index("map wop_padkitchen") < lines.index("set nextmap vstr wop_rot1") < lines.index("exec teams.cfg")
    assert 'set wop_rot1 "map wop_padship; set nextmap vstr wop_rot0"' in lines
    assert "padkitchen and padship in a loop" in lines[1]
    config_files.save_as_startup(read_state(FakeRcon()), cfg_dir, maps=["wop_padkitchen"])
    text = (cfg_dir / "server-friends.cfg").read_text(encoding="utf-8")
    assert "nextmap" not in text and "map wop_padgarden" in text   # one map: the one running now
