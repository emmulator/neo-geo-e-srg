# The incoming missiles as rockets, and the spider's sounds (design, 2026-10-26)

## Intent

The stopper-spider (S1–S3) gave the player a new character, but it still
sounds like the Vectrex's ship, and the incoming missiles are still the
Vectrex's red tetrahedral darts. This pass gives them a matching look and
sound: classic cartoon rockets, and sounds for a metal spider spitting lava.

Approved mockups (10-26): `~/Downloads/esrg-missiles-sounds.html` (both rounds).

## What the user decided

- **Missile:** a classic rocket shape, white with a black outline, with
  red highlights (the red nose and fins variant), and a flame out of the
  back.
- **Moving:** a metallic "scuttle" (mockup scuttle A: light, skittery
  leg-tip taps).
- **Jump:** a creaky, springy noise (jump A: the legs creak as they load,
  then a rising "boing").
- **Fire:** a lava-like fireball (lava B: a sticky "splort", then a thick
  low roar with bubbles). The first-round whoosh A was too high, B too
  ringing.
- **Explosions:** two sounds. A missile shot down (airburst B: a duller,
  longer bang, less debris) and a missile hitting the dome (dome-hit B: a
  thud, glass, then a deep, long rumble as the dome shudders).
- **The dome collapse** mixes both explosions: its rumble beats alternate
  between them.

## Calls made by the orchestrator (check these)

- **The scuttle plays on every cell step**, the first frame of every move
  of SHIP_MOVE_FRAMES (19), and while the ship spins on the spot at the
  peak once every SHIP_MOVE_FRAMES frames from the spin's first frame (the
  same steps the walk animation shows). Not on a jump (it has its own
  sound).
- **Channels:** the scuttle joins fire and jump on ADPCM-A channel 0 (a shot
  only leaves at rest; a jump that starts as a step ends cuts the scuttle's
  tail, which is right). The lock-on pip and its channel are unchanged.
- **The collapse's rumble beats** (collapse frames 0, 9, 18, 27, 36): 0 is
  the ship's death (the shot-down sound, as today), then dome-hit, shot-down,
  dome-hit, shot-down.
- **The flame flickers** through 4 pictures with the LSPC's 4-frame
  auto-animation: no CPU cost, every missile in step (one global counter).
  It costs 12,600 more C ROM tiles (missiles 4,200 → 16,800); the 2 MB C ROM
  had 16,000 free, so it still fits.
- **The rocket stands where the dart stood:** nose at the dart's tip, body
  the dart's length (gen_missiles.DART_LEN); the flame trails behind and is
  not part of the drawn length, so the flight code's placement and shrink
  are unchanged. When the tail faces the camera the flame is drawn in front
  (a tail-on rocket is a cross of red fins round a glowing exhaust).
- **The bullet's old palette** (bul_pal) stays in the header, unused since S3.

## Generators (the orchestrator's, committed with this design)

- `tools/synth_sfx.py OUTDIR`: move/jump/fire/hit/crack.wav at 18500 Hz,
  byte-identical to the approved mockup files (seeded noise, the mockups'
  order). The pip stays `tools/render_sfx.py`'s.
- `tools/render_rockets.py OUTDIR HEADER`: the rocket sheets and
  `build/missile_map.h` (adds `MIS_FRAMES 4`; tile = base + (((k * VIEWS +
  v) * cols + r) * cols + c) * 4, frame 0, every base a multiple of 4), the
  explosion unchanged (it imports render_missiles).
- `tests/rocket_render_checks.py`: the rocket art checks (box, nose, only
  the flame flickers, outline and red trim, the animation layout, C ROM
  placement), to become `tests/test_missile_render.py`.

## Non-goals

- No change to flight paths, speeds, hit tests, scoring, or when a sound
  plays except the new scuttle and the collapse's alternation.
- The explosion picture, the pip, the radar: unchanged.

## Left to the builder (the plan)

- Wiring: Makefile rules, the V ROM sample map, the Z80 command table,
  `sound.h`, `flow.c`'s game_sound, the missiles' SCB1 attribute and the
  LSPC animation speed.
- Moving the sound and missile checkers' models to the new samples and
  tiles, keeping every claim.
