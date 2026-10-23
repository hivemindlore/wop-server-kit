"""The game server's processes for one install: at most one server, and nothing left over once it's stopped.

Asking the server (rcon) isn't enough to know whether it runs: it may still be loading a map, hang, or not answer
because it limits how often it's asked. So the processes are looked at too, recognised by their command line:
the server gets this install's home folder (fs_homepath), the internet-play keeper gets --home, playit's program
its folder in home/playit. Another install (a test copy, the app's sandbox) is never touched.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .catalog import WopError
from .platforms import PlatformBehavior
from .rcon import ServerOffline

QUIT_WAIT = 10.0       # seconds the server gets to quit by itself
ENDED_WAIT = 5.0       # an ended process may take a moment to be gone
LOAD_WAIT = 20.0       # a server that doesn't answer yet may still be loading
LOCK_WAIT = 60.0       # another start (the app and Claude at once) may take this long
START_LOCK = "server-start.lock"


class ServerProcesses:
    def __init__(self, behavior: PlatformBehavior, home: Path,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.behavior = behavior
        self.home = home
        self.clock = clock
        self.sleep = sleep

    def servers(self) -> list[int]:
        return self.behavior.find_processes(self.behavior.server_bin.name, "fs_homepath", str(self.home))

    def keepers(self) -> list[int]:
        return self.behavior.find_processes("online_keeper", "--home", str(self.home))

    def playit(self) -> list[int]:
        return self.behavior.find_processes("--secret-path", str(self.home / "playit"))

    def _end(self, pids: list[int]) -> None:
        for pid in pids:
            try:
                self.behavior.end_process(pid)
            except OSError:
                pass

    def end_helpers(self) -> None:
        """The internet-play keeper first (so it can't start playit again), then playit."""
        self._end(self.keepers())
        self._end(self.playit())

    def end_stray_playit(self) -> None:
        """playit's program without a keeper (the keeper was ended some other way)."""
        if not self.keepers():
            self._end(self.playit())

    def stop(self, rcon) -> bool:
        """Stop the server: asked to quit first, ended if it doesn't. The internet-play helpers go with it.
        True if a server was running. rcon may be None (no settings to ask the server with)."""
        answering = rcon is not None and rcon.is_running()
        if answering:
            try:
                rcon.command("quit", timeout=1.0)
            except ServerOffline:
                pass
        servers = self.servers()
        was_running = answering or bool(servers)
        deadline = self.clock() + (QUIT_WAIT if answering else 0)
        while servers and self.clock() < deadline:
            self.sleep(1.0)
            servers = self.servers()
        self._end(servers)
        self.end_helpers()
        if servers:
            deadline = self.clock() + ENDED_WAIT
            while self.servers():
                if self.clock() > deadline:
                    raise WopError("The server didn't stop. Restarting the computer stops it for sure.")
                self.sleep(0.5)
        return was_running

    def make_room(self, rcon) -> bool:
        """Before a start: True if the server already runs (then nothing is started). A server that doesn't
        answer gets a little time (it may be loading), then it's ended. Two at once are both ended."""
        servers = self.servers()
        if rcon is not None and rcon.is_running(retry=True):
            if len(servers) <= 1:
                return True
        elif servers:
            deadline = self.clock() + LOAD_WAIT
            while self.clock() < deadline:
                self.sleep(2.0)
                if rcon is not None and rcon.is_running():
                    if len(self.servers()) <= 1:
                        return True
                    break
        if servers:
            self.stop(rcon)
        return False

    @contextmanager
    def starting(self) -> Iterator[None]:
        """One start at a time (the app and Claude may ask at the same moment)."""
        lock = self.home / "wop" / START_LOCK
        deadline = self.clock() + LOCK_WAIT
        while (handle := self.behavior.try_lock(lock)) is None:
            if self.clock() > deadline:
                raise WopError("The server is already being started. Try again in a minute.")
            self.sleep(1.0)
        try:
            yield
        finally:
            self.behavior.release_lock(handle)
