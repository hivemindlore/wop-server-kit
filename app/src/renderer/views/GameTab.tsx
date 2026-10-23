import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { GameViewModel } from '../viewmodels/GameViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, Card, Notice, Spinner } from './components'

export function GameTab({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new GameViewModel(api), [api]))
  const view = useViewModel(vm)
  const { draft } = view

  return (
    <div className="grid">
      {view.notice && (
        <div className="span-2">
          <Notice kind={view.notice.kind}>{view.notice.text}</Notice>
        </div>
      )}

      <Card title="Now playing" className="span-2">
        {view.serverOn === null && (
          <p className="muted">
            <Spinner /> Looking for your server...
          </p>
        )}
        {view.serverOn === false && (
          <div className="game-off">
            <p>Your server is off. Start it to play and to change the game.</p>
            <Button kind="primary" disabled={view.startingServer} onClick={() => vm.startServer()}>
              {view.startingServer ? 'Starting...' : 'Start the server'}
            </Button>
          </div>
        )}
        {view.serverOn && view.nowPlaying && (
          <>
            <p className="now-playing">
              <strong>{view.nowPlaying.mode}</strong> on <strong>{view.nowPlaying.map}</strong>
            </p>
            <p className="muted">
              {view.nowPlaying.weapons} · {view.nowPlaying.limits} · {view.nowPlaying.people}
            </p>
            <div className="now-actions">
              <form
                className="inline-form message-form"
                onSubmit={(e) => {
                  e.preventDefault()
                  vm.sendMessage()
                }}
              >
                <input
                  value={view.message}
                  placeholder="A message to everyone in the game"
                  onChange={(e) => vm.setMessage(e.target.value)}
                />
                <Button kind="secondary" type="submit" disabled={!view.canSend}>
                  {view.busy === 'sending' ? 'Sending...' : 'Send'}
                </Button>
              </form>
              <div className="card-actions">
                <Button kind="secondary" disabled={view.busy !== null} onClick={() => vm.restartMatch()}>
                  {view.busy === 'restarting' ? 'Restarting...' : 'Restart the match'}
                </Button>
                <Button kind="quiet" disabled={view.busy !== null} onClick={() => vm.saveAsStartup()}>
                  {view.busy === 'saving' ? 'Saving...' : 'Keep this as the game the server starts with'}
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      {view.weapons && (
        <Card title="Weapons" className="span-2">
          <div className="setting">
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
          {view.spawnProtection && (
            <div className="protection-row">
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
              <div>
                <strong>{view.spawnProtection.label}</strong>
                <p className="muted small">{view.spawnProtection.hint}</p>
              </div>
            </div>
          )}
        </Card>
      )}

      <Card title="Change the game" className="span-2">
        {!draft ? (
          <p className="muted">
            <Spinner /> Getting the game modes...
          </p>
        ) : (
          <div className="game-form">
            <section className="game-step">
              <h3>
                <span className="step-number">1</span> Game mode
              </h3>
              <div className="mode-grid" role="radiogroup" aria-label="Game mode">
                {draft.modes.map((mode) => (
                  <button
                    key={mode.key}
                    role="radio"
                    aria-checked={mode.selected}
                    className={`mode-card ${mode.selected ? 'mode-card-selected' : ''}`}
                    onClick={() => vm.pickMode(mode.key)}
                  >
                    <strong>{mode.name}</strong>
                    <span>{mode.description}</span>
                    <span className="mode-kind">{mode.teamMode ? 'Teams' : 'Everyone for themselves'}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="game-step">
              <h3>
                <span className="step-number">2</span> Map
              </h3>
              <select
                className="map-select"
                aria-label="Map"
                value={draft.maps.find((m) => m.selected)?.id ?? ''}
                onChange={(e) => vm.pickMap(e.target.value)}
              >
                {draft.maps.map((map) => (
                  <option key={map.id} value={map.id}>
                    {map.label}
                  </option>
                ))}
              </select>
            </section>

            <section className="game-step">
              <h3>
                <span className="step-number">3</span> Bots
              </h3>
              <div className={`team-columns ${draft.lists.length === 1 ? 'team-columns-single' : ''}`}>
                {draft.lists.map((list) => (
                  <div key={list.id} className={`team-column team-column-${list.tone}`}>
                    <h4>
                      {list.label} <span className="muted">({list.bots.length})</span>
                    </h4>
                    <ul className="bot-chips">
                      {list.bots.map((bot, i) => (
                        <li key={`${bot}-${i}`} className="bot-chip">
                          {bot}
                          <button
                            className="bot-remove"
                            aria-label={`Take ${bot} out`}
                            onClick={() => vm.removeBot(list.id, i)}
                          >
                            ×
                          </button>
                        </li>
                      ))}
                      {list.bots.length === 0 && <li className="muted small">No bots</li>}
                    </ul>
                    <select
                      className="add-bot"
                      aria-label={`Add a bot to ${list.label}`}
                      value=""
                      disabled={!draft.canAddBot}
                      onChange={(e) => vm.addBot(list.id, e.target.value)}
                    >
                      <option value="">+ Add a bot</option>
                      {draft.botChoices.map((bot) => (
                        <option key={bot} value={bot}>
                          {bot}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              <div className="bot-settings">
                <div className="choice" role="radiogroup" aria-label="How good the bots are">
                  {draft.skills.map((skill) => (
                    <button
                      key={skill.value}
                      role="radio"
                      aria-checked={skill.selected}
                      className={`choice-option ${skill.selected ? 'choice-selected' : ''}`}
                      onClick={() => vm.setSkill(skill.value)}
                    >
                      {skill.label}
                    </button>
                  ))}
                </div>
                <span className={`small ${draft.places.full ? 'places-full' : 'muted'}`}>{draft.places.text}</span>
              </div>
            </section>

            <section className="game-step">
              <h3>
                <span className="step-number">4</span> A match ends at
              </h3>
              <div className="limits">
                <label>
                  <input
                    type="number"
                    min={0}
                    max={999}
                    value={draft.points}
                    onChange={(e) => vm.setPoints(e.target.value)}
                  />{' '}
                  points
                </label>
                <span className="muted">or</span>
                <label>
                  <input
                    type="number"
                    min={0}
                    max={999}
                    value={draft.minutes}
                    onChange={(e) => vm.setMinutes(e.target.value)}
                  />{' '}
                  minutes
                </label>
                <span className="muted small">0 = no limit</span>
              </div>
            </section>

            <footer className="game-apply">
              <div className="card-actions">
                <Button kind="primary" disabled={!draft.canApply} onClick={() => vm.apply()}>
                  {draft.applyLabel}
                </Button>
                <Button kind="quiet" onClick={() => vm.resetDraft()}>
                  Back to the usual setup for this mode
                </Button>
              </div>
              <p className={`small ${draft.places.full ? 'places-full' : 'muted'}`}>{draft.hint}</p>
            </footer>
          </div>
        )}
      </Card>
    </div>
  )
}
