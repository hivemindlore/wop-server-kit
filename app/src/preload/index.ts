import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import { IPC, type LogChange, type ModelName, type WopApi } from '@shared/api'

// The renderer gets exactly this object as window.wop, nothing else from Electron or Node.
const api: WopApi = {
  get: (model) => ipcRenderer.invoke(IPC.get, model),

  onState: (model, listener) => {
    const handler = (_event: IpcRendererEvent, name: ModelName, state: Parameters<typeof listener>[0]) => {
      if (name === model) listener(state)
    }
    ipcRenderer.on(IPC.state, handler)
    return () => ipcRenderer.removeListener(IPC.state, handler)
  },

  call: ((model: string, command: string, ...args: unknown[]) =>
    ipcRenderer.invoke(IPC.call, model, command, args)) as WopApi['call'],

  onLogs: (listener) => {
    const handler = (_event: IpcRendererEvent, change: LogChange) => listener(change)
    ipcRenderer.on(IPC.logs, handler)
    return () => ipcRenderer.removeListener(IPC.logs, handler)
  }
}

contextBridge.exposeInMainWorld('wop', api)
