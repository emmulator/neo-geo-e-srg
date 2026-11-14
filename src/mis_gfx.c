/* mis_gfx.c: see mis_gfx.h.
 *
 * Each object owns 4 sprite slots under the dome and 4 over it, and shows in
 * one set (hiding the other). Its picture is chosen by ring and screen
 * azimuth (25 views, h-flipped beyond 180 deg) and by size: of the three
 * sizes, the smallest whose dart is at least as long as the one on screen,
 * shrunk to fit (from 100% down to 50%). A bullet is a laser bolt: one
 * 16 x 16 tile chosen by the bullet line's screen azimuth (32 pictures, two
 * shimmer frames) in PAL_SHIP, placed by its head pixel on the bullet's
 * point, at the old dart's shrink. Until its tail clears the muzzle it is
 * not drawn. Shrunk sprites can't be a sticky chain (the chain's 16 px offset
 * ignores shrinking), so every column gets its own X. Flipping a
 * multi-column picture also reverses the order of its columns (and of its
 * rows, for a vertical flip): the hardware flips each tile in place.
 *
 * Task 18b split the per-frame update in two. mis_gfx_prepare computes the
 * frame's slot words, pictures and placements into RAM, with no VRAM
 * writes; mis_gfx_commit writes the changes right after ng_wait_vblank(),
 * before game_frame's work. The commit memoises (the props' rules): SCB1
 * picture rows are written only when a slot's picture (tile, flip, height)
 * changed; the blank rows below it only once per slot since it was last
 * hidden (a "cleared" flag); SCB2/SCB3/SCB4 only when they changed; and a
 * slot that just stopped being shown gets SCB3 0 once.
 */
#include <ngdevkit/neogeo.h>
#include "mis_gfx.h"
#include "mis_view.h"
#include "dome.h"
#include "missile_map.h"
#include "ship_gfx.h"            /* PAL_SHIP: the bolt's bank */
#include "ship_map.h"            /* SHIP_BOLT_TILE, bolt_angle, bolt_head */
#include "hud.h"                 /* hud_framecnt: the churn's frame counter */
#include "demo.h"                /* demo_dbg_fc: the counter on the title */

#define SCREEN_W 320
#define SCREEN_H 224

/* CROM tiles 0..255 are the zero padding before the first game tile (4672),
 * so any of them is fully transparent: a "blank" tile. The hardware can
 * sample SCB1 rows 0..31 of a column (the vertical zoom table's 5-bit row
 * counter with its inversion wrap), so blanking the whole column below the
 * picture makes every reachable row blank whatever a previous frame left. */
#define MIS_BLANK_TILE 0
#define MIS_SCB1_ROWS 32

/* the slots this module owns: 5 objects x MIS_COLS_MAX under the dome, the
 * same 5 over it, and NEXPL x EXPL_COLS explosions */
#define MIS_SLOTS  (NOBJ * MIS_COLS_MAX)
#define EXPL_SLOTS (NEXPL * EXPL_COLS)
#define TOTAL_SLOTS (MIS_SLOTS * 2 + EXPL_SLOTS)

/* one slot's prepared state: the column's picture (tile base, row count,
 * source column, palette, flips) and its SCB2/SCB3/SCB4 words. */
typedef struct {
    u8 shown;
    u8 cols;                    /* picture rows in this column */
    u8 sc;                      /* source column (h-flip reversed) */
    u8 pal;
    u8 hflip, vflip;
    u8 anim;                    /* missile: 4-frame flame auto-animation */
    u16 tile0;
    u16 scb2, scb3, scb4;
} mis_slot_t;

typedef struct {
    u8 t;                       /* 0 free, else frames since it started + 1 */
    s16 x, y;                   /* its centre on screen */
} expl_t;

static expl_t expl[NEXPL];

/* the memo: each slot's last prepared state, the pending writes of the
 * frame being prepared, and the "rows MIS_COLS_MAX..31 are blank" flag of
 * every slot (reset when the slot stops being shown, so a later show blanks
 * the whole column and wipes any boot/planted garbage). */
static mis_slot_t prev[TOTAL_SLOTS];
static mis_slot_t pend[TOTAL_SLOTS];
/* the slots whose picture, placement or stop changed this frame, in a
 * compact list: the commit walks only those, not all 36 slots. */
static u8 pic_list[TOTAL_SLOTS];
static u8 place_list[TOTAL_SLOTS];
static u8 stop_list[TOTAL_SLOTS];
static u8 npic, nplace, nstop;
static u8 cleared[TOTAL_SLOTS];

