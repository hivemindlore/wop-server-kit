import type { LogChange, LogLine } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'

export const MAX_LINES = 5000

/**
 * The server's log, as the kit reads it from home/wop/qconsole.log. Keeps the last MAX_LINES lines and
 * passes on only what changed, so a busy server doesn't mean sending the whole log again every half second.
 */
export class LogModel {
  private lines: LogLine[] = []
  private loaded = false
  private listeners = new Set<(change: LogChange) => void>()

  constructor(
    private readonly bridge: Bridge,
    private readonly openFolderInOs: () => Promise<unknown> = () => bridge.request('open.log_folder')
  ) {
    bridge.on('event', (name, data) => {
      if (name === 'log.lines') this.append((data as { lines: LogLine[] }).lines)
      else if (name === 'log.reset') this.reset()
    })
  }

  subscribe(listener: (change: LogChange) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  /** Everything kept so far; the first time, the end of the log file. */
  async history(): Promise<LogLine[]> {
    if (!this.loaded) {
      const { lines } = await this.bridge.request<{ lines: LogLine[] }>('log.history', { lines: 500 })
      this.lines = [...lines, ...this.lines].slice(-MAX_LINES)
      this.loaded = true
    }
    return this.lines
  }

  async openFolder(): Promise<void> {
    await this.openFolderInOs()
  }

  private append(lines: LogLine[]): void {
    if (!lines.length) return
    this.lines = [...this.lines, ...lines].slice(-MAX_LINES)
    this.emit({ type: 'append', lines })
  }

  private reset(): void {
    this.lines = []
    this.emit({ type: 'reset' })
  }

  private emit(change: LogChange): void {
    for (const listener of this.listeners) listener(change)
  }
}
