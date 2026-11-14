/* radar.h: the radar's pure logic (M5 Task 3) — the Elite-style scanner of
 * the Vectrex game (vectrex-e-srg v1.0.0: src/radar.s, tools/gen_dome.py's
 * radar_k/radar_frame) mapped to the Neo Geo screen, plus the lock-on of
 * e-srg.c's lock_update. Like ship.c/missiles.c it touches no hardware and
 * tests/ builds it for the host too (tests/radar_sim).
 *
 * The radar's constants are one block, the user's to tune. The per-frame
 * maths keep to 16-bit operations: the rings' and azimuths' sine/cosine
 * factors are generated tables (build/radar_tables.h, tools/gen_radar.py),
 * and every product is muls.w/mulu.w-sized; the only division is one
 * divu.w for R/6. No floats, no libgcc calls (checked with objdump).
 *
 * Each flying missile within 6.0 radii of the sphere's centre is shown:
 * a spot on the ellipse (from its ring's polar angle and its on-screen
 * azimuth j = (phi + dome_angle) mod 240), a stick up to its height
 * h = R/6 * H * cos(theta)^RADAR_H_POW, and a heading line from the
 * stick's top toward the ellipse's centre — 1/4 of the way (radar.s's
 * HEAD_SHIFT), or 1/2 when locked, because a locked missile flies straight
 * at the ship. The spot turns with the dome: a missile on the near side
 * (cos j > 0) sits in the lower half of the ellipse (y down).
 *
 * Lock-on (e-srg.c lock_update): while the ship is at rest (move_left ==
 * 0), a flying missile in range aimed at the ship's cell (ring, phi) is
 * LOCKED: its heading line is twice as long, and the ellipse blinks bright
 * while locked and (lock_t / RADAR_BLINK) is odd. lock_t counts frames
 * while locked, wraps at 256 (u8) and resets to 0 when not.
 */
#ifndef ESRG_RADAR_H
#define ESRG_RADAR_H
#include <ngdevkit/types.h>
#include "dome.h"                /* DOME_Y: RADAR_CY = DOME_Y + 112 */
#include "missiles.h"            /* mis_t, mis_obj_t, NMIS */
#include "ship.h"                /* ship_t */

/* ---- the radar's constants (screen px) — the user's tuning block ---- */
#define RADAR_CX      38              /* the ellipse's centre */
#define RADAR_CY      (DOME_Y + 112)      /* the ellipse's centre: the radar
                                           * keeps its place beside the dome's
                                           * rim (DOME_Y + 112), so lifting
                                           * the dome lifts the radar with it */
#define RADAR_RX      30              /* x radius */
#define RADAR_RY      84              /* y radius 8.4 px = RX * 0.28 (the
                                       * Vectrex's RADAR_FLAT), in tenths */
#define RADAR_H       30              /* stick height for a missile at 6.0
                                       * radii straight up */
#define RADAR_H_POW   2               /* ~ R/6 * cos(theta)^POW, as on the
                                       * Vectrex */
#define RADAR_RANGE   (6 << 19)       /* 6.0 radii, in 2^-19 radii (the
                                       * Vectrex's RADAR_RANGE): strictly
                                       * inside is shown */
#define RADAR_BLINK   5               /* the ellipse's blink period: 4 Vectrex
                                       * frames x 59/50, rounded */
#define RADAR_HEAD_SHIFT     2        /* the heading ends 1/2^SHIFT = 1/4 of
                                       * the way from the top to the centre
                                       * (radar.s's HEAD_SHIFT) */
#define RADAR_HEAD_SHIFT_LOCKED 1     /* locked: 1/2 (HEAD_SHIFT - 1) */

typedef struct {
    u8 shown;                /* 1: a flying missile within the radar's range */
    u8 locked;               /* 1: shown and aimed at the ship's resting cell */
    s16 sx, sy;              /* the spot on the ellipse (px, y down) */
    u8 h;                    /* the stick height (px): its top is (sx, sy - h) */
    s16 hx, hy;              /* the heading's end (px): from the top toward
                              * (RADAR_CX, RADAR_CY), 1/4 (locked 1/2) */
} radar_blip_t;

typedef struct {
    radar_blip_t blip[NMIS]; /* one per missile slot (bullets are never shown) */
    u8 lock_t;               /* frames while locked (resets to 0) */
    u8 locked;               /* some blip is locked this frame */
    u8 ellipse_bright;       /* the ellipse blinks bright while locked and
                              * (lock_t / RADAR_BLINK) & 1, else dim */
} radar_t;

/* (phi + dome_angle) mod 240 — the on-screen azimuth (the spot turns with
 * the dome, one turn per 240 steps; the near side, cos j > 0, is the
 * ellipse's lower half). */
u8 radar_j(u8 phi, u8 dome_angle);

/* the pure per-missile blip: from its ring, its on-screen azimuth j and
 * its distance r (2^-19 radii), whether it is locked. Out of range, the
 * blip is empty (shown 0, everything 0). The heading ends
 * 1/2^RADAR_HEAD_SHIFT of the way to the centre (one less shift when
 * locked): radar.s's HEAD_SHIFT, checked against that file. */
void radar_blip(radar_blip_t *b, u8 ring, u8 j, s32 r, u8 locked);

/* once per frame, after the ship's move and the missiles update (the
 * Vectrex runs lock_update after game_step): fills out->blip from every
 * missile slot and advances the lock state (out->lock_t is carried between
 * frames; the rest is written fresh). dome_angle = ship.dome_angle. */
void radar_frame(radar_t *out, const mis_t *m, const ship_t *s);
/* ESRG_RADAR_H */
#endif
