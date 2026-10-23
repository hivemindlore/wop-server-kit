import { useEffect, useMemo, useRef } from 'react'
import type { WopApi } from '@shared/api'
import { LogsViewModel } from '../viewmodels/LogsViewModel'
import { useActive, useViewModel } from '../viewmodels/ViewModel'
import { Button, PageHeader, Spinner } from './components'

export function LogsTab({ api }: { api: WopApi }) {
  const vm = useActive(useMemo(() => new LogsViewModel(api), [api]))
  const view = useViewModel(vm)
  const box = useRef<HTMLDivElement>(null)

  // Stay at the newest line while following
  useEffect(() => {
    if (view.follow && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [view.rows, view.follow])

  return (
    <div className="page page-wide logs">
      <PageHeader title="Logs" description="Everything the server says, live." />
      <div className="toolbar">
        <input
          type="search"
          placeholder="Search the log"
          value={view.filter}
          onChange={(e) => vm.setFilter(e.target.value)}
        />
        <span className="muted">{view.total} lines</span>
        {!view.follow && (
          <Button kind="quiet" onClick={() => vm.setFollow(true)}>
            Jump to newest
          </Button>
        )}
        <Button kind="quiet" onClick={() => void vm.copyAll()}>
          Copy
        </Button>
        <Button kind="quiet" onClick={() => vm.openFolder()}>
          Open log folder
        </Button>
      </div>
      <div
        className="log-box"
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget
          vm.setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 24)
        }}
      >
        {view.loading && <Spinner />}
        {view.emptyText && <p className="muted">{view.emptyText}</p>}
        {view.rows.map((row) => (
          <div key={row.key} className="log-line">
            {row.segments.map((segment, i) => (
              <span key={i} className={segment.color ? `c-${segment.color}` : undefined}>
                {segment.text}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
