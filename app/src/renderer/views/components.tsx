import type { ReactNode } from 'react'

// Small building blocks for the views. They only draw; behaviour comes in through props.

// Line icons, 24×24, drawn with currentColor. Paths adapted from Lucide (https://lucide.dev, ISC license).
const ICONS = {
  power: '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>' +
    '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  home: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
  wifi: '<path d="M12 20h.01"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M5 12.86a10 10 0 0 1 14 0"/>' +
    '<path d="M8.5 16.43a5 5 0 0 1 7 0"/>',
  settings: '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" ' +
    'y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" ' +
    'y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" ' +
    'x2="16" y1="18" y2="22"/>',
  gamepad: '<line x1="6" x2="10" y1="12" y2="12"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="15" x2="15.01" ' +
    'y1="13" y2="13"/><line x1="18" x2="18.01" y1="11" y2="11"/><rect width="20" height="12" x="2" y="6" rx="2"/>',
  message: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
  target: '<circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" ' +
    'y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/>',
  flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/>',
  terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
  list: '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/>' +
    '<path d="M8 6h13"/>',
  sparkles: '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14' +
    'a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 ' +
    '6.14a.5.5 0 0 1-.96 0z"/>',
  server: '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/>' +
    '<line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/>',
  restart: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>' +
    '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
  send: '<path d="M14.54 21.69a.5.5 0 0 0 .94-.03l6.5-19a.5.5 0 0 0-.64-.63l-19 6.5a.5.5 0 0 0-.02.93l7.93 3.18a2 2 0 0 1 ' +
    '1.11 1.11z"/><path d="m21.85 2.15-10.94 10.94"/>',
  minus: '<path d="M5 12h14"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'
}

export type IconName = keyof typeof ICONS

export function Icon(props: { name: IconName; size?: number }) {
  const size = props.size ?? 18
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: ICONS[props.name] }}
    />
  )
}

/** The title of a tab, with one sentence about what it's for. */
export function PageHeader(props: { title: string; description: string; aside?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{props.title}</h1>
        <p>{props.description}</p>
      </div>
      {props.aside}
    </header>
  )
}

/** A block of the page: an icon, a title, one line about it, and its content. */
export function Section(props: {
  title?: string
  description?: ReactNode
  icon?: IconName
  aside?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`section ${props.className ?? ''}`}>
      {(props.title || props.aside) && (
        <header className="section-head">
          {props.icon && (
            <span className="section-icon">
              <Icon name={props.icon} />
            </span>
          )}
          <div className="section-titles">
            {props.title && <h2>{props.title}</h2>}
            {props.description && <p>{props.description}</p>}
          </div>
          {props.aside && <div className="section-aside">{props.aside}</div>}
        </header>
      )}
      <div className="section-body">{props.children}</div>
    </section>
  )
}

/** One setting: what it is on the left, the control on the right (below it on narrow windows). */
export function SettingRow(props: { label: string; description?: ReactNode; children: ReactNode }) {
  return (
    <div className="setting-row">
      <div className="setting-text">
        <span className="setting-label">{props.label}</span>
        {props.description && <p className="setting-description">{props.description}</p>}
      </div>
      <div className="setting-control">{props.children}</div>
    </div>
  )
}

/** A numbered step with a title. */
export function Step(props: { number: number; title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <section className="step">
      <header className="step-head">
        <span className="step-number">{props.number}</span>
        <div>
          <h3>{props.title}</h3>
          {props.description && <p>{props.description}</p>}
        </div>
      </header>
      <div className="step-body">{props.children}</div>
    </section>
  )
}

export function Button(props: {
  children: ReactNode
  onClick?: () => void
  kind?: 'primary' | 'secondary' | 'quiet' | 'danger' | 'play' | 'success' | 'info'
  icon?: IconName
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
      {props.icon && <Icon name={props.icon} size={props.kind === 'play' ? 20 : 16} />}
      {props.children}
    </button>
  )
}

export function Switch(props: { on: boolean; label: string; disabled?: boolean; busy?: boolean; large?: boolean;
  onToggle: () => void }) {
  return (
    <button
      className={`switch ${props.large ? '' : 'switch-small'} ${props.on ? 'switch-on' : ''}`}
      role="switch"
      aria-checked={props.on}
      aria-label={props.label}
      disabled={props.disabled}
      onClick={props.onToggle}
    >
      <span className="switch-knob">{props.busy && <Spinner />}</span>
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
      <div className="copy-main">
        <code>{props.value}</code>
        {props.hint && <span className="copy-hint">{props.hint}</span>}
      </div>
      <Button kind="secondary" onClick={props.onCopy}>
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
