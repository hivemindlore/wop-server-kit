import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { GameViewModel, type Limit, type LimitView } from '../viewmodels/GameViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, Icon, Notice, PageHeader, Section, SettingRow, Spinner, Step, Switch } from './components'

function LimitField(props: { label: string; which: Limit; view: LimitView; vm: GameViewModel }) {
  const { which, view, vm } = props
  return (
    <div className="limit">
      <span className="setting-label">{props.label}</span>
      <div className="stepper">
        <button
          className="stepper-button"
          aria-label={`Fewer ${which}`}
          disabled={!view.canLower}
          onClick={() => vm.stepLimit(which, -1)}
        >
          <Icon name="minus" size={16} />
        </button>
        <input
          inputMode="numeric"
          aria-label={props.label}
          value={view.text}
          onChange={(e) => vm.typeLimit(which, e.target.value)}
          onBlur={() => vm.commitLimit(which)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') vm.commitLimit(which)
            if (e.key === 'ArrowUp') (e.preventDefault(), vm.stepLimit(which, 1))
            if (e.key === 'ArrowDown') (e.preventDefault(), vm.stepLimit(which, -1))
          }}
        />
        <button
          className="stepper-button"
          aria-label={`More ${which}`}
          disabled={!view.canRaise}
          onClick={() => vm.stepLimit(which, 1)}
        >
          <Icon name="plus" size={16} />
        </button>
      </div>
      <span className="muted small limit-note">{view.note}</span>
    </div>
  )
}

