/* radar.c: see radar.h. The positions mirror radar.s (the spot on the
 * ellipse, the stick, the heading toward the centre with its two lengths);
 * the lock state mirrors e-srg.c's lock_update. Per-frame maths are 16-bit:
 * the rings' factors and the azimuths' sines are generated tables
 * (build/radar_tables.h) and each product is a mulu.w/muls.w-sized
 * product; the one divide (R/6 in 512ths) is a strength-reduced divu.w.
 * Checked with m68k-neogeo-elf-objdump for __divsi3/__udivsi3/__modsi3/
 * __umodsi3/__mulsi3. */
#include <ngdevkit/neogeo.h>
#include "radar.h"
#include "cells.h"
#include "radar_tables.h"
#include "missiles_tables.h"       /* mis_cell_ring / mis_cell_phi */

/* round-half-up (n / 4), n an s16 (the heading is at most ~30 px). */
static s16 div4(s16 n)
{
    return (s16)(n >= 0 ? (s16)(((u16)n + 2) >> 2)
                        : (s16)-((((u16)(0 - (u16)n)) + 2) >> 2));
}

u8 radar_j(u8 phi, u8 dome_angle)
{
    u16 j = (u16)((u16)phi + (u16)dome_angle);   /* 0..478: one subtract */

    if (j >= 240)
        j = (u16)(j - 240);
    return (u8)j;
}

void radar_blip(radar_blip_t *b, u8 ring, u8 j, s32 r, u8 locked)
{
    s16 q;                       /* s16: the signed q x sin product must stay
                                  * a muls.w, not a __mulsi3 call */
    u16 r6;

    if (r >= (s32)RADAR_RANGE) {               /* beyond the ellipse's edge */
        b->shown = 0;
        b->locked = 0;
        b->sx = b->sy = b->hx = b->hy = 0;
        b->h = 0;
        return;
    }
    /* R/6 in 512ths: round(r / (6 << 19) * 512) = round(r / 6144).
     * r (up to 6<<19) does not fit a 16-bit dividend, so split:
     * r = (r >> 7) * 128 + b, b < 128; r/6144 = (r>>7)/48 + b/6144 with
     * b/6144 < 1/48, so the 16-bit divide below is exact except when the
     * fraction is within 1/48 of a half — then one 512th of R/6, under
     * 0.06 px, well inside the task's 1 px. */
    r6 = (u16)((u16)((u16)((s32)r >> 7) + 24) / 48);
    /* the spot: sx = CX + R/6 * RX * sin(theta) * sin(j),
     *           sy = CY + R/6 * RY * sin(theta) * cos(j)   (y down).
     * q is the ring's factor in 256ths of px (<= 7680, an s16), so the
     * signed product q x radar_sin[j] stays a muls.w; the Q16 -> px
     * divide is a rounding shift. */
    q = (s16)(((u32)r6 * radar_rx[ring] + 256) / (u16)512);   /* Q8 px */
    b->sx = (s16)(RADAR_CX + (s16)(((s32)q * radar_sin[j] + 32768) >> 16));
    q = (s16)(((u32)r6 * radar_ry[ring] + 256) / (u16)512);
    b->sy = (s16)(RADAR_CY + (s16)(((s32)q * radar_cos[j] + 32768) >> 16));
    /* the stick: h = R/6 * H * cos(theta)^RADAR_H_POW, its top (sx, sy-h):
     * r6 (512ths) x hv (Q8) = Q17, divide by 2^17 with rounding */
    b->h = (u8)(((u32)r6 * radar_hv[ring] + 65536) >> 17);
    /* the heading: from the top toward (CX, CY), 1/2^SHIFT of the way
     * (radar.s's HEAD_SHIFT), one shift less when locked. */
    {
        s16 topx = b->sx;
        s16 topy = (s16)(b->sy - b->h);
        s16 num = (s16)(locked ? 2 : 1);   /* 2/4 vs 1/4 of the way */

        b->hx = (s16)(topx + div4((s16)((RADAR_CX - topx) * num)));
        b->hy = (s16)(topy + div4((s16)((RADAR_CY - topy) * num)));
    }
    b->shown = 1;
    b->locked = locked;
}

void radar_frame(radar_t *out, const mis_t *m, const ship_t *s)
{
    u8 i, locked = 0, ring = 255, phi = 0;

    if (s->move_left == 0) {               /* the Vectrex: only at rest does */
        ring = mis_cell_ring[s->cell];     /* the ship's cell set the target */
        phi = mis_cell_phi[s->cell];
    }
    for (i = 0; i < NMIS; i++) {
        const mis_obj_t *o = &m->obj[i];
        radar_blip_t *b = &out->blip[i];

        if (o->state == 1 && o->r < (s32)RADAR_RANGE) {
            if (ring != 255 && o->ring == ring && o->phi == phi)
                b->locked = 1;
            else
                b->locked = 0;
            if (b->locked)
                locked = 1;
            radar_blip(b, o->ring, radar_j(o->phi, s->dome_angle), o->r,
                       b->locked);
        } else {
            b->shown = 0;                  /* no blip at all: nothing stale */
            b->locked = 0;
            b->sx = b->sy = b->hx = b->hy = 0;
            b->h = 0;
        }
    }
    if (locked) {                          /* e-srg.c lock_update: lock_t */
        out->lock_t = (u8)(out->lock_t + 1);   /* counts while locked, */
        out->ellipse_bright = (u8)((u8)(out->lock_t / RADAR_BLINK) & 1);
        out->locked = 1;
    } else {
        out->lock_t = 0;                   /* ... and resets to 0 when not */
        out->ellipse_bright = 0;
        out->locked = 0;
    }
}
