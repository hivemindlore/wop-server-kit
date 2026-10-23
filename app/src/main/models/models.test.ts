import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BRIDGE_PROTOCOL, type Hello } from '@shared/api'
import { FakeBridge, settle } from '../../test/fakes'
import { AiModel } from './AiModel'
import { AppModel } from './AppModel'
import { CommandModel } from './CommandModel'
import { GameModel } from './GameModel'
import { LogModel, MAX_LINES } from './LogModel'
import { NetworkModel } from './NetworkModel'
import {
  ONLINE_POLL_MS, ONLINE_REFRESH_POLLS, ONLINE_WAIT_MS, PLAY_GRACE_MS, POLL_MS, ServerModel
} from './ServerModel'
import { UpdateModel, appVersionOf, type Release, type UpdateDeps } from './UpdateModel'

const hello = (patch: Partial<Hello> = {}): Hello => ({
  protocol: BRIDGE_PROTOCOL,
  kit_version: '2.0.0',
  platform: 'windows',
  installed: true,
  server_name: 'Kim\'s server',
  default_server_name: 'kim\'s WoP server',
  port: 27960,
  root: 'C:/WoPServer',
  ...patch
})

function appModel(bridge: FakeBridge, prepareKit = async () => {}) {
  return new AppModel({ bridge, prepareKit, openExternal: vi.fn(async () => {}), delay: async () => {} })
}

afterEach(() => vi.useRealTimers())

describe('AppModel', () => {
  it('is ready when the kit is installed, and looks for kit updates', async () => {
    const bridge = new FakeBridge({ hello: () => hello(), 'kit.check_update': () => ({ available: true, version: '2.1.0' }) })
    const model = appModel(bridge)
    await model.boot()
    await settle()
    expect(bridge.started).toBe(1)
    expect(model.getState().phase).toBe('ready')
    expect(model.getState().update).toEqual({ available: true, version: '2.1.0', busy: false })
  })

  it('asks for the setup on a fresh computer, and shows its progress', async () => {
    let installed = false
    const bridge = new FakeBridge({
      hello: () => hello({ installed }),
      'setup.start': () => {
        bridge.emit('event', 'setup.step', { text: 'Downloading World of PADMAN' })
        bridge.emit('event', 'setup.progress', { percent: 40 })
        expect(model.getState().setup).toMatchObject({ step: 'Downloading World of PADMAN', percent: 40 })
        installed = true
        return { installed: true }
      }
    })
    const model = appModel(bridge)
    await model.boot()
    expect(model.getState().phase).toBe('needs-setup')
    await model.startSetup('  Bro night ')
    expect(bridge.calls.find((c) => c.method === 'setup.start')?.params).toEqual({ server_name: 'Bro night' })
    expect(model.getState().phase).toBe('ready')
  })

  it('goes back to the setup with the reason when it fails', async () => {
    const bridge = new FakeBridge({
      hello: () => hello({ installed: false }),
      'setup.start': () => {
        throw new Error('Not enough disk space: 1.0 GB free, about 3 GB needed.')
      }
    })
    const model = appModel(bridge)
    await model.boot()
    await model.startSetup('x')
    expect(model.getState().phase).toBe('needs-setup')
    expect(model.getState().setup.error).toContain('disk space')
  })

  it('refuses a kit that speaks another protocol', async () => {
    const model = appModel(new FakeBridge({ hello: () => hello({ protocol: 99 }) }))
    await model.boot()
    expect(model.getState().phase).toBe('error')
    expect(model.getState().error).toContain('newest app')
  })

  it('shows a problem when the kit can\'t be put in place', async () => {
    const model = appModel(new FakeBridge(), async () => {
      throw new Error('disk full')
    })
    await model.boot()
    expect(model.getState()).toMatchObject({ phase: 'error', error: 'disk full' })
  })

  it('restarts the kit after it stopped unexpectedly', async () => {
    const bridge = new FakeBridge({ hello: () => hello(), 'kit.check_update': () => ({ available: false }) })
    const model = appModel(bridge)
    await model.boot()
    bridge.emit('exit', 1)
    await settle()
    expect(bridge.started).toBe(2)
    expect(model.getState().phase).toBe('ready')
  })

  it('updates the kit and restarts it', async () => {
    const bridge = new FakeBridge({
      hello: () => hello(),
      'kit.check_update': () => ({ available: true, version: '2.1.0' }),
      'kit.update': () => ({ updated: true, version: '2.1.0' })
    })
    const model = appModel(bridge)
    await model.boot()
    await settle()
    await model.updateKit()
    expect(bridge.stopped).toBe(1)
    expect(bridge.started).toBe(2)
    expect(model.getState().update).toEqual({ available: false, version: '2.1.0', busy: false })
  })

  it('only opens web links', async () => {
    const openExternal = vi.fn(async () => {})
    const model = new AppModel({ bridge: new FakeBridge(), prepareKit: async () => {}, openExternal })
    await model.openUrl('file:///C:/Windows/system32/calc.exe')
    await model.openUrl('https://worldofpadman.net/en/download/')
    expect(openExternal).toHaveBeenCalledTimes(1)
  })
})

