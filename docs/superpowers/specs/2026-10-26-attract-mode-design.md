# Attract mode: the title over a self-playing game (design, 2026-10-26)

## Intent

Today the title is nine pages of pale-blue text on a black screen, with
the dome spinning alone on page 0. A cabinet left idle shows almost none of
what the game looks like now (the sky, the mountains and towns, the grass
ripple, the trees, the console, the radar, the new collapse). The attract
mode puts the title pages over the real game playing itself, so a passer-by
sees the game while reading the title, the rules and the credits.

## What the user decided

- **The pages stay the existing title pages** (page 0's logo, level, best
  score and prompt; high scores; controls; how to play; levels; collapse;
  radar/score; credits; built with), with today's timing (a page every
  295 frames, C turns the page, B changes the level).
- **Behind them, the game plays itself** at full brightness: the whole scene
  as in play (sky, mountains, band, grass, props, dome, console, radar,
  HUD). Not dimmed.
- **It may be completely scripted**, not a full game, and it **starts over
  each time the page cycle comes back to page 0**.
- **The dome never collapses in the demo**, but the demo shows the regular
  gameplay elements, **jumps included**.
- **The text is gold with a black outline**: the in-game HUD's amber
  gradient (`FIX_RGB_AMBER` 1..4) with a 1-px black outline all round
  (mockup D, `~/Downloads/attract-text.html`, `attract-gold.html`).
- **The E-SRG logo is gold too**, a gold gradient with the same black
  outline, for consistency (`attract-gold.html`).
- **PRESS START** (and its alternates "B TO CHANGE LEVEL", "INSERT COIN")
  moves up from row 27, which the console now covers, to **row 21**, just
  above the console (it sits over the dome's top half).
- **The demo plays its sound effects.**

## Goals

1. The title pages read clearly over the moving scene, on every page.
2. Within each ~53 s cycle (9 x 295 frames) the demo shows: the ship
   walking and climbing the dome (the scenery turning with it), missiles
   coming in, the radar locking on and blinking, the ship shooting missiles
   down (explosions, the score rising), a missile getting through and
   cracking a tile, and the ship jumping over a crack (at least twice).
3. The demo is identical on every cycle, and a test proves it: no collapse,
   no ship death, and each element above happens at a stated frame.
4. Leaving the attract mode (START, or a coin on MVS) begins a real game
   exactly as today: a fresh game with today's seeding, nothing carried
   over from the demo.

## Non-goals

- No change to the game's rules, timing, art or sound set.
- No new title pages and no new page text (only the colours, the outline
  and PRESS START's row).
- No dimming of the scene, no text bars.
- No recording tool for players; the script is authored once.

## Anti-goals (a failure even if it "works")

- The demo ever collapses the dome, kills the ship, or reaches GAME OVER.
- The demo's score or level ever touches the saved best scores (backup RAM)
  or the level the player chose.
- A START/coin press during the demo starts a game that differs in any way
  from one started from today's black title (seed, level, lives, score,
  broken cells, missiles).
- The title text tears or flickers over the scene (the vblank rule of
  Tasks 18/18b/19 holds: fix-layer and palette writes that the picture
  shows are done before the raster reaches them).
- A line goes over 96 sprites (the scene is the game's own scene, so the
  game's budget applies; the title adds only fix-layer tiles, which do not
  count).

## Constraints

- **Hardware:** the fix layer is 40 x 32 tiles of 8 x 8, 16 palettes of 16
  colours; the text font is 5 x 7 inside each 8 x 8 tile with a 1-px drop
  shadow (`tools/generate_srom.py` `FONT57`, `font57_to_pixels`). A full
  1-px outline makes a glyph 7 x 9: one row taller than its tile. Page lines
  are on even rows with a blank row between (`title.h`), so each line's
  bottom outline row can live in "cap" tiles drawn in the row below it.
  The logo is 16 x 4 contiguous tiles (`LOGO_*`): its outline must fit in
  its own tiles or extend the logo by one tile row/column.
- **The game's own state is the demo's state while it runs:** `rules`,
  `ship`, `mis`, the radar, the collapse, the props/scenery commits. The
  demo drives the same code the game uses, with input from a script and a
  fixed seed, so what is shown is the real game.
- **MVS:** the BIOS's demo-sound setting is honoured (see "Calls made").
  The MVS countdown (row 28, cols 19..20) keeps working on every page.
- **The boot-tests** that drive the title today (flow, flow-pages,
  flow-pages-c, flow-level, flow-return, flow-mvs*, best-*, sound*, sky)
  assume a black title with the dome on page 0 only; they will need their
  expectations moved to the attract scene, without weakening what they
  prove (page order, timing, B/C behaviour, best scores, MVS flow).

## The parts decided (as decided)

- Page text, order and timing: unchanged.
- Text style: amber gradient fill, 1-px black outline; logo gold gradient
  with black outline; no dimming.
- PRESS START row: 21.
- Demo: scripted, restarts at page 0, never collapses, shows jumps, plays
  sound.

## Calls made by the orchestrator (check these)

- **Script, not a recorded game:** the demo is a joystick/button script fed
  to the real `ship_frame` / `mis_update` / `rules_*` path with a fixed
  missile seed, instead of a pre-baked animation. It is deterministic, so a
  host model (the existing `tests/*_model.py`) can prove every goal without
  MAME, and MAME confirms it.
- **The ship never dies in the demo**, as well as the dome never
  collapsing (a death would pause the demo for 118 frames of nothing new).
- **What the HUD shows during the demo:** the demo's own score, integrity
  and lives, as in play. The level the demo plays is fixed (NORMAL), not
  the player's choice, and the title's level row still shows the player's
  choice.
- **Sound:** on AES always on; on MVS, a new game soft DIP in the cart
  header, "DEMO SOUND" ON/OFF (default ON), which the operator sets in the
  BIOS's game settings (the MVS BIOS has no global demo-sound switch; games
  declare their own).
- **When the demo restarts:** whenever page 0 begins: the cycle wrapping,
  and also a B press that jumps the title back to page 0. A C press turns
  the page and the demo plays on.
- **The fix layer is shared:** the in-play HUD (score, integrity, lives on
  the console) stays drawn during the demo; the title's rows and columns
  must not overwrite it, and the HUD must not overwrite the title (the plan
  states the rows/columns each one owns and a test checks no overlap).
- **Returning to the title** (after a GAME OVER, or a BIOS entry) starts
  the demo from its beginning on page 0, as the title does today.
- **Page 0's dome is the game's dome:** the separate title-spin of the dome
  goes away; the dome turns as the demo ship walks.
- **The old palette `FIX_RGB` (pale blue) is retired** for the title; the
  amber palette is used everywhere, plus a black outline index and the
  logo's gold indices.

## Left to the builder (the plan)

- The script's exact moves and the seed (found by search against the host
  models, so that every element of goal 2 happens and no death/collapse
  does), and the frame at which each element happens.
- How the cap tiles and the logo's outline are laid out in the S ROM.
- Where the attract state lives in `flow.c` (a demo flag on the title
  state, or a third flow state), and how a START during the demo resets
  the game state to a fresh game.
- How the existing title boot-tests are moved to the attract scene, one
  by one, keeping each one's claims.
- Task split and order (likely: font/outline and colours first, then the
  scene behind the title, then the demo script, then the tests' move).
