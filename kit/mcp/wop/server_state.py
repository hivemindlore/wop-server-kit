"""Read what the server is doing right now: map, mode, weapons, limits and every player."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import TEAM_NAMES, bot_by_model, gamemode_by_id

_COLOR = re.compile(r"\^[^^]")
# "  6     0    2    0 Fat^1Pad          ^7bot      16384"
# The columns are num, score, team, ping (the header line of `status` leaves out team).
_STATUS_ROW = re.compile(r"^\s*(\d+)\s+(-?\d+)\s+(\d+)\s+(\d+|CNCT|ZMBI)\s(.*)\^7(\S+)\s+(\d+)\s*$")


def clean(name: str) -> str:
    """Strip color codes: '^4Pirate^1Pad' -> 'PiratePad'."""
    return _COLOR.sub("", name).strip()


@dataclass
class Player:
    num: int
    name: str            # with color codes
    clean_name: str
    team: str            # free / red / blue / spectator
    bot: bool
    score: int
    ping: int
    bot_type: str | None = None   # catalog bot name, e.g. "FatPad" for "FatPad2"
    skill: int | None = None

    def to_dict(self) -> dict:
        d = {"num": self.num, "name": self.clean_name, "team": self.team, "bot": self.bot,
             "score": self.score, "ping": self.ping}
        if self.bot:
            d["bot_type"] = self.bot_type
            d["skill"] = self.skill
        return d


@dataclass
class GameState:
    map: str
    gametype: int
    instapad: bool
    pointlimit: int
    timelimit: int
    maxclients: int
    lps_lives: int | None
    players: list[Player] = field(default_factory=list)
    spawn_protect: int | None = None   # InstaPad spawn protection in seconds; None: plain WoP 1.7.0 (always 6)

    @property
    def mode(self):
        return gamemode_by_id(self.gametype)

    @property
    def team_mode(self) -> bool:
        return bool(self.mode and self.mode.team)

    @property
    def bots(self) -> list[Player]:
        return [p for p in self.players if p.bot]

    @property
    def humans(self) -> list[Player]:
        return [p for p in self.players if not p.bot]

    def on_team(self, team: str) -> list[Player]:
        return [p for p in self.players if p.team == team]

    def to_dict(self) -> dict:
        mode = self.mode
        d = {
            "running": True,
            "map": self.map,
            "gamemode": {"id": self.gametype, "name": mode.name if mode else f"unknown ({self.gametype})",
                         "team_mode": self.team_mode},
            "weapons": "instapad" if self.instapad else "regular",
            "pointlimit": self.pointlimit,
            "timelimit_minutes": self.timelimit,
            "slots": {"max": self.maxclients, "used": len(self.players),
                      "free": self.maxclients - len(self.players)},
        }
        if self.gametype == 4 and self.lps_lives is not None:
            d["lps_lives"] = self.lps_lives
        if self.instapad:
            d["spawn_protection_seconds"] = 6 if self.spawn_protect is None else self.spawn_protect
        if self.team_mode:
            for team in ("red", "blue", "spectator"):
                d[team] = [p.clean_name + ("" if p.bot else " (human)") for p in self.on_team(team)]
        d["players"] = [p.to_dict() for p in self.players]
        return d


def parse_keyvalues(text: str) -> dict[str, str]:
    """Parse `serverinfo` / `dumpuser` output: one 'key<spaces>value' per line."""
    values = {}
    for line in text.splitlines():
        match = re.match(r"^(\S+)\s+(.*?)\s*$", line)
        if match and not set(match.group(1)) <= {"-"}:
            values[match.group(1)] = match.group(2)
    return values


def parse_status(text: str) -> tuple[str | None, list[Player]]:
    map_name = None
    players = []
    for line in text.splitlines():
        if line.startswith("map:"):
            map_name = line.split(":", 1)[1].strip()
            continue
        match = _STATUS_ROW.match(line)
        if not match:
            continue
        num, score, team, ping, name, address, _rate = match.groups()
        name = name.rstrip()
        players.append(Player(
            num=int(num), name=name, clean_name=clean(name), team=TEAM_NAMES.get(int(team), "free"),
            bot=address == "bot", score=int(score), ping=int(ping) if ping.isdigit() else 0,
        ))
    return map_name, players


def _int(value: str | None, default: int = 0) -> int:
    try:
        return int(float(value or ""))
    except ValueError:
        return default


def read_state(rcon, log=None, bot_details: bool = True) -> GameState:
    """status + serverinfo over rcon; bot model and skill from the server log when possible
    (each `dumpuser` costs one of the few rcon packets the server allows per second)."""
    map_name, players = parse_status(rcon.command("status"))
    info = parse_keyvalues(rcon.command("serverinfo"))

    # Players_Team lists the team of every connected client in client-number order.
    teams = info.get("Players_Team", "").split()
    if len(teams) == len(players):
        for player, team in zip(sorted(players, key=lambda p: p.num), teams):
            player.team = TEAM_NAMES.get(_int(team), player.team)

    if bot_details:
        clients = log.update() if log is not None else {}
        for player in players:
            if not player.bot:
                continue
            known = clients.get(player.num)
            if known and known.model and clean(known.name) == player.clean_name:
                model, skill = known.model, known.skill
            else:
                user = parse_keyvalues(rcon.command(f"dumpuser {player.num}"))
                model, skill = user.get("model", ""), _int(user.get("skill"), 3) or None
            bot = bot_by_model(model)
            player.bot_type = bot.name if bot else None
            player.skill = skill

    lps = info.get("g_LPS_startlives")
    return GameState(
        map=info.get("mapname") or map_name or "?",
        gametype=_int(info.get("g_gametype")),
        instapad=info.get("g_instaPad", "0").strip() == "1",
        pointlimit=_int(info.get("pointlimit")),
        timelimit=_int(info.get("timelimit")),
        maxclients=_int(info.get("sv_maxclients"), 16),
        lps_lives=_int(lps) if lps is not None else None,
        players=players,
        spawn_protect=_int(info["g_spawnProtect"]) if "g_spawnProtect" in info else None,
    )
