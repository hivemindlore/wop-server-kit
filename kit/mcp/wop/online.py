"""Playing over the internet: friends on other networks join through playit.gg (free).

playit.gg gives the server an address on the internet and passes those players on to the server here, so
nothing has to change on the router. The parts:
- playit's program (playitd), downloaded once into tools/ and checked by sha256 (kit.json "playit");
- one approval by the host: the kit makes a claim code, opens https://playit.gg/claim/<code>, the host clicks
  approve there, and the kit swaps the code for this install's key (home/playit/playit.toml, which the
  program reads). Keys and codes never show up in what people read;
- the address: a playit "tunnel" that forwards UDP from the internet to the game port on 127.0.0.1;
- the keeper (online_keeper.py), a small background process that runs the program while the server runs.

home/playit/online.json remembers whether it's switched on and the address. It isn't in install.json
because the app and Claude change it while the setup may be holding install.json.

Everything players come in with through playit arrives from 127.0.0.1, like the kit's own console commands.
"""

from __future__ import annotations

import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from . import config, downloads
from .catalog import WopError
from .platforms import PlatformBehavior
from .rcon import Rcon

API_BASE = "https://api.playit.gg"
CLAIM_PAGE = "https://playit.gg/claim/"
TUNNEL_NAME = "WoP server"
SOFTWARE = "World of PADMAN game server (a free Quake 3 engine shooter), for playing with friends"
MANAGE_PAGE = "https://playit.gg/account/tunnels"
GUEST_LOGIN = "https://playit.gg/login/guest-account/"
LOG_LIMIT = 200_000   # bytes of online.log kept
KIT_JSON = Path(__file__).resolve().parents[2] / "kit.json"
KEEPER_LOCK = "keeper.lock"

NOT_HERE = "Playing over the internet isn't available on this computer yet (playit.gg has no version for it)."
NO_CONNECTION = "Couldn't reach playit.gg, which makes playing over the internet possible. Is this computer online?"


class PlayitRefused(WopError):
    """playit.gg answered, but said no; reason is its own code (CodeExpired, AuthRequired, ...)."""

    def __init__(self, reason: str):
        super().__init__(f"playit.gg said: {reason}")
        self.reason = reason


