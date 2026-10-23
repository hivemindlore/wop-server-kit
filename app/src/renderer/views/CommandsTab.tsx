import { useEffect, useMemo, useRef } from 'react'
import type { WopApi } from '@shared/api'
import { CommandsViewModel } from '../viewmodels/CommandsViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, Card, Notice } from './components'

export function CommandsTab({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new CommandsViewModel(api), [api]))
  const view = useViewModel(vm)
  const output = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (output.current) output.current.scrollTop = output.current.scrollHeight
  }, [view.entries])

  return (
    <div className="grid commands">
      <Card title="Quick actions" className="span-2">
        <div className="quick">
          {view.quickActions.map((action) => (
            <button
              key={action.id}
              className="quick-action"
              disabled={view.serverOff}
              onClick={() => vm.quick(action)}
            >
              <strong>{action.label}</strong>
              <span>{action.description}</span>
            </button>
          ))}
        </div>
        {view.openAction && (
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault()
              vm.confirmAction()
            }}
          >
            <input
              autoFocus
              value={view.openAction.text}
              placeholder={view.openAction.action.input?.placeholder}
              onChange={(e) => vm.setActionText(e.target.value)}
            />
            <Button kind="primary" type="submit" disabled={!view.openAction.text.trim()}>
              Send
            </Button>
            <Button kind="quiet" onClick={() => vm.cancelAction()}>
              Cancel
            </Button>
          </form>
        )}
      </Card>

      <Card
        title="Server console"
        className="span-2"
        aside={
          view.entries.length > 0 && (
            <Button kind="quiet" onClick={() => vm.clear()}>
              Clear
            </Button>
          )
        }
      >
        {view.serverOff && <Notice kind="warn">The server is off. Start it on the Server tab to use commands.</Notice>}
        <div className="console-output" ref={output}>
          {view.entries.length === 0 && (
            <p className="muted">Type a command below, or pick an example. The server's answer shows here.</p>
          )}
          {view.entries.map((entry) => (
            <div key={entry.id} className="console-entry">
              <div className="console-command">&gt; {entry.command}</div>
              <pre className={entry.failed ? 'console-failed' : ''}>{entry.output}</pre>
            </div>
          ))}
        </div>
        <form
          className="console-input"
          onSubmit={(e) => {
            e.preventDefault()
            vm.submit()
          }}
        >
          <input
            value={view.draft}
            placeholder="For example: g_gravity 400"
            spellCheck={false}
            onChange={(e) => vm.setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowUp') (e.preventDefault(), vm.browseHistory('older'))
              if (e.key === 'ArrowDown') (e.preventDefault(), vm.browseHistory('newer'))
            }}
          />
          <Button kind="primary" type="submit" disabled={!view.canRun}>
            {view.busy ? 'Running...' : 'Run'}
          </Button>
        </form>
      </Card>

      <Card title="Examples" className="span-2">
        <ul className="examples">
          {view.examples.map((example) => (
            <li key={example.command}>
              <button className="link-button" onClick={() => vm.useExample(example.command)}>
                <code>{example.command}</code>
              </button>
              <span>{example.meaning}</span>
            </li>
          ))}
        </ul>
        <p className="muted">Tip: the AI tab lets you do all of this by just asking an AI.</p>
      </Card>
    </div>
  )
}
