// The contract between the parts of the app. Data shapes mirror what kit/setup/appbridge.py returns;
// the model states are what the main process (the Model) pushes to the renderer (the ViewModels).

export const BRIDGE_PROTOCOL = 1

// ------------------------------------------------------------------ data from the kit

export interface Hello {
  protocol: number
  kit_version: string
  platform: 'windows' | 'mac' | 'linux'
  installed: boolean
  server_name: string
  default_server_name: string
  port: number
  root: string
}

export interface Player {
  num: number
  name: string
  team: 'free' | 'red' | 'blue' | 'spectator'
  bot: boolean
  score: number
  ping: number
  bot_type?: string | null
  skill?: number | null
}

export interface ServerStatus {
  running: boolean
  port: number
  server_name: string
  map?: string
  gamemode?: { id: number; name: string; team_mode: boolean }
  weapons?: 'regular' | 'instapad'
  /** Only with InstaPad. */
  spawn_protection_seconds?: number
  pointlimit?: number
  timelimit_minutes?: number
  slots?: { max: number; used: number; free: number }
  players?: Player[]
}

/** Weapons and InstaPad spawn protection: what the running server uses, or else what it starts with. */
export interface GameSettings {
  running: boolean
  instapad: boolean
  spawn_protection: boolean
  spawn_protection_seconds: number
  /** False on a server without the kit's game code (plain WoP 1.7.0 always protects 6 seconds). */
  spawn_protection_changeable: boolean
}

export interface JoinInfo {
  server_name: string
  running: boolean
  addresses: { address: string; connection: string }[]
  port: number
  join_password: string | null
  connect_commands: string[]
  how_to_join: string[]
  in_lan_list: boolean
  download_url: string
  /** The internet address, while internet play is on. */
  online: { address: string; port: number; connect_command: string } | null
}

/** Playing over the internet (friends on other networks join through playit.gg). */
export interface OnlineStatus {
  /** False where playit.gg has no program (Mac). */
  available: boolean
  enabled: boolean
  /** approving: waiting for the host to approve it in the browser; server_off: ready, the server is off. */
  phase: 'off' | 'approving' | 'starting' | 'server_off' | 'online' | 'problem'
  address: string | null
  port: number | null
  approve_url: string | null
  message: string
  /** Approved once on playit.gg (this install has its key). */
  approved: boolean
  result?: string
}

export interface NetworkCheck {
  checked: boolean
  ok: boolean
  problems: { text: string; fixable: boolean }[]
  can_fix: boolean
  permission_hint: string
  notes: string[]
  others: string[]
  firewall_name: string
  help_url: string
  accepted?: boolean
}

export interface LogSegment {
  text: string
  color: 'black' | 'red' | 'green' | 'yellow' | 'blue' | 'cyan' | 'magenta' | null
}
export type LogLine = LogSegment[]

export interface CommandResult {
  command: string
  output: string
}

export interface AiApp {
  id: string
  name: string
  blurb: string
  free: boolean
  download_url: string
  connectable: boolean
  available: boolean
  installed: boolean
  connected: boolean
  finish_hint: string
  advice: string
  examples: string[]
  /** Installed where the kit can open it (or, for Claude Code, a terminal can run it). */
  openable: boolean
  /** Open right now; only known for apps the kit can restart. */
  running: boolean
  can_restart: boolean
}

export interface UpdateCheck {
  available: boolean
  version: string
  current: string
}

// ------------------------------------------------------------------ model states

export interface Notice {
  kind: 'info' | 'error'
  text: string
}

export type AppPhase = 'starting' | 'needs-setup' | 'setting-up' | 'ready' | 'error'

export interface AppState {
  phase: AppPhase
  hello: Hello | null
  error: string | null
  setup: { step: string; messages: string[]; percent: number | null; error: string | null }
  update: { available: boolean; version: string; busy: boolean }
}

