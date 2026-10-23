import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { KitInstaller, compareVersions } from './kitInstall'
import { LinuxBehavior, MacBehavior, WindowsBehavior, detectBehavior } from './platform/behaviors'

async function setup(installedVersion: string | null) {
  const dir = await mkdtemp(join(tmpdir(), 'wop-app-'))
  const resources = join(dir, 'resources')
  const behavior = new WindowsBehavior({ LOCALAPPDATA: join(dir, 'local') })
  await mkdir(join(resources, 'kit', 'setup'), { recursive: true })
  await writeFile(join(resources, 'kit', 'VERSION'), '2.0.0\n')
  await writeFile(join(resources, 'kit', 'setup', 'appbridge.py'), '# bundled')
  await mkdir(join(resources, 'uv', 'win-x64'), { recursive: true })
  await writeFile(join(resources, 'uv', 'win-x64', 'uv.exe'), 'uv')
  const installer = new KitInstaller(behavior, resources, {})
  if (installedVersion) {
    await mkdir(join(installer.paths().kit, 'setup'), { recursive: true })
    await writeFile(join(installer.paths().kit, 'VERSION'), installedVersion)
    await writeFile(join(installer.paths().kit, 'setup', 'appbridge.py'), '# installed')
  }
  return installer
}

describe('compareVersions', () => {
  it('compares number by number', () => {
    expect(compareVersions('1.10.0', '1.9.2')).toBe(1)
    expect(compareVersions('2.0', '2.0.0')).toBe(0)
    expect(compareVersions('0', '2.0.0')).toBe(-1)
  })
})

describe('KitInstaller', () => {
  it('installs the bundled kit and uv on a fresh computer', async () => {
    const installer = await setup(null)
    const paths = await installer.ensure()
    expect(paths.root.endsWith(join('local', 'WoPServer'))).toBe(true)
    expect(await readFile(paths.bridge, 'utf8')).toBe('# bundled')
    expect(await readFile(paths.uv, 'utf8')).toBe('uv')
  })

  it('replaces an older kit', async () => {
    const installer = await setup('1.3.0')
    expect(await readFile((await installer.ensure()).bridge, 'utf8')).toBe('# bundled')
  })

  it('keeps a kit that already updated itself to something newer', async () => {
    const installer = await setup('2.1.0')
    expect(await readFile((await installer.ensure()).bridge, 'utf8')).toBe('# installed')
  })

  it('uses WOP_KIT_ROOT for test installs', () => {
    const installer = new KitInstaller(new WindowsBehavior({}), 'res', { WOP_KIT_ROOT: 'D:/test' })
    expect(installer.paths().root).toBe('D:/test')
  })
})

describe('platform behaviors', () => {
  it('picks one per OS', () => {
    expect(detectBehavior('win32').name).toBe('windows')
    expect(detectBehavior('darwin').name).toBe('mac')
    expect(detectBehavior('linux').name).toBe('linux')
    expect(() => detectBehavior('aix')).toThrow()
  })

  it('knows where each OS keeps the kit and which uv it needs', () => {
    expect(new LinuxBehavior({ XDG_DATA_HOME: '/data' }, 'x64').defaultKitRoot()).toBe(join('/data', 'WoPServer'))
    expect(new LinuxBehavior({}, 'arm64').uvResourceDir).toBe('linux-arm64')
    expect(new MacBehavior('arm64').uvResourceDir).toBe('mac-arm64')
    expect(new MacBehavior('arm64').defaultKitRoot()).toContain(join('Library', 'Application Support', 'WoPServer'))
    expect(new WindowsBehavior({ LOCALAPPDATA: 'C:/L' }).uvFileName).toBe('uv.exe')
  })

  it('picks the installer from the release that fits this computer', () => {
    expect(new WindowsBehavior({}).updateAssetName('2.1.0')).toBe('WoP-Server-Setup-2.1.0.exe')
    expect(new MacBehavior('arm64').updateAssetName('2.1.0')).toBe('WoP-Server-2.1.0-arm64.dmg')
    expect(new MacBehavior('x64').updateAssetName('2.1.0')).toBe('WoP-Server-2.1.0-x64.dmg')
    expect(new LinuxBehavior({ APPIMAGE: '/a/WoP.AppImage' }, 'x64').updateAssetName('2.1.0'))
      .toBe('WoP-Server-2.1.0-x86_64.AppImage')
    expect(new LinuxBehavior({}, 'x64').updateAssetName('2.1.0')).toBe('WoP-Server-2.1.0-amd64.deb')
    expect(new LinuxBehavior({}, 'arm64').updateAssetName('2.1.0')).toBeNull()
  })

  it('installs an update the way each OS can', async () => {
    const ran: [string, string[], boolean][] = []
    const runner = (code: number | null) => async (command: string, args: string[], o: { detached: boolean }) => {
      ran.push([command, args, o.detached])
      return code
    }
    expect(await new WindowsBehavior({}, runner(0)).installUpdate('C:/u/Setup.exe'))
      .toEqual({ kind: 'quit', relaunch: false })
    expect(ran.at(-1)).toEqual(['C:/u/Setup.exe', ['/S', '--force-run'], true])
    expect(await new WindowsBehavior({}, runner(null)).installUpdate('C:/u/Setup.exe')).toMatchObject({ kind: 'manual', reveal: true })
    expect(await new MacBehavior('arm64', runner(0)).installUpdate('/u/WoP.dmg'))
      .toMatchObject({ kind: 'manual', reveal: false, message: expect.stringContaining('Applications') })
    expect(ran.at(-1)).toEqual(['open', ['/u/WoP.dmg'], false])
    expect(await new LinuxBehavior({}, 'x64', runner(0)).installUpdate('/u/WoP.deb')).toEqual({ kind: 'quit', relaunch: true })
    expect(ran.at(-1)).toEqual(['pkexec', ['dpkg', '-i', '/u/WoP.deb'], false])
    expect(await new LinuxBehavior({}, 'x64', runner(126)).installUpdate('/u/WoP.deb')).toMatchObject({ kind: 'manual' })
  })

  it('swaps a running AppImage for the new one', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'wop-appimage-'))
    const appImage = join(dir, 'WoP-Server.AppImage')
    await writeFile(appImage, 'old')
    await writeFile(join(dir, 'new.AppImage'), 'new')
    const result = await new LinuxBehavior({ APPIMAGE: appImage }, 'x64').installUpdate(join(dir, 'new.AppImage'))
    expect(result).toEqual({ kind: 'quit', relaunch: true })
    expect(await readFile(appImage, 'utf8')).toBe('new')
  })
})
