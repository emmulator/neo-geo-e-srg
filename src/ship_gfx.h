/* ship_gfx.h: the ship's pre-rendered sprite (2 columns of 2 tiles), drawn
 * over the dome at its latitude view and lifted mid-jump. The two columns
 * are a sticky chain (column 1's SCB3 is the sticky word 1<<6); hiding
 * clears only the driver's SCB3, so the chain survives a death and the
 * respawned ship is whole (see ship_gfx.c). */
#ifndef SHIP_GFX_H
#define SHIP_GFX_H
#include <ngdevkit/types.h>

#define PAL_SHIP    2        /* palette bank */
#include "slots.h"           /* SHIP_SPRITE: the one slot map (M5 Task 1) */

void ship_gfx_init(void);
void ship_gfx_show(u8 lat, u8 lift);    /* once per frame */
void ship_gfx_hide(void);               /* while dead (the Vectrex stops drawing it) */
void ship_gfx_centre(u8 lat, s16 *x, s16 *y);  /* the resting ship's centre on screen */
#endif
