import { spawn, type ChildProcess } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { join } from 'node:path'
import { createInterface } from 'node:readline'
import type { KitPaths } from '../kitInstall'

/** A request the kit couldn't do; message is already worded for the user. */
export class BridgeError extends Error {}

export interface BridgeEvents {
  event: [name: string, data: unknown]
  exit: [code: number | null]
}

/** What the models need from the bridge, so tests can hand them a fake one. */
export interface Bridge {
  request<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T>
  on<K extends keyof BridgeEvents>(name: K, listener: (...args: BridgeEvents[K]) => void): unknown
  off<K extends keyof BridgeEvents>(name: K, listener: (...args: BridgeEvents[K]) => void): unknown
}

interface Pending {
  resolve(value: unknown): void
  reject(error: Error): void
}

/**
 * Runs kit/setup/appbridge.py with the kit's own uv and talks to it one JSON line at a time:
 * requests get answers by id, and the kit pushes events (log lines, setup progress) in between.
 */
export class BridgeClient extends EventEmitter<BridgeEvents> implements Bridge {
  private child: ChildProcess | null = null
  private nextId = 1
  private pending = new Map<number, Pending>()

  constructor(
    private readonly paths: KitPaths,
    private readonly env: NodeJS.ProcessEnv = process.env
  ) {
    super()
  }

  get running(): boolean {
    return this.child !== null
  }

  start(): void {
    if (this.child) return
    const { root } = this.paths
    const child = spawn(this.paths.uv, ['run', '--quiet', '--script', this.paths.bridge], {
      cwd: root,
      env: {
        ...this.env,
        // uv keeps its Python and downloads inside the kit folder, like wopkit.py's UV_ENV
        UV_CACHE_DIR: join(root, 'cache', 'uv'),
        UV_PYTHON_INSTALL_DIR: join(root, 'python'),
        UV_PYTHON_PREFERENCE: 'only-managed',
        PYTHONIOENCODING: 'utf-8',
        PYTHONUNBUFFERED: '1'
      },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true
    })
    this.child = child
    createInterface({ input: child.stdout! }).on('line', (line) => this.receive(line))
    createInterface({ input: child.stderr! }).on('line', (line) => console.error(`[kit] ${line}`))
    child.on('error', (error) => {
      if (this.child === child) this.detach(`The kit couldn't start: ${error.message}`, null)
    })
    child.on('exit', (code) => {
      if (this.child === child) this.detach('The kit stopped unexpectedly.', code)
    })
  }

  /** Stop on purpose: no 'exit' event, and start() can be called right away. */
  stop(): void {
    const child = this.child
    if (!child) return
    this.detach('The kit was restarted.')
    child.stdin?.end()
    child.kill()
  }

  request<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    if (!this.child?.stdin) return Promise.reject(new BridgeError('The kit isn\'t running.'))
    const id = this.nextId++
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject })
      this.child!.stdin!.write(JSON.stringify({ id, method, params }) + '\n')
    })
  }

  private receive(line: string): void {
    let message: { id?: number; result?: unknown; error?: { message: string }; event?: string; data?: unknown }
    try {
      message = JSON.parse(line)
    } catch {
      console.error(`[kit] ${line}`)
      return
    }
    if (message.event) {
      this.emit('event', message.event, message.data)
      return
    }
    const pending = message.id !== undefined ? this.pending.get(message.id) : undefined
    if (!pending) return
    this.pending.delete(message.id!)
    if (message.error) pending.reject(new BridgeError(message.error.message))
    else pending.resolve(message.result)
  }

  /** Forget the process; with an exit code (or null after a failed start) the models hear it stopped. */
  private detach(reason: string, code?: number | null): void {
    this.child = null
    for (const pending of this.pending.values()) pending.reject(new BridgeError(reason))
    this.pending.clear()
    if (code !== undefined) this.emit('exit', code)
  }
}
