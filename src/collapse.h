/* collapse.h: the fireball, the flying glass, the shake's puffs and the
 * ruin's smoke of the dome's collapse (the collapse redo's Tasks C2-C4).
 * From the burst (g 0, g = collapse_frac - COLLAPSE_SHAKE) a fireball grows
 * over the ruin for FIRE_T (45) frames: six 12 x 10-tile pictures, grown by
 * the hardware's shrink, in 12 independent sprite columns (never a sticky
 * chain: a shrunk sticky chain leaves gaps between its columns). The tables
 * and the palettes are the generated collapse header's (build/collapse_map.h,
 * tools/render_collapse.py).
 *
 * The fragments are NFRAGS (49 in Task V2's generator) one-column full-size
 * pieces of the dome's
 * own glass (view 0), in the dome's bank PAL_DOME: their top-left comes from
 * frag_x/frag_y (COLLAPSE_HIDE = not drawn) for g 0..FRAG_T-1, their tile
 * rows from frag_tile, and their whole-piece flip (bit 0 H, bit 1 V) from
 * frag_flip. A V flip reverses a 2-tile piece's rows as well as setting the
 * attribute's V bit. The fragments sit over the smoke and under the
 * fireball (src/slots.h's sub-map), so the commit writes them first.
 *
 * Task C4 adds two more pictures in the same range:
 *  - the puffs, NPUFFS (5) full-size 2 x 2-tile bursts during the shake
 *    (f 0..40) in PAL_FIRE; puff n shows picture i = (f - puff_f0[n]) /
 *    PUFF_STEP while 0 <= i < PUFF_FRAMES, at (puff_x[n], puff_y[n]), in
 *    the slot pair n % 3 (six slots, at most three shown), and every puff
 *    is hidden from the burst (f 41) on;
 *  - the smoke, NPLUMES (6) plumes of SMOKE_COLS x SMOKE_ROWS (2 x 7)
 *    tiles in PAL_SMOKE, each an 8-picture loop: per plume and g the header
 *    gives smoke_pic (0xff = not started), smoke_dx, smoke_lines, smoke_v
 *    (SCB2 0x0f00 | v) and smoke_h (SCB3 height), repeating from SMOKE_LOOP
 *    every SMOKE_PERIOD once g >= SMOKE_T. Per dome step a the header gives
 *    smoke_foot_x/y (the plume's foot) and smoke_front (bit p = plume p is
 *    in front of the ruin). Plume p's left is smoke_foot_x[a][p] +
 *    smoke_dx[p][g] - SMOKE_COLS * 8 and its top smoke_foot_y[a][p] -
 *    smoke_lines[p][g]; columns are independent (col c at left + 16 c).
 *    Each frame the plumes take the next free FRONT pair of slots if their
 *    front bit is set, else the next free BACK pair (both ranges of six
 *    slots: SMOKE_BACK_SPRITE below DOME_SPRITE, COLLAPSE_SMOKE_SPRITE in
 *    the overlay range). The pictures are swapped by the CPU (the LSPC's
 *    one global auto-animation counter cannot give each plume its own
 *    phase).
 *
 * The collapse keeps its own g: collapse_frac - COLLAPSE_SHAKE while the
 * dome death runs, then one more every frame while dome_draw_gone (the
 * dome-death GAME OVER, which starts at g 77 and runs until A restarts the
 * game or the title is returned to).
 *
 * The collapse lives in the broken overlays' slot range, which it owns:
 * src/cracks.c hides the range once on the collapse's first frame and
 * writes nothing there until the dome is whole again.
 *
 * As the trees after Task 18, the words are staged in RAM by
 * collapse_prepare (once per play frame, after the dome's drawing) and
 * written in vblank by collapse_commit (right after ng_wait_vblank, next to
 * props_commit), so no collapse slot is rewritten while the raster is
 * inside it. The fireball, the fragments, the smoke and the puffs therefore
 * show the previous frame's g/f, like the props. The one-time SCB1
 * blanking (the rows the hardware may sample below the fire, fragment,
 * smoke and puff pictures) is spread over the shake's f 0..40, puffs first
 * (they first show at f 14), so no collapse frame's commit is over ~600
 * words; every row is blank before the burst (f 41), which keeps C2/C3's
 * word proofs.
 */
#ifndef COLLAPSE_H
#define COLLAPSE_H
#include "rules.h"           /* rules_t, collapse_frac/COLLAPSE_SHAKE */

/* the fireball's and the puffs' palette bank: the props own 22..43, the
 * ground's ripple 44..54 and the ruin 55. The smoke's own bank is 57. */
#define PAL_FIRE 56
#define PAL_SMOKE 57

/* once at boot (src/main.c's init_all, next to dome_init): load fire_pal
 * into the bank and clear the memo. */
void collapse_init(void);

/* once per play frame, in game_frame after the dome's drawing (and on every
 * FLOW_ENTRY frame after the ring machine): decide this frame's fire,
 * fragment and plume words (g from the rules; out of the collapse every fire
 * column, fragment and plume is hidden) and stage only what changed — the
 * fire columns' SCB2/SCB3/SCB4 when their words differ from the last
 * commit's, the SCB1 tile words of every fire column when fire_pic changed
 * (rows 0..FIRE_ROWS-1, attribute PAL_FIRE << 8), the fragments' SCB3/SCB4
 * and SCB1 rows 0..FRAG_MAX_ROWS-1 when their placement, flip or first-shown
 * state changed (attribute (PAL_DOME << 8) | flip, a V flip's 2-tile rows
 * reversed), and the plumes' placement/tiles from the tables at (angle, g).
 * `angle` is the scene's dome step: ship.dome_angle during the collapse's
 * GAME OVER, entry_dome_angle on the entry screen, 0 at the title's setup.
 * On the collapse's first frame (f 0) it also stages the one-time blanking
 * described above. No VRAM or palette writes. */
void collapse_prepare(const rules_t *r, u8 angle);

/* right after ng_wait_vblank on every play frame: write what
 * collapse_prepare staged (only the words that changed), the fragments
 * before the fireball (a fragment can be as high as screen line 45, the
 * fireball's top is never above line 80). */
void collapse_commit(void);
#endif
