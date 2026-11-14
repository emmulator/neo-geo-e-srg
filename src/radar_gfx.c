/* radar_gfx.c: see radar_gfx.h. The drawing is table-index-only arithmetic
 * (16-bit; no divide, no libgcc — checked with objdump), so the per-frame
 * cost is a handful of VRAM words per blip.
 *
 * Task 18b split the per-frame drawing in two. radar_gfx_prepare computes
 * the two dynamic slots of every blip (its stick and its heading) and the
 * ellipse's blink into RAM, with no VRAM or palette writes;
 * radar_gfx_commit writes only what changed right after ng_wait_vblank(),
 * with the missiles' and props' commits. The memo follows the props' rules:
 * a stick's three picture rows are rewritten only when its picture (h,
 * locked) changed; a heading's row 0 only when its tile or h-flip changed;
 * the heading's blank rows 1..31 once per slot since it was last hidden (a
 * "cleared" flag, so a planted/boot leftover cannot show below a shrunk
 * heading); SCB2/SCB3/SCB4 only when they changed; a slot that just stopped
 * being shown gets SCB3 0 once. The blink is one palette word written only
 * when it changes. radar_gfx_init and radar_gfx_hide still write directly
 * (they run outside play frames). */
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

/* the 6 slots the per-frame drawing changes: for each missile a stick and
 * the heading it owns (slot 0 of its 4 reserved heading slots). */
#define RADAR_DYN_SLOTS (NMIS * 2)

typedef struct {
    u8 shown;
    u8 rows;                    /* picture rows: 3 for a stick, 1 for a heading */
    u8 hflip;                   /* headings only */
    u16 tile;                   /* the picture's first tile */
    u16 scb2, scb3, scb4;
} radar_slot_t;

static radar_slot_t prev[RADAR_DYN_SLOTS];
static radar_slot_t pend[RADAR_DYN_SLOTS];
static u8 pic_list[RADAR_DYN_SLOTS];
static u8 place_list[RADAR_DYN_SLOTS];
static u8 stop_list[RADAR_DYN_SLOTS];
static u8 npic, nplace, nstop;
static u8 cleared[RADAR_DYN_SLOTS];

/* the blink's last prepared/written word (init writes the dim one) */
static u16 pal_last;
static u8 pal_dirty;

/* the absolute slot of dynamic index k: missile i's stick (2i) or its
 * heading (2i + 1) */
static u16 dyn_slot(u8 k)
{
    u8 i = (u8)(k >> 1);

    return (u16)(RADAR_SPRITE + RADAR_FRAME_SLOTS + i * 5 + (k & 1));
}

static void memo_clear(void)
{
    u8 k;

    for (k = 0; k < RADAR_DYN_SLOTS; k++) {
        prev[k].shown = 0;
        prev[k].rows = prev[k].hflip = 0;
        prev[k].tile = prev[k].scb2 = prev[k].scb3 = prev[k].scb4 = 0;
        cleared[k] = 0;
    }
    npic = nplace = nstop = 0;
    pal_dirty = 0;
}

void radar_gfx_init(void)
{
    u8 c, r, i;
    u16 s;

    /* ---- the two palette banks (Task 10) ----
     * Bank 20 holds all of radar_pal (1 the dim amber rim/roof, 2..4 the
     * disc); the lock-on blink rewrites only entry 1 of it. Bank 21 holds
     * radar_stick_pal (entry 1 the sticks'/headings' steady red-orange) and
     * is written once here — no per-frame write ever touches it, so the
     * sticks never blink. */
    for (i = 0; i < 5; i++)
        MMAP_PALBANK1[RADAR_PAL_BANK * 16 + i] = radar_pal[i];
    MMAP_PALBANK1[RADAR_STICK_PAL_BANK * 16 + 0] = radar_stick_pal[0];
    MMAP_PALBANK1[RADAR_STICK_PAL_BANK * 16 + 1] = radar_stick_pal[1];

    /* ---- the frame: 4 slots, one 16-px column each, 2 tiles tall ----
     * The columns sit side by side at x = CX-32 + c*16, y = CY-16; the
     * picture's tiles are row-major in the C ROM (tile r*4+c). Never
     * shrunk, so SCB2 stays 0x0fff; SCB3/SCB4 are fixed too. */
    for (c = 0; c < RADAR_FRAME_SLOTS; c++) {
        s = (u16)(RADAR_SPRITE + c);
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

    memo_clear();
    pal_last = radar_pal[1];             /* init wrote the dim blink entry */
}

void radar_gfx_hide(void)
{
    u16 s;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + RADAR_SPRITE);
    for (s = 0; s < RADAR_COUNT; s++)
        *REG_VRAMRW = 0;
    memo_clear();                        /* the next show writes full columns */
}

