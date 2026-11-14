/* ship.h: the ship's moves and jumps from cell to cell on the dome, ported
 * from the Vectrex game (e-srg.c ship_input/cell_toward, ship_move.s). Pure
 * logic, no hardware access: tests/ builds it with the host gcc too. */
#ifndef SHIP_H
#define SHIP_H
#include <ngdevkit/neogeo.h>

/* the Vectrex's 16 and 24 frames at 50 Hz, x1.18 for the Neo Geo's 59.2 Hz */
#define SHIP_MOVE_FRAMES 19
#define SHIP_JUMP_FRAMES 28
#define SHIP_LIFT_PX     12     /* top of the jump arc: 18 x 2/3 (Dome-scenery
                                 * Task 2; the full dome's 18 was the Vectrex's
                                 * 24 DAC units) */
#define SHIP_TURN        240    /* dome rotation steps per turn */
/* spinning at the peak: the Vectrex's one step per 50 Hz frame, so 50 steps
 * every 59 frames here (the first frame of a spin steps at once) */
#define SHIP_SPIN_NUM    50
#define SHIP_SPIN_DEN    59

typedef struct {
    u8 dome_angle;     /* 0..239: the rotation that brings the ship's cell to the front */
    u8 lat;            /* ship latitude view: 0 = on the peak .. SHIP_LATS-1 */
    u8 cell;           /* the ship's cell, or the destination while moving */
    u8 move_left;      /* frames left in the move or jump, 0 = at rest */
    u8 mlen;           /* frames in this move (SHIP_MOVE_FRAMES or SHIP_JUMP_FRAMES) */
    u8 lift;           /* mid-jump: the ship drawn this many px up */
    u8 jump_req;       /* jump pressed: jump once the ship rests */
    u8 last_dir;       /* the stick's last direction, for a jump with it centred */
    u8 jumped;         /* M7: 1 on the frame a jump started (sound: SND_JUMP) */
    u8 spinning;       /* spun at the peak last frame (paces the spin) */
    u8 spin_acc;       /* the spin's pacing: += SHIP_SPIN_NUM a frame, a step per SHIP_SPIN_DEN */
    s32 acc_s, acc_l;  /* rotation and latitude while moving, 16.16 */
    s32 inc_s, inc_l;  /* per frame */
    u8 broken[10];     /* broken cells, a bit each (cracks arrive in M4) */
    u8 heading;        /* 0..7: the drawing heading, h = ship_dir / 4 (H4) */
} ship_t;

void ship_reset(ship_t *s);                        /* at rest on CELL_START */
void ship_place(ship_t *s, u8 cell);               /* at rest on any cell, clears broken */
void ship_locate(ship_t *s, u8 cell);              /* at rest on any cell, keeps broken */
void ship_set_broken(ship_t *s, u8 cell);
u8 ship_dir(u8 input);         /* bios_p1current -> 0..31 (0 right, 8 up, 16 left, 24 down); 255 = centred */
u8 ship_heading(u8 d);         /* d / 4: the drawing heading for a stick direction */
u8 cell_toward(u8 c, u8 d);    /* c's neighbour nearest direction d (< 45 deg off); 255 = none */
/* once per frame: input = bios_p1current, pressed = bios_p1change (B = jump) */
void ship_frame(ship_t *s, u8 input, u8 pressed);
#endif
