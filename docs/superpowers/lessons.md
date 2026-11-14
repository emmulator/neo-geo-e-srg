# Lessons learned (hardware, toolchain, MAME)

One short entry per item: symptom, cause, how you confirmed it.

## MAME's AES and MVS backup-RAM block reads 0x00 at a fresh boot (2026-10-18)

Symptom: the plan's M6 Task 7 says "backup RAM starts as garbage on a new
MVS board" and asks the level-select code to treat any non-0/1/2 byte as
NORMAL — but a fresh boot (a new `-nvram_directory` on MVS, and AES's RAM)
reads the cart's `.bss.bram` block as **0x00**, which would be a valid
EASY, so the literal sanitize would boot the title on EASY and the first B
press would read EASY -> NORMAL, contradicting the task's own proofs
("B on 1000 -> HARD", "fresh boot shows NORMAL").

Cause: MAME initialises the backup RAM (and the saveram file) to zero; the
BIOS's ~280-frame RAM clear writes 0x55555555 then zeroes the work RAM,
which includes the bram block. There is no garbage byte to catch.

Confirmed: a probe reading 0x100000..0x100023 every frame on `aes -cart
esrg` and on `neogeo -bios euro -cart1 esrg` with a fresh nvram dir read
00 throughout (after frame ~280 on MVS), and the saveram file MAME wrote
was all zeroes at the cart's block.

Fix (Task 7): a second `_backup_ram` byte, the VALID marker, written
together with the level — fresh/garbage memory has marker 0 != the magic,
so it reads NORMAL; once the player (or a game begin) wrote the pair, it
stays valid across entries. The pre-Task-7 `flow_open_highscores` byte was
being cleared at every entry *anyway*; reading it first into a plain
static is the M6 fix.

## A `% LEVELS` on a u8 becomes a 32-bit __modsi3 in per-frame code

The per-frame rule ("no __divsi3/__modsi3/__mulsi3 in the frame loop")
catches even a small wrap: `next = (lvl + 1) % LEVELS` compiles to a
`jsr __modsi3` (the u8 promotes to int, and gcc does not strength-reduce a
modulo by 3). Confirmed with `m68k-neogeo-elf-objdump -r build/flow.o`
(one `__modsi3` relocation), fixed with a conditional
`if (next >= LEVELS) next = 0;` — then no libgcc math relocations at all.
Check `objdump -r x.o | grep __` after any change to per-frame code.

## A probe must not touch the LSPC registers: it moves the cart's VRAM pointer (2026-10-17)

Symptom: the flow boot-test's "row 9 blank on every AES title frame" check saw tile 0 at cols
17..21 of rows 0..3 and 5..9, cells the cart had cleared to spaces, and the zeroes were real
VRAM that stayed. M6 Task 3 first blamed MAME's FIXMAP read-back. The real cause: every probe
read VRAM by writing the address register (0x3c0000) and reading 0x3c0002 from its frame
callback. That callback can run between the cart setting its own VRAM address and writing
through it, so the cart's next writes went to the probe's address (and a read also
auto-increments the pointer by the cart's modulo).

Fix (all probes): read and write MAME's own copy of VRAM, which touches no 68k-visible state:

    local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
    vram:read(addr)          -- addr is the LSPC word address: 0x7000 + col*32 + row, 0x8200 + slot...

Confirmed: with the item reads, the title rows read clean in every order, and the AES flow leg
sees 50 dome views on the title instead of 32. All boot-tests pass unchanged.
## The Neo Geo vertical zoom table maps screen line to (SCB1 row, sub-row)

The LSPC's vertical shrink does not shorten a sprite: a sprite with `height`
tile rows still draws `height × 16` screen lines, and which SCB1 row of the
column each line samples comes from a fixed table, the "000-lo.lo" ROM inside
`aes.zip` (MAME maps it as `spritegen:zoomy`). For a vertical zoom byte `vz`
and sprite line `zl` (0..255 within the 16-line-deep repeat), the table gives
(tile row, sub-row); past the end of the table's slope it returns 0xff, which
MAME decodes as tile 15, sub-row 15 — i.e. the last full row repeats.

Confirmed by decoding `000-lo.lo` (131072 bytes, `zoomy[(vz << 8) | zl]`) and
comparing against MAME's `neosprite_base_device::draw_sprites`: the sampled
SCB1 row is bounded by 31 (5-bit after the `tile ^= 0x1f` inversion wrap), so
blanking SCB1 rows `picture_rows..31` of a slot's column makes every row the
hardware can reach below a shrunk picture blank, whatever an earlier, taller
picture left there. With the game's shrink range (vz 63..255, pictures 1/2/4
tiles) and the height set to `ceil(rows*(vz+1)/256)`, the hardware reaches at
most 7 rows below the picture; the exact number of screen lines each picture
occupies (for pixel-box tests) is the irregular `draw_h` table decoded from
the ROM, not a smooth formula.

The tile row per line does not follow a simple `floor(zl*16/(vz+1))` model;
the LO ROM uses its own rasterisation (sub-row steps of 2 at small zoom), so
read the ROM (or its decoded table) rather than re-deriving it.

## The zoom's point sampling can drop a thin line: shrink needs a floor

The Neo Geo's horizontal shrink draws `hz+1 = round(f/16)` columns of a
16-px tile and samples the tile at `round(c*16/(hz+1))` sub-columns. At a
4-column draw those are {0,4,8,12}: a 1-2 px crack line (the Vectrex's thin
cracks) falls between samples and the crack vanishes from the screen even
though its slot is drawn (VRAM correct, pixels missing). The vertical zoom
samples rows the same way.

Confirmed by simulating the sample grid: with a 5-px-wide art line every
draw of 4+ columns hits (only 3-column draws can miss), so the crack art was
re-rendered 4 px wide and the drawn f clamps to >= 64 (4 px line on the dome
rim). Symptom: MAME snapshot showed no crack pixels at a cell whose crack
slot the probe read as drawn; cause: sub-column 4..8 miss; confirmed by
editing `tools/render_cracks.py`'s stroke width and re-checking the snapshot.

## A 1-tile sprite still needs its column's rows below the picture blanked

Even at height 1, the LSPC draws 16 screen lines and the zoom table can
sample SCB1 rows 1..7 of the column below a small crack (row r is touched
by lines r*f/16 .. (r+1)*f/16; f = 31 reaches row 7). Rows 1..8 of the
column are blanked on every draw (row 0 holds the art); a taller picture
that previously used the slot would otherwise leave tiles there.

## Reading FIXMAP back: the LSPC entry is (palette << 12) | tile

To prove text on the fix layer a probe writes the LSPC address
(`sp:write_u16(0x3c0000, 0x7000 + col*32 + row)`) then reads the data
register (`0x3c0002`); the returned u16 is `(palette << 12) | tile`, and
the tile number is the ASCII code (the S ROM is ASCII at `tile = code`).
A naive `if (entry > 0xff)` mask test compares the whole entry (with the
palette bits, 0x7xxx) and decodes everything to `?`. Symptom: the HUD
boot-test printed rows of all `?` even though the fix layer was correct;
cause: masking with `& 0xfff` was needed; confirmed by reading back rows
with the full entry and comparing the low 12 bits to the expected ASCII.

## MAME's BIOS joypad RAM lags the frame notifier by the BIOS preamble

The AES BIOS spends ~470 MAME frames in preamble before the cart's code is
reached, and the cart's own frame counter (a BSS u32 the main loop
increments) stays 0 for the first ~477 records and then counts 1, 2, ...,
one per main-loop frame. A probe that labels input records with that
counter (instead of an ordinal) collapses the repeated `fc=0` records and
loses real input frames, so replaying a model against the counter keys
diverges from the game after a few hundred frames. Record the ordinal
alongside the cart frame and replay the model in record order from the
first record whose counter is 1. Confirmed by dumping `rec` vs `fc` over a
run (fc = rec - 477 after the flip) and by the model/cart integ diverging
at the collapsed records.

## The LSPC line counter wraps vpos 256..263 to -8..-1 (MAME 0.289)

`lspc_vpos() = ((*REG_LSPCMODE >> 7) & 0x1FF) - 0x100` reads the beam's
vpos, but only because MAME's `get_video_control()` (snk/neogeo_v.cpp)
stores `v_counter = vpos + 0x100` in the register's top 9 bits and wraps
vpos 256..263 down to `vpos - 264` (so lines 256..263 read as -8..-1, a
u16 0xFFF8..0xFFFF) after the 264-line frame. A stored value like 0xFFFE
is therefore a real "work ended at line 262" reading, not uninitialised
garbage: before the cart's first mark the whole BSS word is 0, and after
seeding it the value is never 0xFFFF except as the genuine line-263
reading. A frame's work span is `(end - start) mod 264`; the span, not the
raw end value, is the honest measure of a frame's cost, because
`ng_wait_vblank` can return anywhere in the vblank (measured: start vpos
243, and once 20 on the first frame after init). Confirmed by fetching
MAME 0.289's neogeo_v.cpp `get_video_control` and by correlating the BSS
marks with the model's game events (the worst span lands on heavy-play
frames, not on the random-looking negative readings).

## MAME snapshots land in `snap/<machine>/NNNN.png`, not next to the probe

A probe that snapshots twice (e.g. the ship-respawn boot-test) writes
`0000.png`, `0001.png`, ... under the `-snapshot_directory`'s `aes/`
subdirectory, and `boot_test.sh` copies only the first to `$OUT/snap.png`.
A checker that looks for "the sibling of snap.png" finds nothing (or the
bookmark left by a previous run) and silently compares the first snapshot
with itself — the pixel leg then passes on buggy code, because S1 is not
the after-death picture at all. Symptom: the boot-test reported
"ship pixels: 100 == 100" while a direct read of `snap/aes/0001.png`
showed 50 pixels (the right half of the ship missing). Cause: the checker
searched the wrong directory. Confirmed by re-running after walking
`<$OUT>/snap` for PNGs in snapshot order and comparing them to the probe's
S1/S2 frame records — the buggy code then failed exactly as it should.

## A rules change can move a boot-test's whole timeline: recalibrate the probe

