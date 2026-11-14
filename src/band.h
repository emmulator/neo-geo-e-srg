/* band.h: the band of towns and forests on the horizon (dome-scenery
 * Task 17) — an 768 px panorama that scrolls sideways as the dome turns,
 * in front of the mountains.
 *
 * The picture is tools/render_band.py's (the orchestrator's art, never
 * edited for the picture or palette here): BAND_COLS (48) x BAND_ROWS (2)
 * 16x16 tiles, 768 x 32 px, its bottom row on the horizon at BAND_Y 68
 * (GROUND_Y 100 - 32). One turn of the dome (dome_angle 0..239) is the
 * whole panorama, so the scroll s = round(da * 768 / 240) =
 * (16 * da + 2) / 5 px, 0..765, and the screen shows panorama columns s ..
 * s + 319 (mod 768): as the angle grows the band moves LEFT. The band is
 * nearer than the mountains, so it moves less (768 px a turn, the
 * mountains 960).
 *
 * The chain is BAND_SHOWN (21) full-size 16-px columns, 21 x 16 = 336 covers
 * 320 px at any 16-px phase. Its driver X is -(s & 15) (a 9-bit value, so
 * 512 - (s & 15) when that is not 0), chain column k shows panorama column
 * ((s >> 4) + k) mod 48 (a conditional subtract, never a %), in slots
 * BAND_SPRITE .. BAND_SPRITE + BAND_SHOWN - 1 (src/slots.h: right after the
 * mountains and before the back props, so the band draws over the mountains
 * and under every prop). The palette bank is PAL_BAND (12), holding
 * band_pal.
 *
 * Per frame: band_frame only computes s from ship.dome_angle and writes the
 * driver's X, unless s >> 4 changed since the last frame (or it is the
 * first frame after a show), when it rewrites the 21 columns' SCB1 (21 x
 * BAND_ROWS x 2 = 84 words). band_show (a game start, after a hide) writes
 * the palette bank and the chain's SCB2/SCB3 once: the driver's Y and
 * height, and the full-size zoom for every column (the followers inherit Y
 * and height but NOT the horizontal zoom, so each needs 0x0fff).
 * No % and no 32-bit / or * in the per-frame code: 16 * 239 + 2 = 3826
 * fits a u16, so the scroll is one 16-bit division by the constant 5.
 *
 * band_show / band_hide are called exactly where mountains_show /
 * mountains_hide are (src/flow.c): hidden on the title and at every entry,
 * shown at a game start, and also while the dome is gone (the band is
 * scenery, not the dome).
 */
#ifndef BAND_H
#define BAND_H
#include <ngdevkit/types.h>
#include "slots.h"            /* BAND_SPRITE, BAND_COUNT */
#include "props.h"            /* PROP_TILE_BASE + PROP_TILES: the band follows */
#include "band_map.h"         /* BAND_Y/W/COLS/ROWS + band_pal (build) */

/* the next free palette bank after PAL_CON 10 and PAL_HUD_PLAY 11 (the
 * radar owns 20 and 21, the props 22..43) */
#define PAL_BAND 12

/* 21 x 16 = 336 px covers a 320 px screen at any 16-px phase */
#define BAND_SHOWN BAND_COUNT      /* 21: the band must follow slots.h */

/* the band part's first tile in the assembled C ROM: the Makefile emits the
 * C ROM parts in CROM1_PARTS order (dome, ship, missiles, broken, radar's
 * frame/sticks/headings, the ground, the mountains, the console, the props,
 * then the band), so the band starts exactly where the props' PROP_TILES
 * end. The header's tile numbers are relative to this part (tile (col, row)
 * = col * BAND_ROWS + row); every fetch below adds this base. The band is
 * LAST so no existing tile base moves. */
#define BAND_TILE_BASE (PROP_TILE_BASE + PROP_TILES)

/* once when a game begins (and on any show): the 21 columns' SCB1 tiles, the
 * sticky chain (SCB3 at BAND_Y with BAND_ROWS tiles, followers sticky and 16
 * px apart; every column's SCB2 full size, since a sticky follower does not
 * inherit horizontal zoom), the palette bank, and the first frame's driver X. */
void band_show(u8 dome_angle);

/* hide every column (SCB3 height 0) — the title, and a fresh entry before
 * any game has begun. */
void band_hide(void);

/* once per frame in play, next to mountains_frame: from ship.dome_angle,
 * write the driver's X; rewrite the columns' SCB1 only when s >> 4 changed. */
void band_frame(u8 dome_angle);
#endif
