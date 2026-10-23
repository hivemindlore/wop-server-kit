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

/**
 * All weapons or InstaPad, and InstaPad's protection after respawning, as the Game tab shows the choice it will
 * apply. settings tell what the server can do (its game code may not know the protection setting).
 */
export function describeWeapons(choice: { instapad: boolean; protection: boolean }, settings: GameSettings,
  busy: boolean): { weapons: WeaponsView; spawnProtection: SpawnProtectionView | null } {
  const weapons: WeaponsView = {
    options: [
      { id: 'regular', label: 'All weapons', selected: !choice.instapad },
      { id: 'instapad', label: 'InstaPad (one hit wins)', selected: choice.instapad }
    ],
    note: 'Takes effect when you press Apply changes.',
    disabled: busy
  }
  if (!choice.instapad) return { weapons, spawnProtection: null }
  const seconds = settings.spawn_protection_seconds || 3
  let hint = choice.protection
    ? `Players can't be hurt for ${seconds} seconds after they respawn.`
    : 'Players can be hit right after they respawn.'
  if (!settings.spawn_protection_changeable) {
    hint = settings.running
      ? 'Can be changed after the server restarts once.'
      : 'Not available with this version of World of PADMAN.'
  }
  return {
    weapons,
    spawnProtection: {
      on: choice.protection,
      label: 'Protection after respawning',
      hint,
      disabled: busy || !settings.spawn_protection_changeable
    }
  }
}
