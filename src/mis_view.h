/* mis_view.h: where a missile or bullet appears on screen. Pure logic (no
 * hardware): tests/ builds it on the host too. */
#ifndef MIS_VIEW_H
#define MIS_VIEW_H
#include <ngdevkit/neogeo.h>

typedef struct {
    u8 shown;        /* 0: in front of the camera's near limit, not drawn */
    u8 behind;       /* 1: the dome is between it and the camera */
    s16 x, y;        /* its tip, in the dome box (px; add DOME_X, DOME_Y) */
    u16 len4;        /* the dart's length on screen, Q4 px */
} mis_view_t;

/* the point at distance r (2^-19 radii) on ring `ring`, at screen azimuth
 * j = cell azimuth + dome rotation (0..239 steps) */
void mis_view(mis_view_t *v, u8 ring, u8 j, s32 r);
#endif
