/* entry.c: see entry.h. The ring's phase, the short-way animation, the
 * hold-repeat timing and the pick rules; no hardware access beyond the
 * generated ring header's constants and codes. */
#include <ngdevkit/neogeo.h>
#include "entry.h"
#include "ring_map.h"

#define END_POS    (RING_N - 1)
#define END_PHASE  (END_POS * RING_SUB)

/* one position step (RING_SUB phases) with wrap. Both operands are small,
 * so these avoid a division. */
static u8 pos_add(u8 p, u8 d)
{
    u16 t = (u16)p + d;

    if (t >= RING_PHASES)
        t -= RING_PHASES;
    return (u8)t;
}

static u8 pos_sub(u8 p, u8 d)
{
    u16 t = p;

    if (t < d)
        t += RING_PHASES;
    return (u8)(t - d);
}

void entry_begin(entry_t *e)
{
    e->phase = 0;
    e->target = 0;
    e->ninit = 0;
    e->init[0] = e->init[1] = e->init[2] = 0;
    e->hold = 0;
    e->dir = 0;
    e->done = 0;
    e->sfx = 0;
    e->fly_t = 0;
    e->fly_k = 0;
}

/* one later frame of a flight: the frame that would pass FLY_FRAMES is the
 * landing (fly_t 0, pick + 20). */
static void entry_flight(entry_t *e)
{
    if (e->fly_t == 0)
        return;
    e->fly_t++;
    if (e->fly_t > FLY_FRAMES)
        e->fly_t = 0;
}

/* a new press steps at once; a held direction repeats after
 * ENTRY_REPEAT_FIRST frames, then every ENTRY_REPEAT_EVERY. After the third
 * initial the ring is on its way to END, so directions are ignored (a
 * fourth letter can never be picked). */
static void entry_direction(entry_t *e, u8 cur, u8 change)
{
    u8 dir;

    if (change & CNT_RIGHT) {
        dir = 1;
        e->hold = 0;
    } else if (change & CNT_LEFT) {
        dir = 2;
        e->hold = 0;
    } else if (e->dir == 1 && (cur & CNT_RIGHT)) {
        if (++e->hold < ENTRY_REPEAT_FIRST)
            return;             /* still inside the first delay */
        e->hold = ENTRY_REPEAT_FIRST - ENTRY_REPEAT_EVERY;
        dir = 1;
    } else if (e->dir == 2 && (cur & CNT_LEFT)) {
        if (++e->hold < ENTRY_REPEAT_FIRST)
            return;
        e->hold = ENTRY_REPEAT_FIRST - ENTRY_REPEAT_EVERY;
        dir = 2;
    } else {
        if (e->dir != ENTRY_DIR_JUMP)   /* the jump runs on with no press */
            e->dir = 0;
        e->hold = 0;
        return;
    }

    e->dir = dir;
    if (dir == 1)
        e->target = pos_add(e->target, RING_SUB);
    else
        e->target = pos_sub(e->target, RING_SUB);
}

/* one sub-step toward the target the short way (forward on an exact tie) */
static void entry_move(entry_t *e)
{
    u16 fwd;

    if (e->phase == e->target)
        return;
    if (e->target >= e->phase)
        fwd = (u16)(e->target - e->phase);
    else
        fwd = (u16)e->target + RING_PHASES - e->phase;

    if (fwd <= RING_PHASES / 2)
        e->phase = pos_add(e->phase, 1);
    else
        e->phase = pos_sub(e->phase, 1);
    if ((e->phase % RING_SUB) == 0)
        e->sfx |= ENTRY_SFX_TICK;       /* a position reached the front */
}

/* pick the position at the front, only at rest */
static void entry_pick(entry_t *e, u8 change)
{
    u8 k, code, j;

    if (!(change & CNT_A))
        return;
    if (e->phase != e->target || (e->phase % RING_SUB) != 0)
        return;

    k = (u8)(e->phase / RING_SUB);
    code = ring_code[k];
    if (code == RING_ERASE) {
        e->fly_t = 0;                   /* an erase ends the flight first */
        if (e->ninit > 0) {
            e->ninit--;
            e->init[e->ninit] = 0;
            e->sfx |= ENTRY_SFX_BACK;   /* nothing to erase sends nothing */
        }
    } else if (code == RING_END) {
        e->fly_t = 0;                   /* END ends the flight first */
        e->done = 1;
        for (j = e->ninit; j < ENTRY_INIT_MAX; j++)
            e->init[j] = ' ';
        e->sfx |= ENTRY_SFX_BELL;
    } else if (e->ninit < ENTRY_INIT_MAX) {
        e->fly_t = 0;                   /* a new pick lands the old one */
        e->init[e->ninit] = code;
        e->ninit++;
        e->sfx |= ENTRY_SFX_TYPE;
        e->fly_k = k;
        e->fly_t = 1;                   /* the pick frame's flight */
        if (e->ninit == ENTRY_INIT_MAX) {
            e->target = END_PHASE;      /* the short way is entry_move's */
            e->dir = ENTRY_DIR_JUMP;
            e->hold = 0;
        }
    }
}

void entry_frame(entry_t *e, u8 cur, u8 change)
{
    e->sfx = 0;                         /* the frame's events start empty */
    if (e->done)
        return;
    entry_flight(e);                    /* a flying letter's next frame */
    entry_direction(e, cur, change);
    entry_move(e);
    if (e->dir == ENTRY_DIR_JUMP) {     /* the jump: a second sub-step */
        entry_move(e);
        if (e->phase == e->target)
            e->dir = 0;
    }
    entry_pick(e, change);
}

u8 entry_dome_angle(const entry_t *e, u8 base)
{
    /* base minus the phase's share of one 240-step turn, rounded to the
     * nearest step: the dome turns WITH the ring (the user's pick, 10-30),
     * so Right lowers the angle as Right spins the dome in play. The phase
     * is 0..RING_PHASES-1, so the share is 0..239 and base + 240 - share is
     * 1..479: one conditional subtract is the mod 240. */
    u16 a = (u16)((u16)e->phase * 240 + RING_PHASES / 2);

    a = (u16)(a / RING_PHASES);
    a = (u16)(base + 240 - a);
    if (a >= 240)
        a -= 240;
    return (u8)a;
}
