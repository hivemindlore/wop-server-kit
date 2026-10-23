import { describe, expect, it, vi } from 'vitest'
import type {
  AiApp, GameSettings, JoinInfo, NetworkCheck, OnlineStatus, ServerState, ServerStatus
} from '@shared/api'
import { FakeApi, appState, networkState, serverState, settle, updateState } from '../../test/fakes'
import { AiViewModel } from './AiViewModel'
import { AppViewModel, type Storage } from './AppViewModel'
import { CommandsViewModel, QUICK_ACTIONS } from './CommandsViewModel'
import { LogsViewModel } from './LogsViewModel'
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

describe('ServerViewModel settings', () => {
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

  it('offers both weapons, and protection only with InstaPad', async () => {
    const { view } = await viewWith({})
    expect(view.weapons?.options.map((o) => [o.label, o.selected])).toEqual([
      ['All weapons', true], ['InstaPad (one hit wins)', false]
    ])
    expect(view.weapons?.note).toBe('Switching restarts the current match.')
    expect(view.spawnProtection).toBeNull()
    const off = await viewWith({ running: false })
    expect(off.view.weapons?.note).toBe('Used when the server starts.')
  })

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

  it('switches weapons, but not to what is already chosen', async () => {
    const { api, vm } = await viewWith({})
    vm.chooseWeapons('regular')
    vm.chooseWeapons('instapad')
    expect(api.calls).toEqual([{ model: 'server', command: 'setWeapons', args: [true] }])
  })

  it('toggles spawn protection in InstaPad', async () => {
    const { api, vm, view } = await viewWith({ instapad: true })
    expect(view.spawnProtection).toEqual({
      on: true, label: 'Protection after respawning', disabled: false,
      hint: "Players can't be hurt for 3 seconds after they respawn."
    })
    vm.toggleSpawnProtection()
    expect(api.calls).toEqual([{ model: 'server', command: 'setSpawnProtection', args: [false] }])
    const off = await viewWith({ instapad: true, spawn_protection: false, spawn_protection_seconds: 0 })
    expect(off.view.spawnProtection?.hint).toBe('Players can be hit right after they respawn.')
  })

  it('explains when protection can only change after a restart, or not at all', async () => {
    const old = await viewWith({ instapad: true, spawn_protection_changeable: false })
    expect(old.view.spawnProtection).toMatchObject({ disabled: false, hint: 'Changes apply after the server restarts once.' })
    const none = await viewWith({ instapad: true, running: false, spawn_protection_changeable: false })
    expect(none.view.spawnProtection?.disabled).toBe(true)
  })

  it('locks the settings while something is being saved', async () => {
    const { api, vm, view } = await viewWith({ instapad: true }, 'saving')
    expect(view.weapons?.disabled).toBe(true)
    vm.chooseWeapons('regular')
    vm.toggleSpawnProtection()
    expect(api.calls).toEqual([])
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

  it('remembers the open tab', async () => {
    const storage = memory()
    const vm = new AppViewModel(new FakeApi(), storage)
    vm.selectTab('logs')
    expect(storage.data.tab).toBe('logs')
    expect(new AppViewModel(new FakeApi(), storage).getSnapshot().activeTab).toBe('logs')
    storage.data.tab = 'nonsense'
    expect(new AppViewModel(new FakeApi(), storage).getSnapshot().activeTab).toBe('server')
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

  it('asks for the message before sending it', async () => {
    const api = new FakeApi()
    const vm = new CommandsViewModel(api)
    vm.quick(QUICK_ACTIONS.find((a) => a.id === 'say')!)
    expect(vm.getSnapshot().openAction).not.toBeNull()
    vm.setActionText('Dinner is ready!')
    vm.confirmAction()
    vm.quick(QUICK_ACTIONS.find((a) => a.id === 'restart')!)
    expect(api.calls.map((c) => c.args[0])).toEqual(['ssay Dinner is ready!', 'map_restart 0'])
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
