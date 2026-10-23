"""Static World of PADMAN 1.7.0 data: game modes, maps and bots.

Mirrors gamemodes.md in the project root. Bot display names and models were read from a
running server with `dumpuser`, maps from wop_maps_1.7.0.pk3.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


class WopError(Exception):
    """A problem the AI can fix by changing its request (unknown name, wrong map, ...)."""


# --------------------------------------------------------------------------- maps

MAP_GROUPS: dict[str, list[str]] = {
    "regular": [
        "wop_airplane", "wop_anteroom", "wop_backyard", "wop_bath", "wop_cabin", "wop_diner",
        "wop_huette", "wop_jail", "wop_padattic", "wop_padcrash", "wop_padcrash_dm17",
        "wop_padgarden", "wop_padgarden_night", "wop_padkitchen", "wop_padlibrary",
        "wop_padship", "wop_padshop", "wop_trashmap",
    ],
    "lps": ["wop_padatticLPS", "wop_padkitchenLPS", "wop_padlibraryLPS"],
    "ctl": [
        "wop_colorstageCTL", "wop_fridgeCTL", "wop_journeyCTL", "wop_padasiaCTL", "wop_padbaseCTL",
        "wop_padboxCTL", "wop_padcloisterCTL", "wop_padcrashCTL", "wop_trashmapCTL", "wop_westernsetCTL",
    ],
    "bb": [
        "wop_anteroomBB", "wop_backyardBB", "wop_bathBB", "wop_cabinBB", "wop_dinerBB", "wop_huetteBB",
        "wop_jailBB", "wop_padatticBB", "wop_padcrashBB", "wop_padgardenBB", "wop_padkitchenBB",
        "wop_padlibraryBB", "wop_padshipBB", "wop_padshopBB", "wop_trashmapBB",
    ],
}

MAP_GROUP_TITLES = {
    "regular": "Regular maps",
    "lps": "Last Pad Standing versions",
    "ctl": "CTL maps (lolly modes only)",
    "bb": "Big Balloon maps (Big Balloon only)",
}

ALL_MAPS: list[str] = [m for group in MAP_GROUPS.values() for m in group]


def map_group(map_name: str) -> str:
    for group, maps in MAP_GROUPS.items():
        if map_name in maps:
            return group
    raise KeyError(map_name)


# --------------------------------------------------------------------------- bots

@dataclass(frozen=True)
class Bot:
    name: str          # what addbot takes (also the clean in-game name)
    model: str         # player model, unique per bot; identifies bots that got a custom name
    look: str
    personality: str


BOTS: list[Bot] = [
    Bot("PADMAN", "padman", "Padman", "Padman"),
    Bot("Pad-RA", "padman/padra", "Padman variant", "Padman"),
    Bot("PadRock", "padman/padrock", "Padman variant", "Padman"),
    Bot("PadSoldier", "padman/padsoldier", "Padman variant", "Padman"),
    Bot("StonePad", "padman/stonepad", "Padman variant", "Padman"),
    Bot("SuperPad", "padman/superpad", "Padman variant", "Padman"),
    Bot("BioPad", "padman/biopad", "Padman variant", "Padman"),
    Bot("HellPad", "padman/hellpad", "Padman variant", "Padman"),
    Bot("PadClassic", "padman/padclassic", "Padman variant", "Padman"),
    Bot("PiratePad", "piratepad", "PiratePad", "Padman"),
    Bot("GhostPirate", "piratepad/ghostpirate", "PiratePad variant", "Padman"),
    Bot("Spooky", "piratepad/spooky", "PiratePad variant", "Padman"),
    Bot("FatPad", "fatpad", "FatPad", "Padman"),
    Bot("FATTY", "fatpad/fatty", "FatPad variant", "Padman"),
    Bot("MonsterPad", "monsterpad", "MonsterPad", "Padman"),
    Bot("MonsterHawk", "monsterpad/monsterhawk", "MonsterPad variant", "Padman"),
    Bot("PadKing", "padking", "PadKing", "Padman"),
    Bot("PadKnight", "padking/padknight", "PadKing variant", "Padman"),
    Bot("BeachPad", "beachpad", "BeachPad", "Padman"),
    Bot("PadPunk", "padpunk", "PadPunk", "Padman"),
    Bot("PadCho", "padcho", "PadCho", "Padman"),
    Bot("Pelvis", "padman/pelvis", "Padman variant", "Pelvis"),
    Bot("PadGirl", "padgirl", "PadGirl", "PadGirl"),
    Bot("PadBabe", "padgirl/padbabe", "PadGirl variant", "PadGirl"),
    Bot("PadLilly", "padlilly", "PadLilly", "PadLilly"),
    Bot("Padilla", "padlilly/padilla", "PadLilly variant", "PadLilly"),
    Bot("PaddyBell", "paddybell", "PaddyBell", "Paddy"),
    Bot("BadPaddy", "paddybell/badpaddy", "PaddyBell variant", "Paddy"),
    Bot("PaddyBee", "paddybell/paddybee", "PaddyBell variant", "Paddy"),
]

_BOTS_BY_KEY = {re.sub(r"[^a-z0-9]", "", b.name.lower()): b for b in BOTS}
_BOTS_BY_MODEL = {b.model.lower(): b for b in BOTS}


def bot_by_model(model: str) -> Bot | None:
    return _BOTS_BY_MODEL.get(model.lower())


# --------------------------------------------------------------------------- game modes

@dataclass(frozen=True)
class GameMode:
    id: int
    key: str
    name: str
    team: bool
    map_groups: tuple[str, ...]
    pointlimit: int
    timelimit: int
    default_map: str
    description: str
    aliases: tuple[str, ...] = ()
    # Default lineup from gamemodes.md: (red, blue) for team modes, bots for solo modes
    default_red: tuple[str, ...] = ()
    default_blue: tuple[str, ...] = ()
    default_bots: tuple[str, ...] = ()

    @property
    def maps(self) -> list[str]:
        return [m for g in self.map_groups for m in MAP_GROUPS[g]]


NORMAL = ("regular", "lps")

GAMEMODES: list[GameMode] = [
    GameMode(0, "ffa", "Free For All", False, NORMAL, 32, 16, "wop_padship",
             "Everyone against everyone; most frags wins.",
             ("deathmatch", "dm", "free for all", "freeforall"),
             default_bots=("PADMAN", "PadGirl", "PiratePad", "PadKing", "BeachPad")),
    GameMode(1, "tournament", "Tournament (1 vs 1)", False, NORMAL, 10, 10, "wop_padattic",
             "Two players duel; everyone else waits in line and plays the winner.",
             ("tourney", "1v1", "duel", "1 vs 1"),
             default_bots=("PadKing",)),
    GameMode(3, "syc", "Spray Your Color", False, NORMAL, 256, 16, "wop_padlibrary",
             "Collect spray cartridges from fragged players and spray them on the wall in your color.",
             ("spray your color", "spray"),
             default_bots=("PadGirl", "PadLilly", "PaddyBell", "Pelvis", "PadCho")),
    GameMode(4, "lps", "Last Pad Standing", False, NORMAL, 8, 16, "wop_padatticLPS",
             "Everyone starts with 10 lives; the last one still alive wins.",
             ("last pad standing", "last man standing", "lms"),
             default_bots=("PADMAN", "PiratePad", "MonsterPad", "PadBabe", "SuperPad")),
    GameMode(5, "ctkd", "Catch the Killerduck", False, NORMAL, 64, 16, "wop_padgarden_night",
             "Grab the Killerduck and hold it as long as you can.",
             ("catch the killerduck", "killerduck", "catch the killer duck", "ctk"),
             default_bots=("Spooky", "GhostPirate", "HellPad", "Padilla", "BadPaddy")),
    GameMode(6, "tffa", "Team Free For All", True, NORMAL, 64, 16, "wop_padgarden",
             "Team deathmatch: Red Pads vs Blue Noses, team frags count.",
             ("team free for all", "team ffa", "free for all team", "tdm", "team deathmatch"),
             default_red=("PADMAN", "PadGirl", "PadLilly", "PaddyBell", "Pelvis", "PiratePad"),
             default_blue=("FatPad", "FatPad", "FATTY")),
    GameMode(7, "ft", "Freeze Tag", True, NORMAL, 8, 16, "wop_padcrash",
             "Hits freeze players, teammates thaw them; freeze the whole other team to win the round.",
             ("freeze tag", "freeze", "freezetag"),
             default_red=("PADMAN", "PadGirl", "PadLilly", "PiratePad"),
             default_blue=("PadKing", "MonsterPad", "PaddyBell", "Pelvis")),
    GameMode(8, "ctl", "Capture The Lolly", True, ("ctl",), 8, 16, "wop_padbaseCTL",
             "Capture the flag: steal the other team's lolly and bring it to your base. Played on the lolly maps.",
             ("capture the lolly", "capture the flag", "ctf", "lolly"),
             default_red=("PADMAN", "PadGirl", "PiratePad", "BeachPad"),
             default_blue=("PadKing", "PadLilly", "MonsterPad", "PadPunk")),
    GameMode(9, "1lc", "One Lolly Capture", True, ("ctl",), 12, 16, "wop_journeyCTL",
             "One lolly in the middle; bring it to the other team's base. Played on the lolly maps.",
             ("one lolly capture", "one lolly", "one flag", "1fctf", "olc"),
             default_red=("PadSoldier", "StonePad", "PadRock", "Pad-RA"),
             default_blue=("PadKnight", "MonsterHawk", "PadCho", "PadBabe")),
    GameMode(10, "tsyc", "Spray Your Color Team", True, NORMAL, 512, 16, "wop_padshop",
             "Spray Your Color, scored per team.",
             ("spray your color team", "team spray your color", "team syc", "team spray", "syct"),
             default_red=("PadGirl", "PadLilly", "PaddyBell"),
             default_blue=("Pelvis", "PADMAN", "PadKing")),
    GameMode(11, "bb", "Big Balloon", True, ("bb",), 256, 16, "wop_padgardenBB",
             "Capture and hold the balloon points for your team. Played on the balloon maps.",
             ("big balloon", "balloon"),
             default_red=("PADMAN", "PiratePad", "PadGirl"),
             default_blue=("FatPad", "FATTY", "PadKing")),
]

_MODES_BY_ID = {m.id: m for m in GAMEMODES}


def gamemode_by_id(gametype: int) -> GameMode | None:
    return _MODES_BY_ID.get(gametype)


TEAM_NAMES = {0: "free", 1: "red", 2: "blue", 3: "spectator"}
TEAM_IDS = {"free": 0, "red": 1, "blue": 2, "spectator": 3}
_TEAM_ALIASES = {
    "red": "red", "r": "red", "redpads": "red", "redpad": "red", "redteam": "red",
    "blue": "blue", "b": "blue", "bluenoses": "blue", "bluenose": "blue", "blueteam": "blue",
    "spectator": "spectator", "spectators": "spectator", "spec": "spectator", "s": "spectator",
    "free": "free", "f": "free", "none": "free",
}


# --------------------------------------------------------------------------- name resolution

def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _suggest(text: str, options: list[str], n: int = 3) -> str:
    keys = {_key(o): o for o in options}
    close = difflib.get_close_matches(_key(text), list(keys), n=n, cutoff=0.5)
    return f" Did you mean: {', '.join(keys[c] for c in close)}?" if close else ""


def resolve_bot(text: str) -> Bot:
    key = _key(text)
    if key in _BOTS_BY_KEY:
        return _BOTS_BY_KEY[key]
    names = [b.name for b in BOTS]
    raise WopError(f"Unknown bot '{text}'.{_suggest(text, names)} Use list_bots for all names.")


def resolve_gamemode(text: str | int) -> GameMode:
    if isinstance(text, int) or str(text).strip().isdigit():
        mode = gamemode_by_id(int(text))
        if mode:
            return mode
        raise WopError(f"There is no game mode with number {text}. Use list_gamemodes.")
    key = _key(str(text))
    for mode in GAMEMODES:
        if key in {_key(mode.key), _key(mode.name), *(_key(a) for a in mode.aliases)}:
            return mode
    options = [m.name for m in GAMEMODES] + [m.key for m in GAMEMODES]
    raise WopError(f"Unknown game mode '{text}'.{_suggest(str(text), options)} Use list_gamemodes.")


def resolve_map(text: str, mode: GameMode | None = None) -> str:
    """Find a map by loose name: 'pad garden', 'padgarden night', 'padbase' (+CTL in a lolly mode)."""
    key = _key(text)
    if key.startswith("wop"):
        key = key[3:]
    by_key = {_key(m)[3:]: m for m in ALL_MAPS}
    if mode and (key not in by_key or by_key[key] not in mode.maps):
        # "padbase" in Capture The Lolly means wop_padbaseCTL, "padgarden" in Big Balloon means wop_padgardenBB
        for group in mode.map_groups:
            if group in ("ctl", "bb") and key + group in by_key:
                return by_key[key + group]
    if key in by_key:
        return by_key[key]
    raise WopError(f"Unknown map '{text}'.{_suggest('wop_' + key, ALL_MAPS)} Use list_maps for all names.")


def check_map_fits(map_name: str, mode: GameMode) -> None:
    if map_name in mode.maps:
        return
    group = map_group(map_name)
    if mode.map_groups == ("ctl",):
        hint = "Lolly modes need a CTL map"
    elif mode.map_groups == ("bb",):
        hint = "Big Balloon needs a BB map"
    else:
        hint = f"{MAP_GROUP_TITLES[group]} only work in {'Capture The Lolly / One Lolly Capture' if group == 'ctl' else 'Big Balloon'}"
    raise WopError(
        f"{map_name} doesn't work in {mode.name}. {hint}. Maps that work: {', '.join(mode.maps)}."
    )


def resolve_team(text: str) -> str:
    team = _TEAM_ALIASES.get(_key(text))
    if not team:
        raise WopError(f"Unknown team '{text}'. Use red, blue, spectator or free.")
    return team
