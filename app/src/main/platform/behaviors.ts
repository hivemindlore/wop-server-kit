import { spawn } from 'node:child_process'
import { chmod, copyFile, rename } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'
import type { PlatformBehavior, Runner, UpdateInstall } from './PlatformBehavior'

/** Detached programs resolve as soon as they started (0); the others when they end. */
export const runProgram: Runner = (command, args, { detached }) =>
  new Promise((resolve) => {
    const child = spawn(command, args, { detached, stdio: 'ignore' })
    child.once('error', () => resolve(null))
    if (detached) {
      child.once('spawn', () => {
        child.unref()
        resolve(0)
      })
    } else {
      child.once('exit', (code) => resolve(code))
    }
  })

const OPEN_IT_YOURSELF = 'The update is downloaded, but it couldn\'t be installed by itself. Open the downloaded file to install it.'

export class WindowsBehavior implements PlatformBehavior {
  readonly name = 'windows'
  readonly uvFileName = 'uv.exe'
  readonly uvResourceDir = 'win-x64'

  constructor(
    private readonly env: NodeJS.ProcessEnv = process.env,
    private readonly run: Runner = runProgram
  ) {}

  defaultKitRoot(): string {
    return join(this.env.LOCALAPPDATA ?? join(homedir(), 'AppData', 'Local'), 'WoPServer')
  }

  async makeExecutable(): Promise<void> {}

  updateAssetName(version: string): string {
    return `WoP-Server-Setup-${version}.exe`
  }

  async installUpdate(file: string): Promise<UpdateInstall> {
    // The one-click installer installs quietly for this user (/S) and opens the app again (--force-run)
    const started = await this.run(file, ['/S', '--force-run'], { detached: true })
    return started === 0 ? { kind: 'quit', relaunch: false } : { kind: 'manual', message: OPEN_IT_YOURSELF, reveal: true }
  }
}

export class MacBehavior implements PlatformBehavior {
  readonly name = 'mac'
  readonly uvFileName = 'uv'

  constructor(
    private readonly arch: string = process.arch,
    private readonly run: Runner = runProgram
  ) {}

  get uvResourceDir(): string {
    return this.arch === 'arm64' ? 'mac-arm64' : 'mac-x64'
  }

  defaultKitRoot(): string {
    return join(homedir(), 'Library', 'Application Support', 'WoPServer')
  }

  async makeExecutable(path: string): Promise<void> {
    await chmod(path, 0o755)
  }

  updateAssetName(version: string): string {
    return `WoP-Server-${version}-${this.arch === 'arm64' ? 'arm64' : 'x64'}.dmg`
  }

  async installUpdate(file: string): Promise<UpdateInstall> {
    // Without an Apple Developer ID the app can't replace itself; the host drags it over, as the first time
    const opened = await this.run('open', [file], { detached: false })
    if (opened !== 0) return { kind: 'manual', message: OPEN_IT_YOURSELF, reveal: true }
    return {
      kind: 'manual',
      message: 'Quit WoP Server, drag the new WoP Server into Applications (choose Replace), then open it again.',
      reveal: false
    }
  }
}

export class LinuxBehavior implements PlatformBehavior {
  readonly name = 'linux'
  readonly uvFileName = 'uv'

  constructor(
    private readonly env: NodeJS.ProcessEnv = process.env,
    private readonly arch: string = process.arch,
    private readonly run: Runner = runProgram
  ) {}

  get uvResourceDir(): string {
    return this.arch === 'arm64' ? 'linux-arm64' : 'linux-x64'
  }

  defaultKitRoot(): string {
    return join(this.env.XDG_DATA_HOME || join(homedir(), '.local', 'share'), 'WoPServer')
  }

  async makeExecutable(path: string): Promise<void> {
    await chmod(path, 0o755)
  }

  /** The AppImage replaces itself; the .deb goes through the package manager. Only x64 is built. */
  updateAssetName(version: string): string | null {
    if (this.arch !== 'x64') return null
    return this.env.APPIMAGE ? `WoP-Server-${version}-x86_64.AppImage` : `WoP-Server-${version}-amd64.deb`
  }

  async installUpdate(file: string): Promise<UpdateInstall> {
    const appImage = this.env.APPIMAGE
    if (appImage) {
      try {
        // Copied next to it first, so the running AppImage is swapped in one step
        await copyFile(file, `${appImage}.new`)
        await chmod(`${appImage}.new`, 0o755)
        await rename(`${appImage}.new`, appImage)
        return { kind: 'quit', relaunch: true }
      } catch {
        return { kind: 'manual', message: OPEN_IT_YOURSELF, reveal: true }
      }
    }
    // pkexec asks for the password in a window of the desktop's own
    const code = await this.run('pkexec', ['dpkg', '-i', file], { detached: false })
    return code === 0 ? { kind: 'quit', relaunch: true } : { kind: 'manual', message: OPEN_IT_YOURSELF, reveal: true }
  }
}

/** The behavior for this computer, chosen once at startup. */
export function detectBehavior(platform: NodeJS.Platform = process.platform): PlatformBehavior {
  switch (platform) {
    case 'win32':
      return new WindowsBehavior()
    case 'darwin':
      return new MacBehavior()
    case 'linux':
      return new LinuxBehavior()
    default:
      throw new Error(`WoP Server doesn't run on ${platform}.`)
  }
}
