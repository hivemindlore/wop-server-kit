import { appendFileSync, mkdirSync, renameSync, statSync } from 'node:fs'
import { dirname } from 'node:path'

const LIMIT = 1_000_000   // bytes; then the file becomes <name>.old and a new one starts

/** Appends timestamped lines to a log file that never grows past about twice LIMIT. Never throws. */
export function logWriter(file: string): (line: string) => void {
  return (line) => {
    try {
      mkdirSync(dirname(file), { recursive: true })
      try {
        if (statSync(file).size > LIMIT) renameSync(file, `${file}.old`)
      } catch {
        // no file yet
      }
      appendFileSync(file, `${new Date().toISOString()}  ${line}\n`)
    } catch {
      // a log is never worth an error
    }
  }
}
