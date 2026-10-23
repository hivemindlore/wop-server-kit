import type { AiApp, AiState } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'
import { StateModel, messageOf } from './StateModel'

/** The AI apps that can run the server for you, and connecting them (the kit edits their settings). */
export class AiModel extends StateModel<AiState> {
  constructor(private readonly bridge: Bridge) {
    super({ apps: [], busy: null, notice: null })
  }

  async refresh(): Promise<void> {
    try {
      const { apps } = await this.bridge.request<{ apps: AiApp[] }>('ai.list')
      this.update({ apps })
    } catch (error) {
      this.update({ notice: { appId: '', kind: 'error', text: messageOf(error) } })
    }
  }

  connect(appId: string): Promise<void> {
    return this.change(appId, 'ai.connect')
  }

  disconnect(appId: string): Promise<void> {
    return this.change(appId, 'ai.disconnect')
  }

  private async change(appId: string, method: string): Promise<void> {
    if (this.getState().busy) return
    this.update({ busy: appId, notice: null })
    try {
      const app = await this.bridge.request<AiApp>(method, { app_id: appId })
      this.update({
        apps: this.getState().apps.map((a) => (a.id === appId ? app : a)),
        notice: app.connected && app.finish_hint ? { appId, kind: 'info', text: app.finish_hint } : null
      })
    } catch (error) {
      this.update({ notice: { appId, kind: 'error', text: messageOf(error) } })
    }
    this.update({ busy: null })
  }
}