The MAME boot-tests that script a full game to GAME OVER (collapse, hud,
framemark) hardcode the game's event frames in their probes and checkers:
the collapse probe samples the dome's SCB3 at fixed cart frames around the
first dome death and reads the fix rows near GAME OVER, and the framemark
checker reports the worst frame "during the collapse (fc X..Y)". When a
gameplay rule changes how fast the dome breaks — M4-fixes Task 2's rule
opens the missile targets at 12 hits on the dome, so a no-fire game now
reaches a dome death thousands of frames earlier (first dome death moved
from cart frame 7988 to 6919, GAME OVER from 17111 to 24177) — the probe's
fixed windows no longer bracket anything: the collapse leg read a rebuilt
dome that already existed and "GAME OVER" never appeared in its sampled
rows. Symptom: `make boot-test` FAIL collapse ("no moved SCB3 sample",
"no sample showed the dome hidden", "never showed GAME OVER") while every
host test passed. Cause: the probe/checker's frame constants came from the
old rule's model derivation. Confirmed by replaying the new rule's model
against the probe's recorded inputs (tests/check_collapse.py prints the
model's death/rebuild/GAME OVER frames) and by re-running the leg after
moving the probe windows to the new frames — then PASS. Fix: pick a
deterministic policy that gives clean events (a centred stick with A taps
gives three pure dome deaths, no cell deaths), derive its frames from the
model, and update the fixed windows in the probe and checker together.


## 5-fold symmetry lets cell pictures be stored once per 48 views — via a cell permutation, not shared art

The dome is a 5-fold-symmetric icosphere turning 240 steps, and the camera
is fixed. A naive reading says "the dome repeats every 48 steps, so one
view's art serves all five": wrong. Rotating the MESH by 72 degrees maps
each cell to a *different* cell, so the picture of "cell X at dome_angle s"
equals the picture of "cell r72(X) at dome_angle s+48": the 48 views repeat
with the CELLS RELABELLED. Verified numerically (2106 facing (cell, view)
pictures, all distinct; the identity picture(c, s) == picture(r72^q(c),
s mod 48) holds to 1e-4 for all 76 cells × 240 steps). So the art stores
the 48 views once per cell and the runtime applies a small permutation
table (broken_perm) per dome_angle: art_cell = r72^(dome_angle/48)(cell),
view = dome_angle % 48, instead of storing 240 pictures per cell (5x the
~0.64 MB the overlays use).

