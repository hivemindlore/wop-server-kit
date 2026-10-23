"""Several maps that play one after another, then start over (a map loop).

At the end of a match the game runs `vstr nextmap`, and every time a map loads the engine resets nextmap to
"map_restart 0", which is why a single map simply replays. A loop is a chain of steps like WoP's own rotation.cfg:
step i loads its map and then points nextmap at step i+1 (the last one back at step 0). Because loading a map resets
nextmap, the first map is loaded directly and nextmap is pointed at step 1 right after it.
The maps are also kept in wop_maplist, so the kit can tell later which loop is running.
"""

from __future__ import annotations

from .catalog import ALL_MAPS, GameMode, WopError, check_map_fits, resolve_map

MAX_MAPS = 16
LIST = "wop_maplist"
STEP = "wop_rot"


def clean_maps(maps: list[str], mode: GameMode) -> list[str]:
    """The maps as their real names, each fitting the mode, without repeats."""
    names: list[str] = []
    for text in maps:
        name = resolve_map(str(text), mode)
        check_map_fits(name, mode)
        if name not in names:
            names.append(name)
    if not names:
        raise WopError("Pick at least one map.")
    if len(names) > MAX_MAPS:
        raise WopError(f"That's {len(names)} maps; a loop can have up to {MAX_MAPS}.")
    return names


def define(maps: list[str]) -> list[str]:
    """Commands that set up the loop's steps and remember the maps (run before loading the first map)."""
    lines = []
    if len(maps) > 1:
        lines = [f'set {STEP}{i} "map {name}; set nextmap vstr {STEP}{(i + 1) % len(maps)}"'
                 for i, name in enumerate(maps)]
    return lines + [f'set {LIST} "{" ".join(maps)}"']


def start(maps: list[str]) -> list[str]:
    """Commands that run right after the first map loaded, so its end loads the second map."""
    return [f"set nextmap vstr {STEP}1"] if len(maps) > 1 else []


def parse(text: str | None) -> list[str]:
    """The maps of wop_maplist (unknown names left out)."""
    return [name for name in (text or "").split() if name in ALL_MAPS]


def describe(maps: list[str]) -> str:
    short = [name.removeprefix("wop_") for name in maps]
    if len(short) == 1:
        return short[0]
    return f"{', '.join(short[:-1])} and {short[-1]} in a loop"
