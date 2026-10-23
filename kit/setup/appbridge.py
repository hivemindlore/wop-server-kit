# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The WoP Server app's link to the kit: every rule about the game, the network and the setup lives in
wopkit.py and the wop package; the app asks this process and shows the answers.

    uv run --script appbridge.py        (started by the app; talks on stdin/stdout)

Protocol: one JSON object per line.
    app -> bridge   {"id": 7, "method": "server.status", "params": {}}
    bridge -> app   {"id": 7, "result": {...}}  or  {"id": 7, "error": {"message": "..."}}
    bridge -> app   {"event": "log.lines", "data": {...}}   (no id: pushed whenever something happens)
Requests run on their own threads, so a slow one (starting the server, the first setup) never holds up
the others or the log. Messages meant for people are already worded for people who aren't technical.
"""

from __future__ import annotations

import getpass
import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wopkit  # noqa: E402  (sets up the paths and the OS behavior)
import ai_apps  # noqa: E402
from wop import config  # noqa: E402
from wop.actions import SPAWN_PROTECT_SECONDS, Game  # noqa: E402
from wop.catalog import WopError  # noqa: E402
from wop.config_files import set_cfg_value  # noqa: E402
from wop.serverlog import LogTail, color_segments  # noqa: E402

PROTOCOL = 1
LOG_POLL = 0.5          # seconds between looks at the server log
LOG_HISTORY = 500       # lines sent when the app opens the Logs tab


class Bridge:
    def __init__(self, out=None):
        self.out = out or sys.stdout
        self.lock = threading.Lock()
        self.os = wopkit.OS
        self.game = Game(behavior=self.os)
        self.tail = LogTail(wopkit.CFG / "qconsole.log")
        self.pool = ThreadPoolExecutor(max_workers=8)
        self.setup_lock = threading.Lock()
        self.was_running = False
        wopkit.UI = BridgeUi(self)   # no text window: messages become events, permission asks in a dialog
        self.methods = {
            "hello": self.hello,
            "setup.start": self.setup_start,
            "server.status": self.server_status,
            "server.start": self.server_start,
            "server.stop": self.server_stop,
            "server.join_info": self.join_info,
            "server.set_name": self.set_name,
            "server.set_join_password": self.set_join_password,
            "settings.get": self.settings_get,
            "settings.set_weapons": self.settings_set_weapons,
            "settings.set_spawn_protection": self.settings_set_spawn_protection,
            "network.check": self.network_check,
            "network.fix": self.network_fix,
            "online.status": self.online_status,
            "online.enable": self.online_enable,
            "online.advance": self.online_advance,
            "online.disable": self.online_disable,
            "online.manage": self.online_manage,
            "log.history": self.log_history,
            "console.run": self.console_run,
            "ai.list": self.ai_list,
            "ai.connect": self.ai_connect,
            "ai.disconnect": self.ai_disconnect,
            "ai.open": self.ai_open,
            "ai.restart": self.ai_restart,
            "kit.check_update": self.check_update,
            "kit.update": self.update,
            "game.play": self.play,
            "open.log_folder": self.open_log_folder,
        }

    # ------------------------------------------------------------------ plumbing

    def send(self, message: dict) -> None:
        with self.lock:
            self.out.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.out.flush()

    def emit(self, event: str, data) -> None:
        self.send({"event": event, "data": data})

    def handle(self, line: str) -> None:
        try:
            request = json.loads(line)
        except ValueError:
            return
        if not isinstance(request, dict):
            return
        self.pool.submit(self._answer, request)

    def _answer(self, request: dict) -> None:
        rid = request.get("id")
        method = self.methods.get(request.get("method", ""))
        try:
            if method is None:
                raise WopError(f"Unknown request '{request.get('method')}'.")
            result = method(**(request.get("params") or {}))
            self.send({"id": rid, "result": result})
        except (WopError, ValueError, KeyError) as e:
            self.send({"id": rid, "error": {"message": str(e).strip("'")}})
        except SystemExit as e:  # wopkit stops with a message for the user (no disk space, damaged download)
            self.send({"id": rid, "error": {"message": str(e.code or "Something went wrong.").strip()}})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            self.send({"id": rid, "error": {"message": f"Something went wrong: {e}"}})

    def run(self, stdin=None) -> None:
        threading.Thread(target=self._follow_log, daemon=True).start()
        for line in stdin or sys.stdin:
            if line.strip():
                self.handle(line)
        self.pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ helpers

    def _inst(self) -> dict:
        return wopkit.load_install()

    def _game_dir(self, inst: dict) -> Path | None:
        game = inst.get("game_dir")
        return Path(game) if game and wopkit.game_ok(Path(game)) else None

    def _require_game(self) -> tuple[dict, Path]:
        inst = self._inst()
        game = self._game_dir(inst)
        if not game:
            raise WopError("The server isn't set up yet.")
        return inst, game

    def _port(self) -> int:
        return self._inst().get("port", wopkit.SETTINGS["default_port"])

    # ------------------------------------------------------------------ setup

    def hello(self) -> dict:
        inst = self._inst()
        game = self._game_dir(inst)
        if game and not inst.get("hidden_server"):
            # From now on the server runs without a window, also when Claude starts it
            inst["hidden_server"] = True
            wopkit.save_install(inst)
        if game:
            wopkit.ensure_server_files(inst, game)  # the run-server scripts follow kit updates
        return {"protocol": PROTOCOL, "kit_version": wopkit.kit_version(), "platform": self.os.name,
                "installed": game is not None, "server_name": inst.get("server_name") or config_name(),
                "default_server_name": f"{getpass.getuser()}'s WoP server", "port": self._port(),
                "root": str(wopkit.ROOT)}

    def setup_start(self, server_name: str = "") -> dict:
        """The first-time setup (or a repair): game, server files, Rosetta, AI connection parts, shortcuts.
        Progress comes as setup.step / setup.message / setup.progress events."""
        if not self.setup_lock.acquire(blocking=False):
            raise WopError("The setup is already running.")
        try:
            inst = self._inst()
            name = wopkit.clean_name(server_name) or inst.get("server_name") or f"{getpass.getuser()}'s WoP server"
            inst["server_name"] = name
            inst["hidden_server"] = True
            game = wopkit.prepare(inst)
            wopkit.ensure_rosetta()
            wopkit.ensure_mcp_ready()
            wopkit.ensure_shortcuts(inst, game)
            inst["version"] = wopkit.kit_version()
            wopkit.save_install(inst)
            self.emit("setup.step", {"text": "Done."})
            return {"installed": True, "server_name": name}
        finally:
            self.setup_lock.release()

    # ------------------------------------------------------------------ server

    def server_status(self) -> dict:
        """Polled by the app, so it stays cheap: the server answers only a few questions a second (Claude
        needs some too). Offline costs one quick question; running costs the two that read the state."""
        port = self._port()
        state = {"running": False}
        if self.was_running or self.game.rcon.is_running():
            try:
                state = self.game.state().to_dict()
            except WopError:
                pass
        self.was_running = state["running"]
        state["port"] = port
        state["server_name"] = config_name()
        return state

    def server_start(self) -> dict:
        self._require_game()
        return self.game.start_server()

    def server_stop(self) -> dict:
        return self.game.stop_server()

    def join_info(self) -> dict:
        info = self.game.get_join_info()
        port = info["port"]
        info["addresses"] = [{"address": ip, "connection": name} for ip, name in wopkit.join_addresses()]
        info["in_lan_list"] = port in wopkit.LAN_PORTS
        info["download_url"] = wopkit.SETTINGS["wop_download_page"]
        return info

    def set_name(self, name: str) -> dict:
        result = self.game.set_server_name(name)
        inst = self._inst()
        inst["server_name"] = config_name()
        wopkit.save_install(inst)
        return result

    # ------------------------------------------------------------------ game settings
    # Changed on the running server right away, and saved in server-friends.cfg so the server starts with them.

    def settings_get(self) -> dict:
        running = self.game.rcon.is_running()
        if running:
            state = self.game.state()
            instapad, seconds = state.instapad, state.spawn_protect
            changeable = seconds is not None
        else:
            instapad = (config.setting("g_instaPad") or "0").strip() == "1"
            seconds = int(config.setting("g_spawnProtect") or "6")
            changeable = (wopkit.CFG / "vm" / "qagame.qvm").exists()
        seconds = 6 if seconds is None else seconds
        return {"running": running, "instapad": instapad, "spawn_protection": seconds > 0,
                "spawn_protection_seconds": seconds, "spawn_protection_changeable": changeable}

    def settings_set_weapons(self, instapad: bool) -> dict:
        set_cfg_value(config.server_cfg(), "g_instaPad", "1" if instapad else "0")
        weapons = "InstaPad" if instapad else "all weapons"
        if self.game.rcon.is_running():
            self.game.set_weapons("instapad" if instapad else "regular")
            return {"result": f"Now playing with {weapons}; the match restarted so it applies."}
        return {"result": f"Weapons: {weapons}, saved for the next start."}

    def settings_set_spawn_protection(self, on: bool) -> dict:
        seconds = SPAWN_PROTECT_SECONDS if on else 0
        set_cfg_value(config.server_cfg(), "g_spawnProtect", str(seconds))
        what = f"Spawn protection {'on' if on else 'off'}"
        if self.game.rcon.is_running():
            if self.game.state().spawn_protect is None:
                return {"result": f"{what}: saved. It applies after the server restarts once."}
            self.game.set_spawn_protection(on)
            return {"result": f"{what}, from the next respawn."}
        return {"result": f"{what}: saved for the next start."}

    def set_join_password(self, password: str) -> dict:
        """Kept after a restart too (written to server-friends.cfg), unlike the Claude tool."""
        password = "".join(c for c in password if c.isalnum() or c in "-_.!?")[:32]
        set_cfg_value(config.server_cfg(), "g_password", password)
        if self.game.rcon.is_running():
            self.game.set_join_password(password)
        if password:
            return {"result": f"Join password set to '{password}'. Players type /password {password} in the game's "
                              "console (~) before joining."}
        return {"result": "Join password removed; anyone on your network can join."}

    # ------------------------------------------------------------------ network

    def _check(self, inst: dict, game: Path) -> dict:
        check = wopkit.firewall_check(inst, game, inst.get("port", wopkit.SETTINGS["default_port"]))
        wopkit.save_install(inst)
        problems = check.problems or []
        return {
            "checked": check.problems is not None,
            "ok": check.problems is not None and not problems,
            "problems": [{"text": p.text, "fixable": bool(p.fix)} for p in problems],
            "can_fix": any(p.fix for p in problems),
            "permission_hint": self.os.elevation_hint.replace("\n", " ") if any(p.fix for p in problems) else "",
            "notes": wopkit.network_notes(inst.get("port", wopkit.SETTINGS["default_port"])),
            "others": check.others,
            "firewall_name": self.os.firewall_name,
            "help_url": wopkit.TROUBLESHOOTING_URL,
        }

    def network_check(self) -> dict:
        inst, game = self._require_game()
        return self._check(inst, game)

    def network_fix(self) -> dict:
        inst, game = self._require_game()
        port = inst.get("port", wopkit.SETTINGS["default_port"])
        before = wopkit.firewall_check(inst, game, port)
        accepted, _ = wopkit.fix_firewall(inst, game, port, before)
        result = self._check(inst, game)
        result["accepted"] = accepted
        return result

    # ------------------------------------------------------------------ playing over the internet

    def online_status(self) -> dict:
        return self.game.online.status(running=self.was_running or None)

    def online_enable(self) -> dict:
        """Switch on; then the app calls online.advance every few seconds while it waits (approval, address)."""
        self._require_game()
        return self.game.online.enable()

    def online_advance(self) -> dict:
        return self.game.online.advance()

    def online_disable(self) -> dict:
        return self.game.online.disable()

    def online_manage(self) -> dict:
        return self.game.online.manage()

    # ------------------------------------------------------------------ log and commands

    def log_history(self, lines: int = LOG_HISTORY) -> dict:
        return {"lines": [color_segments(line) for line in self.tail.last_lines(int(lines))]}

    def _follow_log(self) -> None:
        while True:
            time.sleep(LOG_POLL)
            try:
                restarted, lines = self.tail.new_lines()
            except Exception:  # noqa: BLE001 (keep following whatever happens)
                continue
            if restarted:
                self.emit("log.reset", {})
            if lines:
                self.emit("log.lines", {"lines": [color_segments(line) for line in lines]})

    def console_run(self, command: str) -> dict:
        return self.game.run_console_command(command)

    # ------------------------------------------------------------------ AI apps

    def ai_list(self) -> dict:
        name = wopkit.SETTINGS["mcp_name"]
        return {"apps": [ai_apps.describe(app, self.os, name) for app in ai_apps.APPS if app.available(self.os)]}

    def ai_connect(self, app_id: str) -> dict:
        app = ai_apps.find(app_id)
        ai_apps.connect(app, self.os, wopkit.SETTINGS["mcp_name"], wopkit.mcp_entry())
        return ai_apps.describe(app, self.os, wopkit.SETTINGS["mcp_name"])

    def ai_disconnect(self, app_id: str) -> dict:
        app = ai_apps.find(app_id)
        ai_apps.disconnect(app, self.os, wopkit.SETTINGS["mcp_name"])
        return ai_apps.describe(app, self.os, wopkit.SETTINGS["mcp_name"])

    def ai_open(self, app_id: str) -> dict:
        app = ai_apps.find(app_id)
        ai_apps.open_app(app, self.os)
        return ai_apps.describe(app, self.os, wopkit.SETTINGS["mcp_name"])

    def ai_restart(self, app_id: str) -> dict:
        app = ai_apps.find(app_id)
        ai_apps.restart_app(app, self.os)
        return ai_apps.describe(app, self.os, wopkit.SETTINGS["mcp_name"])

    # ------------------------------------------------------------------ kit and game

    def check_update(self) -> dict:
        found = wopkit.newer_kit()
        return {"available": bool(found), "version": found[0] if found else wopkit.kit_version(),
                "current": wopkit.kit_version()}

    def update(self) -> dict:
        found = wopkit.newer_kit()
        if not found:
            return {"updated": False, "version": wopkit.kit_version()}
        wopkit.update_kit(found[1])
        return {"updated": True, "version": found[0]}  # the app restarts this bridge to use the new kit

    def play(self) -> dict:
        _, game = self._require_game()
        self.os.play_game(game)
        return {"result": "World of PADMAN is starting."}

    def open_log_folder(self) -> dict:
        self.os.open_path(wopkit.CFG)
        return {}


def config_name() -> str:
    try:
        return config.server_name()
    except OSError:
        return wopkit.load_install().get("server_name") or "WoP server"


class BridgeUi(wopkit.ConsoleUi):
    """wopkit's messages become events; there are no questions (the app asks them before)."""
    terminal = False

    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self._last = 0.0

    def say(self, text: str = "") -> None:
        text = text.strip()
        if text.startswith(">> "):
            self.bridge.emit("setup.step", {"text": text[3:]})
        elif text:
            self.bridge.emit("setup.message", {"text": text})

    def progress(self, done: int, total: int) -> None:
        now = time.monotonic()
        if now - self._last >= 0.25 or done >= total:
            self._last = now
            self.bridge.emit("setup.progress", {"done": done, "total": total, "percent": int(done * 100 / total)})

    def progress_done(self) -> None:
        pass

    def ask(self, question: str, default: str) -> str:
        return default

    def yes(self, question: str, default: bool = True) -> bool:
        return default

    def pause(self, seconds: float | None = None) -> None:
        pass


def main() -> None:
    # Only protocol lines may go to stdout; anything else printed goes to stderr (the app's log)
    out = sys.stdout
    sys.stdout = sys.stderr
    Bridge(out).run(sys.stdin)


if __name__ == "__main__":
    main()
