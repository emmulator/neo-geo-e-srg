/* ship.c: see ship.h. The comments name the Vectrex code each part ports. */
#include <ngdevkit/neogeo.h>
#include "ship.h"
#include "cells.h"

#define TURN_FP ((s32)SHIP_TURN << 16)

static u8 is_broken(const ship_t *s, u8 c)
{
    return (u8)(s->broken[c >> 3] & (1 << (c & 7)));
}

void ship_set_broken(ship_t *s, u8 cell)
{
    s->broken[cell >> 3] |= (u8)(1 << (cell & 7));
}

void ship_place(ship_t *s, u8 cell)
{
    u8 i;

    s->cell = cell;
    s->dome_angle = cell_step[cell];
    s->lat = cell_lat[cell];
    s->move_left = s->mlen = s->lift = s->jump_req = 0;
    s->last_dir = 8;                     /* up */
    s->jumped = 0;                       /* M7: no jump on a place/respawn frame */
    s->spinning = s->spin_acc = 0;
    s->acc_s = s->acc_l = s->inc_s = s->inc_l = 0;
    for (i = 0; i < sizeof s->broken; i++)
        s->broken[i] = 0;
}

/* as ship_place, but keeps the broken bits: respawn lands on the start cell
 * or the next whole one while old cracks stay (rules.c) */
void ship_locate(ship_t *s, u8 cell)
{
    s->cell = cell;
    s->dome_angle = cell_step[cell];
    s->lat = cell_lat[cell];
    s->move_left = s->mlen = s->lift = s->jump_req = 0;
    s->jumped = 0;                       /* M7: no jump on a respawn */
    s->spinning = s->spin_acc = 0;
    s->last_dir = 8;
    s->acc_s = s->acc_l = s->inc_s = s->inc_l = 0;
}

void ship_reset(ship_t *s)
{
    ship_place(s, CELL_START);
}

u8 ship_dir(u8 input)
{
    static const u8 dirs[3][3] = {       /* [y + 1][x + 1], y up */
        { 20, 24, 28 },                  /* down-left, down, down-right */
        { 16, 255, 0 },                  /* left, centred, right */
        { 12, 8, 4 },                    /* up-left, up, up-right */
    };
    s8 x = 0, y = 0;

    if (input & CNT_RIGHT)
        x++;
    if (input & CNT_LEFT)
        x--;
    if (input & CNT_UP)
        y++;
    if (input & CNT_DOWN)
        y--;
    return dirs[y + 1][x + 1];
}

/* e-srg.c cell_toward */
u8 cell_toward(u8 c, u8 d)
{
    const u8 *a = cell_adj[c];
    u8 i, e, best = 255, bd = 32, want = (u8)(d << 3);

    for (i = 0; i < 6 && a[1] != 255; i++, a += 2) {
        e = (u8)(a[0] - want);
        if (e & 0x80)
            e = (u8)-e;
        if (e < bd) {
            bd = e;
            best = a[1];
        }
    }
    return best;
}

/* ship_move.s start: rotation and latitude run linearly to the cell's (the
 * dome turned the short way round; the peak: no turn) */
static void start(ship_t *s, u8 to, u8 len)
{
    s16 ds = 0;

    s->mlen = s->move_left = len;
    s->cell = to;
    s->jumped = (u8)(len == SHIP_JUMP_FRAMES);  /* M7: a jump just started
                                                 * (sound: SND_JUMP) */
    if (to != 0) {
        ds = (s16)((s16)cell_step[to] - s->dome_angle);
        if (ds > SHIP_TURN / 2)
            ds -= SHIP_TURN;
        else if (ds < -SHIP_TURN / 2)
            ds += SHIP_TURN;
    }
    s->inc_s = ((s32)ds << 16) / len;
    s->inc_l = ((s32)((s16)cell_lat[to] - s->lat) << 16) / len;
    s->acc_s = (s32)s->dome_angle << 16;
    s->acc_l = (s32)s->lat << 16;
}

