import { describe, expect, it, vi } from 'vitest'
import type {
  AiApp, GameCatalog, GameModeInfo, GameSettings, JoinInfo, NetworkCheck, OnlineStatus, ServerState, ServerStatus
} from '@shared/api'
import { FakeApi, appState, gameState, networkState, serverState, settle, updateState } from '../../test/fakes'
import { AiViewModel } from './AiViewModel'
import { AppViewModel, type Storage } from './AppViewModel'
import { CommandsViewModel } from './CommandsViewModel'
import { LogsViewModel } from './LogsViewModel'
import { GameViewModel } from './GameViewModel'
import { describeNetwork } from './network'
import { ServerViewModel, mapLabel } from './ServerViewModel'
import { SetupViewModel } from './SetupViewModel'

const running: ServerStatus = {
  running: true,
  port: 27960,
  server_name: 'Bro night',
  map: 'wop_padbaseCTL',
  gamemode: { id: 8, name: 'Capture The Lolly', team_mode: true },
  weapons: 'instapad',
  pointlimit: 8,
  timelimit_minutes: 15,
  slots: { max: 16, used: 3, free: 13 },
  players: [
    { num: 0, name: 'FatPad', team: 'red', bot: true, score: 2, ping: 0, bot_type: 'FatPad', skill: 3 },
    { num: 1, name: 'PadGirl', team: 'blue', bot: true, score: 1, ping: 0, bot_type: 'PadGirl', skill: 3 },
    { num: 2, name: 'Kim', team: 'blue', bot: false, score: 5, ping: 20 }
  ]
}

const join: JoinInfo = {
  server_name: 'Bro night',
  running: true,
  addresses: [
    { address: '192.168.1.20', connection: 'Wi-Fi' },
    { address: '10.0.0.5', connection: 'Ethernet' }
  ],
  port: 27961,
  join_password: 'pad123',
  connect_commands: [],
  how_to_join: [],
  in_lan_list: true,
  download_url: 'https://worldofpadman.net/en/download/',
  online: null
}

const online = (patch: Partial<OnlineStatus> = {}): OnlineStatus => ({
  available: true,
  enabled: true,
  phase: 'online',
  address: 'happy-pad.gl.ply.gg',
  port: 41234,
  approve_url: null,
  message: 'Friends anywhere can join: address happy-pad.gl.ply.gg, port 41234.',
  approved: true,
  ...patch
})

const check = (patch: Partial<NetworkCheck> = {}): NetworkCheck => ({
  checked: true,
  ok: false,
  problems: [{ text: 'Windows Firewall has no rule that lets the players in.', fixable: true }],
  can_fix: true,
  permission_hint: 'Windows will now ask for permission.',
  notes: [],
  others: [],
  firewall_name: 'Windows Firewall',
  help_url: 'https://example.org/help',
  ...patch
})

const JARGON = /\b(mcp|rcon|cvar|stdio|json|udp)\b/i

describe('ServerViewModel: internet play', () => {
  it("is hidden where it isn't available, and until it is known", async () => {
    const api = new FakeApi()
    api.states.server = serverState({ status: running, joinInfo: join })
    const vm = new ServerViewModel(api)
    await settle()
    expect(vm.getSnapshot().online).toBeNull()
    api.push('server', serverState({
      status: running, joinInfo: join, online: online({ available: false, enabled: false, phase: 'off' })
    }))
    expect(vm.getSnapshot().online).toBeNull()
  })

  it('switches on, and shows the approval wait with a way back', async () => {
    const api = new FakeApi()
    api.states.server = serverState({
      joinInfo: join, online: online({ enabled: false, phase: 'off', address: null, port: null })
    })
    const vm = new ServerViewModel(api)
    await settle()
    expect(vm.getSnapshot().online).toMatchObject({ on: false, address: null, approveUrl: null, note: null })
    expect(vm.getSnapshot().online?.hint).toContain('playit.gg (free)')
    vm.toggleOnline()
    expect(api.calls.at(-1)).toEqual({ model: 'server', command: 'setOnline', args: [true] })
    api.push('server', serverState({
      joinInfo: join,
      online: online({ phase: 'approving', address: null, port: null, approve_url: 'https://playit.gg/claim/abc' })
    }))
    const view = vm.getSnapshot().online!
    expect(view).toMatchObject({ on: true, approveUrl: 'https://playit.gg/claim/abc', address: null })
    expect(view.note).toContain('Approve it on playit.gg')
    vm.toggleOnline()   // Cancel
    expect(api.calls.at(-1)).toEqual({ model: 'server', command: 'setOnline', args: [false] })
  })

  it('shows the internet address and suggests a join password', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ status: running, joinInfo: { ...join, join_password: null }, online: online() })
    const vm = new ServerViewModel(api)
    await settle()
    const view = vm.getSnapshot().online!
    expect(view).toMatchObject({
      address: 'happy-pad.gl.ply.gg',
      port: '41234',
      connectLine: '/connect happy-pad.gl.ply.gg:41234',
      note: null,
      problem: null
    })
    expect(view.passwordTip).toContain('join password')
    expect(JSON.stringify(view)).not.toMatch(JARGON)
    expect(JSON.stringify(view)).not.toMatch(/tunnel|agent/i)
    api.push('server', serverState({ status: running, joinInfo: join, online: online() }))
    expect(vm.getSnapshot().online?.passwordTip).toBeNull()
  })

  it('offers playit.gg itself once it is approved', async () => {
    const api = new FakeApi()
    api.states.server = serverState({
      joinInfo: join, online: online({ phase: 'approving', approved: false, address: null, port: null })
    })
    const vm = new ServerViewModel(api)
    await settle()
    expect(vm.getSnapshot().online?.manageLabel).toBeNull()
    api.push('server', serverState({ joinInfo: join, online: online({ enabled: false, phase: 'off' }) }))
    expect(vm.getSnapshot().online?.manageLabel).toBe('Manage on playit.gg')   // still there when switched off
    vm.manageOnline()
    expect(api.called()).toEqual(['server.manageOnline'])
  })

  it('says when it works, and what went wrong', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ joinInfo: join, online: online({ phase: 'server_off' }) })
    const vm = new ServerViewModel(api)
    await settle()
    expect(vm.getSnapshot().online).toMatchObject({
      address: 'happy-pad.gl.ply.gg', note: 'This works while the server is on.'
    })
    api.push('server', serverState({
      joinInfo: join, online: online({ phase: 'problem', message: 'playit.gg switched it off.' })
    }))
    expect(vm.getSnapshot().online?.problem).toBe('playit.gg switched it off.')
    api.push('server', serverState({ joinInfo: join, online: online(), onlineBusy: true }))
    vm.toggleOnline()
    expect(api.called()).not.toContain('server.setOnline')
  })
})

