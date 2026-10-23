import { join } from 'node:path'
import type { UpdateState } from '@shared/api'
import { compareVersions } from '../kitInstall'
import type { PlatformBehavior } from '../platform/PlatformBehavior'
import { StateModel } from './StateModel'

/** The parts of a GitHub release the update needs. */
export interface Release {
  tag_name: string
  html_url: string
  assets: { name: string; browser_download_url: string; digest?: string | null }[]
}

export interface UpdateDeps {
  /** This app's version (package.json). */
  current: string
  /** owner/name on GitHub (kit.json "repo"). */
  repo: string
  behavior: Pick<PlatformBehavior, 'updateAssetName' | 'installUpdate'>
  /** Where downloaded installers go. */
  folder: string
  fetchRelease(url: string): Promise<Release>
  download(url: string, file: string, progress: (percent: number) => void): Promise<void>
  sha256(file: string): Promise<string>
  /** Also looks for a newer server kit (AppModel); true if there is one. */
  checkKit(): Promise<boolean>
  /** Quit the app (and start it again) so the installed update runs. */
  quit(relaunch: boolean): void
  reveal(file: string): void
}

const NEWEST = 'You have the newest version.'
const OFFLINE = 'Couldn\'t check for updates. Is this computer online?'
const NOT_DOWNLOADED = 'The download didn\'t finish. Is this computer online? Try again.'

/** A problem already worded for the user. */
class UpdateFailed extends Error {}

/** "app-v2.1.0" -> "2.1.0"; null for releases that aren't the app's. */
export function appVersionOf(tag: string): string | null {
  const match = /^app-v(\d+\.\d+\.\d+)$/.exec(tag.trim())
  return match ? match[1] : null
}

/**
 * Updates of the app itself, from the newest published release on GitHub (drafts and pre-releases don't
 * count, so publishing a release is what offers it to everyone). The installer is checked against the
 * sha256 GitHub lists for it, then handed to the platform behavior.
 */
export class UpdateModel extends StateModel<UpdateState> {
  private release: Release | null = null

  constructor(private readonly deps: UpdateDeps) {
    super({ phase: 'idle', current: deps.current, version: '', percent: null, message: null })
  }

  /**
   * quiet: the check at start, which only speaks up when there's something new (the kit is checked at start
   * by AppModel itself). Otherwise the button: the app and the kit, with an answer either way.
   */
  async check(quiet = false): Promise<void> {
    const { phase } = this.getState()
    if (phase === 'checking' || phase === 'downloading' || phase === 'installing') return
    this.update({ phase: 'checking', message: null })
    const kit = quiet ? Promise.resolve(false) : this.deps.checkKit().catch(() => false)
    let release: Release
    try {
      release = await this.deps.fetchRelease(`https://api.github.com/repos/${this.deps.repo}/releases/latest`)
    } catch {
      await kit
      this.update({ phase: quiet ? 'idle' : 'error', version: '', message: quiet ? null : OFFLINE })
      return
    }
    const version = appVersionOf(release.tag_name ?? '')
    if (version && compareVersions(version, this.deps.current) > 0 && this.assetOf(release, version)) {
      this.release = release
      this.update({ phase: 'available', version, message: null })
      return
    }
    const kitNewer = await kit
    this.update({ phase: quiet || kitNewer ? 'idle' : 'upToDate', version: '', message: quiet || kitNewer ? null : NEWEST })
  }

  async install(): Promise<void> {
    const { phase, version } = this.getState()
    const asset = this.release && this.assetOf(this.release, version)
    if (phase !== 'available' && phase !== 'error') return
    if (!asset) return
    const file = join(this.deps.folder, asset.name)
    this.update({ phase: 'downloading', percent: 0, message: null })
    try {
      await this.deps.download(asset.browser_download_url, file, (percent) => this.update({ percent }))
      const want = (asset.digest ?? '').replace(/^sha256:/, '').toLowerCase()
      if (!want || (await this.deps.sha256(file)).toLowerCase() !== want) {
        throw new UpdateFailed('The download was damaged. Please try again.')
      }
      this.update({ phase: 'installing', percent: null })
      const result = await this.deps.behavior.installUpdate(file)
      if (result.kind === 'quit') {
        this.deps.quit(result.relaunch)
        return
      }
      if (result.reveal) this.deps.reveal(file)
      this.update({ phase: 'manual', message: result.message })
    } catch (error) {
      this.update({ phase: 'error', percent: null, message: error instanceof UpdateFailed ? error.message : NOT_DOWNLOADED })
    }
  }

  private assetOf(release: Release, version: string): Release['assets'][number] | undefined {
    const name = this.deps.behavior.updateAssetName(version)
    return name ? release.assets?.find((a) => a.name === name) : undefined
  }
}
