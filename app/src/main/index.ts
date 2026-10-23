import { join } from 'node:path'
import { readFileSync, writeFileSync } from 'node:fs'
import { app, BrowserWindow, dialog, shell } from 'electron'
import { BridgeClient } from './bridge/BridgeClient'
import { downloadFile, fetchJson, sha256File } from './downloads'
import { registerIpc, type Models } from './ipc'
import { KitInstaller } from './kitInstall'
import { AiModel } from './models/AiModel'
import { AppModel } from './models/AppModel'
import { CommandModel } from './models/CommandModel'
import { LogModel } from './models/LogModel'
import { NetworkModel } from './models/NetworkModel'
import { ServerModel } from './models/ServerModel'
import { UpdateModel, type Release } from './models/UpdateModel'
import { detectBehavior } from './platform/behaviors'

let window: BrowserWindow | null = null

function resourcesDir(): string {
  return app.isPackaged ? process.resourcesPath : join(__dirname, '..', '..', 'resources')
}

/** Where the app's releases are (the same repo the kit updates itself from). */
function releaseRepo(): string {
  try {
    return JSON.parse(readFileSync(join(resourcesDir(), 'kit', 'kit.json'), 'utf8')).repo
  } catch {
    return 'hivemindlore/wop-server-kit'
  }
}

/** Shows "the server keeps running" the first time the window closes while the server is on. */
function noteOnce(key: string): boolean {
  const file = join(app.getPath('userData'), 'notes.json')
  let seen: Record<string, boolean> = {}
  try {
    seen = JSON.parse(readFileSync(file, 'utf8'))
  } catch {
    // first time
  }
  if (seen[key]) return false
  seen[key] = true
  try {
    writeFileSync(file, JSON.stringify(seen))
  } catch {
    // not worth bothering the user about
  }
  return true
}

function openWindow(models: Models): BrowserWindow {
  const win = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 820,
    minHeight: 600,
    title: 'WoP Server',
    backgroundColor: '#f6f4ef',
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  win.once('ready-to-show', () => win.show())
  // Links open in the browser, never inside the app
  win.webContents.setWindowOpenHandler(({ url }) => {
    void models.app.openUrl(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (event, url) => {
    if (url !== win.webContents.getURL()) {
      event.preventDefault()
      void models.app.openUrl(url)
    }
  })
  win.on('close', () => {
    if (models.server.getState().status?.running && noteOnce('server-keeps-running')) {
      dialog.showMessageBoxSync(win, {
        type: 'info',
        title: 'WoP Server',
        message: 'Your server keeps running.',
        detail: 'Players can keep playing. Open WoP Server again to see what\'s happening or to stop it.'
      })
    }
  })
  if (process.env.ELECTRON_RENDERER_URL) void win.loadURL(process.env.ELECTRON_RENDERER_URL)
  else void win.loadFile(join(__dirname, '..', 'renderer', 'index.html'))
  return win
}

function main(): void {
  if (!app.requestSingleInstanceLock()) {
    app.quit()
    return
  }

  const behavior = detectBehavior()
  const installer = new KitInstaller(behavior, resourcesDir())
  const bridge = new BridgeClient(installer.paths())
  const models: Models = {
    app: new AppModel({
      bridge,
      prepareKit: () => installer.ensure(),
      openExternal: (url) => shell.openExternal(url)
    }),
    update: new UpdateModel({
      current: app.getVersion(),
      repo: releaseRepo(),
      behavior,
      folder: join(app.getPath('userData'), 'updates'),
      fetchRelease: (url) => fetchJson<Release>(url),
      download: downloadFile,
      sha256: sha256File,
      checkKit: () => models.app.checkKitUpdate(),
      quit: (relaunch) => {
        if (relaunch) app.relaunch()
        app.quit()
      },
      reveal: (file) => shell.showItemInFolder(file)
    }),
    server: new ServerModel(bridge),
    network: new NetworkModel(bridge),
    commands: new CommandModel(bridge),
    ai: new AiModel(bridge),
    logs: new LogModel(bridge)
  }

  // Once the kit is set up, the other models start
  let active = false
  models.app.subscribe((state) => {
    if (state.phase === 'ready' && !active) {
      active = true
      models.server.activate()
      void models.network.check()
      void models.ai.refresh()
      void models.update.check(true)
    }
  })

  registerIpc(models, () => window?.webContents ?? null)

  app.on('second-instance', () => {
    if (window?.isMinimized()) window.restore()
    window?.focus()
  })
  app.on('window-all-closed', () => {
    // The game server keeps running on its own; only the app's helper stops
    models.server.deactivate()
    bridge.stop()
    app.quit()
  })

  void app.whenReady().then(() => {
    window = openWindow(models)
    window.on('closed', () => (window = null))
    void models.app.boot()
  })
}

main()
