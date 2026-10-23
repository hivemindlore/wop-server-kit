import type { ReactNode } from 'react'

// Small building blocks for the views. They only draw; behaviour comes in through props.

export function Card(props: { title?: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${props.className ?? ''}`}>
      {(props.title || props.aside) && (
        <header className="card-head">
          {props.title && <h2>{props.title}</h2>}
          {props.aside}
        </header>
      )}
      {props.children}
    </section>
  )
}

export function Button(props: {
  children: ReactNode
  onClick?: () => void
  kind?: 'primary' | 'secondary' | 'quiet' | 'danger' | 'play'
  disabled?: boolean
  type?: 'button' | 'submit'
  title?: string
}) {
  return (
    <button
      type={props.type ?? 'button'}
      className={`btn btn-${props.kind ?? 'secondary'}`}
      onClick={props.onClick}
      disabled={props.disabled}
      title={props.title}
    >
      {props.children}
    </button>
  )
}

export function Notice(props: { kind: 'info' | 'error' | 'ok' | 'warn'; children: ReactNode }) {
  return (
    <div className={`notice notice-${props.kind}`} role={props.kind === 'error' ? 'alert' : 'status'}>
      {props.children}
    </div>
  )
}

export function Dot(props: { tone: 'on' | 'off' | 'busy' | 'ok' | 'problems' | 'checking' | 'unknown' }) {
  return <span className={`dot dot-${props.tone}`} aria-hidden="true" />
}

export function CopyValue(props: { label: string; value: string; copied: boolean; onCopy: () => void; hint?: string }) {
  return (
    <div className="copy-value">
      <span className="copy-label">{props.label}</span>
      <code>{props.value}</code>
      {props.hint && <span className="copy-hint">{props.hint}</span>}
      <Button kind="quiet" onClick={props.onCopy}>
        {props.copied ? 'Copied!' : 'Copy'}
      </Button>
    </div>
  )
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />
}

export function ProgressBar(props: { percent: number | null }) {
  return (
    <div className={`progress ${props.percent === null ? 'progress-busy' : ''}`}>
      <div className="progress-fill" style={{ width: props.percent === null ? '35%' : `${props.percent}%` }} />
    </div>
  )
}
