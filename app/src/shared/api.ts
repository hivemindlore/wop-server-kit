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
  pointlimit?: number
  timelimit_minutes?: number
  slots?: { max: number; used: number; free: number }
  players?: Player[]
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

export interface ServerState {
  status: ServerStatus | null
  joinInfo: JoinInfo | null
  busy: 'starting' | 'stopping' | 'saving' | null
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
  notice: (Notice & { appId: string }) | null
}

export interface ModelStates {
  app: AppState
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
  server: {
    start(): Promise<void>
    stop(): Promise<void>
    refresh(): Promise<void>
    setName(name: string): Promise<void>
    setJoinPassword(password: string): Promise<void>
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
