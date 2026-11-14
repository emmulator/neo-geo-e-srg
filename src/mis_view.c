/* mis_view.c: see mis_view.h. A perspective projection in fixed point, the
 * same camera as tools/geometry.py: lengths Q12 (sphere radii), sines Q14,
 * pixels Q4. 16 x 16 -> 32-bit products, two 32-bit divisions. */
#include <ngdevkit/neogeo.h>
#include "cells.h"
#include "missiles_tables.h"
#include "mis_view.h"

void mis_view(mis_view_t *v, u8 ring, u8 j, s32 r)
{
    s16 rq = (s16)(r >> 7);                                /* 2^-19 -> Q12 */
    s16 h = (s16)(((s32)rq * ring_sin[ring]) >> 14);      /* from the axis */
    s16 y = (s16)(((s32)rq * ring_cos[ring]) >> 14);      /* height */
    s16 x = (s16)(((s32)h * mis_sin[j]) >> 14);
    s16 zc = (s16)(((s32)h * mis_sin[j + 60 >= 240 ? j - 180 : j + 60]) >> 14);   /* cos */
    s16 dy = (s16)(y - CAM_PY), dz = (s16)(zc - CAM_PZ);
    s32 z = ((s32)dy * CAM_FY + (s32)dz * CAM_FZ) >> 14;   /* depth */
    s32 u = ((s32)dy * CAM_UY + (s32)dz * CAM_UZ) >> 14;   /* up on screen */
    u8 jm = (u8)(j > 120 ? 240 - j : j);

    v->behind = (u8)((r >> 7) < (s32)mis_occ[ring][jm]);
    if (z < VIEW_ZMIN) {
        v->shown = 0;
        return;
    }
    v->shown = 1;
    v->x = (s16)((VIEW_OX4 + (s32)x * VIEW_S4 / z + 8) >> 4);
    v->y = (s16)((VIEW_OY4 - u * VIEW_S4 / z + 8) >> 4);
    v->len4 = (u16)(DART_LEN4 / z);
}
