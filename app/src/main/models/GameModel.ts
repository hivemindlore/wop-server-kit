import type { GameCatalog, GameChoice, GameState } from '@shared/api'
import type { Bridge } from '../bridge/BridgeClient'
import { StateModel, messageOf } from './StateModel'

interface ActionResult {
  result?: string
  problems?: string[]
}

/**
 * The game on the server (the Game tab): the modes, maps and bots to choose from, the maps that play one after
 * another, starting a whole new game, restarting the match, a message to everyone, and keeping the current game as
 * the one the server starts with. What's playing right now comes from the server model; onChanged asks it to look
 * again after a change.
 */
export class GameModel extends StateModel<GameState> {
  constructor(private readonly bridge: Bridge, private readonly onChanged: () => void = () => {}) {
    super({ catalog: null, rotation: null, busy: null, notice: null })
  }

  async loadCatalog(): Promise<void> {
    if (this.getState().catalog) return
    try {
      this.update({ catalog: await this.bridge.request<GameCatalog>('game.catalog') })
    } catch (error) {
      this.update({ notice: { kind: 'error', text: messageOf(error) } })
    }
    await this.loadRotation()
  }

  /** One question to the server, only when the Game tab needs it (not in the status poll). */
  async loadRotation(): Promise<void> {
    try {
      const { maps } = await this.bridge.request<{ maps: string[] }>('game.rotation')
      this.update({ rotation: maps.length ? maps : null })
    } catch {
      // keep what we had
    }
  }

  async apply(choice: GameChoice): Promise<void> {
    // The kit's names (snake_case); test_appbridge.py checks game.set accepts exactly these
    await this.act('applying', 'game.set', {
      gamemode: choice.gamemode,
      maps: choice.maps,
      weapons: choice.weapons,
      spawn_protection: choice.spawnProtection,
      red: choice.red,
      blue: choice.blue,
      bots: choice.bots,
      skill: choice.skill,
      pointlimit: choice.pointlimit,
      timelimit: choice.timelimit
    })
  }

  async restartMatch(): Promise<void> {
    await this.act('restarting', 'game.restart_match')
  }

  async sendMessage(text: string): Promise<void> {
    if (!text.trim()) return
    await this.act('sending', 'game.send_message', { text: text.trim() })
  }

  async saveAsStartup(): Promise<void> {
    await this.act('saving', 'game.save_as_startup')
  }

  private async act(busy: NonNullable<GameState['busy']>, method: string, params?: Record<string, unknown>) {
    if (this.getState().busy) return
    this.update({ busy, notice: null })
    try {
      const result = await this.bridge.request<ActionResult>(method, params)
      const problems = result.problems?.length ? ` (${result.problems.join(' ')})` : ''
      this.update({ notice: result.result ? { kind: 'info', text: result.result + problems } : null })
    } catch (error) {
      this.update({ notice: { kind: 'error', text: messageOf(error) } })
    }
    if (busy === 'applying') await this.loadRotation()
    this.update({ busy: null })
    this.onChanged()
  }
}