/* the stick's SCB1 column: rows 0..2 = the 3 picture tiles; rows 3..31 are
 * never sampled (the stick is full size, so the hardware reads exactly its
 * 3-tile box). The tile is the picture for height h, thin or locked-wide.
 * The picture's line is at art column 7 (thin) or 7..8 (wide), so the
 * sprite's X is sx - 7: the line's foot lands exactly on the spot. */
static void stick_cur(radar_slot_t *s, const radar_blip_t *b)
{
    s->shown = 1;
    s->rows = 3;
    s->hflip = 0;
    s->tile = (u16)(RADAR_STICK_TILE_BASE + (2 * b->h + b->locked) * 3);
    s->scb2 = 0x0fff;                    /* full size, never shrunk */
    s->scb3 = (u16)((u16)((u16)(496 - (b->sy - RADAR_STICK_H)) << 7) | 3);
    s->scb4 = (u16)((u16)(b->sx - 7) << 7);
}

/* one blip's heading into `s`; returns 0 when there is no line (the top IS
 * the centre), so the caller hides the heading slot. The placement formula
 * is the verified one from the old show_blip (see the task's heading notes):
 *
 *     Bx = (sdy >= 0 ? top.x : hx) - (hflip ? dx-1 : 0)
 *     By = (sdy >= 0 ? top.y : hy)
 *
 * The tile is RADAR_HEAD_TILE_BASE + (dy * (RADAR_HEAD_MAX+1) + dx) * 2 +
 * hflip; hz = |dx| - 1 (nibble), vz = radar_head_vz[|dy|]. */
static u8 head_cur(radar_slot_t *s, const radar_blip_t *b)
{
    s16 tx = b->sx;
    s16 ty = (s16)(b->sy - b->h);
    s16 adx = iabs16((s16)(b->hx - tx));
    s16 ady = iabs16((s16)(b->hy - ty));
    u8 hf, hz;

    if (adx == 0 && ady == 0)
        return 0;
    hf = (u8)(((b->hx < tx) ^ (b->hy < ty)) ? 1 : 0);
    hz = (u8)(adx ? (u16)(adx - 1) : 0);
    {
        s16 bx = (b->hy >= ty ? tx : b->hx);
        s16 by = (b->hy >= ty) ? ty : b->hy;

        s->shown = 1;
        s->rows = 1;
        s->hflip = hf;
        s->tile = (u16)(RADAR_HEAD_TILE_BASE
                        + (u16)((u16)((u16)ady * (RADAR_HEAD_MAX + 1)
                                      + (u16)adx) * 2 + hf));
        s->scb2 = (u16)(((u16)hz << 8) | radar_head_vz[ady]);
        s->scb3 = (u16)(((u16)(496 - by) << 7) | 1);
        if (hf && adx)
            bx = (s16)(bx - (adx - 1));
        s->scb4 = (u16)((u16)bx << 7);
    }
    return 1;
}

