import { mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { logWriter } from './logFile'

describe('logWriter', () => {
  it('appends timestamped lines, and starts over past the limit', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'wop-log-'))
    const file = join(dir, 'logs', 'kit.log')
    const log = logWriter(file)
    log('Traceback (most recent call last):')
    log('WopError: playit.gg refused')
    const text = await readFile(file, 'utf8')
    expect(text.split('\n').filter(Boolean)).toHaveLength(2)
    expect(text).toMatch(/^\d{4}-\d\d-\d\dT.*  Traceback/)
    await writeFile(file, 'x'.repeat(1_000_001))
    log('after')
    expect(await readFile(file, 'utf8')).toMatch(/after\n$/)
    expect((await readFile(`${file}.old`, 'utf8')).length).toBe(1_000_001)
  })

  it('never throws', () => {
    expect(() => logWriter(join('\u0000', 'nope', 'kit.log'))('line')).not.toThrow()
  })
})
