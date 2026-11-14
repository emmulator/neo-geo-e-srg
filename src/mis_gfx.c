/* mis_gfx.c: see mis_gfx.h.
 *
 * Each object owns 4 sprite slots under the dome and 4 over it, and shows in
 * one set (hiding the other). Its picture is chosen by ring and screen
 * azimuth (25 views, h-flipped beyond 180 deg) and by size: of the three
 * sizes, the smallest whose dart is at least as long as the one on screen,
 * shrunk to fit (from 100% down to 50%). A bullet is the same picture
 * turned tip-outward (flipped both ways) at half the length, in its own
 * palette. Shrunk sprites can't be a sticky chain (the chain's 16 px offset
 * ignores shrinking), so every column gets its own X. Flipping a
 * multi-column picture also reverses the order of its columns (and of its
 * rows, for a vertical flip): the hardware flips each tile in place. */
#include <ngdevkit/neogeo.h>
#include "mis_gfx.h"
#include "mis_view.h"
#include "dome.h"
#include "missile_map.h"

#define SCREEN_W 320
#define SCREEN_H 224

/* CROM tiles 0..255 are the zero padding before the first game tile (4672),
 * so any of them is fully transparent: a "blank" tile. The hardware can
 * sample SCB1 rows 0..31 of a column (the vertical zoom table's 5-bit row
 * counter with its inversion wrap), so blanking the whole column below the
 * picture makes every reachable row blank whatever a previous frame left. */
#define MIS_BLANK_TILE 0
#define MIS_SCB1_ROWS 32

typedef struct {
    u8 t;                       /* 0 free, else frames since it started + 1 */
    s16 x, y;                   /* its centre on screen */
} expl_t;

static expl_t expl[NEXPL];

static void hide(u16 slot, u8 n)
{
    *REG_VRAMMOD = 1;                            /* SCB3 of consecutive slots */
    *REG_VRAMADDR = ADDR_SCB3 + slot;
    while (n--)
        *REG_VRAMRW = 0;                         /* height 0: not drawn */
}

void mis_gfx_init(void)
{
    u8 i;

    for (i = 0; i < 16; i++) {
        MMAP_PALBANK1[PAL_MISSILE * 16 + i] = mis_pal[i];
        MMAP_PALBANK1[PAL_BULLET * 16 + i] = bul_pal[i];
        MMAP_PALBANK1[PAL_EXPL * 16 + i] = expl_pal[i];
    }
    hide(MIS_BEHIND_SPRITE, NOBJ * MIS_COLS_MAX);
    hide(MIS_FRONT_SPRITE, NOBJ * MIS_COLS_MAX);
    hide(EXPL_SPRITE, NEXPL * EXPL_COLS);
    for (i = 0; i < NEXPL; i++)
        expl[i].t = 0;
}

/* show `cols` x `cols` tiles from `tile0` (row-major runs of `cols`) at
 * top-left (x, y), shrunk by f/256, flipped, in slots from `slot`.
 *
 * Vertical shrink does NOT make a sprite shorter: the hardware still draws
 * `height` x 16 screen lines and samples SCB1 rows of the column top-down
 * (the "000-lo.lo" zoom table maps screen line to tile row and sub-row). The
 * picture therefore fills only the first rows*16*f/256 screen lines, and
 * every line below it samples rows `rows`, `rows+1`, ... of the same SCB1
 * column — which, unless we blank them, hold whatever an earlier, taller
 * picture left there. Two things keep those lines clean:
 *
 *  - height = ceil(cols*(vz+1)/256): the shortest height whose 16*height
 *    lines still contain the whole picture (for the smallest shrink, f=64:
 *    a 4-tile picture is 1 tile tall, a 2-tile picture 1, a 1-tile 1). This
 *    is at most `cols`, so full-size (f=256) darts and explosions keep their
 *    old height and look exactly as before.
 *  - rows `cols`..31 of the column are written with a blank tile every frame.
 *    The zoom table can reach row 31 at most (5-bit row with the inversion
 *    wrap), so every row the hardware can sample below the picture is blank
 *    no matter what an earlier frame left there; with the pictures here
 *    (1..4 tiles, vz 63..255) the reach below the picture is at most 7, and
 *    blanking all 32 rows costs 64 words per column and covers every case. */
static void place(u16 slot, u16 tile0, u8 cols, u8 pal, u8 hflip, u8 vflip, s16 x, s16 y, u16 f)
{
    u8 c, r, hz = (u8)(((f << 4) + 128) >> 8), vz = (u8)(f > 255 ? 255 : f - 1);
    u8 height = (u8)((cols * (u16)(vz + 1) + 255) >> 8);   /* ceil(cols*(vz+1)/256) */
    s16 rr;                                  /* blank rows: cols..31 */
    u16 attr = (u16)((pal << 8) | (vflip << 1) | hflip);

    if (!height)
        height = 1;
    if (hz)
        hz--;                                    /* hz + 1 px per column */
    *REG_VRAMMOD = 1;
    for (c = 0; c < cols; c++) {
        u8 sc = hflip ? (u8)(cols - 1 - c) : c;  /* source column */
        *REG_VRAMADDR = ADDR_SCB1 + (slot + c) * 64;
        for (r = 0; r < cols; r++) {
            u8 sr = vflip ? (u8)(cols - 1 - r) : r;
            *REG_VRAMRW = (u16)(tile0 + sr * cols + sc);
            *REG_VRAMRW = attr;
        }
        for (rr = cols; rr < MIS_SCB1_ROWS; rr++) {   /* blank below the picture */
            *REG_VRAMRW = MIS_BLANK_TILE;
            *REG_VRAMRW = attr;
        }
    }
    *REG_VRAMMOD = 0x200;
    for (c = 0; c < cols; c++) {
        *REG_VRAMADDR = ADDR_SCB2 + slot + c;
        *REG_VRAMRW = (u16)((hz << 8) | vz);
        *REG_VRAMRW = (u16)((u16)((496 - y) << 7) | height);
        *REG_VRAMRW = (u16)((x + c * (hz + 1)) << 7);
    }
}

