import hashlib
import json

import pytest
from wop import actions, online
from wop.catalog import WopError
from wop.online_keeper import GONE_AFTER, POLL, STARTUP_GRACE, Keeper
from wop.platforms.linux import LinuxBehavior
from wop.platforms.mac import MacBehavior

PROGRAM = b"playit program"


def fake_download(data):
    def download(url, dest, *args, **kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return download


class Behavior(LinuxBehavior):
    """Linux, without touching the desktop: records opened pages; the lock is a flag."""
    playit_asset = "linux-x64"

    def __init__(self):
        self.opened = []
        self.locked = False

    def open_url(self, url):
        self.opened.append(url)

    def try_lock(self, path):
        return None if self.locked else object()

    def release_lock(self, handle):
        pass

    def make_executable(self, path):
        pass


class Rcon:
    def __init__(self, running=True, port=27960):
        self.running = running
        self.port = port

    def is_running(self, retry=False):
        return self.running


class Playit:
    """playit.gg as the kit sees it: the claim, the agent's run data, its tunnels."""

    def __init__(self):
        self.claim = "WaitingForUserVisit"
        self.secret_ok = True
        self.tunnels = []
        self.pending = []
        self.calls = []
        self.create_refusal = None

    def post(self, path, body, secret):
        self.calls.append((path, body, secret))
        if path == "/claim/setup":
            if self.claim == "expired":
                raise online.PlayitRefused("CodeExpired")
            return self.claim
        if path == "/claim/exchange":
            return {"secret_key": "abcdef0123"}
        assert secret == "abcdef0123"
        if not self.secret_ok:
            raise online.PlayitRefused("AuthRequired")
        if path == "/agents/rundata":
            return {"agent_id": "agent-1", "tunnels": self.tunnels, "pending": self.pending}
        if path == "/tunnels/create":
            if self.create_refusal:
                raise online.PlayitRefused(self.create_refusal)
            self.pending.append({"id": "tunnel-1"})
            return {"id": "tunnel-1"}
        if path == "/tunnels/delete":
            self.tunnels = [t for t in self.tunnels if t["id"] != body["tunnel_id"]]
            return None
        raise AssertionError(path)

    def allocate(self, port=27960, address="happy-pad.gl.ply.gg", public=41234):
        self.pending = []
        self.tunnels = [{"id": "tunnel-1", "proto": "udp", "local_port": port, "assigned_domain": address,
                         "custom_domain": None, "port": {"from": public, "to": public}, "disabled": None}]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("WOP_HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "wop").mkdir(parents=True)
    (tmp_path / "home" / "wop" / "server-friends.cfg").write_text('set rconpassword "x"\n', encoding="utf-8")
    pins = {"version": "1.0.10", "assets": {"linux-x64": {"url": "https://example.invalid/playit",
                                                          "sha256": hashlib.sha256(PROGRAM).hexdigest()}}}
    monkeypatch.setattr(online, "settings", lambda: pins)
    monkeypatch.setattr(online.downloads, "download", fake_download(PROGRAM))
    return tmp_path


@pytest.fixture
def playit():
    return Playit()


@pytest.fixture
def launched():
    return []


def make(behavior=None, rcon=None, playit=None, launched=None):
    playit = playit or Playit()
    return online.Online(behavior or Behavior(), rcon or Rcon(),
                         api=lambda secret: online.PlayitApi(secret, playit.post, "1.0.10"),
                         launch=lambda argv, cwd: launched.append(argv) if launched is not None else None)


def test_first_time_asks_for_approval_once(home, playit, launched):
    behavior = Behavior()
    o = make(behavior, playit=playit, launched=launched)
    status = o.enable()
    assert status["phase"] == "approving" and status["enabled"]
    assert status["approve_url"].startswith("https://playit.gg/claim/")
    assert behavior.opened == [status["approve_url"]]
    assert (home / "tools" / "playit-1.0.10").read_bytes() == PROGRAM
    assert o.enable()["phase"] == "approving"          # still waiting: the page isn't opened again
    assert behavior.opened == [status["approve_url"]]
    assert playit.calls[0][1]["version"] == "playit 1.0.10" and playit.calls[0][1]["agent_type"] == "self-managed"


def test_approved_gets_an_address_and_starts_the_keeper(home, playit, launched):
    o = make(playit=playit, launched=launched)
    o.enable()
    playit.claim = "UserAccepted"
    status = o.enable()
    assert 'secret_key = "abcdef0123"' in (home / "home" / "playit" / "playit.toml").read_text()
    assert status["phase"] == "starting"                # the address is being set up
    create = next(body for path, body, _ in playit.calls if path == "/tunnels/create")
    assert create["port_type"] == "udp" and create["origin"]["data"] == {
        "agent_id": "agent-1", "local_ip": "127.0.0.1", "local_port": 27960}
    assert launched and launched[0][1] == "-c" and "wop.online_keeper import main" in launched[0][2]
    assert launched[0][3:] == ["--home", str(home / "home"), "--port", "27960"]
    playit.allocate()
    status = o.enable()
    assert status["address"] == "happy-pad.gl.ply.gg" and status["port"] == 41234
    assert sum(path == "/tunnels/create" for path, _, _ in playit.calls) == 1
    assert o.join_details() == {"address": "happy-pad.gl.ply.gg", "port": 41234,
                                "connect_command": "/connect happy-pad.gl.ply.gg:41234"}


def test_phases_follow_the_server_and_the_keeper(home, playit):
    behavior, rcon = Behavior(), Rcon()
    o = make(behavior, rcon, playit)
    playit.claim = "UserAccepted"
    playit.allocate()
    assert o.enable()["phase"] == "starting"            # the keeper hasn't taken its lock yet
    behavior.locked = True
    assert o.status()["phase"] == "online"
    rcon.running = False
    assert o.status()["phase"] == "server_off"
    assert "41234" in o.status()["message"]


def test_off_keeps_the_key_and_on_again_needs_no_approval(home, playit):
    behavior = Behavior()
    o = make(behavior, playit=playit)
    playit.claim = "UserAccepted"
    playit.allocate()
    o.enable()
    result = o.disable()
    assert result["phase"] == "off" and not result["enabled"] and "network" in result["result"]
    assert o.join_details() is None and not o.wanted()
    assert o.secret() == "abcdef0123"
    assert o.enable()["address"] == "happy-pad.gl.ply.gg"
    assert len(behavior.opened) == 1


def test_advance_doesnt_switch_back_on(home, playit):
    o = make(playit=playit)
    o.enable()
    assert o.advance()["phase"] == "approving"
    o.disable()                                          # e.g. Claude, while the app was waiting
    assert o.advance()["phase"] == "off" and not o._state()["enabled"]


def test_not_approved(home, playit):
    o = make(playit=playit)
    o.enable()
    playit.claim = "UserRejected"
    with pytest.raises(WopError, match="wasn't approved"):
        o.enable()
    assert o.status()["phase"] == "off"


def test_expired_approval_page_gets_a_new_one(home, playit):
    behavior = Behavior()
    o = make(behavior, playit=playit)
    o.enable()
    first = behavior.opened[0]
    old_code = first.rsplit("/", 1)[1]

    def post(path, body, secret):
        if path == "/claim/setup" and body["code"] == old_code:
            raise online.PlayitRefused("CodeExpired")
        return playit.post(path, body, secret)
    o.api = lambda secret: online.PlayitApi(secret, post, "1.0.10")
    assert o.enable()["phase"] == "approving"
    assert len(behavior.opened) == 2 and behavior.opened[1] != first


def test_key_no_longer_known_asks_again(home, playit):
    behavior = Behavior()
    o = make(behavior, playit=playit)
    playit.claim = "UserAccepted"
    playit.allocate()
    o.enable()
    playit.secret_ok = False
    playit.claim = "WaitingForUserVisit"
    assert o.enable()["phase"] == "approving"
    assert o.secret() is None and len(behavior.opened) == 2


def test_no_address_given(home, playit):
    o = make(playit=playit)
    playit.claim = "UserAccepted"
    playit.create_refusal = "RequiresVerifiedAccount"
    with pytest.raises(WopError, match="RequiresVerifiedAccount"):
        o.enable()
    assert o.status()["phase"] == "problem"
    o.disable()
    assert o.status()["phase"] == "off"


def test_tunnel_follows_a_new_port(home, playit):
    rcon = Rcon(port=27960)
    o = make(rcon=rcon, playit=playit)
    playit.claim = "UserAccepted"
    playit.allocate(port=27960)
    o.enable()
    rcon.port = 27961                                   # the server was moved to another port
    o.enable()
    assert any(path == "/tunnels/delete" for path, _, _ in playit.calls)
    create = next(body for path, body, _ in playit.calls if path == "/tunnels/create")
    assert create["origin"]["data"]["local_port"] == 27961
    assert o.status()["phase"] == "starting"            # the new address is being set up


def test_mac_has_no_internet_play(home):
    o = make(MacBehavior())
    assert o.status() == {"available": False, "enabled": False, "phase": "off", "address": None, "port": None,
                          "approve_url": None, "message": online.NOT_HERE}
    with pytest.raises(WopError, match="isn't available"):
        o.enable()
    assert o.join_details() is None and not o.start_keeper()


def test_damaged_download(home, playit, monkeypatch):
    monkeypatch.setattr(online.downloads, "download", fake_download(b"evil"))
    with pytest.raises(WopError, match="damaged"):
        make(playit=playit).enable()
    assert not list((home / "tools").glob("playit-*"))


def test_offline(home, playit, monkeypatch):
    def offline(url, dest, *a, **k):
        raise OSError("no network")
    monkeypatch.setattr(online.downloads, "download", offline)
    with pytest.raises(WopError, match="Is this computer online"):
        make(playit=playit).enable()


def test_forget_removes_the_address(home, playit):
    o = make(playit=playit)
    playit.claim = "UserAccepted"
    playit.allocate()
    o.enable()
    o.forget(wait=0)
    assert playit.tunnels == [] and not o.wanted()


def test_program_args(home):
    o = make()
    args = o.program_args()
    assert args[0].endswith("playit-1.0.10")
    assert args[args.index("--secret-path") + 1].endswith("playit.toml")
    assert "--socket-path" in args and "--log-path" in args


def test_join_info_tells_far_away_friends(home, playit, monkeypatch):
    monkeypatch.setattr(actions.Game, "lan_addresses", staticmethod(lambda: ["192.168.1.20"]))
    monkeypatch.setattr(actions.Game, "_cvar", lambda self, name: None)
    game = actions.Game(Rcon(), use_log=False, behavior=Behavior())
    assert game.get_join_info()["online"] is None
    game._online = make(playit=playit)
    playit.claim = "UserAccepted"
    playit.allocate()
    game.online.enable()
    info = game.get_join_info()
    assert info["online"]["address"] == "happy-pad.gl.ply.gg"
    assert any("SPECIFY" in step and "41234" in step for step in info["how_to_join"])


def test_real_pins_are_complete():
    pins = json.loads(online.KIT_JSON.read_text(encoding="utf-8"))["playit"]
    assert set(pins["assets"]) == {"windows-x64", "linux-x64", "linux-arm64"}
    for pin in pins["assets"].values():
        assert pin["url"].startswith(f"https://github.com/playit-cloud/playit-agent/releases/download/v{pins['version']}/")
        assert len(pin["sha256"]) == 64


# ---------------------------------------------------------------- the keeper

class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Program:
    def __init__(self):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def keeper(clock, wanted=lambda: True, running=lambda: True, programs=None):
    programs = programs if programs is not None else []

    def start():
        programs.append(Program())
        return programs[-1]
    return Keeper(wanted, running, start, clock=clock, sleep=clock.sleep), programs


def test_keeper_stops_the_program_when_switched_off():
    clock = Clock()
    k, programs = keeper(clock, wanted=lambda: clock.now < 30)
    assert k.run() == "internet play was switched off"
    assert len(programs) == 1 and programs[0].terminated


def test_keeper_stops_when_the_server_is_gone():
    clock = Clock()
    k, programs = keeper(clock, running=lambda: clock.now < 60)
    assert k.run() == "the server stopped"
    assert 60 + GONE_AFTER <= clock.now <= 60 + GONE_AFTER + 2 * POLL
    assert programs[0].terminated


def test_keeper_waits_for_a_starting_server_and_gives_up():
    clock = Clock()
    k, programs = keeper(clock, running=lambda: False)
    assert k.run() == "the server didn't start"
    assert clock.now > STARTUP_GRACE and programs == []


def test_keeper_restarts_the_program_but_not_in_a_loop():
    clock = Clock()
    programs = []

    def wanted():
        if programs and clock.now < 100:
            programs[-1].returncode = 1   # the program keeps ending right away
        return clock.now < 100
    k, programs = keeper(clock, wanted=wanted, programs=programs)
    k.run()
    assert 2 <= len(programs) <= 5



def test_the_real_lock_keeps_a_second_keeper_out(tmp_path):
    from wop.platforms import detect
    behavior = detect()
    first = behavior.try_lock(tmp_path / "keeper.lock")
    assert first is not None
    assert behavior.try_lock(tmp_path / "keeper.lock") is None
    behavior.release_lock(first)
    again = behavior.try_lock(tmp_path / "keeper.lock")
    assert again is not None
    behavior.release_lock(again)