Also learned, same task: the overlay canvas x/y written in the tables are
dome-box-relative (DOME_X/DOME_Y = 72/88 on screen), and the y is signed
(rows above the dome's centre are negative), stored as a u8 — reading it
back requires a sign extension (s16)(s8), else a -1 becomes 255 and the
overlay sits 256 px lower. Two coordinate conventions fought here: the
geometry's fit() maps to the 176x128 dome box, and dome.h's DOME_X/DOME_Y
places that box on the 320x224 screen.

## A boot-test that snapshots a transient scene must key on the VRAM it reads, not a guessed frame

The broken-tiles boot-test needs one snapshot where a FRONT missile's
sprite box overlaps a broken overlay's box (the draw-order proof). The
first attempt picked a fixed cart frame ("the missile crosses the broken
top cells at fc 721..843, snapshot at 830") from the missile model. The
real cart never showed the missile there: its first missile landed at
cart fc 752 (breaking a whole cell and, through the rules' spread, slowly
changing the scene), while the model's predicted second missile never
launched on the cartridge at all — the seeds diverge because the fix-layer
HUD and the per-frame rules hook consume RNG draws and frame counts the
model does not. Symptom: probe.txt had `snap=1` but the snapshot frame's
front-missile slots were all empty; the checker failed "no front missile
over a broken cell". Cause: the snapshot condition was a time, not a
state. Confirmed by re-running with a probe that computed the overlap
from the very SCB3/SCB4 registers it was already dumping (each overlay
slot is a 16-px stone column; each front missile is 1..4 slot columns) and
snapshotted the FIRST sampled frame whose boxes overlapped — PASS. Fix:
probes that capture a transient event should derive the event from the
cart's own state (registers, VRAM, BSS exports) rather than from a model's
frame numbers.


## A game-ending dome death never reaches the dome's own "gone" state

The collapse state machine (rules.c) has no GAME OVER arm: `collapse_state`
returns 2 (running) only while `dead_t && dome_dead`, and 1 ("whole") as
soon as `!dead_t || !dome_dead`. A dome death that takes the last life sets
`game_over` (rules_begin, lives 0) and never respawns, so at GAME OVER the
rules are in a state the collapse drawing read as "whole": `dome_dead` still
set, `dead_t` 0, `collapse_frac` 0 — the whole branch of `dome_collapse`
re-chained and redrew the dome, and `cracks_show`'s `dome_dead && dead_t`
gate was off, so all 38 broken cells' overlays came back under GAME OVER.

Symptom (MAME, the -DGAMEOVER_DRAW_TEST boot-test): sampled frames through
the dome-death GAME OVER showed the dome's slot SCB3 chain (`cc08 0040…`)
and 27+ overlay columns, and the snapshot had ~13k lit pixels in the dome
box. Cause: the drawing read the rules' post-collapse "gone" frames (which
last only during the countdown, and hide the columns expecting a respawn)
as a normal whole frame. Confirmed by reading rules_begin (no respawn when
lives are 0) and by running the probe on the pre-fix cart vs the fixed one:
pre-fix the phase-1 GAME OVER resurrected the dome; the fix (a drawing-only
`dome_draw_gone` gate keyed on `game_over && dome_dead`, consulted by
`dome_collapse` and `cracks_show`) keeps the columns' SCB3 at 0 and the
overlays hidden, while a non-dome death's GAME OVER (dome_dead 0) still
draws the dome with its real broken tiles. The rules did not change.

## Test what the cartridge fetches, not only the art

The M4 broken-window task's first failure was invisible to every art-side
test: `render_bitmap()` drew the right pictures, the header's tables were
consistent, and a test that re-rendered the art couldn't see the
mismatch. What was wrong was the *ordering* — the runtime's fetch formula
(`tile + r*16 + c`, tiletool's row-major sheet) didn't match the sheet
the C ROM held, so 7,907 of 7,909 stones the cartridge fetched were the
wrong tiles. The test that caught it decodes the *built* `broken.c1`
/`broken.c2` at the exact tile number the runtime computes
(`tile + r*w + c`, the packed stream), and compares each fetched tile
with the stone `render_bitmap()` drew for that (cell, view, stone).

Confirmed by writing the ROM test first: on the pre-fix build it failed
with ~7,907 mismatches, and after the sheet was emitted in the fetch
order it reported 0. The MAME leg then builds the expected picture from
the *actual VRAM tile numbers* through MAME's own 15-bit→RGB pipeline,
and the snapshots at dome_angle 0 and 56 (the permutation) match it
pixel-exact in the dome box. Lesson: assert on the bytes the hardware
will read at the numbers the code computes — re-rendering the source art
proves only that the art is pretty, not that it reached the ROM in the
order the code fetches it.

A second trap surfaced in the expected-picture builder while doing this:
the broken palette's black hole is index 1, which is *black* — a paste
that treats "black pixel" as "transparent" (the dome's index-0 rule)
silently skipped every drawn hole. Transparent must be decided by the
tile's palette index (0), never by the resulting RGB colour.

## Overlays: build them from the picture they cover (2026-10-16)

The user saw the broken-window overlays spill onto neighbouring cells, and small
black triangles on the rim that flipped as the dome turned. Three causes:
- The overlay redrew the cell's outline 5 px wide (at 4x supersampling), and its
  jagged band ran past the outline.
- A black diagonal line in every cell, plus all-black fills on edge-on slivers,
  changed shape from view to view.
- The 5-fold relabel at dome_angle 48 swapped in another cell's randomly seeded
  fragments.

The fix:
- The overlay paints only the dome's own glass pixels of the cell, taken from the
  dome sheet itself.
- The shards are a function of the point on the 3D face, found by casting each
  pixel's ray onto the face plane.
- The fragments are seeded per symmetry orbit, in a pole-aligned frame.

Tests now check the overlay against the dome picture: it covers all of the cell's
glass and paints nothing on the outline or outside the cell. They also check the
look across the 48-step relabel.

## MAME runs missing when boot_test.sh fails: MAME must be on PATH for the whole command

boot_test.sh resolves `MAME` before the run; when I re-ran `scripts/boot_test.sh
stars` from a bare shell that lacked the flatpak path on PATH, `command -v mame`
failed and boot_test exited "no MAME". Cause: a command-level env difference, not
the probe. Confirmed by re-running with the flatpak path (then the run went
through). Fix: run boot-tests the way the Makefile does (`make boot-test`), which
inherits the session env, or set MAME= explicitly.

## A probe that holds input must start holding on the CART frame, not the record count

The AES BIOS preamble is ~477 MAME frames before the cart's main loop runs; a
probe that held "P1 Right" from record 60 (rec counts from PC >= 0x100000) held
it during the BIOS's own boot handling, and the ship never moved on the cart.
Symptom: RAM and stars stayed at dome_angle 0 for the whole run. Fix: gate the
hold on the cart's frame counter (fc >= 60), exactly like the other probes'
drive(). Confirmed by dumping the ship struct fields over frames after the fix:
angles walked 234 -> 74 as expected.

## A per-frame position model must record the state AFTER the frame, like the probe reads it

The cart's hud_framecnt increments in hud_frame, which runs after ship_frame,
so on the frame a probe reads fc the ship has already moved with that frame's
input. A checker comparing "the model's angle before input" (mangle[fc] set at
the top of the loop) reported a constant -1 px error against the cart. Fix:
record the state after the frame's logic, as the hud/collapse checkers do.
Confirmed by flipping to record-after: every sampled frame then matched
exactly.

## The stars cost 21 scanlines: a 32-bit divide in per-frame code

The star field (12 sprites, 2 VRAM words each) pushed the worst frame from 146 to 167 lines.
Cause: `stars_pos` computed the drift as `(u32)da * 320 / 240` and then `% 320`, for every star,
every frame. On the 68000 both are libgcc calls (`__udivsi3`, `__umodsi3`), hundreds of cycles
each. Fix: `(8*da + 3) / 6` in 16 bits (equal for da 0..239), and a conditional subtract for the
mod. Worst frame 149. Confirmed with `boot-test framemark` before and after. Check per-frame
code with `objdump -d` for calls to `__*divsi3`, `__*modsi3` and `__mulsi3`.

## m68k gcc codegen for 16-bit fixed point: operand SIGN decides muls.w vs __mulsi3 (M5 Task 3)

Writing `(s32)q * radar_sin[j]` where `q` is a **u16** makes gcc emit a `jsr __mulsi3`
(32x32), but the same expression with `q` declared **s16** emits the single `mulsw` the 68000
has (32-bit product). The radar's per-blip spot keeps both products and only the q->sin one
needs the signed multiply, so q is declared s16 (its values are ≤ 7680, far inside s16);
radar_rx/radar_ry/radar_hv are u16 and the unsigned r6 x factor products stay `muluw`.
Similarly, a `u16 / 48` (or `/ 512`, `/ 5`) division is **not** a `divu.w` at all: gcc
strength-reduces a division by a constant into the reciprocal magic `muluw.w` + shifts (the
bounded-divisor "never a divide" rule, but on the DIVISOR being constant, not just small).
Both were confirmed by compiling src/radar.c for the 68k and `objdump -r`-ing for `__mulsi3`
(one attempt with the u16 q failed; the s16 q build has no libgcc maths calls at all).

Also learned, same task: a 22-bit fixed-point dividend (a missile's r, up to 6<<19) can be
kept in 16-bit divides by splitting r = (r >> 7) * 128 + b: r/6144 = (r>>7)/48 + b/6144 and
the remainder term b/6144 < 1/48 only matters when the quotient's fraction is within 1/48 of
a half — a 1/512 error in R/6, under 0.06 px, inside the task's 1-px bound.

## A C ROM "next part" base must count TILE-SLOTS, not pictures (M5 Task 4)

The radar's C ROM parts are emitted back to back: frame (8 tiles), sticks (66
pictures × 3 tiles each = 198 tile-slots), headings (578 tiles). The
generated header's `RADAR_HEAD_TILE_BASE` was written as
`RADAR_STICK_TILE_BASE + RADAR_STICK_TILES` (66) instead of
`+ RADAR_STICK_TILES * RADAR_STICK_TILES... no — + 66 * 3` (each stick
picture is 3 tiles tall), so the runtime fetched the heading art 132 tiles
early. Every host test passed (they proved the pictures at each "part's"
numbers, using the same wrong base), and only the MAME boot-test caught it:
the checker computed the expected heading tile for a (dy=7, dx=0) heading
(19582) while the cart wrote 19450, both "in range" of the heading part.

Symptom: `check_radar` reported "heading: VRAM tile 19450, want 19582" on
every shown frame. Cause: the sticks' SCB1 rows are 3 tiles per picture, so
the part's real span in the C ROM is 66×3 = 198 tiles, not 66. Confirmed by
decoding the built `radar-stick.c1` payload (198 tiles) and by the boot-test
after fixing the base (PASS). Fix: the header now defines
`RADAR_STICK_TILE_SLOTS = RADAR_STICK_TILES * STICK_H_TILES` and the heading
base uses it. Lesson: when a part is N pictures of M tiles each, the next
part starts at `base + N*M`, and a test that re-derives a base from picture
counts carries the same bug — the boot-test's independent expected-value
computation is what catches it.

## The AES BIOS preamble's ~470 frames run BIOS demo content, not the cart's

`pc_in_cart` (the PC first crossing into cart space) goes high early — during
a brief cart-space entry in the BIOS login — long before the cart's `main`
has drawn anything, and the BIOS then runs its ~470-frame attract preamble
with its own demo sprites up and a dirty fix layer. So a probe that starts
sampling "frame 0" of the cart sees BIOS garbage (non-zero sprite slots,
non-ASCII fix tiles) as if it were the cart's first frames. With M6 the cart
boots to a title (hud_framecnt stays 0 on the title), and the first good
cart content is not distinguishable from the preamble by `framecnt` alone.

The same trap repeats on the *return* from a spent GAME OVER: the BIOS's
re-entry runs its own preamble before calling `main` again, and the cart's
`.bss` was already zeroed by `init_c_runtime`, so a checker gating "fc == 0
and title_page reads 1..8" accepts the BIOS-rebuild frames (title_page 0,
fix rows blank) as the returned title. Gate such finds on the *drawn* rows
(row 4 "E-SRG" for page 0, a drawn page-1..8 header on row 6), not on the
RAM page byte. Confirmed in the M6 Task 9 best-mvs run: the first fc==0
sample after the return read page 0 with blank rows; the real HIGH SCORES
title (page 1, rows drawn) was ~18 MAME frames later.

Symptom: `flow_probe` reported "19 game slots shown with SCB3 height != 0"
and fix rows of `?` at n=1..7..13 — frames during the BIOS preamble, before
`main`'s `fix_clear`/title draw had run (the `?` was tiles > 0xff). Cause:
sampling every "cart-frame 0" frame included the preamble. Confirmed by the
post-main samples (n≈476 onward, matching the preamble length) showing
nonzero=0 and the title's rows, plus the dome tile turning
(0x000c→0x0100→0x01b0). Fix: gate the probe's title samples on the cart's
title actually being drawn (`is_title()` checks the "E-SRG" row), i.e. only
sample once `main` has rendered, not on `pc_in_cart` or `framecnt == 0`
alone. Lesson: for any cart that shows a title/attract before a game, the
probe must key on the cart's rendered content, not on first entry into cart
space, or it will sample the AES BIOS preamble as if it were the cart.

## The MVS BIOS work RAM is garbage until its ~280-frame RAM clear

On `neogeo` (MVS), early frames read leftover memory: `bios_mvs_flag`
(0x10FD82) read 0x55 at frame 5 and settled to its true 0x80 only around
frame 278..280, and the cart's BSS `hud_framecnt` read 0x55555555 until the
same point. A probe/checker that asserts on these bytes from frame 1 (as the
AES flow probe can) FAILs on values that are not the machine's state at all.
Symptom: the first flow-mvs run's checker reported "game began at MAME frame
1" and "flag not 0x80" from the pre-clear garbage. Cause: unlike the AES
legs, whose probe records start once the PC is in cart space (after the
BIOS's own preamble), the MVS probe writes its M records from frame 1 so the
pre-coin timer 0x00 rows are part of the proof. Confirmed by dumping frames
1..300 (0x55/0x55555555, then the true values from ~280) and by the checker
passing once every MVS assertion starts at frame 280.

## A byte-wise "which rows changed" scan costs ~80 lines of 68k work

The naive "write only the differing rows" (compare each of the 28x40 held
rows with the new rows, per frame) costs ~80-160 scanlines: 1120 byte
compares at ~40-50 cycles each (~55k cycles ~ 70 lines) before any VRAM
write. On the title that pushed the phase-flip frames to ~200 lines.
Bracket-and-measure (the `#ifdef FRAME_MARK` marks) pinned it: `title_rows`
was ~30 lines, the compare loop ~80-160. Fix: decide the changed rows from
the visible *inputs* (page/level/credits change -> every text row; `t & 64`
flips -> page 0's row 8 only), never scan the previous rows. The task's
"keep the previous 28 rows" is about writing only the deltas to VRAM, not
about comparing them byte-wise.

## `-nothrottle` MAME reads of the cart's end-of-work mark race

Reading the framemark cart's `work_end_mark` BSS per MAME frame under
`-nothrottle` can catch the 68k mid-write: the probe saw `end=206` (span
~219) on frames whose cart-side persistent max never exceeded the vblank
tail — a read race, not real work. Even under `-throttle`, a frame whose
work genuinely spans most of the visible area shows `end` inside the
picture; the cart's own persistent max/min are raw-u16 compares and can't
see wrapped vpos values (206 < 65530), so they cannot disprove a late end.
For title-frame budget proofs, drive a dedicated throttled title-only run
(SG_ENABLE=0, -throttle) and read each M record once per frame; treat the
~64-frame-beat "spikes" under -nothrottle as noise and re-measure throttled
before optimizing.

## The page turn, not the phase flip, is the title's heaviest frame

With the input-tracked row writer, the phase-flip frames (1 row: page 0's
row 8) cost ~52 lines; the page turns (the page's whole text block: rows
4..22) cost ~133-141 lines. The title-only worst span 141 sits under the
game's 171. Writing only rows 4..22 (the range the nine pages can put text
on) instead of all 28 rows cut the turn from ~180 to ~141.

## Host-built structs must be packed to match the 68000's layout

Symptom: the M6 Task 8 plan says the `best_t` table is 18 bytes and "write
the host sim so it gives the same bytes" as the 68000, but the host gcc
builds the plain struct as 20 bytes (u32-aligned: `sum` at offset 16, 2
padding bytes) while the m68k-neogeo-elf gcc builds it as 18 (no tail
padding on the 68000). Confirmed by compiling a sizeof probe with both
gccs: plain 20 vs 18, packed 18 on both.

Cause: the 68000 allows unaligned words and gcc's m68k backend emits no
tail padding for a `u16` after three `u32`s, but x86-64's System V ABI
aligns the 2-byte and pads the struct to a 4-byte multiple.

Fix: declare the struct `__attribute__((packed))` in src/best.h — the
layout is then 18 bytes on both ends — and have the host sim serialize the
18 bytes explicitly (big-endian field-by-field, see tests/best_sim.c's
get_bytes) instead of reading raw host memory, which would be
little-endian. The `u8 *p = (const u8 *)b` byte-sum in src/best.c reads
memory order, so big-endian gives exactly the bytes the model checks.

## The AES memory card: MAME's -memcard option, and the BIOS card calls span several frames

Symptom: the M6 Task 10 plan says MAME takes `-memc <file>.neo`, but the
MAME 0.289 flatpak rejects `-memc` and `-memcard` as unknown global
options — the media slot is `memcard` (brief `memc`, per `mame aes
-listmedia`), and the working form is a positional image right after the
machine: `mame aes -memcard <path>.neo -cart esrg`. MAME creates a
missing 2048-byte card file (with a nonfatal "Unable to load image"
first-run line).

Second symptom: the probe read the cart's card-log once, one frame after
the GAME OVER that triggered the save, and saw only the first SAVE's
answer — the FORMAT and the second SAVE had not happened yet. The
ngdevkit `bios_card()` calls run synchronously in the cart's frame, but
each one takes several MAME frames (the BIOS card routine talks to the
card hardware across vblanks), so the whole save (SAVE 0x81, FORMAT,
SAVE) completes some frames later.

Confirmations: (1) with `-memcard`, the card file appeared and the
cart's LOAD answered 0x81 on a fresh card; (2) the probe sampling
card_log every frame from GAME OVER + 2 saw the log grow
`2:81` -> `2:81,3:81` -> `2:81,3:81,0:0,3:0` over several frames, with
the final state stable until the return's .bss/data reset.

Fix: probe the card log every frame during the GAME OVER window and take
the last complete record; and record the card calls' answers for the
checker instead of guessing a single-frame read.

## A generator's "on-screen margin" constant can feed a runtime table: moving DOME_Y changes bullet lives

Symptom: after the HUD-layout Task 1 lift (DOME_Y 88 -> 72), the seeded
gameplay tests (test_rules_play's rings_open / heavy_fire) failed even
though rules/missiles code had not changed: seed 2's game no longer
reached GAME OVER, and a heavy-fire seed's lock frames dropped.

Cause: tools/gen_missiles.py reads DOME_X/DOME_Y for its `on_screen`
margin test (a "margin test only" per the plan), but that test feeds
`r_offscreen`, which is the runtime `bul_life` table the cartridge
compiles: with the dome 16 px higher, bullets leave the top of the screen
sooner, so every seeded game's RNG-driven timeline shifts. The C and the
model both read the regenerated table, so frame-by-frame equality held —
only the seed-picked expectations moved.

Confirmation: recomputing bul_life with DOME_Y 88 vs 72 gives
[16,18,21,23,28,32,40,43,52,69,77,91] vs [14,15,18,19,24,27,33,35,42,55,
60,70]; the C's printed values and the model's matched at both settings.

Fix: re-pick the seeds under the new table (1019/1023 for heavy_fire, 34
for rings_open); the checkers still follow the header, and the plan's
mutation rule covers the header-following checkers.

## MAME snapshots lag the fix layer by ~3 ticks at a rules change (HUD-layout Task 2)

Symptom: the hud boot test's "after the first death, icons (18,18,0)"
check failed at the fc-486 snapshot: the probe read rules.lives == 2 (V
record) on the death frame, but the snapshot's pixels still showed all 3
ships — and an initial "snapshot next tick" fix still showed 3 ships;
only by ~+3..4 ticks did the displayed row 26 lose the third icon.

Cause: MAME's machine.video:snapshot() in the frame notifier captures the
frame buffer of the PREVIOUS completed composition. The cart writes
hud_frame's fix layer late in the frame after rules_end decremented lives;
the probe's snapshot in the next tick sees the frame whose fix writes
happened BEFORE the lives=2 state, so the picture lags the RAM by about
3 ticks. (The sampled fix rows — read from MAME's own videoram copy at
any tick — are NOT affected: they reflect the writes immediately.)

Confirmation: taking a burst of one snapshot per tick after the death
showed (18,18,18) at +0/+1/+2 and (18,18,0) from +3; the lag varied a
frame between runs under -nothrottle.

Fix: in hud_probe.lua, latch the death (rules+78 reads 2) and take the
snapshot on a later tick (death_pending = 8: the lives stay 2 for the
whole 118-frame death countdown, so the margin is safe). Record the V
with the lives RE-read at the snapshot's own fc. Also never let a
snapshot-index helper walk the copied snap.png (it sorts before the
MAME-managed aes/0000.png); index only the MAME snapshot directory.

## A `| head` pipeline can SIGPIPE a `sort` and kill the Makefile gate (set -o pipefail)

Symptom: `make boot-test` died with "sort: write failed: Broken pipe" /
exit 2 right after the hud run produced its 2 snapshots, so the later
modes never ran. The line picked SNAP_SRC with `find … | sort | head -1`.

Cause: with two PNGs present, sort buffers all of them, writes, and the
`head -1` has already closed the pipe; under `set -o pipefail` (boot_test.sh)
the sort's SIGPIPE propagates and the script exits 2.

Fix: read sort's whole output into an array (mapfile) and take element 0,
so nothing closes the pipe early. That also returns the FIRST snapshot
(0000.png) deterministically, which the checker needs.

## The centred score's column math must be done with the display length

Symptom: the score (row 28) was centred with (40 - len) / 2 over the FULL
40-col row; the plan's rule is col = (40 - len) / 2 rounded down, which the
title's "E-SRG" already used. A 10-col write band starting at col 15 (the
widest centred position) writes the same cells as (40-len)/2 for every
len, but a naive `line[i] = digits[i]` (left-aligned from col 0) drifts —
the mutation check proved the boot test catches it on row 28.

Cause: the model (tests/hud_model.py) centres by (40 - len) // 2; the C's
build_score_row must match exactly, and the write band must cover every
cell the digits can occupy (cols 15..25) so a length change both draws
the new digits and blanks the old cells.

Confirmation: mutation (a) (drop the /2 offset) failed the boot test at
every sampled frame's row 28; reverted.

## Per-frame HUD fill cost is visible in the frame mark: build only changed rows

Symptom: Task 2's first hud_frame built all 30 rows (1230 bytes) on every
change frame; the framemark worst span rose from Task 1's 171/160 to
186/167 even though the number of fix writes fell (70 -> 66 words).

Cause: the 30-row fill RAM write on each change frame dominates the
scanline budget more than the FIXMAP word writes. Filling 1230 bytes is
several times the old 410-byte rows' cost, and the frame mark measures
real work.

Fix: build only the changed row(s) per frame (per-row builders sharing
the same pieces as hud_rows: fill_blank + the row's cells). The result
BEAT Task 1's budget: 155 (centred) / 146 (broken) / 151 (title) vs the
task's 171/160/157, with no dropped frames.

Confirmation: rebuilding with per-row builders and re-measuring gave the
155/146/151 numbers; the hud boot test (which holds FIXMAP to the model)
stayed green, proving the per-row builders agree with hud_rows.

## MAME's -wavwrite audio lags the send by ~2.6 ms and the probe notices one frame later (M7 Task 1)

Symptom: check_sound.py's "not silent 0.1 s before / not loud after / wrong
length" failures at every send, with the audible lengths growing into the
next send. The probe's S record is written on the MAME frame AFTER the
cart's frame that sent the command (the frame notifier runs on the frame's
output), and the -wavwrite audio for that frame begins ~2.6 ms into the
next frame's audio stream. So a send the probe notices on frame m started
on frame m-1, and its WAV onset is at (m-1)/59.1856 + ~2.6 ms, not m/59.1856.

Cause: MAME's "-wavwrite writes the sound source" — with -sound none the
stream still has the emulated audio, and the sound stream is one frame
ahead/behind the notifier view. Confirmed by measuring the WAV: the first
sample of the fire send starts at WAV time 9.988 s = (592-1)/59.1856 +
0.0026 while the probe logged the send at MAME frame 592.

Fix: the checker computes each send's time as (mame_n - 1) / 59.1856 (the
frame the send actually happened; the extra ~2.6 ms onset is inside the
generous 0.1 s before/after windows and must NOT be added — adding it
shifted the "silent before" window into the previous sample's tail and
failed the pip), and the audible length stops at the first sustained
0.05 s gap instead of scanning to the WAV's end (the last send's ADPCM
tail runs to the end of the recording; an earlier sample's length measured
to the WAV's end would include the later sends).

## MAME's -wavwrite POV: ADPCM-A playback scales the samples to about half amplitude (M7 Task 1)

Symptom: the boot-test's "loud (peak > 3000)" standard passed for fire
(8556), hit (12031) and crack (12893), but jump (1957) and pip (3727)
measured far lower — and a frame-400 pip check against the full-scale
sample's peak failed even though the pip was playing at full volume on its
own channel.

Cause: MAME plays the ADPCM-A samples at roughly half the WAV's full
scale: the measured playback peaks are 0.44..0.54 of the resampled WAVs'
peaks (fire 8556 of 17059, jump 1957 of 4232, hit 12031 of 24796, crack
12893 of 29369, pip 3727 of 6909), consistently across all five samples.
The plan's "peaked at 10703..16606" measurements were for a different
scratch cart.

Fix: the checker uses a per-effect loud threshold at ~half the sample's
own peak (fire 4000, jump 1000, hit 6000, crack 6000, pip 2000), which
still proves the effect is playing loudly without tying the check to the
exact playback gain. Confirmed by correlating each WAV onset's peak with
the resampled WAV's peak — the ratio is the same for all five.

## The MVS BIOS RAM is garbage until ~frame 280: gate probe RAM reads on sanity (M7 Task 1)

Symptom: the sound-mvs leg's probe read the sound-test log address before
the MVS BIOS's RAM clear and logged 42 garbage records (sound_test_n
reading 0x55/0xAA = 85/170 as a byte count, title frames 21845/43690)
before the cart's own log appeared.

Cause: the MVS BIOS work RAM holds 0x55555555/0xAAAAAAAA until its ~280
frame RAM clear (already in lessons.md); the sound-test BSS variables read
that garbage until the cart's runtime zeroes them. Confirmed by the log:
only after the clear did the probe see the real records (sends noticed at
MAME frames 865+ for title frames 100+).

Fix: the probe waits for sane values — the log byte count <= 32 (the
log's capacity) and the title counter <= 1000 — before emitting any
records. The AES leg does not need this (its probe starts recording once
the PC is in cart space, after the BIOS preamble).

## Adding a new object with BSS moves the -DSOUND_TEST cart's RAM log (2026-10-26, Task C2)

- **Symptom:** after `src/collapse.c` joined `SRCS` (the wildcard links it
  into every cart), the sound-mvs leg failed with 168 garbage records
  (`S 2 21845 21845 85 85`) and "command 4 never logged" — while the same
  cart at HEAD passed. The AES sound leg still passed.
- **Cause:** the `-DSOUND_TEST` cart's `sound_test_log` / `sound_test_n` /
  `sound_test_fc` live in `flow.o`. `collapse.o`'s static memo (about 350
  bytes of BSS) is earlier in the link order, so its BSS shifted
  `flow.o`'s log to a different RAM address. The MVS BIOS leaves
  0x55/0xAA garbage there; at the new address that garbage eventually
  passed the sound probe's `cnt <= 32` + first-command gates (the
  `cnt == 0` branch starts it), so the probe logged garbage and never saw
  the real sends. HEAD's address was cleared/sane by the time the probe
  looked.
