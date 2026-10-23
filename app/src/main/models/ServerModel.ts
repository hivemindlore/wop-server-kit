import type { GameSettings, JoinInfo, OnlineStatus, ServerState, ServerStatus } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'
import { StateModel, messageOf } from './StateModel'

// The server answers only a few questions a second and Claude needs some too, so look every 5 s
export const POLL_MS = 5000
// While internet play waits for the approval in the browser or for its address
export const ONLINE_POLL_MS = 3000
export const ONLINE_WAIT_MS = 10 * 60 * 1000
export const ONLINE_REFRESH_POLLS = 6   // every 6th status poll (30 s), see refresh()

const WAITING: OnlineStatus['phase'][] = ['approving', 'starting']

interface ActionResult {
  result?: string
}

/** Server on/off, what it's playing, how others join (also over the internet), and the weapons settings. */
export class ServerModel extends StateModel<ServerState> {
  private timer: ReturnType<typeof setInterval> | null = null
  private refreshing: Promise<void> | null = null
  private onlineTimer: ReturnType<typeof setInterval> | null = null
  private onlineSince = 0
  private advancing = false
  private polls = 0

  constructor(private readonly bridge: Bridge) {
    super({ status: null, joinInfo: null, settings: null, online: null, busy: null, onlineBusy: false, notice: null })
  }

  activate(): void {
    if (this.timer) return
    void this.refresh()
    void this.loadJoinInfo()
    void this.loadSettings()
    void this.loadOnline()
    this.timer = setInterval(() => void this.refresh(), POLL_MS)
  }

  deactivate(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
    this.stopWaiting()
  }

  refresh(): Promise<void> {
    // Internet play can be switched by Claude too; its status costs the server nothing, so look now and then
    if (++this.polls % ONLINE_REFRESH_POLLS === 0 && !this.onlineTimer) void this.loadOnline()
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

  /** Game settings as after installing; a running server restarts with them. */
  async resetToDefaults(): Promise<void> {
    await this.act('resetting', 'settings.reset')
  }

  /**
   * Friends anywhere can join (on), or only the home network (off). The first time, the kit opens playit.gg
   * in the browser; until the host approves it there (and the address is ready), the kit is asked again
   * every few seconds.
   */
  async setOnline(on: boolean): Promise<void> {
    if (this.getState().onlineBusy) return
    this.update({ onlineBusy: true, notice: null })
    try {
      const online = await this.bridge.request<OnlineStatus>(on ? 'online.enable' : 'online.disable')
      this.applyOnline(online)
      if (online.result) this.update({ notice: { kind: 'info', text: online.result } })
    } catch (error) {
      this.update({ notice: { kind: 'error', text: messageOf(error) } })
      await this.loadOnline()
    }
    void this.loadJoinInfo()
    this.update({ onlineBusy: false })
  }

  async manageOnline(): Promise<void> {
    try {
      await this.bridge.request('online.manage')
    } catch (error) {
      this.update({ notice: { kind: 'error', text: messageOf(error) } })
    }
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
      if (before && before.running !== status.running) {
        void this.loadJoinInfo()
        void this.loadOnline()   // internet play follows the server
      }
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

  private async loadOnline(): Promise<void> {
    try {
      this.applyOnline(await this.bridge.request<OnlineStatus>('online.status'))
    } catch {
      // keep what we had
    }
  }

  private applyOnline(online: OnlineStatus): void {
    this.update({ online })
    if (WAITING.includes(online.phase)) this.waitForOnline()
    else this.stopWaiting()
  }

  private waitForOnline(): void {
    if (this.onlineTimer) return
    this.onlineSince = Date.now()
    this.onlineTimer = setInterval(() => void this.advanceOnline(), ONLINE_POLL_MS)
  }

  private stopWaiting(): void {
    if (this.onlineTimer) clearInterval(this.onlineTimer)
    this.onlineTimer = null
  }

  private async advanceOnline(): Promise<void> {
    if (this.advancing) return
    if (Date.now() - this.onlineSince > ONLINE_WAIT_MS) {
      this.stopWaiting()   // switching it off and on again starts a new wait
      return
    }
    this.advancing = true
    try {
      const before = this.getState().online?.address
      this.applyOnline(await this.bridge.request<OnlineStatus>('online.advance'))
      if (this.getState().online?.address !== before) void this.loadJoinInfo()
    } catch (error) {
      this.stopWaiting()
      this.update({ notice: { kind: 'error', text: messageOf(error) } })
      await this.loadOnline()
    } finally {
      this.advancing = false
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
