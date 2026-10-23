# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""WoP Server Kit: installs, updates, starts and stops a World of PADMAN LAN server,
and connects Claude Desktop to it.

    wopkit.py start       first time: set everything up; every time: update, then run the server
    wopkit.py stop        stop the server
    wopkit.py banner      the "how to join" text shown when the server window opens
    wopkit.py uninstall   remove everything again

Started by start-wop-server.bat / start-wop-server.sh (first time) and by the shortcuts in the
"World of PADMAN" folder on the desktop. The WoP Server app uses the same steps through appbridge.py.
Only uses the Python standard library; uv provides Python.
Everything that differs between Windows, Mac and Linux is in kit/mcp/wop/platforms (OS below).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]          # <root>/kit
ROOT = KIT.parent
sys.path.insert(0, str(KIT / "mcp"))
sys.path.insert(0, str(KIT / "setup"))

import ai_apps  # noqa: E402
from wop import downloads, launcher, online  # noqa: E402
from wop.downloads import fetch, sha256  # noqa: E402
from wop.platforms import FirewallCheck, PlatformBehavior, Shortcut, detect  # noqa: E402

OS: PlatformBehavior = detect()
SETTINGS = json.loads((KIT / "kit.json").read_text(encoding="utf-8"))

HOME = ROOT / "home"
CFG = HOME / "wop"
INSTALL_JSON = ROOT / "install.json"
WOPKIT = KIT / "setup" / "wopkit.py"
LAN_PORTS = range(27960, 27964)                     # the ports the game's LAN list searches
TROUBLESHOOTING_URL = f"https://github.com/{SETTINGS['repo']}/blob/{SETTINGS['branch']}/kit/docs/troubleshooting.md"
SHORTCUT_FOLDER = "World of PADMAN"                 # on the desktop
SERVER_SUBFOLDER = "WOP-server"                     # inside it: Start, Stop, Help, Troubleshooting
NEED_FREE_GB = 3


def uv() -> Path:
    return ROOT / "tools" / OS.uv_name


def run_server_script() -> Path:
    return ROOT / OS.run_script_name


def launcher_script() -> Path:
    return ROOT / OS.launcher_name


# uv keeps its Python and packages inside the kit folder, so uninstalling removes everything
UV_ENV = {
    "UV_CACHE_DIR": str(ROOT / "cache" / "uv"),
    "UV_PYTHON_INSTALL_DIR": str(ROOT / "python"),
    "UV_PYTHON_PREFERENCE": "only-managed",
}
os.environ.update(UV_ENV)
os.environ["WOP_HOME"] = str(HOME)
os.environ["WOP_START_SCRIPT"] = str(run_server_script())


# --------------------------------------------------------------------------- talking to the user

def _tty_input(prompt: str) -> str:
    """input() that also works under `curl ... | bash`, where stdin is the script itself."""
    if OS.keyboard_is_stdin or (sys.stdin and sys.stdin.isatty()):
        try:
            return input(prompt).lstrip("\ufeff")  # piped input from PowerShell starts with a BOM
        except EOFError:
            return ""
    try:
        with open("/dev/tty", "r+") as tty:
            tty.write(prompt)
            tty.flush()
            return tty.readline().rstrip("\n")
    except OSError:
        return ""


class ConsoleUi:
    """The text window. The app bridge swaps in its own Ui (no questions, progress as events)."""
    terminal = True     # questions and passwords can be typed here

    def say(self, text: str = "") -> None:
        print(text, flush=True)

    def progress(self, done: int, total: int) -> None:
        print(f"\r   {int(done * 100 / total):3d}%  ({done / 1e9:.2f} of {total / 1e9:.2f} GB)", end="", flush=True)

    def progress_done(self) -> None:
        print(flush=True)

    def ask(self, question: str, default: str) -> str:
        answer = _tty_input(f"{question} [{default}]: ").strip()
        return answer or default

    def yes(self, question: str, default: bool = True) -> bool:
        if os.environ.get("WOP_ASSUME_YES"):
            return default
        hint = "Y/n" if default else "y/N"
        answer = _tty_input(f"{question} ({hint}): ").strip().lower()
        return default if not answer else answer.startswith(("y", "j"))

    def pause(self, seconds: float | None = None) -> None:
        if seconds is not None:
            time.sleep(seconds)
        elif not os.environ.get("WOP_ASSUME_YES"):
            _tty_input("Press Enter to close this window...")


