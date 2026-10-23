"""Downloading what the kit needs (the game, the program for playing over the internet), checked by sha256.

Used by the setup (wopkit.py) and by the Claude connection, so both fetch files the same way.
"""

from __future__ import annotations

import hashlib
import urllib.request
from collections.abc import Callable
from pathlib import Path

USER_AGENT = "wop-server-kit"


def fetch(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(url: str, dest: Path, expected_size: int | None = None,
             progress: Callable[[int, int], None] | None = None) -> None:
    """Download to dest, continuing a half-finished download. progress(done, total) at every new percent."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = dest.stat().st_size if dest.exists() else 0
    if expected_size and have == expected_size:
        return
    headers = {"User-Agent": USER_AGENT}
    if have:
        headers["Range"] = f"bytes={have}-"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        if have and r.status != 206:      # server ignored the range: start over
            have = 0
        total = expected_size or (have + int(r.headers.get("Content-Length") or 0))
        last = -1
        with open(dest, "ab" if have else "wb") as f:
            while chunk := r.read(1024 * 1024):
                f.write(chunk)
                have += len(chunk)
                if progress and total and int(have * 100 / total) != last:
                    last = int(have * 100 / total)
                    progress(have, total)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()