describe('ServerViewModel', () => {
  it('describes a running game in plain words', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ status: running, joinInfo: join })
    const vm = new ServerViewModel(api)
    await settle()
    const view = vm.getSnapshot()
    expect(view.power).toMatchObject({ on: true, headline: 'Your server is on', buttonLabel: 'Stop server', tone: 'on' })
    expect(view.game).toEqual({
      mode: 'Capture The Lolly',
      map: 'padbase CTL',
      weapons: 'InstaPad (one hit wins)',
      limits: 'first to 8 points or 15 minutes'
    })
    expect(view.playersSummary).toBe('1 player and 2 bots · 13 of 16 places free')
    expect(view.players.map((p) => [p.name, p.team, p.kind])).toEqual([
      ['FatPad', 'Red Pads', 'Bot'],
      ['PadGirl', 'Blue Noses', 'Bot'],
      ['Kim', 'Blue Noses', 'Player']
    ])
    expect(view.join).toMatchObject({
      port: '27961',
      connectLine: '/connect 192.168.1.20:27961',
      passwordLine: '/password pad123',
      warning: null
    })
    expect(view.join?.addresses[0].primary).toBe(true)
    expect(JSON.stringify(view)).not.toMatch(JARGON)
  })

  it('toggles the server, but not while it is busy or unknown', async () => {
    const api = new FakeApi()
    const vm = new ServerViewModel(api)
    await settle()
    vm.toggle()
    expect(api.calls).toEqual([])  // status not known yet
    api.push('server', serverState({ status: { running: false, port: 27960, server_name: 'x' } }))
    vm.toggle()
    api.push('server', serverState({ status: running }))
    vm.toggle()
    api.push('server', serverState({ status: running, busy: 'stopping' }))
    vm.toggle()
    expect(api.called()).toEqual(['server.start', 'server.stop'])
    expect(vm.getSnapshot().power).toMatchObject({ busy: true, headline: 'Stopping your server...' })
  })

  it('warns when nobody else can reach the server', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ joinInfo: { ...join, addresses: [] } })
    const vm = new ServerViewModel(api)
    await settle()
    expect(vm.getSnapshot().join?.warning).toContain('connected to a network')
    api.push('server', serverState({ joinInfo: { ...join, port: 27970, in_lan_list: false } }))
    expect(vm.getSnapshot().join?.warning).toContain('LAN list')
  })

  it('copies and says so for a moment', async () => {
    vi.useFakeTimers()
    const write = vi.fn(async () => {})
    const vm = new ServerViewModel(new FakeApi(), { write })
    await vm.copy('192.168.1.20')
    expect(write).toHaveBeenCalledWith('192.168.1.20')
    expect(vm.getSnapshot().copied).toBe('192.168.1.20')
    vi.advanceTimersByTime(2500)
    expect(vm.getSnapshot().copied).toBeNull()
    vi.useRealTimers()
  })

  it('renames and sets the join password', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ joinInfo: join })
    const vm = new ServerViewModel(api)
    await settle()
    vm.editName()
    expect(vm.getSnapshot().nameDraft).toBe('Bro night')
    vm.setNameDraft('Pad party')
    await vm.saveName()
    vm.setPasswordDraft(' se cret ')
    await vm.savePassword()
    expect(api.calls.map((c) => [c.command, c.args[0]])).toEqual([['setName', 'Pad party'], ['setJoinPassword', 'secret']])
    expect(vm.getSnapshot()).toMatchObject({ editingName: false, passwordDraft: '' })
  })

  it('names maps the way players say them', () => {
    expect(mapLabel('wop_padkitchenLPS')).toBe('padkitchen LPS')
    expect(mapLabel('wop_padgarden')).toBe('padgarden')
  })
})

describe('Weapons (Game tab) and reset (My server)', () => {
  const settings = (patch: Partial<GameSettings> = {}): GameSettings => ({
    running: true, instapad: false, spawn_protection: true, spawn_protection_seconds: 3,
    spawn_protection_changeable: true, ...patch
  })

  async function viewWith(patch: Partial<GameSettings>, busy: ServerState['busy'] = null) {
    const api = new FakeApi()
    api.states.server = serverState({ settings: settings(patch), busy })
    const vm = new ServerViewModel(api)
    await settle()
    return { api, vm, view: vm.getSnapshot() }
  }


  it('resets to the defaults only after a confirmation', async () => {
    const { api, vm } = await viewWith({})
    expect(vm.getSnapshot().reset.confirming).toBe(false)
    vm.confirmReset()
    expect(api.calls).toEqual([])
    vm.askReset()
    expect(vm.getSnapshot().reset.confirming).toBe(true)
    vm.cancelReset()
    expect(vm.getSnapshot().reset.confirming).toBe(false)
    expect(api.calls).toEqual([])
    vm.askReset()
    vm.confirmReset()
    expect(api.calls).toEqual([{ model: 'server', command: 'resetToDefaults', args: [] }])
    expect(vm.getSnapshot().reset.confirming).toBe(false)
  })

  it('warns that the server restarts only while it runs', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ status: running })
    const vm = new ServerViewModel(api)
    await settle()
    expect(vm.getSnapshot().reset.warning).toContain('server restarts')
    api.push('server', serverState({ status: { ...running, running: false } }))
    expect(vm.getSnapshot().reset.warning).not.toContain('restarts')
    expect(vm.getSnapshot().reset.warning).toContain('server name stays')
    api.push('server', serverState({ status: running, busy: 'resetting' }))
    expect(vm.getSnapshot()).toMatchObject({ reset: { busy: true }, saving: true, power: { busy: true } })
  })

})

