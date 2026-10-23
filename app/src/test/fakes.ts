import { EventEmitter } from 'node:events'
import type {
  AppState,
  CommandModel,
  LogChange,
  ModelName,
  ModelStates,
  NetworkState,
  ServerState,
  WopApi
} from '@shared/api'
import type { BridgeEvents } from '../main/bridge/BridgeClient'
import { BridgeError } from '../main/bridge/BridgeClient'

type Handler = (params: Record<string, unknown>) => unknown

/** Answers requests like appbridge.py would, from a table of handlers. */
export class FakeBridge extends EventEmitter<BridgeEvents> {
  calls: { method: string; params: Record<string, unknown> }[] = []
  started = 0
  stopped = 0

  constructor(public handlers: Record<string, Handler> = {}) {
    super()
  }

  start(): void {
    this.started++
  }

  stop(): void {
    this.stopped++
  }

  async request<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    this.calls.push({ method, params })
    const handler = this.handlers[method]
    if (!handler) throw new BridgeError(`no fake for ${method}`)
    return (await handler(params)) as T
  }

  methods(): string[] {
    return this.calls.map((c) => c.method)
  }
}

export const appState = (patch: Partial<AppState> = {}): AppState => ({
  phase: 'ready',
  hello: null,
  error: null,
  setup: { step: '', messages: [], percent: null, error: null },
  update: { available: false, version: '', busy: false },
  ...patch
})

export const serverState = (patch: Partial<ServerState> = {}): ServerState => ({
  status: null,
  joinInfo: null,
  settings: null,
  busy: null,
  notice: null,
  ...patch
})

export const networkState = (patch: Partial<NetworkState> = {}): NetworkState => ({
  check: null,
  busy: null,
  error: null,
  ...patch
})

const DEFAULTS: ModelStates = {
  app: appState(),
  server: serverState(),
  network: networkState(),
  commands: { entries: [], busy: false },
  ai: { apps: [], busy: null, restartPending: [], notice: null }
}

/** window.wop for ViewModel tests: push model states in, see which commands were called. */
export class FakeApi implements WopApi {
  states: ModelStates = structuredClone(DEFAULTS)
  calls: { model: string; command: string; args: unknown[] }[] = []
  results: Record<string, unknown> = {}
  private listeners = new Map<ModelName, Set<(state: never) => void>>()
  private logListeners = new Set<(change: LogChange) => void>()

  get<M extends ModelName>(model: M): Promise<ModelStates[M]> {
    return Promise.resolve(this.states[model])
  }

  onState<M extends ModelName>(model: M, listener: (state: ModelStates[M]) => void) {
    const set = this.listeners.get(model) ?? new Set()
    set.add(listener as (state: never) => void)
    this.listeners.set(model, set)
    return () => set.delete(listener as (state: never) => void)
  }

  call = ((model: CommandModel, command: string, ...args: unknown[]) => {
    this.calls.push({ model, command, args })
    return Promise.resolve(this.results[`${model}.${command}`])
  }) as WopApi['call']

  onLogs(listener: (change: LogChange) => void) {
    this.logListeners.add(listener)
    return () => this.logListeners.delete(listener)
  }

  push<M extends ModelName>(model: M, state: ModelStates[M]): void {
    this.states[model] = state
    for (const listener of this.listeners.get(model) ?? []) (listener as (s: ModelStates[M]) => void)(state)
  }

  pushLogs(change: LogChange): void {
    for (const listener of this.logListeners) listener(change)
  }

  called(): string[] {
    return this.calls.map((c) => `${c.model}.${c.command}`)
  }
}

/** Let pending promise callbacks run. */
export const settle = () => new Promise((resolve) => setTimeout(resolve, 0))
