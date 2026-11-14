/* rules.h: the game's rules that surround the missiles — broken cells and
 * collapsing (crack, surrounded, break_tile), the dome's integrity and
 * scoring, deaths, lives, respawn and GAME OVER — ported from the Vectrex
 * game (e-srg.c: crack, surrounded, break_tile, integrity_update,
 * kill_ship, new_dome, respawn, new_game and the dead_t/game_over handling
 * in game_step). Pure logic, no hardware: tests/ builds it on the host too.
 *
 * The one source of truth for broken cells: a bit in ship_t.broken (M2,
 * missiles skip broken targets) and the order they broke in r->broken
 * (cracks.s draws them in that order in Task 2).
 *
 * Levels (as on the Vectrex): EASY 0, NORMAL 1, HARD 2. A tile collapses
 * once COLLAPSE_EASY - level of its neighbours are broken (all of them, if
 * it has fewer: rim cells). A dome death (integrity 0) costs one life on
 * NORMAL, nothing on EASY, the game on HARD; deaths take DEAD_FRAMES
 * Vectrex frames (x 59/50), after which the ship comes back on the start
 * cell or the next whole one, and a new dome appears after a dome death.
 * EASY's missiles also fly at 0.75x (v1.1.0: mis_dr_easy, see missiles.c).
 * Pressing A while GAME OVER starts a new game.
 *
 * The per-frame order mirrors e-srg.c game_step exactly: first the early
 * branches (GAME OVER + A restarts; a dead ship's countdown, which may
 * respawn it), during which the ship neither moves nor fires (rules_begin
 * returns 1 on those frames); then the missiles update (which launches
 * again on the very frame the ship came back — the countdown runs first);
 * then the death checks and the integrity recast (rules_end; as on the
 * Vectrex they only run while the ship is alive and the game is on, so a
 * death counts down its full DEAD_FRAMES before any further check). The
 * score a kill makes uses the integrity from the end of the previous
 * frame, so r->integ_pct moves to m->integ_pct at the end of every frame.
 *
 * The state the drawing tasks need is exposed here: broken cells in the
 * order they broke (r->broken, r->nbroken — Task 2 draws cracks over the
 * dome in that order), the integrity (r->integ_pct, Task 3's HUD), lives,
 * the score (m->score10 x 10, Task 3), dead / dome-dead with their frame
 * counter (r->dead_t, r->dome_dead — Task 4's collapse), and game over
 * (r->game_over, Task 3). These lines outside the functions are for that:
 * Task 2's cracks need the broken order, Task 3's HUD needs a change to
 * know when to redraw (the HUD's own `shown` state, as the Vectrex's
 * integ_shown/lives_shown/score_shown), and Task 4's collapse needs the
 * death's age. */
#ifndef RULES_H
#define RULES_H
#include <ngdevkit/neogeo.h>
#include "ship.h"

/* A debug export for the ship-respawn boot test (M4-fixes Task 1): the
 * "ship is alive and the game is on" flag — 0 while a death's countdown
 * runs (and at GAME OVER), 1 on the frame the ship comes back. The MAME
 * probe reads it from the ELF (like hud_framecnt) to detect the first
 * death and the exact respawn frame without any cart cooperation. The
 * normal cart contains it (a tiny .bss word, no behaviour). */
extern u8 rules_dbg_alive;

#define COLLAPSE_EASY 5          /* collapse once this many - level neighbours are broken */
#define LEVEL_EASY   0
#define LEVEL_NORMAL 1
#define LEVEL_HARD   2
#define LEVELS       3
#define DOME_LIMIT   38          /* integrity 0% at this many broken cells (half the dome) */
#define DEAD_FRAMES  118         /* 100 Vectrex frames x 59/50 */