describe('ServerModel', () => {
  it('polls the status and fetches how to join', async () => {
    vi.useFakeTimers()
    const bridge = new FakeBridge({
      'server.status': () => ({ running: false, port: 27960, server_name: 'x' }),
      'server.join_info': () => ({ addresses: [] })
    })
    const model = new ServerModel(bridge)
    model.activate()
    await vi.advanceTimersByTimeAsync(POLL_MS * 2)
    model.deactivate()
    expect(bridge.methods().filter((m) => m === 'server.status')).toHaveLength(3)
    expect(model.getState().status?.running).toBe(false)
    expect(model.getState().joinInfo).toEqual({ addresses: [] })
  })

  it('starts the server, says what happened and reads the new status', async () => {
    let running = false
    const bridge = new FakeBridge({
      'server.start': () => {
        running = true
        return { result: 'Server started in the background.' }
      },
      'server.status': () => ({ running }),
      'server.join_info': () => ({})
    })
    const model = new ServerModel(bridge)
    const seen: (string | null)[] = []
    model.subscribe((s) => seen.push(s.busy))
    await model.start()
    expect(seen[0]).toBe('starting')
    expect(model.getState()).toMatchObject({ busy: null, status: { running: true } })
    expect(model.getState().notice).toEqual({ kind: 'info', text: 'Server started in the background.' })
  })

  it('shows why something failed', async () => {
    const bridge = new FakeBridge({
      'server.start': () => {
        throw new Error('The server isn\'t set up yet.')
      },
      'server.status': () => ({ running: false }),
      'server.join_info': () => ({})
    })
    const model = new ServerModel(bridge)
    await model.start()
    expect(model.getState().notice).toEqual({ kind: 'error', text: 'The server isn\'t set up yet.' })
  })
})

describe('ServerModel settings', () => {
  it('saves weapons and protection, then reads everything again', async () => {
    let settings = { running: true, instapad: false, spawn_protection: true, spawn_protection_seconds: 3 }
    const bridge = new FakeBridge({
      'settings.get': () => settings,
      'settings.set_weapons': ({ instapad }) => {
        settings = { ...settings, instapad: Boolean(instapad) }
        return { result: 'Now playing with InstaPad; the match restarted so it applies.' }
      },
      'settings.set_spawn_protection': () => ({ result: 'Spawn protection off, from the next respawn.' }),
      'server.status': () => ({ running: true, weapons: settings.instapad ? 'instapad' : 'regular' }),
      'server.join_info': () => ({})
    })
    const model = new ServerModel(bridge)
    await model.setWeapons(true)
    expect(bridge.calls.find((c) => c.method === 'settings.set_weapons')?.params).toEqual({ instapad: true })
    expect(model.getState().settings?.instapad).toBe(true)
    expect(model.getState().notice?.text).toContain('InstaPad')
    await model.setSpawnProtection(false)
    expect(bridge.calls.find((c) => c.method === 'settings.set_spawn_protection')?.params).toEqual({ on: false })
  })

  it('resets to the defaults and reads everything again', async () => {
    const states: (string | null)[] = []
    const bridge = new FakeBridge({
      'settings.reset': () => ({ result: 'Back to the original game settings. The server restarted with them.' }),
      'settings.get': () => ({ running: true, instapad: false }),
      'server.status': () => ({ running: true }),
      'server.join_info': () => ({})
    })
    const model = new ServerModel(bridge)
    model.subscribe((state) => states.push(state.busy))
    await model.resetToDefaults()
    expect(states).toContain('resetting')
    expect(model.getState().busy).toBeNull()
    expect(model.getState().notice?.text).toContain('original game settings')
    expect(bridge.methods()).toEqual(expect.arrayContaining(['settings.reset', 'server.status', 'settings.get']))
  })

  it('reads the settings again when someone else changed the weapons', async () => {
    let weapons = 'regular'
    const bridge = new FakeBridge({
      'settings.get': () => ({ running: true, instapad: weapons === 'instapad' }),
      'server.status': () => ({ running: true, weapons }),
      'server.join_info': () => ({})
    })
    const model = new ServerModel(bridge)
    model.activate()
    await settle()
    weapons = 'instapad'   // e.g. Claude switched to InstaPad
    await model.refresh()
    await settle()
    model.deactivate()
    expect(model.getState().settings?.instapad).toBe(true)
  })
})

