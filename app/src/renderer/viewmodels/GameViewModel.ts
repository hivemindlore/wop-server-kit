import type { GameModeInfo, GameState, Notice, ServerState, WopApi } from '@shared/api'
import { mapLabel } from './ServerViewModel'
import { ViewModel } from './ViewModel'
import { describeWeapons, type SpawnProtectionView, type WeaponsView } from './weapons'

export type BotList = 'red' | 'blue' | 'bots'
export type Limit = 'points' | 'minutes'

const SKILLS: { value: number; label: string }[] = [
  { value: 1, label: 'Very easy' },
  { value: 2, label: 'Easy' },
  { value: 3, label: 'Normal' },
  { value: 4, label: 'Hard' },
  { value: 5, label: 'Very hard' }
]
const DEFAULT_PLACES = 16
const MAX_LIMIT = 999
const MAX_MAPS = 16

export interface LimitView {
  /** What's in the box (may be half typed). */
  text: string
  /** "no limit" at 0, otherwise empty. */
  note: string
  canLower: boolean
  canRaise: boolean
}

export interface GameView {
  notice: Notice | null
  /** null while it isn't known yet whether the server runs. */
  serverOn: boolean | null
  startingServer: boolean
  nowPlaying: { mode: string; map: string; weapons: string; limits: string; people: string; loop: string | null } | null
  busy: GameState['busy']
  message: string
  canSend: boolean
  sendLabel: string
  weapons: WeaponsView | null
  spawnProtection: SpawnProtectionView | null
  draft: {
    modes: { key: string; name: string; description: string; teamMode: boolean; selected: boolean }[]
    /** The maps that fit the mode; order is the place in the loop (1, 2, ...), null when not picked. */
    maps: { id: string; label: string; order: number | null }[]
    loopText: string
    lists: { id: BotList; label: string; tone: 'red' | 'blue' | 'none'; bots: string[] }[]
    botChoices: string[]
    canAddBot: boolean
    skills: { value: number; label: string; selected: boolean }[]
    points: LimitView
    minutes: LimitView
    limitsHint: string | null
    places: { text: string; full: boolean }
  } | null
  /** The bar that stays at the bottom of the Game tab. */
  footer: {
    restart: { label: string; disabled: boolean }
    apply: { label: string; disabled: boolean }
    save: { label: string; disabled: boolean; hint: string }
    hint: string
    warn: boolean
  }
}

interface Draft {
  mode: string
  maps: string[]
  red: string[]
  blue: string[]
  bots: string[]
  skill: number
  points: number
  minutes: number
}

