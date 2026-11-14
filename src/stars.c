/* stars.c: see stars.h. Pure half first (stars_pos), then the drawing. */
#include <ngdevkit/neogeo.h>
#include "stars.h"

/* the table's real length momentarily differs from NSTARS only in the
 * -DNSTARS=16 renumbering proof build (Task 1): the stars' lowest-slot
 * block then spans 16 slots, of which the first STARS_COUNT are drawn and
 * the rest stay hidden. A runtime guard on the index keeps every consumer
 * (stars_pos, stars_init, stars_show) within the table whatever NSTARS
 * the build used. */
#define STARS_USED ((NSTARS) < (STARS_COUNT) ? (NSTARS) : (STARS_COUNT))

/* the drift per dome_angle step. da*320/240 = da*4/3, whose exact half
 * never occurs (multiples of 3 in 0..239 give exactly multiples of 4), so
 * round-half-up is (da*320 + 120) / 240 = (8*da + 3) / 6 for every step —
 * the C round() and the Python model agree on this (tests/stars_model.py).
 * The drift reaches 318 (da 239), so it must be u16, not u8. Kept in 16
 * bits on purpose: a u32 divide is a libgcc call, and with a % 320 on top
 * it cost ~21 scanlines a frame for the 12 stars (worst frame 146 -> 167);
 * 8*239+3 fits a u16, so this is one native divu.w. */
#define DRIFT(da) ((u16)((u16)((u16)(da) * 8 + 3) / 6))

void stars_pos(u8 i, u8 dome_angle, u16 *x, u8 *y)
{
    if (i >= STARS_USED) {           /* the -DNSTARS=16 proof's spare slots */
        *x = 0;
        *y = 0;
        return;
    }
    /* +320 first: x0 - drift can be negative; the sum is 0..638, so one
     * conditional subtract is the mod 320 (no divide) */
    u16 sx = (u16)(star_x0[i] + 320 - DRIFT(dome_angle));
    *x = sx >= 320 ? (u16)(sx - 320) : sx;
    *y = star_y[i];
}

/* ---- drawing ------------------------------------------------------ */

/* the star tile and palettes come from the generated map. The tile is one
 * 16x16 tile with a 2x2 dot at its top-left (colour index 1) — putting the
 * dot at the top-left makes the sprite's X and Y the dot's, so a probe
 * that reads SCB4>>7 and 496-(SCB3>>7) gets the star's own position. */
void stars_init(void)
{
    u8 i;

    for (i = 0; i < STARS_USED; i++) {
        MMAP_PALBANK1[(STAR_PAL_BASE + i) * 16 + 1] = star_pal[1];
        *REG_VRAMMOD = 1;
        *REG_VRAMADDR = (u16)(ADDR_SCB1 + (STAR_SPRITE + i) * 64);
        *REG_VRAMRW = STAR_TILE_BASE;                       /* the dot tile */
        *REG_VRAMRW = (u16)((STAR_PAL_BASE + i) << 8);      /* its palette */
        *REG_VRAMMOD = 0x200;
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + STAR_SPRITE + i);
        *REG_VRAMRW = 0x0fff;                    /* full size, never shrunk */
        *REG_VRAMRW = 0;                         /* hidden: the first stars_show places them */
        *REG_VRAMRW = (u16)((u16)star_x0[i] << 7);   /* the rest position */
    }
}

/* once per frame. Every star is one sprite: write its Y (SCB3 height 1:
 * the LSPC draws 16 screen lines and the zoom table samples SCB1 row 0 —
 * the dot tile; rows 1..31 of the column were never written, so they are
 * tile 0, fully transparent) and its X (SCB4). */
void stars_show(u8 dome_angle)
{
    u8 i;

    *REG_VRAMMOD = 0x200;
    for (i = 0; i < STARS_USED; i++) {
        u16 x;
        u8 y;
        u16 slot = (u16)(STAR_SPRITE + i);

        stars_pos(i, dome_angle, &x, &y);
        *REG_VRAMADDR = (u16)(ADDR_SCB3 + slot);
        *REG_VRAMRW = (u16)(((u16)(496 - y) << 7) | 1);     /* height 1 */
        *REG_VRAMRW = (u16)(x << 7);
    }
    /* the spare slots of an -DNSTARS=16 block stay hidden (the block now
     * spans more than the table): SCB3 height 0, so they draw nothing. */
    for (; i < NSTARS; i++) {
        *REG_VRAMADDR = (u16)(ADDR_SCB3 + STAR_SPRITE + i);
        *REG_VRAMRW = 0;
    }
}

void stars_hide(void)
{
    u8 i;

    *REG_VRAMMOD = 1;                   /* consecutive SCB3 words */
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + STAR_SPRITE);
    for (i = 0; i < NSTARS; i++)
        *REG_VRAMRW = 0;
}
