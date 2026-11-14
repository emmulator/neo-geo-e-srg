/* radar_gfx.c: see radar_gfx.h. The drawing is table-index-only arithmetic
 * (16-bit; no divide, no libgcc — checked with objdump), so the per-frame
 * cost is a handful of VRAM words per blip. */
#include <ngdevkit/neogeo.h>
#include "radar_gfx.h"

/* The heading's vertical zoom: the smallest vertical byte whose box draws
 * exactly `dy` screen lines, all sampling SCB1 row 0 (the heading's only
 * picture row) — from the "000-lo.lo" table (tools/render_radar.py's
 * _VZ_FOR_DY; the art is solved against the very same bytes). Index 0 is
 * the horizontal case (1 line). */
static const u8 radar_head_vz[17] = {
    1, 1, 17, 33, 49, 65, 81, 97, 113, 129, 145, 161, 177, 193, 209, 225, 241
};

/* the absolute value of an s16 (the heading spans are small: |dx|, |dy|
 * <= 16), without calling abs/__abs */
static s16 iabs16(s16 n)
{
    return (s16)(n < 0 ? (s16)(0 - (u16)n) : n);
}

void radar_gfx_init(void)
{
    u8 c, r, s;

    MMAP_PALBANK1[RADAR_PAL_BANK * 16 + 1] = radar_pal[1];

    /* ---- the frame: 4 slots, one 16-px column each, 2 tiles tall ----
     * The columns sit side by side at x = CX-32 + c*16, y = CY-16; the
     * picture's tiles are row-major in the C ROM (tile r*4+c). Never
     * shrunk, so SCB2 stays 0x0fff; SCB3/SCB4 are fixed too. */
    for (c = 0; c < RADAR_FRAME_SLOTS; c++) {
        s = (u8)(RADAR_SPRITE + c);
        *REG_VRAMMOD = 1;
        *REG_VRAMADDR = (u16)(ADDR_SCB1 + s * 64);
        for (r = 0; r < 2; r++) {
            *REG_VRAMRW = (u16)(RADAR_FRAME_TILE_BASE + r * 4 + c);
            *REG_VRAMRW = (u16)(RADAR_PAL_BANK << 8);
        }
        for (; r < 32; r++) {              /* blank below the picture */
            *REG_VRAMRW = 0;
            *REG_VRAMRW = (u16)(RADAR_PAL_BANK << 8);
        }
        *REG_VRAMMOD = 0x200;
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + s);
        *REG_VRAMRW = 0x0fff;              /* full size, never shrunk */
        *REG_VRAMRW = (u16)((u16)((u16)(496 - (RADAR_CY - 16)) << 7) | 2);
        *REG_VRAMRW = (u16)((u16)(RADAR_CX - 32 + c * 16) << 7);
    }

    /* ---- the sticks and headings: SCB2 and SCB3, hidden for now ----
     * The stick slots' SCB2 is full size (a stick is never shrunk; SCB2 is
     * the horizontal nibble + vertical byte, and a zero vertical byte would
     * make the stick invisible); the heading slots' SCB2 is written per
     * frame (it carries the shrink). Here every radar slot that is not a
     * frame starts hidden (SCB3 0). */
    *REG_VRAMMOD = 0x200;
    for (s = RADAR_FRAME_SLOTS; s < RADAR_COUNT; s += 5) {   /* the stick slots */
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + RADAR_SPRITE + s);
        *REG_VRAMRW = 0x0fff;            /* full size, never shrunk */
    }
    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + RADAR_SPRITE + RADAR_FRAME_SLOTS);
    for (s = RADAR_FRAME_SLOTS; s < RADAR_COUNT; s++)
        *REG_VRAMRW = 0;
}

static void hide(u8 s)
{
    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + s);
    *REG_VRAMRW = 0;
}

/* the stick's SCB1 column (rows 0..2 = the 3 picture tiles, 3..31 left as
 * the init wrote them — the stick is never shrunk, so only rows 0..2 are
 * ever sampled; the leftover plant covers only the shrinking heading
 * slots). The tile is the picture for height h, thin or locked-wide.
 * The picture's line is at art columns 7 (thin) or 7..8 (wide), so the
 * sprite's X is sx - 7: the line's foot lands exactly on the spot. */
static void stick_scb1(u8 s, u8 h, u8 wide)
{
    u16 tile = (u16)(RADAR_STICK_TILE_BASE + (2 * h + wide) * 3);
    u8 r;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB1 + s * 64);
    for (r = 0; r < 3; r++) {
        *REG_VRAMRW = (u16)(tile + r);
        *REG_VRAMRW = (u16)(RADAR_PAL_BANK << 8);
    }
    *REG_VRAMMOD = 0x200;
}

/* the heading's SCB1 column: row 0 = the picture tile (with the h-flip the
 * art was solved for, the SCB1 attribute's bit 0 — the hardware flips the
 * tile in place), rows 1..31 blank (the vertical zoom samples rows below
 * the picture when its box line count is below 16 — see the fractional
 * fragment comment in mis_gfx.c — so the blanking is unconditional, and it
 * is what keeps the leftover boot-test's planted garbage out). */
