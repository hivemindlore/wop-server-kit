import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { SetupViewModel } from '../viewmodels/SetupViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import logo from '../assets/wop-logo.svg'
import { Button, Notice, ProgressBar } from './components'
import { NetworkCard } from './NetworkCard'

export function SetupWizard({ api, onFinished }: { api: WopApi; onFinished: () => void }) {
  const vm = useActive(useMemo(() => new SetupViewModel(api, onFinished), [api, onFinished]))
  const view = useViewModel(vm)

  return (
    <main className="wizard">
      <div className="wizard-card">
        <header className="wizard-head">
          <img className="wizard-logo" src={logo} alt="World of PADMAN" />
          <p className="muted small">
            Step {view.stepNumber} of {view.stepCount}
          </p>
        </header>

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

        {view.step === 'claude' && (
          <>
            <h1>Want an AI to run your server?</h1>
            <p>
              Claude Desktop is an app where you chat with Claude, an AI. It's free to start; you sign in with a
              Claude account. Once it's set up, you can just ask it things like{' '}
              <em>"Switch to Capture The Lolly with 4 bots on each team"</em> or <em>"How do my friends join?"</em>{' '}
              and it changes your server for you.
            </p>
            <p className="muted">You don't need it: everything also works from this app. You can get it later too.</p>
            {view.claude.busy ? (
              <>
                <p>{view.claude.progress.title}</p>
                <ProgressBar percent={view.claude.progress.percent} />
                <p className="muted">{view.claude.progress.percentLabel}</p>
              </>
            ) : view.claude.installed ? (
              <>
                <Notice kind="ok">
                  Claude Desktop is installed and knows your server. Sign in there, then ask it something. You'll
                  also find it on the AI tab.
                </Notice>
                <Button kind="primary" onClick={() => vm.next()}>
                  Continue
                </Button>
              </>
            ) : (
              <>
                {view.claude.error && <Notice kind="error">{view.claude.error}</Notice>}
                <div className="button-row">
                  <Button kind="primary" onClick={() => vm.installClaude()}>
                    {view.claude.installLabel}
                  </Button>
                  <Button kind="quiet" onClick={() => vm.next()}>
                    {view.claude.skipLabel}
                  </Button>
                </div>
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
            <div className="button-row">
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