describe('ServerModel internet play', () => {
  const status = (phase: string, extra: object = {}) => ({
    available: true, enabled: phase !== 'off', phase, address: null, port: null, approve_url: null, message: '',
    ...extra
  })
  const ready = () => status('online', { address: 'happy-pad.gl.ply.gg', port: 41234 })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('switches on, waits for the approval and the address, then stops asking', async () => {
    vi.useFakeTimers()
    const answers = [status('approving'), status('approving'), status('starting'), ready()]
    const bridge = new FakeBridge({
      'online.enable': () => status('approving', { approve_url: 'https://playit.gg/claim/abc' }),
      'online.advance': () => answers.shift() ?? ready(),
      'server.join_info': () => ({})
    })
    const model = new ServerModel(bridge)
    await model.setOnline(true)
    expect(model.getState().online?.approve_url).toBe('https://playit.gg/claim/abc')
    await vi.advanceTimersByTimeAsync(ONLINE_POLL_MS * 6)
    expect(model.getState().online).toMatchObject({ phase: 'online', address: 'happy-pad.gl.ply.gg' })
    expect(bridge.methods().filter((m) => m === 'online.advance')).toHaveLength(4)
    expect(bridge.methods().filter((m) => m === 'server.join_info').length).toBeGreaterThanOrEqual(2)
  })

  it('stops waiting when switched off, and after a while', async () => {
    vi.useFakeTimers()
    const bridge = new FakeBridge({
      'online.enable': () => status('approving'),
      'online.advance': () => status('approving'),
      'online.disable': () => ({ ...status('off'), result: 'Only players on your network can join now.' }),
      'server.join_info': () => ({})
    })
    const model = new ServerModel(bridge)
    await model.setOnline(true)
    await model.setOnline(false)
    expect(model.getState().notice?.text).toBe('Only players on your network can join now.')
    await vi.advanceTimersByTimeAsync(ONLINE_POLL_MS * 3)
    expect(bridge.methods()).not.toContain('online.advance')
    await model.setOnline(true)
    await vi.advanceTimersByTimeAsync(ONLINE_WAIT_MS + ONLINE_POLL_MS * 3)
    const asked = bridge.methods().filter((m) => m === 'online.advance').length
    await vi.advanceTimersByTimeAsync(ONLINE_POLL_MS * 5)
    expect(bridge.methods().filter((m) => m === 'online.advance').length).toBe(asked)
  })

  it('shows why it could not switch on', async () => {
    const bridge = new FakeBridge({
      'online.enable': () => {
        throw new Error("Couldn't reach playit.gg.")
      },
      'online.status': () => status('off'),
      'server.join_info': () => ({})
    })
    const model = new ServerModel(bridge)
    await model.setOnline(true)
    expect(model.getState()).toMatchObject({ onlineBusy: false, notice: { kind: 'error' }, online: { phase: 'off' } })
  })

  it('notices now and then when someone else (Claude) switched it', async () => {
    vi.useFakeTimers()
    let phase = 'off'
    const bridge = new FakeBridge({
      'server.status': () => ({ running: true }),
      'server.join_info': () => ({}),
      'settings.get': () => ({}),
      'online.status': () => status(phase)
    })
    const model = new ServerModel(bridge)
    model.activate()
    await vi.advanceTimersByTimeAsync(0)
    phase = 'online'
    await vi.advanceTimersByTimeAsync(POLL_MS * ONLINE_REFRESH_POLLS)
    model.deactivate()
    expect(model.getState().online?.phase).toBe('online')
  })

  it('opens playit.gg, and says when it could not', async () => {
    let fail = false
    const bridge = new FakeBridge({
      'online.manage': () => {
        if (fail) throw new Error('Something went wrong.')
        return { result: 'playit.gg opened in your browser.' }
      }
    })
    const model = new ServerModel(bridge)
    await model.manageOnline()
    expect(bridge.methods()).toEqual(['online.manage'])
    expect(model.getState().notice).toBeNull()
    fail = true
    await model.manageOnline()
    expect(model.getState().notice).toEqual({ kind: 'error', text: 'Something went wrong.' })
  })

  it('reads it again when the server starts or stops', async () => {
    let running = false
    const bridge = new FakeBridge({
      'server.status': () => ({ running }),
      'server.join_info': () => ({}),
      'settings.get': () => ({}),
      'online.status': () => (running ? ready() : status('server_off'))
    })
    const model = new ServerModel(bridge)
    model.activate()
    await settle()
    expect(model.getState().online?.phase).toBe('server_off')
    running = true
    await model.refresh()
    await settle()
    model.deactivate()
    expect(model.getState().online?.phase).toBe('online')
  })
})

