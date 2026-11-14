/* mountains.c: see mountains.h. The band is a sticky chain of MTN_SHOWN
 * full-size 16-px columns at y MTN_Y, MTN_ROWS tiles tall, in palette bank
 * PAL_MTN (9); the tiles come from the mountain part of the C ROM, right
 * after the ground's. Per frame nothing is written but the driver's X
 * (SCB4), except on a frame where the panorama column window changed (or
 * on a show), when the 21 columns' SCB1 tiles are rewritten.
 */
#include <ngdevkit/neogeo.h>
#include "mountains.h"

/* s = da * 960 / 240 = 4 * da (0..956): 960 px is one full turn of the
 * dome, so every step is exactly 4 px and there is no rounding and no
 * divide (tests/mountains_model.py holds it for all 240). 4*239 = 956
 * fits a u16. */
#define MTN_SCROLL(da) ((u16)((u8)(da) << 2))

/* the panorama column window the columns last showed (s >> 4, 0..59;
 * 0xff = never, so the first show/rewrite draws everything) */
static u8 mtn_win = 0xff;

/* write chain column k's MTN_ROWS SCB1 tile words for panorama column p */
static void column_tiles(u8 k, u8 p)
{
    u8 r;
    u16 base = (u16)(MTN_TILE_BASE + p * MTN_ROWS);

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB1 + (MTN_SPRITE + k) * 64);
    for (r = 0; r < MTN_ROWS; r++) {
        *REG_VRAMRW = (u16)(base + r);              /* tile */
        *REG_VRAMRW = (u16)(PAL_MTN << 8);          /* palette, no flip */
    }
}

/* write the chain's SCB2/SCB3: the driver's Y (MTN_ROWS tiles tall) and the
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
    *REG_VRAMADDR = (u16)(ADDR_SCB2 + MTN_SPRITE);
    *REG_VRAMRW = 0x0fff;                            /* driver: full size */
    *REG_VRAMRW = (u16)(((496 - MTN_Y) << 7) | MTN_ROWS);
    for (k = 1; k < MTN_SHOWN; k++) {
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + MTN_SPRITE + k);
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
    *REG_VRAMADDR = (u16)(ADDR_SCB4 + MTN_SPRITE);
    *REG_VRAMRW = (u16)((ph ? (512 - ph) : 0) << 7);
}

void mountains_show(u8 dome_angle)
{
    u8 i;

    /* the palette bank: the mountains' own colours */
    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_MTN * 16 + i] = mtn_pal[i];

    /* the sticky chain (after a hide cleared the followers' sticky bits
     * and left stale SCB2 zoom in the slots): driver Y/height/full size,
     * every follower sticky and full size */
    place_chain();
    mtn_win = 0xff;                 /* force the columns' SCB1 rewrite */
    mountains_frame(dome_angle);    /* SCB1 tiles for this angle + the X */
}

void mountains_hide(void)
{
    u8 c;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + MTN_SPRITE);
    for (c = 0; c < MTN_SHOWN; c++)
        *REG_VRAMRW = 0;                         /* height 0: not drawn */
    mtn_win = 0xff;                 /* a later show rewrites the columns */
}

void mountains_frame(u8 dome_angle)
{
    u16 s = MTN_SCROLL(dome_angle);
    u8 win = (u8)(s >> 4);
    u8 k;

    if (win != mtn_win) {
        /* the panorama column window changed: rewrite every column's SCB1
         * (a conditional subtract is the mod 60 — never a %) */
        mtn_win = win;
        for (k = 0; k < MTN_SHOWN; k++) {
            u8 p = (u8)(win + k);
            if (p >= MTN_COLS)
                p = (u8)(p - MTN_COLS);
            column_tiles(k, p);
        }
    }
    /* every frame: the driver's X alone (one divu.w for s above); a window
     * change frame is 126 SCB1 words + this one */
    place_x(s);
}
