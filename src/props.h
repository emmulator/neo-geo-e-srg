/* props.h: the trees and rocks on the grass (dome-scenery Task 12; split
 * into two pools by Task 15) — the 22 props of tools/render_props.py,
 * placed by src/props_layout.c's props_layout() and written to VRAM here.
 *
 * Two pools (src/slots.h):
 *   - the BACK pool at PROP_SPRITE .. + PROP_BACK_COUNT, right after the
 *     mountains and before the missiles behind the dome: every prop whose
 *     foot is behind the dome's centre, drawn over the grass and the
 *     mountains and under everything else;
 *   - the FRONT pool at PROP_FRONT_SPRITE .. + PROP_FRONT_COUNT, right
 *     after the broken overlays and before the ship: a near prop in front
 *     of the dome's centre whose crown or stone covers the dome on screen
 *     (the generator's prop_front), drawn over the dome and its overlays
 *     and under the ship, the console, the front missiles, the explosions
 *     and the radar.
 * A prop that changes pool leaves its old pool slot hidden (SCB3 0).
 *
 * Each prop owns one palette bank, PROP_PAL_BANK + i (banks 22..43; 0..11,
 * 20 and 21 are taken), and its sprite columns are independent (their X
 * positions come from props_layout; a sticky chain's 16 px stride cannot
 * express the props' shrink).
 *
 * The props part's tiles follow the console's in the assembled C ROM (the
 * Makefile's CROM1_PARTS/CROM2_PARTS order: ..., mountains, console, props),
 * so its first tile is CON_TILE_BASE + CON_TILES. The generated header's
 * tile numbers are relative to this part; the runtime adds the base.
 *
 * props_show loads every prop's bank with prop_pal[i][0], puts the runtime
 * shadow rows (entries 1 and 13) in and draws both pools' first frame with
 * the dome whole — outside a play frame, so it writes at once.
 * props_prepare runs every play frame where mountains_frame runs, with
 * dome_whole = dome_is_whole(&rules), and computes the SCB1 tiles (only for
 * a slot whose (prop, LOD, column) changed), SCB2/3/4 (only for a slot in
 * use whose placement changed, and SCB3 0 for the slots that just stopped)
 * and each shown prop's palette into RAM. props_layout is a pure function
 * of the dome angle, so a frame at the same angle AND the same whole/gone
 * state as the last one prepares nothing at all. The palette is the variant
 * d = dome_whole && prop_dark[i][da] (prop_pal[i][d], entries 1 and 13 from
 * prop_shadow[d][y]) — the whole bank when d changes, entries 1/13 when d or
 * the foot row changes. props_commit then writes the prepared changes and
 * is called right after ng_wait_vblank on every play frame, so no tree is
 * rewritten while the raster is inside it (Task 18). props_hide zeroes
 * every slot of both pools' SCB3 (the title) and writes at once.
 */
#ifndef PROPS_H
#define PROPS_H
#include <ngdevkit/types.h>
#include "slots.h"            /* PROP_SPRITE/BACK_COUNT, PROP_FRONT_* */
#include "console.h"          /* CON_TILE_BASE, CON_TILES */
#include "props_layout.h"     /* props_layout(), prop_slot_t + props_map.h */

/* the next free palette bank after the radar's 21: one bank per prop */
#define PROP_PAL_BANK 22

/* the props part's first tile in the assembled C ROM: the Makefile emits
 * the C ROM parts in CROM1_PARTS / CROM2_PARTS order (dome, ship, missiles,
 * broken, radar's frame/sticks/headings, the ground, the mountains, the
 * console, then the props), so the props start exactly where the console's
 * CON_TILES end. */
#define PROP_TILE_BASE (CON_TILE_BASE + CON_TILES)

/* the most tile rows any prop picture has (the largest tree: 5 rows at
 * LOD 2). A prop column is at most 5 tiles tall (80 screen lines), and the
 * vertical zoom table (000-lo.lo) samples SCB1 rows 0..15 only for a box
 * that short (checked over every vz, 0..255), so rows below the picture
 * are blanked to row 15 and no leftover from an earlier, taller picture can
 * show under a shrunk prop. */
#define PROP_MAX_ROWS 5
#define PROP_SCB1_ROWS 16

/* once when a game begins (and after a hide): every prop's palette bank,
 * its shadow entries for this angle, and both pools' first layout. The
 * generator's rounding tables are built on the first props_layout call,
 * which happens here — never in a play frame. */
void props_show(u8 dome_angle);

/* hide every slot of both pools (SCB3 height 0) — the title, and at every
 * entry. */
void props_hide(void);

/* once per play frame, next to mountains_frame: props_layout(da), the slot
 * words/tiles and the palette variant (dome_whole = dome_is_whole(rules))
 * prepared into RAM, with no VRAM or palette writes. */
void props_prepare(u8 dome_angle, u8 dome_whole);

/* right after ng_wait_vblank on every play frame: write what props_prepare
 * prepared (only the words that changed). */
void props_commit(void);
#endif
