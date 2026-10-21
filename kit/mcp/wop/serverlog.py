"""Follow home\\wop\\qconsole.log (the kit runs the server with logfile 2).

The server only answers about one rcon packet a second once a small burst is used up, so
details that would otherwise need one `dumpuser` per bot (model, skill) are read from the
`ClientUserinfoChanged` lines in the log instead. Batches of commands also report their
errors here, because the output of an `exec`ed file never comes back over rcon.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path

_USERINFO = re.compile(r"^ClientUserinfoChanged: (\d+) (.*)$")
_DISCONNECT = re.compile(r"^ClientDisconnect: (\d+)")


@dataclass
class ClientInfo:
    name: str
    model: str
    skill: int | None


def parse_userinfo(text: str) -> dict[str, str]:
    """'n\\FatPad2\\t\\2\\model\\fatpad\\skill\\ 3.00' -> {'n': 'FatPad2', 't': '2', ...}"""
    parts = text.split("\\")
    return {parts[i]: parts[i + 1] for i in range(0, len(parts) - 1, 2)}


class ServerLog:
    def __init__(self, path: Path):
        self.path = path
        self._offset = 0
        self._partial = b""
        self._lock = threading.Lock()
        self.clients: dict[int, ClientInfo] = {}

    def exists(self) -> bool:
        return self.path.exists()

    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def read_from(self, offset: int) -> str:
        try:
            with open(self.path, "rb") as f:
                f.seek(offset)
                data = f.read()
        except OSError:
            return ""
        return data.replace(b"\0", b"").decode("latin-1", errors="replace")

    def update(self) -> dict[int, ClientInfo]:
        """Read what's new since last time and keep track of who's connected."""
        with self._lock:
            size = self.size()
            if size < self._offset:          # the server restarted and started a new log
                self._offset, self._partial, self.clients = 0, b"", {}
            if size == self._offset:
                return self.clients
            try:
                with open(self.path, "rb") as f:
                    f.seek(self._offset)
                    data = self._partial + f.read(size - self._offset)
            except OSError:
                return self.clients
            self._offset = size
            lines = data.split(b"\n")
            self._partial = lines.pop()       # last line may still be incomplete
            for raw in lines:
                line = raw.replace(b"\0", b"").decode("latin-1", errors="replace").strip()
                if match := _USERINFO.match(line):
                    info = parse_userinfo(match.group(2))
                    skill = info.get("skill", "").strip()
                    self.clients[int(match.group(1))] = ClientInfo(
                        name=info.get("n", ""), model=info.get("model", ""),
                        skill=int(float(skill)) if skill else None)
                elif match := _DISCONNECT.match(line):
                    self.clients.pop(int(match.group(1)), None)
            return self.clients
