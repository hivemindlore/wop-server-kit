"""Changes to the server's config files.

save_as_startup writes the current game into teams.cfg and server-friends.cfg: only the text
between the '// >>> startup game' and '// <<< startup game' markers in server-friends.cfg is
replaced, and both files get a .bak copy first. set_cfg_value changes one `set` line. reset_to_defaults
puts the files of a fresh install back.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import config, maploop
from .catalog import WopError, resolve_bot
from .server_state import GameState

TEMPLATES = Path(__file__).resolve().parents[2] / "server"   # kit/server: the files of a fresh install

START_MARK = "// >>> startup game"
END_MARK = "// <<< startup game"

TEAMS_HEADER = """//
//    WoP server - team lineup
//
//    Loaded automatically when the server starts. Reload it any time while the
//    server runs: type  exec teams.cfg  in the server window,
//    or  /rcon exec teams.cfg  in the game console.
//    Last written by save_as_startup in the WoP MCP server.
//
//    To remove a bot from the lineup, put // in front of its line.
//    Format:  addbot <botname> <skill 1-5> <red|blue|free> [delay ms] ["custom name"]
//    All bot names are listed in gamemodes.md (bottom), or ask Claude.
//    Adding the same bot twice? Give the second one its own name, like FatPad2.
//
//    Humans pick their own team with /team red or /team blue (or the Esc menu).
//

// Remove all bots first so reloading this file never creates duplicates
kick allbots
"""


def server_cfg_text(server_name: str, rcon_password: str) -> str:
    """server-friends.cfg as a fresh install has it."""
    template = (TEMPLATES / "server-friends.cfg").read_text(encoding="utf-8")
    return template.replace("__SERVER_NAME__", server_name).replace("__RCON_PASSWORD__", rcon_password)


def reset_to_defaults(cfg_dir: Path | None = None) -> None:
    """server-friends.cfg, teams.cfg and mode.cfg as a fresh install has them, keeping the server's name and
    its admin password (so the kit can still reach a running server). The old files are kept as .bak."""
    cfg_dir = cfg_dir or config.cfg_dir()
    server_cfg = cfg_dir / "server-friends.cfg"
    name = config.cfg_value("sv_hostname", server_cfg) or "WoP server"
    password = config.cfg_value("rconpassword", server_cfg)
    if not password:
        raise WopError(f"Can't find the admin password in {server_cfg}, so the settings can't be reset.")
    for file in ("server-friends.cfg", "teams.cfg", "mode.cfg"):
        if (cfg_dir / file).exists():
            shutil.copyfile(cfg_dir / file, cfg_dir / (file + ".bak"))
    server_cfg.write_text(server_cfg_text(name, password), encoding="utf-8")
    for file in ("teams.cfg", "mode.cfg"):
        shutil.copyfile(TEMPLATES / file, cfg_dir / file)


def set_cfg_value(path: Path, name: str, value: str) -> None:
    """Replace the `set <name> ...` line in a cfg file (or add one before the startup block)."""
    text = path.read_text(encoding="utf-8")
    new_line = f'set {name} "{value}"'
    pattern = re.compile(rf'^[ \t]*seta?[ \t]+{re.escape(name)}[ \t].*$', re.IGNORECASE | re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda _: new_line, text)
    elif START_MARK in text:
        i = text.index(START_MARK)
        text = text[:i] + new_line + "\n\n" + text[i:]
    else:
        text = text.rstrip("\n") + "\n" + new_line + "\n"
    path.write_text(text, encoding="utf-8")


def _addbot_line(bot_name: str, skill: int, team: str, custom: str | None) -> str:
    line = f"addbot {bot_name:<11} {skill} {team}"
    return line + (f' 0 "{custom}"' if custom else "")


def teams_cfg_text(state: GameState) -> str:
    groups: dict[str, list[str]] = {}
    for p in state.bots:
        if not p.bot_type:
            continue
        bot = resolve_bot(p.bot_type)
        team = p.team if state.team_mode and p.team in ("red", "blue") else "free"
        custom = re.sub(r'["\\;]', "", p.name) if p.clean_name != bot.name else None
        groups.setdefault(team, []).append(_addbot_line(bot.name, p.skill or 3, team, custom))
    titles = {"red": "RED PADS (red)", "blue": "BLUE NOSES (blue)", "free": "BOTS (no team in this mode)"}
    text = TEAMS_HEADER
    for team in ("red", "blue", "free"):
        if team in groups:
            text += f"\n//\n// {titles[team]}: {len(groups[team])} bots\n//\n" + "\n".join(groups[team]) + "\n"
    return text


def startup_block(state: GameState, maps: list[str] | None = None) -> str:
    """maps: the running map loop; the server then starts on its first map and plays them in turn."""
    mode = state.mode
    loop = maps if maps and len(maps) > 1 else [state.map]
    lines = [
        START_MARK,
        f"// {mode.name if mode else 'Game type ' + str(state.gametype)} on {maploop.describe(loop)}, "
        f"{'InstaPad' if state.instapad else 'regular weapons'} (written by save_as_startup)",
        f'set g_gametype     "{state.gametype}"',
        'set bot_minplayers "0"',
        f'set g_instaPad     "{int(state.instapad)}"',
        f'set pointlimit     "{state.pointlimit}"',
        f'set timelimit      "{state.timelimit}"',
    ]
    if state.gametype == 4 and state.lps_lives:
        lines.append(f'set g_LPS_startlives "{state.lps_lives}"')
    lines += maploop.define(loop) + [f"map {loop[0]}"] + maploop.start(loop) + ["exec teams.cfg", END_MARK]
    return "\n".join(lines)


def save_as_startup(state: GameState, cfg_dir: Path | None = None, maps: list[str] | None = None) -> dict:
    cfg_dir = cfg_dir or config.cfg_dir()
    server_cfg, teams_cfg = cfg_dir / "server-friends.cfg", cfg_dir / "teams.cfg"
    text = server_cfg.read_text(encoding="utf-8")
    start, end = text.find(START_MARK), text.find(END_MARK)
    if start < 0 or end < start:
        raise WopError(f"Can't find the '{START_MARK}' / '{END_MARK}' lines in {server_cfg}, "
                       "so the startup game can't be saved automatically.")
    block = startup_block(state, maps)
    new_text = text[:start] + block + text[end + len(END_MARK):]

    for path in (server_cfg, teams_cfg):
        if path.exists():
            shutil.copyfile(path, path.with_name(path.name + ".bak"))
    server_cfg.write_text(new_text, encoding="utf-8")
    if state.spawn_protect is not None:   # InstaPad's protection after respawning (kit's game code only)
        set_cfg_value(server_cfg, "g_spawnProtect", str(state.spawn_protect))
    teams_cfg.write_text(teams_cfg_text(state), encoding="utf-8")
    return {
        "result": "Saved. The server will start with this setup from now on.",
        "files": [str(server_cfg), str(teams_cfg)],
        "backups": [str(server_cfg) + ".bak", str(teams_cfg) + ".bak"],
        "startup_block": block,
        "note": "A join password and changes made with run_console_command aren't saved.",
    }
