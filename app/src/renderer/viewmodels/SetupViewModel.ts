import type { AiApp, AiState, AppState, NetworkState, WopApi } from '@shared/api'
import { describeNetwork, type NetworkView } from './network'
import { ViewModel } from './ViewModel'

export type SetupStep = 'welcome' | 'name' | 'installing' | 'claude' | 'network' | 'done'

export interface SetupView {
  step: SetupStep
  stepNumber: number
  stepCount: number
  nameDraft: string
  canContinue: boolean
  install: { title: string; percent: number | null; percentLabel: string; lines: string[]; error: string | null }
  claude: {
    busy: boolean
    /** While it downloads and installs. */
    progress: { title: string; percent: number | null; percentLabel: string }
    installed: boolean
    /** False: the button opens the download page instead. */
    installable: boolean
    error: string | null
    downloadUrl: string
    installLabel: string
    skipLabel: string
  }
  network: NetworkView
  networkNext: { label: string; primary: boolean }
  starting: boolean
}

const ORDER: SetupStep[] = ['welcome', 'name', 'installing', 'claude', 'network', 'done']
const CLAUDE = 'claude-desktop'
const CLAUDE_PAGE = 'https://claude.ai/download'

/** The first-time setup: a name, the game download, Claude Desktop if wanted, letting other computers in,
 *  and starting the server. */
export class SetupViewModel extends ViewModel<SetupView> {
  private step: SetupStep = 'welcome'
  private nameDraft: string | null = null
  private app: AppState | null = null
  private ai: AiState | null = null
  private network: NetworkState | null = null
  private starting = false
  /** Whether the Claude Desktop step is shown; null until the game is installed and the AI apps are known. */
  private offerClaude: boolean | null = null

  constructor(api: WopApi, private readonly onFinished: () => void) {
    super(api)
    this.mirror('app', (state) => {
      const before = this.app?.phase
      this.app = state
      if (state.phase === 'setting-up') this.step = 'installing'
      if (state.phase === 'ready' && before === 'setting-up') void this.afterInstall()
      if (state.phase === 'ready' && before === undefined) this.step = 'network'  // reopened halfway
    })
    this.mirror('ai', (state) => (this.ai = state))
    this.mirror('network', (state) => (this.network = state))
  }

  protected present(): SetupView {
    const setup = this.app?.setup
    const percent = setup?.percent ?? null
    const name = this.nameDraft ?? this.app?.hello?.default_server_name ?? ''
    const order = ORDER.filter((step) => step !== 'claude' || this.offerClaude !== false)
    const claude = this.claudeCard()
    const notice = this.ai?.notice
    const claudeError = notice?.appId === CLAUDE && notice.kind === 'error' ? notice.text : null
    const installable = claude?.installable ?? false
    return {
      step: this.step,
      stepNumber: order.indexOf(this.step) + 1,
      stepCount: order.length,
      nameDraft: name,
      canContinue: name.trim().length > 0,
      install: {
        title: setup?.error ? 'That didn\'t work' : setup?.step || 'Getting ready...',
        percent,
        percentLabel: percent === null ? '' : `${percent}%`,
        lines: setup?.messages.slice(-6) ?? [],
        error: setup?.error ?? null
      },
      claude: {
        busy: this.ai?.busy === CLAUDE,
        progress: {
          title: setup?.step || 'Getting Claude Desktop...',
          percent,
          percentLabel: percent === null ? '' : `${percent}%`
        },
        installed: claude?.installed ?? false,
        installable,
        error: claudeError,
        downloadUrl: claude?.download_url ?? CLAUDE_PAGE,
        installLabel: claudeError ? 'Try again' : installable ? 'Install Claude Desktop' : 'Open the download page',
        skipLabel: claudeError ? 'Continue without it' : installable ? 'Skip' : 'Continue'
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
    else if (this.step === 'claude') return this.toNetwork()
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

  /** Downloads and installs Claude Desktop (connected to the server), or where that can't be done, opens its
   *  download page. */
  installClaude(): void {
    const { claude } = this.getSnapshot()
    if (claude.installable) void this.api.call('ai', 'install', CLAUDE)
    else this.openUrl(claude.downloadUrl)
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

  private claudeCard(): AiApp | undefined {
    return this.ai?.apps.find((app) => app.id === CLAUDE)
  }

  /** The game is in place: offer Claude Desktop where it exists and isn't installed yet, else go on. */
  private async afterInstall(): Promise<void> {
    await this.api.call('ai', 'refresh')
    this.ai = await this.api.get('ai')
    const claude = this.claudeCard()
    this.offerClaude = !!claude && !claude.installed
    if (this.offerClaude) {
      this.step = 'claude'
      this.changed()
    } else {
      this.toNetwork()
    }
  }

  private toNetwork(): void {
    this.step = 'network'
    this.changed()
    void this.api.call('network', 'check')
  }
}
