# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Check the World of Padman official server docs here:
https://worldofpadman.net/en/tutorials/create-a-dedicated-wop-server/

## What this is

Important: the app is built for none-technical people so they can easily setup and manage a server without knowing anything technical. the goal is to make it as eadsy as possible to use, hiding all complexity behind the scenes and making everything work with simple toggles and buttons.

A kit that installs and runs a World of PADMAN (Quake 3 engine) game server on a home network and lets Claude
(or another AI app) manage it. Three layers:

- **`start-wop-server.bat` / `.sh`**: bootstrap only. They fetch a pinned uv (SHA-256 checked) and this repo's
  `kit/`, then run `kit/setup/wopkit.py`.
- **`kit/`** (Python): everything real. `kit/setup/wopkit.py` (standard library only) does the install, firewall
  checks, config, shortcuts, Claude Desktop registration and starting the server. `kit/mcp/` is the MCP server
  (`server.py`, run as a uv inline-script with `mcp==2.3.0`) built on the `wop` package.
- **`app/`** (Electron + React + TypeScript): the desktop app. It ships a copy of `kit/` and uv and installs them
  into the same folder the start scripts use, so both routes share one install.

The audience is non-technical. Every user-visible string (app UI, console messages, README user sections, MCP
tool results) must avoid jargon such as MCP, rcon, cvar, UDP, JSON, stdio. Maintainer docs may be technical.

## Commands

Kit tests (from the repo root; this is what CI runs on Windows, Mac and Linux):
```
cd kit/mcp && uv run --no-project --with pytest --with "mcp==2.3.0" python -m pytest tests -q
cd kit/setup && uv run --no-project --with pytest python -m pytest -q
```
Single test: append e.g. `tests/test_actions.py::test_name` (mcp) or `test_wopkit.py -k name` (setup).

End-to-end against a real *test* install (never a real server):
`cd kit/mcp && uv run --no-project --with "mcp==2.3.0" python tests/integration.py <test install folder>`.

App (`cd app`, Node.js 22.12+):
```
npm install
npm test                      # vitest; single file: npx vitest run src/main/models/models.test.ts, or -t "name"
npm run typecheck
npm run build
npm run sandbox               # runs the app on app/.sandbox (port 27961), reusing the installed game read-only
npm run sandbox -- --fresh    # full first-time setup in the sandbox, including the 1.2 GB download
npm run dev                   # runs on the REAL install; prefer sandbox
```
`npm run resources` (also run by `dev`/`dist`) copies `../kit` and uv into `app/resources`; rerun it after kit changes
when not using the sandbox.

Rebuild the patched server game code (reproducible; CI `qagame.yml` checks it against `kit/kit.json`):
`docker run --rm -v "$PWD:/kit" -w /kit ubuntu:24.04 bash kit/server/game/build-qvm.sh`

## Architecture

### OS differences: Strategy pattern only
Everything that differs per OS lives in one behavior class per platform, picked once and injected:
- Python: `kit/mcp/wop/platforms/` (`base.py` interface; `WindowsBehavior`, `MacBehavior`, `LinuxBehavior`,
  with shared POSIX code in `posix.py`); `detect()` / `for_name()` in `__init__.py`.
- TypeScript: `app/src/main/platform/` (`PlatformBehavior.ts`, `behaviors.ts`; `detectBehavior()` in `main/index.ts`).

No other code checks the OS. Add new OS-dependent behavior as a method on these classes, never as an
`if windows` branch.

### Talking to the game server (`kit/mcp/wop/`)
- `rcon.py` talks to the server on 127.0.0.1. Port and the per-install random password come from the install's
  run-server script and `home/wop/server-friends.cfg` (`config.py` locates them through `WOP_HOME` /
  `WOP_START_SCRIPT` env vars, which the kit sets).
- The server rate-limits rcon after a short burst, so `actions.py` writes multi-step changes to
  `home/wop/mcp-batch.cfg`, runs a single `exec`, and reads the result from `home/wop/qconsole.log`
  (the kit always starts the server with `logfile 2`). Keep changes batched like this.
- `catalog.py` mirrors `kit/docs/gamemodes.md` (modes, maps, bots, default lineups) by hand. Update both together.
- `save_as_startup` (`config_files.py`) rewrites the install's `home/wop/teams.cfg` and only the marked block in
  `server-friends.cfg`, keeping `.bak` copies; templates of both are in `kit/server/`.
- Bots moved between teams are removed and re-added, because `forceteam` doesn't survive a map restart.

### The app (strict MVVM)
- **Views** (`src/renderer/views`) only render and call view-model methods; they never touch `window.wop`.
- **View models** (`src/renderer/viewmodels`, base class `ViewModel.ts`) mirror model states and shape display state.
- **Models** are the main process (`src/main/models`, mostly `StateModel` subclasses whose state is pushed over IPC) plus the kit.
  No business logic in the renderer; game/network/setup rules belong in the kit, not in TypeScript.
