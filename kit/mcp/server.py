# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0"]
# ///
"""WoP MCP server: lets Claude run a World of PADMAN server installed by the WoP Server Kit.

Run:  uv run --script server.py              (stdio; started by Claude Desktop)
      uv run --script server.py --selftest   (setup uses this to download Python + mcp ahead of time)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from wop import config as wop_config  # noqa: E402
from wop import config_files  # noqa: E402
from wop.actions import Game  # noqa: E402
from wop.catalog import WopError  # noqa: E402
from wop.platforms import detect  # noqa: E402

INSTRUCTIONS = """\
You control a World of PADMAN (WoP 1.7.0) game server on this computer, for players on the same
home network (and, when it's switched on, friends anywhere over the internet). WoP is a free cartoon
arena shooter (Quake 3 engine): players are tiny figures fighting on giant everyday sets (gardens,
kitchens, bathrooms). The person you talk to is usually
not technical: explain things simply, never ask them to edit files or type console commands
when a tool can do it, and tell them what changed in plain words.

How to work:
- Call get_server_status first to see what is running (map, mode, weapons, who is on which team).
  If the server isn't running, offer to start it with start_server.
- "How do my friends join?" -> get_join_info, then explain the steps it returns.
- Friends in another home (not on this network) can join over the internet once set_online_play is on.
  The first time, the host approves it once on playit.gg (free) in the browser; then call it again.
- Use the catalog tools (list_gamemodes, list_maps, list_bots) instead of guessing names. Loose names are
  fine in every tool: "pad garden", "padgarden night", "ctl", "team ffa", "fatty".
- Every action tool returns the new server state; check it and tell the user what changed.
- If a tool returns an error, it explains what to fix (wrong map for a mode, unknown bot, too many players).

Game rules worth knowing:
- Teams are Red Pads (red) and Blue Noses (blue). Team modes: Team Free For All, Freeze Tag,
  Capture The Lolly, One Lolly Capture, Spray Your Color Team, Big Balloon. The rest are solo (everyone for themselves).
- Capture The Lolly and One Lolly Capture only work on ...CTL maps, Big Balloon only on ...BB maps,
  all other modes on the regular maps and the ...LPS maps.
- Weapons are either "regular" (all weapons) or "instapad" (one weapon, one hit kills).
  In InstaPad, players can't be hurt for a few seconds after respawning; set_spawn_protection turns that on or off.
- Bot skill is 1 (easy) to 5 (hard); 3 is the default. The same bot can be added more than once
  (copies are named FatPad2, FatPad3, ... automatically).
- The server has 16 slots for humans and bots together. Humans choose their own team in the game
  (/team red, /team blue or the Esc menu); move_player can move them.
- A match that ends replays the same map and mode, unless set_game got several maps: then they play one
  after another and start over. Restarting the server goes back to the saved startup game; save_as_startup
  makes the current setup (including such a map loop) the new startup game.
- For a full switch (mode + map + weapons + bots at once) use set_game. For small changes use
  change_map, set_weapons, set_limits, set_teams, add_bots, remove_bots or move_player.
"""

mcp = MCPServer("wop", instructions=INSTRUCTIONS)
game = Game(behavior=detect())
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


class BotSpec(BaseModel):
    name: str = Field(description="Bot name from list_bots, e.g. 'FatPad' or 'padgirl'")
    skill: int | None = Field(None, ge=1, le=5, description="1 (easy) to 5 (hard); default from the tool's skill")
    team: Literal["red", "blue"] | None = Field(None, description="Only for add_bots / set_game 'bots'")
    custom_name: str | None = Field(None, description="Optional in-game name, e.g. 'FatPad2'")


Bots = list[BotSpec | str]


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except WopError as e:
        raise ToolError(str(e)) from None


# ---------------------------------------------------------------- catalog

@mcp.tool(annotations=READ_ONLY)
def list_gamemodes() -> list[dict]:
    """All 11 game modes: id, name, team or solo, which maps fit, default limits and default bot lineup."""
    return game.list_gamemodes()


@mcp.tool(annotations=READ_ONLY)
def list_maps(gamemode: Annotated[str | None, Field(description="Only maps that work in this mode")] = None) -> dict:
    """All 46 maps grouped (regular, LPS, CTL, Big Balloon) with the modes each group works in,
    or only the maps that work in one game mode."""
    return _call(game.list_maps, gamemode)


@mcp.tool(annotations=READ_ONLY)
def list_bots() -> list[dict]:
    """All 29 bots with their look and AI personality (bots with the same personality play alike)."""
    return game.list_bots()


@mcp.tool(annotations=READ_ONLY)
def get_server_status() -> dict:
    """What's running now: map, game mode, weapons, limits, free slots, and every player
    (number, name, team, bot or human, bot type and skill, score, ping)."""
    try:
        return game.state().to_dict()
    except WopError as e:
        return {"running": False, "message": str(e)}


# ---------------------------------------------------------------- gameplay

@mcp.tool()
def set_game(
    gamemode: Annotated[str, Field(description="Game mode name, key or id, e.g. 'Capture The Lolly', 'ctl', 8")],
    map: Annotated[str | None, Field(description="Map; omit for the mode's default map")] = None,
    weapons: Annotated[Literal["regular", "instapad"] | None, Field(description="Omit to keep the current setting")] = None,
    red: Annotated[Bots | None, Field(description="Bots for the Red Pads (team modes)")] = None,
    blue: Annotated[Bots | None, Field(description="Bots for the Blue Noses (team modes)")] = None,
    bots: Annotated[Bots | None, Field(description="Bots without a team: solo modes, or auto-balanced in team modes")] = None,
    skill: Annotated[int, Field(ge=1, le=5, description="Skill for bots that don't set their own")] = 3,
    pointlimit: Annotated[int | None, Field(ge=0, description="Omit for the mode's default, 0 = none")] = None,
    timelimit: Annotated[int | None, Field(ge=0, description="Minutes; omit for the mode's default, 0 = none")] = None,
    keep_current_bots: Annotated[bool, Field(description="Re-add the bots that are on now instead of the default lineup")] = False,
    lps_lives: Annotated[int | None, Field(ge=1, description="Last Pad Standing: lives per player")] = None,
    maps: Annotated[list[str] | None, Field(description="Several maps that play one after another, then start "
                                                        "over (instead of map)")] = None,
) -> dict:
    """Switch everything at once: game mode, map, weapons, limits and bots (replaces all bots).
    If no bots are given and keep_current_bots is false, the mode's default lineup from gamemodes.md is used."""
    return _call(game.set_game, gamemode, map, weapons, red, blue, bots, skill, pointlimit, timelimit,
                 keep_current_bots, lps_lives, maps=maps)


@mcp.tool()
def change_map(map: Annotated[str, Field(description="Map name, e.g. 'wop_padkitchen' or 'pad kitchen'")]) -> dict:
    """Load another map, keeping the game mode, weapons and bots. Refuses maps that don't fit the mode."""
    return _call(game.change_map, map)


@mcp.tool()
def set_weapons(weapons: Literal["regular", "instapad"]) -> dict:
    """Regular weapons or InstaPad (one weapon, one hit kills). Reloads the current map so it applies."""
    return _call(game.set_weapons, weapons)


@mcp.tool()
def set_spawn_protection(on: Annotated[bool, Field(description="true: 3 seconds of protection, false: none")]) -> dict:
    """InstaPad only: whether players can't be hurt for a few seconds after respawning. Applies from the next
    respawn and lasts until the server restarts (save_as_startup doesn't keep it; the WoP Server app can)."""
    return _call(game.set_spawn_protection, on)


@mcp.tool()
def set_limits(
    pointlimit: Annotated[int | None, Field(ge=0, description="0 = no point limit")] = None,
    timelimit: Annotated[int | None, Field(ge=0, description="Minutes, 0 = no time limit")] = None,
) -> dict:
    """Change when a match ends. Applies right away."""
    return _call(game.set_limits, pointlimit, timelimit)


@mcp.tool()
def set_teams(
    red: Annotated[Bots | None, Field(description="Bots for the Red Pads")] = None,
    blue: Annotated[Bots | None, Field(description="Bots for the Blue Noses")] = None,
    skill: Annotated[int, Field(ge=1, le=5)] = 3,
) -> dict:
    """Replace all bots with this team lineup (team modes only). Humans stay on their team."""
    return _call(game.set_teams, red, blue, skill)


@mcp.tool()
def add_bots(
    bots: Annotated[Bots, Field(description="Bots to add, e.g. ['FatPad', {'name': 'PadGirl', 'skill': 5}]")],
    team: Annotated[Literal["red", "blue"] | None, Field(description="Team for bots that don't set one; omit to balance")] = None,
    skill: Annotated[int, Field(ge=1, le=5)] = 3,
) -> dict:
    """Add bots without touching the others. In team modes, bots without a team go to the smaller team."""
    return _call(game.add_bots, bots, team, skill)


@mcp.tool()
def remove_bots(
    names: Annotated[list[str] | None, Field(description="In-game names (e.g. 'FatPad2') or numbers from get_server_status")] = None,
    all: Annotated[bool, Field(description="Remove every bot")] = False,
) -> dict:
    """Remove some bots, or all of them."""
    return _call(game.remove_bots, names, all)


@mcp.tool()
def move_player(
    player: Annotated[str, Field(description="Name or number from get_server_status (human or bot)")],
    team: Literal["red", "blue", "spectator", "free"],
) -> dict:
    """Move a human or a bot to another team. Bots are re-added on the new team so the move sticks."""
    return _call(game.move_player, player, team)


@mcp.tool()
def restart_match() -> dict:
    """Restart the current match (scores back to 0, same map, mode and bots)."""
    return _call(game.restart_match)


# ---------------------------------------------------------------- joining and naming

@mcp.tool(annotations=READ_ONLY)
def get_join_info() -> dict:
    """How players join: server name, this computer's network address(es), port, join password,
    the internet address when internet play is on (online), and step-by-step instructions
    (including where to download World of PADMAN)."""
    return _call(game.get_join_info)


@mcp.tool()
def set_online_play(on: Annotated[bool, Field(description="true: friends anywhere can join too, false: only this network")]) -> dict:
    """Let friends on other networks join over the internet (through playit.gg, free), or only players on this
    network. The setting is kept: the internet address works whenever the server runs. The first time, this
    opens a playit.gg page in the browser where the host approves it once; when phase is 'approving', ask the
    host to click approve there and then call this again. The result has the address and port to give friends."""
    def switch():
        result = game.online.enable() if on else game.online.disable()
        result.setdefault("result", result["message"])
        return result
    return _call(switch)


@mcp.tool()
def set_server_name(name: Annotated[str, Field(description="New name shown in the server list")]) -> dict:
    """Rename the server. Applies right away and is kept after a restart."""
    return _call(game.set_server_name, name)


# ---------------------------------------------------------------- player admin

@mcp.tool()
def kick_player(player: Annotated[str, Field(description="Name or number from get_server_status")]) -> dict:
    """Kick a human or bot from the server."""
    return _call(game.kick_player, player)


@mcp.tool()
def send_message(
    text: str,
    player: Annotated[str | None, Field(description="Name or number for a private message; omit for everyone")] = None,
) -> dict:
    """Show a message in the game as the server."""
    return _call(game.send_message, text, player)


@mcp.tool()
def set_join_password(password: Annotated[str, Field(description="New password, or '' to remove it")]) -> dict:
    """Require a password to join (players already on stay). Lasts until the server restarts."""
    return _call(game.set_join_password, password)


# ---------------------------------------------------------------- server control

@mcp.tool()
def start_server() -> dict:
    """Start the server (it opens in its own window) and wait until it answers."""
    return _call(game.start_server)


@mcp.tool()
def stop_server() -> dict:
    """Stop the server. Everyone is disconnected. Only do this when the user asks for it."""
    return _call(game.stop_server)


@mcp.tool()
def run_console_command(command: Annotated[str, Field(description="One server console command, e.g. 'g_gravity 400'")]) -> dict:
    """Escape hatch: run any server console command and get its output. Prefer the dedicated tools.
    quit, killserver and changing the rcon password are blocked."""
    return _call(game.run_console_command, command)


@mcp.tool()
def save_as_startup() -> dict:
    """Make the current mode, map, weapons, limits and bot lineup the game the server starts with
    (writes teams.cfg and the startup block of server-friends.cfg, keeping .bak copies)."""
    def save():
        return config_files.save_as_startup(game.state(), maps=game.map_rotation())
    return _call(save)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print(f"ok: {len(game.list_bots())} bots, {len(game.list_gamemodes())} game modes, "
              f"config {wop_config.server_cfg()}")
    else:
        mcp.run()
