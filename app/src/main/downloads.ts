import { createHash } from 'node:crypto'
import { createReadStream, createWriteStream } from 'node:fs'
import { mkdir, rm } from 'node:fs/promises'
import { dirname } from 'node:path'
import { Readable, Transform } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const HEADERS = { 'User-Agent': 'wop-server-app' }

export async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { ...HEADERS, Accept: 'application/vnd.github+json' } })
  if (!response.ok) throw new Error(`${url} answered ${response.status}`)
  return (await response.json()) as T
}

/** Download to file; progress(percent) whenever the whole percent changes. */
export async function downloadFile(url: string, file: string, progress: (percent: number) => void): Promise<void> {
  await mkdir(dirname(file), { recursive: true })
  const response = await fetch(url, { headers: HEADERS })
  if (!response.ok || !response.body) throw new Error(`${url} answered ${response.status}`)
  const total = Number(response.headers.get('content-length')) || 0
  let done = 0
  let last = -1
  const count = new Transform({
    transform(chunk: Buffer, _encoding, callback) {
      done += chunk.length
      const percent = total ? Math.floor((done * 100) / total) : 0
      if (percent !== last) progress((last = percent))
      callback(null, chunk)
    }
  })
  try {
    await pipeline(Readable.fromWeb(response.body as import('node:stream/web').ReadableStream), count,
      createWriteStream(file))
  } catch (error) {
    await rm(file, { force: true })
    throw error
  }
}

export async function sha256File(file: string): Promise<string> {
  const hash = createHash('sha256')
  await pipeline(createReadStream(file), hash)
  return hash.digest('hex')
}
