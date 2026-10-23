import type { GameSettings, JoinInfo, ServerState, ServerStatus } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'
import { StateModel, messageOf } from './StateModel'

// The server answers only a few questions a second and Claude needs some too, so look every 5 s
export const POLL_MS = 5000

interface ActionResult {
  result?: string
}

/** Server on/off, what it's playing, how others join, and the weapons settings. */
export class ServerModel extends StateModel<ServerState> {
  private timer: ReturnType<typeof setInterval> | null = null
  private refreshing: Promise<void> | null = null

  constructor(private readonly bridge: Bridge) {
    super({ status: null, joinInfo: null, settings: null, busy: null, notice: null })
  }

  activate(): void {
    if (this.timer) return
    void this.refresh()
    void this.loadJoinInfo()
    void this.loadSettings()
    this.timer = setInterval(() => void this.refresh(), POLL_MS)
  }

  deactivate(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }

  refresh(): Promise<void> {
    this.refreshing ??= this.readStatus().finally(() => (this.refreshing = null))
    return this.refreshing
  }

  async start(): Promise<void> {
    await this.act('starting', 'server.start')
  }

  async stop(): Promise<void> {
    await this.act('stopping', 'server.stop')
  }

  async setName(name: string): Promise<void> {
    if (!name.trim()) return
    await this.act('saving', 'server.set_name', { name })
  }

  async setJoinPassword(password: string): Promise<void> {
    await this.act('saving', 'server.set_join_password', { password })
  }

  /** InstaPad or all weapons: changes the running server (restarting the match) and is kept for the next start. */
  async setWeapons(instapad: boolean): Promise<void> {
    await this.act('saving', 'settings.set_weapons', { instapad })
  }

  /** InstaPad's few seconds of not getting hurt after respawning. */
  async setSpawnProtection(on: boolean): Promise<void> {
    await this.act('saving', 'settings.set_spawn_protection', { on })
  }

  async play(): Promise<void> {
    try {
      const result = await this.bridge.request<ActionResult>('game.play')
      this.update({ notice: { kind: 'info', text: result.result ?? '' } })
    } catch (error) {
      this.update({ notice: { kind: 'error', text: messageOf(error) } })
    }
  }

  private async act(busy: NonNullable<ServerState['busy']>, method: string, params?: Record<string, unknown>) {
    if (this.getState().busy) return
    this.update({ busy, notice: null })
    try {
      const result = await this.bridge.request<ActionResult>(method, params)
      this.update({ notice: result.result ? { kind: 'info', text: result.result } : null })
    } catch (error) {
      this.update({ notice: { kind: 'error', text: messageOf(error) } })
    }
    await this.refreshing
    await this.readStatus()
    await this.loadJoinInfo()
    await this.loadSettings()
    this.update({ busy: null })
  }

  private async readStatus(): Promise<void> {
    try {
      const status = await this.bridge.request<ServerStatus>('server.status')
      const { status: before, settings } = this.getState()
      this.update({ status })
      if (before && before.running !== status.running) void this.loadJoinInfo()
      // Started, stopped, or changed by someone else (e.g. Claude): read the settings again
      const changed = settings && status.running &&
        ((status.weapons === 'instapad') !== settings.instapad ||
          (status.spawn_protection_seconds !== undefined &&
            status.spawn_protection_seconds !== settings.spawn_protection_seconds))
      if ((before && before.running !== status.running) || changed) void this.loadSettings()
    } catch {
      // the kit is restarting; the next poll tries again
    }
  }

  private async loadSettings(): Promise<void> {
    try {
      this.update({ settings: await this.bridge.request<GameSettings>('settings.get') })
    } catch {
      // keep what we had
    }
  }

  private async loadJoinInfo(): Promise<void> {
    try {
      this.update({ joinInfo: await this.bridge.request<JoinInfo>('server.join_info') })
    } catch {
      // keep what we had
    }
  }
}