describe('describeNetwork', () => {
  it('goes from checking to problems to fixed', () => {
    expect(describeNetwork(null).status).toBe('checking')
    const problems = describeNetwork(networkState({ check: check() }))
    expect(problems).toMatchObject({ status: 'problems', canFix: true, fixLabel: 'Fix it' })
    expect(problems.problems).toHaveLength(1)
    expect(describeNetwork(networkState({ check: check(), busy: 'fixing' }))).toMatchObject({
      canFix: false, fixing: true, title: 'Waiting for your permission...'
    })
    const declined = describeNetwork(networkState({ check: check({ accepted: false }) }))
    expect(declined.permissionHint).toContain('permission wasn\'t given')
    expect(describeNetwork(networkState({ check: check({ ok: true, problems: [], can_fix: false }) }))).toMatchObject({
      status: 'ok', helpUrl: null
    })
  })

  it('admits when the firewall couldn\'t be read', () => {
    const view = describeNetwork(networkState({ check: check({ checked: false, problems: [], can_fix: false }) }))
    expect(view.status).toBe('unknown')
    expect(view.title).toContain('Couldn\'t read the Windows Firewall settings')
  })
})

describe('ViewModel lifecycle', () => {
  it('keeps following the models after React mounts the view twice (StrictMode)', async () => {
    const api = new FakeApi()
    api.states.app = appState({ phase: 'starting' })
    const vm = new AppViewModel(api)
    vm.dispose()   // StrictMode's first unmount
    vm.activate()  // and the mount that stays
    await settle()
    api.push('app', appState({ phase: 'ready' }))
    expect(vm.getSnapshot().screen).toBe('main')
  })

  it('stops following after a real unmount', async () => {
    const api = new FakeApi()
    const vm = new AppViewModel(api)
    await settle()
    vm.dispose()
    api.push('app', appState({ phase: 'error', error: 'x' }))
    expect(vm.getSnapshot().screen).not.toBe('error')
  })
})

describe('AppViewModel', () => {
  const memory = (): Storage & { data: Record<string, string> } => {
    const data: Record<string, string> = {}
    return { data, get: (k) => data[k] ?? null, set: (k, v) => void (data[k] = v) }
  }

  it('shows loading, then the wizard until it is finished, then the tabs', async () => {
    const api = new FakeApi()
    api.states.app = appState({ phase: 'starting' })
    const vm = new AppViewModel(api, memory())
    await settle()
    expect(vm.getSnapshot().screen).toBe('loading')
    api.push('app', appState({ phase: 'needs-setup' }))
    expect(vm.getSnapshot().screen).toBe('setup')
    api.push('app', appState({ phase: 'ready' }))
    expect(vm.getSnapshot().screen).toBe('setup')  // the wizard still has its last steps
    vm.finishSetup()
    expect(vm.getSnapshot().screen).toBe('main')
  })

  it('has Server and AI on top, and My server, Game, Commands and Logs inside Server', () => {
    const view = new AppViewModel(new FakeApi(), memory()).getSnapshot()
    expect(view.tabs.map((t) => t.label)).toEqual(['Server', 'AI'])
    expect(view.serverTabs.map((t) => t.label)).toEqual(['My server', 'Game', 'Commands', 'Logs'])
    expect(view).toMatchObject({ activeTab: 'server', activeServerTab: 'my-server' })
  })

  it('remembers the open tabs', async () => {
    const storage = memory()
    const vm = new AppViewModel(new FakeApi(), storage)
    vm.selectTab('ai')
    vm.selectServerTab('game')
    expect(storage.data).toMatchObject({ tab: 'ai', serverTab: 'game' })
    expect(new AppViewModel(new FakeApi(), storage).getSnapshot()).toMatchObject({ activeTab: 'ai', activeServerTab: 'game' })
    storage.data.tab = 'nonsense'
    storage.data.serverTab = 'nonsense'
    expect(new AppViewModel(new FakeApi(), storage).getSnapshot())
      .toMatchObject({ activeTab: 'server', activeServerTab: 'my-server' })
  })

  it('opens Logs or Commands inside Server for people who had them open before', () => {
    const storage = memory()
    storage.data.tab = 'logs'
    expect(new AppViewModel(new FakeApi(), storage).getSnapshot())
      .toMatchObject({ activeTab: 'server', activeServerTab: 'logs' })
  })

  it('opens My server after the setup', () => {
    const storage = memory()
    storage.data.tab = 'ai'
    storage.data.serverTab = 'logs'
    const vm = new AppViewModel(new FakeApi(), storage)
    vm.finishSetup()
    expect(vm.getSnapshot()).toMatchObject({ activeTab: 'server', activeServerTab: 'my-server' })
  })

  it('offers kit updates', async () => {
    const api = new FakeApi()
    api.states.app = appState({ update: { available: true, version: '2.1.0', busy: false } })
    const vm = new AppViewModel(api, memory())
    await settle()
    expect(vm.getSnapshot().update?.text).toContain('2.1.0')
    vm.updateKit()
    expect(api.called()).toEqual(['app.updateKit'])
    vm.runUpdate()
    expect(api.called()).toEqual(['app.updateKit', 'app.updateKit'])
  })

  it('offers a new app first, and shows its download', async () => {
    const api = new FakeApi()
    api.states.app = appState({ update: { available: true, version: '2.1.1', busy: false } })
    api.states.update = updateState({ phase: 'available', version: '2.2.0' })
    const vm = new AppViewModel(api, memory())
    await settle()
    expect(vm.getSnapshot().update).toMatchObject({
      text: 'A new version of WoP Server is ready (2.2.0).', buttonLabel: 'Update now', action: 'app'
    })
    vm.runUpdate()
    expect(api.called()).toEqual(['update.install'])
    api.push('update', updateState({ phase: 'downloading', version: '2.2.0', percent: 40 }))
    expect(vm.getSnapshot().update).toMatchObject({ text: 'Downloading WoP Server 2.2.0... 40%', busy: true, buttonLabel: null })
    vm.runUpdate()
    expect(api.called()).toEqual(['update.install'])
    api.push('update', updateState({ phase: 'error', version: '2.2.0', message: 'The download was damaged.' }))
    expect(vm.getSnapshot().update).toMatchObject({ text: 'The download was damaged.', buttonLabel: 'Try again' })
  })

  it('checks for updates from the footer and says what it found', async () => {
    const api = new FakeApi()
    api.states.update = updateState({ current: '2.1.0' })
    const vm = new AppViewModel(api, memory())
    await settle()
    expect(vm.getSnapshot()).toMatchObject({
      appVersion: '2.1.0', updateCheck: { label: 'Check for updates', busy: false, text: null }
    })
    vm.checkForUpdates()
    expect(api.called()).toEqual(['update.check'])
    api.push('update', updateState({ phase: 'checking' }))
    expect(vm.getSnapshot().updateCheck).toMatchObject({ label: 'Checking...', busy: true })
    vm.checkForUpdates()
    expect(api.called()).toEqual(['update.check'])
    api.push('update', updateState({ phase: 'upToDate', message: 'You have the newest version.' }))
    expect(vm.getSnapshot().updateCheck.text).toBe('You have the newest version.')
    api.push('update', updateState({ phase: 'error', message: 'Couldn\'t check for updates.' }))
    expect(vm.getSnapshot().updateCheck.text).toContain('Couldn')
    expect(vm.getSnapshot().update).toBeNull()
  })
})

