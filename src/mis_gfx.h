/* mis_gfx.h: missiles, bullets and explosions as sprites. A missile behind
 * the dome uses sprite slots below the dome's, so the dome covers it; one in
 * front uses slots above (the hardware draws higher slots over lower). */
#ifndef MIS_GFX_H
#define MIS_GFX_H
#include <ngdevkit/types.h>
#include "missiles.h"

#define PAL_MISSILE  3          /* palette banks */
#define PAL_BULLET   4
#define PAL_EXPL     5
#define MIS_COLS_MAX 4          /* the largest picture: 4 columns of 4 tiles */
#include "slots.h"              /* the slot map (M5 Task 1): MIS_BEHIND_SPRITE
                                 * under the dome, MIS_FRONT_SPRITE over it and
                                 * the ship, EXPL_SPRITE over everything */
#define NEXPL        2
#define EXPL_TIME    38         /* frames an explosion lasts (the Vectrex's 32 x 59/50) */

void mis_gfx_init(void);
/* once per frame, after mis_frame: draw everything with the dome at dome_angle */
void mis_gfx_show(const mis_t *m, u8 dome_angle);
/* an explosion centred at screen (x, y), shown from the next mis_gfx_show:
 * the ship's death (e-srg.c kill_ship's explode_at) */
void mis_gfx_explode_at(s16 x, s16 y);
#endif
