# E-SRG on the Neo Geo — conversion plan

Status: decisions made (section 5), 2026-10-11. Nothing is built yet.

Source game: `~/Development/gitlocal/vectrex-e-srg` (v1.0.0, tag `v1.0.0`).
Toolchain and hardware knowledge: the `neo-geo-dev` and
`neo-geo-gfx-pipeline` skills, plus what `neo-geo-one` already solved
(MAME software-list launch, BIOS repacking, headless Lua probes, frame
budget measurement).

## 1. What changes between the two machines

| | Vectrex | Neo Geo (AES/MVS) |
|---|---|---|
| CPU | 6809 @ 1.5 MHz, 30k cycles/frame | 68000 @ 12 MHz, ~203k cycles/frame (+ Z80 for sound) |
| Frame | 50 Hz, no fixed refresh | 59.2 Hz, fixed |
| Display | vector beam, portrait, monochrome + overlay | raster 320×224, landscape, up to 3,840 colours on screen |
| Drawing | lines drawn at run time | **no run-time pixels at all**: everything is tiles from ROM (sprites from C ROM, fix layer from S ROM) placed, flipped, palette-swapped and shrunk by the LSPC |
| Sprites | — | 381 sprites (16 px wide columns, up to 32 tiles tall), 96 per scanline, shrink only (never enlarge) |
| Text | BIOS raster text, slow | fix layer: 40×32 grid of 8×8 tiles, free |
| RAM / ROM | 1 KB / 32 KB | 64 KB / megabytes (P ROM 1–2 MB, C ROM up to 64 MB) |
| Sound | AY-3-8910 written directly | YM2610 (FM, **SSG = AY-compatible**, ADPCM-A/B) driven by a Z80 program |
| Input | analog stick, 4 buttons | 8-way digital stick, A B C D, Start, Select |
| Persistence | BIOS high-score slot | backup RAM (MVS), memory card (AES) |

The consequence that shapes everything: **the Vectrex game draws every
line every frame from geometry; the Neo Geo can only show pictures that
were drawn in advance.** The conversion is therefore mostly an *asset
pipeline* problem — render every view of every object ahead of time from
the same geometry — plus a port of the game logic, which gets easier
(8× the CPU, real 32-bit maths, plenty of RAM and ROM).

What carries over almost unchanged:
- the geometry and all the generated tables (`tools/gen_dome.py`: cells,
  neighbours, views, missile flights, occlusion, crack placement);
- the game rules (`src/e-srg.c`: moves/jumps, missiles, collisions,
  cracks spreading, collapse, scoring, levels, title pages);
