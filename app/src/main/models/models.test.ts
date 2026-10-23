import { afterEach, describe, expect, it, vi } from 'vitest'
import { BRIDGE_PROTOCOL, type Hello } from '@shared/api'
import { FakeBridge, settle } from '../../test/fakes'
import { AiModel } from './AiModel'
import { AppModel } from './AppModel'
import { CommandModel } from './CommandModel'
import { LogModel, MAX_LINES } from './LogModel'
import { NetworkModel } from './NetworkModel'
import { POLL_MS, ServerModel } from './ServerModel'

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
