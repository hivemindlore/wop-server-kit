# World of PADMAN Server Kit

Host your own **World of PADMAN** game server for everyone on your home network, and change anything
about it (map, game mode, bots, weapons) by just **asking Claude**. No technical knowledge needed.

[World of PADMAN](https://worldofpadman.net) is a free, colorful cartoon shooter. This kit downloads the
game, sets up a server, and connects it to the Claude Desktop app. One file, a few clicks.

---

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
   - Windows asks "*Do you want to allow this app to make changes?*" → click **Yes**
     (this lets the players on your network connect, nothing from the internet);
   - "*Install Claude Desktop now?*" → press Enter for yes, then sign in to Claude when it opens.

The first time takes a while (the game is 1.2 GB). After that, your desktop has a **World of PADMAN** folder:

| In the folder | What it does |
|---------------|--------------|
| **Play World of PADMAN** | Play on this computer too |
| **WOP-server** → **Start WoP Server** | Starts the server (and installs updates of this kit) |
| **WOP-server** → **Stop WoP Server** | Stops it (closing the server window does the same) |
| **WOP-server** → **WoP Server Help** | Opens this page |

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
3. Answer the questions. If your Mac's firewall is on, it asks for your Mac password once, so the players on your
   network can connect. If Claude Desktop isn't installed, the download page opens: install it, then go back
   to Terminal and press Enter.

Your desktop then has a **World of PADMAN** folder with **Play World of PADMAN**, and a **WOP-server** folder inside
it with **Start WoP Server**, **Stop WoP Server** and **WoP Server Help**. Double-click them.

---

## How do the others join?

Everyone needs World of PADMAN 1.7.0 (free) from **https://worldofpadman.net/en/download/** and has to be on
the **same Wi-Fi / network** as the computer running the server.

1. Start World of PADMAN → **Multiplayer** → set the source to **LAN** → pick your server → **Join**.
2. Not in the list? Press **~** (the key under Esc) and type the `/connect …` line shown in the server window.

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

| Problem | Try this |
|---------|----------|
| Others can't see the server | Same Wi-Fi? (A *guest* Wi-Fi usually blocks this.) Use the `/connect …` line from the server window. Run **Start WoP Server** again and click **Yes** on the Windows permission box (Mac: type your password when asked). |
| Claude doesn't know the server | Fully quit Claude Desktop (right-click its icon by the clock → Quit, or ⌘Q on Mac) and open it again. Claude Desktop → Settings → Developer should list **wop-server**. |
| "The server isn't answering" in Claude | The server is off. Ask Claude to start it, or use **Start WoP Server**. |
| The server window shows an error | Close it and use **Start WoP Server** again. |

## Removing it

Windows: press **Windows + R**, paste this line, press Enter, and type `yes` when asked:
```
cmd /k "%LOCALAPPDATA%\WoPServer\wopkit.cmd" uninstall
```
Mac: paste this in Terminal and type `yes` when asked:
```
"$HOME/Library/Application Support/WoPServer/wopkit.sh" uninstall
```

This removes the server, its settings, the World of PADMAN desktop folder, the firewall rule and the Claude connection.
A World of PADMAN game you had installed yourself stays.

---

## For the maintainer

<details>
<summary>How the kit works, releasing updates, testing</summary>

- **Files:** `start-wop-server.bat` (Windows: a cmd/PowerShell file) and `start-wop-server.sh` (Mac) only fetch
  [uv](https://github.com/astral-sh/uv) (pinned version + SHA-256) and this repo's `kit/` folder, then run
  `kit/setup/wopkit.py`. That script (Python standard library only) does everything else: downloads the official
  WoP 1.7.0 zip from the PadWorld GitHub release (SHA-256 checked), writes the server config with a random rcon
  password, allows the server through the Windows Firewall / macOS application firewall, prepares and registers
  the MCP server (`kit/mcp`) in Claude Desktop, makes the desktop folder with the shortcuts and starts the server.
- **Install folder:** `%LOCALAPPDATA%\WoPServer` / `~/Library/Application Support/WoPServer`: `kit/` (replaced on
  update), `home/wop/` (the host's settings; never touched by updates), `game/`, `tools/uv`, `python/`, `cache/`.
- **Releasing an update:** change files under `kit/`, raise the number in `kit/VERSION`, push to `main`.
  Every host gets it the next time they use **Start WoP Server**.
- **Repo name:** `hivemindlore/wop-server-kit` appears in `kit/kit.json`, both start scripts and this README.
- **Tests:** `kit/mcp/tests` (MCP server, `pytest`), `kit/setup/test_wopkit.py` (setup helpers), and
  `kit/mcp/tests/integration.py` (every MCP tool against a real test server).
  For a "fresh friend" run on your own PC without touching your real setup, set these before running the .bat:
  `WOP_KIT_ROOT` (test folder), `WOP_KIT_URL` (a local zip of this repo), `WOP_PORT` (e.g. 27961),
  `WOP_CLAUDE_CONFIG` (a copy of the Claude config), `WOP_NO_CLAUDE_LAUNCH=1`, `WOP_DESKTOP` (test folder),
  optionally `WOP_SKIP_FIREWALL=1`, `WOP_GAME_ZIP` (an already downloaded WoP zip), `WOP_NO_SERVER=1`.
- **License:** World of PADMAN may be copied and shared for non-commercial use (see its `COPYING.md`); the kit
  downloads it from the official release instead of re-hosting it.

</details>