- **Fix:** the `-DSOUND_TEST` carts (sound, sound-mvs, sound-game,
  sound-radar) link a `collapse-soundtest.o` built with `-DSOUND_TEST`,
  whose `collapse_init`/`collapse_prepare`/`collapse_commit` are empty
  stubs. With no BSS, `flow.o`'s log keeps its HEAD address. The normal
  cart and every other test cart link the real `collapse.o`. The stub
  loses no coverage: the sound legs never play the collapse, and the
  collapse leg runs the normal cart.
- **Also:** `tools/render_collapse.py` imports `render_broken.py`, which
  reads `build/slots.json`; the collapse-map rule must depend on
  `$(SLOTS_JSON)` or a clean parallel `make` can schedule the collapse
  before the slot map and fail with "build/slots.json missing". The
  radar-map rule already had this dependency; the collapse rule now
  matches it.

## The BIOS logo moves every boot-time frame number (2026-10-19)
- **Symptom:** after setting `rom_eye_catcher_mode=2` (no "MAX 330 MEGA" logo), `flow-pages-c`, `flow-mvs`, `flow-mvs-start` and `flow-return` failed: C taps landed on page 2, the pre-coin window never saw page 0.
- **Cause:** with the logo off the BIOS calls the cart ~450 frames sooner. Measured from the probes' T records: the AES title starts at MAME frame ~24 (was ~477), the MVS title at ~299 (was ~749). Tests keyed on the cart's own frame counter were unaffected; only windows that had to land on the title's first page moved.
- **Also:** the eye-catcher mode is a linker `--defsym`; `make` does not relink on a Makefile change, so check the header byte at 0x114 after `make clean`.

