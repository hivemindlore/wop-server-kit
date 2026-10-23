import type { CommandsState, ServerState, WopApi } from '@shared/api'
import { ViewModel } from './ViewModel'

export interface QuickAction {
  id: string
  label: string
  description: string
  /** Asks for a bit of text first (e.g. the message to send); {text} in command is replaced by it. */
  input?: { placeholder: string }
  command: string
}

export const QUICK_ACTIONS: QuickAction[] = [
  {
    id: 'say',
    label: 'Send a message',
    description: 'Shows a message to everyone in the game.',
    input: { placeholder: 'Your message' },
    command: 'ssay {text}'  // WoP's own; the engine's say doesn't show in WoP
  },
  { id: 'restart', label: 'Restart the match', description: 'Scores back to 0, same map and bots.', command: 'map_restart 0' },
  { id: 'status', label: 'Who\'s playing?', description: 'Everyone on the server with their number and ping.', command: 'status' },
  { id: 'info', label: 'Server settings', description: 'Map, game mode, limits and more.', command: 'serverinfo' }
]

export const EXAMPLES: { command: string; meaning: string }[] = [
  { command: 'g_gravity 400', meaning: 'Moon jumps: half the normal gravity (800 is normal).' },
  { command: 'timelimit 10', meaning: 'Matches end after 10 minutes (0 = no time limit).' },
  { command: 'addbot padgirl 3', meaning: 'Adds the bot PadGirl at skill 3 (1 easy - 5 hard).' },
  { command: 'kick allbots', meaning: 'Removes every bot.' },
  { command: 'map wop_padkitchen', meaning: 'Switches to the kitchen map.' }
]

export interface CommandsView {
  entries: { id: number; command: string; output: string; failed: boolean }[]
  draft: string
  busy: boolean
  canRun: boolean
  serverOff: boolean
  quickActions: QuickAction[]
  openAction: { action: QuickAction; text: string } | null
  examples: typeof EXAMPLES
}

/** The Commands tab: type a server command, see its answer; quick actions for the common ones. */
export class CommandsViewModel extends ViewModel<CommandsView> {
  private commands: CommandsState | null = null
  private server: ServerState | null = null
  private draft = ''
  private history: string[] = []
  private historyIndex = -1
  private openAction: { action: QuickAction; text: string } | null = null

  constructor(api: WopApi) {
    super(api)
    this.mirror('commands', (state) => (this.commands = state))
    this.mirror('server', (state) => (this.server = state))
  }

  protected present(): CommandsView {
    const busy = this.commands?.busy ?? false
    const serverOff = this.server?.status?.running === false
    return {
      entries: this.commands?.entries ?? [],
      draft: this.draft,
      busy,
      canRun: !busy && !serverOff && this.draft.trim().length > 0,
      serverOff,
      quickActions: QUICK_ACTIONS,
      openAction: this.openAction,
      examples: EXAMPLES
    }
  }

  setDraft(text: string): void {
    this.draft = text
    this.historyIndex = -1
    this.changed()
  }

  submit(): void {
    if (!this.getSnapshot().canRun) return
    const command = this.draft.trim()
    this.history = [command, ...this.history.filter((c) => c !== command)].slice(0, 50)
    this.draft = ''
    this.historyIndex = -1
    this.changed()
    void this.api.call('commands', 'run', command)
  }

  /** Arrow up/down in the input walks through earlier commands. */
  browseHistory(direction: 'older' | 'newer'): void {
    const index = this.historyIndex + (direction === 'older' ? 1 : -1)
    if (index < -1 || index >= this.history.length) return
    this.historyIndex = index
    this.draft = index === -1 ? '' : this.history[index]
    this.changed()
  }

  useExample(command: string): void {
    this.setDraft(command)
  }

  quick(action: QuickAction): void {
    if (action.input) {
      this.openAction = { action, text: '' }
      this.changed()
      return
    }
    void this.api.call('commands', 'run', action.command)
  }

  setActionText(text: string): void {
    if (!this.openAction) return
    this.openAction = { ...this.openAction, text: text.slice(0, 150) }
    this.changed()
  }

  confirmAction(): void {
    const open = this.openAction
    if (!open || !open.text.trim()) return
    this.openAction = null
    this.changed()
    void this.api.call('commands', 'run', open.action.command.replace('{text}', open.text.trim()))
  }

  cancelAction(): void {
    this.openAction = null
    this.changed()
  }

  clear(): void {
    void this.api.call('commands', 'clear')
  }
}
