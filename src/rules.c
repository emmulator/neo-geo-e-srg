/* rules.c: see rules.h. The comments name the Vectrex code each part ports. */
#include <ngdevkit/neogeo.h>
#include "rules.h"
#include "cells.h"
#include "missiles.h"

/* the debug "ship is alive" flag (rules.h): the rules own dead_t and
 * game_over, so the flag is derived right here, once per frame, where the
 * rules_begin early branches settle it (main.c reads it only through the
 * boot probe; the drawing never uses it). */
u8 rules_dbg_alive;

static void rules_dbg_update(const rules_t *r)
{
    rules_dbg_alive = (u8)(!r->dead_t && !r->game_over);
}

void rules_reset(rules_t *r)
{
    u8 i;

    for (i = 0; i < 76; i++)
        r->broken[i] = 0;
    r->nbroken = 0;
    r->level = LEVEL_NORMAL;
    r->lives = 3;
    r->integ_pct = 100;
    r->dead_t = r->dome_dead = r->game_over = 0;
    rules_dbg_update(r);
}

/* e-srg.c is_broken, on the ship's bits (the one source of truth) */
static u8 is_broken(const ship_t *s, u8 c)
{
    return (u8)(s->broken[c >> 3] & (1 << (c & 7)));
}

/* e-srg.c surrounded: at = COLLAPSE_EASY - level; a rim cell with fewer
 * than `at` neighbours needs all of them (n < at ? n : at) */
static u8 surrounded(const rules_t *r, const ship_t *s, u8 c)
{
    const u8 *a = cell_adj[c] + 1;
    u8 i, n = 0, b = 0, at = (u8)(COLLAPSE_EASY - r->level);

    for (i = 0; i < 6 && *a != 255; i++, a += 2) {
        n++;
        if (is_broken(s, *a))
            b++;
    }
    return (u8)(b >= (n < at ? n : at));
}

/* e-srg.c break_tile: cell c breaks, then whole cells with enough broken
 * neighbours collapse too, and that can spread (todo holds the cells whose
 * neighbours have not been checked yet; the Vectrex's 16-entry stack).
 * Returns 1 when c broke, 0 when it was already broken — the v1.0.1 hits
 * rule: mis_update counts a dome hit only when the landing broke a whole
 * cell (break_tile's hits++ sits after its is_broken early return). */
u8 rules_break_cell(rules_t *r, ship_t *s, u8 c)
{
    u8 todo[16], ntodo = 0, x, i;
    const u8 *a;

    if (is_broken(s, c))                /* (missiles don't aim at broken cells) */
        return 0;
    ship_set_broken(s, c);
    r->broken[r->nbroken++] = c;
    todo[ntodo++] = c;
    while (ntodo) {
        x = todo[--ntodo];
        a = cell_adj[x] + 1;
        for (i = 0; i < 6 && *a != 255; i++, a += 2)
            if (!is_broken(s, *a) && surrounded(r, s, *a)) {
                ship_set_broken(s, *a);
                r->broken[r->nbroken++] = *a;
                if (ntodo < 16)
                    todo[ntodo++] = *a;
            }
    }
    return 1;
}

/* e-srg.c integrity_update: 100% less one 38th per broken cell (100 (n * 100
 * + 19) / 38), capped at 0 at DOME_LIMIT; a kill scores the current value.
 * The missiles read m->integ_pct when they score a kill (collide), so the
 * value is mirrored there — the Vectrex's single integ_pct, split across
 * the modules on this side. */
static void integrity_update(rules_t *r, mis_t *m)
{
    u8 n = r->nbroken;

    r->integ_pct = n >= DOME_LIMIT ? 0
        : (u8)(100 - ((u32)n * 100 + DOME_LIMIT / 2) / DOME_LIMIT);
    m->integ_pct = r->integ_pct;
}

/* e-srg.c kill_ship: everything in flight is cleared (its explosion is a
 * drawing concern, M4 Task 2), and it comes back after DEAD_FRAMES. On
 * NORMAL a death costs a life (any death); EASY's dome death is free,
 * HARD's ends the game (lives = 0). dome: the integrity was gone. */
static void kill_ship(rules_t *r, mis_t *m, ship_t *s, u8 dome)
{
    u8 i;

    for (i = 0; i < NOBJ; i++)
        m->obj[i].state = 0;
    s->move_left = 0;
    s->lift = 0;
    if (!dome || r->level == LEVEL_NORMAL)
        r->lives--;
    else if (r->level == LEVEL_HARD)
        r->lives = 0;
    r->dead_t = DEAD_FRAMES;
    r->dome_dead = dome;
}

/* e-srg.c new_dome */
static void new_dome(rules_t *r, ship_t *s)
{
    u8 i;

    r->nbroken = 0;
    for (i = 0; i < 10; i++)
        s->broken[i] = 0;
}

/* e-srg.c respawn: after a death the ship comes back on the start cell, or
 * the next whole one (wrapping past the last cell to 1); a dome death
 * rebuilds the dome first. The spawn timer is reset, so launches resume
 * from a fresh countdown. */
static void respawn(rules_t *r, ship_t *s, mis_t *m)
{
    u8 c = CELL_START;

    if (r->dome_dead)
        new_dome(r, s);
    while (is_broken(s, c))
        if (++c == 76)
            c = 1;
    ship_locate(s, c);
    m->spawn_timer = SPAWN_FIRST;
}