## The BIOS enters the cart with the vblank flag already set (2026-10-20)
- **Symptom:** the title's first frame showed its text half drawn at the probe's frame-end sample (the logo rows, not the prompt on row 27).
- **Cause:** at a BIOS entry the first `ng_wait_vblank()` returns at once (the flag is stale), so the first frame's work starts mid-frame and runs past the next frame boundary. Confirmed: with two waits at the entry the text is whole at MAME frame 26 (title_t 0) and the first title frame is 27.
- **Also:** plain `make` does not rebuild the frame-mark carts (`make framemark-cart crackframemark-cart` or `make boot-test` does) — three "it didn't change" measurements were of a stale cart.

## A changed RNG seed moves every seed-keyed frame number, and some proof policies stop scoring (2026-10-20, RNG seed task)

Symptom: after seeding the missiles from the title's time, every boot leg
whose probe keys input on a fixed cart frame failed or silently stopped
finding its event: `check_flow`'s GAME OVER windows (the Up-held game
moved from fc 6509 to 17525 on AES at the default Start, 8188 at the flow
legs' Start 1200, and 16551 on MVS), the collapse's probe sampling window
(the first dome death moved 8202 -> 8359), the sound-game/hud budgets, and
the best-mvs/best-aes `score10 > 0` proofs, whose old "centred" policy
now scores 0 because no missile happens to cross a bullet under the new
seed.

Cause: the probes press Start at fixed MAME frames, but the seed is
`RNG_SEED ^ title frames at Start`, so every game's missile sequence — and
with it the first death, GAME OVER and score — depends on the Start
frame. A fixed window that used to bracket an event may now miss it by
thousands of frames; a policy that scored under 0xACE1 is not guaranteed
to score under another seed (the first centred game's 0 was luck).

Fix: the checkers key GAME OVER on the model replay of the recorded
inputs (the model now starts at the cart's `mis_seed_used`, read by the
probes), so only the probes' floors and the boot budgets are frame-keyed;
set those with margin from the model timeline. For the score proofs,
replace the luck-dependent centred policy with a deterministic scoring
one (Right held + A taps every 11 frames: the model gives 987 at MVS seed
0xadf9 and 699 at AES seed 0xaede). Confirmed by running each leg and
replaying the model: the probe's FIRST record (ring, phi) equals the
model's first spawn for the seed read from RAM.

## A header that includes a generated header must be generated in order (2026-10-22)

Symptom: making `src/slots.h` read `DOME_COLS` from `build/dome_map.h`
(`#include "dome_map.h"`) made `build/slots.json` wrong on a clean build if
the slot-map generator ran before the dome's: the include was not evaluated
and `DOME_COUNT` came out as a literal 11, which happened to agree today but
would not follow a smaller knob.

Cause: the slots rule's only prerequisite was `src/slots.h`, so the Makefile
was free to generate `slots.json` before `build/dome_map.h` existed; the C
compiler never saw this because every C rule waits for `$(GEN_HEADERS)`.

Fix: add `$(DOME_MAP)` as a prerequisite of `$(SLOTS_LUA) $(SLOTS_JSON)` and
have `tools/gen_slots.py` seed `DOME_COLS` from `tools/geometry.py` (its one
source) instead of parsing the generated file. Confirmed on a clean build:
`build/slots.json` has `DOME_COUNT` 11 with the default knob and 10 with
`DOME_COLS` 10 (and `make test` passes at 10).

## Sprite pictures are 16-px tile boxes: scale the full-dome art, then pad, don't re-clamp (2026-10-22, dome-scenery Task 2)

Symptom: regenerating the missile sheets at 2/3 and re-clamping the dart's
length in the smaller canvas made the near-front views 3-8 px too short
(and the mid views too tall): the clamp's "room" is the *canvas*, and the
dart's foreshortened projected extent does not shrink in the same
proportion as the dart's nominal length.

Cause: a sprite picture can only be a whole number of 16-px columns and
tiles, so every level's box is round-up(box0 * 2/3) to 16 px (64 -> 48,
32 -> 32, 16 -> 16): the art cannot be exactly 2/3 of the full-dome sheet
on every axis. Drawing the *full-dome* picture (its own clamp, its own
strokes) and then scaling the geometry by 2/3 reproduces the full-dome
shape at every view; re-deriving the clamp at the small canvas flattens
the near views.

Fix: keep the full-dome clamp (room and stroke: box0/16 px), scale the
drawn length and the stroke by 2/3, centre the result in the tile box;
snap the header's tip to the nearest lit pixel so the runtime's placement
vertex is on the picture. Confirmed per view against the old sheets: every
view is within 2 px of 2/3 the old size except the few near-front m views
whose 2/3 target is below the 32-px canvas' minimum (the 16-px tile grid
cannot hold them). The explosion is the same: draw at 64x64, 0.6 px per
Vectrex unit, then centre in 48x48.

## A convex silhouette's bottom row is a tangent: a flat cut is one unbroken run, not 60 px (2026-10-23, dome-scenery Task 3)

Symptom: the plan's Task 3 proof 2 asks that view 0's lowest lit row span at
least 60 px after the dome gets a flat base. The flat cut projects to an
ellipse; its lowest pixel row is the ellipse's tangent point, 4 px wide
(the approved mockup measures 8 px), and no horizontal cut can make a
perspective silhouette's bottom row wide.

Cause: for a convex solid seen in perspective, the bottom row of the
picture is where the silhouette's lower boundary is horizontal - a single
tangent point, measure zero, never a 60-px run. The wide, straight part of
the flat base is the ellipse's *widest* row (row 63 here: 116 px), not its
bottom row. What the flat cut does change is gaps: the 76 cells alone have
3 runs in rows 88..90 (the old jagged rim); the cut's 25 partial pieces
fill them, so every row 19..94 of view 0 is one run.

Confirmed: rendering view 0 from the 76 cells only vs the full flat-cut mesh
gives 3 runs vs 1 at rows 88..90; the full picture's bottom row is 4 px
(x 62..65) and its lowest >=60 px row is y 88 (64 px); the widest row is
y 63 (116 px). Stated in the commit as a Plan-deviation, with the measured
numbers.

## A coloured backdrop breaks every "max channel > 40" lit-pixel test (2026-10-23, dome-scenery Task 4)

Symptom: after the play backdrop became the sky (RGB 120,176,228 -> MAME
(117,182,233)), the dome, HUD-icon, gameover-draw and flow-pages
snapshot checks failed with absurd counts: the dome box read 12288 "lit"
pixels (the whole 128x96 box), the HUD icon cells read 64 each instead of
18, and the phase-1 "dome gone" snapshot read 12288 lit pixels.

Cause: the checkers' lit predicate was `max(px[:3]) > 40`, which was a
proxy for "not the black backdrop". The sky is brighter than 40, so every
backdrop pixel counted as drawn art. The fix is to test against the
backdrop colour itself: `tests/neo_palette.py` now has `SKY_RGB_WORD`
0x47be, `SKY_RGB` (neo_rgb of it: (117,182,233)), `BLACK_RGB`, and
`is_lit(px, backdrop)`; the title snapshots use `BLACK_RGB`, the play ones
`SKY_RGB`. Confirmed on the hud leg: icon cells went from (64,64,64) back
to (18,18,18) and the gameover-draw phase-1 box from 12288 to 0.

## A second static backdrop (the grass) breaks every "not the sky" lit test (2026-10-23, dome-scenery Task 5)

Symptom: after the ground block (y 100..223) was added, the dome, HUD-icon
and gameover-draw snapshot checks counted the grass as drawn art: the dome
box read 3072 lit samples in the dome's band (the ground fills its lower
rows), the HUD icon cells read 64 each again (they sit at y 192..199 inside
the grass), and the gameover-draw phase-1 "dome gone" box read 12288.

Cause: the checkers' lit predicate was "not the sky" (or, before Task 4,
"not black"); the grass is a second static picture the cart draws with no
sprite, so any pixel-based "is something drawn here" test that does not
subtract both backdrops counts it. The fix is `neo_palette.is_grass(px)` /
`ground_rgb_set()`, which reads the generated `build/ground_map.h`'s two
ground banks through MAME's DAC; the dome/HUD/gameover scans use `dome_lit`
(lit and not grass). check_broken's pixel-exact compare paints the ground
first (it is the lowest sprite slot) before compositing the dome, overlays
and ship. Confirmed on the hud leg: icon cells went from (64,64,64) back to
(18,18,18); the dome leg from 3072 lit samples in the box back to 1837;
check_broken's compare went from 3470 differing pixels to 0.

## A slot map shifted by the grass: stale generated slots.json and hard-coded RADAR0

Symptom: after moving the whole slot map up by 20 (the ground took slots
1..20, missiles behind from 21), the radar leg failed with "240 radar frame
slot SCB3 mismatches" and "blip shown but no slot read", and the broken
leg's pixel-exact compare differed by thousands of pixels while the dome
looked right on screen.

Cause: two copies of the old map. `tests/check_radar.py` had a hand-written
`RADAR0 = 157` (now 177), and the probes dofile `build/slots.lua`, which
the grouped Makefile rule regenerates only when `src/slots.h` is newer, so
a build that ran before `src/slots.h` was re-written kept the old numbers
and the probe dumped the wrong slots. Confirmed by regenerating
(`python3 tools/gen_slots.py build`) and re-running: `DOME_SPRITE` 36,
`RADAR_SPRITE` 177; both legs then PASSed. Fix: the checker reads
`RADAR_SPRITE` from `build/slots.json` (the one map), and the slot map's
generated files must be rebuilt after any slots.h edit.

## A second static band above the dome (the mountains) breaks the "above the box" lit test (2026-10-23, dome-scenery Task 6)

Symptom: the `dome` leg failed with "lit samples inside dome box: 1837,
above it: 128" right after the mountains were placed at y 52..99. The band
sits right above the dome box (y 104..199) and its bottom rows (y 96..99)
overlap the check's 8-row "nothing lit above the box" scan (y 96..103), so
the mountain colours counted as dome pixels.

Cause: the check's lit predicate subtracted only the sky and the grass; the
mountain band is a third static picture the cart draws (in its own palette
bank 9), so `neo_palette.is_mountain(px)` / `mountain_rgb_set()` (reading
`build/mountain_map.h`'s bank through MAME's DAC) joined `is_grass` in
`check_snapshot.dome_lit`. Only that one scan overlaps the band: the
gameover-draw and HUD box scans start at y 104 / y 192, and check_broken's
pixel-exact compare is inside the dome box, so they need no change.
Confirmed on the dome leg: above-the-box samples 128 -> 0, inside 1837
unchanged; the mountains leg's own pixel proof compares 15360/15360 band
pixels with 0 mismatches.

## The console's amber is the ship's amber: two pictures share a colour word (2026-10-24, dome-scenery Task 7)