describe('UpdateModel', () => {
  const release = (tag: string, digest: string | null = 'sha256:ABC123'): Release => ({
    tag_name: tag,
    html_url: 'https://github.com/x/y/releases/tag/' + tag,
    assets: [
      { name: `WoP-Server-Setup-${tag.replace('app-v', '')}.exe`, browser_download_url: 'https://dl/setup.exe', digest },
      { name: 'WoP-Server-2.2.0-amd64.deb', browser_download_url: 'https://dl/x.deb', digest }
    ]
  })

  function make(patch: Partial<UpdateDeps> = {}) {
    const calls: string[] = []
    const deps: UpdateDeps = {
      current: '2.1.0',
      repo: 'hivemindlore/wop-server-kit',
      behavior: {
        updateAssetName: (v) => `WoP-Server-Setup-${v}.exe`,
        installUpdate: async (file) => {
          calls.push(`install ${file}`)
          return { kind: 'quit', relaunch: false }
        }
      },
      folder: '/updates',
      fetchRelease: async (url) => {
        calls.push(url)
        return release('app-v2.2.0')
      },
      download: async (url, _file, progress) => {
        calls.push(`download ${url}`)
        progress(50)
        progress(100)
      },
      sha256: async () => 'abc123',
      checkKit: async () => {
        calls.push('kit')
        return false
      },
      quit: (relaunch) => calls.push(`quit ${relaunch}`),
      reveal: (file) => calls.push(`reveal ${file}`),
      ...patch
    }
    return { model: new UpdateModel(deps), calls }
  }

  it('reads the app version from the release tag', () => {
    expect(appVersionOf('app-v2.10.1')).toBe('2.10.1')
    expect(appVersionOf('kit-1.3.0')).toBeNull()
    expect(appVersionOf('app-v2.1')).toBeNull()
  })

  it('finds a newer app, downloads it, checks it and lets the installer take over', async () => {
    const { model, calls } = make()
    const percents: (number | null)[] = []
    model.subscribe((s) => percents.push(s.percent))
    await model.check()
    expect(model.getState()).toMatchObject({ phase: 'available', version: '2.2.0', current: '2.1.0' })
    expect(calls).toContain('https://api.github.com/repos/hivemindlore/wop-server-kit/releases/latest')
    await model.install()
    expect(percents).toContain(50)
    expect(calls).toContain('download https://dl/setup.exe')
    expect(calls.slice(-2)).toEqual([`install ${join('/updates', 'WoP-Server-Setup-2.2.0.exe')}`, 'quit false'])
  })

  it('says when it is up to date, and asks about the kit too', async () => {
    const { model, calls } = make({ fetchRelease: async () => release('app-v2.1.0') })
    await model.check()
    expect(model.getState()).toMatchObject({ phase: 'upToDate', message: 'You have the newest version.' })
    expect(calls).toContain('kit')
    await model.check(true)   // the quiet check at start
    expect(model.getState()).toMatchObject({ phase: 'idle', message: null })
  })

  it('stays quiet about older releases, other releases and computers without an installer', async () => {
    for (const fetchRelease of [async () => release('app-v2.0.0'), async () => release('kit-v9.0.0')]) {
      const { model } = make({ fetchRelease })
      await model.check(true)
      expect(model.getState().phase).toBe('idle')
    }
    const { model } = make({ behavior: { updateAssetName: () => null, installUpdate: async () => ({ kind: 'quit', relaunch: false }) } })
    await model.check()
    expect(model.getState().phase).toBe('upToDate')
  })

  it('a newer kit alone is not "the newest version"', async () => {
    const { model } = make({ fetchRelease: async () => release('app-v2.1.0'), checkKit: async () => true })
    await model.check()
    expect(model.getState()).toMatchObject({ phase: 'idle', message: null })
  })

  it('refuses a download that does not match, or has nothing to check against', async () => {
    const { model, calls } = make({ sha256: async () => 'evil' })
    await model.check()
    await model.install()
    expect(model.getState()).toMatchObject({ phase: 'error', message: 'The download was damaged. Please try again.' })
    expect(calls.some((c) => c.startsWith('install'))).toBe(false)
    const unchecked = make({ fetchRelease: async () => release('app-v2.2.0', null) })
    await unchecked.model.check()
    await unchecked.model.install()
    expect(unchecked.model.getState().phase).toBe('error')
    expect(unchecked.calls.some((c) => c.startsWith('install'))).toBe(false)
  })

  it('explains being offline', async () => {
    const offline = make({ fetchRelease: async () => { throw new Error('fetch failed') } })
    await offline.model.check()
    expect(offline.model.getState()).toMatchObject({ phase: 'error', message: expect.stringContaining('online') })
    const broken = make({ download: async () => { throw new Error('ECONNRESET') } })
    await broken.model.check()
    await broken.model.install()
    expect(broken.model.getState()).toMatchObject({ phase: 'error', version: '2.2.0', message: expect.stringContaining('Try again') })
  })

  it('hands over to the user where the app cannot replace itself', async () => {
    const { model, calls } = make({
      behavior: {
        updateAssetName: (v) => `WoP-Server-Setup-${v}.exe`,
        installUpdate: async () => ({ kind: 'manual', message: 'Drag it into Applications.', reveal: true })
      }
    })
    await model.check()
    await model.install()
    expect(model.getState()).toMatchObject({ phase: 'manual', message: 'Drag it into Applications.' })
    expect(calls.at(-1)).toBe(`reveal ${join('/updates', 'WoP-Server-Setup-2.2.0.exe')}`)
  })
})