function limitsText(points: number | undefined, minutes: number | undefined): string {
  return [points ? `first to ${points} points` : '', minutes ? `${minutes} minutes` : '']
    .filter(Boolean).join(' or ') || 'no limit'
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

function clampLimit(value: number): number {
  return Math.min(MAX_LIMIT, Math.max(0, Math.round(value)))
}

/**
 * The Game tab: what's playing now, a message to everyone, the weapons, and choosing a whole new game: mode,
 * one map or several in a loop, the bots and when a match ends. A bar at the bottom restarts the match, applies
 * the new game and keeps the current game as the one the server starts with.
 */
export class GameViewModel extends ViewModel<GameView> {
  private game: GameState | null = null
  private server: ServerState | null = null
  private draft: Draft | null = null
  private message = ''
  /** What's typed in the limit boxes, until it's committed (blur, Enter, Apply). */
  private typed: Partial<Record<Limit, string>> = {}

  constructor(api: WopApi) {
    super(api)
    this.mirror('game', (state) => {
      this.game = state
      this.startDraft()
    })
    this.mirror('server', (state) => {
      const wasOn = this.server?.status?.running
      this.server = state
      if (wasOn === false && state.status?.running) void this.api.call('game', 'loadRotation')
      this.startDraft()
    })
    void this.api.call('game', 'loadRotation')
  }

  protected present(): GameView {
    const status = this.server?.status ?? null
    const on = status ? status.running : null
    const busy = this.game?.busy ?? null
    const players = status?.players ?? []
    const humans = players.filter((p) => !p.bot).length
    const draft = this.presentDraft(humans)
    const rotation = this.game?.rotation ?? []
    let hint = 'Players stay connected; the map loads again and the bots are replaced.'
    let warn = false
    if (on === false) hint = 'Start the server on My server to change the game.'
    else if (draft?.places.full) {
      hint = `That's more players and bots than the ${status?.slots?.max ?? DEFAULT_PLACES} places. Take some bots out.`
      warn = true
    }
    return {
      notice: this.game?.notice ?? this.server?.notice ?? null,
      serverOn: on,
      startingServer: this.server?.busy === 'starting',
      nowPlaying: on && status?.gamemode
        ? {
            mode: status.gamemode.name,
            map: mapLabel(status.map ?? ''),
            weapons: status.weapons === 'instapad' ? 'InstaPad (one hit wins)' : 'All weapons',
            limits: limitsText(status.pointlimit, status.timelimit_minutes),
            people: `${plural(humans, 'player')} and ${plural(players.length - humans, 'bot')}`,
            loop: rotation.length > 1 ? `Maps in a loop: ${rotation.map(mapLabel).join(' → ')}` : null
          }
        : null,
      busy,
      message: this.message,
      canSend: on === true && busy === null && this.message.trim().length > 0,
      sendLabel: busy === 'sending' ? 'Sending...' : 'Send',
      ...describeWeapons(this.server?.settings, (this.server?.busy ?? null) !== null),
      draft,
      footer: {
        restart: { label: busy === 'restarting' ? 'Restarting...' : 'Restart match', disabled: on !== true || busy !== null },
        apply: {
          label: busy === 'applying' ? 'Applying...' : 'Apply changes',
          disabled: on !== true || busy !== null || !draft || draft.places.full
        },
        save: {
          label: busy === 'saving' ? 'Saving...' : 'Save as default',
          disabled: on !== true || busy !== null,
          hint: 'The server starts with the game that is playing now.'
        },
        hint,
        warn
      }
    }
  }

  private presentDraft(humans: number): GameView['draft'] {
    const catalog = this.game?.catalog
    const draft = this.draft
    const mode = draft && catalog?.modes.find((m) => m.key === draft.mode)
    if (!catalog || !draft || !mode) return null
    const places = this.server?.status?.slots?.max ?? DEFAULT_PLACES
    const bots = this.botCount()
    const used = bots + humans
    const lists: NonNullable<GameView['draft']>['lists'] = mode.team_mode
      ? [
          { id: 'red', label: 'Red Pads', tone: 'red', bots: draft.red },
          { id: 'blue', label: 'Blue Noses', tone: 'blue', bots: draft.blue }
        ]
      : [{ id: 'bots', label: 'Bots', tone: 'none', bots: draft.bots }]
    const names = draft.maps.map(mapLabel)
    return {
      modes: catalog.modes.map((m) => ({
        key: m.key, name: m.name, description: m.description, teamMode: m.team_mode, selected: m.key === mode.key
      })),
      maps: mode.maps.map((id) => {
        const index = draft.maps.indexOf(id)
        return { id, label: mapLabel(id), order: index < 0 ? null : index + 1 }
      }),
      loopText: names.length === 1
        ? `Only ${names[0]}: every match is on this map.`
        : `${names.join(' → ')}, then from the start again.`,
      lists,
      botChoices: catalog.bots,
      canAddBot: used < places,
      skills: SKILLS.map((s) => ({ ...s, selected: s.value === draft.skill })),
      points: this.presentLimit('points'),
      minutes: this.presentLimit('minutes'),
      limitsHint: draft.points === 0 && draft.minutes === 0 ? 'With no limits at all, a match never ends.' : null,
      places: {
        text: humans
          ? `${plural(bots, 'bot')} and ${plural(humans, 'player')}: ${used} of ${places} places`
          : `${plural(bots, 'bot')}: ${used} of ${places} places`,
        full: used > places
      }
    }
  }

  private presentLimit(which: Limit): LimitView {
    const value = this.draft![which]
    return {
      text: this.typed[which] ?? String(value),
      note: value === 0 ? 'no limit' : '',
      canLower: value > 0,
      canRaise: value < MAX_LIMIT
    }
  }

  /** The first time the modes and the server are known: start from what's playing now. */
  private startDraft(): void {
    const catalog = this.game?.catalog
    if (this.draft || !catalog?.modes.length) return
    const status = this.server?.status
    if (status === null || status === undefined) return
    const current = status.gamemode && catalog.modes.find((m) => m.id === status.gamemode!.id)
    const mode = current ?? catalog.modes.find((m) => m.key === 'tffa') ?? catalog.modes[0]
    this.draft = this.defaults(mode)
    if (current) {
      const loop = (this.game?.rotation ?? []).filter((m) => mode.maps.includes(m))
      if (loop.length) this.draft.maps = loop
      else if (status.map && mode.maps.includes(status.map)) this.draft.maps = [status.map]
      this.draft.points = status.pointlimit ?? this.draft.points
      this.draft.minutes = status.timelimit_minutes ?? this.draft.minutes
    }
  }

  private defaults(mode: GameModeInfo): Draft {
    return {
      mode: mode.key,
      maps: [mode.default_map],
      red: [...mode.default_red],
      blue: [...mode.default_blue],
      bots: [...mode.default_bots],
      skill: this.draft?.skill ?? 3,
      points: mode.default_pointlimit,
      minutes: mode.default_timelimit
    }
  }

  private botCount(): number {
    const d = this.draft
    if (!d) return 0
    const mode = this.game?.catalog?.modes.find((m) => m.key === d.mode)
    return mode?.team_mode ? d.red.length + d.blue.length : d.bots.length
  }

  private modeInfo(key: string): GameModeInfo | undefined {
    return this.game?.catalog?.modes.find((m) => m.key === key)
  }

  pickMode(key: string): void {
    const mode = this.modeInfo(key)
    if (!mode || this.draft?.mode === key) return
    this.draft = this.defaults(mode)
    this.typed = {}
    this.changed()
  }

  /** Adds the map at the end of the loop, or takes it out (the last one stays). */
  toggleMap(map: string): void {
    const mode = this.draft && this.modeInfo(this.draft.mode)
    if (!this.draft || !mode?.maps.includes(map)) return
    const maps = this.draft.maps
    if (maps.includes(map)) {
      if (maps.length === 1) return
      this.draft = { ...this.draft, maps: maps.filter((m) => m !== map) }
    } else {
      if (maps.length >= MAX_MAPS) return
      this.draft = { ...this.draft, maps: [...maps, map] }
    }
    this.changed()
  }

  addBot(list: BotList, name: string): void {
    if (!this.draft || !name || !this.getSnapshot().draft?.canAddBot) return
    this.draft = { ...this.draft }
    this.draft[list] = [...this.draft[list], name]
    this.changed()
  }

  removeBot(list: BotList, index: number): void {
    if (!this.draft) return
    this.draft = { ...this.draft }
    this.draft[list] = this.draft[list].filter((_, i) => i !== index)
    this.changed()
  }

  setSkill(skill: number): void {
    if (!this.draft || !SKILLS.some((s) => s.value === skill)) return
    this.draft = { ...this.draft, skill }
    this.changed()
  }

  /** Typing in a limit box: only digits, at most three. */
  typeLimit(which: Limit, text: string): void {
    if (!this.draft) return
    const digits = text.replace(/\D/g, '').slice(0, 3)
    this.typed = { ...this.typed, [which]: digits }
    if (digits) this.draft = { ...this.draft, [which]: clampLimit(Number(digits)) }
    this.changed()
  }

  /** Leaving the box (or Enter): an empty box goes back to the last number. */
  commitLimit(which: Limit): void {
    if (this.typed[which] === undefined) return
    const { [which]: _, ...rest } = this.typed
    this.typed = rest
    this.changed()
  }

  stepLimit(which: Limit, by: number): void {
    if (!this.draft) return
    const { [which]: _, ...rest } = this.typed
    this.typed = rest
    this.draft = { ...this.draft, [which]: clampLimit(this.draft[which] + by) }
    this.changed()
  }

  /** Back to the usual maps, bots and limits of the chosen mode. */
  resetDraft(): void {
    const mode = this.draft && this.modeInfo(this.draft.mode)
    if (!mode) return
    this.draft = this.defaults(mode)
    this.typed = {}
    this.changed()
  }

  apply(): void {
    this.typed = {}
    this.changed()
    const d = this.draft
    if (!d || this.getSnapshot().footer.apply.disabled) return
    const team = this.modeInfo(d.mode)?.team_mode ?? false
    void this.api.call('game', 'apply', {
      gamemode: d.mode,
      maps: d.maps,
      red: team ? d.red : [],
      blue: team ? d.blue : [],
      bots: team ? [] : d.bots,
      skill: d.skill,
      pointlimit: d.points,
      timelimit: d.minutes
    })
  }

  setMessage(text: string): void {
    this.message = text.slice(0, 150)
    this.changed()
  }

  sendMessage(): void {
    if (!this.getSnapshot().canSend) return
    const text = this.message.trim()
    this.message = ''
    this.changed()
    void this.api.call('game', 'sendMessage', text)
  }

  restartMatch(): void {
    if (this.getSnapshot().footer.restart.disabled) return
    void this.api.call('game', 'restartMatch')
  }

  saveAsStartup(): void {
    if (this.getSnapshot().footer.save.disabled) return
    void this.api.call('game', 'saveAsStartup')
  }

  startServer(): void {
    if (this.server?.busy) return
    void this.api.call('server', 'start')
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
}
