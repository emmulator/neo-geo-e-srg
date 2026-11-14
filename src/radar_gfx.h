/* radar_gfx.h: the radar's drawing (M5 Task 4) — from the radar_t the
 * logic produced (src/radar.c, Task 3) to the sprite slots the Task 1 map
 * reserved (RADAR_SPRITE .. +RADAR_COUNT-1, slot 219..237).
 *
 * Three kinds of sprite:
 *
 *   FRAME — the static picture (the ellipse + the Vectrex's roof), 4 x 2
 *       tiles (64 x 32 px) centred on (RADAR_CX, RADAR_CY), drawn by 4
 *       sprite slots (one per 16-px column, each 2 tiles tall). It never
 *       moves, so its SCB1/SCB2/SCB3/SCB4 are written once at init; the
 *       only per-frame radar thing it needs is the palette blink.
 *
 *   STICKS — one sprite per missile: a 1-tile-wide, 3-tile-tall (48 px)
 *       picture (a vertical line ending at the picture's bottom row),
 *       placed so the line's foot is the spot (sx, sy). The picture's
 *       tile depends on the stick's height h and whether the blip is
 *       locked (2 px wide); the tile changes as h changes, so the stick's
 *       SCB1 column is rewritten each shown frame.
 *
 *   HEADINGS — one sprite per missile: the heading line from the stick's
 *       top toward the ellipse's centre, drawn by hardware-shrinking a
 *       pre-rendered 16 x 16 staircase diagonal (tile
 *       RADAR_HEAD_TILE_BASE + (dy * (RADAR_HEAD_MAX+1) + dx) * 2 + hflip,
 *       hflip = (sdx < 0) XOR (sdy < 0) — the art is solved against the
 *       Neo Geo's zoom tables so the drawn line lands where the physics
 *       says). Horizontal shrink hz = |dx| - 1 (nibble), vertical vz =
 *       the zoom byte that draws exactly |dy| box lines (generated table);
 *       the box's corner that must hold the stick's top is placed per the
 *       direction (see radar_gfx.c's comment). Each missile keeps 4
 *       heading slots reserved; the runtime uses slot 0 of them and hides
 *       the other 3 (they stay hidden: SCB3 height 0).
 *
 * The palette: one bank (RADAR_PAL_BANK, the next free after the stars'
 * 8..19), entry 1 = the dim colour, bright = radar_pal_bright; the lock-on
 * blink writes exactly this one entry each frame (radar.ellipse_bright).
 * The leftover boot-test plants garbage in the heading slots (they shrink,
 * the only radar sprites that can show rows below the picture), so the
 * heading's SCB1 rows 1..31 are re-blanked every shown frame.
 */
#ifndef RADAR_GFX_H
#define RADAR_GFX_H
#include <ngdevkit/types.h>
#include "slots.h"            /* RADAR_SPRITE, RADAR_COUNT */
#include "radar.h"            /* radar_t */
#include "radar_map.h"        /* the tile bases + palette (build) */

/* the next free palette bank: 0 text, 1 dome, 2 ship, 3 missile, 4 bullet,
 * 5 explosion, 6 broken overlays, 7 HUD, 8..19 the stars' 12 banks */
#define RADAR_PAL_BANK 20
#define RADAR_FRAME_SLOTS 4               /* the 4x2-tile picture: one 16-px
                                           * column per slot */
#define RADAR_HEADING_SLOTS 4             /* reserved per missile (3 hidden) */

/* once at boot: the palette, the frame's sprites, the stick/heading slots'
 * SCB2 (full size) and SCB3 (hidden until the first show). */
void radar_gfx_init(void);

/* once per frame, after radar_frame (and after every other draw: the radar
 * is the topmost slot range): places every blip's stick and heading, hides
 * the rest, and writes the ellipse's palette entry (dim or bright). */
void radar_gfx_show(const radar_t *radar);

#endif
