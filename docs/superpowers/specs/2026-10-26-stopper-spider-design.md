# The player as a stopper-spider, its shots as fireballs (design, 2026-10-26)

## Intent

The player's craft is today the Vectrex's orange pyramid, and its shots are
the missiles' dart turned around in a pale palette. The redesign gives the
player a character: a metallic-black, mechanical, creepy six-legged spider
whose body is shaped like an upside-down bottle stopper (the stopper is only
the shape's base, not the look), with a hollow stalk that heaves to spit
molten fireballs. Approved mockup: `~/Downloads/stopper-spider.html` (the orchestrator's
script becomes the generator `tools/render_spider.py`).

## What the user decided

- Metallic black, mechanical and creepy; not as tall as a real stopper.
- Six legs that walk across the dome; on a jump they scrunch, then
  elongate.
- The hollow stalk heaves when it shoots, almost as if throwing up.
- The shot is a molten fireball.
- Minimal sprite work: pre-drawn frames, no new hardware tricks.

## Goals

1. The spider replaces the pyramid everywhere the ship is drawn (play, the
   attract demo, respawn), at the same place and scale (a 32 x 32 sprite,
   2 x 2 tiles, on the dome's front meridian, one view per latitude).
2. It animates with the game's existing timing: a walk cycle while a move
   runs, the jump's four poses over a jump, the heave's four frames when a
   shot leaves.
3. The fireball replaces the bullet everywhere, shrinking with distance as
   the bullet does today.
4. Nothing about the game's rules, timing, hit-boxes or sounds changes.

## Non-goals and anti-goals

- No change to movement, jump length, firing rate, collisions.
- The sprite must not get bigger than 2 x 2 tiles or cost more sprites per
  line (the collapse census's 92 of 96 stays the worst).
- The animation must never show a pose that contradicts the motion (a
  walking pose mid-jump, legs scrunched while walking).

## Calls made by the orchestrator (check these)

- **The stalk leans 50 degrees up the dome** (toward the peak), like a
  mortar: the front of the dome faces the camera, and an upright stalk
  reads as a hole seen down its barrel.
- **Frames:** 4 walk + 4 jump + 4 heave + 1 rest = 13 pictures per
  latitude x 48 latitudes x 4 tiles = 2496 C ROM tiles (the 2 MB C ROM has
  room). The fireball: 4 churning 16 x 16 pictures, one tile each.
- **Timing:** walk frame = (move frames elapsed x 4 / SHIP_MOVE_FRAMES)
  (one full cycle per cell step: 19 frames); jump, over SHIP_JUMP_FRAMES
  (28): scrunch for frames 0..6, launch 7..10, airborne 11..20, land
  21..27, the existing lift unchanged; heave: 4 frames
  of 3 game frames each from the frame a shot leaves (SFX_FIRE), and a
  shot fired during a heave restarts it; rest otherwise.
- **Turning on the spot at the peak** (the ship's spin) plays the walk
  cycle in place, at the same rate. A shot can only leave at rest (the
  game's rule), so a heave never overlaps a walk or a jump.
- **The furnace glows dim at rest** and flares during the heave (palette
  indices of one bank, no palette animation).
- **The fireball's churn** follows the frame counter (each bullet offset by
  its slot), not the LSPC's auto-animation.
- **The ship's palette bank** (PAL_SHIP) is replaced by the spider's 16
  colours; the bullet's palette (PAL_BULLET) by the fireball's.

## Left to the builder (the plan)

- The C ROM layout and header (the orchestrator's generator writes it).
- The runtime's frame choice and the probes that prove it (per frame:
  the drawn picture equals the timing rule above from the ship's state).
- Moving the ship/bullet checkers' pixel models to the new art.

## For later consideration (not planned)

- **An arachnophobia option** (raised by the user 10-26, deferred): a legless
  variant of the same body (a skirt of short struts or a hover glow in place
  of the six legs: a bob instead of the walk, a squash for the jump, the
  same heave), the same 13 frames per latitude (~2500 more C ROM tiles).
  The switch: an MVS soft DIP beside DEMO SOUND; on AES, a player-set
  choice (e.g. a button combination on the title). Precedent: Grounded,
  Satisfactory and Hogwarts Legacy offer arachnophobia modes. Clinical
  arachnophobia is commonly estimated at about 3-6% of adults; this design
  is small and mechanical (no hair, eyes or fangs), but its six legs and
  scuttling walk are the usual triggers.
