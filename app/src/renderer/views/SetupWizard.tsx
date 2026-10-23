import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { SetupViewModel } from '../viewmodels/SetupViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, Notice, ProgressBar } from './components'
import { NetworkCard } from './NetworkCard'

export function SetupWizard({ api, onFinished }: { api: WopApi; onFinished: () => void }) {
  const vm = useActive(useMemo(() => new SetupViewModel(api, onFinished), [api, onFinished]))
  const view = useViewModel(vm)

  return (
    <main className="wizard">
      <div className="wizard-card">
        <p className="muted small">
          Step {view.stepNumber} of {view.stepCount}
        </p>

        {view.step === 'welcome' && (
          <>
            <h1>Welcome!</h1>
            <p>
              Let's set up your own World of PADMAN server, so everyone on your home network can play together.
              It takes a few minutes the first time.
            </p>
            <Button kind="primary" onClick={() => vm.next()}>
              Let's go
            </Button>
          </>
        )}

        {view.step === 'name' && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              vm.install()
            }}
          >
            <h1>Name your server</h1>
            <p>Players see this name in the game's server list.</p>
            <input autoFocus value={view.nameDraft} onChange={(e) => vm.setName(e.target.value)} maxLength={40} />
            <Button kind="primary" type="submit" disabled={!view.canContinue}>
              Continue
            </Button>
          </form>
        )}

        {view.step === 'installing' && (
          <>
            <h1>{view.install.title}</h1>
            {!view.install.error && (
              <>
                <ProgressBar percent={view.install.percent} />
                <p className="muted">{view.install.percentLabel}</p>
                <p className="muted small">
                  World of PADMAN is downloaded once (1.2 GB). You can leave this running.
                </p>
              </>
            )}
            <ul className="setup-log">
              {view.install.lines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
            {view.install.error && (
              <>
                <Notice kind="error">{view.install.error}</Notice>
                <Button kind="primary" onClick={() => vm.tryAgain()}>
                  Try again
                </Button>
              </>
            )}
          </>
        )}

        {view.step === 'network' && (
          <>
            <h1>Let the others in</h1>
            <p>Your computer's firewall decides whether other computers on your network may join.</p>
            <NetworkCard
              view={view.network}
              onFix={() => vm.fixNetwork()}
              onCheck={() => vm.checkNetwork()}
              onOpenUrl={(url) => vm.openUrl(url)}
            />
            <Button kind={view.networkNext.primary ? 'primary' : 'secondary'} onClick={() => vm.next()}>
              {view.networkNext.label}
            </Button>
          </>
        )}

        {view.step === 'done' && (
          <>
            <h1>All set!</h1>
            <p>Your server is ready. Start it now? You can always turn it on and off on the Server tab.</p>
            <div className="card-actions">
              <Button kind="primary" disabled={view.starting} onClick={() => void vm.finish(true)}>
                Start my server
              </Button>
              <Button kind="quiet" onClick={() => void vm.finish(false)}>
                Not now
              </Button>
            </div>
          </>
        )}
      </div>
    </main>
  )
}