/* The collapse effect (M4 Task 4), from the Vectrex's collapse_update
 * (e-srg.c v1.0.0) with the plan's x 59/50 on the frame counts: on a dome
 * death the dome shakes harder and harder, then its runs fly apart and
 * fall while its palette fades, then it is gone until the new dome — all
 * inside the death's DEAD_FRAMES. The pure half lives here (the rules own
 * dead_t/dome_dead); the drawing lives in dome.c. */
#define COLLAPSE_SHAKE 41        /* 35 Vectrex frames x 59/50: the shake */
#define COLLAPSE_GONE  100       /* 85 Vectrex frames x 59/50: gone from here */
#define COLLAPSE_MAX_DIM 58      /* the fade's range: COLLAPSE_GONE-1-COLLAPSE_SHAKE */

typedef struct rules_t {
    u8 level;                    /* LEVEL_EASY / LEVEL_NORMAL / LEVEL_HARD */
    u8 broken[76];               /* broken cells, in the order they broke */
    u8 nbroken;                  /* how many (integrity = 100% less one 38th each) */
    u8 lives;                    /* 3 at the start of a game */
    u8 integ_pct;                /* the integrity (%), what a kill scores */
    u8 dead_t;                   /* > 0: frames until the ship comes back */
    u8 dome_dead;                /* the death was a dome death: rebuild the dome */
    u8 game_over;                /* no lives left: A starts a new game */
} rules_t;

#include "missiles.h"            /* mis_update sees the full rules_t */

void rules_reset(rules_t *r);    /* as new_game: NORMAL, 3 lives, score 0, the first dome */
u8 rules_break_cell(rules_t *r, ship_t *s, u8 cell);
                                 /* a missile reached the dome: its cell breaks, and
                                  * whole cells with enough broken neighbours collapse
                                  * with it, spreading (e-srg.c break_tile). Returns 1
                                  * when the landed cell broke, 0 when it was already
                                  * broken (the v1.0.1 hits rule: mis_update counts
                                  * the dome hit only on 1). */
u8 rules_begin(rules_t *r, ship_t *s, mis_t *m, u8 pressed);
                                 /* once per frame, before ship_frame and mis_update:
                                  * GAME OVER (A starts a new game) and the dead
                                  * ship's countdown. Returns 1 on frames where that
                                  * took the player's turn: the ship does not move or
                                  * fire then (e-srg.c game_step's early branches). */
int rules_end(rules_t *r, ship_t *s, mis_t *m);
                                 /* once per frame, after mis_update: the death checks
                                  * (resting on a broken cell, the dome's integrity
                                  * gone) and the integrity recast. Returns 1 if the
                                  * ship died this frame. */

/* ---- the collapse state machine (M4 Task 4) ----
 * Pure functions of the rules' dead_t/dome_dead (the death's age), so the
 * drawing can read them every frame and the host tests can hold the C to
 * tests/collapse_model.py. The Vectrex runs the collapse while
 * dead_t && dome_dead, with f = DEAD_FRAMES - dead_t (0 on the death
 * frame itself), and zeroes every effect when the gate is off. */
u8 collapse_state(const rules_t *r);
                                 /* 1 = draw the dome whole, 2 = the collapse is
                                  * running (effects apply), 0 would mean gone:
                                  * collapse_state returns 1 from COLLAPSE_GONE on
                                  * (the Vectrex zeroes the effects, so 0/1 are
                                  * merged as "1: the dome is not collapsing") */
u8 collapse_frac(const rules_t *r);  /* f = DEAD_FRAMES - dead_t (0 on the death, 0 when off) */
u8 collapse_shake(const rules_t *r); /* px of jitter: 3, 7, 15, 31 ramping, 31 in the fall */
u8 collapse_burst(const rules_t *r); /* px the runs spread apart: g * 3, g = f - COLLAPSE_SHAKE */
u8 collapse_fall(const rules_t *r);  /* px the whole dome sinks: the Vectrex's sum of g>>3, cap 120 */
u8 collapse_dim(const rules_t *r);   /* the palette fade over the fall: 0..COLLAPSE_MAX_DIM */
#endif
