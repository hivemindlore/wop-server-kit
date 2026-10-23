import { BRIDGE_PROTOCOL, type AppState, type Hello, type UpdateCheck } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'
import { StateModel, messageOf } from './StateModel'

export interface BridgeProcess extends Bridge {
  start(): void
  stop(): void
}

export interface AppModelDeps {
  bridge: BridgeProcess
  /** Puts the kit and uv in place (KitInstaller.ensure). */
  prepareKit(): Promise<unknown>
  openExternal(url: string): Promise<void>
  /** Waits before the kit is restarted after it stopped unexpectedly. */
  delay?(ms: number): Promise<void>
}

const MAX_SETUP_MESSAGES = 50

/** Starting the kit, the first-time setup and kit updates. The other models start once phase is 'ready'. */
export class AppModel extends StateModel<AppState> {
  private restarting = false
  private readonly delay: (ms: number) => Promise<void>

  constructor(private readonly deps: AppModelDeps) {
    super({
      phase: 'starting',
      hello: null,
      error: null,
      setup: { step: '', messages: [], percent: null, error: null },
      update: { available: false, version: '', busy: false }
    })
    this.delay = deps.delay ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)))
    deps.bridge.on('event', (name, data) => this.onEvent(name, data))
    deps.bridge.on('exit', () => void this.onBridgeExit())
  }

  async boot(): Promise<void> {
    this.update({ phase: 'starting', error: null })
    try {
      await this.deps.prepareKit()
      this.deps.bridge.start()
      await this.sayHello()
    } catch (error) {
      this.update({ phase: 'error', error: messageOf(error) })
      return
    }
    if (this.getState().phase === 'ready') void this.checkUpdate()
  }

  retry(): Promise<void> {
    return this.boot()
  }

  async startSetup(serverName: string): Promise<void> {
    if (this.getState().phase === 'setting-up') return
    this.update({ phase: 'setting-up', setup: { step: 'Getting ready...', messages: [], percent: null, error: null } })
    try {
      await this.deps.bridge.request('setup.start', { server_name: serverName.trim() })
      await this.sayHello()
    } catch (error) {
      this.update({ phase: 'needs-setup', setup: { ...this.getState().setup, error: messageOf(error) } })
    }
  }

  async updateKit(): Promise<void> {
    this.update({ update: { ...this.getState().update, busy: true } })
    try {
      const result = await this.deps.bridge.request<{ updated: boolean; version: string }>('kit.update')
      if (result.updated) await this.restartBridge()
      this.update({ update: { available: false, version: result.version, busy: false } })
    } catch (error) {
      this.update({ update: { ...this.getState().update, busy: false }, error: messageOf(error) })
    }
  }

  async openUrl(url: string): Promise<void> {
    if (/^https?:\/\//.test(url)) await this.deps.openExternal(url)
  }

  private async sayHello(): Promise<void> {
    const hello = await this.deps.bridge.request<Hello>('hello')
    if (hello.protocol !== BRIDGE_PROTOCOL) {
      throw new Error('This version of the WoP Server app doesn\'t match the installed kit. Please download the newest app.')
    }
    this.update({ hello, phase: hello.installed ? 'ready' : 'needs-setup', error: null })
  }

  private async checkUpdate(): Promise<void> {
    try {
      const check = await this.deps.bridge.request<UpdateCheck>('kit.check_update')
      this.update({ update: { available: check.available, version: check.version, busy: false } })
    } catch {
      // offline: try again next time the app starts
    }
  }

  private async restartBridge(): Promise<void> {
    this.restarting = true
    this.deps.bridge.stop()
    await this.delay(500)
    this.deps.bridge.start()
    this.restarting = false
    await this.sayHello()
  }

  private async onBridgeExit(): Promise<void> {
    const { phase } = this.getState()
    if (this.restarting || phase === 'starting' || phase === 'error') return
    await this.delay(1000)
    try {
      this.deps.bridge.start()
      await this.sayHello()
    } catch (error) {
      this.update({ phase: 'error', error: messageOf(error) })
    }
  }

  private onEvent(name: string, data: unknown): void {
    const setup = this.getState().setup
    const text = (data as { text?: string })?.text ?? ''
    if (name === 'setup.step') {
      this.update({ setup: { ...setup, step: text, percent: null } })
    } else if (name === 'setup.message') {
      this.update({ setup: { ...setup, messages: [...setup.messages, text].slice(-MAX_SETUP_MESSAGES) } })
    } else if (name === 'setup.progress') {
      this.update({ setup: { ...setup, percent: (data as { percent: number }).percent } })
    }
  }
}
