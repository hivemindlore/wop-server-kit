import type { AppState, NetworkState, WopApi } from '@shared/api'
import { describeNetwork, type NetworkView } from './network'
import { ViewModel } from './ViewModel'

export type SetupStep = 'welcome' | 'name' | 'installing' | 'network' | 'done'

export interface SetupView {
  step: SetupStep
  stepNumber: number
  stepCount: number
  nameDraft: string
  canContinue: boolean
  install: { title: string; percent: number | null; percentLabel: string; lines: string[]; error: string | null }
  network: NetworkView
  networkNext: { label: string; primary: boolean }
  starting: boolean
}

const ORDER: SetupStep[] = ['welcome', 'name', 'installing', 'network', 'done']

/** The first-time setup: a name, the game download, letting other computers in, and starting the server. */
export class SetupViewModel extends ViewModel<SetupView> {
  private step: SetupStep = 'welcome'
  private nameDraft: string | null = null
  private app: AppState | null = null
  private network: NetworkState | null = null
  private starting = false

  constructor(api: WopApi, private readonly onFinished: () => void) {
    super(api)
    this.mirror('app', (state) => {
      const before = this.app?.phase
      this.app = state
      if (state.phase === 'setting-up') this.step = 'installing'
      if (state.phase === 'ready' && before === 'setting-up') {
        this.step = 'network'
        void this.api.call('network', 'check')
      }
      if (state.phase === 'ready' && before === undefined) this.step = 'network'  // reopened halfway
    })
    this.mirror('network', (state) => (this.network = state))
  }

  protected present(): SetupView {
    const setup = this.app?.setup
    const percent = setup?.percent ?? null
    const name = this.nameDraft ?? this.app?.hello?.default_server_name ?? ''
    return {
      step: this.step,
      stepNumber: ORDER.indexOf(this.step) + 1,
      stepCount: ORDER.length,
      nameDraft: name,
      canContinue: name.trim().length > 0,
      install: {
        title: setup?.error ? 'That didn\'t work' : setup?.step || 'Getting ready...',
        percent,
        percentLabel: percent === null ? '' : `${percent}%`,
        lines: setup?.messages.slice(-6) ?? [],
        error: setup?.error ?? null
      },
      network: describeNetwork(this.network),
      networkNext: this.network?.check?.ok
        ? { label: 'Continue', primary: true }
        : { label: 'Skip for now', primary: false },
      starting: this.starting
    }
  }

  next(): void {
    if (this.step === 'welcome') this.step = 'name'
    else if (this.step === 'network') this.step = 'done'
    this.changed()
  }

  setName(name: string): void {
    this.nameDraft = name.slice(0, 40)
    this.changed()
  }

  install(): void {
    const name = this.getSnapshot().nameDraft.trim()
    if (!name) return
    this.step = 'installing'
    this.changed()
    void this.api.call('app', 'startSetup', name)
  }

  /** After a failed install: back to the name step to try again. */
  tryAgain(): void {
    this.step = 'name'
    this.changed()
    this.install()
  }

  openUrl(url: string): void {
    void this.api.call('app', 'openUrl', url)
  }

  fixNetwork(): void {
    void this.api.call('network', 'fix')
  }

  checkNetwork(): void {
    void this.api.call('network', 'check')
  }

  async finish(startServer: boolean): Promise<void> {
    if (startServer) {
      this.starting = true
      this.changed()
      void this.api.call('server', 'start')
    }
    this.onFinished()
  }
}
