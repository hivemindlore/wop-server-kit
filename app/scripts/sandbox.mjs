// Runs the app against a test folder (app/.sandbox) instead of the real WoP Server install, so trying the app
// never changes the server you play on, its settings or your Claude Desktop setup.
//
//   npm run sandbox             uses the World of PADMAN you already installed (no download), port 27961
//   npm run sandbox -- --fresh  starts from nothing: the full first-time setup, including the 1.2 GB download
//   Other options go to electron-vite, e.g.  npm run sandbox -- --remoteDebuggingPort 9229
//
// Stop a sandbox server that's still running without the app:  app\.sandbox\wopkit.cmd stop  (Mac/Linux: wopkit.sh)
// Start over: close the app and delete app/.sandbox.

import { spawn, spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const [major, minor] = process.versions.node.split('.').map(Number)
if (major < 22 || (major === 22 && minor < 12)) {
  console.error(`The app's build tools (Electron, Vite) need Node.js 22.12 or newer; this is ${process.version}.`)
  console.error('Install the current LTS from https://nodejs.org (Windows: winget install OpenJS.NodeJS.LTS),')
  console.error('then run "npm install" in the app folder once more, and "npm run sandbox".')
  process.exit(1)
}

const PORT = 27961  // next to a real server on 27960, and still in the game's LAN list
const app = join(dirname(fileURLToPath(import.meta.url)), '..')
const sandbox = join(app, '.sandbox')
const fresh = process.argv.includes('--fresh')

// Where the start scripts install the real kit, and its server program, per OS
const REAL_INSTALL = {
  win32: () => [join(process.env.LOCALAPPDATA ?? join(homedir(), 'AppData', 'Local'), 'WoPServer'), 'wopded.x86_64.exe'],
  darwin: () => [join(homedir(), 'Library', 'Application Support', 'WoPServer'),
    join('wopded.x86_64.app', 'Contents', 'MacOS', 'wopded.x86_64')],
  linux: () => [join(process.env.XDG_DATA_HOME || join(homedir(), '.local', 'share'), 'WoPServer'), 'wopded.x86_64']
}

function run(args) {
  const result = spawnSync(process.execPath, args, { cwd: app, stdio: 'inherit' })
  if (result.status !== 0) process.exit(result.status ?? 1)
}

if (fresh) rmSync(sandbox, { recursive: true, force: true })
mkdirSync(join(sandbox, 'desktop'), { recursive: true })

// "Connect Claude Desktop" writes here instead of the real Claude settings
const claudeConfig = join(sandbox, 'claude_desktop_config.json')
if (!existsSync(claudeConfig)) writeFileSync(claudeConfig, '{}\n')

const installJson = join(sandbox, 'install.json')
if (!fresh && !existsSync(installJson)) {
  const [realRoot, serverBin] = REAL_INSTALL[process.platform]?.() ?? []
  const game = realRoot && join(realRoot, 'game')
  if (game && existsSync(join(game, serverBin))) {
    // game_reused: the sandbox only reads that game folder and never deletes it
    writeFileSync(installJson, JSON.stringify({ port: PORT, server_name: 'Sandbox server', game_dir: game,
      game_reused: true }, null, 2))
    console.log(`Sandbox uses the game in ${game}`)
  } else {
    console.log('No installed World of PADMAN found, so the sandbox starts with the full first-time setup.')
  }
}

// npm install doesn't always fetch Electron itself
if (!existsSync(join(app, 'node_modules', 'electron', 'path.txt'))) {
  console.log('Downloading Electron...')
  run([join('node_modules', 'electron', 'install.js')])
}
run([join('scripts', 'prepare-resources.mjs')])
// The app only replaces a kit with a newer version number; here the repo's kit always wins, so changes show up
rmSync(join(sandbox, 'kit'), { recursive: true, force: true })
cpSync(join(app, 'resources', 'kit'), join(sandbox, 'kit'), { recursive: true })

console.log(`Starting the app with the test folder ${sandbox}`)
const child = spawn(process.execPath, [join('node_modules', 'electron-vite', 'bin', 'electron-vite.js'), 'dev',
  ...process.argv.slice(2).filter((arg) => arg !== '--fresh')], {
  cwd: app,
  stdio: 'inherit',
  env: {
    ...process.env,
    WOP_KIT_ROOT: sandbox,
    WOP_PORT: String(PORT),
    WOP_CLAUDE_CONFIG: claudeConfig,
    WOP_DESKTOP: join(sandbox, 'desktop'),
    WOP_NO_CLAUDE_LAUNCH: '1'
  }
})
child.on('exit', (code) => process.exit(code ?? 0))
