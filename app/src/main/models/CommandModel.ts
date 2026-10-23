import type { CommandResult, CommandsState } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'
import { StateModel, messageOf } from './StateModel'

export const MAX_ENTRIES = 200

/** Commands typed for the server, with what it answered. The kit refuses the ones that would break things. */
export class CommandModel extends StateModel<CommandsState> {
  private nextId = 1

  constructor(private readonly bridge: Bridge) {
    super({ entries: [], busy: false })
  }

  async run(command: string): Promise<void> {
    command = command.trim().replace(/^[/\\]/, '')  // "/map x" in the game's console is "map x" here
    if (!command || this.getState().busy) return
    this.update({ busy: true })
    let entry
    try {
      const result = await this.bridge.request<CommandResult>('console.run', { command })
      entry = { id: this.nextId++, command, output: result.output, failed: false }
    } catch (error) {
      entry = { id: this.nextId++, command, output: messageOf(error), failed: true }
    }
    this.update({ entries: [...this.getState().entries, entry].slice(-MAX_ENTRIES), busy: false })
  }

  async clear(): Promise<void> {
    this.update({ entries: [] })
  }
}
