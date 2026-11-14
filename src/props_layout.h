/* props_layout.h: the props' placement at one dome angle (dome-scenery
 * Tasks 11 and 15). Pure arithmetic over the generated tables in
 * build/props_map.h (the 22 trees and rocks of tools/render_props.py):
 * which props are visible, split into the back pool (under the dome) and
 * the front pool (a near prop whose crown or stone covers the dome on
 * screen), each far to near, and for each of their sprite columns the
 * SCB2/3/4 words and the first SCB1 tile. No hardware, no per-frame divide
 * (see props_layout.c). Host-built like src/ship.c (tests/props_sim) and
 * linked into the cart (src/props.c draws the props). */
#ifndef PROPS_LAYOUT_H
#define PROPS_LAYOUT_H
#include <ngdevkit/neogeo.h>

/* build/props_map.h defines the generated tables; most of them are not used
 * here (only the ones props_layout.c reads), so keep gcc from warning about
 * the unused static consts in this include. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-const-variable"
#include "props_map.h"
#pragma GCC diagnostic pop

/* one sprite column of a props pool (relative to PROP_SPRITE for the back
 * pool and PROP_FRONT_SPRITE for the front one once the cart shows them):
 * shown = 0 marks an unused slot. */
typedef struct {
    u8 shown;       /* 0 unused / 1 drawn */
    u8 prop;        /* the prop's index 0..NPROPS-1 */
    u8 lod;         /* the picture's LOD 0..PROP_NLOD-1 */
    u8 col;         /* the picture's column 0..cols-1 */
    u16 scb2;       /* (hz << 8) | v */
    u16 scb3;       /* ((496 - top) << 7) | rows */
    u16 scb4;       /* ((col_x & 0x1ff) << 7) */
    u16 tile;       /* first + col * rows (relative to the props part) */
} prop_slot_t;

/* fill the two pools for dome angle da (0..PROP_NDA-1): a visible prop is
 * in front when prop_front[i][da] is 1, else in back; each pool ordered by
 * foot y, smallest first (far first, ties to the lower index), its columns
 * in slots 0.., the rest shown 0 with every word 0. */
void props_layout(u8 da, prop_slot_t back[PROP_BACK_SLOTS],
                  prop_slot_t front[PROP_FRONT_SLOTS]);
#endif