/* ship_move.s move_step: one frame of a move; the last lands exactly */
static void move_step(ship_t *s)
{
    s->acc_s += s->inc_s;
    if (s->acc_s >= TURN_FP)
        s->acc_s -= TURN_FP;
    else if (s->acc_s < 0)
        s->acc_s += TURN_FP;
    s->dome_angle = (u8)((s->acc_s + 0x8000) >> 16);
    if (s->dome_angle >= SHIP_TURN)
        s->dome_angle = 0;
    s->acc_l += s->inc_l;
    s->lat = (u8)((s->acc_l + 0x8000) >> 16);
    s->move_left--;
    if (s->mlen == SHIP_JUMP_FRAMES) {   /* arc: 4 h k (n - k) / n^2 */
        u32 k = s->move_left, n = SHIP_JUMP_FRAMES;
        s->lift = (u8)(4u * SHIP_LIFT_PX * k * (n - k) / (n * n));
    }
    if (s->move_left == 0) {
        s->lift = 0;
        if (s->cell != 0)
            s->dome_angle = cell_step[s->cell];
        s->lat = cell_lat[s->cell];
    }
}

/* the peak's spin, paced to the Vectrex's 50 steps a second: a spin's first
 * frame steps, then SHIP_SPIN_NUM of every SHIP_SPIN_DEN frames do */
static u8 spin_due(ship_t *s, u8 was)
{
    s->spinning = 1;
    if (!was)
        s->spin_acc = SHIP_SPIN_DEN - SHIP_SPIN_NUM;
    s->spin_acc += SHIP_SPIN_NUM;
    if (s->spin_acc < SHIP_SPIN_DEN)
        return 0;
    s->spin_acc -= SHIP_SPIN_DEN;
    return 1;
}

/* e-srg.c ship_input (and the jump request from its main loop) */
void ship_frame(ship_t *s, u8 input, u8 pressed)
{
    u8 d, v, m, was = s->spinning;

    s->jumped = 0;                   /* M7: the frame's jump flag (cleared at
                                      * the frame's start, set by start()) */
    s->spinning = 0;
    if (pressed & CNT_B)
        s->jump_req = 1;
    if (s->move_left) {                  /* input waits until the move lands */
        move_step(s);
        return;
    }
    d = ship_dir(input);
    if (d == 255) {                      /* centred: only a jump moves, */
        if (!s->jump_req)                /* the way the stick last pointed */
            return;
        d = s->last_dir;
    } else
        s->last_dir = d;
    v = (u8)(s->dome_angle % CELL_VIEWS);
    if (s->jump_req) {                   /* two cells on, over the next one */
        s->jump_req = 0;
        if (s->cell != 0)
            m = cell_toward(s->cell, d);
        else
            m = (d >= 19 && d <= 29) ? peak_down[v] : 255;
        if (m != 255 && m != 0) {        /* (no jumping over the peak) */
            m = cell_toward(m, d);
            if (m != 255 && m != s->cell && !is_broken(s, m))
                start(s, m, SHIP_JUMP_FRAMES);
        }
        return;
    }
    if (s->cell != 0) {
        m = cell_toward(s->cell, d);
        if (m != 255 && !is_broken(s, m))    /* broken cells: jump over them */
            start(s, m, SHIP_MOVE_FRAMES);
        return;
    }
    if (d >= 19 && d <= 29) {            /* the peak: down-ish leaves it */
        if (!is_broken(s, peak_down[v]))
            start(s, peak_down[v], SHIP_MOVE_FRAMES);
    } else if ((input & (CNT_LEFT | CNT_RIGHT)) == CNT_RIGHT) {
        if (spin_due(s, was))
            s->dome_angle = (u8)(s->dome_angle == 0 ? SHIP_TURN - 1 : s->dome_angle - 1);
    } else if ((input & (CNT_LEFT | CNT_RIGHT)) == CNT_LEFT) {
        if (spin_due(s, was))
            s->dome_angle = (u8)(s->dome_angle == SHIP_TURN - 1 ? 0 : s->dome_angle + 1);
    }
}