describe('SetupViewModel', () => {
  it('walks through name, install, network and done', async () => {
    const api = new FakeApi()
    api.states.app = appState({
      phase: 'needs-setup',
      hello: { default_server_name: 'kim\'s WoP server' } as never
    })
    const finished = vi.fn()
    const vm = new SetupViewModel(api, finished)
    await settle()
    expect(vm.getSnapshot().step).toBe('welcome')
    vm.next()
    expect(vm.getSnapshot()).toMatchObject({ step: 'name', nameDraft: 'kim\'s WoP server', canContinue: true })
    vm.setName('Bro night')
    vm.install()
    expect(api.calls[0]).toEqual({ model: 'app', command: 'startSetup', args: ['Bro night'] })
    api.push('app', appState({ phase: 'setting-up', setup: { step: 'Downloading', messages: ['a'], percent: 42, error: null } }))
    expect(vm.getSnapshot().install).toMatchObject({ title: 'Downloading', percentLabel: '42%' })
    api.push('app', appState({ phase: 'ready' }))
    await settle()
    expect(vm.getSnapshot().step).toBe('network')   // no Claude Desktop on this computer: no Claude step
    expect(vm.getSnapshot()).toMatchObject({ stepNumber: 4, stepCount: 5 })
    expect(api.called()).toContain('network.check')
    expect(vm.getSnapshot().networkNext.label).toBe('Skip for now')
    vm.next()
    await vm.finish(true)
    expect(api.called()).toContain('server.start')
    expect(finished).toHaveBeenCalled()
  })

  it('shows a failed install with a way to try again', async () => {
    const api = new FakeApi()
    api.states.app = appState({ phase: 'needs-setup' })
    const vm = new SetupViewModel(api, () => {})
    await settle()
    vm.next()
    vm.setName('x')
    vm.install()
    api.push('app', appState({ phase: 'needs-setup', setup: { step: '', messages: [], percent: null, error: 'No internet.' } }))
    expect(vm.getSnapshot().install).toMatchObject({ title: 'That didn\'t work', error: 'No internet.' })
  })
})

describe('SetupViewModel: Claude Desktop', () => {
  const claude = (patch: Partial<AiApp> = {}): AiApp => ({
    id: 'claude-desktop', name: 'Claude Desktop', blurb: '', free: false, download_url: 'https://claude.ai/download',
    connectable: true, available: true, installed: false, connected: false, finish_hint: '', advice: '', examples: [],
    openable: false, running: false, can_restart: true, installable: true, ...patch
  })

  async function installed(app: AiApp | null) {
    const api = new FakeApi()
    api.states.app = appState({ phase: 'needs-setup' })
    api.states.ai = { apps: app ? [app] : [], busy: null, restartPending: [], notice: null }
    const vm = new SetupViewModel(api, () => {})
    await settle()
    vm.next()
    vm.install()
    api.push('app', appState({ phase: 'setting-up' }))
    api.push('app', appState({ phase: 'ready' }))
    await settle()
    return { api, vm }
  }

  it('offers Claude Desktop after the game is installed, and can skip it', async () => {
    const { api, vm } = await installed(claude())
    expect(api.called()).toContain('ai.refresh')
    expect(vm.getSnapshot()).toMatchObject({ step: 'claude', stepNumber: 4, stepCount: 6 })
    expect(vm.getSnapshot().claude).toMatchObject({ installed: false, busy: false, installLabel: 'Install Claude Desktop' })
    expect(api.called()).not.toContain('network.check')
    vm.next()
    expect(vm.getSnapshot().step).toBe('network')
    expect(api.called()).toContain('network.check')
    expect(api.called()).not.toContain('ai.install')
  })

  it('installs it, shows the progress and then that it is ready', async () => {
    const { api, vm } = await installed(claude())
    vm.installClaude()
    expect(api.calls.at(-1)).toEqual({ model: 'ai', command: 'install', args: ['claude-desktop'] })
    api.push('app', appState({ setup: { step: 'Downloading Claude Desktop', messages: [], percent: 30, error: null } }))
    api.push('ai', { apps: [claude()], busy: 'claude-desktop', restartPending: [], notice: null })
    expect(vm.getSnapshot().claude).toMatchObject({ busy: true, progress: { title: 'Downloading Claude Desktop', percentLabel: '30%' } })
    api.push('ai', { apps: [claude({ installed: true, connected: true })], busy: null, restartPending: [], notice: null })
    expect(vm.getSnapshot().claude).toMatchObject({ busy: false, installed: true })
    expect(vm.getSnapshot().step).toBe('claude')
    vm.next()
    expect(vm.getSnapshot().step).toBe('network')
  })

  it("shows why it couldn't be installed, with a way to go on", async () => {
    const { api, vm } = await installed(claude())
    api.push('ai', {
      apps: [claude()], busy: null, restartPending: [],
      notice: { appId: 'claude-desktop', kind: 'error', text: "Claude Desktop couldn't be installed." }
    })
    expect(vm.getSnapshot().claude).toMatchObject({
      error: "Claude Desktop couldn't be installed.", installLabel: 'Try again', skipLabel: 'Continue without it'
    })
  })

  it('opens the download page where it can only be downloaded by hand', async () => {
    const { api, vm } = await installed(claude({ installable: false }))
    vm.installClaude()
    expect(api.calls.at(-1)).toEqual({ model: 'app', command: 'openUrl', args: ['https://claude.ai/download'] })
  })

  it('skips the step when Claude Desktop is already installed', async () => {
    const { vm } = await installed(claude({ installed: true }))
    expect(vm.getSnapshot()).toMatchObject({ step: 'network', stepCount: 5 })
  })
})

