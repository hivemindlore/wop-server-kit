import type { GameModeInfo, GameState, Notice, ServerState, WopApi } from '@shared/api'
import { mapLabel } from './ServerViewModel'
import { ViewModel } from './ViewModel'
import { describeWeapons, type SpawnProtectionView, type WeaponsView } from './weapons'

export type BotList = 'red' | 'blue' | 'bots'

const SKILLS: { value: number; label: string }[] = [
  { value: 1, label: 'Very easy' },
  { value: 2, label: 'Easy' },
  { value: 3, label: 'Normal' },
  { value: 4, label: 'Hard' },
  { value: 5, label: 'Very hard' }
]
const DEFAULT_PLACES = 16
const MAX_LIMIT = 999

export interface GameView {
  notice: Notice | null
  /** null while it isn't known yet whether the server runs. */
  serverOn: boolean | null
  startingServer: boolean
  nowPlaying: { mode: string; map: string; weapons: string; limits: string; people: string } | null
  busy: GameState['busy']
  message: string
  canSend: boolean
  weapons: WeaponsView | null
  spawnProtection: SpawnProtectionView | null
  draft: {
    modes: { key: string; name: string; description: string; teamMode: boolean; selected: boolean }[]
    maps: { id: string; label: string; selected: boolean }[]
    lists: { id: BotList; label: string; tone: 'red' | 'blue' | 'none'; bots: string[] }[]
    botChoices: string[]
    canAddBot: boolean
    skills: { value: number; label: string; selected: boolean }[]
    points: number
    minutes: number
    places: { text: string; full: boolean }
    canApply: boolean
    applyLabel: string
    hint: string
  } | null
}

interface Draft {
  mode: string
  map: string
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

/**
 * The Game tab: what's playing now (restart the match, a message to everyone, keep it as the startup game),
 * the weapons, and choosing a whole new game: mode, a map that fits it, the bots and when a match ends.
 */
export class GameViewModel extends ViewModel<GameView> {
  private game: GameState | null = null
  private server: ServerState | null = null
  private draft: Draft | null = null
  private message = ''

  constructor(api: WopApi) {
    super(api)
    this.mirror('game', (state) => {
      this.game = state
      this.startDraft()
    })
    this.mirror('server', (state) => {
      this.server = state
      this.startDraft()
    })
  }

  protected present(): GameView {
    const status = this.server?.status ?? null
    const on = status ? status.running : null
    const busy = this.game?.busy ?? null
    const players = status?.players ?? []
    const humans = players.filter((p) => !p.bot).length
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
            people: `${plural(humans, 'player')} and ${plural(players.length - humans, 'bot')}`
          }
        : null,
      busy,
      message: this.message,
      canSend: on === true && busy === null && this.message.trim().length > 0,
      ...describeWeapons(this.server?.settings, (this.server?.busy ?? null) !== null),
      draft: this.presentDraft(on === true, busy, humans)
    }
  }

  private presentDraft(on: boolean, busy: GameState['busy'], humans: number): GameView['draft'] {
    const catalog = this.game?.catalog
    const draft = this.draft
    const mode = draft && catalog?.modes.find((m) => m.key === draft.mode)
    if (!catalog || !draft || !mode) return null
    const places = this.server?.status?.slots?.max ?? DEFAULT_PLACES
    const bots = this.botCount()
    const used = bots + humans
    const full = used > places
    const lists: NonNullable<GameView['draft']>['lists'] = mode.team_mode
      ? [
          { id: 'red', label: 'Red Pads', tone: 'red', bots: draft.red },
          { id: 'blue', label: 'Blue Noses', tone: 'blue', bots: draft.blue }
        ]
      : [{ id: 'bots', label: 'Bots', tone: 'none', bots: draft.bots }]
    let hint = 'Players stay connected; the map loads again and the bots are replaced.'
    if (!on) hint = 'Start the server first; then you can switch the game.'
    else if (full) hint = `That's more than the ${places} places on the server. Take some bots out.`
    return {
      modes: catalog.modes.map((m) => ({
        key: m.key, name: m.name, description: m.description, teamMode: m.team_mode, selected: m.key === mode.key
      })),
      maps: mode.maps.map((id) => ({ id, label: mapLabel(id), selected: id === draft.map })),
      lists,
      botChoices: catalog.bots,
      canAddBot: used < places,
      skills: SKILLS.map((s) => ({ ...s, selected: s.value === draft.skill })),
      points: draft.points,
      minutes: draft.minutes,
      places: {
        text: humans
          ? `${plural(bots, 'bot')} and ${plural(humans, 'player')}: ${used} of ${places} places`
          : `${plural(bots, 'bot')}: ${used} of ${places} places`,
        full
      },
      canApply: on && busy === null && !full,
      applyLabel: busy === 'applying' ? 'Starting the game...' : 'Start this game',
      hint
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
      if (status.map && mode.maps.includes(status.map)) this.draft.map = status.map
      this.draft.points = status.pointlimit ?? this.draft.points
      this.draft.minutes = status.timelimit_minutes ?? this.draft.minutes
    }
  }

  private defaults(mode: GameModeInfo): Draft {
    return {
      mode: mode.key,
      map: mode.default_map,
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
    this.changed()
  }

  pickMap(map: string): void {
    const mode = this.draft && this.modeInfo(this.draft.mode)
    if (!this.draft || !mode?.maps.includes(map)) return
    this.draft = { ...this.draft, map }
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

  setPoints(value: string): void {
    this.setLimit('points', value)
  }

  setMinutes(value: string): void {
    this.setLimit('minutes', value)
  }

  private setLimit(which: 'points' | 'minutes', value: string): void {
    if (!this.draft) return
    const number = Math.min(MAX_LIMIT, Math.max(0, Math.floor(Number(value) || 0)))
    this.draft = { ...this.draft }
    this.draft[which] = number
    this.changed()
  }

  /** Back to the usual map, bots and limits of the chosen mode. */
  resetDraft(): void {
    const mode = this.draft && this.modeInfo(this.draft.mode)
    if (!mode) return
    this.draft = this.defaults(mode)
    this.changed()
  }

  apply(): void {
    const view = this.getSnapshot().draft
    const d = this.draft
    if (!view?.canApply || !d) return
    const team = this.modeInfo(d.mode)?.team_mode ?? false
    void this.api.call('game', 'apply', {
      gamemode: d.mode,
      map: d.map,
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
    if (this.game?.busy) return
    void this.api.call('game', 'restartMatch')
  }

  saveAsStartup(): void {
    if (this.game?.busy) return
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
