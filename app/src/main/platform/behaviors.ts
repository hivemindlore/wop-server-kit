import { chmod } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'
import type { PlatformBehavior } from './PlatformBehavior'

export class WindowsBehavior implements PlatformBehavior {
  readonly name = 'windows'
  readonly uvFileName = 'uv.exe'
  readonly uvResourceDir = 'win-x64'

  constructor(private readonly env: NodeJS.ProcessEnv = process.env) {}

  defaultKitRoot(): string {
    return join(this.env.LOCALAPPDATA ?? join(homedir(), 'AppData', 'Local'), 'WoPServer')
  }

  async makeExecutable(): Promise<void> {}
}

export class MacBehavior implements PlatformBehavior {
  readonly name = 'mac'
  readonly uvFileName = 'uv'

  constructor(private readonly arch: string = process.arch) {}

  get uvResourceDir(): string {
    return this.arch === 'arm64' ? 'mac-arm64' : 'mac-x64'
  }

  defaultKitRoot(): string {
    return join(homedir(), 'Library', 'Application Support', 'WoPServer')
  }

  async makeExecutable(path: string): Promise<void> {
    await chmod(path, 0o755)
  }
}

export class LinuxBehavior implements PlatformBehavior {
  readonly name = 'linux'
  readonly uvFileName = 'uv'

  constructor(
    private readonly env: NodeJS.ProcessEnv = process.env,
    private readonly arch: string = process.arch
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
