import type { NetworkState, Notice, Player, ServerState, WopApi } from '@shared/api'
import { describeNetwork, type NetworkView } from './network'
import { ViewModel } from './ViewModel'

export interface Clipboard {
  write(text: string): Promise<void>
}

export const browserClipboard: Clipboard = {
  write: (text) => navigator.clipboard.writeText(text)
}

export interface PlayerRow {
  key: string
  name: string
  kind: 'Player' | 'Bot'
  team: string
  teamTone: 'red' | 'blue' | 'none'
  score: number
}

export interface ServerView {
  power: {
    on: boolean
    known: boolean
    busy: boolean
    headline: string
    buttonLabel: string
    tone: 'on' | 'off' | 'busy'
    hint: string
  }
  game: { mode: string; map: string; weapons: string; limits: string } | null
  playersSummary: string
  players: PlayerRow[]
  join: {
    serverName: string
    addresses: { address: string; connection: string; primary: boolean }[]
    port: string
    connectLine: string | null
    password: string | null
    passwordLine: string | null
    steps: string[]
    downloadUrl: string
    warning: string | null
  } | null
  network: NetworkView
  weapons: {
    options: { id: 'regular' | 'instapad'; label: string; selected: boolean }[]
    note: string
    disabled: boolean
  } | null
  /** Only with InstaPad. */
  spawnProtection: { on: boolean; label: string; hint: string; disabled: boolean } | null
  /** Friends somewhere else, over the internet; null where it isn't available (Mac). */
  online: {
    on: boolean
    busy: boolean
    label: string
    hint: string
    /** Waiting for the host to approve it on playit.gg. */
    approveUrl: string | null
    address: string | null
    port: string | null
    connectLine: string | null
    note: string | null
    problem: string | null
    passwordTip: string | null
  } | null
  notice: Notice | null
  copied: string | null
  saving: boolean
  editingName: boolean
  nameDraft: string
  passwordDraft: string
}