static void head_scb1(u8 s, u16 tile, u8 hflip)
{
    u8 r;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB1 + s * 64);
    *REG_VRAMRW = tile;
    *REG_VRAMRW = (u16)((RADAR_PAL_BANK << 8) | hflip);
    for (r = 1; r < 32; r++) {
        *REG_VRAMRW = 0;
        *REG_VRAMRW = (u16)(RADAR_PAL_BANK << 8);
    }
    *REG_VRAMMOD = 0x200;
}

/* one blip's stick and heading, and the ellipse's blink entry. */
static void show_blip(const radar_blip_t *b, u8 stick_slot, u8 head_slot)
{
    /* ---- the stick: the line's foot is the spot (sx, sy) ----
     * The picture is RADAR_STICK_H (48) px tall and the line ends at its
     * bottom row, so the sprite's top is (sx, sy - 48) and the box height
     * is 3 (48 screen lines). No shrink. The line is at art column 7, so
     * the sprite's X is sx - 7 (thin and wide alike: their art fills
     * columns 7..8, whose centre is column 7.5 — within the task's 1-px
     * bound of the spot either way). */
    s16 sy = b->sy;
    u16 y = (u16)(496 - (sy - RADAR_STICK_H));

    stick_scb1(stick_slot, b->h, b->locked);
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + stick_slot);
    *REG_VRAMRW = (u16)((u16)(y << 7) | 3);
    *REG_VRAMRW = (u16)((u16)(b->sx - 7) << 7);

    /* ---- the heading: from the stick's top toward the centre ----
     * top = (sx, sy - h); the heading ends at (hx, hy). dx/dy are the
     * signed px deltas (|dx|, |dy| <= 16). The pre-rendered tile is
     * solved so that, drawn with SCB2 hz = |dx|-1, vz = the byte that
     * draws |dy| lines, and hflip = (sdx<0) XOR (sdy<0), the lit pixels
     * form a 1-px staircase from one box corner to the opposite. The
     * runtime places the box so the corner the staircase STARTS at is the
     * stick's top:
     *
     *     +dx (line going right):  the start is the box's LEFT column;
     *     -dx:                     the RIGHT column (set X = top.x - dx+1);
     *     +dy (going down):        the start is the box's TOP line;
     *     -dy (going up):          the box's BOTTOM is the top (the drawn
     *                              staircase's top is the heading's END,
     *                              so the box's top line sits at hy);
     *
     * which this single formula covers (the verified placement):
     *
     *     Bx = (sdy >= 0 ? top.x : hx) - (hflip ? dx-1 : 0)
     *     By = (sdy >= 0 ? top.y : hy)
     *
     * The drawn line's endpoints end up within 1 px of (top) and (hx, hy)
     * (the boot-test's bound), and the box never leaves the screen. */
    {
        s16 tx = b->sx;
        s16 ty = (s16)(b->sy - b->h);
        s16 adx = iabs16((s16)(b->hx - tx));
        s16 ady = iabs16((s16)(b->hy - ty));
        u8 hf, hz;

        if (adx == 0 && ady == 0) {      /* the top IS the centre: no line */
            hide(head_slot);
            return;
        }
        hf = (u8)(((b->hx < tx) ^ (b->hy < ty)) ? 1 : 0);
        hz = (u8)(adx ? (u16)(adx - 1) : 0);
        {
            s16 bx = (b->hy >= ty ? tx : b->hx);
            s16 by = (b->hy >= ty) ? ty : b->hy;
            u16 tile = (u16)(RADAR_HEAD_TILE_BASE
                             + (u16)((u16)((u16)ady * (RADAR_HEAD_MAX + 1)
                                           + (u16)adx) * 2 + hf));

            if (hf && adx)
                bx = (s16)(bx - (adx - 1));
            head_scb1(head_slot, tile, hf);
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + head_slot);
            *REG_VRAMRW = (u16)(((u16)hz << 8) | radar_head_vz[ady]);
            *REG_VRAMRW = (u16)(((u16)(496 - by) << 7) | 1);
            *REG_VRAMRW = (u16)((u16)bx << 7);
        }
    }
}

void radar_gfx_show(const radar_t *radar)
{
    u8 i;

    /* the ellipse's palette entry: the only per-frame palette write, the
     * blink (dim while not locked, then bright every RADAR_BLINK-th
     * locked frame). */
    MMAP_PALBANK1[RADAR_PAL_BANK * 16 + 1] =
        radar->ellipse_bright ? radar_pal_bright : radar_pal[1];

    for (i = 0; i < NMIS; i++) {
        const radar_blip_t *b = &radar->blip[i];
        u8 stick = (u8)(RADAR_SPRITE + RADAR_FRAME_SLOTS + i * 5);
        u8 head = (u8)(stick + 1);

        if (!b->shown) {                 /* hidden this frame: both slots 0 */
            hide(stick);
            hide(head);
            continue;
        }
        show_blip(b, stick, head);
        /* the missile's 3 other reserved heading slots stay hidden (they
         * are never written here; SCB3 was 0 since init) */
    }
}
