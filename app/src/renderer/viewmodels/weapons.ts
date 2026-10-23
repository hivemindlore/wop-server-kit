import type { GameSettings } from '@shared/api'

export interface WeaponsView {
  options: { id: 'regular' | 'instapad'; label: string; selected: boolean }[]
  note: string
  disabled: boolean
}

/** Only with InstaPad. */
export interface SpawnProtectionView {
  on: boolean
  label: string
  hint: string
  disabled: boolean
}

/** All weapons or InstaPad, and InstaPad's protection after respawning, as the Game tab shows them. */
export function describeWeapons(settings: GameSettings | null | undefined, busy: boolean): {
  weapons: WeaponsView | null
  spawnProtection: SpawnProtectionView | null
} {
  if (!settings) return { weapons: null, spawnProtection: null }
  const weapons: WeaponsView = {
    options: [
      { id: 'regular', label: 'All weapons', selected: !settings.instapad },
      { id: 'instapad', label: 'InstaPad (one hit wins)', selected: settings.instapad }
    ],
    note: settings.running ? 'Switching restarts the current match.' : 'Used when the server starts.',
    disabled: busy
  }
  if (!settings.instapad) return { weapons, spawnProtection: null }
  const seconds = settings.spawn_protection_seconds
  let hint = settings.spawn_protection
    ? `Players can't be hurt for ${seconds} seconds after they respawn.`
    : 'Players can be hit right after they respawn.'
  if (!settings.spawn_protection_changeable) {
    hint = settings.running
      ? 'Changes apply after the server restarts once.'
      : 'Not available with this version of World of PADMAN.'
  }
  return {
    weapons,
    spawnProtection: {
      on: settings.spawn_protection,
      label: 'Protection after respawning',
      hint,
      disabled: busy || (!settings.running && !settings.spawn_protection_changeable)
    }
  }
}