/** Updates of the app itself (the server kit's updates are in AppState.update). */
export interface UpdateState {
  /** manual: downloaded and opened; the user finishes it as message says (Mac). */
  phase: 'idle' | 'checking' | 'upToDate' | 'available' | 'downloading' | 'installing' | 'manual' | 'error'
  current: string
  /** The newer version, while there is one. */
  version: string
  percent: number | null
  message: string | null
}

export interface ServerState {
  status: ServerStatus | null
  joinInfo: JoinInfo | null
  settings: GameSettings | null
  online: OnlineStatus | null
  busy: 'starting' | 'stopping' | 'saving' | null
  /** Switching internet play on or off (on its own, so the server can be started meanwhile). */
  onlineBusy: boolean
  notice: Notice | null
}

export interface NetworkState {
  check: NetworkCheck | null
  busy: 'checking' | 'fixing' | null
  error: string | null
}

export interface CommandEntry {
  id: number
  command: string
  output: string
  failed: boolean
}

export interface CommandsState {
  entries: CommandEntry[]
  busy: boolean
}

export interface AiState {
  apps: AiApp[]
  busy: string | null
  /** Connected while they were open: they need a restart to see the server. */
  restartPending: string[]
  notice: (Notice & { appId: string }) | null
}

export interface ModelStates {
  app: AppState
  update: UpdateState
  server: ServerState
  network: NetworkState
  commands: CommandsState
  ai: AiState
}

export type ModelName = keyof ModelStates

// What the renderer may ask each model to do. The new state arrives through onState.
export interface ModelCommands {
  app: {
    startSetup(serverName: string): Promise<void>
    retry(): Promise<void>
    updateKit(): Promise<void>
    openUrl(url: string): Promise<void>
  }
  update: {
    check(): Promise<void>
    install(): Promise<void>
  }
  server: {
    start(): Promise<void>
    stop(): Promise<void>
    refresh(): Promise<void>
    setName(name: string): Promise<void>
    setJoinPassword(password: string): Promise<void>
    setWeapons(instapad: boolean): Promise<void>
    setSpawnProtection(on: boolean): Promise<void>
    setOnline(on: boolean): Promise<void>
    /** Opens playit.gg in the browser, to see and change the internet addresses. */
    manageOnline(): Promise<void>
    play(): Promise<void>
  }
  network: {
    check(): Promise<void>
    fix(): Promise<void>
  }
  commands: {
    run(command: string): Promise<void>
    clear(): Promise<void>
  }
  ai: {
    refresh(): Promise<void>
    connect(appId: string): Promise<void>
    disconnect(appId: string): Promise<void>
    open(appId: string): Promise<void>
    restart(appId: string): Promise<void>
  }
  logs: {
    history(): Promise<LogLine[]>
    openFolder(): Promise<void>
  }
}

export type CommandModel = keyof ModelCommands
export type CommandName<M extends CommandModel> = keyof ModelCommands[M] & string
type Fn = (...args: never[]) => unknown
export type CommandArgs<M extends CommandModel, C extends CommandName<M>> =
  ModelCommands[M][C] extends Fn ? Parameters<ModelCommands[M][C]> : never
export type CommandResultOf<M extends CommandModel, C extends CommandName<M>> =
  ModelCommands[M][C] extends Fn ? ReturnType<ModelCommands[M][C]> : never

export type LogChange = { type: 'append'; lines: LogLine[] } | { type: 'reset' }

export type Unsubscribe = () => void

/** window.wop: the only way the renderer talks to the rest of the app. */
export interface WopApi {
  get<M extends ModelName>(model: M): Promise<ModelStates[M]>
  onState<M extends ModelName>(model: M, listener: (state: ModelStates[M]) => void): Unsubscribe
  call<M extends CommandModel, C extends CommandName<M>>(model: M, command: C, ...args: CommandArgs<M, C>):
    CommandResultOf<M, C>
  onLogs(listener: (change: LogChange) => void): Unsubscribe
}

export const IPC = {
  get: 'wop:get',
  call: 'wop:call',
  state: 'wop:state',
  logs: 'wop:logs'
} as const