Symptom: after the console was placed (y 144..223, all 20 columns), the
`ship` leg failed with "ship pixels: 180". The ship's own amber palette and
the console's trim/lamps both go through MAME's DAC to (255, 146, 22)
(console `con_pal[5]` 0x7f81 is the same word as one of the ship's amber
shades), so `check_snapshot`'s colour-only `amber(px)` counted the panel's
static trim under the ship.

Cause: a colour predicate cannot tell which palette bank drew a pixel. The
console is scenery, not the ship, so the fix is to subtract the console
bank's colours from that one predicate (`neo_palette.is_console_only`), the
same way the grass and the mountains were subtracted from the dome's lit
scan. Confirmed on the ship leg: 180 -> 52 pixels, centre y 189 -> 152; the
ship's real count (52 at the start cell) and the console's own pixel proof
are unchanged.

The same collision hit the ground leg's shadow proof: the console's 20
column boxes span y 144..223 across the whole width, so the old "right of
x 225" window had no uncovered shadow pixels left. The fix there is the
console's generated picture, not its boxes: a pixel under a console box is
still visible wherever that column's art is transparent
(`render_console.console_picture()[y, x] == 0`), 850 art shadow pixels
remain uncovered (668 right of x 225), and the 50-pixel twin/plain proof
still passes 50/50. Confirmed on the ground leg (0 -> 50 picked after the
change).

## A lowered console's wing trim enters the dome box's bottom corners (2026-10-24, dome-scenery Task 8)

Symptom: after the console art was lowered (the wings' top edge y 182, the
columns' first tile row y 176), two checkers failed on their static-scenery
predicates even though the game was unchanged: the `gameover-draw` leg saw
"30 lit pixels in the dome box" on a GAME OVER with the dome hidden, and the
`cracks` leg's pixel-exact compare saw 30 px differ in the dome box.

Cause: the new console picture reaches y 195..199 at x 96..100 and x
219..223 — the dome box's bottom-left and bottom-right corners (the box is
x 96..223, y 104..199). The Task 7 art stopped at y 204 on those columns (its
strip), so no console pixel had ever been inside the box. Both checkers had
already learned to subtract the grass from the box; the console is the same
kind of static picture (its own palette bank, no shared colour words with the
dome or the grass), so the fix is `neo_palette.is_console_only(px)` in
`check_gameover_draw.dome_lit_pixels` (30 -> 0 lit) and the generator's own
opaque picture in `check_broken`'s expected composite (30 px differ -> 0).
Confirmed on both legs; the console's own pixel proof is unaffected.

## The amber HUD is the ship's amber: a whole-screen ship scan counts the score (2026-10-24, dome-scenery Task 9)

Symptom: after the in-play HUD moved to the amber fix palette, the
`ship-top` leg failed with "ship pixels: 55 (whole ship ~36, half ~18:
>= 28), centre y 150 (peak: < 131)" although the ship was at the peak.

Cause: `check_snapshot.ship_centre_y` scanned every row of the screen in
the dome's columns for "amber" (r > 150, g > b + 50), and the in-play
score's fix row 28 (screen y 208..215) now draws in the amber bank, whose
(241,109,14)/(255,160,38)/(255,190,86)/(255,225,152) pass that predicate.
The scan counted 16 score pixels below the dome box and pulled the centre
down. (The blue bank's 1..5 did not pass it, so the leg passed before.)
Fix: scan only the DOME BOX's y span (DOME_Y..DOME_Y+DOME_H-1), where the
ship always lives — the HUD row is below the box's bottom (199) — and not
by colour, because the ship's palette and the amber HUD share (255,225,152)
and (65,22,0). Confirmed on both legs: ship 52 (centre 152), ship-top 36
(centre 117), the documented whole-ship counts. The `dome-lift` check
already excluded the score by position (x 128..191, y 208..215).

## The boot test runs its legs in parallel (2026-10-24)

`make boot-test` now runs scripts/boot_test_all.sh: every leg in its own
`build/boot-legs/NN-MODE/` (BOOT_OUT), half the cores at a time, outputs
printed in order: ~2 min instead of ~13. A single leg
(`scripts/boot_test.sh MODE`) still writes build/boot. A checker must find
its files from its own leg's directory (`$OUT`, the directory of the
`snap.png` it is given), never by walking up: check_gameover_draw and
check_ship_respawn looked two levels up (all of build/), which only worked
while every leg shared build/boot, and picked another leg's snapshot once
they didn't. Legs that share state (the best-mvs and best-aes groups) are
one job that runs its legs in order; a new leg goes in the LEGS list in
boot_test_all.sh.

## An opaque sprite above a static picture moves that picture's coverage bound (2026-10-24)

Symptom: after Task 10 turned the radar's frame into a mostly-opaque
scanner disc, the `console` boot leg failed with "only 9463 of 10740 opaque
console pixels compared (need at least 90%)" while its pixel comparison
still had 0 mismatches.

Cause: the checker's anti-vacuity bound compared against the panel
picture's total opaque pixel count, subtracting only the pixels the slots
above it really draw. The radar frame's new fill/rings/bezel are opaque
(index 2..4), so they legitimately cover 1064 panel pixels (plus 213 more
from the sticks/headings), and 88.1% of the whole picture was all that was
left to compare. Nothing was actually wrong with the panel.

Confirmed by rebuilding the same probe dump with the checker: 10740 opaque
panel pixels, 1277 covered by the slots above (1064 inside the radar's
64x32 box, 213 outside it), 9463 compared, 0 mismatches.

Fix: keep the 90% bound but take it over the pixels nothing above covers
(`opaque - covered`), not the picture's total. The rule the bound encodes
— every panel pixel not hidden by a sprite is compared — is unchanged;
only the denominator follows the art. Do not lower the percentage.

## Python's round() is banker's rounding: reproduce it exactly, not with half-up (2026-10-25, dome-scenery Task 11)

The props generator places each picture with `round(ax * k)` and
`round(16 * k)` on exact floats, and Python's `round()` rounds half to
**even** (`round(0.5) = 0`, `round(1.5) = 2`). C's `(n + half) / den`
(half-up) disagrees at every exact .5 (5-12 mismatches over the props'
anchors), and a 16-bit fixed-point `K = round(se * 65536 / ppu)` table
loses the numerator's remainder and breaks ties differently (1071).
Exact instead: keep the true numerator (`n = a * se`, fits u16 here),
`q = (n * 10923) >> (18 + lod)` (= `n / (24 << lod)`, exact to n 24576,
one `mulu.w`, no `divu`), then the remainder decides the half, a tie to
even. Checked bit-exact for se 0..96, a 0..256, all three LODs.

## A shrunk sprite's pixels come from the BIOS zoom tables, not `i*16/(hz+1)` (2026-10-25, dome-scenery Task 12)

Symptom: the props' pixel proof (Task 12) failed 928 of 3594 compared
pixels although every SCB word matched Task 11's model. The expected image
had been built the way `tools/render_props.compose()` previews it — art
column `i * 16 // (hz + 1)` for drawn column i, art row
`line * 256 // (v + 1)` for box line — and that is a linear resample, not
what the LSPC does.

Cause: horizontal shrink is a 16-bit mask (`ZOOM_X` in
`tools/render_radar.py`, decoded from MAME's `zoom_x_tables`): the drawn
box column k reads the art column of the k-th set bit, so hz $B (12 px)
reads art cols 0,1,2,3,4,5,8,9,10,11,14,15 — not 0,1,3,4,5,6,8,9,10,12,13,
14. Vertical shrink is the BIOS `000-lo.lo` table (`_ZOOM_Y[(vz << 8) |
line]` gives the SCB1 row and the art row). The preview is an
approximation; the runtime is exact.

Confirmed: rebuilding the expected image from those tables gave 0
mismatches on 3678 compared pixels (the same probe dump). The checker now
imports `render_radar`'s tables, so the proof is against the hardware.
The radar tests had already documented the tables; the props' generator
preview did not, and copying its sampler was the trap.

## A checker's sprite box must wrap SCB4's 9-bit X at 512 (2026-10-25, dome-scenery Task 17)

Symptom: the mountains' pixel proof compared all 15360 band pixels and
reported 2401 mismatches after the towns band was added, although the band
drew correctly on screen. The checker's `covered()` used each sprite box's
`SCB4 >> 7` as a plain screen x, so the band chain's driver at X 509 (the
9-bit form of `-3`) was treated as starting at x509 and its 21 columns were
all off-screen.

Cause: SCB4's X is 9 bits and wraps at 512. A column at bx covers screen x
when `(x - bx) mod 512` is inside its 16-px width (so bx 509 covers x0..12),
and each sticky follower advances `(x + 16) & 0x1ff`, not `x + 16`. With
both fixed the mountains checker compares its still-visible 5120 px with 0
mismatches. The runtime itself was never wrong; only the Python box model
was.

## A signed 32-bit `/ 5` becomes a `__divsi3` call; cast the numerator to u16 (2026-10-25, dome-scenery Task 17)

Symptom: `(16 * da + 2) / 5` in the band's scroll compiled to a `jsr
__divsi3` libgcc call, not a 16-bit divide. `int` is 32-bit on this
toolchain, so the signed expression was a 32-bit divide.

Fix: cast the numerator to `u16` first. gcc then knows the dividend fits
16 bits and strength-reduces the constant `/ 5` to one `mulu.w #-13107`
plus a swap/shift (objdump: no `__divsi3`/`__udivsi3`). The quotient is
the same for all 240 angles (tests/band_model.py). Check any new divide
with `objdump -r` for `__divsi3`/`__udivsi3`; a libgcc call is a
per-frame cost the plan does not budget.

## A commit after vblank leaves the VRAM one frame behind the cart's model (2026-10-25, dome-scenery Task 18b)

Symptom: after the missiles/radar moved to the vblank commit, the radar
boot-test compared frame fc's VRAM with the model at fc and failed: the cart's
radar_t at frame fc was already prepared, but the commit at the start of fc had
written frame fc-1's prepared state.

Fix: the radar probe records the previous frame's cart radar_t (the `b`/`r`
lines) and check_radar.py compares the VRAM/palette/pixels with frame fc-1.
The same offset already applied to the props; any per-frame commit after
vblank needs it. State the offset in the commit.

## A generated header's unused static-const tables warn; scope the diagnostic around the include (2026-10-25, collapse Task C1)

Symptom: including `build/collapse_map.h` in src/dome.c for Task C1's ruin
raised `warning: 'fire_pal' defined but not used [-Wunused-const-variable=]`
(and one per unused table) even though the header is generated and the rest
of its tables were deliberately left for Tasks C2-C4; the gate forbids
warning lines.

Cause: the generator emits every table as `static const`, and `-Wall`'s
`-Wunused-const-variable` warns for each file-scope static that the including
translation unit never references. (`ruin_tile`/`ruin_pal` are used, so only
the C2-C4 tables warn.)

