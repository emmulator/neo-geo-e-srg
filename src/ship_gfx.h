/* ship_gfx.h: the ship's pre-rendered sprite (2 columns of 2 tiles), drawn
 * over the dome at its latitude view and lifted mid-jump. The two columns
 * are a sticky chain (column 1's SCB3 is the sticky word 1<<6); hiding
 * clears only the driver's SCB3, so the chain survives a death and the
 * respawned ship is whole (see ship_gfx.c).
 *
 * The stopper-spider (10-26) has 13 pictures per latitude: REST, 4 WALK, 4
 * JUMP and 4 HEAVE. The frame is chosen from the ship's state by
 * ship_frame_of(): walk at 4 frames / SHIP_MOVE_FRAMES while a move runs or
 * the ship spins at the peak, the jump's scrunch/launch/airborne/land over
 * SHIP_JUMP_FRAMES, the heave's 4 frames of 3 game frames from the frame a
 * shot leaves (a new shot restarts it), REST otherwise. The function is pure
 * and is host-built, so tests/ can hold it to a Python model frame by frame.
 *
 * The per-frame VRAM work is split as the props are (Task 18): prepare
 * stages the SCB1 tile list only when (heading, lat, frame) changed and the
 * driver's SCB3 Y every frame; commit writes them right after ng_wait_vblank,
 * so the ship's slots never tear. The heading is the ship's drawing state
 * (H4: h = ship_dir / 4); the SCB1 picture is ship_anim_tile[heading][lat]
 * [frame] and the Y ship_oy[heading][lat]. show/init/hide write at once
 * (they run outside a play frame or while the ship is hidden); show draws
 * the heading already in effect (a fresh game's 1). */
#ifndef SHIP_GFX_H
#define SHIP_GFX_H
#include <ngdevkit/types.h>
#include "ship.h"             /* ship_t: the frame choice's input */

#define PAL_SHIP    2        /* palette bank */
#include "slots.h"           /* SHIP_SPRITE: the one slot map (M5 Task 1) */

/* the animation state ship_frame_of carries from frame to frame: the walk
 * cycle's elapsed frames, the heave's elapsed frames (SHIP_HEAVE_NONE when
 * idle), and the previous frame's moving/steping flags (to show the last
 * walk picture on the frame a move ends, never a REST between a walk and a
 * jump that starts next frame). */
#define SHIP_HEAVE_NONE 0xff
#define SHIP_HEAVE_FRAMES 12     /* 4 pictures x 3 game frames */

typedef struct {
    u8 walk_t;          /* frames into the walk cycle: 0..SHIP_MOVE_FRAMES */
    u8 heave_t;         /* frames since the shot; SHIP_HEAVE_NONE = idle */
    u8 was_moving;      /* the previous frame the ship was moving/spinning */
    u8 was_move;        /* the previous frame's move_left was nonzero */
} ship_anim_t;

/* the animation at rest, as a fresh game / a respawn / a demo restart shows
 * it. Also clears a heave left over from the pose the ship died in. */
void ship_anim_rest(ship_anim_t *a);

/* the picture for this frame, from the ship's state after its logic and
 * this frame's shot event (mis.sfx & SFX_FIRE). Updates *a. The timing is
 * the design's: walk = F_WALK + (elapsed * 4 / SHIP_MOVE_FRAMES), the jump's
 * four poses over SHIP_JUMP_FRAMES, the heave's 4 x 3 game frames from a
 * shot (restarted by a new shot), REST otherwise. */
u8 ship_frame_of(const ship_t *s, u8 shot, ship_anim_t *a);

void ship_gfx_init(void);

/* once per play frame, after the frame's logic: choose the frame from the
 * ship's state (the shot event this frame) and stage the changed SCB1 tile
 * list and the driver's Y. */
void ship_gfx_prepare(const ship_t *s, u8 shot);

/* right after ng_wait_vblank on every play frame: write what
 * ship_gfx_prepare staged. */
void ship_gfx_commit(void);

/* draw at once (outside a play frame: a game start / the entry's scene):
 * stage nothing, write the picture and Y now. The heading is the one already
 * in effect: ship_gfx_init sets a fresh game's 1 (up-right). */
void ship_gfx_show(u8 lat, u8 lift, u8 frame);

/* reset the animation to REST (a demo restart, a new game). */
void ship_gfx_anim_reset(void);

void ship_gfx_hide(void);               /* while dead (the Vectrex stops drawing it) */
void ship_gfx_centre(u8 lat, s16 *x, s16 *y);  /* the resting ship's centre on screen, heading shown */
#endif