def _post(path: str, body: dict, secret: str | None) -> object:
    headers = {"Content-Type": "application/json", "User-Agent": downloads.USER_AGENT}
    if secret:
        headers["Authorization"] = f"Agent-Key {secret}"
    req = urllib.request.Request(API_BASE + path, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            reply = json.loads(r.read())
    except urllib.error.HTTPError as e:  # refusals can come with an error status too
        try:
            reply = json.loads(e.read())
        except ValueError:
            raise WopError(NO_CONNECTION) from None
    except (OSError, ValueError):
        raise WopError(NO_CONNECTION) from None
    if not isinstance(reply, dict):
        raise WopError(NO_CONNECTION)
    if reply.get("status") == "success":
        return reply.get("data")
    data = reply.get("data")
    reason = data if isinstance(data, str) else (data or {}).get("message") or json.dumps(data)
    raise PlayitRefused(str(reason))


class PlayitApi:
    """The few calls of playit.gg's API the kit needs. The claim is what playit's own setup sends; the tunnel
    calls are the v1 ones playit.gg's website sends (the old /tunnels/create refuses custom tunnels now)."""

    def __init__(self, secret: str | None = None, post: Callable[[str, dict, str | None], object] = _post,
                 version: str = "", log: Callable[[str], None] = lambda _: None):
        self.secret = secret
        self.post = post
        self.version = version
        self.log = log

    def _call(self, path: str, body: dict, secret: str | None) -> object:
        try:
            return self.post(path, body, secret)
        except PlayitRefused as e:
            self.log(f"{path} refused: {e.reason}")
            raise
        except WopError as e:
            self.log(f"{path} failed: {e}")
            raise

    def claim_setup(self, code: str) -> str:
        """WaitingForUserVisit, WaitingForUser, UserAccepted or UserRejected."""
        return str(self._call("/claim/setup", {"code": code, "agent_type": "self-managed",
                                               "version": f"playit {self.version}"}, None))

    def claim_exchange(self, code: str) -> str:
        return str(self._call("/claim/exchange", {"code": code}, None)["secret_key"])

    def rundata(self) -> dict:
        """agent_id; tunnels with their display_address ("host:port") and agent_config (local_ip/local_port,
        which playit's program reads); pending tunnels with a status_msg; notices."""
        return self._call("/v1/agents/rundata", {}, self.secret)

    def create_tunnel(self, agent_id: str, port: int) -> str:
        fields = [{"name": "local_ip", "value": "127.0.0.1"}, {"name": "local_port", "value": str(port)}]
        body = {"name": TUNNEL_NAME,
                "protocol": {"type": "raw-ports", "details": {"port_type": "udp", "port_count": 1,
                                                              "software_description": SOFTWARE}},
                "origin": {"type": "agent", "data": {"agent_id": agent_id, "config": {"fields": fields}}},
                "endpoint": {"type": "region", "details": {"region": "global", "port": None}},
                "enabled": True}
        return str(self._call("/v1/tunnels/create", body, self.secret)["id"])

    def delete_tunnel(self, tunnel_id: str) -> None:
        self._call("/tunnels/delete", {"tunnel_id": tunnel_id}, self.secret)

    def guest_login(self) -> str:
        """A web session for a guest account (refused with AccountIsNotGuest for a real account)."""
        return str(self._call("/login/guest", {}, self.secret)["session_key"])


def _field(tunnel: dict, name: str) -> str | None:
    for field in (tunnel.get("agent_config") or {}).get("fields") or []:
        if field.get("name") == name:
            return str(field.get("value"))
    return None


def _local_port(tunnel: dict) -> int | None:
    try:
        return int(_field(tunnel, "local_port") or "")
    except ValueError:
        return None


def _split_address(display: str) -> tuple[str, int] | None:
    host, _, port = (display or "").rpartition(":")
    return (host, int(port)) if host and port.isdigit() else None


# playit.gg's refusals that people can do something about, in plain words
REFUSALS = {
    "RequiresVerifiedAccount": "playit.gg wants you to confirm your email address first. Open playit.gg (Manage on "
                               "playit.gg), confirm it, then switch this on again.",
    "AccountHasFlaggedTunnel": "playit.gg wants a description for one of your other addresses first. Open playit.gg "
                               "(Manage on playit.gg) and update it, then switch this on again.",
    "RequiresPlayitPremium": "playit.gg only allows this with its paid plan.",
    "PublicPortRequiresPlayitPremium": "playit.gg only allows this with its paid plan.",
    "RegionRequiresPlayitPremium": "playit.gg only allows this with its paid plan.",
}


def settings() -> dict:
    return json.loads(KIT_JSON.read_text(encoding="utf-8"))["playit"]


class Online:
    """Switching internet play on and off, and what to tell the host and the players about it."""

    def __init__(self, behavior: PlatformBehavior, rcon: Rcon | None = None,
                 api: Callable[[str | None], PlayitApi] | None = None,
                 launch: Callable[[list[str], Path], None] | None = None):
        self.behavior = behavior
        self.rcon = rcon or Rcon()
        self.pins = settings()
        self.api = api or (lambda secret: PlayitApi(secret, version=self.pins["version"], log=self.log))
        self.launch = launch or behavior.launch_hidden

    def log(self, text: str) -> None:
        """home/playit/online.log: what playit.gg refused and why, for troubleshooting."""
        path = self.folder / "online.log"
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size > LOG_LIMIT:
                path.write_text(path.read_text(encoding="utf-8", errors="replace")[-LOG_LIMIT // 2:], encoding="utf-8")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ files

    @property
    def folder(self) -> Path:
        return config.home_dir() / "playit"

    @property
    def secret_file(self) -> Path:
        return self.folder / "playit.toml"

    @property
    def available(self) -> bool:
        return self.behavior.playit_asset in self.pins["assets"]

    def program(self) -> Path:
        """tools/playit-<version>: a new version gets a new file, so an update never replaces a running one."""
        return config.root_dir() / "tools" / f"playit-{self.pins['version']}{self.behavior.exe_suffix}"

    def program_args(self) -> list[str]:
        return [str(self.program()), "--secret-path", str(self.secret_file),
                "--log-path", str(self.folder / "playitd.log"),
                "--socket-path", self.behavior.playit_socket(self.folder, self.rcon.port)]

    def _state(self) -> dict:
        try:
            data = json.loads((self.folder / "online.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, state: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / "online.json.tmp"
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(self.folder / "online.json")

    def secret(self) -> str | None:
        try:
            text = self.secret_file.read_text(encoding="utf-8")
        except OSError:
            return None
        match = re.search(r'secret_key\s*=\s*"([0-9a-fA-F]+)"', text)
        return match.group(1) if match else None

    def _save_secret(self, secret: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.secret_file.write_text(f'secret_key = "{secret}"\n', encoding="utf-8")
        try:
            self.secret_file.chmod(0o600)
        except OSError:
            pass

    def _forget_key(self, state: dict) -> None:
        self.secret_file.unlink(missing_ok=True)
        for key in ("tunnel_id", "address", "public_port"):
            state.pop(key, None)

    # ------------------------------------------------------------------ what it looks like

    def wanted(self) -> bool:
        """Switched on and approved (the keeper checks this)."""
        return bool(self._state().get("enabled")) and self.secret() is not None

    def status(self, running: bool | None = None) -> dict:
        """phase: off, approving (waiting for the host in the browser), starting, server_off (ready, the
        server isn't on), online or problem. running: whether the server runs, if the caller knows."""
        state = self._state()
        enabled = self.available and bool(state.get("enabled"))
        address, port = state.get("address"), state.get("public_port")
        out = {"available": self.available, "enabled": enabled, "phase": "off", "address": address if enabled else None,
               "port": port if enabled else None, "approve_url": None, "message": "",
               "approved": self.available and self.secret() is not None}
        if not self.available:
            out["message"] = NOT_HERE
        elif not enabled:
            out["message"] = "Only players on your network can join."
        elif state.get("problem"):
            out.update(phase="problem", message=state["problem"])
        elif not self.secret():
            out.update(phase="approving", approve_url=CLAIM_PAGE + state["claim"] if state.get("claim") else None,
                       message="Approve it once on playit.gg in your browser (it's free), then it switches on.")
        elif not address:
            waiting = f" ({state['pending']})" if state.get("pending") else ""
            out.update(phase="starting", message=f"Getting an internet address from playit.gg{waiting}...")
        elif not (self.rcon.is_running() if running is None else running):
            out.update(phase="server_off", message=f"Friends anywhere can join at {address}, port {port}, "
                                                   "while the server is on.")
        elif not self.keeper_running():
            out.update(phase="starting", message="Connecting to playit.gg...")
        else:
            out.update(phase="online", message=f"Friends anywhere can join: address {address}, port {port}.")
        return out

    def join_details(self) -> dict | None:
        """The address for players somewhere else, or None while there is none."""
        state = self._state()
        if not (self.available and state.get("enabled") and state.get("address") and self.secret()):
            return None
        address, port = state["address"], state["public_port"]
        return {"address": address, "port": port, "connect_command": f"/connect {address}:{port}"}

    # ------------------------------------------------------------------ switching

    def enable(self) -> dict:
        """Switch internet play on, or take the next step: the app calls this again every few seconds while
        it waits, and Claude when the host says they approved. Opens the approval page once."""
        if not self.available:
            raise WopError(NOT_HERE)
        state = self._state()
        state["enabled"] = True
        state.pop("problem", None)
        self._save(state)
        self.ensure_program()
        secret = self.secret() or self._approve(state)
        if not secret:
            return self.status(running=False)
        running = self.rcon.is_running()
        if running:
            self.start_keeper()   # playit gives the address sooner while its program is connected
        if not self._find_address(secret, state):
            self._approve(state)   # playit.gg doesn't know this computer any more: a new approval page
        return self.status(running=running)

    def advance(self) -> dict:
        """The next step while the app waits (approval, address, connecting), but only while it's still on:
        Claude may have switched it off in the meantime."""
        if not (self.available and self._state().get("enabled")):
            return self.status(running=False)
        return self.enable()

    def disable(self) -> dict:
        """Only the home network again. The key and the address stay, so switching on again is instant."""
        state = self._state()
        state["enabled"] = False
        for key in ("claim", "problem"):
            state.pop(key, None)
        self._save(state)
        return {**self.status(running=False), "result": "Only players on your network can join now."}

    def manage(self) -> dict:
        """Open playit.gg to see and change the addresses. A guest account (no email) is signed in straight
        away; that link is a login, so it goes to the browser only, never to the screen."""
        secret = self.secret() if self.available else None
        url = MANAGE_PAGE if secret else "https://playit.gg"
        if secret:
            try:
                url = GUEST_LOGIN + self.api(secret).guest_login()
            except WopError:
                pass   # a real account (AccountIsNotGuest), or offline: the page asks to sign in
        self.behavior.open_url(url)
        return {"result": "playit.gg opened in your browser."}

    def forget(self, wait: float = 10.0) -> None:
        """Uninstall: switch off, let the keeper stop the program, and remove the address from playit.gg."""
        if not self._state() and not self.secret():
            return
        self.disable()
        deadline = time.monotonic() + wait
        while self.keeper_running() and time.monotonic() < deadline:
            time.sleep(0.5)
        state, secret = self._state(), self.secret()
        if secret and state.get("tunnel_id"):
            try:
                self.api(secret).delete_tunnel(state["tunnel_id"])
            except WopError:
                pass   # offline: the address just stays unused in the playit.gg account

    def _approve(self, state: dict) -> str | None:
        """The approval in the browser: the key once the host approved, else None (still waiting)."""
        code = state.get("claim")
        if not code:
            code = secrets.token_hex(5)
            state["claim"] = code
            self._save(state)
            self.behavior.open_url(CLAIM_PAGE + code)
        api = self.api(None)
        try:
            answer = api.claim_setup(code)
        except PlayitRefused:   # the code expired: start over with a new page
            state.pop("claim", None)
            self._save(state)
            return self._approve(state)
        if answer == "UserRejected":
            state["enabled"] = False
            state.pop("claim", None)
            self._save(state)
            raise WopError("It wasn't approved on playit.gg, so only players on your network can join.")
        if answer != "UserAccepted":
            return None
        try:
            secret = api.claim_exchange(code)
        except PlayitRefused:
            return None
        self._save_secret(secret)
        state.pop("claim", None)
        self._save(state)
        return secret

    def _find_address(self, secret: str, state: dict) -> bool:
        """Read (or ask for) the internet address. False if playit.gg doesn't accept the key any more."""
        api = self.api(secret)
        try:
            run = api.rundata()
        except PlayitRefused:
            self._forget_key(state)
            self._save(state)
            return False
        port = self.rcon.port
        ours = state.get("tunnel_id")
        udp = [t for t in run.get("tunnels") or [] if t.get("port_type") == "udp"]
        # Ours by id; else one made for this port before (by this kit first), e.g. after online.json was lost
        tunnel = next((t for t in udp if t.get("id") == ours), None) or next(
            (t for t in udp if _local_port(t) == port and t.get("name") == TUNNEL_NAME), None) or next(
            (t for t in udp if _local_port(t) == port), None)
        if tunnel and _local_port(tunnel) != port:   # the server moved to another port
            api.delete_tunnel(tunnel["id"])
            tunnel, ours = None, None
        state.pop("pending", None)
        found = tunnel and _split_address(tunnel.get("display_address", ""))
        if tunnel and found:
            state.update(tunnel_id=tunnel["id"], address=found[0], public_port=found[1])
            if tunnel.get("disabled_reason"):
                state["problem"] = (f"playit.gg has switched the internet address off ({tunnel['disabled_reason']}). "
                                    "Open playit.gg (Manage on playit.gg) to see why, or switch internet play off.")
                self.log(f"tunnel {tunnel['id']} disabled: {tunnel['disabled_reason']}")
            self._save(state)
            return True
        if tunnel:   # there, but without its address yet
            state["tunnel_id"] = tunnel["id"]
            self._save(state)
            return True
        pending = next((p for p in run.get("pending") or [] if p.get("id") == ours), None) if ours else None
        if pending:   # still being set up at playit.gg
            if pending.get("status_msg"):
                state["pending"] = pending["status_msg"]
            self._save(state)
            return True
        try:
            state["tunnel_id"] = api.create_tunnel(run["agent_id"], port)
        except PlayitRefused as e:
            state["problem"] = REFUSALS.get(e.reason) or (
                f"playit.gg didn't give this server an internet address ({e.reason}).")
            self._save(state)
            raise WopError(state["problem"]) from None
        self.log(f"asked playit.gg for an address: tunnel {state['tunnel_id']} to 127.0.0.1:{port}")
        for key in ("address", "public_port"):
            state.pop(key, None)
        self._save(state)
        return True

    # ------------------------------------------------------------------ the program and its keeper

    def ensure_program(self) -> Path:
        path = self.program()
        if path.exists():
            return path
        pin = self.pins["assets"][self.behavior.playit_asset]
        part = path.with_name(path.name + ".part")
        try:
            downloads.download(pin["url"], part)
        except OSError:
            part.unlink(missing_ok=True)
            raise WopError(NO_CONNECTION) from None
        if downloads.sha256(part) != pin["sha256"]:
            part.unlink(missing_ok=True)
            raise WopError("The download from playit.gg was damaged. Please try again.")
        part.replace(path)
        self.behavior.make_executable(path)
        for old in path.parent.glob("playit-*"):
            if old != path:
                try:
                    old.unlink()
                except OSError:
                    pass   # still running; it goes next time
        return path

    def keeper_running(self) -> bool:
        handle = self.behavior.try_lock(self.folder / KEEPER_LOCK)
        if handle is None:
            return True
        self.behavior.release_lock(handle)
        return False

    def start_keeper(self) -> bool:
        """Start the keeper if internet play is on (call when the server starts). False if it's off."""
        if not (self.available and self.wanted() and self.program().exists()):
            return False
        if not self.keeper_running():
            # Run from home/playit, not from inside kit/: Windows can't replace a folder a program runs in,
            # and kit updates replace kit/
            mcp = Path(__file__).resolve().parents[1]
            start = f"import sys; sys.path.insert(0, {str(mcp)!r}); from wop.online_keeper import main; sys.exit(main())"
            self.folder.mkdir(parents=True, exist_ok=True)
            self.launch([sys.executable, "-c", start, "--home", str(config.home_dir()), "--port", str(self.rcon.port)],
                        self.folder)
        return True