describe('CommandsViewModel', () => {
  it('runs typed commands and walks the history', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ status: running })
    const vm = new CommandsViewModel(api)
    await settle()
    expect(vm.getSnapshot().canRun).toBe(false)
    vm.setDraft('g_gravity 400')
    vm.submit()
    vm.setDraft('timelimit 10')
    vm.submit()
    expect(api.calls.map((c) => c.args[0])).toEqual(['g_gravity 400', 'timelimit 10'])
    vm.browseHistory('older')
    expect(vm.getSnapshot().draft).toBe('timelimit 10')
    vm.browseHistory('older')
    expect(vm.getSnapshot().draft).toBe('g_gravity 400')
    vm.browseHistory('newer')
    vm.browseHistory('newer')
    expect(vm.getSnapshot().draft).toBe('')
  })

  it('can\'t run commands while the server is off', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ status: { running: false, port: 27960, server_name: 'x' } })
    const vm = new CommandsViewModel(api)
    await settle()
    vm.setDraft('status')
    expect(vm.getSnapshot()).toMatchObject({ serverOff: true, canRun: false })
  })
})

describe('AiViewModel', () => {
  const app = (patch: Partial<AiApp>): AiApp => ({
    id: 'x', name: 'X', blurb: '', free: false, download_url: 'https://x', connectable: true, available: true,
    installed: false, connected: false, finish_hint: '', advice: '', examples: ['How do my friends join?'],
    openable: false, running: false, can_restart: false, installable: false, ...patch
  })

  it('orders the cards and gives each the right button', async () => {
    const api = new FakeApi()
    api.states.ai = {
      apps: [
        app({ id: 'chatgpt', name: 'ChatGPT', connectable: false, advice: 'Use another app.' }),
        app({ id: 'cursor', name: 'Cursor' }),
        app({ id: 'lm-studio', name: 'LM Studio', free: true, installed: true }),
        app({ id: 'claude-desktop', name: 'Claude Desktop', installed: true, connected: true })
      ],
      busy: null,
      restartPending: [],
      notice: null
    }
    const vm = new AiViewModel(api)
    await settle()
    const cards = vm.getSnapshot().cards
    expect(cards.map((c) => [c.id, c.status, c.action?.label ?? null])).toEqual([
      ['claude-desktop', 'connected', 'Disconnect'],
      ['lm-studio', 'ready', 'Connect'],
      ['cursor', 'not-installed', 'Connect'],
      ['chatgpt', 'advice', null]
    ])
    expect(cards[1].price).toBe('Free · runs on your computer')
    expect(cards[2].download).toEqual({ label: 'Get Cursor', url: 'https://x' })
    expect(cards[3]).toMatchObject({ download: null, examples: [], advice: 'Use another app.' })
    expect(JSON.stringify(vm.getSnapshot())).not.toMatch(JARGON)
  })

  it('locks the buttons while one app is being connected', async () => {
    const api = new FakeApi()
    api.states.ai = { apps: [app({ id: 'a' }), app({ id: 'b' })], busy: 'a', restartPending: [], notice: null }
    const vm = new AiViewModel(api)
    await settle()
    expect(vm.getSnapshot().cards.map((c) => [c.action?.label, c.action?.disabled])).toEqual([
      ['One moment...', true],
      ['Connect', true]
    ])
  })
})

describe('AiViewModel: opening the app', () => {
  const app = (patch: Partial<AiApp>): AiApp => ({
    id: 'claude-desktop', name: 'Claude Desktop', blurb: '', free: false, download_url: 'https://x',
    connectable: true, available: true, installed: true, connected: true, finish_hint: 'Quit and reopen it.',
    advice: '', examples: [], openable: true, running: false, can_restart: true, installable: true, ...patch
  })

  async function cardFor(patch: Partial<AiApp>, restartPending: string[] = []) {
    const api = new FakeApi()
    api.states.ai = { apps: [app(patch)], busy: null, restartPending, notice: null }
    const vm = new AiViewModel(api)
    await settle()
    return { api, vm, card: vm.getSnapshot().cards[0] }
  }

  it('offers to open a connected app', async () => {
    const { api, vm, card } = await cardFor({})
    expect(card.open).toEqual({ label: 'Open Claude Desktop', kind: 'open', disabled: false })
    vm.openApp('claude-desktop')
    expect(api.calls).toEqual([{ model: 'ai', command: 'open', args: ['claude-desktop'] }])
  })

  it('offers a restart when the app was open while it got connected', async () => {
    const { api, vm, card } = await cardFor({ running: true }, ['claude-desktop'])
    expect(card.open).toMatchObject({ label: 'Restart Claude Desktop', kind: 'restart' })
    vm.openApp('claude-desktop')
    expect(api.called()).toEqual(['ai.restart'])
  })

  it("shows no button when it isn't connected or can't be found", async () => {
    expect((await cardFor({ connected: false })).card.open).toBeNull()
    expect((await cardFor({ openable: false })).card.open).toBeNull()
  })

  it('says to restart instead of the general hint while a restart is pending', async () => {
    const api = new FakeApi()
    api.states.ai = {
      apps: [app({ running: true })],
      busy: null,
      restartPending: ['claude-desktop'],
      notice: { appId: 'claude-desktop', kind: 'info', text: 'Quit and reopen it.' }
    }
    const vm = new AiViewModel(api)
    await settle()
    expect(vm.getSnapshot().cards[0].notice?.text).toContain('click "Restart Claude Desktop"')
  })
})