describe('NetworkModel', () => {
  it('checks and fixes', async () => {
    const bridge = new FakeBridge({
      'network.check': () => ({ ok: false, can_fix: true }),
      'network.fix': () => ({ ok: true, accepted: true })
    })
    const model = new NetworkModel(bridge)
    await model.check()
    expect(model.getState().check).toEqual({ ok: false, can_fix: true })
    await model.fix()
    expect(model.getState()).toMatchObject({ check: { ok: true }, busy: null })
  })
})

describe('CommandModel', () => {
  it('runs commands and keeps the answers, also the refusals', async () => {
    const bridge = new FakeBridge({
      'console.run': ({ command }) => {
        if (command === 'quit') throw new Error('That command isn\'t allowed here.')
        return { command, output: 'g_gravity set' }
      }
    })
    const model = new CommandModel(bridge)
    await model.run('/g_gravity 400')
    await model.run('quit')
    await model.run('   ')
    expect(bridge.calls.map((c) => c.params.command)).toEqual(['g_gravity 400', 'quit'])
    expect(model.getState().entries).toMatchObject([
      { command: 'g_gravity 400', output: 'g_gravity set', failed: false },
      { command: 'quit', output: 'That command isn\'t allowed here.', failed: true }
    ])
    await model.clear()
    expect(model.getState().entries).toEqual([])
  })
})

describe('AiModel', () => {
  const app = { id: 'lm-studio', connected: false, finish_hint: 'Restart LM Studio.' }

  it('connects an app and says what to do next', async () => {
    const bridge = new FakeBridge({
      'ai.list': () => ({ apps: [app] }),
      'ai.connect': ({ app_id }) => ({ ...app, id: app_id, connected: true })
    })
    const model = new AiModel(bridge)
    await model.refresh()
    await model.connect('lm-studio')
    expect(model.getState().apps[0].connected).toBe(true)
    expect(model.getState().notice).toEqual({ appId: 'lm-studio', kind: 'info', text: 'Restart LM Studio.' })
    expect(model.getState().busy).toBeNull()
  })
})

