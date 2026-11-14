/* mis_gfx.h: missiles, bullets and explosions as sprites. A missile behind
 * the dome uses sprite slots below the dome's, so the dome covers it; one in
 * front uses slots above (the hardware draws higher slots over lower).
 *
 * Task 18b: the per-frame drawing is a prepare/commit pair, called with the
 * props' pair on play frames: mis_gfx_prepare computes the slot words and
 * pictures into RAM (no VRAM writes), and mis_gfx_commit writes only what
 * changed right after ng_wait_vblank(). mis_gfx_init and mis_gfx_hide write
 * directly (they run outside play frames). */
#ifndef MIS_GFX_H
#define MIS_GFX_H
#include <ngdevkit/types.h>
#include "missiles.h"

#define PAL_MISSILE  3          /* palette banks */
#define PAL_BULLET   4
#define PAL_EXPL     5
#define MIS_COLS_MAX 3          /* the largest picture: 3 columns of 3 tiles
                                 * (the 2/3 large dart; was 4 at the full dome) */
#include "slots.h"              /* the slot map (M5 Task 1): MIS_BEHIND_SPRITE
                                 * under the dome, MIS_FRONT_SPRITE over it and
                                 * the ship, EXPL_SPRITE over everything */
#define NEXPL        2
#define EXPL_TIME    38         /* frames an explosion lasts (the Vectrex's 32 x 59/50) */

void mis_gfx_init(void);
/* hide every missile/bullet/explosion slot directly (SCB3 0) and forget the
 * memo — the title, every entry, and game_begin (outside play frames). */
void mis_gfx_hide(void);
/* once per play frame, where mis_gfx_show ran: compute everything into RAM
 * with no VRAM writes. */
void mis_gfx_prepare(const mis_t *m, u8 dome_angle);
/* right after ng_wait_vblank, with the props' and radar's commits: write the
 * prepared slot words (only the ones that changed). */
void mis_gfx_commit(void);
/* an explosion centred at screen (x, y), shown from the next prepare: the
 * ship's death (e-srg.c kill_ship's explode_at) */
void mis_gfx_explode_at(s16 x, s16 y);
#endif