describe('LogsViewModel', () => {
  it('shows history plus new lines, and filters them', async () => {
    const api = new FakeApi()
    api.results['logs.history'] = [[{ text: 'Kill: FatPad killed PadGirl', color: null }]]
    const vm = new LogsViewModel(api)
    await settle()
    api.pushLogs({ type: 'append', lines: [[{ text: 'Say: hello', color: null }]] })
    expect(vm.getSnapshot().total).toBe(2)
    vm.setFilter('say')
    expect(vm.getSnapshot().rows).toHaveLength(1)
    vm.setFilter('nothing like this')
    expect(vm.getSnapshot().emptyText).toContain('No lines with')
    api.pushLogs({ type: 'reset' })
    vm.setFilter('')
    expect(vm.getSnapshot().emptyText).toContain('Start the server')
  })
})

describe('ServerViewModel: Play and how others join', () => {
  it('grays out Play while the game is open', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ status: running })
    const vm = new ServerViewModel(api)
    await settle()
    expect(vm.getSnapshot().play).toEqual({ label: 'Play World of PADMAN', disabled: false })
    vm.play()
    expect(api.called()).toEqual(['server.play'])
    api.push('server', serverState({ status: running, playing: true }))
    expect(vm.getSnapshot().play).toEqual({ label: 'Running...', disabled: true })
    vm.play()
    expect(api.called()).toEqual(['server.play'])
  })

  it('explains joining from home in three steps with the server name', async () => {
    const api = new FakeApi()
    api.states.server = serverState({ status: running, joinInfo: join })
    const vm = new ServerViewModel(api)
    await settle()
    expect(vm.getSnapshot().join?.lanSteps).toEqual(['Open Multiplayer', 'Set the source to LAN', 'Pick Bro night and join'])
    expect(vm.getSnapshot().join?.passwordLine).toBe('/password pad123')
    api.push('server', serverState({ status: running, joinInfo: { ...join, join_password: null } }))
    expect(vm.getSnapshot().join?.passwordLine).toBeNull()
  })

  it('shows one internet-play state at a time', async () => {
    const api = new FakeApi()
    const vm = new ServerViewModel(api)
    await settle()
    const states: [Partial<OnlineStatus>, string][] = [
      [{ enabled: false, phase: 'off', address: null, port: null }, 'off'],
      [{ phase: 'approving', approve_url: 'https://playit.gg/claim/x', address: null, port: null }, 'approving'],
      [{ phase: 'server_off', address: null, port: null }, 'waiting'],
      [{}, 'ready']
    ]
    for (const [patch, state] of states) {
      api.push('server', serverState({ status: running, joinInfo: join, online: online(patch) }))
      expect(vm.getSnapshot().online?.state).toBe(state)
    }
  })
})

