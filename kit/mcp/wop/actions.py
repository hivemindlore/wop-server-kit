"""Gameplay actions: validate the request, send the console commands, report what happened.

Rules learned from the real server:
- g_gametype and g_instaPad only apply when a map loads, so they're set before `map`.
- Bots stay through `map` and `map_restart`, so a full switch starts with `kick allbots`.
- A bot moved with `forceteam` goes back to its own team at the next map restart (end of warmup,
  match replay), so bots change team by being re-added on the new team.
- rcon allows only a few packets a second, so a group of commands is written to mcp-batch.cfg and
  run with one `exec`; the server log shows when it's done and what went wrong.
"""

from __future__ import annotations

import re
import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import config, launcher
from .catalog import (
    BOTS, GAMEMODES, MAP_GROUP_TITLES, MAP_GROUPS, Bot, WopError, check_map_fits,
    resolve_bot, resolve_gamemode, resolve_map, resolve_team,
)
from .config_files import reset_to_defaults, set_cfg_value
from .online import Online
from .platforms import PlatformBehavior, detect
from .processes import ServerProcesses
from .rcon import Rcon
from .server_state import GameState, Player, clean, read_state
from .serverlog import ServerLog

MAP_TIMEOUT = 30.0
SPAWN_PROTECT_SECONDS = 3   # WoP's new default; 1.7.0 used 6
BATCH_FILE = "mcp-batch.cfg"
_ERROR_MARKERS = ("error", "can't find", "couldn't", "unknown", "not defined", "usage:", "invalid")


def _problems(cmd_label: str, text: str) -> list[str]:
    problems = []
    for line in text.splitlines():
        low = line.lower()
        if any(m in low for m in _ERROR_MARKERS) and "sound" not in low and "shader" not in low:
            problems.append(f"{cmd_label}: {clean(line).strip()}" if cmd_label else clean(line).strip())
    return problems


@dataclass
class LineupBot:
    bot: Bot
    team: str | None      # red / blue, or None in solo modes
    skill: int
    custom_name: str | None = None


def sanitize(text: str, limit: int = 64) -> str:
    """Keep player text from breaking out of a console command."""
    return re.sub(r'["\\;\r\n]', "", str(text)).strip()[:limit]


def _skill(value) -> int:
    try:
        skill = int(value)
    except (TypeError, ValueError):
        raise WopError(f"Skill must be a whole number from 1 (easy) to 5 (hard), not '{value}'.") from None
    if not 1 <= skill <= 5:
        raise WopError(f"Skill must be from 1 (easy) to 5 (hard), not {skill}.")
    return skill


def _weapons(value: str) -> bool:
    key = re.sub(r"[^a-z]", "", str(value).lower())
    if key in {"instapad", "insta", "instagib", "instakill", "oneshot", "onehit"}:
        return True
    if key in {"regular", "normal", "default", "standard", "all", "allweapons"}:
        return False
    raise WopError(f"Unknown weapons setting '{value}'. Use 'regular' or 'instapad'.")