export function GameTab({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new GameViewModel(api), [api]))
  const view = useViewModel(vm)
  const { draft, footer } = view

  return (
    <div className="page page-with-footer">
      <PageHeader title="Game" description="See what's playing, talk to the players, and change the game." />

      {view.notice && <Notice kind={view.notice.kind}>{view.notice.text}</Notice>}

      <div className="two-col">
        <Section icon="gamepad" title="Now playing">
          {view.serverOn === null && (
            <p className="muted">
              <Spinner /> Looking for your server...
            </p>
          )}
          {view.serverOn === false && (
            <div className="stack">
              <p className="muted">Your server is off. Start it to play and to change the game.</p>
              <div className="button-row">
                <Button kind="primary" icon="power" disabled={view.startingServer} onClick={() => vm.startServer()}>
                  {view.startingServer ? 'Starting...' : 'Start the server'}
                </Button>
              </div>
            </div>
          )}
          {view.serverOn && view.nowPlaying && (
            <div className="now-playing">
              <p className="now-playing-title">
                {view.nowPlaying.mode} <span className="muted">on</span> {view.nowPlaying.map}
              </p>
              <dl className="facts">
                <dt>Weapons</dt>
                <dd>{view.nowPlaying.weapons}</dd>
                <dt>Ends at</dt>
                <dd>{view.nowPlaying.limits}</dd>
                <dt>On the server</dt>
                <dd>{view.nowPlaying.people}</dd>
              </dl>
              {view.nowPlaying.loop && <p className="muted small">{view.nowPlaying.loop}</p>}
            </div>
          )}
        </Section>

        <Section icon="message" title="Message to the server" description="Everyone playing sees it on their screen.">
          <form
            className="message-form"
            onSubmit={(e) => {
              e.preventDefault()
              vm.sendMessage()
            }}
          >
            <textarea
              rows={3}
              value={view.message}
              placeholder={view.serverOn ? 'For example: Dinner in 5 minutes!' : 'Start the server to send a message'}
              disabled={!view.serverOn}
              onChange={(e) => vm.setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) (e.preventDefault(), vm.sendMessage())
              }}
            />
            <div className="button-row">
              <Button kind="primary" icon="send" type="submit" disabled={!view.canSend}>
                {view.sendLabel}
              </Button>
            </div>
          </form>
        </Section>
      </div>

      {view.weapons && (
        <Section icon="target" title="Weapons" description={view.weapons.note}>
          <SettingRow label="Weapons" description="All weapons, or InstaPad where one hit wins.">
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
          </SettingRow>
          {view.spawnProtection && (
            <SettingRow label={view.spawnProtection.label} description={view.spawnProtection.hint}>
              <Switch
                on={view.spawnProtection.on}
                label={view.spawnProtection.label}
                disabled={view.spawnProtection.disabled}
                onToggle={() => vm.toggleSpawnProtection()}
              />
            </SettingRow>
          )}
        </Section>
      )}

      <Section
        icon="flag"
        title="Change the game"
        description="Choose a game mode, its maps, the bots and when a match ends. Then press Apply changes below."
        aside={
          draft && (
            <Button kind="quiet" onClick={() => vm.resetDraft()}>
              Usual setup for this mode
            </Button>
          )
        }
      >
        {!draft ? (
          <p className="muted">
            <Spinner /> Getting the game modes...
          </p>
        ) : (
          <div className="steps">
            <Step number={1} title="Game mode">
              <div className="mode-grid" role="radiogroup" aria-label="Game mode">
                {draft.modes.map((mode) => (
                  <button
                    key={mode.key}
                    role="radio"
                    aria-checked={mode.selected}
                    className={`option-card ${mode.selected ? 'option-card-selected' : ''}`}
                    onClick={() => vm.pickMode(mode.key)}
                  >
                    <span className="option-card-title">
                      {mode.name}
                      {mode.selected && <Icon name="check" size={16} />}
                    </span>
                    <span className="option-card-text">{mode.description}</span>
                    <span className="option-card-kind">{mode.teamMode ? 'Teams' : 'Everyone for themselves'}</span>
                  </button>
                ))}
              </div>
            </Step>

            <Step
              number={2}
              title="Maps"
              description="Pick one map, or several to play one after another. After the last one it starts over."
            >
              <div className="map-grid">
                {draft.maps.map((map) => (
                  <button
                    key={map.id}
                    aria-pressed={map.order !== null}
                    className={`map-option ${map.order !== null ? 'map-option-selected' : ''}`}
                    onClick={() => vm.toggleMap(map.id)}
                  >
                    <span className="map-order">{map.order ?? ''}</span>
                    {map.label}
                  </button>
                ))}
              </div>
              <p className="loop-text">
                <Icon name="restart" size={14} /> {draft.loopText}
              </p>
            </Step>

            <Step number={3} title="Bots" description={draft.places.text}>
              <div className={`team-columns ${draft.lists.length === 1 ? 'team-columns-single' : ''}`}>
                {draft.lists.map((list) => (
                  <div key={list.id} className={`team-column team-column-${list.tone}`}>
                    <h4>
                      {list.label} <span className="muted">· {list.bots.length}</span>
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
                            <Icon name="x" size={12} />
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
              <div className="skill-row">
                <span className="setting-label">How good the bots are</span>
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
              </div>
            </Step>

            <Step number={4} title="A match ends at" description="Whichever comes first. 0 means no limit.">
              <div className="limits">
                <LimitField label="Points" which="points" view={draft.points} vm={vm} />
                <span className="limits-or">or</span>
                <LimitField label="Minutes" which="minutes" view={draft.minutes} vm={vm} />
              </div>
              {draft.limitsHint && <Notice kind="warn">{draft.limitsHint}</Notice>}
            </Step>
          </div>
        )}
      </Section>

      <footer className="action-bar">
        <p className={`action-bar-hint ${footer.warn ? 'action-bar-warn' : ''}`}>{footer.hint}</p>
        <div className="action-bar-buttons">
          <Button kind="info" icon="restart" disabled={footer.restart.disabled} onClick={() => vm.restartMatch()}>
            {footer.restart.label}
          </Button>
          <Button
            kind="secondary"
            icon="save"
            title={footer.save.hint}
            disabled={footer.save.disabled}
            onClick={() => vm.saveAsStartup()}
          >
            {footer.save.label}
          </Button>
          <Button kind="success" icon="check" disabled={footer.apply.disabled} onClick={() => vm.apply()}>
            {footer.apply.label}
          </Button>
        </div>
      </footer>
    </div>
  )
}
