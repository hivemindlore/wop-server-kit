// Puts what the app ships with into app/resources: a copy of the kit (../kit) and uv, the helper that
// provides Python for the kit, pinned to the same version and checksums as start-wop-server.bat / .sh.
//
//   node scripts/prepare-resources.mjs            this computer's OS only (for npm run dev)
//   node scripts/prepare-resources.mjs --all      every OS (the release build)
//   node scripts/prepare-resources.mjs mac-arm64  just these

import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, statSync, writeFileSync, chmodSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const UV_VERSION = '0.9.2'
const UV = {
  'win-x64': { asset: 'uv-x86_64-pc-windows-msvc.zip', sha256: 'ba61d01b7470b282e09e7c82a053472723c2a737fb3d137bd0f111e420cc1d9f', file: 'uv.exe' },
  'mac-arm64': { asset: 'uv-aarch64-apple-darwin.tar.gz', sha256: '90b1e69da3d04772565dd556ae8e72c86bdb7da85a8dfc2c6b50c400b0e6aa97', file: 'uv' },
  'mac-x64': { asset: 'uv-x86_64-apple-darwin.tar.gz', sha256: 'c887d2c4f629eee99b80a347880870f3bc77f7746db81923efe520f609f80857', file: 'uv' },
  'linux-x64': { asset: 'uv-x86_64-unknown-linux-gnu.tar.gz', sha256: 'b775bb84c72210c6c0b9670cfaad0ac2e3953f12a2947d52b57603b4fbae3798', file: 'uv' },
  'linux-arm64': { asset: 'uv-aarch64-unknown-linux-gnu.tar.gz', sha256: '0f0ecf2abcb50f8fb5d2b52c8095af4c133897086e3f2e0259f4fcb3d8ddf273', file: 'uv' }
}

const app = join(dirname(fileURLToPath(import.meta.url)), '..')
const resources = join(app, 'resources')

function thisComputer() {
  const os = { win32: 'win', darwin: 'mac', linux: 'linux' }[process.platform]
  return `${os}-${process.arch === 'arm64' ? 'arm64' : 'x64'}`
}

function copyKit() {
  const target = join(resources, 'kit')
  rmSync(target, { recursive: true, force: true })
  cpSync(join(app, '..', 'kit'), target, {
    recursive: true,
    filter: (src) => !/(__pycache__|\.pytest_cache|\.pyc$)/.test(src)
  })
  console.log(`kit -> ${target}`)
}

function find(dir, name) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      const found = find(path, name)
      if (found) return found
    } else if (entry === name) return path
  }
  return null
}

async function fetchUv(target) {
  const spec = UV[target]
  if (!spec) throw new Error(`Unknown target ${target}; use one of ${Object.keys(UV).join(', ')}`)
  const dest = join(resources, 'uv', target, spec.file)
  if (existsSync(dest)) return
  const url = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${spec.asset}`
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Download failed (${response.status}): ${url}`)
  const data = Buffer.from(await response.arrayBuffer())
  const sha = createHash('sha256').update(data).digest('hex')
  if (sha !== spec.sha256) throw new Error(`Checksum mismatch for ${spec.asset}`)
  const work = mkdtempSync(join(tmpdir(), 'wop-uv-'))
  const archive = join(work, spec.asset)
  writeFileSync(archive, data)
  // Windows' own tar reads .zip too; the GNU tar that Git puts first on PATH can't (and takes C: for a host)
  const tar = process.platform === 'win32' ? join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'tar.exe') : 'tar'
  execFileSync(tar, ['-xf', spec.asset], { cwd: work })
  mkdirSync(dirname(dest), { recursive: true })
  cpSync(find(work, spec.file), dest)
  if (spec.file === 'uv') chmodSync(dest, 0o755)
  rmSync(work, { recursive: true, force: true })
  console.log(`uv ${UV_VERSION} -> ${dest}`)
}

const args = process.argv.slice(2)
const targets = args.includes('--all') ? Object.keys(UV) : args.length ? args : [thisComputer()]
copyKit()
for (const target of targets) await fetchUv(target)
