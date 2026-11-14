/* cracks.h: broken-window overlays drawn over every broken cell (M4-fixes
 * Task 3).
 *
 * Every broken cell the camera can see shows a broken window: a full-tile
 * overlay drawn in exactly the cell's own projection in the dome picture
 * (the picture covers the cell's outline exactly, as the dome draws it at
 * that view), black in the middle with jagged glass fragments in the
 * dome's colours clinging to the cell's edges. The pictures are
 * pre-rendered per (cell, view) by tools/render_broken.py (broken_map.h)
 * and drawn as full-size sprite tiles ("stones"), so the overlay never
 * shrinks and never has leftover rows.
 *
 * Constraint record (the plan's style):
 *
 *   Sprite slots: THE map lives in src/slots.h (M5 Task 1); the overlays
 *   own BROKEN_SLOT_BASE .. BROKEN_SLOT_AFTER-1 (36..145: 110 columns for
 *   the 76 cells' widest pictures; the draw packs the facing cells
 *   contiguously from BROKEN_SLOT_BASE). A HIGHER slot draws on top
 *   (neo-geo-dev, "Sprite drawn behind something it should cover"), so the
 *   slot constants all move with slots.h:
 *     Stars:       1..12 (behind everything, Task 2)
 *     Missiles:    13..27 (behind the dome)
 *     Dome:        28..35 (8 columns, a sticky chain, never shrunk)
 *     Broken:      36..145 (packed, one stone column per 16 px of cell)
 *     Ship:        146..147 (2 columns)
 *     Front darts: 148..162 (NOBJ x MIS_COLS_MAX)
 *     Explosions:  163..168 (NEXPL x EXPL_COLS)
 *     Radar:       169..187 (reserved, Task 4)
 *   A broken overlay draws over the dome and under the ship, the front
 *   missiles and the explosions; a missile behind the dome stays hidden by
 *   it.
 *
 *   C ROM range: BROKEN_TILE_BASE comes from build/broken_map.h (7096:
 *   right after the 2/3 missile and explosion sheets; the Makefile
 *   concatenates the parts back to back, so the number follows the art).
 *   The art is 4,693 tiles (7,909 stones packed), PACKED in the runtime's
 *   fetch order: per (cell, view) picture, its w x h stones are
 *   consecutive tiles,
 *   picture = BROKEN_TILE_BASE + broken_tile0[cell] +
 *   broken_view_t0[cell][view], stone (r, c) = picture + r * w + c.
 *   render_broken.py emits broken.c1/c2 in exactly this order (~0.30 MB),
 *   so CROMSIZE comes back down to 1 MB per chip (the plan: "put CROMSIZE
 *   back as low as the data allows"). Only the 48 views are stored: the
 *   dome's 5-fold symmetry maps (cell, dome_angle = q*48 + r) to
 *   (broken_perm^q(cell), view r).
 *
 *   Leftovers: the stones are never shrunk, so the hardware draws each as
 *   a full 16x16 tile and the M3/M4 "rows below the picture" reach does
 *   not exist (a full-size sprite has no shrink to leave a tail). Every
 *   stone of a shown picture is written every frame; a hidden cell's run
 *   gets SCB3 height 0.
 *
 *   Placement: broken_cell[cell][view] gives the picture's w/h (stones)
 *   and canvas x/y (dome-box px, the top-left of the full-size stones),
 *   and the runtime draws the stones at that offset: the overlay covers
 *   the cell exactly as the art does (tests/test_broken_geometry.py proves
 *   the art covers the cell's visible area in the dome picture).
 */
#ifndef CRACKS_H
#define CRACKS_H
#include <ngdevkit/neogeo.h>
#include "rules.h"
#include "broken_map.h"
#include "dome.h"
#include "mis_gfx.h"
#include "ship_gfx.h"
#include "slots.h"

#define PAL_BROKEN 6     /* the overlays' palette bank (6 was the cracks') */

typedef struct broken_place {
    u16 tile;                  /* C ROM tile: the picture's first stone */
    u8 w, h;                   /* stones wide / tall */
    s16 x, y;                  /* top-left in the dome box (canvas offset) */
} broken_place_t;

/* the pure half (host-testable, no hardware): what a cell's overlay at a
 * dome view must hold, from the tables. The caller maps a dome_angle to an
 * art cell and view through broken_perm first (see cracks.c). */
void broken_place(u8 cell, u8 view, broken_place_t *out);

void cracks_init(void);
/* once per frame, after mis_gfx_show: draw a broken window over every
 * broken cell that faces the camera, with the dome at dome_angle
 * (0..239). The cells come from the broken order in r (the same list the
 * collapse uses). Hidden on the collapse's frames and under a
 * game-ending dome death's GAME OVER (dome.h's dome_draw_gone). */
void cracks_show(const rules_t *r, u8 dome_angle);
void cracks_show_empty(void);
#endif
