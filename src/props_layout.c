/* props_layout.c: see props_layout.h. The arithmetic of Tasks 11 and 15:
 *
 *  - prop_se[i][da] != 0 marks a visible prop. A visible prop whose
 *    prop_front[i][da] is 1 goes to the FRONT pool (it covers the dome on
 *    screen), every other visible prop to the BACK pool. Each pool is
 *    ordered by prop_y[i][da] (smallest first: far first), ties to the
 *    lower i;
 *  - prop i's LOD is the smallest l with prop_lod_ppu[l] >= se; its picture
 *    is prop_tree_pic or prop_rock_pic[shape][l]; k = se / ppu, hz =
 *    round(16 k) - 1 (at least 0), v = round(256 k) - 1 (0..255), and the
 *    top-left is (x - round(ax k), y - round(ay k)); column c sits at
 *    left + c (hz + 1);
 *  - each column's words are SCB2 (hz << 8) | v, SCB3 ((496 - top) << 7) |
 *    rows, SCB4 ((col_x & 0x1ff) << 7), and the first SCB1 tile
 *    first + c * rows (relative to the props part);
 *  - each pool's unused slots are shown 0 with every word 0.
 *
 * round(16 k) and round(256 k) are read from a table built once from the
 * header's prop_lod_ppu (built without a divide: the numerator's quotient
 * and remainder advance by 16 / 256 a step), and the anchor rounding is an
 * exact multiply-and-shift (mulu, no divide): the magic 10923 with the LOD's
 * shift gives n / (24 << lod), then the remainder decides the half (ties to
 * even, like Python's round() and tools/render_props.drawn()).
 * tests/test_props.py holds every word of both pools to a model written
 * from the header and drawn(); its mutations break the tie order and the
 * hz rounding. */
#include "props_layout.h"

#define PROP_HZ_MAGIC 10923u    /* 10923 / 2^(18+lod) = 1 / (24 << lod),
                                 * exact for the products here (<= 24576) */

static u8 hz_tab[PROP_NLOD][256];
static u8 v_tab[PROP_NLOD][256];
static u8 tables_ready;

/* the table of round(16 k) - 1 and round(256 k) - 1 for every se 0..255 and
 * LOD; built once (no divide). */
static void build_tables(void)
{
    u8 l;
    u16 se;

    for (l = 0; l < PROP_NLOD; l++) {
        u16 ppu = prop_lod_ppu[l];
        u16 q16 = 0, r16 = 0, q256 = 0, r256 = 0;

        for (se = 0; se < 256; se++) {
            u16 hz, v;

            if (se) {                   /* next numerator: +16 / +256 */
                r16 = (u16)(r16 + 16);
                while (r16 >= ppu) {
                    r16 = (u16)(r16 - ppu);
                    q16++;
                }
                r256 = (u16)(r256 + 256);
                while (r256 >= ppu) {
                    r256 = (u16)(r256 - ppu);
                    q256++;
                }
            }
            /* round half to even: q + 1 if the remainder is over half, a
             * tie goes up only when q is odd */
            hz = q16;
            if (2 * r16 > ppu || (2 * r16 == ppu && (q16 & 1)))
                hz++;
            v = q256;
            if (2 * r256 > ppu || (2 * r256 == ppu && (q256 & 1)))
                v++;
            hz_tab[l][se] = (u8)(hz ? hz - 1 : 0);
            v_tab[l][se] = (u8)(v ? (v > 256 ? 255 : v - 1) : 0);
        }
    }
    tables_ready = 1;
}

/* round(a * se / (24 << lod)) exactly, without a divide: the magic product
 * gives the quotient, the remainder the half (ties to even). a is a
 * picture's anchor (ax/ay, at most 67) and se at most 96, so a * se fits
 * 16 bits. */
static u16 round_anchor(u8 a, u8 se, u8 lod)
{
    u16 ppu = prop_lod_ppu[lod];
    u16 n = (u16)(a * se);
    u16 q = (u16)(((u32)n * PROP_HZ_MAGIC) >> (18 + lod));
    u16 r = (u16)(n - q * ppu);
    u16 half = (u16)(ppu >> 1);

    if (r > half)
        return (u16)(q + 1);
    if (r < half)
        return q;
    return (u16)(q + (q & 1));           /* exact .5: to even */
}

static const prop_pic_t *pic_of(u8 prop, u8 lod)
{
    if (prop_kind[prop] == 0)
        return &prop_tree_pic[prop_shape[prop]][lod];
    return &prop_rock_pic[prop_shape[prop]][lod];
}

/* fill one pool: its visible props, far to near, ties to the lower index,
 * their columns in slots 0.., the rest shown 0 with every word 0. */
static void fill_pool(u8 da, u8 front_pool, prop_slot_t *out, u8 cap)
{
    u8 order[NPROPS];
    u8 n = 0, i, c, l, slot;
    u8 lod, se, hz, v;
    s16 left, top;
    const prop_pic_t *pic;

    /* the visible props of this pool, insertion-sorted by foot y; inserting
     * each i in index order and stopping at the first y that is not greater
     * keeps equal y in lower-i-first order (the far-first tie rule). */
    for (i = 0; i < NPROPS; i++) {
        u8 j;

        if (!prop_se[i][da])
            continue;
        if ((prop_front[i][da] != 0) != (front_pool != 0))
            continue;
        j = n;
        while (j > 0 && prop_y[order[j - 1]][da] > prop_y[i][da]) {
            order[j] = order[j - 1];
            j--;
        }
        order[j] = i;
        n++;
    }

    slot = 0;
    for (i = 0; i < n; i++) {
        u8 p = order[i];

        se = prop_se[p][da];
        for (l = 0; l < PROP_NLOD - 1; l++) {
            if (prop_lod_ppu[l] >= se)
                break;
        }
        lod = l;
        pic = pic_of(p, lod);
        hz = hz_tab[lod][se];
        v = v_tab[lod][se];
        left = (s16)(prop_x[p][da] - round_anchor(pic->ax, se, lod));
        top = (s16)(prop_y[p][da] - round_anchor(pic->ay, se, lod));
        for (c = 0; c < pic->cols; c++) {
            prop_slot_t *o = &out[slot];

            o->shown = 1;
            o->prop = p;
            o->lod = lod;
            o->col = c;
            o->scb2 = (u16)((hz << 8) | v);
            o->scb3 = (u16)((((u16)(496 - top)) << 7) | pic->rows);
            o->scb4 = (u16)(((u16)(left + c * (hz + 1)) & 0x1ff) << 7);
            o->tile = (u16)(pic->first + c * pic->rows);
            slot++;
        }
    }
    for (; slot < cap; slot++) {
        out[slot].shown = 0;
        out[slot].prop = 0;
        out[slot].lod = 0;
        out[slot].col = 0;
        out[slot].scb2 = 0;
        out[slot].scb3 = 0;
        out[slot].scb4 = 0;
        out[slot].tile = 0;
    }
}

void props_layout(u8 da, prop_slot_t back[PROP_BACK_SLOTS],
                  prop_slot_t front[PROP_FRONT_SLOTS])
{
    if (!tables_ready)
        build_tables();

    fill_pool(da, 0, back, PROP_BACK_SLOTS);
    fill_pool(da, 1, front, PROP_FRONT_SLOTS);
}