class Game:
    def __init__(self, rcon: Rcon | None = None, log: ServerLog | None = None, use_log: bool = True,
                 behavior: PlatformBehavior | None = None):
        self.rcon = rcon or Rcon()
        self._behavior = behavior
        self.use_log = use_log
        self.log = log or (ServerLog(config.cfg_dir() / "qconsole.log") if use_log else None)
        self._online: Online | None = None

    # ------------------------------------------------------------------ helpers

    @property
    def behavior(self) -> PlatformBehavior:
        """What differs per OS; detected on first use unless one was passed in."""
        if self._behavior is None:
            self._behavior = detect()
        return self._behavior

    @property
    def online(self) -> Online:
        """Playing over the internet (playit.gg)."""
        if self._online is None:
            self._online = Online(self.behavior, self.rcon)
        return self._online

    @property
    def processes(self) -> ServerProcesses:
        """This install's server processes (at most one server; nothing left once it's stopped)."""
        return ServerProcesses(self.behavior, config.home_dir())

    def state(self) -> GameState:
        return read_state(self.rcon, self.log)

    def _run(self, commands: list[str]) -> list[str]:
        """Run console commands; return any lines that look like errors."""
        if self.log is None or not self.log.exists():
            return self._run_each(commands)
        token = f"WOP_MCP_DONE_{uuid.uuid4().hex[:8]}"
        (config.cfg_dir() / BATCH_FILE).write_text("\n".join(commands + [f"echo {token}"]) + "\n",
                                                   encoding="latin-1")
        start = self.log.size()
        self.rcon.command(f"exec {BATCH_FILE}", timeout=3.0)
        deadline = time.monotonic() + MAP_TIMEOUT
        while time.monotonic() < deadline:
            text = self.log.read_from(start)
            if token in text:
                return _problems("", text[:text.index(token)])
            time.sleep(0.2)
        raise WopError(f"The server didn't finish the commands within {int(MAP_TIMEOUT)} s. Check its window.")

    def _run_each(self, commands: list[str]) -> list[str]:
        """Fallback without a log: one rcon packet per command (slow: about 1 a second)."""
        problems = []
        for cmd in commands:
            timeout = MAP_TIMEOUT if cmd.startswith(("map ", "map_restart")) else 3.0
            problems += _problems(cmd, self.rcon.command(cmd, timeout=timeout))
        return problems

    def _result(self, summary: str, problems: list[str] | None = None, wait: float = 1.5,
                notes: list[str] | None = None) -> dict:
        time.sleep(wait)  # let queued bots join
        result = {"result": summary, "state": self.state().to_dict()}
        if problems:
            result["problems"] = problems
        if notes:
            result["notes"] = notes
        return result

    def _lineup(self, entries, team: str | None, default_skill: int) -> list[LineupBot]:
        lineup = []
        for entry in entries or []:
            if isinstance(entry, str):
                entry = {"name": entry}
            elif not isinstance(entry, dict):
                entry = entry.model_dump(exclude_none=True)
            bot = resolve_bot(entry["name"])
            entry_team = entry.get("team")
            lineup.append(LineupBot(
                bot=bot,
                team=resolve_team(entry_team) if entry_team else team,
                skill=_skill(entry.get("skill", default_skill)),
                custom_name=sanitize(entry["custom_name"], 32) or None if entry.get("custom_name") else None,
            ))
        return lineup

    @staticmethod
    def _balance(lineup: list[LineupBot], red: int = 0, blue: int = 0) -> None:
        """Put bots without a team on whichever team is smaller."""
        for lb in lineup:
            if lb.team in ("red", "blue"):
                red, blue = red + (lb.team == "red"), blue + (lb.team == "blue")
        for lb in lineup:
            if lb.team not in ("red", "blue"):
                lb.team = "red" if red <= blue else "blue"
                red, blue = red + (lb.team == "red"), blue + (lb.team == "blue")

    @staticmethod
    def _name_bots(lineup: list[LineupBot], taken: set[str]) -> None:
        """Give extra copies of the same bot their own name (FatPad, FatPad2, FatPad3...)."""
        taken = {t.lower() for t in taken}
        for lb in lineup:
            if lb.custom_name:
                if lb.custom_name.lower() in taken:
                    raise WopError(f"The name '{lb.custom_name}' is already used on the server.")
                taken.add(lb.custom_name.lower())
        for lb in lineup:
            if lb.custom_name:
                continue
            if lb.bot.name.lower() not in taken:
                taken.add(lb.bot.name.lower())
                continue
            n = 2
            while f"{lb.bot.name}{n}".lower() in taken:
                n += 1
            lb.custom_name = f"{lb.bot.name}{n}"
            taken.add(lb.custom_name.lower())

    @staticmethod
    def _addbot(lb: LineupBot) -> str:
        cmd = f"addbot {lb.bot.name} {lb.skill} {lb.team or 'free'}"
        return cmd + (f' 0 "{lb.custom_name}"' if lb.custom_name else "")

    @staticmethod
    def _check_slots(state: GameState, keep: int, adding: int) -> None:
        if keep + adding > state.maxclients:
            raise WopError(
                f"That's {keep + adding} players but the server has {state.maxclients} slots "
                f"({keep} staying, {adding} bots to add). Use fewer bots."
            )

    def find_player(self, state: GameState, player: str | int) -> Player:
        text = str(player).strip()
        if text.isdigit():
            for p in state.players:
                if p.num == int(text):
                    return p
            raise WopError(f"No player with number {text}. Use get_server_status to see who's on.")
        key = clean(text).lower()
        exact = [p for p in state.players if p.clean_name.lower() == key]
        if len(exact) == 1:
            return exact[0]
        partial = [p for p in state.players if key in p.clean_name.lower()]
        if len(partial) == 1:
            return partial[0]
        names = ", ".join(f"{p.clean_name} (#{p.num})" for p in (exact or partial or state.players))
        if exact or partial:
            raise WopError(f"'{text}' matches more than one player: {names}. Use the number.")
        raise WopError(f"No player called '{text}'. On the server: {names or 'nobody'}.")

    # ------------------------------------------------------------------ catalog

    @staticmethod
    def list_gamemodes() -> list[dict]:
        out = []
        for m in GAMEMODES:
            d = {"id": m.id, "key": m.key, "name": m.name, "team_mode": m.team, "description": m.description,
                 "maps": " + ".join(MAP_GROUP_TITLES[g] for g in m.map_groups),
                 "default_map": m.default_map, "default_pointlimit": m.pointlimit,
                 "default_timelimit_minutes": m.timelimit}
            if m.team:
                d["default_red"], d["default_blue"] = list(m.default_red), list(m.default_blue)
            else:
                d["default_bots"] = list(m.default_bots)
            out.append(d)
        return out

    @staticmethod
    def list_maps(gamemode: str | None = None) -> dict:
        if gamemode:
            mode = resolve_gamemode(gamemode)
            return {"gamemode": mode.name, "maps": mode.maps}
        groups = {}
        for group, maps in MAP_GROUPS.items():
            fits = [m.name for m in GAMEMODES if group in m.map_groups]
            groups[group] = {"title": MAP_GROUP_TITLES[group], "works_in": fits, "maps": maps}
        return groups

    @staticmethod
    def list_bots() -> list[dict]:
        return [{"name": b.name, "looks_like": b.look, "ai_personality": b.personality} for b in BOTS]

    # ------------------------------------------------------------------ gameplay

    def set_game(self, gamemode, map=None, weapons=None, red=None, blue=None, bots=None, skill=3,
                 pointlimit=None, timelimit=None, keep_current_bots=False, lps_lives=None) -> dict:
        state = self.state()
        mode = resolve_gamemode(gamemode)
        map_name = resolve_map(map, mode) if map else mode.default_map
        check_map_fits(map_name, mode)
        instapad = _weapons(weapons) if weapons is not None else state.instapad
        skill = _skill(skill)

        if red or blue or bots:
            lineup = (self._lineup(red, "red", skill) + self._lineup(blue, "blue", skill)
                      + self._lineup(bots, None, skill))
        elif keep_current_bots:
            lineup = [LineupBot(resolve_bot(p.bot_type), p.team if p.team in ("red", "blue") else None,
                                p.skill or skill, p.clean_name if p.clean_name != p.bot_type else None)
                      for p in state.bots if p.bot_type]
        elif mode.team:
            lineup = (self._lineup(mode.default_red, "red", skill)
                      + self._lineup(mode.default_blue, "blue", skill))
        else:
            lineup = self._lineup(mode.default_bots, None, skill)

        if mode.team:
            self._balance(lineup)
        else:
            for lb in lineup:
                lb.team = None
        self._check_slots(state, len(state.humans), len(lineup))
        self._name_bots(lineup, {p.clean_name for p in state.humans})

        commands = ["kick allbots", "set bot_minplayers 0", f"set g_gametype {mode.id}",
                    f"set g_instaPad {int(instapad)}",
                    f"set pointlimit {int(pointlimit if pointlimit is not None else mode.pointlimit)}",
                    f"set timelimit {int(timelimit if timelimit is not None else mode.timelimit)}"]
        if lps_lives is not None:
            commands.append(f"set g_LPS_startlives {int(lps_lives)}")
        commands.append(f"map {map_name}")
        commands += [self._addbot(lb) for lb in lineup]
        problems = self._run(commands)

        notes = []
        if mode.team and state.humans:
            notes.append("Humans pick their own team again: /team red or /team blue (or the Esc menu).")
        return self._result(f"Now playing {mode.name} on {map_name} with "
                            f"{'InstaPad' if instapad else 'regular weapons'} and {len(lineup)} bots.",
                            problems, wait=2.0, notes=notes)

    def change_map(self, map: str) -> dict:
        state = self.state()
        mode = state.mode or resolve_gamemode(state.gametype)
        map_name = resolve_map(map, mode)
        check_map_fits(map_name, mode)
        problems = self._run([f"map {map_name}"])
        return self._result(f"Changed map to {map_name} ({mode.name}); the bots stayed.", problems, wait=2.0)

    def set_weapons(self, weapons: str) -> dict:
        instapad = _weapons(weapons)
        state = self.state()
        problems = self._run([f"set g_instaPad {int(instapad)}", f"map {state.map}"])
        return self._result(f"Weapons set to {'InstaPad' if instapad else 'regular'}; "
                            f"{state.map} was reloaded so it applies.", problems, wait=2.0)

    def set_limits(self, pointlimit=None, timelimit=None) -> dict:
        if pointlimit is None and timelimit is None:
            raise WopError("Give a pointlimit, a timelimit (minutes), or both. 0 means no limit.")
        commands = []
        if pointlimit is not None:
            commands.append(f"pointlimit {max(0, int(pointlimit))}")
        if timelimit is not None:
            commands.append(f"timelimit {max(0, int(timelimit))}")
        return self._result("Limits changed (they apply right away).", self._run(commands), wait=0.2)

    def set_teams(self, red=None, blue=None, skill=3) -> dict:
        state = self.state()
        if not state.team_mode:
            raise WopError(f"{state.mode.name if state.mode else 'This mode'} has no teams. "
                           "Use set_game to switch to a team mode, or add_bots for solo modes.")
        skill = _skill(skill)
        lineup = self._lineup(red, "red", skill) + self._lineup(blue, "blue", skill)
        self._check_slots(state, len(state.humans), len(lineup))
        self._name_bots(lineup, {p.clean_name for p in state.humans})
        problems = self._run(["kick allbots"] + [self._addbot(lb) for lb in lineup])
        reds = sum(lb.team == "red" for lb in lineup)
        return self._result(f"New bot lineup: {reds} on red, {len(lineup) - reds} on blue. Humans kept their team.",
                            problems)

    def add_bots(self, bots, team=None, skill=3) -> dict:
        state = self.state()
        lineup = self._lineup(bots, resolve_team(team) if team else None, _skill(skill))
        if not lineup:
            raise WopError("Name at least one bot to add.")
        if state.team_mode:
            self._balance(lineup, len(state.on_team("red")), len(state.on_team("blue")))
        else:
            for lb in lineup:
                lb.team = None
        self._check_slots(state, len(state.players), len(lineup))
        self._name_bots(lineup, {p.clean_name for p in state.players})
        problems = self._run([self._addbot(lb) for lb in lineup])
        added = ", ".join(lb.custom_name or lb.bot.name for lb in lineup)
        return self._result(f"Added {added}.", problems)

    def remove_bots(self, names=None, all=False) -> dict:
        state = self.state()
        if all:
            return self._result(f"Removed all {len(state.bots)} bots.", self._run(["kick allbots"]), wait=0.5)
        if not names:
            raise WopError("Name the bots to remove, or set all=true.")
        targets, missing = [], []
        for name in names:
            key = clean(str(name)).lower()
            hits = [p for p in state.bots if p.clean_name.lower() == key or str(p.num) == key]
            if not hits:
                try:
                    bot = resolve_bot(str(name))
                    hits = [p for p in state.bots if p.bot_type == bot.name][:1]
                except WopError:
                    pass
            if hits:
                targets += [h for h in hits if h not in targets]
            else:
                missing.append(str(name))
        problems = self._run([f"clientkick {p.num}" for p in targets])
        if missing:
            bots = ", ".join(p.clean_name for p in state.bots) or "none"
            problems.append(f"Not on the server: {', '.join(missing)}. Bots now: {bots}.")
        return self._result(f"Removed {', '.join(p.clean_name for p in targets) or 'nobody'}.", problems, wait=0.5)

    def move_player(self, player, team: str) -> dict:
        state = self.state()
        p = self.find_player(state, player)
        team = resolve_team(team)
        if not state.team_mode and team in ("red", "blue"):
            raise WopError(f"{state.mode.name if state.mode else 'This mode'} has no teams.")
        if p.team == team:
            return {"result": f"{p.clean_name} is already on {team}.", "state": state.to_dict()}
        if not p.bot:
            return self._result(f"Moved {p.clean_name} to {team}.", self._run([f"forceteam {p.num} {team}"]))
        if team not in ("red", "blue"):
            raise WopError("Bots can only be moved to red or blue. Use remove_bots to take a bot out.")
        if not p.bot_type:
            raise WopError(f"Can't tell which bot {p.clean_name} is, so it can't be re-added. "
                           "Remove it and add a new one instead.")
        # forceteam on a bot doesn't survive the next map restart, so re-add it on the new team
        lb = LineupBot(resolve_bot(p.bot_type), team, p.skill or 3,
                       sanitize(p.name, 32) if p.clean_name != p.bot_type else None)
        problems = self._run([f"clientkick {p.num}", self._addbot(lb)])
        return self._result(f"Moved {p.clean_name} to {team}.", problems)

    def restart_match(self) -> dict:
        return self._result("Match restarted.", self._run(["map_restart 0"]), wait=2.0)

    # ------------------------------------------------------------------ player admin

    def kick_player(self, player) -> dict:
        p = self.find_player(self.state(), player)
        return self._result(f"Kicked {p.clean_name}.", self._run([f"clientkick {p.num}"]), wait=0.5)

    def send_message(self, text: str, player=None) -> dict:
        text = sanitize(text, 150)
        if not text:
            raise WopError("The message is empty.")
        # WoP's own ssay/stell: the engine's say/tell send a chat line WoP's game no longer understands
        if player is None:
            self.rcon.command(f"ssay {text}")
            return {"result": f"Said to everyone: {text}"}
        p = self.find_player(self.state(), player)
        self.rcon.command(f"stell {p.num} {text}")
        return {"result": f"Told {p.clean_name}: {text}"}

    def set_join_password(self, password: str) -> dict:
        password = sanitize(password, 32).replace(" ", "")
        self.rcon.command(f'g_password "{password}"')
        if password:
            return {"result": f"Join password set to '{password}'. New players type /password {password} "
                              "before connecting. Players already on stay. Resets when the server restarts."}
        return {"result": "Join password removed; anyone on the network can join."}

    # ------------------------------------------------------------------ joining and naming

    def _cvar(self, name: str) -> str | None:
        """Read a setting: the server answers '"sv_hostname" is:"My server^7" default:...'."""
        match = re.search(r'is:"(.*?)\^7"', self.rcon.command(name))
        return clean(match.group(1)) if match else None

    @staticmethod
    def lan_addresses() -> list[str]:
        """This computer's network addresses, the one other devices should use first."""
        found = []
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("192.0.2.1", 9))  # sends nothing; picks the adapter of the default route
                found.append(s.getsockname()[0])
        except OSError:
            pass
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                found.append(info[4][0])
        except OSError:
            pass
        out = []
        for ip in found:
            if ip not in out and not ip.startswith(("127.", "169.254.", "0.")):
                out.append(ip)
        return out

    def get_join_info(self) -> dict:
        running = self.rcon.is_running(retry=True)
        name = config.server_name()
        password = config.join_password()
        if running:
            name = self._cvar("sv_hostname") or name
            live_password = self._cvar("g_password")
            password = live_password if live_password is not None else password
        port = self.rcon.port
        addresses = self.lan_addresses()
        suffix = "" if port == 27960 else f":{port}"
        connect = [f"/connect {ip}{suffix}" for ip in addresses]
        steps = [
            "Every player needs World of PADMAN 1.7.0 (free): https://worldofpadman.net/en/download/",
            "Be on the same Wi-Fi / network as this computer.",
            "Start World of PADMAN → Multiplayer → set the source to LAN → pick "
            f"'{name}' → Join. (On this computer itself: /connect localhost{suffix})",
            f"If it doesn't show up: press ~ to open the console and type {connect[0] if connect else '/connect <IP>'}",
        ]
        if password:
            steps.insert(2, f"Before joining, type /password {password} in the console (~).")
        online = self.online.join_details()
        if online:
            steps.append(f"Players somewhere else (another home, over the internet): Multiplayer → SPECIFY → "
                         f"address {online['address']}, port {online['port']}, or type {online['connect_command']} "
                         "in the console (~). This works while the server is on.")
        return {"server_name": name, "running": running, "addresses": addresses, "port": port,
                "join_password": password or None, "connect_commands": connect, "how_to_join": steps,
                "online": online}

    def set_server_name(self, name: str) -> dict:
        name = sanitize(name, 40)
        if not name:
            raise WopError("The name is empty.")
        set_cfg_value(config.server_cfg(), "sv_hostname", name)
        live = False
        if self.rcon.is_running(retry=True):
            self.rcon.command(f'sv_hostname "{name}"')
            live = True
        return {"result": f"The server is now called '{name}'" + (" (shown to players right away)." if live
                else " (applies when the server starts)."), "saved_in": str(config.server_cfg())}

    # ------------------------------------------------------------------ server control

    def start_server(self, wait: float = 30.0) -> dict:
        """With the WoP Server app the server runs without a window (the app shows its log); otherwise it
        opens in its own window, like double-clicking run-server. Never a second server: one that hangs is
        ended first."""
        with self.processes.starting():
            return self._start_server(wait)

    def _start_server(self, wait: float) -> dict:
        if self.processes.make_room(self.rcon):
            self.online.start_keeper()
            return {"result": "The server is already running.", "state": self.state().to_dict()}
        if self.use_log:
            self.log = ServerLog(config.cfg_dir() / "qconsole.log")  # the new server starts a new log
        inst = config.install()
        game = Path(inst.get("game_dir") or "")
        if inst.get("hidden_server") and (game / self.behavior.server_bin).exists():
            launcher.launch_server(self.behavior, game, config.home_dir(), self.rcon.port)
            started = "Server started in the background; the WoP Server app shows what it's doing."
            where = "Open the WoP Server app and look at its Logs tab."
        else:
            script = config.start_script(self.behavior.run_script_name)
            if not script.exists():
                raise WopError(f"Can't find {script}. Run the WoP Server Kit setup again.")
            self.behavior.open_in_window(script)
            started, where = "Server started in its own window.", "Check its window for errors."
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            time.sleep(1.0)
            if self.rcon.is_running():
                if self.online.start_keeper():
                    started += " Friends anywhere can join over the internet too."
                return self._result(started, wait=3.0)
        raise WopError(f"The server was started, but it didn't answer within {int(wait)} s. {where}")

    def reset_to_defaults(self) -> dict:
        """Game settings as after installing (the server's name stays). A running server restarts with them, so
        nothing of the old settings stays behind on it."""
        running = bool(self.processes.servers()) or self.rcon.is_running()
        if running:
            self.stop_server()
        reset_to_defaults()
        if not running:
            return {"result": "Back to the original game settings. The server starts with them next time."}
        result = self.start_server()
        return {**result, "result": "Back to the original game settings. The server restarted with them."}

    def set_spawn_protection(self, on: bool) -> dict:
        """InstaPad's few seconds of not getting hurt after respawning. Applies from the next respawn."""
        state = self.state()
        if state.spawn_protect is None:
            raise WopError("The server that's running can't change spawn protection yet (plain World of PADMAN "
                           "1.7.0 always uses 6 seconds). Restart the server once; then it can.")
        seconds = SPAWN_PROTECT_SECONDS if on else 0
        self.rcon.command(f"set g_spawnProtect {seconds}")
        note = "" if state.instapad else " It only matters with InstaPad weapons."
        return self._result(f"Spawn protection {'on' if on else 'off'} ({seconds} seconds) from the next "
                            f"respawn.{note}", wait=0.2)

    def stop_server(self) -> dict:
        """Asked to quit, and ended if it doesn't; the internet-play helpers stop with it."""
        if not self.processes.stop(self.rcon):
            return {"result": "The server isn't running."}
        return {"result": "Server stopped."}

    # say/tell as typed in Quake 3 -> WoP's ssay/stell (see send_message)
    _WOP_CHAT = re.compile(r"^(say|tell)(?=\s|$)", re.IGNORECASE)

    _BLOCKED = re.compile(r"^\s*(quit|killserver|rconpassword|(seta?|sets|setu)\s+rconpassword|"
                          r"exec\s+\"?server-friends)", re.IGNORECASE)

    def run_console_command(self, command: str) -> dict:
        command = command.replace("\r", " ").replace("\n", " ").strip()
        if not command:
            raise WopError("The command is empty.")
        if self._BLOCKED.match(command):
            raise WopError("That command isn't allowed here. Use stop_server to stop the server; "
                           "the rcon password can only be changed in server-friends.cfg.")
        command = self._WOP_CHAT.sub(lambda m: "s" + m.group(1).lower(), command)
        timeout = MAP_TIMEOUT if command.lower().startswith(("map ", "devmap", "map_restart", "vstr")) else 5.0
        out = self.rcon.command(command, timeout=timeout)
        return {"command": command, "output": clean(out).strip() or "(no output)"}
