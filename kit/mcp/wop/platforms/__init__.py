"""The behavior for the OS this runs on: detect() once, then pass it around (see base.py)."""

from __future__ import annotations

import sys

from .base import FirewallCheck, NetworkProblem, PlatformBehavior, Shortcut

__all__ = ["FirewallCheck", "NetworkProblem", "PlatformBehavior", "Shortcut", "detect", "for_name"]


def for_name(name: str) -> PlatformBehavior:
    """windows / mac / linux (also accepts sys.platform values)."""
    if name in ("windows", "win32"):
        from .windows import WindowsBehavior
        return WindowsBehavior()
    if name in ("mac", "darwin"):
        from .mac import MacBehavior
        return MacBehavior()
    if name == "linux" or name.startswith("linux"):
        from .linux import LinuxBehavior
        return LinuxBehavior()
    raise RuntimeError(f"World of PADMAN servers aren't supported on {name}.")


def detect() -> PlatformBehavior:
    return for_name(sys.platform)