describe('GameViewModel', () => {
  const mode = (patch: Partial<GameModeInfo>): GameModeInfo => ({
    id: 6, key: 'tffa', name: 'Team Free For All', team_mode: true, description: 'Team deathmatch.',
    maps: ['wop_padgarden', 'wop_padkitchen', 'wop_padship'], default_map: 'wop_padgarden', default_pointlimit: 64,
    default_timelimit: 16, default_red: ['PADMAN', 'PadGirl'], default_blue: ['FatPad'], default_bots: [], ...patch
  })
  const catalog: GameCatalog = {
    modes: [
      mode({}),
      mode({ id: 8, key: 'ctl', name: 'Capture The Lolly', maps: ['wop_padbaseCTL', 'wop_journeyCTL', 'wop_fridgeCTL'],
        default_map: 'wop_padbaseCTL', default_pointlimit: 8, default_red: ['PADMAN'], default_blue: ['PadKing'] }),
      mode({ id: 0, key: 'ffa', name: 'Free For All', team_mode: false, default_map: 'wop_padgarden',
        default_pointlimit: 32, default_red: [], default_blue: [], default_bots: ['PADMAN', 'PadGirl', 'PadKing'] })
    ],
    bots: ['PADMAN', 'PadGirl', 'PadKing', 'FatPad']
  }

  async function gameTab(status: ServerStatus = running, rotation: string[] | null = null) {
    const api = new FakeApi()
    api.states.server = serverState({ status })
    api.states.game = gameState({ catalog, rotation })
    const vm = new GameViewModel(api)
    await settle()
    api.calls = []    // the tab asks for the map loop when it opens
    return { api, vm }
  }

  const picked = (vm: GameViewModel) =>
    vm.getSnapshot().draft!.maps.filter((m) => m.order !== null).sort((a, b) => a.order! - b.order!).map((m) => m.id)

  it('asks which maps play in a loop when it opens', async () => {
    const api = new FakeApi()
    new GameViewModel(api)
    expect(api.called()).toEqual(['game.loadRotation'])
  })

  it('shows what is playing now, with the map loop', async () => {
    const { vm } = await gameTab(running, ['wop_padbaseCTL', 'wop_journeyCTL'])
    expect(vm.getSnapshot()).toMatchObject({
      serverOn: true,
      nowPlaying: { mode: 'Capture The Lolly', map: 'padbase CTL', weapons: 'InstaPad (one hit wins)',
        limits: 'first to 8 points or 15 minutes', people: '1 player and 2 bots',
        loop: 'Maps in a loop: padbase CTL → journey CTL' }
    })
  })

  it('starts the new game from the current mode and its map loop', async () => {
    const { vm } = await gameTab(running, ['wop_padbaseCTL', 'wop_fridgeCTL'])
    const draft = vm.getSnapshot().draft!
    expect(draft.modes.find((m) => m.selected)?.name).toBe('Capture The Lolly')
    expect(picked(vm)).toEqual(['wop_padbaseCTL', 'wop_fridgeCTL'])
    expect(draft.loopText).toBe('padbase CTL → fridge CTL, then from the start again.')
    expect(draft.lists.map((l) => [l.label, l.bots])).toEqual([['Red Pads', ['PADMAN']], ['Blue Noses', ['PadKing']]])
    expect(draft.points).toMatchObject({ text: '8', note: '' })
    expect(vm.getSnapshot().footer.apply).toEqual({ label: 'Apply changes', disabled: false })
  })

  it('picks maps for a loop in the order they are clicked, but never none', async () => {
    const { vm } = await gameTab()
    expect(picked(vm)).toEqual(['wop_padbaseCTL'])
    expect(vm.getSnapshot().draft!.loopText).toBe('Only padbase CTL: every match is on this map.')
    vm.toggleMap('wop_fridgeCTL')
    vm.toggleMap('wop_journeyCTL')
    expect(picked(vm)).toEqual(['wop_padbaseCTL', 'wop_fridgeCTL', 'wop_journeyCTL'])
    expect(vm.getSnapshot().draft!.maps.map((m) => m.order)).toEqual([1, 3, 2])
    vm.toggleMap('wop_padbaseCTL')
    vm.toggleMap('wop_fridgeCTL')
    vm.toggleMap('wop_journeyCTL')     // the last one stays
    expect(picked(vm)).toEqual(['wop_journeyCTL'])
    vm.toggleMap('wop_padgarden')      // doesn't fit Capture The Lolly
    expect(picked(vm)).toEqual(['wop_journeyCTL'])
  })

  it('picking a mode brings its usual map, bots and limits', async () => {
    const { vm } = await gameTab()
    vm.toggleMap('wop_journeyCTL')
    vm.pickMode('ffa')
    const draft = vm.getSnapshot().draft!
    expect(picked(vm)).toEqual(['wop_padgarden'])
    expect(draft.lists).toEqual([{ id: 'bots', label: 'Bots', tone: 'none', bots: ['PADMAN', 'PadGirl', 'PadKing'] }])
    expect(draft.points.text).toBe('32')
  })

  it('keeps the match limits valid while typing', async () => {
    const { vm } = await gameTab()
    vm.typeLimit('points', '1a2')
    expect(vm.getSnapshot().draft!.points).toMatchObject({ text: '12', note: '' })
    vm.typeLimit('points', '')
    expect(vm.getSnapshot().draft!.points.text).toBe('')      // still typing
    vm.commitLimit('points')
    expect(vm.getSnapshot().draft!.points.text).toBe('12')    // empty goes back to the last number
    vm.typeLimit('minutes', '99999')
    expect(vm.getSnapshot().draft!.minutes.text).toBe('999')
    vm.stepLimit('minutes', 1)
    expect(vm.getSnapshot().draft!.minutes).toMatchObject({ text: '999', canRaise: false })
    vm.typeLimit('minutes', '0')
    vm.commitLimit('minutes')
    vm.stepLimit('minutes', -1)
    expect(vm.getSnapshot().draft!.minutes).toMatchObject({ text: '0', note: 'no limit', canLower: false })
    expect(vm.getSnapshot().draft!.limitsHint).toBeNull()
    vm.typeLimit('points', '0')
    expect(vm.getSnapshot().draft!.limitsHint).toContain('never ends')
  })

  it('applies the chosen game, with the maps in their order', async () => {
    const { api, vm } = await gameTab()
    vm.addBot('blue', 'FatPad')
    vm.removeBot('red', 0)
    vm.setSkill(5)
    vm.typeLimit('points', '3')       // applied even without leaving the box
    vm.typeLimit('minutes', '10')
    vm.toggleMap('wop_journeyCTL')
    vm.apply()
    expect(api.calls.at(-1)).toEqual({
      model: 'game', command: 'apply', args: [{ gamemode: 'ctl', maps: ['wop_padbaseCTL', 'wop_journeyCTL'],
        weapons: 'instapad', spawnProtection: true, red: [],
        blue: ['PadKing', 'FatPad'], bots: [], skill: 5, pointlimit: 3, timelimit: 10 }]
    })
    vm.resetDraft()
    expect(vm.getSnapshot().draft!.lists.map((l) => l.bots)).toEqual([['PADMAN'], ['PadKing']])
    expect(picked(vm)).toEqual(['wop_padbaseCTL'])
  })

  it('counts the places and stops at a full server', async () => {
    const { api, vm } = await gameTab({ ...running, slots: { max: 4, used: 3, free: 1 } })
    expect(vm.getSnapshot().draft!.places).toEqual({ text: '2 bots and 1 player: 3 of 4 places', full: false })
    vm.addBot('red', 'PadGirl')
    expect(vm.getSnapshot().draft!.canAddBot).toBe(false)
    vm.addBot('red', 'FatPad')
    expect(vm.getSnapshot().draft!.lists[0].bots).toEqual(['PADMAN', 'PadGirl'])
    api.push('server', serverState({ status: { ...running, slots: { max: 3, used: 3, free: 0 } } }))
    expect(vm.getSnapshot().draft!.places.full).toBe(true)
    expect(vm.getSnapshot().footer).toMatchObject({ apply: { disabled: true }, warn: true })
    expect(vm.getSnapshot().footer.hint).toContain('than the 3 places')
  })

  it('needs a running server to change the game', async () => {
    const { api, vm } = await gameTab({ running: false, port: 27960, server_name: 'x' })
    expect(vm.getSnapshot()).toMatchObject({ serverOn: false, nowPlaying: null, canSend: false })
    expect(vm.getSnapshot().footer).toMatchObject({
      restart: { disabled: true }, apply: { disabled: true }, save: { disabled: true }
    })
    expect(vm.getSnapshot().footer.hint).toContain('Start the server')
    expect(vm.getSnapshot().draft!.modes.find((m) => m.selected)?.key).toBe('tffa')
    vm.apply()
    vm.restartMatch()
    vm.saveAsStartup()
    vm.startServer()
    expect(api.called()).toEqual(['server.start'])
    api.push('server', serverState({ status: running }))
    expect(api.called()).toEqual(['server.start', 'game.loadRotation'])   // it came on: which maps loop now?
  })

  it('sends a message, restarts the match and saves the game as the default', async () => {
    const { api, vm } = await gameTab()
    expect(vm.getSnapshot().canSend).toBe(false)
    vm.setMessage('  Dinner is ready!  ')
    vm.sendMessage()
    vm.restartMatch()
    vm.saveAsStartup()
    expect(api.calls).toEqual([
      { model: 'game', command: 'sendMessage', args: ['Dinner is ready!'] },
      { model: 'game', command: 'restartMatch', args: [] },
      { model: 'game', command: 'saveAsStartup', args: [] }
    ])
    expect(vm.getSnapshot().message).toBe('')
    expect(vm.getSnapshot().footer).toMatchObject({
      restart: { label: 'Restart match' }, save: { label: 'Save as default' }
    })
  })

  it('waits while something runs', async () => {
    const { api, vm } = await gameTab()
    api.push('game', gameState({ catalog, busy: 'applying' }))
    expect(vm.getSnapshot().footer).toMatchObject({
      apply: { label: 'Applying...', disabled: true }, restart: { disabled: true }, save: { disabled: true }
    })
    vm.restartMatch()
    vm.saveAsStartup()
    vm.apply()
    expect(api.calls).toEqual([])
  })

  describe('weapons', () => {
    const settings = (patch: Partial<GameSettings> = {}): GameSettings => ({
      running: true, instapad: false, spawn_protection: true, spawn_protection_seconds: 3,
      spawn_protection_changeable: true, ...patch
    })

    async function weaponsTab(patch: Partial<GameSettings> = {}) {
      const api = new FakeApi()
      api.states.server = serverState({ status: running, settings: settings(patch) })
      api.states.game = gameState({ catalog })
      const vm = new GameViewModel(api)
      await settle()
      api.calls = []
      return { api, vm }
    }

    it('starts from what the server uses, and protection only shows with InstaPad', async () => {
      const { vm } = await weaponsTab()
      expect(vm.getSnapshot().weapons?.options.map((o) => [o.label, o.selected])).toEqual([
        ['All weapons', true], ['InstaPad (one hit wins)', false]
      ])
      expect(vm.getSnapshot().weapons?.note).toBe('Takes effect when you press Apply changes.')
      expect(vm.getSnapshot().spawnProtection).toBeNull()
      expect(vm.getSnapshot().footer.pending).toBe(false)
    })

    it('changes only the page until Apply changes', async () => {
      const { api, vm } = await weaponsTab()
      vm.chooseWeapons('regular')                 // already chosen: nothing changes
      expect(vm.getSnapshot().footer.pending).toBe(false)
      vm.chooseWeapons('instapad')
      expect(vm.getSnapshot().spawnProtection).toEqual({
        on: true, label: 'Protection after respawning', disabled: false,
        hint: "Players can't be hurt for 3 seconds after they respawn."
      })
      vm.toggleSpawnProtection()
      expect(vm.getSnapshot().spawnProtection?.hint).toBe('Players can be hit right after they respawn.')
      expect(api.calls).toEqual([])               // nothing sent to the server yet
      expect(vm.getSnapshot().footer).toMatchObject({ pending: true, hint: expect.stringContaining('Apply changes') })
      vm.apply()
      expect(api.calls.at(-1)).toMatchObject({
        model: 'game', command: 'apply', args: [{ weapons: 'instapad', spawnProtection: false }]
      })
      expect(vm.getSnapshot().footer.pending).toBe(false)
    })

    it('every change on the page waits for Apply changes', async () => {
      const { api, vm } = await weaponsTab()
      vm.toggleMap('wop_journeyCTL')
      expect(vm.getSnapshot().footer.pending).toBe(true)
      expect(api.calls).toEqual([])
    })

    it('keeps the weapons when another mode is picked', async () => {
      const { vm } = await weaponsTab({ instapad: true, spawn_protection: false })
      vm.pickMode('ffa')
      expect(vm.getSnapshot().weapons?.options.find((o) => o.selected)?.id).toBe('instapad')
      expect(vm.getSnapshot().spawnProtection?.on).toBe(false)
    })

    it('explains when protection can only change after a restart', async () => {
      const { vm } = await weaponsTab({ instapad: true, spawn_protection_changeable: false })
      expect(vm.getSnapshot().spawnProtection).toMatchObject({
        disabled: true, hint: 'Can be changed after the server restarts once.'
      })
      vm.toggleSpawnProtection()
      expect(vm.getSnapshot().spawnProtection?.on).toBe(true)
    })

    it('waits while the game is being changed', async () => {
      const { api, vm } = await weaponsTab({ instapad: true })
      api.push('game', gameState({ catalog, busy: 'applying' }))
      expect(vm.getSnapshot().weapons?.disabled).toBe(true)
      vm.chooseWeapons('regular')
      vm.toggleSpawnProtection()
      expect(vm.getSnapshot().weapons?.options.find((o) => o.selected)?.id).toBe('instapad')
    })
  })
})