- `src/shared/api.ts` is the contract: data shapes from the bridge, model states, and the commands each model
  exposes. `src/main/ipc.ts` has an `ALLOWED` whitelist per model; a new command must be added to both.
- The models reach the kit through `kit/setup/appbridge.py`: a long-lived process (started by `BridgeClient.ts`
  with the kit's uv) speaking JSON lines on stdin/stdout. Requests carry an `id` and get `result`/`error`;
  events (log lines, setup progress) are pushed without an id. `appbridge.py` replaces `wopkit.UI` so prompts
  become app dialogs. Error messages from the bridge are already user-worded and shown as-is.
- With the app, the server runs windowless (`hidden_server` in `install.json`, started via `wop/launcher.py`);
  otherwise it opens in its own console window. Either way it outlives the app and Claude.
- Tests use `src/test/fakes.ts` (`FakeBridge` answers like `appbridge.py`); Python tests use a `FakeRcon` in
  `kit/mcp/tests/conftest.py` with captured real server output. `kit/setup/conftest.py` puts `kit/mcp` on `sys.path`.

### Playing over the internet (playit.gg)
`kit/mcp/wop/online.py` holds all of it (the app and Claude only call `enable` / `advance` / `disable` / `status`):
the one-time approval on playit.gg (claim code → key in `home/playit/playit.toml`), the address from playit's API,
and `home/playit/online.json` (on/off, address; not install.json, to avoid write races with the setup). The
playitd binary is pinned in `kit.json` "playit" and downloaded into `tools/playit-<version>`. `online_keeper.py` is a
detached process (one per install, lock file) that runs playitd while the server runs and stops itself when the
setting is off or the server stops answering; every start path (`Game.start_server`, `wopkit.cmd_banner`) calls
`Online.start_keeper()`. Mac has no playit build: `playit_asset` is None and the app hides the switch.
Tunneled players arrive from 127.0.0.1 and share the server's per-address rcon budget with the kit.

### App updates
`app/src/main/models/UpdateModel.ts` reads GitHub's latest *published* release (`app-vX.Y.Z`), picks the asset via
`PlatformBehavior.updateAssetName` (names must match `electron-builder.yml` `artifactName`), verifies the asset's
GitHub `digest`, then `installUpdate` (per OS). Network helpers are in `app/src/main/downloads.ts`.

### Install folder and updates
`%LOCALAPPDATA%\WoPServer` / `~/Library/Application Support/WoPServer` / `~/.local/share/WoPServer` holds `kit/`
(replaced on update), `home/wop/` (host settings, never touched by updates), `game/`, `tools/uv`, `python/`, `cache/`.
Hosts auto-update from GitHub `main` when they start the server, gated by `kit/VERSION`; the app only installs its
bundled kit if it is newer.

### Spawn-protection game code
`kit/server/vm/qagame.qvm` is WoP 1.7.0's server code plus `kit/server/game/spawn-protect.patch` (adds
`g_spawnProtect`). `ensure_game_module` in `wopkit.py` installs it to `home/wop/vm/` only while the game is 1.7.0.
If you change the patch, rebuild the qvm and update `patched_qagame_sha256` in `kit/kit.json`.

## Testing without touching a real setup
Env vars for a "fresh friend" run of the start scripts: `WOP_KIT_ROOT`, `WOP_KIT_URL` (local zip of the repo),
`WOP_PORT` (e.g. 27961), `WOP_CLAUDE_CONFIG`, `WOP_NO_CLAUDE_LAUNCH=1`, `WOP_DESKTOP`, and optionally
`WOP_SKIP_FIREWALL=1`, `WOP_GAME_ZIP`, `WOP_NO_SERVER=1`. Never start, stop or reconfigure the real server on port
27960 while developing.

## Releasing
- Kit: change `kit/`, bump `kit/VERSION`, push to `main` (hosts pick it up on next start). Each version is developed
  on its own branch, `feature/version-X.Y.Z`.
- App: bump `app/package.json` version, tag `app-vX.Y.Z` and push; `.github/workflows/app.yml` builds unsigned
  installers into a draft GitHub release. Publishing the draft offers the update to every installed app.
- The repo name `hivemindlore/wop-server-kit` is hard-coded in `kit/kit.json`, both start scripts and the README.
- Pinned versions with checksums (uv 0.9.2 in the start scripts, `app/scripts/prepare-resources.mjs` and CI; the
  WoP zip and playit 1.0.10 in `kit/kit.json`) must be changed together. A new playit version also changes the
  `version` sent in `/claim/setup`.
