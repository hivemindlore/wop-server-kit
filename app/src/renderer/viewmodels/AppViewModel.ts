import type { AppState, UpdateState, WopApi } from '@shared/api'
import { ViewModel } from './ViewModel'

export type TabId = 'server' | 'ai'

export const TABS: { id: TabId; label: string }[] = [
  { id: 'server', label: 'Server' },
  { id: 'ai', label: 'AI' }
]

/** The tabs inside the Server tab. */
export type ServerTabId = 'my-server' | 'game' | 'commands' | 'logs'

export const SERVER_TABS: { id: ServerTabId; label: string }[] = [
  { id: 'my-server', label: 'My server' },
  { id: 'game', label: 'Game' },
  { id: 'commands', label: 'Commands' },
  { id: 'logs', label: 'Logs' }
]

export interface AppView {
  screen: 'loading' | 'setup' | 'main' | 'error'
  loadingText: string
  errorText: string | null
  tabs: { id: TabId; label: string; active: boolean }[]
  activeTab: TabId
  serverTabs: { id: ServerTabId; label: string; active: boolean }[]
  activeServerTab: ServerTabId
  kitVersion: string
  appVersion: string
  /** A newer app or server kit; the app's own update comes first (it brings the newest kit along). */
  update: { text: string; buttonLabel: string | null; busy: boolean; action: 'app' | 'kit' } | null
  /** The footer's "Check for updates". */
  updateCheck: { label: string; busy: boolean; text: string | null }
}

export interface Storage {
  get(key: string): string | null
  set(key: string, value: string): void
}

/** Browser storage that never throws (it can be off or full); only remembers the open tabs. */
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
  private updates: UpdateState | null = null
  private tab: TabId
  private serverTab: ServerTabId
  private wizardOpen = false

  constructor(api: WopApi, private readonly storage: Storage = safeStorage) {
    super(api)
    const saved = storage.get('tab')
    const savedInner = storage.get('serverTab')
    this.tab = TABS.some((t) => t.id === saved) ? (saved as TabId) : 'server'
    this.serverTab = SERVER_TABS.some((t) => t.id === savedInner) ? (savedInner as ServerTabId) : 'my-server'
    if (saved === 'logs' || saved === 'commands') this.serverTab = saved  // top-level tabs before 2.3
    this.mirror('app', (state) => {
      // The wizard stays open after the install itself, for its last steps (network check, done)
      if (state.phase === 'needs-setup' || state.phase === 'setting-up') this.wizardOpen = true
      this.app = state
    })
    this.mirror('update', (state) => (this.updates = state))
  }

  protected present(): AppView {
    const app = this.app
    let screen: AppView['screen'] = 'loading'
    if (app?.phase === 'error') screen = 'error'
    else if (this.wizardOpen) screen = 'setup'
    else if (app?.phase === 'ready') screen = 'main'
    const updates = this.updates
    const busy = updates?.phase === 'checking' || updates?.phase === 'downloading' || updates?.phase === 'installing'
    return {
      screen,
      loadingText: 'Getting your server ready...',
      errorText: app?.error ?? null,
      tabs: TABS.map((t) => ({ ...t, active: t.id === this.tab })),
      activeTab: this.tab,
      serverTabs: SERVER_TABS.map((t) => ({ ...t, active: t.id === this.serverTab })),
      activeServerTab: this.serverTab,
      kitVersion: app?.hello?.kit_version ?? '',
      appVersion: updates?.current ?? '',
      update: screen === 'main' ? (this.presentAppUpdate() ?? this.presentKitUpdate()) : null,
      updateCheck: {
        label: updates?.phase === 'checking' ? 'Checking...' : 'Check for updates',
        busy,
        text: updates?.phase === 'upToDate' || (updates?.phase === 'error' && !updates.version) ? updates.message : null
      }
    }
  }

  private presentAppUpdate(): AppView['update'] {
    const u = this.updates
    if (!u?.version) return null
    const base = { busy: false, action: 'app' as const, buttonLabel: null }
    switch (u.phase) {
      case 'available':
        return { ...base, text: `A new version of WoP Server is ready (${u.version}).`, buttonLabel: 'Update now' }
      case 'downloading':
        return { ...base, busy: true, text: `Downloading WoP Server ${u.version}... ${u.percent ?? 0}%` }
      case 'installing':
        return { ...base, busy: true, text: 'Installing the update. WoP Server opens again by itself.' }
      case 'manual':
        return { ...base, text: u.message ?? '' }
      case 'error':
        return { ...base, text: u.message ?? '', buttonLabel: 'Try again' }
      default:
        return null
    }
  }

  private presentKitUpdate(): AppView['update'] {
    const update = this.app?.update
    if (!update?.available) return null
    return {
      text: `A new version of the server kit is ready (${update.version}).`,
      buttonLabel: update.busy ? 'Updating...' : 'Update now',
      busy: update.busy,
      action: 'kit'
    }
  }

  /** The banner's button. */
  runUpdate(): void {
    const update = this.getSnapshot().update
    if (!update || update.busy) return
    if (update.action === 'app') void this.api.call('update', 'install')
    else this.updateKit()
  }

  checkForUpdates(): void {
    if (this.getSnapshot().updateCheck.busy) return
    void this.api.call('update', 'check')
  }

  selectTab(tab: TabId): void {
    this.tab = tab
    this.storage.set('tab', tab)
    this.changed()
  }

  selectServerTab(tab: ServerTabId): void {
    this.serverTab = tab
    this.storage.set('serverTab', tab)
    this.changed()
  }

  finishSetup(): void {
    this.wizardOpen = false
    this.tab = 'server'
    this.serverTab = 'my-server'
    this.changed()
  }

  retry(): void {
    void this.api.call('app', 'retry')
  }

  updateKit(): void {
    void this.api.call('app', 'updateKit')
  }
}
