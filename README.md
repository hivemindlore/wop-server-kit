# World of PADMAN Server Kit

Host your own **World of PADMAN** game server for everyone on your home network, and change anything
about it (map, game mode, bots, weapons) by just **asking Claude**. No technical knowledge needed.

[World of PADMAN](https://worldofpadman.net) is a free, colorful cartoon shooter. This kit downloads the
game, sets up a server, and connects it to the Claude Desktop app. One file, a few clicks.

---

## The WoP Server app (Windows, Mac, Linux)

The easiest way: one app that sets everything up and lets you run your server with a few clicks.

1. **Download** the app for your computer from the
   [latest release](https://github.com/hivemindlore/wop-server-kit/releases/latest):
   **Windows** `WoP-Server-Setup-….exe` · **Mac** `WoP-Server-….dmg` (`arm64` for M1/M2/M3/M4, `x64` for Intel) ·
   **Linux** `WoP-Server-….AppImage` (or the `.deb`).
2. **Open it.** The first time, it asks for a name for your server and downloads World of PADMAN (1.2 GB).
   - Windows may say "*Windows protected your PC*": click **More info** → **Run anyway**.
   - Mac may say the app "*can't be opened*": right-click the app → **Open** → **Open**.
   - Linux: right-click the `.AppImage` → Properties → allow it to run as a program, then double-click it.
3. **That's it.** The app has four tabs:

| Tab | What you do there |
|-----|-------------------|
| **Server** | Turn the server on and off, see who's playing, how others join (address and port to copy), and whether other computers on your network can find it (with a **Fix it** button if not). Rename the server or set a join password. |
| **Logs** | Everything the server says, live, with a search box. |
| **Commands** | Give the server commands, with quick buttons for the common ones (send a message, restart the match). |
| **AI** | Connect an AI with one click: Claude Desktop, LM Studio (free, runs on your own computer), and more. Then just ask it to change the game. |

The server runs in the background: closing the app doesn't stop it. Open the app again to see it or turn it off.
The app and the files below install the same server, so you can switch between them.

## Without the app

You can also set up the server with a single file and run it from desktop shortcuts. The server then shows in its
own window.

## Windows (10 or 11)

**You need:** internet, about 3 GB of free disk space, and a (free) [Claude account](https://claude.ai) if you
want Claude to manage the server.

1. **Download** the file: open [start-wop-server.bat](https://github.com/hivemindlore/wop-server-kit/blob/main/start-wop-server.bat)
   and click the **download button** (the arrow ↓ at the top right of the file).
   If your browser warns that the file "isn't commonly downloaded", choose **Keep**.
2. **Double-click** `start-wop-server.bat`.
   If Windows shows a blue box "*Windows protected your PC*": click **More info** → **Run anyway**.
   (The file is a plain script; you can open it in Notepad to see what it does.)
3. **Answer the questions** in the black window:
   - a name for your server (or just press Enter);
   - "*Do you want to allow this?*" (so the players on your network can join) → press Enter for yes. Windows then
     asks "*Do you want to allow this app to make changes?*" → click **Yes**
     (this lets the players on your network connect, nothing from the internet);
   - "*Install Claude Desktop now?*" → press Enter for yes, then sign in to Claude when it opens.

The first time takes a while (the game is 1.2 GB). After that, your desktop has a **World of PADMAN** folder:

| In the folder | What it does |
|---------------|--------------|
| **Play World of PADMAN** | Play on this computer too |
| **WOP-server** → **Start WoP Server** | Starts the server (and installs updates of this kit) |
| **WOP-server** → **Stop WoP Server** | Stops it (closing the server window does the same) |
| **WOP-server** → **WoP Server Help** | Opens this page |
| **WOP-server** → **WoP Server Troubleshooting** | Commands to check the server, network and firewall, and fixes |

<details>
<summary>Can't download or run the .bat file? Use this instead</summary>

Press the Windows key, type **PowerShell**, open it, paste this line and press Enter:
```
irm https://raw.githubusercontent.com/hivemindlore/wop-server-kit/main/start-wop-server.bat | iex
```
</details>

## Mac (beta)

> The Mac version hasn't been tested on a real Mac yet.

**You need:** macOS 11 or newer, internet, about 3 GB of free disk space. World of PADMAN is made for Intel
Macs; on an Apple-silicon Mac (M1/M2/M3/M4) the kit installs Apple's free *Rosetta* (it asks for your Mac password).

1. Open **Terminal** (press ⌘ Space, type *Terminal*, press Enter).
2. Paste this line and press Enter:
   ```
   curl -fsSL https://raw.githubusercontent.com/hivemindlore/wop-server-kit/main/start-wop-server.sh | bash
   ```
3. Answer the questions. If your Mac's firewall is on, it asks "*Do you want to allow this?*" and then your Mac
   password, so the players on your network can connect. If Claude Desktop isn't installed, the download page opens: install it, then go back
   to Terminal and press Enter.

Your desktop then has a **World of PADMAN** folder with **Play World of PADMAN**, and a **WOP-server** folder inside
it with **Start WoP Server**, **Stop WoP Server**, **WoP Server Help** and **WoP Server Troubleshooting**.
Double-click them.

## Linux (beta)

> The Linux version hasn't been tested on every distribution yet.

**You need:** a 64-bit Linux desktop (Ubuntu, Fedora, Mint, …), internet, about 3 GB of free disk space.

1. Open a **Terminal**.
2. Paste this line and press Enter:
   ```
   curl -fsSL https://raw.githubusercontent.com/hivemindlore/wop-server-kit/main/start-wop-server.sh | bash
   ```
3. Answer the questions. If your firewall (ufw or firewalld) is on, it asks "*Do you want to allow this?*" and then
   your password, so the players on your network can connect.

Your desktop then has the same **World of PADMAN** folder as on Windows and Mac. Claude Desktop isn't available
for Linux; use the app's **AI** tab to connect another AI app (for example LM Studio).

---

## How do the others join?

Everyone needs World of PADMAN 1.7.0 (free) from **https://worldofpadman.net/en/download/** and has to be on
the **same Wi-Fi / network** as the computer running the server.

1. Start World of PADMAN → **Multiplayer** → set the source to **LAN** → pick your server → **Join**.
2. Not in the list? Click **Specify** in the Multiplayer screen and enter the **address** and **port** shown in
   the *How to join* window, which opens next to the server window. Or press **~** (the key under Esc) and type
   the `/connect …` line from that window.

Or ask Claude: *"How do my friends join?"*

## Changing the game: ask Claude

Open Claude Desktop and just ask, for example:

- *"What's running on my WoP server?"*
- *"Switch to Capture The Lolly with 4 bots on each team."*
- *"Put FatPad and FATTY on the blue team and make the bots harder."*
- *"Play on the kitchen map with InstaPad."* (one hit kills)
- *"Start the server"* · *"Rename the server to Bro Night"* · *"Set a join password"*
- *"Keep this setup when the server starts next time."*

Claude knows all 11 game modes, 46 maps and 29 bots, so you don't need to know any names.
The full list is in [gamemodes.md](kit/docs/gamemodes.md).

## Something doesn't work?

Every **Start WoP Server** checks whether the other computers on your network can join (the firewall and the
network). If something blocks them, it tells you what and asks *"Do you want to allow this?"*.

| Problem | Try this |
|---------|----------|
| Others can't see the server | Same Wi-Fi? (A *guest* Wi-Fi usually blocks this.) Click **Specify** in the game's Multiplayer screen and enter the address and port from the *How to join* window. Run **Start WoP Server** again, answer yes and click **Yes** on the Windows permission box (Mac: type your password when asked). |
| Claude doesn't know the server | Fully quit Claude Desktop (right-click its icon by the clock → Quit, or ⌘Q on Mac) and open it again. Claude Desktop → Settings → Developer should list **wop-server**. |
| "The server isn't answering" in Claude | The server is off. Ask Claude to start it, or use **Start WoP Server**. |
| The server window shows an error | Close it and use **Start WoP Server** again. |

Still stuck? The [troubleshooting guide](kit/docs/troubleshooting.md) has commands to see your server, settings,
network and firewall, a quick check that tests everything at once, and fixes for common problems.

## Removing it

Windows: press **Windows + R**, paste this line, press Enter, and type `yes` when asked:
```
cmd /k "%LOCALAPPDATA%\WoPServer\wopkit.cmd" uninstall
```
Mac: paste this in Terminal and type `yes` when asked:
```
"$HOME/Library/Application Support/WoPServer/wopkit.sh" uninstall
```
Linux: paste this in Terminal and type `yes` when asked:
```
"${XDG_DATA_HOME:-$HOME/.local/share}/WoPServer/wopkit.sh" uninstall
```

This removes the server, its settings, the World of PADMAN desktop folder, the firewall rule and the AI connections.
If you use the app, remove the app itself the usual way afterwards.
A World of PADMAN game you had installed yourself stays.

---

## For the maintainer

<details>
<summary>How the kit works, releasing updates, testing</summary>

- **Files:** `start-wop-server.bat` (Windows: a cmd/PowerShell file) and `start-wop-server.sh` (Mac, Linux) only fetch
  [uv](https://github.com/astral-sh/uv) (pinned version + SHA-256) and this repo's `kit/` folder, then run
  `kit/setup/wopkit.py`. That script (Python standard library only) does everything else: downloads the official
  WoP 1.7.0 zip from the PadWorld GitHub release (SHA-256 checked), writes the server config with a random rcon
  password, checks on every start that the firewall (Windows Firewall / macOS application firewall / ufw or
  firewalld) lets the players in (and offers to fix it), prepares and registers
  the MCP server (`kit/mcp`) in Claude Desktop, makes the desktop folder with the shortcuts and starts the server.
- **One OS behavior per platform (Strategy pattern):** everything that differs between Windows, Mac and Linux
  (paths, firewall, elevation, shortcuts, starting the server, Claude Desktop) lives in `kit/mcp/wop/platforms/`
  (`WindowsBehavior`, `MacBehavior`, `LinuxBehavior`, picked once by `detect()` and passed in). The app does the same
  for its few OS differences in `app/src/main/platform/`. No other code checks the OS.
- **The app** (`app/`, Electron + React + TypeScript, MVVM): views (`src/renderer/views`) only draw;
  view models (`src/renderer/viewmodels`) turn model state into what's shown; the model is the main process
  (`src/main/models`) plus the kit itself, reached through `kit/setup/appbridge.py` (JSON lines over stdin/stdout,
  run with the kit's uv). The app ships a copy of `kit/` and uv, and installs them into the same folder the
  start scripts use (only if its kit is newer). With the app, the server runs without a window
  (`hidden_server` in `install.json`, also used by the Claude connection) and its log shows in the Logs tab.
  Try it without touching your real setup (Node.js 22.12+): `cd app && npm install && npm run sandbox`. That runs
  the app on `app/.sandbox` (port 27961, your installed game reused read-only, Claude Desktop settings and
  shortcuts kept in the sandbox) with the repo's current `kit/`; `npm run sandbox -- --fresh` starts with the full
  first-time setup instead. `npm run dev` runs it on the real install. Tests: `npm test`, `npm run typecheck`.
  Release: tag `app-vX.Y.Z` and push; `.github/workflows/app.yml` builds the installers into a GitHub release.
  The installers aren't code-signed yet (Windows SmartScreen and macOS Gatekeeper warn the first time).
- **Install folder:** `%LOCALAPPDATA%\WoPServer` / `~/Library/Application Support/WoPServer` /
  `~/.local/share/WoPServer`: `kit/` (replaced on update), `home/wop/` (the host's settings; never touched by
  updates), `game/`, `tools/uv`, `python/`, `cache/`.
- **Releasing an update:** change files under `kit/`, raise the number in `kit/VERSION`, push to `main`.
  Every host gets it the next time they use **Start WoP Server**.
- **Repo name:** `hivemindlore/wop-server-kit` appears in `kit/kit.json`, both start scripts and this README.
- **Tests:** `kit/mcp/tests` (MCP server, `pytest`), `kit/setup/test_*.py` (setup helpers, OS behaviors, AI app
  connections, the app bridge), `kit/mcp/tests/integration.py` (every MCP tool against a real test server) and
  `app` (`npm test`). CI runs them all on Windows, Mac and Linux.
  For a "fresh friend" run on your own PC without touching your real setup, set these before running the .bat:
  `WOP_KIT_ROOT` (test folder), `WOP_KIT_URL` (a local zip of this repo), `WOP_PORT` (e.g. 27961),
  `WOP_CLAUDE_CONFIG` (a copy of the Claude config), `WOP_NO_CLAUDE_LAUNCH=1`, `WOP_DESKTOP` (test folder),
  optionally `WOP_SKIP_FIREWALL=1`, `WOP_GAME_ZIP` (an already downloaded WoP zip), `WOP_NO_SERVER=1`.
- **License:** World of PADMAN may be copied and shared for non-commercial use (see its `COPYING.md`); the kit
  downloads it from the official release instead of re-hosting it.

</details>
