import type { NetworkCheck, NetworkState } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'
import { StateModel, messageOf } from './StateModel'

/** Can other computers on the network find and join the server? And fixing it when they can't. */
export class NetworkModel extends StateModel<NetworkState> {
  constructor(private readonly bridge: Bridge) {
    super({ check: null, busy: null, error: null })
  }

  check(): Promise<void> {
    return this.run('checking', 'network.check')
  }

  /** The OS asks the user for permission (a dialog), then the kit checks again. */
  fix(): Promise<void> {
    return this.run('fixing', 'network.fix')
  }

  private async run(busy: 'checking' | 'fixing', method: string): Promise<void> {
    if (this.getState().busy) return
    this.update({ busy, error: null })
    try {
      this.update({ check: await this.bridge.request<NetworkCheck>(method), busy: null })
    } catch (error) {
      this.update({ busy: null, error: messageOf(error) })
    }
  }
}
