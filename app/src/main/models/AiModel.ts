import type { AiApp, AiState } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'
import { StateModel, messageOf } from './StateModel'

/**
 * The AI apps that can run the server for you: connecting them (the kit edits their settings) and opening them.
 * An app that was already open when it got connected only sees the server after a restart; for apps the kit
 * can restart (Claude Desktop) that's remembered in restartPending until it's done.
 */
export class AiModel extends StateModel<AiState> {
  constructor(private readonly bridge: Bridge) {
    super({ apps: [], busy: null, restartPending: [], notice: null })
  }

  async refresh(): Promise<void> {
    try {
      const { apps } = await this.bridge.request<{ apps: AiApp[] }>('ai.list')
      this.update({ apps })
    } catch (error) {
      this.update({ notice: { appId: '', kind: 'error', text: messageOf(error) } })
    }
  }

  async connect(appId: string): Promise<void> {
    const app = await this.change(appId, 'ai.connect')
    if (app?.connected && app.can_restart && app.running) this.setRestartPending(appId, true)
  }

  async disconnect(appId: string): Promise<void> {
    if (await this.change(appId, 'ai.disconnect')) this.setRestartPending(appId, false)
  }

  async open(appId: string): Promise<void> {
    await this.change(appId, 'ai.open', false)
  }

  async restart(appId: string): Promise<void> {
    if (await this.change(appId, 'ai.restart', false)) this.setRestartPending(appId, false)
  }

  /** Runs one request for one app; returns its new card, or null if it failed (the card then shows why). */
  private async change(appId: string, method: string, showHint = true): Promise<AiApp | null> {
    if (this.getState().busy) return null
    this.update({ busy: appId, notice: null })
    let app: AiApp | null = null
    try {
      app = await this.bridge.request<AiApp>(method, { app_id: appId })
      const card = app
      this.update({
        apps: this.getState().apps.map((a) => (a.id === appId ? card : a)),
        notice: showHint && card.connected && card.finish_hint ? { appId, kind: 'info', text: card.finish_hint } : null
      })
    } catch (error) {
      this.update({ notice: { appId, kind: 'error', text: messageOf(error) } })
    }
    this.update({ busy: null })
    return app
  }

  private setRestartPending(appId: string, pending: boolean): void {
    const others = this.getState().restartPending.filter((id) => id !== appId)
    this.update({ restartPending: pending ? [...others, appId] : others })
  }
}
