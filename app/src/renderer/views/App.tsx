import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { AppViewModel } from '../viewmodels/AppViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { AiTab } from './AiTab'
import { CommandsTab } from './CommandsTab'
import { Button, Notice, Spinner } from './components'
import { GameTab } from './GameTab'
import { LogsTab } from './LogsTab'
import { MyServerTab } from './MyServerTab'
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
          <span>
            {view.update.busy && <Spinner />} {view.update.text}
          </span>
          {view.update.buttonLabel && (
            <Button kind="primary" disabled={view.update.busy} onClick={() => vm.runUpdate()}>
              {view.update.buttonLabel}
            </Button>
          )}
        </div>
      )}
      <main className="content" role="tabpanel">
        {view.activeTab === 'server' && (
          <div className="server-section">
            <nav className="subtabs" role="tablist" aria-label="Server">
              {view.serverTabs.map((tab) => (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={tab.active}
                  className={`subtab ${tab.active ? 'subtab-active' : ''}`}
                  onClick={() => vm.selectServerTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
            <div className="subpanel" role="tabpanel">
              {view.activeServerTab === 'my-server' && <MyServerTab api={api} />}
              {view.activeServerTab === 'game' && <GameTab api={api} />}
              {view.activeServerTab === 'commands' && <CommandsTab api={api} />}
              {view.activeServerTab === 'logs' && <LogsTab api={api} />}
            </div>
          </div>
        )}
        {view.activeTab === 'ai' && <AiTab api={api} />}
      </main>
      <footer className="footer">
        <span>
          WoP Server {view.appVersion} · Server kit {view.kitVersion}
        </span>
        <Button kind="quiet" disabled={view.updateCheck.busy} onClick={() => vm.checkForUpdates()}>
          {view.updateCheck.label}
        </Button>
        {view.updateCheck.text && <span>{view.updateCheck.text}</span>}
      </footer>
    </div>
  )
}
