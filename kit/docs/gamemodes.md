# WoP server: game modes, maps and bots

> **The easy way:** just ask Claude, e.g. *"switch to Capture The Lolly with 4 bots on each team"*.
> This page is for people who like to do it by hand, and as a list of all names.

Ready-made command blocks to switch the running server to any game mode. Change the map or the bots
by swapping in names from the [bot list](#bot-names) and [map list](#map-names) at the bottom.

## How to switch by hand

1. Open `home\wop\mode.cfg` in the WoP Server folder (Windows: `%LOCALAPPDATA%\WoPServer`,
   Mac: `~/Library/Application Support/WoPServer`) with Notepad / TextEdit.
2. Paste one block below over everything under the `-----` line, swap map/bot names if you want, save.
3. In the server window type `exec mode.cfg`.

The new mode starts right away and **keeps replaying** (same map, same bots) until you switch again.
Restarting the server always goes back to the startup game (the first block below).

> Why not paste straight into the server window? It only keeps the first line of a multi-line paste,
> so the rest of the block gets lost. Going through `mode.cfg` always works.

### What the lines do
| Line | Meaning |
|------|---------|
| `kick allbots` | Removes the bots from the previous mode (bots otherwise stay through a map change) |
| `set bot_minplayers 0` | No random extra bots; only the ones listed in the block |
| `set g_gametype <n>` | The game mode |
| `set g_instaPad 0` | Weapons: `0` = regular weapons, `1` = InstaPad (one weapon, one hit kills) |
| `set pointlimit <n>` / `set timelimit <min>` | When a match ends (0 = no limit) |
| `map <mapname>` | Loads the map. Must come **after** the `set` lines and **before** the bots |
| `addbot <bot> <skill> <red/blue>` | Adds a bot. Skill 1 (easy) to 5 (hard). Solo modes leave out the team |
| `addbot <bot> <skill> <team> 0 "<name>"` | Same, with its own name. Needed when you add the same bot twice (e.g. `FatPad2`) |

Keep it to **16 players total** (humans + bots). Humans pick their team with `/team red`, `/team blue` or the Esc menu.
Lolly modes need a `…CTL` map and Big Balloon needs a `…BB` map (see [map names](#map-names)).

---

## Team Free For All (startup game)
- **Game mode:** Team Free For All (`g_gametype 6`)
- **Teams:** Red Pads: PADMAN, PadGirl, PadLilly, PaddyBell, Pelvis, PiratePad (6) · Blue Noses: FatPad, FatPad2, FATTY (3)
- **Weapons:** Regular
- **Map:** wop_padgarden

```
// Team Free For All | Red 6 vs Blue 3 | Regular weapons | wop_padgarden
kick allbots
set bot_minplayers 0
set g_gametype 6
set g_instaPad 0
set pointlimit 64
set timelimit 16
map wop_padgarden
addbot padman    3 red
addbot padgirl   3 red
addbot padlilly  3 red
addbot paddybell 3 red
addbot pelvis    3 red
addbot piratepad 3 red
addbot fatpad    3 blue
addbot fatpad    3 blue 0 "FatPad2"
addbot fatty     3 blue
```

## Free For All
- **Game mode:** Free For All (`g_gametype 0`): everyone against everyone
- **Bots:** PADMAN, PadGirl, PiratePad, PadKing, BeachPad (5)
- **Weapons:** Regular
- **Map:** wop_padship

```
// Free For All | 5 bots | Regular weapons | wop_padship
kick allbots
set bot_minplayers 0
set g_gametype 0
set g_instaPad 0
set pointlimit 32
set timelimit 16
map wop_padship
addbot padman    3
addbot padgirl   3
addbot piratepad 3
addbot padking   3
addbot beachpad  3
```

## Free For All, InstaPad
- **Game mode:** Free For All (`g_gametype 0`)
- **Bots:** MonsterPad, PadLilly, PadPunk, StonePad, PaddyBell (5)
- **Weapons:** InstaPad
- **Map:** wop_padkitchen

```
// Free For All | 5 bots | InstaPad | wop_padkitchen
kick allbots
set bot_minplayers 0
set g_gametype 0
set g_instaPad 1
set pointlimit 32
set timelimit 16
map wop_padkitchen
addbot monsterpad 3
addbot padlilly   3
addbot padpunk    3
addbot stonepad   3
addbot paddybell  3
```

## Tournament (1 vs 1)
- **Game mode:** Tournament (`g_gametype 1`): two play, everyone else waits in line and plays the winner
- **Bots:** PadKing (1)
- **Weapons:** Regular
- **Map:** wop_padattic

```
// Tournament 1v1 | 1 bot | Regular weapons | wop_padattic
kick allbots
set bot_minplayers 0
set g_gametype 1
set g_instaPad 0
set pointlimit 10
set timelimit 10
map wop_padattic
addbot padking 3
```

## Spray Your Color
- **Game mode:** Spray Your Color (`g_gametype 3`): collect cartridges, spray them on your color's wall
- **Bots:** PadGirl, PadLilly, PaddyBell, Pelvis, PadCho (5)
- **Weapons:** Regular
- **Map:** wop_padlibrary

```
// Spray Your Color | 5 bots | Regular weapons | wop_padlibrary
kick allbots
set bot_minplayers 0
set g_gametype 3
set g_instaPad 0
set pointlimit 256
set timelimit 16
map wop_padlibrary
addbot padgirl   3
addbot padlilly  3
addbot paddybell 3
addbot pelvis    3
addbot padcho    3
```

## Last Pad Standing
- **Game mode:** Last Pad Standing (`g_gametype 4`): everyone has a set number of lives, last one alive wins
- **Bots:** PADMAN, PiratePad, MonsterPad, PadBabe, SuperPad (5)
- **Weapons:** Regular
- **Map:** wop_padatticLPS

```
// Last Pad Standing | 5 bots | Regular weapons | wop_padatticLPS
kick allbots
set bot_minplayers 0
set g_gametype 4
set g_instaPad 0
set g_LPS_startlives 10
set pointlimit 8
set timelimit 16
map wop_padatticLPS
addbot padman     3
addbot piratepad  3
addbot monsterpad 3
addbot padbabe    3
addbot superpad   3
```

## Catch the Killerduck
- **Game mode:** Catch the Killerduck (`g_gametype 5`): hold the Killerduck as long as you can
- **Bots:** Spooky, GhostPirate, HellPad, Padilla, BadPaddy (5)
- **Weapons:** Regular
- **Map:** wop_padgarden_night

```
// Catch the Killerduck | 5 bots | Regular weapons | wop_padgarden_night
kick allbots
set bot_minplayers 0
set g_gametype 5
set g_instaPad 0
set pointlimit 64
set timelimit 16
map wop_padgarden_night
addbot spooky      3
addbot ghostpirate 3
addbot hellpad     3
addbot padilla     3
addbot badpaddy    3
```

## Freeze Tag
- **Game mode:** Freeze Tag (`g_gametype 7`): hits freeze players, teammates thaw them, freeze the whole other team to win the round
- **Teams:** Red Pads: PADMAN, PadGirl, PadLilly, PiratePad (4) · Blue Noses: PadKing, MonsterPad, PaddyBell, Pelvis (4)
- **Weapons:** Regular
- **Map:** wop_padcrash

```
// Freeze Tag | Red 4 vs Blue 4 | Regular weapons | wop_padcrash
kick allbots
set bot_minplayers 0
set g_gametype 7
set g_instaPad 0
set pointlimit 8
set timelimit 16
map wop_padcrash
addbot padman     3 red
addbot padgirl    3 red
addbot padlilly   3 red
addbot piratepad  3 red
addbot padking    3 blue
addbot monsterpad 3 blue
addbot paddybell  3 blue
addbot pelvis     3 blue
```

## Capture The Lolly
- **Game mode:** Capture The Lolly (`g_gametype 8`): steal the other team's lolly and bring it home
- **Teams:** Red Pads: PADMAN, PadGirl, PiratePad, BeachPad (4) · Blue Noses: PadKing, PadLilly, MonsterPad, PadPunk (4)
- **Weapons:** Regular
- **Map:** wop_padbaseCTL (needs a `…CTL` map)

```
// Capture The Lolly | Red 4 vs Blue 4 | Regular weapons | wop_padbaseCTL
kick allbots
set bot_minplayers 0
set g_gametype 8
set g_instaPad 0
set pointlimit 8
set timelimit 16
map wop_padbaseCTL
addbot padman     3 red
addbot padgirl    3 red
addbot piratepad  3 red
addbot beachpad   3 red
addbot padking    3 blue
addbot padlilly   3 blue
addbot monsterpad 3 blue
addbot padpunk    3 blue
```

## One Lolly Capture
- **Game mode:** One Lolly Capture (`g_gametype 9`): one lolly in the middle, bring it to the other team's base
- **Teams:** Red Pads: PadSoldier, StonePad, PadRock, Pad-RA (4) · Blue Noses: PadKnight, MonsterHawk, PadCho, PadBabe (4)
- **Weapons:** Regular
- **Map:** wop_journeyCTL (needs a `…CTL` map)

```
// One Lolly Capture | Red 4 vs Blue 4 | Regular weapons | wop_journeyCTL
kick allbots
set bot_minplayers 0
set g_gametype 9
set g_instaPad 0
set pointlimit 12
set timelimit 16
map wop_journeyCTL
addbot padsoldier  3 red
addbot stonepad    3 red
addbot padrock     3 red
addbot pad-ra      3 red
addbot padknight   3 blue
addbot monsterhawk 3 blue
addbot padcho      3 blue
addbot padbabe     3 blue
```

## Spray Your Color Team
- **Game mode:** Spray Your Color Team (`g_gametype 10`): Spray Your Color, scored per team
- **Teams:** Red Pads: PadGirl, PadLilly, PaddyBell (3) · Blue Noses: Pelvis, PADMAN, PadKing (3)
- **Weapons:** Regular
- **Map:** wop_padshop

```
// Spray Your Color Team | Red 3 vs Blue 3 | Regular weapons | wop_padshop
kick allbots
set bot_minplayers 0
set g_gametype 10
set g_instaPad 0
set pointlimit 512
set timelimit 16
map wop_padshop
addbot padgirl   3 red
addbot padlilly  3 red
addbot paddybell 3 red
addbot pelvis    3 blue
addbot padman    3 blue
addbot padking   3 blue
```

## Big Balloon
- **Game mode:** Big Balloon (`g_gametype 11`): capture and hold the balloon points
- **Teams:** Red Pads: PADMAN, PiratePad, PadGirl (3) · Blue Noses: FatPad, FATTY, PadKing (3)
- **Weapons:** Regular
- **Map:** wop_padgardenBB (needs a `…BB` map)

```
// Big Balloon | Red 3 vs Blue 3 | Regular weapons | wop_padgardenBB
kick allbots
set bot_minplayers 0
set g_gametype 11
set g_instaPad 0
set pointlimit 256
set timelimit 16
map wop_padgardenBB
addbot padman    3 red
addbot piratepad 3 red
addbot padgirl   3 red
addbot fatpad    3 blue
addbot fatty     3 blue
addbot padking   3 blue
```

---

## Bot names
Use the name in the first column with `addbot` (upper/lower case doesn't matter). Bots with the same
AI personality play the same way; the rest is just their look. You can add a bot more than once if you give
the extra copies their own name: `addbot fatpad 3 blue 0 "FatPad2"`.

| Bot name | Looks like | AI personality |
|----------|-----------|----------------|
| `PADMAN` | Padman | Padman |
| `Pad-RA` | Padman variant | Padman |
| `PadRock` | Padman variant | Padman |
| `PadSoldier` | Padman variant | Padman |
| `StonePad` | Padman variant | Padman |
| `SuperPad` | Padman variant | Padman |
| `BioPad` | Padman variant | Padman |
| `HellPad` | Padman variant | Padman |
| `PadClassic` | Padman variant | Padman |
| `PiratePad` | PiratePad | Padman |
| `GhostPirate` | PiratePad variant | Padman |
| `Spooky` | PiratePad variant | Padman |
| `FatPad` | FatPad | Padman |
| `FATTY` | FatPad variant | Padman |
| `MonsterPad` | MonsterPad | Padman |
| `MonsterHawk` | MonsterPad variant | Padman |
| `PadKing` | PadKing | Padman |
| `PadKnight` | PadKing variant | Padman |
| `BeachPad` | BeachPad | Padman |
| `PadPunk` | PadPunk | Padman |
| `PadCho` | PadCho | Padman |
| `Pelvis` | Padman variant | **Pelvis** |
| `PadGirl` | PadGirl | **PadGirl** |
| `PadBabe` | PadGirl variant | **PadGirl** |
| `PadLilly` | PadLilly | **PadLilly** |
| `Padilla` | PadLilly variant | **PadLilly** |
| `PaddyBell` | PaddyBell | **Paddy** |
| `BadPaddy` | PaddyBell variant | **Paddy** |
| `PaddyBee` | PaddyBell variant | **Paddy** |

## Map names
All 46 maps in WoP 1.7.0.

**Regular maps** work in Free For All, Tournament, Spray Your Color, Last Pad Standing, Catch the Killerduck,
Team Free For All, Freeze Tag and Spray Your Color Team:

| | | |
|---|---|---|
| `wop_airplane` | `wop_anteroom` | `wop_backyard` |
| `wop_bath` | `wop_cabin` | `wop_diner` |
| `wop_huette` | `wop_jail` | `wop_padattic` |
| `wop_padcrash` | `wop_padcrash_dm17` | `wop_padgarden` |
| `wop_padgarden_night` | `wop_padkitchen` | `wop_padlibrary` |
| `wop_padship` | `wop_padshop` | `wop_trashmap` |

**Last Pad Standing versions** (made for Last Pad Standing, also playable in the other non-lolly modes):
`wop_padatticLPS`, `wop_padkitchenLPS`, `wop_padlibraryLPS`

**CTL maps**, the only ones that work for Capture The Lolly and One Lolly Capture:

| | |
|---|---|
| `wop_colorstageCTL` | `wop_fridgeCTL` |
| `wop_journeyCTL` | `wop_padasiaCTL` |
| `wop_padbaseCTL` | `wop_padboxCTL` |
| `wop_padcloisterCTL` | `wop_padcrashCTL` |
| `wop_trashmapCTL` | `wop_westernsetCTL` |

The official One Lolly Capture rotation only uses colorstage, fridge, journey, trashmap and westernset.

**Big Balloon maps**, the only ones that work for Big Balloon:

| | | |
|---|---|---|
| `wop_anteroomBB` | `wop_backyardBB` | `wop_bathBB` |
| `wop_cabinBB` | `wop_dinerBB` | `wop_huetteBB` |
| `wop_jailBB` | `wop_padatticBB` | `wop_padcrashBB` |
| `wop_padgardenBB` | `wop_padkitchenBB` | `wop_padlibraryBB` |
| `wop_padshipBB` | `wop_padshopBB` | `wop_trashmapBB` |