const TEAMS: Record<Player['team'], { label: string; tone: PlayerRow['teamTone'] }> = {
  red: { label: 'Red Pads', tone: 'red' },
  blue: { label: 'Blue Noses', tone: 'blue' },
  spectator: { label: 'Watching', tone: 'none' },
  free: { label: '', tone: 'none' }
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

/** "wop_padkitchenLPS" -> "padkitchen LPS" */
export function mapLabel(map: string): string {
  return map.replace(/^wop_/, '').replace(/(CTL|LPS|BB)$/, ' $1')
}

/** The Server tab: on/off, what's playing, who's on, how others join, and whether they can. */
export class ServerViewModel extends ViewModel<ServerView> {
  private server: ServerState | null = null
  private network: NetworkState | null = null
  private copied: string | null = null
  private copiedTimer: ReturnType<typeof setTimeout> | null = null
  private editingName = false
  private nameDraft = ''
  private passwordDraft = ''

  constructor(api: WopApi, private readonly clipboard: Clipboard = browserClipboard) {
    super(api)
    this.mirror('server', (state) => (this.server = state))
    this.mirror('network', (state) => (this.network = state))
  }

  protected present(): ServerView {
    const status = this.server?.status ?? null
    const busy = this.server?.busy ?? null
    const on = Boolean(status?.running)
    let headline = on ? 'Your server is on' : 'Your server is off'
    if (!status) headline = 'Looking for your server...'
    if (busy === 'starting') headline = 'Starting your server...'
    if (busy === 'stopping') headline = 'Stopping your server...'

    const players = status?.players ?? []
    const humans = players.filter((p) => !p.bot).length
    const bots = players.length - humans
    const join = this.server?.joinInfo ?? null
    const suffix = join && join.port !== 27960 ? `:${join.port}` : ''

    return {
      power: {
        on,
        known: status !== null,
        busy: busy === 'starting' || busy === 'stopping',
        headline,
        buttonLabel: on ? 'Stop server' : 'Start server',
        tone: busy === 'starting' || busy === 'stopping' ? 'busy' : on ? 'on' : 'off',
        hint: on || !status ? '' : 'Turn it on and everyone on your network can join.'
      },
      game:
        on && status?.gamemode
          ? {
              mode: status.gamemode.name,
              map: mapLabel(status.map ?? ''),
              weapons: status.weapons === 'instapad' ? 'InstaPad (one hit wins)' : 'All weapons',
              limits: [
                status.pointlimit ? `first to ${status.pointlimit} points` : '',
                status.timelimit_minutes ? `${status.timelimit_minutes} minutes` : ''
              ].filter(Boolean).join(' or ') || 'no limit'
            }
          : null,
      playersSummary: on
        ? `${plural(humans, 'player')} and ${plural(bots, 'bot')}` +
          (status?.slots ? ` · ${status.slots.free} of ${status.slots.max} places free` : '')
        : '',
      players: players.map((p) => ({
        key: String(p.num),
        name: p.name,
        kind: p.bot ? 'Bot' : 'Player',
        team: TEAMS[p.team]?.label ?? '',
        teamTone: TEAMS[p.team]?.tone ?? 'none',
        score: p.score
      })),
      join: join && {
        serverName: join.server_name,
        addresses: join.addresses.map((a, i) => ({ ...a, primary: i === 0 })),
        port: String(join.port),
        connectLine: join.addresses.length ? `/connect ${join.addresses[0].address}${suffix}` : null,
        password: join.join_password,
        passwordLine: join.join_password ? `/password ${join.join_password}` : null,
        steps: join.how_to_join,
        downloadUrl: join.download_url,
        warning: !join.addresses.length
          ? 'This computer doesn\'t seem to be connected to a network, so nobody else can join yet.'
          : !join.in_lan_list
            ? `Players won't see this server in the game's LAN list (port ${join.port}); they join with the /connect line.`
            : null
      },
      network: describeNetwork(this.network),
      ...this.presentSettings(busy !== null),
      online: this.presentOnline(),
      notice: this.server?.notice ?? null,
      copied: this.copied,
      saving: busy === 'saving',
      editingName: this.editingName,
      nameDraft: this.nameDraft,
      passwordDraft: this.passwordDraft
    }
  }

  toggle(): void {
    const view = this.getSnapshot()
    if (view.power.busy || !view.power.known) return
    void this.api.call('server', view.power.on ? 'stop' : 'start')
  }

  async copy(text: string): Promise<void> {
    try {
      await this.clipboard.write(text)
    } catch {
      return
    }
    this.copied = text
    this.changed()
    if (this.copiedTimer) clearTimeout(this.copiedTimer)
    this.copiedTimer = setTimeout(() => {
      this.copied = null
      this.changed()
    }, 2000)
  }

  editName(): void {
    this.editingName = true
    this.nameDraft = this.server?.joinInfo?.server_name ?? this.server?.status?.server_name ?? ''
    this.changed()
  }

  setNameDraft(name: string): void {
    this.nameDraft = name.slice(0, 40)
    this.changed()
  }

  cancelName(): void {
    this.editingName = false
    this.changed()
  }

  async saveName(): Promise<void> {
    const name = this.nameDraft.trim()
    if (!name) return
    this.editingName = false
    this.changed()
    await this.api.call('server', 'setName', name)
  }

  setPasswordDraft(password: string): void {
    this.passwordDraft = password.replace(/\s/g, '').slice(0, 32)
    this.changed()
  }

  async savePassword(): Promise<void> {
    const password = this.passwordDraft
    this.passwordDraft = ''
    this.changed()
    await this.api.call('server', 'setJoinPassword', password)
  }

  chooseWeapons(id: 'regular' | 'instapad'): void {
    const weapons = this.getSnapshot().weapons
    if (!weapons || weapons.disabled || weapons.options.find((o) => o.selected)?.id === id) return
    void this.api.call('server', 'setWeapons', id === 'instapad')
  }

  toggleSpawnProtection(): void {
    const protection = this.getSnapshot().spawnProtection
    if (!protection || protection.disabled) return
    void this.api.call('server', 'setSpawnProtection', !protection.on)
  }

  private presentSettings(busy: boolean): Pick<ServerView, 'weapons' | 'spawnProtection'> {
    const settings = this.server?.settings
    if (!settings) return { weapons: null, spawnProtection: null }
    const weapons: ServerView['weapons'] = {
      options: [
        { id: 'regular', label: 'All weapons', selected: !settings.instapad },
        { id: 'instapad', label: 'InstaPad (one hit wins)', selected: settings.instapad }
      ],
      note: settings.running ? 'Switching restarts the current match.' : 'Used when the server starts.',
      disabled: busy
    }
    if (!settings.instapad) return { weapons, spawnProtection: null }
    const seconds = settings.spawn_protection_seconds
    let hint = settings.spawn_protection
      ? `Players can't be hurt for ${seconds} seconds after they respawn.`
      : 'Players can be hit right after they respawn.'
    if (!settings.spawn_protection_changeable) {
      hint = settings.running
        ? 'Changes apply after the server restarts once.'
        : 'Not available with this version of World of PADMAN.'
    }
    return {
      weapons,
      spawnProtection: {
        on: settings.spawn_protection,
        label: 'Protection after respawning',
        hint,
        disabled: busy || (!settings.running && !settings.spawn_protection_changeable)
      }
    }
  }

  toggleOnline(): void {
    const online = this.getSnapshot().online
    if (!online || online.busy) return
    void this.api.call('server', 'setOnline', !online.on)
  }

  private presentOnline(): ServerView['online'] {
    const online = this.server?.online
    if (!online?.available) return null
    const on = online.enabled
    const ready = on && online.address !== null && online.port !== null
    const notes: Partial<Record<typeof online.phase, string>> = {
      approving: 'Approve it on playit.gg in your browser (the page just opened). It switches on right after.',
      starting: online.message,
      server_off: 'This works while the server is on.'
    }
    return {
      on,
      busy: this.server?.onlineBusy ?? false,
      label: 'Friends anywhere can join (over the internet)',
      hint: on
        ? 'Friends in another home join with the address and port below.'
        : 'Uses playit.gg (free). The first time, you approve it once in your browser.',
      approveUrl: online.phase === 'approving' ? online.approve_url : null,
      address: ready ? online.address : null,
      port: ready ? String(online.port) : null,
      connectLine: ready ? `/connect ${online.address}:${online.port}` : null,
      note: notes[online.phase] ?? null,
      problem: online.phase === 'problem' ? online.message : null,
      passwordTip: ready && !this.server?.joinInfo?.join_password
        ? 'Anyone with this address can join. Set a join password below to keep it to your friends.'
        : null
    }
  }

  async removePassword(): Promise<void> {
    await this.api.call('server', 'setJoinPassword', '')
  }

  play(): void {
    void this.api.call('server', 'play')
  }

  checkNetwork(): void {
    void this.api.call('network', 'check')
  }

  fixNetwork(): void {
    void this.api.call('network', 'fix')
  }

  openUrl(url: string): void {
    void this.api.call('app', 'openUrl', url)
  }

  dispose(): void {
    if (this.copiedTimer) clearTimeout(this.copiedTimer)
    super.dispose()
  }
}
