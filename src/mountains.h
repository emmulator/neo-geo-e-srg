/* mountains.h: the mountain band on the horizon (dome-scenery Task 16) — a
 * 960 px panorama that scrolls sideways as the dome turns.
 *
 * The picture is tools/render_mountains.py's (the orchestrator's art, never
 * edited for the picture or palette here): MTN_COLS (60) x MTN_ROWS (3)
 * 16x16 tiles, 960 x 48 px, its bottom row on the horizon at MTN_Y 52
 * (GROUND_Y 100 - 48). One turn of the dome (dome_angle 0..239) is the
 * whole panorama, so the scroll s = da * 960 / 240 = 4 * da px,
 * 0..956, and the screen shows panorama columns s .. s + 319 (mod 960): as
 * the angle grows the mountains move LEFT.
 *
 * The chain is MTN_SHOWN (21) full-size 16-px columns, 21 x 16 = 336 covers
 * 320 px at any 16-px phase. Its driver X is -(s & 15) (a 9-bit value, so
 * 512 - (s & 15) when that is not 0), chain column k shows panorama column
 * ((s >> 4) + k) mod 60 (a conditional subtract, never a %), in slots
 * MTN_SPRITE .. MTN_SPRITE + MTN_SHOWN - 1 (src/slots.h: right after the
 * ground, so the mountains draw over nothing but the grass and under
 * everything else). The palette bank is PAL_MTN (9), holding mtn_pal.
 *
 * Per frame: mountains_frame only computes s from ship.dome_angle and writes
 * the driver's X, unless s >> 4 changed since the last frame (or it is the
 * first frame after a show), when it rewrites the 21 columns' SCB1 (21 x
 * MTN_ROWS x 2 = 126 words). mountains_show (a game start, after a hide)
 * writes the palette bank and the chain's SCB2/SCB3 once: the driver's Y
 * and height, and the full-size zoom for every column (the followers
 * inherit Y and height but NOT the horizontal zoom, so each needs 0x0fff).
 * No % and no 32-bit / or * in the per-frame code: the scroll is a
 * 16-bit shift (4 * da, no rounding and no divide).
 *
 * mountains_show / mountains_hide are called exactly where ground_show /
 * ground_hide are (src/flow.c): hidden on the title, shown at a game start,
 * and also while the dome is gone (the mountains are scenery, not the dome).
 */
#ifndef MOUNTAINS_H
#define MOUNTAINS_H
#include <ngdevkit/types.h>
#include "slots.h"            /* MTN_SPRITE, MTN_COUNT */
#include "mountain_map.h"     /* MTN_Y/COLS/ROWS + mtn_pal (build) */
#include "radar_map.h"        /* RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES */
#include "ground_map.h"       /* GROUND_TILES: the mountain part follows it */

/* the next free palette bank after PAL_GROUND 8 (the radar owns 20) */
#define PAL_MTN 9

/* 21 x 16 = 336 px covers a 320 px screen at any 16-px phase */
#define MTN_SHOWN MTN_COUNT      /* 21: the band must follow slots.h */

/* the mountain part's first tile in the assembled C ROM: the Makefile emits
 * the C ROM parts in CROM1_PARTS order (dome, ship, missiles, broken,
 * radar's frame/sticks/headings, the ground, then the mountains), so the
 * mountains start exactly where the ground's GROUND_TILES end. The header's
 * tile numbers are relative to this part (tile (col, row) = col * MTN_ROWS
 * + row); every fetch below adds this base. */
#define MTN_TILE_BASE (RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES + GROUND_TILES)

/* once when a game begins (and on any show): the 21 columns' SCB1 tiles, the
 * sticky chain (SCB3 at MTN_Y with MTN_ROWS tiles, followers sticky and 16
 * px apart; every column's SCB2 full size, since a sticky follower does not
 * inherit horizontal zoom), the palette bank, and the first frame's driver X. */
void mountains_show(u8 dome_angle);

/* hide every column (SCB3 height 0) — the title, and a fresh entry before
 * any game has begun. */
void mountains_hide(void);

/* once per frame in play, next to ground_frame: from ship.dome_angle, write
 * the driver's X; rewrite the columns' SCB1 only when s >> 4 changed. */
void mountains_frame(u8 dome_angle);
#endif
