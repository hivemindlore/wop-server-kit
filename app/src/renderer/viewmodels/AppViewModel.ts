import type { AppState, WopApi } from '@shared/api'
import { ViewModel } from './ViewModel'

export type TabId = 'server' | 'logs' | 'commands' | 'ai'

export const TABS: { id: TabId; label: string }[] = [
  { id: 'server', label: 'Server' },
  { id: 'logs', label: 'Logs' },
  { id: 'commands', label: 'Commands' },
  { id: 'ai', label: 'AI' }
]

export interface AppView {
  screen: 'loading' | 'setup' | 'main' | 'error'
  loadingText: string
  errorText: string | null
  tabs: { id: TabId; label: string; active: boolean }[]
  activeTab: TabId
  kitVersion: string
  update: { text: string; buttonLabel: string; busy: boolean } | null
}

export interface Storage {
  get(key: string): string | null
  set(key: string, value: string): void
}

/** Browser storage that never throws (it can be off or full); only remembers the open tab. */
export const safeStorage: Storage = {
  get(key) {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value)
    } catch {
      // not important
    }
  }
}

/** Which screen shows (loading, first-time setup, the tabs, a problem) and which tab is open. */
export class AppViewModel extends ViewModel<AppView> {
  private app: AppState | null = null
  private tab: TabId
  private wizardOpen = false

  constructor(api: WopApi, private readonly storage: Storage = safeStorage) {
    super(api)
    const saved = storage.get('tab') as TabId | null
    this.tab = TABS.some((t) => t.id === saved) ? saved! : 'server'
    this.mirror('app', (state) => {
      // The wizard stays open after the install itself, for its last steps (network check, done)
      if (state.phase === 'needs-setup' || state.phase === 'setting-up') this.wizardOpen = true
      this.app = state
    })
  }

  protected present(): AppView {
    const app = this.app
    let screen: AppView['screen'] = 'loading'
    if (app?.phase === 'error') screen = 'error'
    else if (this.wizardOpen) screen = 'setup'
    else if (app?.phase === 'ready') screen = 'main'
    const update = app?.update
    return {
      screen,
      loadingText: 'Getting your server ready...',
      errorText: app?.error ?? null,
      tabs: TABS.map((t) => ({ ...t, active: t.id === this.tab })),
      activeTab: this.tab,
      kitVersion: app?.hello?.kit_version ?? '',
      update:
        update?.available && screen === 'main'
          ? {
              text: `A new version of the server kit is ready (${update.version}).`,
              buttonLabel: update.busy ? 'Updating...' : 'Update now',
              busy: update.busy
            }
          : null
    }
  }

  selectTab(tab: TabId): void {
    this.tab = tab
    this.storage.set('tab', tab)
    this.changed()
  }

  finishSetup(): void {
    this.wizardOpen = false
    this.tab = 'server'
    this.changed()
  }

  retry(): void {
    void this.api.call('app', 'retry')
  }

  updateKit(): void {
    void this.api.call('app', 'updateKit')
  }
}
