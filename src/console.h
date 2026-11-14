/* console.h: the console across the bottom (dome-scenery Task 7) — a dark
 * control panel that runs the screen's width, angled up beside the dome,
 * from tools/render_console.py (the orchestrator's art, never edited for the
 * picture or palette here).
 *
 * The picture is CON_COLS (20) 16-px columns. Each column is its OWN sprite,
 * never a sticky chain: the wings' columns (0..5 and 13..19) start at
 * con_top 176 and are 3 tiles tall, the strip under the dome (6..12) starts
 * at con_top 192 and is 2 tiles tall, and every column ends at y 223. A
 * sticky chain can only carry one Y and one height, so it cannot express the
 * step between the wings and the strip (the strip would start at the wings'
 * y 176, one tile of stale picture above y 192). Column c sits at x 16c.
 *
 * The palette bank is PAL_CON (10), holding con_pal. The panel covers the fix
 * rows of the HUD (rows 26 and 28); the fix layer always draws over sprites,
 * so the text stays on top.
 *
 * The slots (src/slots.h) put the console right after the ship and before the
 * front missiles: it draws over the grass, the mountains, the dome, its
 * overlays and the ship, and UNDER the front missiles, the explosions and the
 * radar (missiles fly in from in front of the camera, across the bottom of
 * the screen; the console must never hide one).
 *
 * console_show writes every column once when a game begins; nothing here is
 * per frame. console_hide zeroes every column's SCB3 (height 0) on the title
 * and at every entry — the panel covers the bottom of the screen, so it must
 * not show there.
 */
#ifndef CONSOLE_H
#define CONSOLE_H
#include <ngdevkit/types.h>
#include "slots.h"            /* CON_SPRITE, CON_COUNT */
#include "console_map.h"      /* CON_COLS/TILES + con_top/rows/first/pal (build) */
#include "mountain_map.h"     /* MTN_TILES: the console part follows it */
#include "radar_map.h"        /* RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES */
#include "ground_map.h"       /* GROUND_TILES */

/* the next free palette bank after PAL_MTN 9 (the radar owns 20) */
#define PAL_CON 10

/* the console part's first tile in the assembled C ROM: the Makefile emits
 * the C ROM parts in CROM1_PARTS / CROM2_PARTS order (dome, ship, missiles,
 * broken, radar's frame/sticks/headings, the ground, the mountains, then the
 * console), so the console starts exactly where the mountains' MTN_TILES
 * end. The header's con_first[c] numbers are relative to this part; every
 * fetch below adds this base. */
#define CON_TILE_BASE (RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES + GROUND_TILES \
                       + MTN_TILES)

/* once when a game begins (after a hide): every column's SCB1 tiles (the
 * part base plus con_first[c]), SCB2 full size, its own SCB3 (top
 * con_top[c], con_rows[c] tiles tall, sticky bit clear) and SCB4 (x 16c),
 * plus the palette bank holding con_pal. */
void console_show(void);

/* hide every column (SCB3 height 0) — the title, and a fresh entry before
 * any game has begun. */
void console_hide(void);
#endif
