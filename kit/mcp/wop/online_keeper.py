"""Keeps playit's program running while the game server runs, for playing over the internet (see online.py).

    python -c "...; from wop.online_keeper import main; main()" --home <root>/home --port 27960

Started in the background by online.Online.start_keeper whenever the server starts with internet play on.
Only one runs per install (a lock file). It ends the program, and itself, when internet play is switched off
or the server is gone, however it stopped (the app, Claude, closing its window, a crash). The server is
asked whether it runs only every few seconds: players coming through playit share its question budget.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from collections.abc import Callable

POLL = 5.0             # seconds between looks
STARTUP_GRACE = 120.0  # how long the server may take to answer after the keeper started
GONE_AFTER = 20.0      # the server is gone when it hasn't answered for this long
RESTART_PAUSE = 30.0   # at most one start of the program per this many seconds
LOCK_TRIES = 6         # someone may be peeking at the lock (status checks) just as the keeper starts


class Keeper:
    def __init__(self, wanted: Callable[[], bool], server_running: Callable[[], bool],
                 start_program: Callable[[], subprocess.Popen], log: Callable[[str], None] = lambda _: None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.wanted = wanted
        self.server_running = server_running
        self.start_program = start_program
        self.log = log
        self.clock = clock
        self.sleep = sleep

    def run(self) -> str:
        """Until there's no reason left to run; returns that reason."""
        began = self.clock()
        seen: float | None = None
        program: subprocess.Popen | None = None
        next_start = 0.0
        try:
            while True:
                if not self.wanted():
                    return "internet play was switched off"
                now = self.clock()
                if self.server_running():
                    seen = now
                elif seen is None:
                    if now - began > STARTUP_GRACE:
                        return "the server didn't start"
                elif now - seen > GONE_AFTER:
                    return "the server stopped"
                if seen is not None and (program is None or program.poll() is not None) and now >= next_start:
                    if program is not None:
                        self.log(f"playit ended (exit code {program.returncode}); starting it again")
                    next_start = now + RESTART_PAUSE
                    program = self.start_program()
                    self.log("playit started")
                self.sleep(POLL)
        finally:
            if program is not None and program.poll() is None:
                program.terminate()
                try:
                    program.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    program.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args(argv)
    os.environ["WOP_HOME"] = args.home   # the rcon password and the playit files are found from here

    from .online import KEEPER_LOCK, Online
    from .platforms import detect
    from .rcon import Rcon

    behavior = detect()
    online = Online(behavior, Rcon(port=args.port))
    lock = None
    for _ in range(LOCK_TRIES):
        lock = behavior.try_lock(online.folder / KEEPER_LOCK)
        if lock is not None:
            break
        time.sleep(0.5)
    if lock is None:
        return 0   # another keeper runs already
    log_file = online.folder / "keeper.log"
    log_file.write_text("", encoding="utf-8")

    def log(text: str) -> None:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")

    def start_program() -> subprocess.Popen:
        return behavior.start_child_hidden(online.program_args(), cwd=online.folder)

    try:
        reason = Keeper(online.wanted, online.rcon.is_running, start_program, log).run()
        log(f"stopped: {reason}")
    finally:
        behavior.release_lock(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
