import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { ServerViewModel } from '../viewmodels/ServerViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, CopyValue, Icon, Notice, PageHeader, Section, SettingRow, Spinner, Switch } from './components'
import { NetworkCard } from './NetworkCard'

export function MyServerTab({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new ServerViewModel(api), [api]))
  const view = useViewModel(vm)
  const { power, join, online } = view

  return (
    <div className="page">
      <PageHeader title="My server" description="Turn your server on, play, and let others join." />

      <Section
        icon="power"
        title="Server"
        className={`power power-${power.tone}`}
        aside={
          <Switch
            large
            on={power.on}
            label={power.buttonLabel}
            busy={power.busy}
            disabled={power.busy || !power.known}
            onToggle={() => vm.toggle()}
          />
        }
      >
        <div className="power-status">
          <span className={`status-dot status-dot-${power.tone}`} aria-hidden="true" />
          <div>
            <p className="power-headline">{power.headline}</p>
            {view.game ? (
              <p className="muted">
                <strong className="text-strong">{view.game.mode}</strong> on{' '}
                <strong className="text-strong">{view.game.map}</strong> · {view.game.weapons} · {view.game.limits}
              </p>
            ) : (
              power.hint && <p className="muted">{power.hint}</p>
            )}
            {view.playersSummary && <p className="muted small">{view.playersSummary}</p>}
          </div>
        </div>
        {view.notice && <Notice kind={view.notice.kind}>{view.notice.text}</Notice>}
      </Section>

      <Section icon="play" title="Play World of PADMAN" description="Play on this computer: on your server or any other.">
        <Button kind="play" icon="play" disabled={view.play.disabled} onClick={() => vm.play()}>
          {view.play.label}
        </Button>
      </Section>

      <Section icon="users" title="How others join" description="Friends at home or anywhere can join your server.">
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
                    Join password <code>{join.password}</code>
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
                  <span className="join-badge">
                    <Icon name="home" />
                  </span>
                  <div>
                    <h3>Same Wi-Fi or home network</h3>
                    <p className="muted small">The server shows up in the game's list.</p>
                  </div>
                </header>
                <ol className="step-list">
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
                    <span className="join-badge">
                      <Icon name="globe" />
                    </span>
                    <div>
                      <h3>Friends anywhere</h3>
                      <p className="muted small">Over the internet, through playit.gg (free).</p>
                    </div>
                    <Switch
                      on={online.on}
                      label={online.label}
                      busy={online.busy}
                      disabled={online.busy}
                      onToggle={() => vm.toggleOnline()}
                    />
                  </header>
                  {online.state === 'off' && <p className="muted small">{online.hint}</p>}
                  {online.state === 'approving' && (
                    <>
                      <p>
                        <Spinner /> {online.note}
                      </p>
                      <div className="button-row">
                        <Button kind="secondary" onClick={() => vm.openUrl(online.approveUrl!)}>
                          Open the page again
                        </Button>
                        <Button kind="quiet" onClick={() => vm.toggleOnline()}>
                          Cancel
                        </Button>
                      </div>
                    </>
                  )}
                  {online.state === 'waiting' && online.note && <p className="muted small">{online.note}</p>}
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
                    <div className="button-row">
                      <Button kind="quiet" onClick={() => vm.manageOnline()}>
                        {online.manageLabel}
                      </Button>
                    </div>
                  )}
                </section>
              )}
            </div>
          </>
        )}
      </Section>

      <NetworkCard
        view={view.network}
        onFix={() => vm.fixNetwork()}
        onCheck={() => vm.checkNetwork()}
        onOpenUrl={(url) => vm.openUrl(url)}
      />

      <Section icon="settings" title="Settings" description="The name players see, who may join, and a fresh start.">
        <SettingRow label="Server name" description="Players see this name in the game's server list.">
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
              <strong className="text-strong">{join?.serverName ?? ''}</strong>
              <Button kind="secondary" onClick={() => vm.editName()} disabled={view.saving}>
                Rename
              </Button>
            </div>
          )}
        </SettingRow>
        <SettingRow
          label="Join password"
          description={join?.password ? 'Players need this password to join.' : 'None: anyone who finds the server can join.'}
        >
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault()
              void vm.savePassword()
            }}
          >
            <input
              value={view.passwordDraft}
              placeholder={join?.password ? 'New password' : 'Set a password'}
              onChange={(e) => vm.setPasswordDraft(e.target.value)}
            />
            <Button kind="secondary" type="submit" disabled={!view.passwordDraft || view.saving}>
              Set
            </Button>
            {join?.password && (
              <Button kind="quiet" onClick={() => vm.removePassword()} disabled={view.saving}>
                Remove
              </Button>
            )}
          </form>
        </SettingRow>
        <SettingRow
          label="Reset to defaults"
          description="Game mode, map, bots, weapons and join password as after installing. The name stays."
        >
          {!view.reset.confirming && (
            <Button kind="secondary" onClick={() => vm.askReset()} disabled={view.saving}>
              {view.reset.busy ? 'Resetting...' : 'Reset...'}
            </Button>
          )}
        </SettingRow>
        {view.reset.confirming && (
          <div className="confirm">
            <Notice kind="warn">{view.reset.warning}</Notice>
            <div className="button-row">
              <Button kind="danger" onClick={() => vm.confirmReset()}>
                Reset to defaults
              </Button>
              <Button kind="quiet" onClick={() => vm.cancelReset()}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </Section>

      {view.players.length > 0 && (
        <Section icon="users" title="Who's on" description={view.playersSummary}>
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
                  <td className="text-strong">{p.name}</td>
                  <td>{p.team && <span className={`team-badge team-badge-${p.teamTone}`}>{p.team}</span>}</td>
                  <td className="muted">{p.kind}</td>
                  <td className="num">{p.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
    </div>
  )
}
