/* radar_gfx.h: the radar's drawing (M5 Task 4) — from the radar_t the
 * logic produced (src/radar.c, Task 3) to the sprite slots the Task 1 map
 * reserved (RADAR_SPRITE .. +RADAR_COUNT-1, slot 169..187 since
 * Dome-scenery Task 2's smaller missile/explosion pictures).
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
 *       SCB1 column is rewritten only when that picture changes.
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
 * The palette (Task 10): two banks. RADAR_PAL_BANK (20) holds all of
 * radar_pal — 1 the dim amber rim/roof, 2..4 the disc's fill/rings/bezel —
 * and the lock-on blink writes only its entry 1 when it changes
 * (radar.ellipse_bright: dim radar_pal[1] / bright radar_pal_bright).
 * RADAR_STICK_PAL_BANK (21) holds radar_stick_pal and is written once at
 * init; the sticks' and headings' SCB1 palette is 21, the frame's stays 20,
 * so the sticks are steady red-orange and never blink. The leftover
 * boot-test plants garbage in the heading slots (they shrink, the only
 * radar sprites that can show rows below the picture), so the heading's
 * SCB1 rows 1..31 are re-blanked whenever the slot is first shown after a
 * hide.
 *
 * Task 18b: radar_gfx_prepare computes the per-frame slots and the blink
 * into RAM (no VRAM or palette writes); radar_gfx_commit writes only the
 * changes right after ng_wait_vblank(), with the missiles' and props'
 * commits. radar_gfx_init and radar_gfx_hide still write directly (they run
 * outside play frames).
 */
#ifndef RADAR_GFX_H
#define RADAR_GFX_H
#include <ngdevkit/types.h>
#include "slots.h"            /* RADAR_SPRITE, RADAR_COUNT */
#include "radar.h"            /* radar_t */
#include "radar_map.h"        /* the tile bases + palette (build) */

/* the radar's palette banks: 0 text, 1 dome, 2 ship, 3 missile, 4 bullet,
 * 5 explosion, 6 broken overlays, 7 HUD, 8..19 the stars' retired banks,
 * 20 the radar frame's, 21 the sticks'/headings' (Task 10). */
#define RADAR_PAL_BANK 20
#define RADAR_STICK_PAL_BANK 21
#define RADAR_FRAME_SLOTS 4               /* the 4x2-tile picture: one 16-px
                                           * column per slot */
#define RADAR_HEADING_SLOTS 4             /* reserved per missile (3 hidden) */

/* once at boot and at every game start: the palette, the frame's sprites,
 * the stick/heading slots' SCB2 (full size) and SCB3 (hidden until the first
 * show), and a cleared per-frame memo. */
void radar_gfx_init(void);

/* hide every radar slot directly (SCB3 0, the title and every entry) and
 * forget the per-frame memo. */
void radar_gfx_hide(void);

/* once per play frame, where radar_gfx_show ran: compute the sticks,
 * headings and the ellipse's blink into RAM with no VRAM or palette
 * writes. */
void radar_gfx_prepare(const radar_t *radar);

/* right after ng_wait_vblank, with the missiles' and props' commits: write
 * the prepared blink and slot words (only the ones that changed). */
void radar_gfx_commit(void);

#endif
