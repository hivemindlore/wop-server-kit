"""At most one server per install, and nothing left running once it's stopped (processes.py)."""

from pathlib import Path

import pytest

from wop import actions
from wop.catalog import WopError
from wop.platforms.linux import LinuxBehavior
from wop.platforms.posix import matching_pids
from wop.processes import ServerProcesses

HOME = Path("/data/WoPServer/home")
OTHER = Path("/data/sandbox/home")


def server(home=HOME):
    return f"/data/WoPServer/game/wopded.x86_64 +set fs_basepath /g +set fs_homepath {home} +exec server-friends.cfg"


def keeper(home=HOME):
    return f"/py/python -c from wop.online_keeper import main --home {home} --port 27960"


def playit(home=HOME):
    return f"/data/WoPServer/tools/playit-1.0.10 --secret-path {home / 'playit' / 'playit.toml'}"


class Machine(LinuxBehavior):
    """A process table instead of the real computer."""

    def __init__(self, processes: dict[int, str], ignores_quit=False):
        self.processes = dict(processes)
        self.ignores_quit = ignores_quit
        self.ended: list[int] = []
        self.launched: list[list[str]] = []
        self.locked = False

    def find_processes(self, *markers):
        return [pid for pid, args in self.processes.items() if all(m in args for m in markers)]

    def end_process(self, pid):
        self.ended.append(pid)
        self.processes.pop(pid, None)

    def try_lock(self, path):
        if self.locked:
            return None
        self.locked = True
        return path

    def release_lock(self, handle):
        self.locked = False


class Rcon:
    """Answers while one of the machine's servers is up (and answering)."""
    port = 27960

    def __init__(self, machine: Machine, answering=True):
        self.machine, self.answering, self.sent = machine, answering, []

    def servers(self):
        return [pid for pid, args in self.machine.processes.items() if args == server()]

    def is_running(self, retry=False):
        return self.answering and bool(self.servers())

    def command(self, cmd, timeout=2.0, quiet=0.3, retry=True):
        self.sent.append(cmd)
        if cmd == "quit" and not self.machine.ignores_quit:
            for pid in self.servers():
                del self.machine.processes[pid]
        return ""


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def guard(machine, clock=None):
    clock = clock or Clock()
    return ServerProcesses(machine, HOME, clock=clock, sleep=clock.sleep)


def test_stop_asks_first_and_takes_the_internet_helpers_along():
    machine = Machine({10: server(), 11: keeper(), 12: playit(), 20: server(OTHER), 21: keeper(OTHER)})
    rcon = Rcon(machine)
    assert guard(machine).stop(rcon) is True
    assert rcon.sent == ["quit"]
    assert machine.ended == [11, 12]                     # the server quit by itself
    assert set(machine.processes) == {20, 21}            # another install is never touched


def test_stop_ends_a_server_that_does_not_quit():
    machine = Machine({10: server(), 11: keeper()}, ignores_quit=True)
    clock = Clock()
    assert guard(machine, clock).stop(Rcon(machine)) is True
    assert machine.ended == [10, 11] and clock.now >= 10  # it had its chance first
    assert machine.processes == {}


def test_stop_ends_a_server_that_does_not_answer_right_away():
    machine = Machine({10: server()})
    clock = Clock()
    assert guard(machine, clock).stop(Rcon(machine, answering=False)) is True
    assert machine.ended == [10] and clock.now == 0


def test_stop_when_nothing_runs():
    machine = Machine({20: server(OTHER)})
    assert guard(machine).stop(Rcon(machine)) is False
    assert guard(machine).stop(None) is False
    assert machine.ended == []


def test_stop_says_so_when_a_server_cannot_be_ended():
    class Stubborn(Machine):
        def end_process(self, pid):
            self.ended.append(pid)

    machine = Stubborn({10: server()})
    with pytest.raises(WopError, match="didn't stop"):
        guard(machine).stop(Rcon(machine, answering=False))


def test_make_room_keeps_one_answering_server():
    machine = Machine({10: server()})
    assert guard(machine).make_room(Rcon(machine)) is True
    assert machine.ended == []


def test_make_room_ends_a_server_that_never_answers():
    machine = Machine({10: server(), 11: keeper(), 12: playit()})
    clock = Clock()
    assert guard(machine, clock).make_room(Rcon(machine, answering=False)) is False
    assert set(machine.ended) == {10, 11, 12} and clock.now >= 20   # it got time to finish loading


def test_make_room_waits_for_a_server_that_is_still_loading():
    machine = Machine({10: server()})
    rcon = Rcon(machine, answering=False)
    clock = Clock()

    def sleep(seconds):
        clock.now += seconds
        rcon.answering = clock.now >= 6          # done loading after 6 seconds

    assert ServerProcesses(machine, HOME, clock=clock, sleep=sleep).make_room(rcon) is True
    assert machine.ended == []


def test_make_room_ends_two_servers_so_one_can_start():
    machine = Machine({10: server(), 13: server()}, ignores_quit=True)
    assert guard(machine).make_room(Rcon(machine)) is False
    assert sorted(machine.ended) == [10, 13]


def test_make_room_with_nothing_running():
    machine = Machine({20: server(OTHER)})
    assert guard(machine).make_room(Rcon(machine)) is False
    assert guard(machine).make_room(None) is False
    assert machine.ended == []


def test_stray_playit_is_ended_only_without_its_keeper():
    machine = Machine({11: keeper(), 12: playit()})
    guard(machine).end_stray_playit()
    assert machine.ended == []
    del machine.processes[11]
    guard(machine).end_stray_playit()
    assert machine.ended == [12]


def test_one_start_at_a_time():
    machine = Machine({})
    clock = Clock()
    g = guard(machine, clock)
    with g.starting():
        with pytest.raises(WopError, match="already being started"):
            with g.starting():
                pass
    assert clock.now > 60
    with g.starting():                           # free again afterwards
        assert machine.locked


def test_game_start_never_starts_a_second_server(monkeypatch):
    machine = Machine({10: server()})
    game = actions.Game(Rcon(machine), use_log=False, behavior=machine)
    monkeypatch.setattr(actions.config, "home_dir", lambda: HOME)
    monkeypatch.setattr(actions.Game, "state", lambda self: type("S", (), {"to_dict": lambda s: {}})())
    monkeypatch.setattr(type(game.online), "start_keeper", lambda self: False)
    monkeypatch.setattr(actions.launcher, "launch_server", lambda *a: machine.launched.append(list(a)))
    assert game.start_server()["result"] == "The server is already running."
    assert machine.launched == [] and not machine.locked


def test_game_stop_always_ends_the_server(monkeypatch):
    machine = Machine({10: server(), 11: keeper()}, ignores_quit=True)
    monkeypatch.setattr(actions.config, "home_dir", lambda: HOME)
    monkeypatch.setattr("wop.processes.QUIT_WAIT", 0)
    game = actions.Game(Rcon(machine), use_log=False, behavior=machine)
    assert game.stop_server() == {"result": "Server stopped."}
    assert machine.processes == {}
    assert game.stop_server() == {"result": "The server isn't running."}


def test_ps_output_is_read():
    out = (f"  101 {server()}\n"
           f"  102 {server(OTHER)}\n"
           "  103 /bin/bash -c ps\n"
           f"  104 {server()}\n")
    assert matching_pids(out, ("wopded.x86_64", "fs_homepath", str(HOME)), me=104) == [101]
