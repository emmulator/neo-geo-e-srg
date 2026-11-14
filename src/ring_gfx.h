/* ring_gfx.h: the high-score initials ring's sprites (high-score boards
 * Task B6). The art and its precomputed geometry are tools/render_ring.py's
 * build/ring_map.h: 37 glyph positions (one 16x16 tile each), a blinking
 * pointer tile and a palette bank per ring kind (back, front, front at
 * rest). src/ring_gfx.c owns the C ROM tile base (after the collapse part)
 * and the slots RING_SPRITE .. RING_SPRITE + RING_COUNT - 1.
 *
 * The ring is drawn in FLOW_ENTRY only. ring_gfx_prepare runs in the entry
 * frame and stages the 37 glyph sprites in ring_order (back to front) plus
 * the pointer; ring_gfx_commit writes the changed words in vblank, like the
 * scene's other groups. ring_gfx_init/ring_gfx_hide write directly (they
 * run outside play frames).
 *
 * K2: ring_gfx_prepare/ring_gfx_commit also stage and write the flying
 * letter at FLY_SPRITE, one slot above the ring: while entry_t.fly_t > 0 it
 * shows the picked position's tile (ring_kind 2's hot palette) at
 * fly_x/fly_y[ninit - 1][fly_t - 1] with fly_scb2[fly_t - 1], one tile
 * high; otherwise SCB3 is 0 (hidden). ring_gfx_hide hides it with the ring.
 */
#ifndef RING_GFX_H
#define RING_GFX_H
#include <ngdevkit/types.h>
#include "entry.h"

/* the three ring palette banks (13, 14, 15 were free after Task C4) */
#define PAL_RING_BASE 13

/* hide all 38 ring slots and stage the three palette banks for the next
 * vblank commit; call once at every flow_run entry. */
void ring_gfx_init(void);

/* stage one entry frame's ring: the 37 glyphs at the entry's phase in
 * ring_order (back to front, the front letter in the highest slot) and the
 * pointer shown on `frame` where (frame >> 3) & 1 is set. */
void ring_gfx_prepare(const entry_t *e, u16 frame);

/* write the staged ring/palette words; call in vblank with the scene's
 * other commits. Only changed groups are written. */
void ring_gfx_commit(void);

/* hide all 38 ring slots now (leave to the title after END); direct write,
 * call outside the play frame. */
void ring_gfx_hide(void);

#endif
