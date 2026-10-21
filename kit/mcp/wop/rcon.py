"""Remote console (rcon) over UDP, the same way `/rcon` works in the game.

One command per packet. The server silently drops rcon packets from an address once a burst
of 10 is used up, and then allows only 1 per second, so this client keeps the same budget and
waits instead of losing commands. Each command uses a fresh socket, so a late reply to one
command can never be mistaken for the reply to the next.
"""

from __future__ import annotations

import socket
import threading
import time

from . import config
from .catalog import WopError

PREFIX = b"\xff\xff\xff\xff"
MIN_GAP = 0.15      # seconds between commands
BURST = 9           # the server allows 10; keep one spare for an admin typing /rcon
REFILL = 1.05       # seconds per extra packet once the burst is used


class ServerOffline(WopError):
    pass


class Rcon:
    def __init__(self, host: str = "127.0.0.1", port: int | None = None, password: str | None = None):
        self.host = host
        self._port = port
        self._password = password
        self._lock = threading.Lock()
        self._last = 0.0
        self._tokens = float(BURST)
        self._refilled = time.monotonic()

    @property
    def port(self) -> int:
        return self._port or config.port()

    def _take_token(self) -> None:
        now = time.monotonic()
        self._tokens = min(BURST, self._tokens + (now - self._refilled) / REFILL)
        self._refilled = now
        if self._tokens < 1:
            time.sleep((1 - self._tokens) * REFILL)
            self._tokens, self._refilled = 1.0, time.monotonic()
        self._tokens -= 1
        wait = MIN_GAP - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)

    def _send(self, packet: bytes, timeout: float, quiet: float) -> list[bytes] | None:
        self._take_token()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(packet, (self.host, self.port))
            sock.settimeout(timeout)
            try:
                chunks = [sock.recv(65536)]
            except (TimeoutError, socket.timeout, ConnectionResetError):
                # Windows reports "port unreachable" as ConnectionResetError
                return None
            sock.settimeout(quiet)
            while True:
                try:
                    chunks.append(sock.recv(65536))
                except (TimeoutError, socket.timeout, ConnectionResetError):
                    return chunks
        finally:
            sock.close()
            self._last = time.monotonic()

    def command(self, cmd: str, timeout: float = 2.0, quiet: float = 0.3, retry: bool = True) -> str:
        """Send one console command and return what the server printed."""
        password = self._password or config.rcon_password()
        packet = PREFIX + f"rcon {password} {cmd}".encode("latin-1", errors="replace")
        with self._lock:
            chunks = self._send(packet, timeout, quiet)
            if chunks is None and retry:
                # Maybe dropped by the rate limit (someone else used rcon too): wait for a fresh packet
                self._tokens = 0.0
                chunks = self._send(packet, timeout, quiet)
        if chunks is None:
            raise ServerOffline(
                f"The WoP server isn't answering on UDP port {self.port}. "
                "It's probably not running; use start_server."
            )
        text = "".join(_payload(c) for c in chunks)
        if "Bad rconpassword" in text:
            raise WopError("The server rejected the rcon password from server-friends.cfg.")
        return text

    def is_running(self, retry: bool = False) -> bool:
        try:
            self.command("status", timeout=1.0, quiet=0.1, retry=retry)
            return True
        except ServerOffline:
            return False


def _payload(packet: bytes) -> str:
    if packet.startswith(PREFIX):
        packet = packet[4:]
    if packet.startswith(b"print\n"):
        packet = packet[6:]
    return packet.decode("latin-1", errors="replace")