UI = ConsoleUi()


def say(text: str = "") -> None:
    UI.say(text)


def step(text: str) -> None:
    say(f"\n>> {text}")


def ask(question: str, default: str) -> str:
    return UI.ask(question, default)


def yes(question: str, default: bool = True) -> bool:
    return UI.yes(question, default)


def pause(seconds: float | None = None) -> None:
    UI.pause(seconds)


# --------------------------------------------------------------------------- small helpers

def load_install() -> dict:
    try:
        return json.loads(INSTALL_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_install(inst: dict) -> None:
    INSTALL_JSON.write_text(json.dumps(inst, indent=2), encoding="utf-8")


def kit_version() -> str:
    try:
        return (KIT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def _version_tuple(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in v.strip().split("."))


def download(url: str, dest: Path, expected_size: int | None = None) -> None:
    """Download with progress (UI.progress); continues a half-finished download."""
    downloads.download(url, dest, expected_size, progress=UI.progress)
    UI.progress_done()


def clean_name(text: str) -> str:
    return "".join(c for c in text if c.isprintable() and c not in '"\\;\ufeff').strip()[:40]


def server_running(port: int) -> bool:
    from wop.rcon import Rcon
    try:
        return Rcon(port=port).is_running(retry=True)
    except Exception:  # noqa: BLE001 (no config yet, ...)
        return False


def desktop_dir() -> Path:
    if os.environ.get("WOP_DESKTOP"):
        return Path(os.environ["WOP_DESKTOP"])
    return OS.desktop_dir()


# --------------------------------------------------------------------------- update

def remote_version_and_zip() -> tuple[str, str] | None:
    """(version, zip url) of the newest kit, or None when offline."""
    override = os.environ.get("WOP_KIT_URL")
    if override:  # a local zip, for testing updates
        path = Path(override.removeprefix("file:///").removeprefix("file://"))
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith("kit/VERSION"))
            return z.read(name).decode().strip(), str(path)
    repo, branch = SETTINGS["repo"], SETTINGS["branch"]
    try:
        version = fetch(f"https://raw.githubusercontent.com/{repo}/{branch}/kit/VERSION", timeout=5).decode().strip()
    except OSError:
        return None
    return version, f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"


def install_kit_zip(zip_path: Path) -> None:
    """Replace <root>/kit with the kit/ folder from a repo zip. home/, game/ etc. stay untouched."""
    new, old = ROOT / "kit.new", ROOT / "kit.old"
    shutil.rmtree(new, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            parts = info.filename.split("/", 1)
            if len(parts) < 2 or not parts[1].startswith("kit/") or info.is_dir():
                continue
            target = new / parts[1][len("kit/"):]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    KIT.rename(old)
    new.rename(KIT)
    shutil.rmtree(old, ignore_errors=True)


def newer_kit() -> tuple[str, str] | None:
    """(version, zip) when a newer kit is out, else None."""
    found = remote_version_and_zip()
    if not found or _version_tuple(found[0]) <= _version_tuple(kit_version()):
        return None
    return found


def update_kit(url: str) -> None:
    if Path(url).exists():
        zip_path = Path(url)
    else:
        zip_path = Path(tempfile.gettempdir()) / "wop-server-kit-update.zip"
        zip_path.write_bytes(fetch(url, timeout=60))
    install_kit_zip(zip_path)


def maybe_update() -> None:
    found = newer_kit()
    if not found:
        return
    version, url = found
    step(f"Updating the WoP Server Kit from {kit_version()} to {version}...")
    update_kit(url)
    say("   Updated. Restarting with the new version...")
    sys.exit(subprocess.call([str(uv()), "run", "--script", str(WOPKIT), *sys.argv[1:], "--no-update"]))


# --------------------------------------------------------------------------- game

def game_ok(game: Path) -> bool:
    return (game / OS.server_bin).exists() and (game / "wop" / "wop_maps_1.7.0.pk3").exists()


def ensure_game(inst: dict) -> Path:
    if inst.get("game_dir") and game_ok(Path(inst["game_dir"])):
        return Path(inst["game_dir"])
    existing = None if os.environ.get("WOP_FORCE_DOWNLOAD") else OS.find_existing_game()
    if existing:
        step(f"Found World of PADMAN already installed in {existing}; using that.")
        inst["game_dir"], inst["game_reused"] = str(existing), True
        return existing

    game = ROOT / "game"
    step("Downloading World of PADMAN 1.7.0 (1.2 GB, from the official WoP website on GitHub).")
    say("   This only happens once. It can take a while on slow internet; you can leave it running.")
    free = shutil.disk_usage(ROOT).free / 1e9
    if free < NEED_FREE_GB:
        raise SystemExit(f"   Not enough disk space: {free:.1f} GB free, about {NEED_FREE_GB} GB needed.")
    zip_path = ROOT / "downloads" / "wop-1.7.0-unified.zip"
    local = os.environ.get("WOP_GAME_ZIP")  # testing: use an already downloaded copy
    if local:
        zip_path = Path(local)
    else:
        download(SETTINGS["wop_zip_url"], zip_path, SETTINGS["wop_zip_size"])
    say("   Checking the download...")
    if sha256(zip_path) != SETTINGS["wop_zip_sha256"]:
        if not local:
            zip_path.unlink(missing_ok=True)
        raise SystemExit("   The download is damaged. Run the kit again to download it again.")

    say("   Unpacking...")
    partial = ROOT / "game.partial"
    shutil.rmtree(partial, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if OS.wanted_in_game_zip(info.filename):
                z.extract(info, partial)
    OS.prepare_game(partial)
    shutil.rmtree(game, ignore_errors=True)
    partial.rename(game)
    if not local:
        shutil.rmtree(ROOT / "downloads", ignore_errors=True)
    inst["game_dir"], inst["game_reused"] = str(game), False
    say("   World of PADMAN is ready.")
    return game


# --------------------------------------------------------------------------- server files

def ensure_game_module(game: Path) -> None:
    """The server's game code with the g_spawnProtect setting (kit/server/game: WoP 1.7.0 plus one patch).

    The server reads vm/qagame.qvm from its home folder before the game's own, so only the server uses it; the
    game folder and the players' games stay as they are. It's only for WoP 1.7.0: with any other version it's
    removed again, so a newer official game never runs with this older game code.
    """
    target = CFG / "vm" / "qagame.qvm"
    patched = KIT / "server" / "vm" / "qagame.qvm"
    want = SETTINGS["patched_qagame_sha256"]
    if (game / SETTINGS["patched_qagame_for"]).exists() and patched.exists() and sha256(patched) == want:
        if not target.exists() or sha256(target) != want:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(patched, target)
    elif target.exists() and sha256(target) == want:
        target.unlink()


def ensure_server_files(inst: dict, game: Path) -> None:
    CFG.mkdir(parents=True, exist_ok=True)
    cfg = CFG / "server-friends.cfg"
    if not cfg.exists():
        template = (KIT / "server" / "server-friends.cfg").read_text(encoding="utf-8")
        password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
        text = template.replace("__SERVER_NAME__", inst["server_name"]).replace("__RCON_PASSWORD__", password)
        cfg.write_text(text, encoding="utf-8")
    for name in ("teams.cfg", "mode.cfg"):
        if not (CFG / name).exists():
            shutil.copyfile(KIT / "server" / name, CFG / name)
    ensure_game_module(game)

    # The "how to join" text gets its own window: in the server window the server's log scrolls it away
    scripts = OS.run_scripts(ROOT, inst["port"], UV_ENV, uv(), WOPKIT, game,
                             lambda port_var: launcher.script_line(OS, game, HOME, port_var))
    for path, text in scripts.items():
        path.write_text(text, encoding="utf-8", newline="")
        OS.make_executable(path)


# --------------------------------------------------------------------------- network / Rosetta

def firewall_check(inst: dict, game: Path, port: int) -> FirewallCheck:
    if os.environ.get("WOP_SKIP_FIREWALL"):
        return FirewallCheck([])
    return OS.firewall_check(str(game / OS.server_bin), port, inst)


def fix_firewall(inst: dict, game: Path, port: int, check: FirewallCheck) -> tuple[bool, FirewallCheck]:
    """Apply every fix at once (the OS asks for permission once). (accepted, the check afterwards)."""
    fixes = [p.fix for p in check.problems or [] if p.fix]
    accepted = OS.run_elevated(fixes, terminal=UI.terminal) if fixes else True
    if accepted:
        OS.after_fix([p for p in check.problems or [] if p.fix], port, inst)
    after = firewall_check(inst, game, port)
    return accepted, (after if after.problems is not None else check)


def network_notes(port: int) -> list[str]:
    """Things the kit can't fix but that decide whether the players find the server."""
    from wop.actions import Game
    notes = []
    if not Game.lan_addresses():
        notes.append("This computer doesn't seem to be connected to a network, so nobody else can join yet.")
    if port not in LAN_PORTS:
        notes.append(f"The game's LAN list only searches ports 27960-27963, and this server uses {port}. "
                     f"The players won't see it in the list; they join with /connect <address>:{port}")
    return notes


def ensure_firewall(inst: dict, game: Path, port: int) -> None:
    """Checked on every start: can the other computers on the network reach the server? If not, offer to fix it."""
    if not os.environ.get("WOP_SKIP_FIREWALL"):
        _firewall_console(inst, game, port)
    for note in network_notes(port):
        say(f"\n   Note: {note}")


def _say_problems(problems: list[str]) -> None:
    say("   Other computers on your network can't join your server yet:")
    for problem in problems:
        say(f"   - {problem}")


def _say_not_fixed(problems: list[str]) -> None:
    say("   Not everything could be fixed:")
    for problem in problems:
        say(f"   - {problem}")
    say(f"   The server still works on this computer. Help with this: {TROUBLESHOOTING_URL}")


def _say_declined() -> None:
    say("   OK, nothing changed. The server still works, but only on this computer.")
    say("   You'll be asked again the next time you start the server.")


def _firewall_console(inst: dict, game: Path, port: int) -> None:
    step("Checking that the players on your network can join...")
    check = firewall_check(inst, game, port)
    if check.problems is None:
        say(f"   Couldn't read the {OS.firewall_name} settings, so this was skipped.")
        say(f"   If the players can't join: {TROUBLESHOOTING_URL}")
        return
    problems = check.problems
    if not problems:
        say("   OK.")
    elif not any(p.fix for p in problems):
        _say_not_fixed([p.text for p in problems])
    else:
        _say_problems([p.text for p in problems])
        if yes("   Do you want to allow this?"):
            for line in OS.elevation_hint.splitlines():
                say(f"   {line}")
            accepted, check = fix_firewall(inst, game, port, check)
            problems = check.problems or []
            if not problems:
                say("   Done. Other computers on your network can now join.")
            elif not accepted and any(p.fix for p in problems):
                _say_declined()
            else:
                _say_not_fixed([p.text for p in problems])
        else:
            _say_declined()
    if check.others and check.others != inst.get("other_firewalls"):
        say(f"   Note: {', '.join(check.others)} also guards this computer. If the players can't join, allow")
        say("   World of PADMAN there too (or ask its support how to allow a program on your home network).")
    inst["other_firewalls"] = check.others


def ensure_rosetta() -> None:
    if not OS.needs_rosetta():
        return
    step("World of PADMAN is made for Intel Macs; your Mac needs Apple's free \"Rosetta\" to run it.")
    say(f"   {OS.elevation_short}")
    OS.run_elevated([OS.rosetta_command()], terminal=UI.terminal)


# --------------------------------------------------------------------------- Claude Desktop

def claude_config_paths() -> list[Path]:
    if os.environ.get("WOP_CLAUDE_CONFIG"):
        return [Path(os.environ["WOP_CLAUDE_CONFIG"])]
    return OS.claude_config_paths()


def claude_control() -> bool:
    """False in tests (WOP_NO_CLAUDE_LAUNCH): never look at, quit or open the real Claude Desktop."""
    return not os.environ.get("WOP_NO_CLAUDE_LAUNCH")


def claude_app() -> str | None:
    """How to open Claude Desktop, or None if it isn't installed."""
    if "WOP_CLAUDE_APP" in os.environ:
        return os.environ["WOP_CLAUDE_APP"] or None
    return OS.claude_app()


def claude_running() -> bool:
    return claude_control() and OS.claude_running()


def install_claude() -> None:
    page = SETTINGS["claude_download_page"]
    if not claude_control():
        return
    if OS.can_install_claude():
        say("   Installing Claude Desktop (this can take a minute)...")
        OS.install_claude()
        return
    say(f"   Opening {page}. Download and install Claude Desktop, then come back here.")
    OS.open_url(page)
    _tty_input("   Press Enter when Claude Desktop is installed...")


def mcp_entry() -> dict:
    return {
        "command": str(uv()),
        "args": ["run", "--script", str(KIT / "mcp" / "server.py")],
        "env": {"WOP_HOME": str(HOME), "WOP_START_SCRIPT": str(run_server_script()), **UV_ENV},
    }


def set_claude_entry(entry: dict | None) -> bool:
    """Add (or with None remove) our server in Claude's config. True if a file changed."""
    paths = claude_config_paths()
    for path in paths:
        if path.exists() and ai_apps._read(path) is None:
            say(f"   Couldn't read {path} (not valid JSON); left it alone.")
    return ai_apps.set_entry(paths, "mcpServers", SETTINGS["mcp_name"], entry)


def ensure_mcp_ready() -> bool:
    step("Preparing the Claude connection (downloads a few small parts the first time)...")
    for attempt in range(3):
        # Antivirus scanning fresh downloads can make the first try fail ("failed to persist temporary file")
        proc = subprocess.run([str(uv()), "run", "--quiet", "--script", str(KIT / "mcp" / "server.py"), "--selftest"],
                              capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.startswith("ok"):
            say("   Ready.")
            return True
        time.sleep(2 * (attempt + 1))
    say("   That didn't work, so Claude can't manage the server yet. The server itself works fine.")
    say("   Check your internet connection and run Start WoP Server again.")
    details = (proc.stderr or proc.stdout).strip().splitlines()
    if details:
        say(f"   (details: {details[-1][:200]})")
    return False


def ensure_claude(inst: dict, first_run: bool) -> None:
    if not claude_config_paths():
        return  # no Claude Desktop for this OS
    app = claude_app()
    if not app and not inst.get("claude_declined"):
        step("Claude Desktop lets you change the game by just asking (\"switch to Capture The Lolly\").")
        if yes("   Claude Desktop isn't installed. Install it now?"):
            install_claude()
            app = claude_app()
            if not app:
                say("   Claude Desktop still isn't found. You can install it later from "
                    f"{SETTINGS['claude_download_page']} and run Start WoP Server again.")
        else:
            inst["claude_declined"] = True
            say(f"   OK. You can install it later from {SETTINGS['claude_download_page']}.")

    changed = set_claude_entry(mcp_entry())
    if not app:
        return
    if changed and claude_running():
        say("\n   Claude Desktop needs a restart to connect to your server.")
        if yes("   Restart Claude Desktop now?"):
            if claude_control():
                OS.quit_claude()
                OS.open_claude(app)
    elif not claude_running() and (changed or first_run or inst.get("open_claude", True)) and claude_control():
        OS.open_claude(app)
    if changed:
        say("   Claude Desktop is connected to your server. In Claude, try: \"What's running on my WoP server?\"")


# --------------------------------------------------------------------------- shortcuts

def ensure_shortcuts(inst: dict, game: Path) -> None:
    if os.environ.get("WOP_SKIP_SHORTCUTS"):
        return
    try:
        _make_shortcuts(inst, game)
    except OSError as e:  # e.g. the Mac asked "allow access to Desktop?" and the answer was no
        say(f"   Couldn't put the shortcuts in the {SHORTCUT_FOLDER} folder on your desktop ({e.strerror or e}).")
        say(f"   Start the server later by running this kit again, or with {launcher_script()} start")


def _make_shortcuts(inst: dict, game: Path) -> None:
    """Desktop/World of PADMAN/ holds Play; its WOP-server/ subfolder holds Start, Stop, Help and Troubleshooting."""
    folder = desktop_dir() / SHORTCUT_FOLDER
    server_dir = folder / SERVER_SUBFOLDER
    server_dir.mkdir(parents=True, exist_ok=True)
    icon = game / OS.client_bin
    kit = launcher_script()
    web_links = {"WoP Server Help": f"https://github.com/{SETTINGS['repo']}#readme",
                 "WoP Server Troubleshooting": TROUBLESHOOTING_URL}
    made = OS.make_shortcuts(server_dir, [Shortcut("Start WoP Server", kit, ["start"], ROOT, icon),
                                          Shortcut("Stop WoP Server", kit, ["stop"], ROOT, icon)], web_links)
    made += OS.make_shortcuts(folder, [Shortcut("Play World of PADMAN", game / OS.client_bin, [], game, icon,
                                                app=True)], {})
    # older kits put the shortcuts loose on the desktop: remove those
    for old in set(inst.get("shortcuts", [])) - {str(p) for p in made}:
        Path(old).unlink(missing_ok=True)
    inst["shortcuts"] = [str(p) for p in made if p.exists() or p.is_symlink()]
    inst["shortcut_dirs"] = [str(server_dir), str(folder)]


def remove_shortcuts(inst: dict) -> None:
    for shortcut in inst.get("shortcuts", []):
        Path(shortcut).unlink(missing_ok=True)
    for folder in inst.get("shortcut_dirs", []):  # innermost first; anything the user put there stays
        try:
            Path(folder).rmdir()
        except OSError:
            pass


# --------------------------------------------------------------------------- joining

def join_addresses() -> list[tuple[str, str]]:
    """(address, connection name) the players can use, the one other devices should use first."""
    from wop.actions import Game
    preferred = Game.lan_addresses()
    found = OS.network_adapters()
    if not found:
        return [(ip, "") for ip in preferred[:1]]
    return sorted(found, key=lambda entry: bool(preferred) and entry[0] != preferred[0])


# --------------------------------------------------------------------------- commands

def cmd_banner(_args) -> None:
    from wop import config
    from wop.actions import Game
    inst = load_install()
    port = inst.get("port", SETTINGS["default_port"])
    ips = Game.lan_addresses()
    suffix = "" if port == 27960 else f":{port}"
    line = "=" * 74
    say(line)
    say(f'  World of PADMAN server "{config.server_name()}" is starting.')
    say("")
    say("  Players on your network: World of PADMAN -> Multiplayer -> LAN -> Join.")
    if ips:
        say(f"  Not in the list? Click SPECIFY there: address {ips[0]}, port {port}  (or /connect {ips[0]}{suffix})")
    friends = online.Online(OS)
    if friends.start_keeper():   # internet play is on: it follows this server
        details = friends.join_details()
        if details:
            say(f"  Friends somewhere else: SPECIFY address {details['address']}, port {details['port']}")
    say('  All the steps are in the "how to join" window that opened next to this one.')
    say("")
    say("  Want another map, game mode, bots or weapons? Just ask Claude, for example:")
    say('     "Switch to Capture The Lolly with 4 bots on each team"')
    say("")
    say("  Keep this window open while you play. Close it (or use Stop WoP Server) to stop.")
    say(line)


def cmd_joininfo(_args) -> None:
    """The "how to join" window that opens next to the server window, and stays."""
    from wop import config
    port = load_install().get("port", SETTINGS["default_port"])
    suffix = "" if port == 27960 else f":{port}"
    addresses = join_addresses()
    password = config.join_password()
    line = "=" * 74
    say(line)
    say(f'  How to join "{config.server_name()}"')
    say(line)
    say("  1. Everyone must be on the SAME network as this computer: the same Wi-Fi")
    say("     or router (a guest Wi-Fi doesn't work). Everyone needs World of")
    say(f"     PADMAN 1.7.0 (free): {SETTINGS['wop_download_page']}")
    say("")
    say("  2. In World of PADMAN: Multiplayer -> source LAN -> pick the server -> Join.")
    say("")
    if addresses:
        ip, name = addresses[0]
        say("  3. Not in the list? In the Multiplayer screen click SPECIFY and fill in:")
        say(f"         Address:  {ip:<16} {f'({name})' if name else ''}".rstrip())
        say(f"         Port:     {port}")
        say(f"     Or press ~ in the game and type:  /connect {ip}{suffix}")
        for ip, name in addresses[1:]:
            say(f"     Players on this computer's other network{f' ({name})' if name else ''} use address {ip}")
    else:
        say("  3. This computer doesn't seem to be connected to a network, so nobody else")
        say("     can join yet. Connect it to your Wi-Fi or router and start the server again.")
    details = online.Online(OS).join_details()
    if details:
        say("")
        say("  4. Friends somewhere else (another home): in the Multiplayer screen click")
        say("     SPECIFY and fill in:")
        say(f"         Address:  {details['address']}")
        say(f"         Port:     {details['port']}")
        say(f"     Or press ~ in the game and type:  {details['connect_command']}")
    if password:
        say("")
        say(f"  Join password: {password}  (players first type /password {password} in the console, ~)")
    say("")
    say("  The server runs in the other window. You can close this one;")
    say("  the server keeps running.")
    say(line)
    pause()


def prepare(inst: dict) -> Path:
    """Everything the server needs before it can start (the first time this downloads the game)."""
    inst.setdefault("port", int(os.environ.get("WOP_PORT") or SETTINGS["default_port"]))
    save_install(inst)
    game = ensure_game(inst)
    save_install(inst)
    ensure_server_files(inst, game)
    return game


def cmd_start(args) -> None:
    say("WoP Server Kit " + kit_version())
    if not args.no_update:
        maybe_update()
    inst = load_install()
    first_run = not inst
    if first_run:
        say("\nHi! This sets up a World of PADMAN server for the players on your network,")
        say("and connects it to Claude so you can change the game by just asking.")
    if not inst.get("server_name"):
        default = f"{getpass.getuser()}'s WoP server"
        inst["server_name"] = clean_name(ask("\nWhat should your server be called?", default)) or default

    game = prepare(inst)
    ensure_firewall(inst, game, inst["port"])
    ensure_rosetta()
    if ensure_mcp_ready():
        ensure_claude(inst, first_run)
    ensure_shortcuts(inst, game)
    inst["version"] = kit_version()
    save_install(inst)

    if server_running(inst["port"]):
        say("\nThe server is already running.")
        pause(8)
        return
    if first_run:
        say("\nAll set! From now on, start the server with \"Start WoP Server\" in the")
        say(f"{SHORTCUT_FOLDER} folder on your desktop (inside {SERVER_SUBFOLDER}).")
    say("\nStarting the server...\n")
    if os.environ.get("WOP_NO_SERVER"):
        return
    sys.exit(OS.run_script_here(run_server_script()))


def stop_server(port: int) -> bool:
    """Ask the server to quit. False if it wasn't running."""
    from wop.rcon import Rcon, ServerOffline
    if not server_running(port):
        return False
    try:
        Rcon(port=port).command("quit", timeout=1.0)
    except ServerOffline:
        pass
    return True


def cmd_stop(_args) -> None:
    if stop_server(load_install().get("port", SETTINGS["default_port"])):
        say("The WoP server is stopping.")
    else:
        say("The WoP server isn't running.")
    pause(3)


def uninstall(inst: dict) -> None:
    """Remove the server, its settings, the firewall permission, the AI connections and the shortcuts."""
    stop_server(inst.get("port", SETTINGS["default_port"]))
    online.Online(OS).forget()   # stops playing over the internet before the folder goes
    removal = [] if os.environ.get("WOP_SKIP_FIREWALL") else OS.firewall_removal(inst)
    if removal:
        say(f"Removing the firewall permission for the server. {OS.elevation_short}")
        OS.run_elevated(removal, terminal=UI.terminal)
    set_claude_entry(None)
    for app in ai_apps.APPS:
        if app.id != "claude-desktop" and app.available(OS):
            ai_apps.disconnect(app, OS, SETTINGS["mcp_name"])
    remove_shortcuts(inst)


def cmd_uninstall(_args) -> None:
    inst = load_install()
    say(f"This removes the WoP server, its settings and the {SHORTCUT_FOLDER} folder on your desktop.")
    if inst.get("game_reused"):
        say(f"(Your World of PADMAN game in {inst['game_dir']} stays.)")
    if _tty_input('Type "yes" to remove everything: ').strip().lower() != "yes":
        say("Nothing removed.")
        pause()
        return
    uninstall(inst)
    say("Removed. The WoP Server folder is deleted after this window closes.")
    OS.remove_folder_after_exit(ROOT)
    pause(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="WoP Server Kit")
    parser.add_argument("command", choices=["start", "stop", "banner", "joininfo", "uninstall"])
    parser.add_argument("--no-update", action="store_true")
    args = parser.parse_args()
    try:
        {"start": cmd_start, "stop": cmd_stop, "banner": cmd_banner, "joininfo": cmd_joininfo,
         "uninstall": cmd_uninstall}[args.command](args)
    except KeyboardInterrupt:
        say("\nStopped.")
    except SystemExit as e:
        if e.code not in (None, 0) and isinstance(e.code, str):
            say(e.code)
            pause()
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