- the sound designs (the YM2610's SSG is register-compatible with the AY).

What has to be rebuilt: every piece of drawing code (`dome_draw.s`,
`missile_draw.s`, `radar.s`, `cracks.s`, `hud.s`, `stars.s`), the
calibration machinery (meaningless on a raster screen — dropped), input
(analog → digital), the screen layout (portrait → landscape) and the
sound driver.

## 2. Converting each element

### 2.1 The dome — pre-rendered views

The Vectrex dome has 240 rotation steps but only **48 distinct views**
(5-fold symmetry), 25 stored plus mirrors. On the Neo Geo each view
becomes a picture made of sprite columns.

- Size: about 176×120 px (11 columns × 8 tiles) for a dome a bit over half
  the screen width with room above for incoming missiles. 48 views × 88
  tiles ≈ 4,200 tiles ≈ 540 KB of C ROM (before removing duplicate/empty
  tiles) — small by Neo Geo standards. No mirroring tricks needed.
- Display: 11 sprites; changing the view rewrites their SCB1 tile lists
  (88 words) — trivial per frame.
- Rendering: extend `gen_dome.py` (or a sibling `render.py`) to draw each
  view with PIL at 4× and downsample (anti-aliasing), quantise to a
  16-colour palette, then `tiletool.py` → C ROM, plus a C header of
  ready-made SCB1 tile lists per view (the NeoDev "`.map` sidecar" idea).

**[decide] D1 — the look.**
- **A. Vector look:** glowing lines on black, close to the Vectrex
  (anti-aliased, a bloom ramp in the palette). Fastest to make, faithful.
  But a wireframe can't hide missiles behind it (see 2.3) without the
  occlusion table, and it under-uses the machine.
- **B. Glass dome:** the same edges, plus each cell filled with a dark
  translucent-looking tint and a highlight shading by its angle to a light;
  rim glow. Occludes missiles naturally, reads well on a CRT, still clearly
  the same game.
- **C. Fully re-imagined art** (e.g. Blender-rendered frames, a planet
  backdrop). Most impressive, most work, art-skill dependent.
- **Recommended: B**, built so the renderer is one swappable step: A comes
  free as a debug style and C stays possible later with the same layout,
  tables and code.

### 2.2 Cracks

Cracked cells are game state (any of 76 cells, any combination), so they
can't be baked into the 48 views.

- **Recommended: overlay sprites** — the Vectrex approach translated.
  `crack_pos` already gives each cell's screen centre per view and
  `crack_look` its foreshortening; pre-render the 4 crack shapes × 8
  flattenings (× mirror via h-flip) as 1–2 column sprites and place one per
  visible broken cell, shrunk with SCB2 for distance. Up to ~38 sprites,
  well inside 381; a scanline sees far fewer than 96.
- Alternative: darken broken cells by baking per-cell variants of every
  view — combinatorially impossible. Rejected.
- The collapse effect (Vectrex: deliberately wrong calibration) becomes:
  shake the dome's 11 columns independently, then let them fall and spin
  apart with per-column velocities and fade the palette — arguably better
  than the original.

### 2.3 Ship, missiles, bullets, explosions

- **Ship:** 48 latitude views (as on the Vectrex) pre-rendered as a
  1–2 column sprite; the jump arc is just a Y offset.
- **Missiles and bullets:** keep the fixed-point flight model, but project
  *every* object *every* frame (the 68000 can; the 6809 managed one per
  frame). Pictures: the Vectrex already stores darts per ring × 7.5° of
  azimuth; pre-render those, and handle perspective size with **2–3 size
  levels plus hardware shrink** within each level (shrink-only hardware
  means render at the largest size; heavy shrink looks poor, hence levels).
  Use per-column X positions, never sticky chains, for anything that
  shrinks (the 16 px sticky offset trap from `neo-geo-one`).
- **Hidden behind the dome:** with the glass look (D1 B), use **sprite
  priority**: sprites with lower numbers are drawn first, so a missile on
  the far side uses a slot below the dome's, a near one a slot above it.
  The existing `mis_occ` table decides which side. Partial occlusion at the
  dome's edge then comes for free.
- **Explosions:** the Vectrex's 2D fragment animation rendered to a short
  sprite animation (could use LSPC auto-animation, tiles 4/8-aligned).

### 2.4 Radar, HUD, stars, title screens

- **Radar:** ellipse and roof as one static sprite picture. Each missile's
  stick is a 1-tile-wide sprite whose **vertical shrink sets its height**;
  the blip/heading line a small sprite picked from ~16 pre-rendered angles.
  Lock-on blink = a palette change (free).
- **HUD:** integrity, lives, score on the fix layer (free text).
- **Stars:** a full-width background — either a scrolling sprite plane (21
  columns, scroll by moving the driver sprite; parallax layers possible)
  or the fix layer. Recommended: sprite plane, so stars sit behind the
  dome and can be richer (colours, twinkle via palette cycling).
- **Title pages, levels, high scores:** fix-layer text (no speed limits
  any more — the Vectrex's 6-line rule goes away). The dome turning behind
  the title is free.

### 2.5 Screen layout and timing

- Landscape 320×224 instead of a tall portrait screen: dome centred and
  low, radar bottom-left, HUD bottom-right/top, missiles arrive from above
  and the sides. The camera and fit in `gen_dome.py` get Neo Geo settings
  (pixel units, 224 px tall).
- 59.2 Hz instead of 50: frame-counted constants (move 16 frames, jump 24,
  flight speeds, timers) get rescaled ×1.18, kept in one table so the
  feel can be tuned. The catch-up mechanism becomes unnecessary (fixed
  60 Hz with ample CPU) but measuring the frame budget stays part of the
  test loop.

### 2.6 Input

- 8-way digital stick: the Vectrex picks the neighbour cell nearest the
  stick's direction among 32; with 8 directions the same `cell_toward`
  logic works (at the peak and on the rim some neighbours may need a
  diagonal). Worth a play-test.
- Buttons: A fire, B jump / change level on title, C next page, D unused
  (no calibration needed). Start begins a game; MVS coins and credits
  handled by the BIOS (ngdevkit examples 07 and 10).

### 2.7 Sound

The SSG half of the YM2610 is AY-3-8910-compatible, but sound runs on the
Z80, and the 68000 talks to it one command byte at a time.

- **A. ADPCM samples of the Vectrex effects:** record each effect from
  vecx (`tests/vxhost --wav` already does this), convert with
  `adpcmtool.py`, trigger by command. Exact sounds, least code.
- **B. SSG effect scripts in the Z80 driver:** port the AY register
  sequences as data. Small and authentic, but means extending nullsound.
- **C. Furnace (`furtool.py`) for music and SSG instruments**, as
  ngdevkit's nullsound supports.
- **Recommended: A for effects now, C later if we want music.**

### 2.8 High scores

Per-level high scores (EASY / NORMAL / HARD, as in 1.0.0), kept in
**backup RAM on MVS** (ngdevkit example 11) and on the **memory card on
AES** (example 18) — a real persistent table, initials entry optional.

## 3. Code structure

**[decide] D2 — how to share the geometry with the Vectrex repo.**
- **Copy** `gen_dome.py`'s geometry and table code into this repo and
  adapt it (Neo Geo camera, pixel units, 32-bit fixed point). Independent
  repos, simple builds. **Recommended.**
- Git submodule of the Vectrex repo and import from it: one source of
  truth, but every Vectrex tweak can break this build.

Language: **C only** (ngdevkit's modern gcc for the 68000, `-O2`). The
6809 assembly routines are re-expressed in C; the 68000 has the headroom.
Hot spots, if any, get measured first (the `neo-geo-one` bracket-and-
measure recipe) before any 68000 assembly.

Proposed layout (mirrors `neo-geo-one` where it works):

```
src/        game C: main loop, dome, ship, missiles, radar, hud, title, sound
tools/      geometry.py (tables), render.py (pictures), build helpers
assets/     generated sprite sheets (git-ignored) + hand-made art if any
scripts/    mame.sh, mame_softlist.py, mame_bios.py (copied from neo-geo-one)
tests/      host-side tests (pytest for the generators, C unit tests for
            the logic), headless MAME probes (snapshot, PC check, budget)
docs/       this plan, notes
```

Build: ngdevkit (`m68k-neogeo-elf-gcc`, `tiletool.py`, `paltool.py`,
`adpcmtool.py`), MAME via a generated software list (the only reliable way
to boot a homebrew cart in the MAME flatpak), gngeo as a quick second
emulator.

## 4. Milestones

Each ends with a headless MAME check (it boots, the 68k reaches cart
space, a snapshot shows what it should) and a look in the emulator.

| # | Milestone | Done when |
|---|---|---|
| M0 | Skeleton: ngdevkit build, MAME softlist launch, headless snapshot test, BIOS staging | an empty cart boots in MAME headless and the test passes |
| M1 | Dome pipeline: geometry port, 48 views rendered (style B), C ROM + SCB1 maps; dome turns with the stick | dome rotates smoothly at 60 Hz, all 48 views verified against the Vectrex geometry |
| M2 | Ship + moves + jumps on the dome (port of `cell_adj`/`cell_toward`, 8-way input) | same cell paths as the Vectrex for the same inputs |
| M3 | Missiles, bullets, explosions, occlusion by sprite priority | hits and misses match the Vectrex rules; no missile shows through the dome |
| M4 | Cracks, spreading, integrity, collapse effect, lives, score, levels (fix-layer HUD) | a full game can be played to GAME OVER |
| M5 | Radar and star field | radar matches the Vectrex's information; budget measured |
| M6 | Title pages, level select, persistent high scores (backup RAM / memory card), attract mode | MVS and AES both boot to title and keep scores |
| M7 | Sound effects (ADPCM from the Vectrex captures) | every effect plays at the right moment |
| M8 | Polish: art pass, tuning for 60 Hz feel, real-hardware test if available | release 1.0.0 |

M1 is the risky one (does a pre-rendered dome look and feel right?), so it
comes first and gets your review before the rest is built on it.

## 5. Decisions (2026-10-11)

- **D1 look: B, glass dome.** Later, the crack overlays may be replaced by
  more detailed "broken glass" art (same overlay mechanism: per visible
  broken cell, placed from `crack_pos`, so only the pictures change).
- **D2 geometry: copied** into this repo, to evolve independently.
- **D3 target: emulators** (MAME, gngeo) for now. An original **AES** is a
  possible later target, so: follow the documented real-hardware rules
  where they're cheap (VRAM access spacing, no `CLR` on LSPC registers,
  YM2610 delays via nullsound), keep high scores on the memory card path
  (the AES has no backup RAM), and avoid emulator-only behaviour.
- **D4 execution: Claude subagent-driven development** (implementer and
  reviewer per task; gates re-run by the orchestrating session).
- **D5 licence: GPL-3.0-or-later** (`LICENSE`).

## 6. Reference version (2026-10-17)

The rules follow **vectrex-e-srg 1.1.0**:
- **1.0.1:** the target rings open at 6 kills or at 6 dome hits that break a whole cell
  (issue #1, the stall).
- **1.0.2:** the dome stays gone under GAME OVER after a dome death (issue #2). This port
  already had it.
- **1.1.0:** EASY's missiles fly at 0.75x speed.

Before this, the port had its own 12-hits rule (M4 fixes). The Vectrex rule replaces it.
