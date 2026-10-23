# WoP MCP server

Lets Claude Desktop run the World of PADMAN server that the WoP Server Kit installed. Just ask:

- "What's running on the server?"
- "Capture The Lolly on padbase with InstaPad, 4 vs 4 bots, put FatPad and FATTY on blue."
- "Switch to Big Balloon on the garden map." · "Make the bots harder." · "Move FATTY to red."
- "Add three bots to blue." · "Kick PadGirl." · "Set a join password." · "Keep this as the startup game."

Claude knows all game modes, maps and bots, checks that a map fits the mode, and reads back the
server state after every change. You don't need to know any names or commands.

## Tools

| Tool | What it does |
|------|--------------|
| `get_join_info`, `set_server_name` | How players join (address, steps, download link) / rename the server |
| `get_server_status` | Map, mode, weapons, limits, free slots, every player with team / bot type / skill |
| `list_gamemodes`, `list_maps`, `list_bots` | The game catalog (11 modes, 46 maps, 29 bots) |
| `set_game` | Full switch: mode + map + weapons + limits + bots (defaults from gamemodes.md) |
| `change_map`, `set_weapons`, `set_limits`, `restart_match` | Smaller changes |
| `set_spawn_protection` | InstaPad: a few seconds of not getting hurt after respawning, on or off (needs the kit's game code, `kit/server/game`) |
| `set_teams`, `add_bots`, `remove_bots`, `move_player` | Bot lineup and teams |
| `kick_player`, `send_message`, `set_join_password` | Player admin |
| `start_server`, `stop_server` | Starts the server (in the background when the WoP Server app is used, otherwise in its own window) / stops it |
| `run_console_command` | Any other console command (quit, killserver and the rcon password are blocked) |
| `save_as_startup` | Makes the current setup the startup game (rewrites `teams.cfg` and the marked block in `server-friends.cfg`, keeps `.bak` copies) |

## How it works

- Talks to the server over **rcon** on `127.0.0.1` (UDP). Port and password are read from
  the install's `run-server` script and `home/wop/server-friends.cfg` (random password per install), so nothing needs to be set up here.
- The server only answers about one rcon packet a second after a short burst. So a change is
  written to `home\wop\mcp-batch.cfg` and run with a single `exec`, and its result is read from
  `home\wop\qconsole.log`. The kit always runs the server with `logfile 2`; without the log everything still works, just slowly.
- `start_server`: with the WoP Server app (`hidden_server` in `install.json`) the server starts without a window
  (`wop/launcher.py`), and the app shows its log. Otherwise it opens `run-server.cmd` (Mac: `.command`, Linux: `.sh`)
  in its own window, like double-clicking it. Either way the server keeps running when Claude closes.
- Everything that differs per OS is in `wop/platforms/` (one behavior class per OS; `detect()` picks it).
- Bots moved to another team are removed and re-added there, because the game puts a bot moved with
  `forceteam` back on its old team at the next map restart.

## Setup

Nothing to do by hand: `kit/setup/wopkit.py` registers this server in Claude Desktop as **wop-server**
(command: the kit's own `uv`, `run --script <kit>/mcp/server.py`, with `WOP_HOME`, `WOP_START_SCRIPT` and the
`UV_*` folders in `env`), and pre-downloads its Python and `mcp==2.3.0` with `server.py --selftest`.

## Tests

```
cd kit/mcp
uv run --no-project --with pytest --with "mcp==2.3.0" python -m pytest tests
```

End-to-end against a kit test install (never touches a real server; see the repo README, "For the maintainer"):
```
uv run --no-project --with "mcp==2.3.0" python tests/integration.py <test install folder>
```
It starts and stops the test install's server itself.
