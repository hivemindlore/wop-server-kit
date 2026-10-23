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


# ^0..^7 are the game's colors; any other ^x code (WoP has a few extra) falls back to the default color
_CODE = re.compile(r"\^(.)")
COLORS = {"0": "black", "1": "red", "2": "green", "3": "yellow", "4": "blue", "5": "cyan", "6": "magenta",
          "7": None}


def color_segments(line: str) -> list[dict]:
    """'^1Pad^4King^7: hi' -> [{'text': 'Pad', 'color': 'red'}, {'text': 'King', 'color': 'blue'}, ...]."""
    segments: list[dict] = []
    color = None
    pos = 0
    for match in _CODE.finditer(line):
        if match.start() > pos:
            segments.append({"text": line[pos:match.start()], "color": color})
        color = COLORS.get(match.group(1))
        pos = match.end()
    if pos < len(line):
        segments.append({"text": line[pos:], "color": color})
    return segments


class LogTail:
    """Follow the log for a viewer: new complete lines since last time; notices when a new server starts a new log."""

    def __init__(self, path: Path):
        self.log = ServerLog(path)
        self.offset = 0
        self.partial = ""

    def last_lines(self, count: int) -> list[str]:
        size = self.log.size()
        text = self.log.read_from(max(0, size - 200 * count))
        lines = text.splitlines()
        if size > 200 * count and lines:
            lines = lines[1:]                 # the first line is probably cut off
        self.offset, self.partial = size, ""
        return lines[-count:]

    def new_lines(self) -> tuple[bool, list[str]]:
        """(restarted, lines). restarted: the log got shorter, so a new server started a new log."""
        size = self.log.size()
        restarted = size < self.offset
        if restarted:
            self.offset, self.partial = 0, ""
        if size == self.offset:
            return restarted, []
        try:
            with open(self.log.path, "rb") as f:
                f.seek(self.offset)
                data = f.read(size - self.offset)
        except OSError:
            return restarted, []
        self.offset += len(data)
        text = self.partial + data.replace(b"\0", b"").decode("latin-1", errors="replace")
        lines = text.split("\n")
        self.partial = lines.pop()
        return restarted, [line.rstrip("\r") for line in lines]
