import { createHash } from 'node:crypto'
import { createServer, type Server } from 'node:http'
import { mkdtemp, readFile } from 'node:fs/promises'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { downloadFile, fetchJson, sha256File } from './downloads'

const DATA = Buffer.alloc(300_000, 7)
let server: Server
let base = ''

beforeAll(async () => {
  server = createServer((req, res) => {
    if (req.url === '/release') {
      res.setHeader('Content-Type', 'application/json')
      res.end(JSON.stringify({ tag_name: 'app-v2.2.0', agent: req.headers['user-agent'] }))
    } else if (req.url === '/file') {
      res.setHeader('Content-Length', DATA.length)
      res.end(DATA)
    } else {
      res.statusCode = 404
      res.end()
    }
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
})

afterAll(() => {
  server.close()
})

describe('downloads', () => {
  it('reads JSON with a user agent (GitHub requires one)', async () => {
    expect(await fetchJson(`${base}/release`)).toEqual({ tag_name: 'app-v2.2.0', agent: 'wop-server-app' })
    await expect(fetchJson(`${base}/missing`)).rejects.toThrow('404')
  })

  it('downloads with progress and hashes the file', async () => {
    const file = join(await mkdtemp(join(tmpdir(), 'wop-dl-')), 'sub', 'setup.exe')
    const seen: number[] = []
    await downloadFile(`${base}/file`, file, (percent) => seen.push(percent))
    expect((await readFile(file)).equals(DATA)).toBe(true)
    expect(seen.at(-1)).toBe(100)
    expect(await sha256File(file)).toBe(createHash('sha256').update(DATA).digest('hex'))
    await expect(downloadFile(`${base}/missing`, file, () => {})).rejects.toThrow('404')
  })
})
