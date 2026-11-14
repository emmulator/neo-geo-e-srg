/* ship_gfx.c: see ship_gfx.h. The ship is never shrunk, so its two columns
 * are a sticky chain; a new latitude rewrites their SCB1 tiles, the lift
 * only moves the chain's Y. */
#include <ngdevkit/neogeo.h>
#include "ship_gfx.h"
#include "dome.h"
#include "ship_map.h"

static const u16 ship_pal[16] =
#include "assets/ship.pal"
;

static u8 shown_lat = 255;

void ship_gfx_init(void)
{
    u8 i, c;

    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_SHIP * 16 + i] = ship_pal[i];
    MMAP_PALBANK1[PAL_SHIP * 16] = 0x8000;       /* entry 0: transparent */

    *REG_VRAMMOD = 0x200;                         /* SCB2 -> SCB3 -> SCB4 */
    for (c = 0; c < SHIP_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB2 + SHIP_SPRITE + c;
        *REG_VRAMRW = 0x0fff;                     /* full size */
        if (c == 0) {
            *REG_VRAMRW = (u16)(((496 - DOME_Y) << 7) | SHIP_ROWS);   /* ship_gfx_show sets Y */
            *REG_VRAMRW = (u16)((DOME_X + SHIP_OX) << 7);
        } else {
            *REG_VRAMRW = 1 << 6;                 /* sticky: follows column c-1 */
            /* the sticky column's own SCB4 is read by nothing (it inherits
             * the driver's X), but write its box X anyway, like the dome:
             * the VRAM then holds the whole ship deterministically, so the
             * respawn boot-test can prove "the respawned ship's VRAM words
             * equal the start of the game's" word for word (an un-written
             * SCB4 would carry whatever the BIOS init left in VRAM — a
             * value the test could only accidentally agree on). */
            *REG_VRAMRW = (u16)((DOME_X + SHIP_OX + (s16)c * 16) << 7);
        }
    }
    shown_lat = 255;
}

void ship_gfx_show(u8 lat, u8 lift)
{
    u8 c, r;
    s16 y = (s16)(DOME_Y + ship_oy[lat] - lift);

    if (lat != shown_lat) {
        *REG_VRAMMOD = 1;
        for (c = 0; c < SHIP_COLS; c++) {
            *REG_VRAMADDR = ADDR_SCB1 + (SHIP_SPRITE + c) * 64;
            for (r = 0; r < SHIP_ROWS; r++) {
                *REG_VRAMRW = ship_tile[lat][c][r];
                *REG_VRAMRW = (u16)(PAL_SHIP << 8);
            }
        }
        shown_lat = lat;
    }
    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = ADDR_SCB3 + SHIP_SPRITE;
    *REG_VRAMRW = (u16)(((496 - y) << 7) | SHIP_ROWS);
}

/* the centre of the ship's 2 x 2-tile picture at rest (no lift) at view
 * lat: where its death explosion goes (e-srg.c kill_ship: explode_at the
 * ship's spot) */
void ship_gfx_centre(u8 lat, s16 *x, s16 *y)
{
    *x = (s16)(DOME_X + SHIP_OX + SHIP_COLS * 8);
    *y = (s16)(DOME_Y + ship_oy[lat] + SHIP_ROWS * 8);
}

/* hide the ship (SCB3 height 0): the Vectrex stops drawing it while it is
 * dead (e-srg.c: if (!dead_t && !game_over) ship_draw). The rows below the
 * 2-tall picture are blanked on every show, so nothing lingers there.
 * Only the sticky chain's DRIVER is hidden (SCB3 = 0 on column 0): the
 * follower's SCB3 (the sticky bit 1<<6 and inherited height) is left
 * intact, so the chain survives the hide and the ship comes back whole.
 * (Zeroing the follower too would clear its sticky bit; a later show
 * rewrites only the driver's SCB3, and the follower would stay a
 * non-sticky sprite with height 0 — the "only the left half" bug.) */
void ship_gfx_hide(void)
{
    if (shown_lat != 255) {
        *REG_VRAMMOD = 1;
        *REG_VRAMADDR = ADDR_SCB3 + SHIP_SPRITE;
        *REG_VRAMRW = 0;
        shown_lat = 255;                     /* force a full redraw on show */
    }
}
