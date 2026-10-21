import pytest
from conftest import FakeRcon

from wop import actions, config


class CvarRcon(FakeRcon):
    def __init__(self, values, port=27960):
        super().__init__()
        self.values = values
        self.port = port

    def command(self, cmd, timeout=2.0, quiet=0.3, retry=True):
        name = cmd.split()[0]
        if name in self.values and " " not in cmd:
            return f'"{name}" is:"{self.values[name]}^7" default:"^7"\n'
        return super().command(cmd)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    (tmp_path / "wop").mkdir()
    (tmp_path / "wop" / "server-friends.cfg").write_text(
        'set sv_hostname "From file"\nset rconpassword "x"\nset g_password ""\n', encoding="utf-8")
    monkeypatch.setenv("WOP_HOME", str(tmp_path))
    monkeypatch.setattr(actions.Game, "lan_addresses", staticmethod(lambda: ["192.168.1.20", "10.0.0.5"]))
    return tmp_path


def test_join_info_live(cfg):
    game = actions.Game(CvarRcon({"sv_hostname": "^1Kim^7's server", "g_password": "pizza"}), use_log=False)
    info = game.get_join_info()
    assert info["server_name"] == "Kim's server" and info["join_password"] == "pizza"
    assert info["connect_commands"] == ["/connect 192.168.1.20", "/connect 10.0.0.5"]
    assert any("/password pizza" in s for s in info["how_to_join"])
    assert any("worldofpadman.net" in s for s in info["how_to_join"])


def test_join_info_other_port_and_offline(cfg):
    rcon = CvarRcon({}, port=27961)
    rcon.is_running = lambda retry=False: False
    info = actions.Game(rcon, use_log=False).get_join_info()
    assert info["server_name"] == "From file" and not info["running"]
    assert info["connect_commands"][0] == "/connect 192.168.1.20:27961"
    assert info["join_password"] is None


def test_set_server_name(cfg):
    rcon = CvarRcon({})
    result = actions.Game(rcon, use_log=False).set_server_name('Bros "LAN"; quit')
    assert rcon.sent == ['sv_hostname "Bros LAN quit"']
    assert 'set sv_hostname "Bros LAN quit"' in (cfg / "wop" / "server-friends.cfg").read_text(encoding="utf-8")
    assert "right away" in result["result"]
    assert config.server_name() == "Bros LAN quit"


def test_lan_addresses_skips_loopback():
    for ip in actions.Game.lan_addresses():
        assert not ip.startswith(("127.", "169.254."))