void radar_gfx_prepare(const radar_t *radar)
{
    radar_slot_t cur[RADAR_DYN_SLOTS];
    u8 i, k;
    u16 want;

    /* only the shown flag needs clearing: a hidden slot's other fields are
     * never read (the memo's compare tests `shown` first), and every shown
     * slot's fields are set by stick_cur/head_cur. */
    for (k = 0; k < RADAR_DYN_SLOTS; k++)
        cur[k].shown = 0;
    for (i = 0; i < NMIS; i++) {
        const radar_blip_t *b = &radar->blip[i];
        u8 stick = (u8)(i * 2);

        if (!b->shown)
            continue;                    /* both slots hidden */
        stick_cur(&cur[stick], b);
        head_cur(&cur[stick + 1], b);    /* returns 0: the slot stays hidden */
    }

    npic = nplace = nstop = 0;
    for (k = 0; k < RADAR_DYN_SLOTS; k++) {
        if (cur[k].shown) {
            if (!prev[k].shown || prev[k].tile != cur[k].tile
                || prev[k].hflip != cur[k].hflip
                || prev[k].rows != cur[k].rows) {
                pic_list[npic++] = k;
                pend[k] = cur[k];
            }
            if (!prev[k].shown || prev[k].scb2 != cur[k].scb2
                || prev[k].scb3 != cur[k].scb3
                || prev[k].scb4 != cur[k].scb4) {
                place_list[nplace++] = k;
                pend[k] = cur[k];
            }
        } else if (prev[k].shown) {
            stop_list[nstop++] = k;
            cleared[k] = 0;              /* the next show re-blanks the column */
            pend[k] = cur[k];
        }
        /* both hidden: prev is already hidden and its other fields are
         * never read, so skip the full struct copy */
        if (cur[k].shown || prev[k].shown)
            prev[k] = cur[k];
    }

    /* the blink: only when the blink word changes */
    want = radar->ellipse_bright ? radar_pal_bright : radar_pal[1];
    if (want != pal_last) {
        pal_dirty = 1;
        pal_last = want;
    }
}
/* write a shown slot's SCB1: the stick's 3 picture rows (its whole reachable
 * box), or a heading's row 0 plus its blank rows 1..31 on the first write
 * since the slot was hidden. A heading's picture is one row, so rows 1..31
 * can never hold a picture; blanking them clears boot/planted leftovers. */
static void write_tiles(const radar_slot_t *s, u8 *was_cleared)
{
    u16 attr = (u16)((RADAR_STICK_PAL_BANK << 8) | s->hflip);
    u8 r;

    *REG_VRAMMOD = 1;
    if (s->rows == 3) {
        for (r = 0; r < 3; r++) {
            *REG_VRAMRW = (u16)(s->tile + r);
            *REG_VRAMRW = attr;
        }
        return;
    }
    *REG_VRAMRW = s->tile;
    *REG_VRAMRW = attr;
    if (!*was_cleared) {
        for (r = 1; r < 32; r++) {
            *REG_VRAMRW = 0;
            *REG_VRAMRW = attr;
        }
        *was_cleared = 1;
    }
}

void radar_gfx_commit(void)
{
    u8 j, k;

    /* the blink first: it is the only palette write, and it belongs before
     * any radar line */
    if (pal_dirty) {
        MMAP_PALBANK1[RADAR_PAL_BANK * 16 + 1] = pal_last;
        pal_dirty = 0;
    }

    *REG_VRAMMOD = 1;
    for (j = 0; j < npic; j++) {
        k = pic_list[j];
        *REG_VRAMADDR = (u16)(ADDR_SCB1 + dyn_slot(k) * 64);
        write_tiles(&pend[k], &cleared[k]);
    }
    npic = 0;

    *REG_VRAMMOD = 0x200;
    for (j = 0; j < nplace; j++) {
        k = place_list[j];
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + dyn_slot(k));
        *REG_VRAMRW = pend[k].scb2;
        *REG_VRAMRW = pend[k].scb3;
        *REG_VRAMRW = pend[k].scb4;
    }
    nplace = 0;

    *REG_VRAMMOD = 1;
    for (j = 0; j < nstop; j++) {
        k = stop_list[j];
        *REG_VRAMADDR = (u16)(ADDR_SCB3 + dyn_slot(k));
        *REG_VRAMRW = 0;
    }
    nstop = 0;
}