describe('AiModel: open and restart', () => {
  const card = (patch = {}) => ({ id: 'claude-desktop', connected: true, can_restart: true, running: true,
    finish_hint: 'Quit and reopen it.', ...patch })

  it('remembers that an app connected while it was open needs a restart, until it is restarted', async () => {
    const bridge = new FakeBridge({
      'ai.list': () => ({ apps: [card({ connected: false })] }),
      'ai.connect': () => card(),
      'ai.restart': () => card(),
      'ai.open': () => card()
    })
    const model = new AiModel(bridge)
    await model.refresh()
    await model.connect('claude-desktop')
    expect(model.getState().restartPending).toEqual(['claude-desktop'])
    await model.open('claude-desktop')
    expect(model.getState().restartPending).toEqual(['claude-desktop'])  // opening isn't restarting
    await model.restart('claude-desktop')
    expect(model.getState().restartPending).toEqual([])
    expect(bridge.methods()).toEqual(['ai.list', 'ai.connect', 'ai.open', 'ai.restart'])
  })

  it("needs no restart when the app wasn't open, or can't be restarted from here", async () => {
    for (const patch of [{ running: false }, { can_restart: false }]) {
      const model = new AiModel(new FakeBridge({ 'ai.connect': () => card(patch) }))
      await model.connect('claude-desktop')
      expect(model.getState().restartPending).toEqual([])
    }
  })

  it('installs Claude Desktop, which then needs no restart', async () => {
    const bridge = new FakeBridge({ 'ai.install': () => card({ installed: true }) })
    const model = new AiModel(bridge)
    await model.install('claude-desktop')
    expect(model.getState()).toMatchObject({ apps: [], busy: null, restartPending: [], notice: null })
    expect(bridge.calls).toEqual([{ method: 'ai.install', params: { app_id: 'claude-desktop' } }])
  })

  it("shows why it couldn't be installed", async () => {
    const model = new AiModel(new FakeBridge({
      'ai.install': () => {
        throw new Error("Claude Desktop couldn't be installed.")
      }
    }))
    await model.install('claude-desktop')
    expect(model.getState().notice).toEqual({
      appId: 'claude-desktop', kind: 'error', text: "Claude Desktop couldn't be installed."
    })
  })

  it("shows why an app couldn't be opened", async () => {
    const model = new AiModel(new FakeBridge({
      'ai.open': () => {
        throw new Error("Couldn't find Cursor on this computer. Is it installed?")
      }
    }))
    await model.open('cursor')
    expect(model.getState().notice).toEqual({
      appId: 'cursor', kind: 'error', text: "Couldn't find Cursor on this computer. Is it installed?"
    })
  })
})

describe('LogModel', () => {
  it('loads the end of the log once, then follows it', async () => {
    const bridge = new FakeBridge({ 'log.history': () => ({ lines: [[{ text: 'old', color: null }]] }) })
    const model = new LogModel(bridge)
    const changes: string[] = []
    model.subscribe((c) => changes.push(c.type))
    bridge.emit('event', 'log.lines', { lines: [[{ text: 'new', color: 'red' }]] })
    const lines = await model.history()
    expect(lines.map((l) => l[0].text)).toEqual(['old', 'new'])
    await model.history()
    expect(bridge.methods()).toEqual(['log.history'])
    bridge.emit('event', 'log.reset', {})
    expect(await model.history()).toEqual([])
    expect(changes).toEqual(['append', 'reset'])
  })

  it('keeps only the newest lines', async () => {
    const bridge = new FakeBridge({ 'log.history': () => ({ lines: [] }) })
    const model = new LogModel(bridge)
    const many = Array.from({ length: MAX_LINES + 10 }, (_, i) => [{ text: String(i), color: null }])
    bridge.emit('event', 'log.lines', { lines: many })
    const lines = await model.history()
    expect(lines).toHaveLength(MAX_LINES)
    expect(lines[0][0].text).toBe('10')
  })
})

