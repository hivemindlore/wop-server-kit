import type { LogChange, LogLine, WopApi } from '@shared/api'
import { ViewModel } from './ViewModel'

export const MAX_LINES = 5000

export interface LogRow {
  key: number
  segments: LogLine
}

export interface LogsView {
  rows: LogRow[]
  total: number
  filter: string
  follow: boolean
  emptyText: string | null
  loading: boolean
}

/** The Logs tab: everything the server prints, newest at the bottom, with a search box. */
export class LogsViewModel extends ViewModel<LogsView> {
  private lines: LogRow[] = []
  private nextKey = 0
  private filter = ''
  private follow = true
  private loading = true

  constructor(api: WopApi) {
    super(api)
    this.source(() => api.onLogs((change) => this.apply(change)))
    void api.call('logs', 'history').then((lines) => {
      this.lines = [...lines.map((segments) => this.row(segments)), ...this.lines].slice(-MAX_LINES)
      this.loading = false
      this.changed()
    })
  }

  protected present(): LogsView {
    const needle = this.filter.trim().toLowerCase()
    const rows = needle
      ? this.lines.filter((row) => row.segments.map((s) => s.text).join('').toLowerCase().includes(needle))
      : this.lines
    let emptyText: string | null = null
    if (!this.loading && !this.lines.length) emptyText = 'Nothing yet. Start the server and its messages appear here.'
    else if (!this.loading && !rows.length) emptyText = `No lines with "${this.filter.trim()}".`
    return { rows, total: this.lines.length, filter: this.filter, follow: this.follow, emptyText, loading: this.loading }
  }

  setFilter(filter: string): void {
    this.filter = filter
    this.changed()
  }

  /** The view turns following off when the user scrolls up, and on again at the bottom. */
  setFollow(follow: boolean): void {
    if (follow === this.follow) return
    this.follow = follow
    this.changed()
  }

  text(): string {
    return this.getSnapshot().rows.map((row) => row.segments.map((s) => s.text).join('')).join('\n')
  }

  async copyAll(write: (text: string) => Promise<void> = (t) => navigator.clipboard.writeText(t)): Promise<void> {
    await write(this.text())
  }

  openFolder(): void {
    void this.api.call('logs', 'openFolder')
  }

  private apply(change: LogChange): void {
    if (change.type === 'reset') this.lines = []
    else this.lines = [...this.lines, ...change.lines.map((segments) => this.row(segments))].slice(-MAX_LINES)
    this.changed()
  }

  private row(segments: LogLine): LogRow {
    return { key: this.nextKey++, segments }
  }
}