/* e-srg.c new_game, the parts that belong to the rules */
static void new_game(rules_t *r, ship_t *s, mis_t *m)
{
    r->lives = 3;
    m->level = r->level;                /* EASY's missiles fly at 0.75x (missiles.c) */
    m->kills = 0;
    m->dome_hits = 0;                   /* the v1.0.1 rule: the targets open at
                                         * LOW_RINGS_AT hits that broke a whole
                                         * cell too (see missiles.h); the count
                                         * is per game, like kills, so it resets
                                         * where kills resets, at a new game. */
    m->score10 = 0;
    r->game_over = 0;
    r->dome_dead = 1;
    respawn(r, s, m);
    integrity_update(r, m);
}

/* e-srg.c game_step's early branches, in its order: GAME OVER (button 1
 * starts a new game), then the dead ship's countdown (on its last frame the
 * ship comes back, or the game ends). Returns 1 when one of these took the
 * turn (the Vectrex then skips the ship and fire; the missiles update still
 * runs, and on the respawn frame it can launch again). A death's explosion
 * is a drawing concern (M4 Task 2); only the rules live here. */
u8 rules_begin(rules_t *r, ship_t *s, mis_t *m, u8 pressed)
{
    if (r->game_over) {
        if (pressed & CNT_A)
            new_game(r, s, m);
        rules_dbg_update(r);
        return 1;
    }
    if (r->dead_t) {
        if (--r->dead_t == 0) {
            if (r->lives)
                respawn(r, s, m);
            else
                r->game_over = 1;
        }
        rules_dbg_update(r);
        return 1;
    }
    rules_dbg_update(r);
    return 0;
}

/* e-srg.c game_step + integrity_update's late checks, in their order: the
 * dome's integrity gone (a dome death) — else the ship resting on a broken
 * cell — then the integrity the next kill scores is recast from the broken
 * count (the Vectrex runs integrity_update after game_step). As there: while
 * the ship is dead or the game over, nothing is checked, and the missile
 * update ran its landings before the death checks, so a ship resting on a
 * cell broken this frame dies this frame. Returns `died`. */
int rules_end(rules_t *r, ship_t *s, mis_t *m)
{
    if (r->dead_t || r->game_over)
        return 0;
    if (r->nbroken >= DOME_LIMIT) {
        kill_ship(r, m, s, 1);              /* the dome is gone */
        integrity_update(r, m);
        return 1;
    }
    if (s->move_left == 0 && is_broken(s, s->cell)) {
        kill_ship(r, m, s, 0);              /* resting on a broken cell */
        integrity_update(r, m);
        return 1;
    }
    integrity_update(r, m);
    return 0;
}

/* ---- the collapse state machine (M4 Task 4) ----
 * e-srg.c collapse_update, x 59/50 on the frame counts (rules.h). f =
 * DEAD_FRAMES - dead_t: 0 on the death frame (dead_t was just set to
 * DEAD_FRAMES), and the countdown starts on the next frame, so effect f
 * shows for the death's f-th countdown frame. The Vectrex zeroed
 * burst/shake/dim/sink and returned 1 (draw) whenever the gate was off or
 * the fall was over; the drawing's "0" (don't draw) only ever covers
 * f >= COLLAPSE_GONE. collapse_state merges the off and gone cases as 1
 * (the fixed dome), returning 2 only while the collapse actually runs —
 * the drawing reads the effects, which are 0 either way. */

u8 collapse_state(const rules_t *r)
{
    if (!r->dead_t || !r->dome_dead)
        return 1;
    if ((u8)(DEAD_FRAMES - r->dead_t) >= COLLAPSE_GONE)
        return 1;
    return 2;
}

u8 collapse_frac(const rules_t *r)
{
    if (!r->dead_t || !r->dome_dead)
        return 0;
    return (u8)(DEAD_FRAMES - r->dead_t);
}

u8 collapse_shake(const rules_t *r)
{
    u8 f;

    if (collapse_state(r) != 2)
        return 0;
    f = collapse_frac(r);
    if (f >= COLLAPSE_SHAKE)
        return 21;                       /* 31 x 2/3 (Dome-scenery Task 2) */
    return (u8)(f < 8 ? 2 : f < 16 ? 5 : f < 26 ? 10 : 21);
}

u8 collapse_burst(const rules_t *r)
{
    u8 f = collapse_frac(r);

    if (f < COLLAPSE_SHAKE || f >= COLLAPSE_GONE)
        return 0;                        /* (and 0 while the gate is off) */
    return (u8)((f - COLLAPSE_SHAKE) * 2);   /* 3 x 2/3 */
}

u8 collapse_fall(const rules_t *r)
{
    u8 f = collapse_frac(r), g, q, fall = 0;

    if (f < COLLAPSE_SHAKE || f >= COLLAPSE_GONE)
        return 0;
    /* e-srg.c: for each g, if (fall + (g >> 3) <= 120) fall += g >> 3,
     * the cap scaled by 2/3 (Dome-scenery Task 2): 120 -> 80.
     * One pass over the fall's g = 0..58 is 8 iterations of a 3-op loop —
     * the 68000's DIVU is 140 cycles, so the closed form
     * ((g>>3)*((g>>3)*4-4) + ((g&7)+1)*(g>>3)) is not worth it; the loop
     * runs during the collapse only, and the countdown is 118 frames. */
    g = (u8)(f - COLLAPSE_SHAKE);
    for (q = 0; q <= g && fall < 80; q++)
        if (fall + (q >> 3) <= 80)
            fall = (u8)(fall + (q >> 3));
    return fall;
}

u8 collapse_dim(const rules_t *r)
{
    u8 f = collapse_frac(r);

    if (f < COLLAPSE_SHAKE || f >= COLLAPSE_GONE)
        return 0;
    return (u8)(f - COLLAPSE_SHAKE);
}
