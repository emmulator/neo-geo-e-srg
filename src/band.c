/* band.c: see band.h. The band is a sticky chain of BAND_SHOWN full-size
 * 16-px columns at y BAND_Y, BAND_ROWS tiles tall, in palette bank PAL_BAND
 * (12); the tiles come from the band part of the C ROM, right after the
 * props'. Per frame nothing is written but the driver's X (SCB4), except on
 * a frame where the panorama column window changed (or on a show), when the
 * 21 columns' SCB1 tiles are rewritten.
 */
#include <ngdevkit/neogeo.h>
#include "band.h"

/* s = round(da * 768 / 240) = (16 * da + 2) / 5 (0..765): 768 px is one
 * full turn of the dome, and 768/240 = 3.2 never lands on a half step, so
 * the integer division equals round() for all 240 angles
 * (tests/band_model.py holds it for all of them). 16*239 + 2 = 3826 fits a
 * u16, so the numerator is kept in a u16: gcc then strength-reduces the
 * constant /5 to one 16-bit mulu.w (objdump: no __divsi3/__udivsi3 call;
 * without the cast the signed 32-bit divide became a __divsi3 call). */
#define BAND_SCROLL(da) ((u16)(((u16)(16 * (u8)(da) + 2)) / 5))

/* the panorama column window the columns last showed (s >> 4, 0..47;
 * 0xff = never, so the first show/rewrite draws everything) */
static u8 band_win = 0xff;

/* write chain column k's BAND_ROWS SCB1 tile words for panorama column p */
static void column_tiles(u8 k, u8 p)
{
    u8 r;
    u16 base = (u16)(BAND_TILE_BASE + p * BAND_ROWS);

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB1 + (BAND_SPRITE + k) * 64);
    for (r = 0; r < BAND_ROWS; r++) {
        *REG_VRAMRW = (u16)(base + r);              /* tile */
        *REG_VRAMRW = (u16)(PAL_BAND << 8);         /* palette, no flip */
    }
}

/* write the chain's SCB2/SCB3: the driver's Y (BAND_ROWS tiles tall) and the
 * full-size zoom for EVERY column. The followers inherit Y, height and
 * vertical zoom from the driver (sticky), but NOT the horizontal zoom
 * (each sticky sprite has its own SCB2 hzoom): they must be written full
 * size too, never left at whatever a previous user of the slot wrote.
 * Column c sits at the driver's X + 16c. Called on a show only: a hide
 * clears SCB3 (and the followers' sticky bit), so the show re-establishes
 * it; nothing else touches these words while the band is up, so a window
 * change does not need them. */
static void place_chain(void)
{
    u8 k;

    *REG_VRAMMOD = 0x200;
    *REG_VRAMADDR = (u16)(ADDR_SCB2 + BAND_SPRITE);
    *REG_VRAMRW = 0x0fff;                            /* driver: full size */
    *REG_VRAMRW = (u16)(((496 - BAND_Y) << 7) | BAND_ROWS);
    for (k = 1; k < BAND_SHOWN; k++) {
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + BAND_SPRITE + k);
        *REG_VRAMRW = 0x0fff;                        /* follower: full size */
        *REG_VRAMRW = 1 << 6;                        /* sticky: Y/height from
                                                      * the driver */
    }
}

/* every frame only: the driver's X from the scroll phase */
static void place_x(u16 s)
{
    u16 ph = (u16)(s & 15);

    *REG_VRAMMOD = 0;
    *REG_VRAMADDR = (u16)(ADDR_SCB4 + BAND_SPRITE);
    *REG_VRAMRW = (u16)((ph ? (512 - ph) : 0) << 7);
}

void band_show(u8 dome_angle)
{
    u8 i;

    /* the palette bank: the band's own colours */
    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_BAND * 16 + i] = band_pal[i];

    /* the sticky chain (after a hide cleared the followers' sticky bits
     * and left stale SCB2 zoom in the slots): driver Y/height/full size,
     * every follower sticky and full size */
    place_chain();
    band_win = 0xff;                 /* force the columns' SCB1 rewrite */
    band_frame(dome_angle);          /* SCB1 tiles for this angle + the X */
}

void band_hide(void)
{
    u8 c;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + BAND_SPRITE);
    for (c = 0; c < BAND_SHOWN; c++)
        *REG_VRAMRW = 0;                         /* height 0: not drawn */
    band_win = 0xff;                 /* a later show rewrites the columns */
}

void band_frame(u8 dome_angle)
{
    u16 s = BAND_SCROLL(dome_angle);
    u8 win = (u8)(s >> 4);
    u8 k;

    if (win != band_win) {
        /* the panorama column window changed: rewrite every column's SCB1
         * (a conditional subtract is the mod 48 — never a %) */
        band_win = win;
        for (k = 0; k < BAND_SHOWN; k++) {
            u8 p = (u8)(win + k);
            if (p >= BAND_COLS)
                p = (u8)(p - BAND_COLS);
            column_tiles(k, p);
        }
    }
    /* every frame: the driver's X alone (the 16-bit scroll above); a
     * window change frame is 84 SCB1 words + this one */
    place_x(s);
}