Fix: wrap the include in `#pragma GCC diagnostic push` /
`ignored "-Wunused-const-variable"` / `#pragma GCC diagnostic pop`, so only
the generated header's unused tables are quiet. Confirmed by rebuilding the
normal and GAMEOVER_DRAW_TEST carts (no warnings; the ruin's tables still
reach the ROM). Do not suppress it globally — only around the generated
include.

## Blanking SCB1 tile rows: write only the tile words with VRAMMOD 2 (2026-10-25, collapse Task C3)

Need: Task C3 blanks the fragment slots' SCB1 rows 2..31 on the collapse's
first frame: 46 slots x 30 rows. Writing the normal tile+attribute pair is
2760 VRAM words; the tile-only form is 1380.

Fix: the rows are invisible when their tile is the part's blank tile
(COLLAPSE_TILE_BASE + 0): palette index 0 is transparent whatever the stale
attribute word says. Set `REG_VRAMMOD = 2` and write only each row's tile
word (the address steps over the attribute), halving the blanking to 1380
words. The fragment commit measured 1518 words (1380 blank tiles + 138
SCB2/3/4) at vpos 16..78; the whole collapse commit on that frame (fragments
+ the 528-word fire blanking) was 2046 words at vpos 16..95 (80 lines). The
collapse leg checked all 1380 rows as COLLAPSE_TILE_BASE, and the centred
framemark's worst span is 167 (the collapse frame 167 at fc 8360), no
dropped frames. Only valid for a transparent tile; never skip the
attributes of a visible tile.

## The collapse's first-frame prepare must stay short: cracks_show hides the overlays after it (2026-10-25, collapse Task C4)

Need: Task C4's first collapse frame originally staged the initial hidden
SCB2/SCB3/SCB4 of all 73 collapse slots plus the first 50 blank rows in
`collapse_prepare`. That pushed `src/cracks.c`'s one-time overlay hide
(which runs after `collapse_prepare` in `game_frame`) to vpos 135, inside
the old overlays' visible span (SCB3 tops 109..124 -> screen lines
125..140). C3's tear proof (and the smoke/puff taps) flagged the hide as a
tear at fc 8359, even though the hide itself is safe.

Fix: the first frame stages no hidden words. Set the memos to the hidden
values in `reset_*`, set `initial_hides`, and write the initial
SCB2/SCB3/SCB4 of every collapse slot directly in that frame's vblank
commit (219 words). Start the one-time blanking at f 1 with 52 rows a frame
(2080 > 2049), not f 0, so it still finishes at f 40. Measured: cracks'
hide now runs at vpos 111..113, before the old overlays' first line (vpos
125); the f 0 commit is 219 words; the worst collapse
commit is 546 words, 33 lines at fc 8401; the centred framemark's collapse
worst dropped from 167 (fc 8360) to 156 (fc 8359), and the full collapse
leg passes with 0 puff/smoke tear frames.

## MAME's snapshot at frame n shows frame n-1's display, not the VRAM read at n (2026-10-26, attract A1)

Symptom: the flow-pages title pixel proof compared the PNG taken at a page
PIN frame with the FIXMAP rows decoded in that same frame. Every expected
text fill pixel was black: the F record already held the new page's
TITLE_FONT_BASE/TITLE_CAP_BASE tiles, but the snapshot still showed the
previous page (the page-1 PIN's PNG showed page 0; page 0's first PIN PNG
was the blank pre-title frame).

Cause: MAME's `machine.video:snapshot()` at frame n captures the display
of frame n-1, while a Lua `vread()` of FIXMAP at frame n sees the cart's
just-written VRAM. The two are one frame out of step at a page turn.

Fix: `scripts/flow_probe.lua` schedules the PIN's C block/snapshot two MAME
frames after the PIN (`pending_dump = { at = n + 2, page = page }`) and
takes it only if the page is still the scheduled one. The rows do not
change in those two frames: page 0's prompt is still PRESS START at t 2,
and a text page's rows do not depend on t. The proof then read 0
mismatches: page 0 frame 28 = 272 text fill (amber 1..4) / 661 text
outline (black) / 1152 logo fill (gold 1/3/6..9) / 704 logo outline
(black); page 1 frame 323 = 449 text fill / 1081 outline.

## A MAME notifier can catch the demo mid-frame; log on the cart's hash frame (2026-10-26, attract A3)

`demo_probe.lua` reads `demo_dbg_fc` and the demo's state in a MAME
frame notifier, but the cart may be between `demo_input` (which bumps
`demo_dbg_fc`) and `game_frame` / `demo_hash_frame`. Then the fields are
one frame ahead of the hash and a sampled record cannot be aligned by
hash. Export the cart-side `demo_dbg_hash_fc` (set to `demo_dbg_fc` at
the end of `demo_hash_frame`) and log a D line only when it equals
`demo_dbg_fc`; the epoch hash still covers every frame, including the
one or two the notifier misses at an epoch's start.

## A staged title commit is one vblank behind; the drawn rows use t-1 (2026-10-26, attract A2)