/* one missile or bullet; returns 0 if nothing is drawn */
static u8 show_obj(u8 i, const mis_obj_t *o, u8 dome_angle)
{
    mis_view_t v;
    u8 j = (u8)(o->phi + dome_angle >= 240 ? o->phi + dome_angle - 240 : o->phi + dome_angle);
    u8 q = (u8)((j + 2) / 5), hflip = 0, vflip = 0, l, cols, pal = PAL_MISSILE;
    u16 len4, f, size;
    s16 tx, ty, x, y;
    const u8 *tip;

    mis_view(&v, o->ring, j, o->r);
    if (!v.shown)
        return 0;
    len4 = v.len4;
    if (q >= 48)
        q = 0;
    if (q > 24) {                                /* the other half: mirrored */
        q = (u8)(48 - q);
        hflip = 1;
    }
    if (o->kind == KIND_BULLET) {                /* tip outward, half size */
        len4 >>= 1;
        hflip ^= 1;
        vflip = 1;
        pal = PAL_BULLET;
    }
    for (l = 0; l < MIS_LEVELS - 1 && len4 < (u16)mis_len[l] * 8; l++)
        ;                                        /* (len4 / 16 < half of size l's dart) */
    cols = mis_cols[l];
    tip = mis_tip[l][o->ring * MIS_VIEWS + q];
    f = (u16)(((u32)len4 << 8) / ((u16)tip[2] << 4));       /* shrink, /256 */
    if (f > 256)
        f = 256;                                 /* (shrink only: very near darts stay at 100%) */
    if (f < 64)
        f = 64;
    size = (u16)(cols * 16);
    tx = hflip ? (s16)(size - 1 - tip[0]) : tip[0];
    ty = vflip ? (s16)(size - 1 - tip[1]) : tip[1];
    x = (s16)(DOME_X + v.x - ((tx * (s16)f) >> 8));
    y = (s16)(DOME_Y + v.y - ((ty * (s16)f) >> 8));
    if (x >= SCREEN_W || y >= SCREEN_H || x + ((size * f) >> 8) <= 0 || y + ((size * f) >> 8) <= 0)
        return 0;
    hide(v.behind ? MIS_FRONT_SPRITE + i * MIS_COLS_MAX : MIS_BEHIND_SPRITE + i * MIS_COLS_MAX, MIS_COLS_MAX);
    {
        u16 slot = (u16)((v.behind ? MIS_BEHIND_SPRITE : MIS_FRONT_SPRITE) + i * MIS_COLS_MAX);
        place(slot, (u16)(mis_tile_base[l] + (o->ring * MIS_VIEWS + q) * cols * cols),
              cols, pal, hflip, vflip, x, y, f);
        if (cols < MIS_COLS_MAX)
            hide((u16)(slot + cols), (u8)(MIS_COLS_MAX - cols));
    }
    return 1;
}

static void explode(const mis_hit_t *h, u8 dome_angle)
{
    mis_view_t v;
    u8 j = (u8)(h->phi + dome_angle >= 240 ? h->phi + dome_angle - 240 : h->phi + dome_angle);
    s16 x, y;

    mis_view(&v, h->ring, j, h->r);
    x = (s16)(DOME_X + v.x);
    y = (s16)(DOME_Y + v.y);
    if (!v.shown || v.behind || x < 0 || x >= SCREEN_W || y < 0 || y >= SCREEN_H)
        return;                                  /* unseen: no explosion (the Vectrex's rule) */
    mis_gfx_explode_at(x, y);
}

void mis_gfx_explode_at(s16 x, s16 y)
{
    expl_t *e = expl;

    if (e->t && (expl[1].t == 0 || expl[1].t > e->t))
        e = expl + 1;                            /* a free one, or the older */
    e->t = 1;
    e->x = x;
    e->y = y;
}

void mis_gfx_show(const mis_t *m, u8 dome_angle)
{
    u8 i;

    for (i = 0; i < NOBJ; i++)
        if (m->obj[i].state != 1 || !show_obj(i, &m->obj[i], dome_angle)) {
            hide((u16)(MIS_BEHIND_SPRITE + i * MIS_COLS_MAX), MIS_COLS_MAX);
            hide((u16)(MIS_FRONT_SPRITE + i * MIS_COLS_MAX), MIS_COLS_MAX);
        }
    for (i = 0; i < m->nhit; i++)
        explode(&m->hit[i], dome_angle);
    for (i = 0; i < NEXPL; i++) {
        expl_t *e = &expl[i];
        u16 slot = (u16)(EXPL_SPRITE + i * EXPL_COLS);

        if (!e->t) {
            hide(slot, EXPL_COLS);
            continue;
        }
        place(slot, (u16)(EXPL_TILE_BASE + (e->t - 1) * EXPL_FRAMES / EXPL_TIME * EXPL_COLS * EXPL_COLS),
              EXPL_COLS, PAL_EXPL, 0, 0, (s16)(e->x - EXPL_COLS * 8), (s16)(e->y - EXPL_COLS * 8), 256);
        if (++e->t > EXPL_TIME)
            e->t = 0;
    }
}
