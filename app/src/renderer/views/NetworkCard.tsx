import type { NetworkView } from '../viewmodels/network'
import { Button, Card, Dot, Notice } from './components'

export function NetworkCard(props: {
  view: NetworkView
  onFix: () => void
  onCheck: () => void
  onOpenUrl: (url: string) => void
}) {
  const { view } = props
  return (
    <Card
      title="Can other computers find your server?"
      aside={
        <Button kind="quiet" onClick={props.onCheck} disabled={view.status === 'checking' || view.fixing}>
          Check again
        </Button>
      }
    >
      <p className="status-line">
        <Dot tone={view.status} />
        {view.title}
      </p>
      {view.problems.length > 0 && (
        <ul className="problems">
          {view.problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
      {view.canFix && (
        <div className="fix-row">
          <Button kind="primary" onClick={props.onFix}>
            {view.fixLabel}
          </Button>
          {view.permissionHint && <span className="muted">{view.permissionHint}</span>}
        </div>
      )}
      {view.fixing && <p className="muted">{view.title} Your computer may show a permission question.</p>}
      {view.notes.map((note) => (
        <Notice key={note} kind="warn">
          {note}
        </Notice>
      ))}
      {view.others && <Notice kind="warn">{view.others}</Notice>}
      {view.error && <Notice kind="error">{view.error}</Notice>}
      {view.helpUrl && (
        <p className="muted">
          Still stuck?{' '}
          <a href={view.helpUrl} onClick={(e) => (e.preventDefault(), props.onOpenUrl(view.helpUrl!))}>
            Open the help page
          </a>
          . Also check that everyone is on the same Wi-Fi (a guest Wi-Fi usually doesn't work).
        </p>
      )}
    </Card>
  )
}