With the title's rows staged in `title_frame` after the vblank and written
by `title_commit` in the next vblank, the FIXMAP read at frame n shows the
state that produced it, while the T record's RAM read is the new state:
one title frame ahead. Compare the drawn rows with `t-1` (and, on a turn
with t 0, the previous page's t 294). The row-28 MVS countdown likewise
shows the timer byte read at n-1. The entry's two-vblank scene setup costs
two MAME frames; advancing `title_t`/`title_seed_t` by 2 keeps the page
timing and the Start seed at their pre-A2 values (flow's Start seed
0xa876; the AES 600 Start's 0xaede).

## A MAME write tap gives the absolute address and a byte port's value in both halves (2026-10-26, attract A4)

Symptom: the REG_SOUND write tap logged `data` 0x0404/0x0808 and
`offset` 0x320000, so a filter for commands 4..8 matched nothing; and
`install_write_tap(0x320000, 0x320000, ...)` aborted with "end address has
low bits unset, did you mean 320001?". Cause: MAME's tap callback receives
the ABSOLUTE address (not an offset from the range start), and a byte port's
`move.b` reaches it as the 16-bit value with the byte duplicated in both
halves. Confirmed by logging every write (`W 441 3276800 2056 ...`) and
masking `data & 0xff` to 8. Fix: tap the odd end 0x320000..0x320001, test
the absolute offset, and use the low byte.

## On MVS a coin re-enters the cart at main_mvs_title and resets .bss (2026-10-26, attract A4)

Symptom: after the demo-sound probe inserted a coin and pressed Start five
frames later, the cart's demo epoch jumped back to 1 (`E 5635 3 1 1 1`) and
the game never began. Cause: on MVS the BIOS re-enters the cart at
`main_mvs_title` (the post-coin title) after the coin, which zeroes `.bss`
and restarts the demo; a Start pressed before that entry is lost. Confirmed
by the E records and by the game starting at cart fc 4 with command 4 at
MAME 5640 once the probe waited for the re-entry (epoch 1 again) before
pressing Start. Fix: coin, wait for the epoch to return to 1, then Start.

## The ship's staged SCB1/SCB3 commit is one vblank behind; sample the next frame (2026-10-26, stopper-spider S2)

`ship_gfx_prepare` chooses the picture from the state after frame N and
stages the SCB1 tiles plus SCB3 Y; `ship_gfx_commit` writes them in the
vblank at the start of frame N+1. So the slots read at frame N show the
picture chosen for the state after N-1. The `spider` leg compares frame N's
SCB1 with `ship_anim_tile[lat][frame_of(state after N-1)]`, and
`ship-respawn` dumps the first respawn picture at the respawn frame + 1
(3806, not 3805) and checks the model state at dump-1. Sampling the respawn
frame itself read the hide's SCB3=0 and the old pose's tiles, which looked
exactly like a failed respawn.

## The first attract page is not a full demo cycle; the next page is (2026-10-26, stopper-spider S2)

The first entry's page 0 has 2652 demo frames (dfc 1..2652), because the
0-page turn resets `demo_fc` to 0 and the restart frame's `demo_input`
bumps it to 1 as epoch 2. The next page 0 runs the full `DEMO_FRAMES` =
2655 frames (dfc 1..2655). To prove one full demo script cycle, let epoch 2
run out and press Start on epoch 3; epoch 1's 2652 frames do not cover the
whole script.

## sox at the WAV's own rate is bit-identical; synth_sfx.py needs its OUTDIR (2026-10-27, rockets-and-sounds R1)

`sox in.wav -r 18500 out.wav` leaves an already-18500 Hz mono WAV
byte-for-byte identical (`cmp` on all five R1 synth WAVs: move/jump/fire/
hit/crack). So the V ROM's sample bytes are the ADPCM-A encoding of
`tools/synth_sfx.py`'s own output, not a resampled copy; the V ROM test
encodes `build/sfx-synth/*.wav` and compares directly. `tools/synth_sfx.py
OUTDIR` also assumes OUTDIR exists (unlike `tools/render_sfx.py`, which
makes it), so the Makefile and the host test create it first.

## An h-flipped sprite samples art column `15 - col`, not `col` (2026-10-27, rockets-and-sounds R2)

Symptom: a pixel-exact rocket check against the SCB1 art and the BIOS
`ZOOM_X_COLS` table failed on every h-flipped missile (111 of 126 pixels at
one snapshot), even though the tile numbers and position matched the model.
Cause: SCB1 odd-word bit 0 mirrors each 16-px tile before the horizontal
zoom samples it, so the art column for screen offset `j` is
`15 - ZOOM_X_COLS[hz][j]`; the separate column-order reversal
(`sc = cols-1-c`) only chooses which tile is fetched. Confirmed by decoding
both front missiles with `15 - artcol` and getting 0 mismatches at the
snapshot's LSPC counter.

## The MAME notifier can miss the demo's heaviest frame; the cart hash covers it (2026-10-28, attract D1)

Symptom: the spider boot-test's full-cycle check failed on the new demo
player with `epoch 2: 2654 frames`, though the cart ran all 2655: the D
records were missing dfc 507, the demo's worst work frame (263 scanlines).
Cause: the frame notifier sampled before the cart's title frame 507
completed when that frame overran the MAME frame boundary, so the next
sample saw dfc 508. Confirmed by running the spider leg on the pre-D1
`flow.c`/`softdip.c` (the same miss) and by reading the cart's
`demo_dbg_hash` at dfc 2655 = `0x6d11f0ae`, the model's full-cycle hash.
Fix: the spider probe logs that hash and the checker accepts a full cycle
when the last logged dfc's hash equals the model's; the animation check
still runs on every logged D line (5500 displays, 0 bad tiles).

## P1: the demo's props budget can trade frame time for a sprite-census overrun (2026-10-28, title-frame P1)

The props layout is the demo title frame's largest cost (~110 lines) and
the props commit writes the changed columns (~50-70). Budgeting both by
vpos (prepare only while the frame has used <=70 lines, commit only while
<=60) cut the worst cycle frame from 290 to 199 lines. But a skipped props
update keeps the previous angle's SCB3 heights, and a long lag put 98
sprites on one line (the hardware limit is 96) even though the correct
layout has 80. A prepare budget of 68 fixed the span but still left the
98-sprite frame; 70 is the measured point that keeps the census at 93 and
the worst frame at 199. Budget the props only after checking the census,
not just the span.

## Press Start on the cart's title frame count, not a MAME frame (2026-10-28, props-table P2)

Symptom: on the boot-test's fixed MAME Start (600/1200/1400/1800), P2's
cheaper title frames moved the game's missile seed: title_seed_t was 577 at
MAME 600 instead of HEAD's 575 (mis_seed_used 0xaea0 vs 0xaede), so the
calibrated collapse/radar/flow/best legs missed their GAME OVER frames.
Cause: the game seeds from mis_seed_from(title_seed_t at the Start), and
title_seed_t is the cart's title frame count; a fixed MAME press lands on a
different title frame when the title's work changes. Confirmed with the
flow/collapse probes: the seed is one more than the title_seed_t read at
the MAME frame's start, because the notifier runs before that frame's
title_frame increments the counter. Fix: scripts/start_game.lua and
scripts/mvs_input.lua press on title_seed_t (its nm address) at HEAD's title
count (575 on AES; 280 after the MVS coin), accounting for that one-frame
offset. The title entry's props_show also became cheap and started the
title two MAME frames early (title_t 7 vs HEAD's 5 at MAME 31, which the
flow-return proof checks); a two-vblank wait in the title entry restores
HEAD's title start.

## A downstream tile-count change needs its upstream generator as a Makefile prerequisite (2026-10-28, H4)

Symptom: after the 8-heading hovercraft made the ship part 20,032 tiles
(was 2,560), `make cart` rebuilt the ship, missiles and broken parts but
left `build/radar_map.h` at 26,757 (`RADAR_FRAME_TILE_BASE`) instead of the
new 44,229, so `tests/test_radar_render.py` failed with
`26757 == 44229` and the cart would fetch the radar art at the old absolute
tile numbers. Cause: `tools/render_radar.py` imports `render_broken` (which
imports `render_hovercraft`) to compute its base, but the Makefile's
`$(RADAR_MAP) ... &:` rule listed only `render_radar.py`, `render_broken.py`,
`src/radar.h` and the slot JSON — not `render_hovercraft.py` (nor the broken
map/part it derives from), so make considered the old radar output current.
Confirmed by the timestamps (`build/radar_map.h` older than
`tools/render_hovercraft.py`) and by rebuilding after adding those
prerequisites: the header and the radar c1/c2 parts regenerated at the new
base and the test passed. Lesson: a generator that imports another generator
for a tile base must name that generator (or its generated header) as a
Makefile prerequisite; otherwise a tile-count change silently leaves every
part after it at the old absolute numbers.

## A packed struct with a 3-byte array before a u32 misaligns the 68000 (2026-10-29, B1)

Symptom (caught by design, before it ran): a `board_entry_t` planned as
`u8 init[3]; u32 score10;` with `__attribute__((packed))` would put the
u32 at an odd byte offset in every other entry (stride 7: 4 + 7k + 3).
Cause: the 68000 raises an address error on an odd 16/32-bit access, so a
field read/write there faults even though the host (x86) tolerates it.
Confirmed with a host `offsetof` build: adding one explicit pad byte per
entry puts every `score10` at 8, 16, ..., 120 and `sum` at 124, all even,
and `sizeof(board_t)` is 126 on both builds. Lesson: a packed wire format
that mixes byte arrays and u32s needs an explicit pad (or a reordered
layout) so every multi-byte field sits on an even 68000 offset; "packed"
does not make a misaligned u32 safe.


## The AES card keeps saved bytes in order; MVS saveram word-swaps them (2026-10-30, B2)

The AES `card.neo` image holds the cart's saved bytes as written: after the
first best-aes run the 126-byte board's `ESR2` magic was at file offset 320
as big-endian `45 53 52 32`, and one `bios_card()` save/load of
`sizeof(board_t)` (126 bytes) worked (the entry LOAD answered 0x81, the
save 0x81, FORMAT 0, SAVE 0). The MVS `saveram` file stores each 16-bit
backup-RAM word little-endian: the same magic appeared as `53 45 32 52` at
file offset 802 (cart address 0x100002 maps to saveram offset 802).
Confirmed by reading both images after the measured best legs, and by
patching the magic to the old `ESRG`: `45 53 52 47` in the card and
`53 45 47 52` in saveram. Both entries rejected it and started from the
five defaults. Lesson: when proving a cart's backup-RAM/card state from
MAME, patch the card file as bytes but the MVS saveram as byte-swapped
words.

## A sprite's SCB1 row is two words; reading +2 reads the next row (2026-10-30, B6)

The entry ring's first commit wrote the correct tile (the C ROM base + 18)
into slot 320 but the probe read the attribute as 0. Cause: a Neo Geo
sprite's SCB1 control block has **two words per row** — the tile number at
`ADDR_SCB1 + slot*64 + 0` (a full 16-bit tile index, which is why the ring's
46610 base fits) and the attribute word (palette in bits 8..11, plus the
flip/shrink bits) at `+1`. Reading `+2` is the *next row's* tile, not the
attribute. FIXMAP is different: each fix cell is one word with the palette
in the high nibble. Confirmed by fixing the read to `+1` and by the ring
word count (37 glyph slots × 5 words + pointer). Lesson: sprite SCB1 is
`tile` then `attr` per row; only the fix layer packs palette and tile into
one word.

## VRAM auto-increment does not wrap SCB4 back to SCB2 (2026-10-30, B6)

The ring's first commit set `VRAMMOD=0x200` and `VRAMADDR=ADDR_SCB2+320`
once, then wrote 3 words per slot for all 38 slots. The result was garbage
SCB2/3/4 words after slot 0: the auto-increment walked from SCB2 slot 320
to SCB3 slot 320 to SCB4 slot 320, then continued into the SCB1/other
region instead of wrapping back to SCB2 slot 321. The fix is the same
pattern radar_gfx.c uses: set `VRAMMOD=0x200` and `VRAMADDR=ADDR_SCB2+slot`
**inside the slot loop**, then write that slot's three words. Confirmed by
the entry leg's 3496 ring-slot words matching build/ring_map.h. Lesson:
when writing a slot's SCB2/SCB3/SCB4 triple, reset the address per slot;
the modulo only wraps within the 0x200 window, not between the three
arrays.

## A 68k enum is 4 bytes; a probe must read `flow` as u32 (2026-10-30, B6)

The entry probe read the `flow` state with `sp:read_u8(flow_addr)` and
always saw 0 while the cart was in FLOW_ENTRY (hud_framecnt had frozen at
GAME OVER + 118, so it had entered). `nm` shows `flow` as a 4-byte object:
the enum's value 3 is stored big-endian as `00 00 00 03`, so the byte at
the symbol's address is 0. Reading `sp:read_u32(flow_addr)` fixed the
leg's transition detection. Lesson: read 68k enums/ints at their declared
width (u32 unless the source says u8/u16); the host's `sizeof(enum)` is
not the m68k ABI's 1 byte.

## A 68k local array indexed in an unrolled loop lost a store (2026-10-30, V1)

`show_smoke` staged each plume column's SCB2/SCB3/SCB4 in two local stack
arrays (`s2[12]`, `s3[12]`, `s4[12]`) inside a `for (c = 0; c < SMOKE_COLS;
c++)` loop. The compiler unrolled the two iterations; the probe then read
the first column's SCB3 as 0 while the second column's was right (and the
entry leg's `SM` words showed the same shape on every plume pair). The
placement memo and the tile words were correct, so the staged SCB3 was
being lost. Moving the three staging arrays to file scope (`smoke_s2`,
`smoke_s3`, `smoke_s4`) made every column's SCB3 land. Lesson: on this
68k GCC, prefer file-scope arrays for a staging table that a small fixed
loop indexes; a stack array in an unrolled loop can drop one iteration's
store.

## An entry snapshot's pixels are one staged frame behind the entry state (2026-10-30, K2)

The entry probe reads `entry_state` and the ring/flyer VRAM words at the
same tick, and takes one snapshot at entry frame 6. The words are staged by
the previous frame's body and committed in this frame's vblank, so the
ring-slot check compares `entry_state` at frame N-1. The snapshot follows
the same lag: comparing the mid-flight flyer against the snapshot's own E
record (fly_t 4) gave 121 of 152 pixels wrong; against the previous frame's
E record (fly_t 3, so `fly_scb2[2]`) gave 0 of 152. The ruin pixel check
had already matched at the snapshot's own angle, so only the flyer's
per-frame motion exposed the lag. Lesson: when checking a snapshot against
a staged sprite group, use the previous frame's state, exactly as the
VRAM-word checks do.

## A hot fix-span writer must stay inlined to keep the demo's frame time (2026-10-31, G1)

Moving `title_fix_span`'s inlined loop out of `flow.c` into an external
`fix_span` in `fix.c` added 10 scanlines to the demo cycle's worst frame:
`boot-test demo` went from the baseline's 237-line work span to 247
(limit 240) at demo frame 2066. The table/init move did not matter; an
external call per dirty row did. Keeping the one writer as a `static
inline` in `fix.h` with the pair table and `fix_thick_init` still in
`fix.c` restored 237. The GAME OVER drawing helper also had to sit after
`hud_demo_stage`/`hud_demo_commit` in `hud.c`, or its added code shifted the
demo's hot functions and the span grew again. Lesson: on this 68k build, a
per-row fix writer that was inlined must stay inline (header or same TU);
moving it to another translation unit costs enough to fail the demo's
240-line framemark check even though the cart is functionally identical.

## `TITLE_ROW_NONE` must take the ASCII path in the thick span writer (2026-10-31, G1)

Page 1's row 21/22 restore sets `title_dirty_base` to `TITLE_ROW_NONE`
(0xffff), the same path the old `title_fix_span` sent through its
`else` (base + character) branch; the probe maps the resulting control byte
to a space. A new thick/ASCII test of `base != 0` sent 0xffff through the
thick branch instead, and `boot-test demo` read `'+++++++++++++++'` on
page 1's row 21 (the wrapped thick tile decoded as '+'). The fix is to test
the two thick bases (`base == TITLE2_ROW_BASE || base == TITLE2_CAP_BASE`),
not "nonzero". Lesson: `TITLE_ROW_NONE` is a sentinel for "blank the row",
not a thick base; every span writer must keep it on the ASCII-space path.
