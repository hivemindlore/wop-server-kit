import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { AppViewModel } from '../viewmodels/AppViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { AiTab } from './AiTab'
import { CommandsTab } from './CommandsTab'
import { Button, Notice, Spinner } from './components'
import { LogsTab } from './LogsTab'
import { ServerTab } from './ServerTab'
import { SetupWizard } from './SetupWizard'

export function App({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new AppViewModel(api), [api]))
  const view = useViewModel(vm)

  if (view.screen === 'loading') {
    return (
      <main className="center-screen">
        <Spinner />
        <p>{view.loadingText}</p>
      </main>
    )
  }
  if (view.screen === 'error') {
    return (
      <main className="center-screen">
        <h1>Something went wrong</h1>
        <Notice kind="error">{view.errorText}</Notice>
        <Button kind="primary" onClick={() => vm.retry()}>
          Try again
        </Button>
      </main>
    )
  }
  if (view.screen === 'setup') return <SetupWizard api={api} onFinished={() => vm.finishSetup()} />

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">W</span>
          <span>WoP Server</span>
        </div>
        <nav className="tabs" role="tablist">
          {view.tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={tab.active}
              className={`tab ${tab.active ? 'tab-active' : ''}`}
              onClick={() => vm.selectTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>
      {view.update && (
        <div className="banner">
          <span>{view.update.text}</span>
          <Button kind="primary" disabled={view.update.busy} onClick={() => vm.updateKit()}>
            {view.update.buttonLabel}
          </Button>
        </div>
      )}
      <main className="content" role="tabpanel">
        {view.activeTab === 'server' && <ServerTab api={api} />}
        {view.activeTab === 'logs' && <LogsTab api={api} />}
        {view.activeTab === 'commands' && <CommandsTab api={api} />}
        {view.activeTab === 'ai' && <AiTab api={api} />}
      </main>
      <footer className="footer">Server kit {view.kitVersion}</footer>
    </div>
  )
}
