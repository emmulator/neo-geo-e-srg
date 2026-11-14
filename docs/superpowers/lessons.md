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
