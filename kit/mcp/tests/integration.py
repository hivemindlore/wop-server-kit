"""End-to-end test: an MCP client drives a kit-installed test server through every tool.

    uv run --no-project --with "mcp==2.3.0" python tests/integration.py <kit root>

<kit root> is a test install made by start-wop-server.bat with WOP_KIT_ROOT and WOP_PORT set
(see README "Testing"): it has home/, run-server.cmd (or .command) and the game. The port comes
from that install, so a running real server is never touched.
"""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[1]
failures = []


def check(label, ok, detail=""):
    print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


async def main(root: str):
    root_dir = Path(root)
    script = root_dir / ("run-server.command" if sys.platform == "darwin" else "run-server.cmd")
    env = dict(os.environ, WOP_HOME=str(root_dir / "home"), WOP_START_SCRIPT=str(script))
    env.pop("WOP_PORT", None)  # read from the install's start script, like Claude Desktop does
    params = StdioServerParameters(command=shutil.which("uv"), args=["run", "--script", str(HERE / "server.py")],
                                   env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        await s.initialize()

        async def call(_tool, **args):
            res = await s.call_tool(_tool, args)
            error = getattr(res, "isError", None) or getattr(res, "is_error", False)
            data = getattr(res, "structuredContent", None) or getattr(res, "structured_content", None)
            text = " ".join(getattr(c, "text", "") for c in res.content)
            if data is None:
                try:
                    data = json.loads(text)
                except ValueError:
                    data = {}
            if isinstance(data, dict) and set(data) == {"result"} and not isinstance(data["result"], str):
                data = data["result"]  # list results are wrapped
            return error, data, text

        def bots(state, team=None):
            return sorted(p["name"] for p in state["players"] if p["bot"] and (team is None or p["team"] == team))

        tools = {t.name for t in (await s.list_tools()).tools}
        check("22 tools listed", len(tools) == 22, sorted(tools))

        err, st, _ = await call("get_server_status")
        check("status while offline says not running", not err and st.get("running") is False, st)

        err, r, text = await call("start_server")
        st = r.get("state", {})
        check("start_server -> TFFA padgarden 6v3", not err and st.get("map") == "wop_padgarden"
              and len(st.get("red", [])) == 6 and len(st.get("blue", [])) == 3, text[:300])
        check("startup blue team", bots(st, "blue") == ["FATTY", "FatPad", "FatPad2"], bots(st, "blue"))

        err, modes, _ = await call("list_gamemodes")
        check("list_gamemodes has 11", not err and len(modes) == 11, modes)
        err, maps, _ = await call("list_maps", gamemode="ctl")
        check("list_maps ctl has 10", not err and len(maps["maps"]) == 10, maps)
        err, allbots, _ = await call("list_bots")
        check("list_bots has 29", not err and len(allbots) == 29)

        err, info, text = await call("get_join_info")
        check("get_join_info: running, address, steps", not err and info["running"] and info["addresses"]
              and info["connect_commands"][0].endswith(f":{info['port']}") == (info["port"] != 27960)
              and any("worldofpadman.net" in s for s in info["how_to_join"]), text[:400])
        err, r, text = await call("set_server_name", name="Kit Test Server")
        err2, info, _ = await call("get_join_info")
        check("set_server_name live + saved", not err and not err2 and info["server_name"] == "Kit Test Server"
              and 'set sv_hostname "Kit Test Server"' in (root_dir / "home" / "wop" / "server-friends.cfg")
              .read_text(encoding="utf-8"), text[:300])

        err, r, text = await call("set_game", gamemode="capture the lolly", map="padbase", weapons="instapad",
                                  red=["padman", {"name": "padgirl", "skill": 5}], blue=["fatpad", "fatpad"])
        st = r.get("state", {})
        check("set_game CTL padbase instapad 2v2", not err and st["map"] == "wop_padbaseCTL"
              and st["gamemode"]["id"] == 8 and st["weapons"] == "instapad"
              and bots(st, "red") == ["PADMAN", "PadGirl"] and bots(st, "blue") == ["FatPad", "FatPad2"], text[:400])
        check("PadGirl skill 5", any(p["name"] == "PadGirl" and p["skill"] == 5 for p in st["players"]), st)
        check("no problems reported", "problems" not in r, r.get("problems"))

        err, r, text = await call("change_map", map="wop_padgarden")
        check("change_map to a regular map in CTL refused", err and "CTL" in text, text)

        err, r, text = await call("set_game", gamemode="big balloon", map="padgarden")
        st = r.get("state", {})
        check("set_game Big Balloon padgarden -> padgardenBB, default 3v3", not err and st["map"] == "wop_padgardenBB"
              and len(st["red"]) == 3 and len(st["blue"]) == 3 and st["weapons"] == "instapad", text[:300])

        err, r, text = await call("set_game", gamemode="ffa", map="pad ship", weapons="regular",
                                  bots=["padman", "padman", "fatty"])
        st = r.get("state", {})
        check("set_game FFA, duplicate bot named PADMAN2, no teams", not err and st["gamemode"]["id"] == 0
              and bots(st) == ["FATTY", "PADMAN", "PADMAN2"] and all(p["team"] == "free" for p in st["players"]),
              text[:400])

        err, r, text = await call("set_game", gamemode="team ffa", map="pad garden")
        st = r.get("state", {})
        check("set_game TFFA default lineup", not err and len(st["red"]) == 6 and len(st["blue"]) == 3
              and st["weapons"] == "regular", text[:300])

        err, r, text = await call("change_map", map="wop_fridgeCTL")
        check("change_map CTL map in TFFA refused", err and "Capture The Lolly" in text, text)
        err, r, text = await call("change_map", map="pad kitchen")
        st = r.get("state", {})
        check("change_map pad kitchen keeps bots", not err and st["map"] == "wop_padkitchen"
              and len(st["red"]) == 6 and len(st["blue"]) == 3, text[:300])

        err, r, _ = await call("set_weapons", weapons="instapad")
        check("set_weapons instapad", not err and r["state"]["weapons"] == "instapad", r)
        err, r, _ = await call("set_weapons", weapons="regular")
        check("set_weapons regular, bots stay", not err and r["state"]["weapons"] == "regular"
              and len(r["state"]["red"]) == 6, r)

        err, r, text = await call("set_teams", red=["padking", "padgirl"], blue=["fatpad", "fatty"], skill=4)
        st = r.get("state", {})
        check("set_teams 2v2", not err and bots(st, "red") == ["PadGirl", "PadKing"]
              and bots(st, "blue") == ["FATTY", "FatPad"] and all(p["skill"] == 4 for p in st["players"] if p["bot"]),
              text[:300])

        err, r, text = await call("add_bots", bots=["monsterpad", {"name": "padlilly", "skill": 5, "team": "blue"}])
        st = r.get("state", {})
        check("add_bots", not err and "MonsterPad" in bots(st) and "PadLilly" in bots(st, "blue"), text[:300])

        err, r, text = await call("remove_bots", names=["monsterpad"])
        check("remove_bots", not err and "MonsterPad" not in bots(r["state"]), text[:300])

        err, r, text = await call("move_player", player="FATTY", team="red")
        check("move_player FATTY -> red", not err and "FATTY" in bots(r["state"], "red"), text[:300])
        err, r, text = await call("restart_match")
        check("FATTY still red after a match restart", not err and "FATTY" in bots(r["state"], "red"), text[:300])

        err, r, _ = await call("set_limits", pointlimit=30, timelimit=12)
        check("set_limits", not err and r["state"]["pointlimit"] == 30 and r["state"]["timelimit_minutes"] == 12, r)

        err, r, _ = await call("send_message", text="Hello from Claude")
        check("send_message", not err, r)
        err, r, _ = await call("send_message", text="psst", player="PadKing")
        check("send_message private", not err, r)

        err, r, _ = await call("set_join_password", password="abc")
        err2, out, _ = await call("run_console_command", command="g_password")
        check("set_join_password", not err and not err2 and '"abc' in out["output"], out)
        await call("set_join_password", password="")

        err, r, text = await call("run_console_command", command="quit")
        check("run_console_command blocks quit", err, text)
        err, r, _ = await call("run_console_command", command="sv_hostname")
        check("run_console_command output", not err and "Kit Test Server" in r["output"], r)

        err, r, text = await call("kick_player", player="PadGirl")
        check("kick_player", not err and "PadGirl" not in bots(r["state"]), text[:300])

        err, before, _ = await call("get_server_status")
        err, r, text = await call("save_as_startup")
        check("save_as_startup", not err and "startup_block" in r, text[:300])

        err, r, text = await call("stop_server")
        check("stop_server", not err and "stopped" in r["result"], text)
        err, r, text = await call("start_server")
        st = r.get("state", {})
        check("restart brings the saved setup back", not err and st["map"] == before["map"]
              and st["gamemode"] == before["gamemode"] and bots(st, "red") == bots(before, "red")
              and bots(st, "blue") == bots(before, "blue") and st["pointlimit"] == 30, text[:500])
        err, r, text = await call("stop_server")
        check("final stop_server", not err, text)

    print(f"\n{len(failures)} failure(s)" + (": " + ", ".join(failures) if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