static void hide(u16 slot, u8 n)
{
    *REG_VRAMMOD = 1;                            /* SCB3 of consecutive slots */
    *REG_VRAMADDR = ADDR_SCB3 + slot;
    while (n--)
        *REG_VRAMRW = 0;                         /* height 0: not drawn */
}

/* forget every memo entry: used by the init and hide paths, which write
 * directly (outside a play frame), so the next show starts from a cleared
 * column. */
static void memo_clear(void)
{
    u8 k;

    for (k = 0; k < TOTAL_SLOTS; k++) {
        prev[k].shown = 0;
        prev[k].cols = prev[k].sc = prev[k].pal = 0;
        prev[k].hflip = prev[k].vflip = prev[k].anim = 0;
        prev[k].tile0 = prev[k].scb2 = prev[k].scb3 = prev[k].scb4 = 0;
        cleared[k] = 0;
    }
    npic = nplace = nstop = 0;
}

void mis_gfx_init(void)
{
    u8 i;

    for (i = 0; i < 16; i++) {
        MMAP_PALBANK1[PAL_MISSILE * 16 + i] = mis_pal[i];
        MMAP_PALBANK1[PAL_BULLET * 16 + i] = bul_pal[i];
        MMAP_PALBANK1[PAL_EXPL * 16 + i] = expl_pal[i];
    }
    /* R2: the flame's 4-frame auto-animation (SCB1 bit 2) runs on the
     * LSPC's global counter. Speed 3 makes one animation frame last 4
     * video frames; every other bit (timer interrupt, stall) stays 0.
     * Written once here, before the first frame. */
    *REG_LSPCMODE = 0x0300;
    hide(MIS_BEHIND_SPRITE, MIS_SLOTS);
    hide(MIS_FRONT_SPRITE, MIS_SLOTS);
    hide(EXPL_SPRITE, EXPL_SLOTS);
    for (i = 0; i < NEXPL; i++)
        expl[i].t = 0;
    memo_clear();
}

/* the title / every entry: hide every slot directly (outside a play frame)
 * and forget the memo, so the first play frame's show writes full columns. */
void mis_gfx_hide(void)
{
    hide(MIS_BEHIND_SPRITE, MIS_SLOTS);
    hide(MIS_FRONT_SPRITE, MIS_SLOTS);
    hide(EXPL_SPRITE, EXPL_SLOTS);
    memo_clear();
}

/* the absolute VRAM slot of a memo index */
static u16 abs_slot(u8 k)
{
    if (k < MIS_SLOTS)
        return (u16)(MIS_BEHIND_SPRITE + k);
    k = (u8)(k - MIS_SLOTS);
    if (k < MIS_SLOTS)
        return (u16)(MIS_FRONT_SPRITE + k);
    k = (u8)(k - MIS_SLOTS);
    return (u16)(EXPL_SPRITE + k);
}

/* the picture chosen for one missile/bullet, without writing: the same
 * arithmetic show_obj did, into `d`. */
typedef struct {
    u8 behind;                  /* the used set */
    u8 cols, pal, hflip, vflip;
    u16 tile0;
    s16 x, y;
    u8 hz, vz, height;
} obj_draw_t;

/* Task H2: the bolt's shimmer follows the game's frame counter (the
 * demo's own counter on the title, where hud_framecnt stays 0). */
static u16 churn_fc(void)
{
    return (u16)(hud_framecnt ? hud_framecnt : demo_dbg_fc);
}

/* a missile: the dart picture chosen by ring and screen azimuth, shrunk to
 * fit. Its path is kept as it was in R2. */
static u8 obj_draw(const mis_obj_t *o, u8 dome_angle, obj_draw_t *d)
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

    d->behind = (u8)v.behind;
    d->cols = cols;
    d->pal = pal;
    d->hflip = hflip;
    d->vflip = vflip;
    d->tile0 = (u16)(mis_tile_base[l]
                    + (o->ring * MIS_VIEWS + q) * cols * cols * MIS_FRAMES);
    d->x = x;
    d->y = y;
    d->hz = (u8)(((f << 4) + 128) >> 8);
    d->vz = (u8)(f > 255 ? 255 : f - 1);
    d->height = (u8)((cols * (u16)(d->vz + 1) + 255) >> 8);   /* ceil(cols*(vz+1)/256) */
    if (!d->height)
        d->height = 1;
    if (d->hz)
        d->hz--;                                 /* hz + 1 px per column */

    return 1;
}

/* Task H2: a bullet's laser bolt: one 16 x 16 tile from the bullet line's
 * screen azimuth (q48 before the dart's mirroring) and its two-frame
 * shimmer, in PAL_SHIP; its head pixel goes on the bullet's point at the
 * old dart's shrink. Hidden until its tail clears the muzzle. */
