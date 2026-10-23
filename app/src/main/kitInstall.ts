import { access, cp, mkdir, readFile, rename, rm } from 'node:fs/promises'
import { join } from 'node:path'
import type { PlatformBehavior } from './platform/PlatformBehavior'

export interface KitPaths {
  root: string
  kit: string
  uv: string
  bridge: string
}

/** 1.10.0 > 1.9.2; missing parts count as 0. */
export function compareVersions(a: string, b: string): number {
  const pa = a.trim().split('.').map((p) => parseInt(p, 10) || 0)
  const pb = b.trim().split('.').map((p) => parseInt(p, 10) || 0)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (diff) return Math.sign(diff)
  }
  return 0
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

async function version(kitDir: string): Promise<string> {
  try {
    return (await readFile(join(kitDir, 'VERSION'), 'utf8')).trim()
  } catch {
    return '0'
  }
}

/**
 * Puts the kit that ships inside the app into the kit folder, unless the folder already has the same or a
 * newer kit (the kit updates itself from GitHub). Also puts uv there. This replaces the download part of
 * start-wop-server.bat / .sh; the rest of the setup is the kit's own (appbridge.py).
 */
export class KitInstaller {
  constructor(
    private readonly behavior: PlatformBehavior,
    private readonly resourcesDir: string,
    private readonly env: NodeJS.ProcessEnv = process.env
  ) {}

  paths(): KitPaths {
    const root = this.env.WOP_KIT_ROOT || this.behavior.defaultKitRoot()
    return {
      root,
      kit: join(root, 'kit'),
      uv: join(root, 'tools', this.behavior.uvFileName),
      bridge: join(root, 'kit', 'setup', 'appbridge.py')
    }
  }

  async ensure(): Promise<KitPaths> {
    const paths = this.paths()
    await mkdir(join(paths.root, 'tools'), { recursive: true })

    const bundled = join(this.resourcesDir, 'kit')
    if (compareVersions(await version(bundled), await version(paths.kit)) > 0) {
      const fresh = join(paths.root, 'kit.new')
      await rm(fresh, { recursive: true, force: true })
      await cp(bundled, fresh, { recursive: true })
      await rm(paths.kit, { recursive: true, force: true })
      await rename(fresh, paths.kit)
    }

    if (!(await exists(paths.uv))) {
      await cp(join(this.resourcesDir, 'uv', this.behavior.uvResourceDir, this.behavior.uvFileName), paths.uv)
      await this.behavior.makeExecutable(paths.uv)
    }
    return paths
  }
}
