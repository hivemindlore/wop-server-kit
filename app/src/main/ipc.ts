import { ipcMain, type WebContents } from 'electron'
import { IPC, type CommandModel, type ModelCommands, type ModelName, type ModelStates } from '@shared/api'
import type { AiModel } from './models/AiModel'
import type { AppModel } from './models/AppModel'
import type { CommandModel as CommandsModel } from './models/CommandModel'
import type { LogModel } from './models/LogModel'
import type { NetworkModel } from './models/NetworkModel'
import type { ServerModel } from './models/ServerModel'

export interface Models {
  app: AppModel
  server: ServerModel
  network: NetworkModel
  commands: CommandsModel
  ai: AiModel
  logs: LogModel
}

// The commands the renderer may call, per model. The type below makes sure every model offers what
// shared/api.ts promises, and nothing else can be called through IPC.
const ALLOWED: { [M in CommandModel]: (keyof ModelCommands[M])[] } = {
  app: ['startSetup', 'retry', 'updateKit', 'openUrl'],
  server: ['start', 'stop', 'refresh', 'setName', 'setJoinPassword', 'setWeapons', 'setSpawnProtection', 'play'],
  network: ['check', 'fix'],
  commands: ['run', 'clear'],
  ai: ['refresh', 'connect', 'disconnect', 'open', 'restart'],
  logs: ['history', 'openFolder']
}

export function registerIpc(models: Models, target: () => WebContents | null): void {
  const handlers: { [M in CommandModel]: ModelCommands[M] } = models
  const stateful: { [M in ModelName]: { getState(): ModelStates[M]; subscribe(l: (s: ModelStates[M]) => void): unknown } } =
    models

  ipcMain.handle(IPC.get, (_event, model: ModelName) => {
    if (!(model in stateful)) throw new Error(`Unknown model ${model}`)
    return stateful[model].getState()
  })

  ipcMain.handle(IPC.call, (_event, model: CommandModel, command: string, args: unknown[]) => {
    const allowed = ALLOWED[model] as string[] | undefined
    if (!allowed?.includes(command)) throw new Error(`Unknown command ${model}.${command}`)
    const handler = handlers[model] as unknown as Record<string, (...a: unknown[]) => unknown>
    return handler[command](...(Array.isArray(args) ? args : []))
  })

  for (const model of Object.keys(stateful) as ModelName[]) {
    stateful[model].subscribe((state) => target()?.send(IPC.state, model, state))
  }
  models.logs.subscribe((change) => target()?.send(IPC.logs, change))
}
