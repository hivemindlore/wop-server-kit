import { describe, expect, it, vi } from 'vitest'
import type { AiApp, GameSettings, JoinInfo, NetworkCheck, ServerState, ServerStatus } from '@shared/api'
import { FakeApi, appState, networkState, serverState, settle } from '../../test/fakes'
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
  download_url: 'https://worldofpadman.net/en/download/'
}

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
    expect(vm.getSnapshot().step).toBe('network')
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
    openable: false, running: false, can_restart: false, ...patch
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
    advice: '', examples: [], openable: true, running: false, can_restart: true, ...patch
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
