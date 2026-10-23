import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { ServerViewModel } from '../viewmodels/ServerViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, Card, CopyValue, Notice, Spinner } from './components'
import { NetworkCard } from './NetworkCard'

export function MyServerTab({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new ServerViewModel(api), [api]))
  const view = useViewModel(vm)
  const { power, join, online } = view

  return (
    <div className="grid">
      <Card className={`power power-${power.tone} span-2`}>
        <div className="power-row">
          <div>
            <h1>{power.headline}</h1>
            {view.game ? (
              <p className="game-line">
                <strong>{view.game.mode}</strong> on <strong>{view.game.map}</strong> · {view.game.weapons} ·{' '}
                {view.game.limits}
              </p>
            ) : (
              power.hint && <p className="muted">{power.hint}</p>
            )}
            {view.playersSummary && <p className="muted">{view.playersSummary}</p>}
          </div>
          <button
            className={`switch ${power.on ? 'switch-on' : ''}`}
            role="switch"
            aria-checked={power.on}
            aria-label={power.buttonLabel}
            disabled={power.busy || !power.known}
            onClick={() => vm.toggle()}
          >
            <span className="switch-knob">{power.busy && <Spinner />}</span>
          </button>
        </div>
        {view.notice && <Notice kind={view.notice.kind}>{view.notice.text}</Notice>}
        <div className="power-actions">
          <Button kind="play" disabled={view.play.disabled} onClick={() => vm.play()}>
            {view.play.label}
          </Button>
        </div>
      </Card>

      <Card title="How others join" className="span-2">
        {!join ? (
          <p className="muted">
            <Spinner /> Looking up your network...
          </p>
        ) : (
          <>
            <div className="join-intro">
              <p>
                Everyone needs World of PADMAN 1.7.0 (free).{' '}
                <a href={join.downloadUrl} onClick={(e) => (e.preventDefault(), vm.openUrl(join.downloadUrl))}>
                  Download it
                </a>
              </p>
              {join.password && (
                <div className="password-pill">
                  <span>
                    Join password: <code>{join.password}</code>
                  </span>
                  <Button kind="quiet" onClick={() => vm.copy(join.passwordLine!)}>
                    {view.copied === join.passwordLine ? 'Copied!' : 'Copy'}
                  </Button>
                </div>
              )}
            </div>
            {join.passwordLine && (
              <p className="muted small">
                Players type <code>{join.passwordLine}</code> in the game's console (press ~) before they join.
              </p>
            )}

            <div className="join-sections">
              <section className="join-section">
                <header className="join-section-head">
                  <span className="join-badge" aria-hidden="true">🏠</span>
                  <h3>Same Wi-Fi or home network</h3>
                </header>
                <ol className="step-chips">
                  {join.lanSteps.map((step, i) => (
                    <li key={step}>
                      <span className="step-number">{i + 1}</span>
                      {step}
                    </li>
                  ))}
                </ol>
                <details className="join-manual">
                  <summary>Not in the list? Type the address yourself</summary>
                  <p className="muted small">
                    In the Multiplayer screen click <strong>Specify</strong> and fill in:
                  </p>
                  <div className="copy-grid">
                    {join.addresses.map((a) => (
                      <CopyValue
                        key={a.address}
                        label={a.primary ? 'Address' : 'Other network'}
                        value={a.address}
                        hint={a.connection}
                        copied={view.copied === a.address}
                        onCopy={() => vm.copy(a.address)}
                      />
                    ))}
                    <CopyValue
                      label="Port"
                      value={join.port}
                      copied={view.copied === join.port}
                      onCopy={() => vm.copy(join.port)}
                    />
                    {join.connectLine && (
                      <CopyValue
                        label="Or type"
                        value={join.connectLine}
                        hint="in the game's console (press ~)"
                        copied={view.copied === join.connectLine}
                        onCopy={() => vm.copy(join.connectLine!)}
                      />
                    )}
                  </div>
                </details>
                {join.warning && <Notice kind="warn">{join.warning}</Notice>}
              </section>

              {online && (
                <section className={`join-section ${online.on ? 'join-section-on' : ''}`}>
                  <header className="join-section-head">
                    <span className="join-badge" aria-hidden="true">🌍</span>
                    <h3>Friends anywhere (internet)</h3>
                    <button
                      className={`switch switch-small ${online.on ? 'switch-on' : ''}`}
                      role="switch"
                      aria-checked={online.on}
                      aria-label={online.label}
                      disabled={online.busy}
                      onClick={() => vm.toggleOnline()}
                    >
                      <span className="switch-knob">{online.busy && <Spinner />}</span>
                    </button>
                  </header>
                  {online.state === 'off' && <p className="muted">{online.hint}</p>}
                  {online.state === 'approving' && (
                    <>
                      <p>
                        <Spinner /> {online.note}
                      </p>
                      <div className="card-actions">
                        <Button kind="secondary" onClick={() => vm.openUrl(online.approveUrl!)}>
                          Open the page again
                        </Button>
                        <Button kind="quiet" onClick={() => vm.toggleOnline()}>
                          Cancel
                        </Button>
                      </div>
                    </>
                  )}
                  {online.state === 'waiting' && online.note && <p className="muted">{online.note}</p>}
                  {online.state === 'ready' && (
                    <>
                      <p className="muted small">
                        Friends somewhere else click <strong>Specify</strong> in the Multiplayer screen and fill in:
                      </p>
                      <div className="copy-grid">
                        <CopyValue
                          label="Address"
                          value={online.address!}
                          copied={view.copied === online.address}
                          onCopy={() => vm.copy(online.address!)}
                        />
                        <CopyValue
                          label="Port"
                          value={online.port!}
                          copied={view.copied === online.port}
                          onCopy={() => vm.copy(online.port!)}
                        />
                        <CopyValue
                          label="Or type"
                          value={online.connectLine!}
                          hint="in the game's console (press ~)"
                          copied={view.copied === online.connectLine}
                          onCopy={() => vm.copy(online.connectLine!)}
                        />
                      </div>
                    </>
                  )}
                  {online.problem && <Notice kind="error">{online.problem}</Notice>}
                  {online.passwordTip && <Notice kind="warn">{online.passwordTip}</Notice>}
                  {online.manageLabel && (
                    <Button kind="quiet" onClick={() => vm.manageOnline()}>
                      {online.manageLabel}
                    </Button>
                  )}
                </section>
              )}
            </div>
          </>
        )}
      </Card>

      <NetworkCard
        view={view.network}
        onFix={() => vm.fixNetwork()}
        onCheck={() => vm.checkNetwork()}
        onOpenUrl={(url) => vm.openUrl(url)}
      />

      <Card title="Settings">
        <div className="setting">
          <span className="setting-label">Server name</span>
          {view.editingName ? (
            <form
              className="inline-form"
              onSubmit={(e) => {
                e.preventDefault()
                void vm.saveName()
              }}
            >
              <input autoFocus value={view.nameDraft} onChange={(e) => vm.setNameDraft(e.target.value)} />
              <Button kind="primary" type="submit" disabled={!view.nameDraft.trim()}>
                Save
              </Button>
              <Button kind="quiet" onClick={() => vm.cancelName()}>
                Cancel
              </Button>
            </form>
          ) : (
            <div className="inline-form">
              <strong>{join?.serverName ?? ''}</strong>
              <Button kind="quiet" onClick={() => vm.editName()} disabled={view.saving}>
                Rename
              </Button>
            </div>
          )}
        </div>
        <div className="setting">
          <span className="setting-label">Join password</span>
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault()
              void vm.savePassword()
            }}
          >
            <input
              value={view.passwordDraft}
              placeholder={join?.password ? 'New password' : 'None: anyone on your network can join'}
              onChange={(e) => vm.setPasswordDraft(e.target.value)}
            />
            <Button kind="secondary" type="submit" disabled={!view.passwordDraft || view.saving}>
              Set
            </Button>
            {join?.password && (
              <Button kind="quiet" onClick={() => vm.removePassword()} disabled={view.saving}>
                Remove password
              </Button>
            )}
          </form>
        </div>
        <div className="setting">
          {view.reset.confirming ? (
            <>
              <Notice kind="warn">{view.reset.warning}</Notice>
              <div className="inline-form">
                <Button kind="danger" onClick={() => vm.confirmReset()}>
                  Reset
                </Button>
                <Button kind="quiet" onClick={() => vm.cancelReset()}>
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            <div className="inline-form">
              <Button kind="quiet" onClick={() => vm.askReset()} disabled={view.saving}>
                {view.reset.busy ? 'Resetting...' : 'Reset to defaults'}
              </Button>
            </div>
          )}
        </div>
      </Card>

      {view.players.length > 0 && (
        <Card title="Who's on" className="span-2">
          <table className="players">
            <thead>
              <tr>
                <th>Name</th>
                <th>Team</th>
                <th></th>
                <th className="num">Score</th>
              </tr>
            </thead>
            <tbody>
              {view.players.map((p) => (
                <tr key={p.key}>
                  <td>{p.name}</td>
                  <td>{p.team && <span className={`team team-${p.teamTone}`}>{p.team}</span>}</td>
                  <td className="muted">{p.kind}</td>
                  <td className="num">{p.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
