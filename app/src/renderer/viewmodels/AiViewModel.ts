import type { AiApp, AiState, WopApi } from '@shared/api'
import { ViewModel } from './ViewModel'

export interface AiCard {
  id: string
  name: string
  blurb: string
  price: string
  status: 'connected' | 'ready' | 'not-installed' | 'advice'
  statusLabel: string
  action: { label: string; kind: 'connect' | 'disconnect'; busy: boolean; disabled: boolean } | null
  /** Open (or restart) the app itself, once it's connected. */
  open: { label: string; kind: 'open' | 'restart'; disabled: boolean } | null
  download: { label: string; url: string } | null
  advice: string | null
  examples: string[]
  notice: { kind: 'info' | 'error'; text: string } | null
}

export interface AiView {
  intro: string
  cards: AiCard[]
  loading: boolean
}

/** The AI tab: which AI apps can run the server for you, connected with one click. */
export class AiViewModel extends ViewModel<AiView> {
  private ai: AiState | null = null

  constructor(api: WopApi) {
    super(api)
    this.mirror('ai', (state) => (this.ai = state))
  }

  protected present(): AiView {
    const busy = this.ai?.busy ?? null
    const notice = this.ai?.notice ?? null
    const apps = [...(this.ai?.apps ?? [])].sort((a, b) => order(a) - order(b))
    return {
      intro: 'Let an AI run your server: ask it in plain words to change the map, add bots or start a ' +
        'new game. Connect an app below and it knows your server.',
      loading: this.ai === null || !this.ai.apps.length,
      cards: apps.map((app) =>
        card(app, busy, this.ai?.restartPending.includes(app.id) ?? false, notice?.appId === app.id ? notice : null)
      )
    }
  }

  openApp(appId: string): void {
    const open = this.getSnapshot().cards.find((c) => c.id === appId)?.open
    if (!open || open.disabled) return
    void this.api.call('ai', open.kind === 'restart' ? 'restart' : 'open', appId)
  }

  connect(appId: string): void {
    void this.api.call('ai', 'connect', appId)
  }

  disconnect(appId: string): void {
    void this.api.call('ai', 'disconnect', appId)
  }

  refresh(): void {
    void this.api.call('ai', 'refresh')
  }

  openUrl(url: string): void {
    void this.api.call('app', 'openUrl', url)
  }
}

/** Connected first, then installed ones, then the rest; advice-only cards last. */
function order(app: AiApp): number {
  if (!app.connectable) return 3
  if (app.connected) return 0
  return app.installed ? 1 : 2
}

function card(app: AiApp, busy: string | null, restartPending: boolean, notice: AiCard['notice']): AiCard {
  let status: AiCard['status'] = 'advice'
  let statusLabel = ''
  if (app.connectable) {
    status = app.connected ? 'connected' : app.installed ? 'ready' : 'not-installed'
    statusLabel = app.connected ? 'Connected' : app.installed ? 'Ready to connect' : 'Not installed'
  }
  return {
    id: app.id,
    name: app.name,
    blurb: app.blurb,
    price: app.free ? 'Free · runs on your computer' : 'Needs an account',
    status,
    statusLabel,
    action: app.connectable
      ? {
          label: busy === app.id ? 'One moment...' : app.connected ? 'Disconnect' : 'Connect',
          kind: app.connected ? 'disconnect' : 'connect',
          busy: busy === app.id,
          disabled: busy !== null
        }
      : null,
    open:
      app.connected && app.openable
        ? {
            label: busy === app.id
              ? 'One moment...'
              : restartPending ? `Restart ${app.name}` : `Open ${app.name}`,
            kind: restartPending ? 'restart' : 'open',
            disabled: busy !== null
          }
        : null,
    download: app.connectable && !app.installed ? { label: `Get ${app.name}`, url: app.download_url } : null,
    advice: app.connectable ? null : app.advice,
    examples: app.connectable ? app.examples : [],
    notice:
      notice?.kind === 'info' && restartPending
        ? { kind: 'info', text: `${app.name} is open right now: click "Restart ${app.name}" so it sees your server.` }
        : notice
  }
}
