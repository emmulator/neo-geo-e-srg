# The player as a 1950s hovercraft, its shots as laser bolts (design, 2026-10-28)

## Intent

The stopper-spider (10-26) is replaced by a small cherry-red hovercraft: a
1950s finned automobile crossed with a desert landspeeder. Its shot becomes
a short laser bolt, and it gets a hover sound and a bolt sound. Approved
over five mockup rounds (10-28):
https://claude.ai/artifact/KKgLAnfGNPKkvNLTABSPfM

## What the user decided

- A cross between a 1950s automobile with big tail fins ("wings") and a
  landspeeder, without visible thrusters. Cherry red (not seafoam).
- A cannon on top like the spider's stalk, but thinner, pointing straight up
  (round 2), half the round-3 height (round 4), with the cockpit and cannon
  moved forward (round 3).
- The shot: a short red / orange / yellow laser bolt, shorter than the
  incoming rockets; two-thirds of round 4's length (round 5); it starts above
  the cannon, never inside it (round 4).
- The craft lowers to the ground briefly before a jump, and the recoil
  pushes it down when it fires.
- Sounds: a new hover sound (round 3: an airy blower, "C1"), at about half
  the other effects' volume (round 4); a new bolt sound (Bolt B without its
  metallic ring, round 2); the spider's jump sound stays.

## Calls made by the orchestrator (check these)

- **Same frame layout as the spider**: REST, 4 hover bob (the spider's WALK
  slot), 4 jump (dip, launch nose-up, airborne, land), 4 recoil (the HEAVE
  slot: flash, pushed down, rising, rest). The runtime's frame choice (Task
  S2) and its timing are unchanged.
- **Scale 1.60** (the mockups were 1.85): the largest at which every pose
  of every latitude view fits the 32 x 32 sprite with a clear border; the
  mockups clipped the fins at the lower latitudes. The body sits 0.10 of
  its length forward of the anchor (the cannon), which centres the craft on
  the anchor on screen.
- **The dip and the recoil also push the picture down on screen** (2 px,
  then 1): low on the dome the surface normal points at the camera, and a
  3D drop alone barely moves the picture there.
- **At the lowest cell the craft's tail hangs 3 px below the dome box**; the
  console strip draws over the ship there, covering at most 2 px.
- **The cannon stands at the anchor**: every bullet's line starts at the
  ship's cell and runs straight out along the surface normal, so that is
  the only place the bolt can leave the barrel.
- **The bolt is drawn by its head** on the bullet's point, trailing back
  toward the craft, from 32 angle pictures (2 shimmer frames each) chosen
  by the bullet's ring and screen azimuth; it is drawn only once its tail
  is above the muzzle (about 5 frames after the shot; the muzzle flash
  covers them). The game's bullet (start, speed, life, hit test) is
  unchanged.
- **Bolts on the lowest rings run down the screen**: those cells' outward
  lines come toward the camera (as the old bullets did).

## Generators (the orchestrator's, staged with this design)

- `tools/render_hovercraft.py SHEET HEADER`: the ship sheet and
  `build/ship_map.h` with the spider's names (ship_tile, ship_anim_tile,
  ship_oy, SHIP_F_*), plus SHIP_BOLT_TILE, BOLT_ANGLES 32, BOLT_FRAMES 2,
  bolt_head[32][2], bolt_angle[rings][48], SHIP_MUZZLE_R, BOLT_LEN_R, and an
  interim SHIP_FIREBALL_TILE alias for Task H1. TILES = 48 x 13 x 4 + 64.
- `tools/synth_sfx.py`: move.wav is the hover (C1 at RMS 0.069), fire.wav
  the bolt; jump, hit and crack unchanged (all five byte-identical to the
  approved mockup files).
- `tests/hovercraft_render_checks.py`: the art checks, to become
  `tests/test_ship_render.py`.

## Non-goals

- No change to movement, jump length, firing rate, the bullet's flight or
  hit tests, scoring, or when a sound plays.

## For later consideration (not planned)

- The arachnophobia option recorded with the spider no longer applies.
