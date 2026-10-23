import { useMemo } from 'react'
import type { WopApi } from '@shared/api'
import { AiViewModel } from '../viewmodels/AiViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, Card, Notice, Spinner } from './components'

export function AiTab({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new AiViewModel(api), [api]))
  const view = useViewModel(vm)

  return (
    <div className="ai">
      <p className="intro">{view.intro}</p>
      {view.loading && <Spinner />}
      <div className="ai-cards">
        {view.cards.map((card) => (
          <Card
            key={card.id}
            title={card.name}
            className={`ai-card ai-${card.status}`}
            aside={card.statusLabel && <span className={`badge badge-${card.status}`}>{card.statusLabel}</span>}
          >
            <p className="muted small">{card.price}</p>
            <p>{card.blurb}</p>
            {card.advice && <p className="advice">{card.advice}</p>}
            {card.examples.length > 0 && (
              <div className="ask">
                <span className="muted small">Then ask, for example:</span>
                <ul>
                  {card.examples.map((example) => (
                    <li key={example}>“{example}”</li>
                  ))}
                </ul>
              </div>
            )}
            {card.notice && <Notice kind={card.notice.kind}>{card.notice.text}</Notice>}
            <div className="card-actions">
              {card.action && (
                <Button
                  kind={card.action.kind === 'connect' ? 'primary' : 'secondary'}
                  disabled={card.action.disabled}
                  onClick={() => (card.action!.kind === 'connect' ? vm.connect(card.id) : vm.disconnect(card.id))}
                >
                  {card.action.label}
                </Button>
              )}
              {card.open && (
                <Button
                  kind={card.open.kind === 'restart' ? 'primary' : 'secondary'}
                  disabled={card.open.disabled}
                  onClick={() => vm.openApp(card.id)}
                >
                  {card.open.label}
                </Button>
              )}
              {card.download && (
                <Button kind="quiet" onClick={() => vm.openUrl(card.download!.url)}>
                  {card.download.label}
                </Button>
              )}
            </div>
          </Card>
        ))}
      </div>
      <p className="muted small">
        Installed an app just now? <button className="link-button" onClick={() => vm.refresh()}>Check again</button>
      </p>
    </div>
  )
}