describe('ServerModel: is the game open?', () => {
  it('counts the game as open right after Play, until it shows up or the wait is over', async () => {
    let now = 1000
    let open = false
    const bridge = new FakeBridge({
      'game.play': () => ({ result: 'World of PADMAN is starting.' }),
      'game.playing': () => ({ playing: open })
    })
    const model = new ServerModel(bridge, () => now)
    await model.checkPlaying()
    expect(model.getState().playing).toBe(false)
    await model.play()
    expect(model.getState().playing).toBe(true)
    await model.checkPlaying()
    expect(model.getState().playing).toBe(true)        // still loading
    await model.play()                                 // a second click does nothing
    expect(bridge.methods().filter((m) => m === 'game.play')).toHaveLength(1)
    now += PLAY_GRACE_MS
    await model.checkPlaying()
    expect(model.getState().playing).toBe(false)       // it never showed up (or was closed)
    open = true
    await model.checkPlaying()
    expect(model.getState().playing).toBe(true)        // started some other way
  })

  it('shows why the game could not start', async () => {
    const model = new ServerModel(new FakeBridge({
      'game.play': () => {
        throw new Error('World of PADMAN is already running.')
      },
      'game.playing': () => ({ playing: false })
    }))
    await model.play()
    expect(model.getState()).toMatchObject({
      playing: false, notice: { kind: 'error', text: 'World of PADMAN is already running.' }
    })
  })
})

describe('GameModel', () => {
  const catalog = { modes: [{ key: 'ctl' }], bots: ['PADMAN'] }

  it('loads the modes once', async () => {
    const bridge = new FakeBridge({ 'game.catalog': () => catalog, 'game.rotation': () => ({ maps: ['wop_padbaseCTL'] }) })
    const model = new GameModel(bridge)
    await model.loadCatalog()
    await model.loadCatalog()
    expect(model.getState().catalog).toEqual(catalog)
    expect(bridge.methods()).toEqual(['game.catalog', 'game.rotation'])
    expect(model.getState().rotation).toEqual(['wop_padbaseCTL'])
  })

  it('starts a new game, says how it went and lets the server look again', async () => {
    const changed = vi.fn()
    const busy: (string | null)[] = []
    const bridge = new FakeBridge({
      'game.set': () => ({ result: 'Now playing Capture The Lolly on wop_padbaseCTL.', problems: [] }),
      'game.rotation': () => ({ maps: ['wop_padbaseCTL', 'wop_journeyCTL'] })
    })
    const model = new GameModel(bridge, changed)
    model.subscribe((state) => busy.push(state.busy))
    const choice = { gamemode: 'ctl', maps: ['wop_padbaseCTL', 'wop_journeyCTL'], weapons: 'regular' as const,
      spawnProtection: true, red: ['PADMAN'], blue: [], bots: [], skill: 3,
      pointlimit: 8, timelimit: 16 }
    await model.apply(choice)
    // The kit's names: kit/setup/test_appbridge.py (test_game_set_takes_what_the_app_sends) checks the same list
    expect(bridge.calls).toEqual([
      { method: 'game.set', params: { gamemode: 'ctl', maps: ['wop_padbaseCTL', 'wop_journeyCTL'], weapons: 'regular',
        spawn_protection: true, red: ['PADMAN'], blue: [], bots: [], skill: 3, pointlimit: 8, timelimit: 16 } },
      { method: 'game.rotation', params: {} }
    ])
    expect(model.getState().rotation).toEqual(['wop_padbaseCTL', 'wop_journeyCTL'])   // the new loop
    expect(busy).toContain('applying')
    expect(model.getState()).toMatchObject({
      busy: null, notice: { kind: 'info', text: 'Now playing Capture The Lolly on wop_padbaseCTL.' }
    })
    expect(changed).toHaveBeenCalledOnce()
  })

  it('restarts the match, sends messages and keeps the game, one at a time', async () => {
    let release = () => {}
    const bridge = new FakeBridge({
      'game.restart_match': () => new Promise((resolve) => (release = () => resolve({ result: 'Match restarted.' }))),
      'game.send_message': ({ text }) => ({ result: `Said to everyone: ${text}` }),
      'game.save_as_startup': () => ({ result: 'Saved.' })
    })
    const model = new GameModel(bridge)
    const restarting = model.restartMatch()
    await model.saveAsStartup()                 // busy: ignored
    release()
    await restarting
    await model.sendMessage('   ')              // empty: nothing to send
    await model.sendMessage(' hi ')
    expect(bridge.calls.map((c) => [c.method, c.params])).toEqual([
      ['game.restart_match', {}], ['game.send_message', { text: 'hi' }]
    ])
    expect(model.getState().notice?.text).toBe('Said to everyone: hi')
  })

  it('shows why something did not work', async () => {
    const model = new GameModel(new FakeBridge({
      'game.restart_match': () => {
        throw new Error('The server is off. Start it on My server first.')
      }
    }))
    await model.restartMatch()
    expect(model.getState().notice).toEqual({ kind: 'error', text: 'The server is off. Start it on My server first.' })
  })
})