static u8 bullet_draw(const mis_obj_t *o, u8 dome_angle, obj_draw_t *d,
                      u8 obj_i, u16 fc)
{
    mis_view_t v;
    u8 j = (u8)(o->phi + dome_angle >= 240 ? o->phi + dome_angle - 240 : o->phi + dome_angle);
    u8 q48 = (u8)((j + 2) / 5), q, l, angle;
    u16 len4, f;
    s16 hx, hy, fs, x, y;
    const u8 *tip, *head;

    if (o->r < (s32)(SHIP_MUZZLE_R + BOLT_LEN_R))
        return 0;                                /* still inside the cannon */
    mis_view(&v, o->ring, j, o->r);
    if (!v.shown)
        return 0;
    len4 = v.len4 >> 1;                          /* the dart's shrink, half size */
    if (q48 >= 48)
        q48 = 0;
    q = q48;
    if (q > 24)                                  /* the dart's mirrored view */
        q = (u8)(48 - q);
    for (l = 0; l < MIS_LEVELS - 1 && len4 < (u16)mis_len[l] * 8; l++)
        ;
    tip = mis_tip[l][o->ring * MIS_VIEWS + q];
    f = (u16)(((u32)len4 << 8) / ((u16)tip[2] << 4));
    if (f > 256)
        f = 256;
    if (f < 64)
        f = 64;
    angle = bolt_angle[o->ring][q48];
    head = bolt_head[angle];
    hx = (s16)head[0];
    hy = (s16)head[1];
    fs = (s16)((16 * f) >> 8);
    x = (s16)(DOME_X + v.x - ((hx * (s16)f) >> 8));
    y = (s16)(DOME_Y + v.y - ((hy * (s16)f) >> 8));
    if (x >= SCREEN_W || y >= SCREEN_H || x + fs <= 0 || y + fs <= 0)
        return 0;
    d->behind = (u8)v.behind;
    d->cols = 1;
    d->pal = PAL_SHIP;
    d->hflip = d->vflip = 0;
    d->tile0 = (u16)(SHIP_BOLT_TILE + angle * BOLT_FRAMES
                     + ((fc + (u8)(obj_i - NMIS)) & 1));
    d->x = x;
    d->y = y;
    d->hz = (u8)(((f << 4) + 128) >> 8);
    d->vz = (u8)(f > 255 ? 255 : f - 1);
    d->height = 1;                               /* one 16 x 16 tile */
    if (d->hz)
        d->hz--;
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

void mis_gfx_prepare(const mis_t *m, u8 dome_angle)
{
    mis_slot_t cur[TOTAL_SLOTS];
    u8 i, c, k;
    u16 fc = churn_fc();

    /* only the shown flag needs clearing: a hidden slot's other fields are
     * never read (the memo's compare tests `shown` first), and every shown
     * slot's fields are set below. */
    for (k = 0; k < TOTAL_SLOTS; k++)
        cur[k].shown = 0;

    /* ---- the missiles and bullets: one set each, the other hidden ---- */
    for (i = 0; i < NOBJ; i++) {
        obj_draw_t d;
        u8 drawn;
        u8 behind = (u8)(i * MIS_COLS_MAX);
        u8 front = (u8)(MIS_SLOTS + i * MIS_COLS_MAX);

        if (m->obj[i].state != 1)
            continue;
        if (m->obj[i].kind == KIND_BULLET)
            drawn = bullet_draw(&m->obj[i], dome_angle, &d, i, fc);
        else
            drawn = obj_draw(&m->obj[i], dome_angle, &d);
        if (drawn) {
            u8 base = d.behind ? behind : front;

            for (c = 0; c < d.cols; c++) {
                mis_slot_t *s = &cur[base + c];

                s->shown = 1;
                s->cols = d.cols;
                s->sc = d.hflip ? (u8)(d.cols - 1 - c) : c;
                s->pal = d.pal;
                s->hflip = d.hflip;
                s->vflip = d.vflip;
                s->anim = (u8)(m->obj[i].kind == KIND_MISSILE);
                s->tile0 = d.tile0;
                s->scb2 = (u16)(((u16)d.hz << 8) | d.vz);
                s->scb3 = (u16)(((u16)(496 - d.y) << 7) | d.height);
                s->scb4 = (u16)(((u16)(d.x + (s16)c * (s16)(d.hz + 1))) << 7);
            }
        }
    }

    /* ---- a hit's explosion starts this frame (after the objects, as the
     * old show did); the explosion loop then draws it and ages it ---- */
    for (i = 0; i < m->nhit; i++)
        explode(&m->hit[i], dome_angle);
    for (i = 0; i < NEXPL; i++) {
        expl_t *e = &expl[i];

        if (!e->t)
            continue;
        {
            u8 base = (u8)(2 * MIS_SLOTS + i * EXPL_COLS);
            u16 tile0 = (u16)(EXPL_TILE_BASE
                              + (e->t - 1) * EXPL_FRAMES / EXPL_TIME
                              * EXPL_COLS * EXPL_COLS);
            s16 x = (s16)(e->x - EXPL_COLS * 8);
            s16 y = (s16)(e->y - EXPL_COLS * 8);

            for (c = 0; c < EXPL_COLS; c++) {
                mis_slot_t *s = &cur[base + c];

                s->shown = 1;
                s->cols = EXPL_COLS;
                s->sc = c;
                s->pal = PAL_EXPL;
                s->hflip = s->vflip = 0;
                s->anim = 0;
                s->tile0 = tile0;
                s->scb2 = 0x0fff;                /* full size */
                s->scb3 = (u16)(((u16)(496 - y) << 7) | EXPL_COLS);
                s->scb4 = (u16)(((u16)(x + c * 16)) << 7);
            }
        }
        if (++e->t > EXPL_TIME)
            e->t = 0;
    }

    /* ---- the memo: mark only the changed words, then adopt this frame's
     * state (the next prepare compares against what this frame commits).
     * The changed slots go in compact lists so the commit does not walk all
     * 36 slots of a frame that changes only a few. ---- */
    npic = nplace = nstop = 0;
    for (k = 0; k < TOTAL_SLOTS; k++) {
        if (cur[k].shown) {
            if (!prev[k].shown || prev[k].tile0 != cur[k].tile0
                || prev[k].cols != cur[k].cols || prev[k].sc != cur[k].sc
                || prev[k].pal != cur[k].pal
                || prev[k].hflip != cur[k].hflip
                || prev[k].vflip != cur[k].vflip
                || prev[k].anim != cur[k].anim) {
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
            cleared[k] = 0;                     /* the next show re-blanks all */
            pend[k] = cur[k];
        }
        /* both hidden: prev is already hidden and its other fields are
         * never read, so skip the full struct copy */
        if (cur[k].shown || prev[k].shown)
            prev[k] = cur[k];
    }
}


/* write a shown column's SCB1: the picture rows, then a blank tile for
 * every row the hardware can sample below it. A picture is at most
 * MIS_COLS_MAX (3) rows, so rows 3..31 are blanked on the first write since
 * the slot was hidden, and never again (no picture can reach them). */
static void write_tiles(u16 slot, const mis_slot_t *s, u8 *was_cleared)
{
    u16 attr = (u16)(((u16)s->pal << 8) | (s->anim ? 0x0004 : 0)
                     | (s->vflip << 1) | s->hflip);
    u8 r, last = *was_cleared ? MIS_COLS_MAX : MIS_SCB1_ROWS;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB1 + slot * 64);
    for (r = 0; r < last; r++) {
        if (r < s->cols) {
            u8 sr = s->vflip ? (u8)(s->cols - 1 - r) : r;

            if (s->anim)                         /* tile0 + cell * 4 + frame 0 */
                *REG_VRAMRW = (u16)(s->tile0
                                    + ((u16)sr * s->cols + s->sc) * MIS_FRAMES);
            else
                *REG_VRAMRW = (u16)(s->tile0 + (u16)sr * s->cols + s->sc);
        } else {
            *REG_VRAMRW = MIS_BLANK_TILE;
        }
        *REG_VRAMRW = attr;
    }
    *was_cleared = 1;
}

void mis_gfx_commit(void)
{
    u8 j, k;

    *REG_VRAMMOD = 1;
    for (j = 0; j < npic; j++) {
        k = pic_list[j];
        write_tiles(abs_slot(k), &pend[k], &cleared[k]);
    }
    npic = 0;

    *REG_VRAMMOD = 0x200;
    for (j = 0; j < nplace; j++) {
        k = place_list[j];
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + abs_slot(k));
        *REG_VRAMRW = pend[k].scb2;
        *REG_VRAMRW = pend[k].scb3;
        *REG_VRAMRW = pend[k].scb4;
    }
    nplace = 0;

    *REG_VRAMMOD = 1;
    for (j = 0; j < nstop; j++) {
        k = stop_list[j];
        *REG_VRAMADDR = (u16)(ADDR_SCB3 + abs_slot(k));
        *REG_VRAMRW = 0;
    }
    nstop = 0;
}
