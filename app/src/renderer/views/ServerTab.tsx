import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { ServerViewModel } from '../viewmodels/ServerViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, Card, CopyValue, Notice, Spinner } from './components'
import { NetworkCard } from './NetworkCard'

export function ServerTab({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new ServerViewModel(api), [api]))
  const view = useViewModel(vm)
  const { power, join, online } = view

  return (
    <div className="grid">
      <Card className={`power power-${power.tone}`}>
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
          <Button kind="play" onClick={() => vm.play()}>
            ▶ Play World of PADMAN
          </Button>
        </div>
      </Card>

      <Card title="How others join">
        {!join ? (
          <p className="muted">
            <Spinner /> Looking up your network...
          </p>
        ) : (
          <>
            <ol className="steps">
              <li>
                Everyone needs World of PADMAN 1.7.0 (free):{' '}
                <a href={join.downloadUrl} onClick={(e) => (e.preventDefault(), vm.openUrl(join.downloadUrl))}>
                  download it here
                </a>
                , and has to be on the same Wi-Fi or network as this computer.
              </li>
              <li>
                In the game: <strong>Multiplayer</strong> → set the source to <strong>LAN</strong> → pick{' '}
                <strong>{join.serverName}</strong> → <strong>Join</strong>.
              </li>
              <li>Not in the list? Click <strong>Specify</strong> in the Multiplayer screen and fill in:</li>
            </ol>
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
            <CopyValue label="Port" value={join.port} copied={view.copied === join.port} onCopy={() => vm.copy(join.port)} />
            {join.connectLine && (
              <CopyValue
                label="Or type"
                value={join.connectLine}
                hint="in the game's console (press ~)"
                copied={view.copied === join.connectLine}
                onCopy={() => vm.copy(join.connectLine!)}
              />
            )}
            {join.passwordLine && (
              <CopyValue
                label="Password"
                value={join.passwordLine}
                hint="players type this in the console first"
                copied={view.copied === join.passwordLine}
                onCopy={() => vm.copy(join.passwordLine!)}
              />
            )}
            {join.warning && <Notice kind="warn">{join.warning}</Notice>}
          </>
        )}
        {online && (
          <div className="online">
            <div className="setting setting-row">
              <div>
                <span className="setting-label">{online.label}</span>
                <p className="muted small">{online.hint}</p>
              </div>
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
            </div>
            {online.note && (
              <p className="muted">
                {online.approveUrl && <Spinner />} {online.note}
              </p>
            )}
            {online.approveUrl && (
              <div className="power-actions">
                <Button kind="secondary" onClick={() => vm.openUrl(online.approveUrl!)}>
                  Open the page again
                </Button>
                <Button kind="quiet" onClick={() => vm.toggleOnline()}>
                  Cancel
                </Button>
              </div>
            )}
            {online.address && (
              <>
                <p>Friends somewhere else click <strong>Specify</strong> in the Multiplayer screen and fill in:</p>
                <CopyValue
                  label="Address"
                  value={online.address}
                  hint="from anywhere"
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
              </>
            )}
            {online.problem && <Notice kind="error">{online.problem}</Notice>}
            {online.passwordTip && <Notice kind="warn">{online.passwordTip}</Notice>}
            {online.manageLabel && (
              <div className="power-actions">
                <Button kind="quiet" onClick={() => vm.manageOnline()}>
                  {online.manageLabel}
                </Button>
              </div>
            )}
          </div>
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
        {view.weapons && (
          <div className="setting">
            <span className="setting-label">Weapons</span>
            <div className="choice" role="radiogroup" aria-label="Weapons">
              {view.weapons.options.map((option) => (
                <button
                  key={option.id}
                  role="radio"
                  aria-checked={option.selected}
                  className={`choice-option ${option.selected ? 'choice-selected' : ''}`}
                  disabled={view.weapons!.disabled}
                  onClick={() => vm.chooseWeapons(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <span className="muted small">{view.weapons.note}</span>
          </div>
        )}
        {view.spawnProtection && (
          <div className="setting setting-row">
            <div>
              <span className="setting-label">{view.spawnProtection.label}</span>
              <p className="muted small">{view.spawnProtection.hint}</p>
            </div>
            <button
              className={`switch switch-small ${view.spawnProtection.on ? 'switch-on' : ''}`}
              role="switch"
              aria-checked={view.spawnProtection.on}
              aria-label={view.spawnProtection.label}
              disabled={view.spawnProtection.disabled}
              onClick={() => vm.toggleSpawnProtection()}
            >
              <span className="switch-knob" />
            </button>
          </div>
        )}
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
