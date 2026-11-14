/* host unit tests for src/rules.c (built with tests/host/ngdevkit/neogeo.h).
 * The edges a random game rarely hits: a rim cell collapsing, a chain
 * collapse that spreads more than one step, the respawn cell when the start
 * cell is broken, exactly 38 broken cells, and a dome death at each level.
 * The cells and orders below were worked out from the fixture's adjacency
 * (tests/fixtures/vectrex_cells.json) with the Vectrex rules; the comments
 * show the surrounding counts that make them collapse. */
#include <stdio.h>
#include "ship.h"
#include "missiles.h"
#include "rules.h"
#include "cells.h"
#include "missiles_tables.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* e-srg.c crack: a cell breaks on its own — the bit and the order list —
 * without the surrounding spread. Tests seed broken sets with it, as the
 * Vectrex's CRACK_TEST build does; missiles' landings go through
 * rules_break_cell (break_tile), the spread. */
static void crack(rules_t *r, ship_t *s, u8 c)
{
    ship_set_broken(s, c);
    r->broken[r->nbroken++] = c;
}

/* one frame of the game the way main.c runs it (no input) */
static void frame(rules_t *r, ship_t *s, mis_t *m)
{
    u8 busy = rules_begin(r, s, m, 0);

    if (!r->dead_t && !r->game_over)
        ship_frame(s, 0, 0);
    mis_update(m, s, r, 0, busy);
    rules_end(r, s, m);
}

static int in_order(const rules_t *r, u8 n, const u8 *cells)
{
    u8 i;

    if (r->nbroken != n)
        return 0;
    for (i = 0; i < n; i++)
        if (r->broken[i] != cells[i])
            return 0;
    return 1;
}

/* 38 whole cells to crack, in an order that never gives any cell its
 * collapse count of broken neighbours (verified against the adjacency), and
 * none of them the start cell — so the ship rests on a whole cell and the
 * 38th crack is a clean dome death, not a broken-cell one. */
static const u8 whole38[38] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
    19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 33, 34, 35,
    37, 38, 40
};

static void break38(rules_t *r, ship_t *s)
{
    u8 i;

    for (i = 0; i < 38; i++)
        crack(r, s, whole38[i]);
    CHECK(r->nbroken == 38);
}

int main(void)
{
    rules_t r;
    ship_t s;
    mis_t m;
    u8 i;

    /* ---- a rim cell collapses when all of its neighbours are broken ----
     * Cell 71 (on the south rim) has only three neighbours, 47, 62 and 65:
     * fewer than the NORMAL collapse count 4, so it needs all of them.
     * Crack 62 and 65, then a missile lands on 47 (its third neighbour):
     * 47 and then 71 break, in that order. */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    crack(&r, &s, 62);
    crack(&r, &s, 65);
    {
        static const u8 want[] = { 62, 65, 47, 71 };
        rules_break_cell(&r, &s, 47);
        CHECK(in_order(&r, 4, want));
    }

    /* ---- rules_break_cell's return (Vectrex 1.1.0): 1 when the landed
     * cell broke, 0 when it was already broken (the hits rule counts only
     * a break that broke a whole cell, e-srg.c break_tile's hits++ after
     * its is_broken early return). Cell 13 twice: 1 then 0. */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    CHECK(rules_break_cell(&r, &s, 13) == 1);
    CHECK(rules_break_cell(&r, &s, 13) == 0);

    /* a 6-neighbour cell needs the full count: 27 with three of its four
     * neighbours broken does not collapse; breaking the fourth (36) does —
     * the landing on 36 makes 27 crack (a 4-of-6 collapse) */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    crack(&r, &s, 13);
    crack(&r, &s, 17);
    rules_break_cell(&r, &s, 21);            /* 27 has 3 of 4: spared */
    CHECK(r.nbroken == 3 && r.broken[2] == 21);
    rules_break_cell(&r, &s, 36);            /* 27's fourth: it cracks */
    CHECK(r.nbroken == 5 && r.broken[4] == 27);

    /* ---- a chain collapse spreads more than one step ----
     * Crack 1, 3, 12 and 15. A missile lands on 0, and the collapse runs
     * on: 0's neighbour 4 then has four broken neighbours (0, 1, 3, 15)
     * and cracks; 4's own neighbour 6 then has four (1, 4, 12, 15) and
     * cracks — a second, far step reached through the first. */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    crack(&r, &s, 1);
    crack(&r, &s, 3);
    crack(&r, &s, 12);
    crack(&r, &s, 15);
    {
        static const u8 want[] = { 1, 3, 12, 15, 0, 4, 6 };
        rules_break_cell(&r, &s, 0);
        CHECK(in_order(&r, 7, want));
    }

    /* ---- exactly 38 broken cells ----
     * The integrity is 100% less one 38th per broken cell, rounded like the
     * Vectrex: 100 - (n * 100 + 19) / 38. At 37 broken the ship is alive
     * and the integrity shows 3; the 38th brings it to 0 and the very next
     * frame is a dome death. */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    for (i = 0; i < 37; i++)
        crack(&r, &s, whole38[i]);
    frame(&r, &s, &m);                       /* refreshes the integrity */
    CHECK(r.nbroken == 37 && r.integ_pct == 3 && r.dead_t == 0);
    crack(&r, &s, whole38[37]);
    CHECK(r.nbroken == 38);
    frame(&r, &s, &m);                       /* the 38th: a dome death */
    CHECK(r.dead_t == DEAD_FRAMES && r.dome_dead == 1 && r.integ_pct == 0);
    CHECK(r.nbroken == 38);                  /* the count is cleared at the rebuild */
    CHECK(r.lives == 2);                     /* NORMAL: a dome death costs a life */
    for (i = 0; i < DEAD_FRAMES; i++)
        frame(&r, &s, &m);                   /* the countdown, then the rebuild */
    CHECK(r.dead_t == 0 && r.nbroken == 0 && r.lives == 2);

    /* ---- a dome death at each level ----
     * The same 38 cracks: NORMAL (above) costs a life, EASY loses nothing,
     * HARD ends the game (lives 0; GAME OVER comes when the countdown
     * ends). */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    r.level = LEVEL_EASY;
    break38(&r, &s);
    frame(&r, &s, &m);
    CHECK(r.dead_t == DEAD_FRAMES && r.dome_dead == 1 && r.lives == 3);

    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    r.level = LEVEL_HARD;
    break38(&r, &s);
    frame(&r, &s, &m);
    CHECK(r.dead_t == DEAD_FRAMES && r.lives == 0 && r.game_over == 0);

    /* ---- the respawn cell when the start cell is broken ----
     * The ship rests on cell 27; breaking it kills it on the next frame,
     * and DEAD_FRAMES later it comes back on the next whole cell (28) —
     * old cracks stay, only a dome death rebuilds the dome. */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    crack(&r, &s, 27);
    frame(&r, &s, &m);                       /* resting on a broken cell */
    CHECK(r.dead_t == DEAD_FRAMES && r.dome_dead == 0 && r.lives == 2);
    CHECK(s.cell == 27 && s.move_left == 0);
    for (i = 0; i < DEAD_FRAMES - 1; i++)
        frame(&r, &s, &m);
    CHECK(r.dead_t == 1 && r.game_over == 0);
    frame(&r, &s, &m);                       /* the last frame: back */
    CHECK(r.dead_t == 0 && s.cell == 28 && s.move_left == 0);
    CHECK(r.nbroken == 1 && r.lives == 2);

    /* a death on a cell further out still comes back to the start cell */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    ship_place(&s, 7);
    crack(&r, &s, 7);
    frame(&r, &s, &m);
    CHECK(r.dead_t == DEAD_FRAMES && r.dome_dead == 0);
    for (i = 0; i < DEAD_FRAMES; i++)
        frame(&r, &s, &m);
    CHECK(r.dead_t == 0 && s.cell == CELL_START && s.move_left == 0);

    /* ---- GAME OVER: no lives left, the ship doesn't come back, and A
     * starts a new game (which clears the score and the cracks) ----
     * Three broken-cell deaths take the three NORMAL lives. */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    crack(&r, &s, 27);
    frame(&r, &s, &m);                       /* death 1: lives 2 */
    for (i = 0; i < DEAD_FRAMES; i++)
        frame(&r, &s, &m);                   /* back on 28 (27 still cracked) */
    CHECK(r.game_over == 0 && s.cell == 28);
    crack(&r, &s, 28);
    frame(&r, &s, &m);                       /* death 2: lives 1 */
    for (i = 0; i < DEAD_FRAMES; i++)
        frame(&r, &s, &m);                   /* back on 29 */
    CHECK(r.game_over == 0 && s.cell == 29);
    crack(&r, &s, 29);
    frame(&r, &s, &m);                       /* death 3: lives 0 */
    for (i = 0; i < DEAD_FRAMES; i++)
        frame(&r, &s, &m);                   /* the last countdown: GAME OVER */
    CHECK(r.game_over == 1 && r.dead_t == 0 && r.lives == 0);
    m.score10 = 54321;                       /* a score to clear */
    m.kills = LOW_RINGS_AT;                  /* and the v1.1.0 counts: the */
    m.dome_hits = LOW_RINGS_AT;              /* fresh-break hit count opens the targets */
    frame(&r, &s, &m);                       /* (nothing happens while game over) */
    CHECK(r.game_over == 1 && m.score10 == 54321 && r.nbroken == 3);
    CHECK(m.kills == LOW_RINGS_AT && m.dome_hits == LOW_RINGS_AT);
    rules_begin(&r, &s, &m, CNT_A);          /* A: a new game */
    CHECK(r.game_over == 0 && r.lives == 3 && m.score10 == 0 && r.nbroken == 0);
    CHECK(m.kills == 0 && m.dome_hits == 0);
    CHECK(r.dome_dead == 1 && s.cell == CELL_START && r.dead_t == 0);

    /* ---- the score a kill makes is the current integrity ----
     * Crack 0, 1 and 2 (none of them neighbours enough to collapse): the
     * integrity reads 92 (100 - (3 * 100 + 19) / 38). A missile on the
     * ship's line, then a shot: the hit scores 92 (and nothing more), the
     * kill counted. */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    crack(&r, &s, 0);
    crack(&r, &s, 1);
    crack(&r, &s, 2);
    frame(&r, &s, &m);                       /* refreshes the integrity */
    CHECK(r.integ_pct == 92 && r.nbroken == 3);
    {
        mis_obj_t *o = &m.obj[0];
        u8 ring = mis_cell_ring[CELL_START], phi = mis_cell_phi[CELL_START], f;

        o->state = 1;
        o->kind = KIND_MISSILE;
        o->ring = ring;
        o->phi = phi;
        o->dr = mis_dr[0];
        o->r = 4 * MIS_R_LAND;
        m.fire_req = 1;                      /* A pressed: the shot flies */
        for (f = 0; f < 200 && o->state; f++)
            frame(&r, &s, &m);
        CHECK(o->state == 0 && m.nland == 0);
        CHECK(m.nhit == 1 && m.kills == 1 && m.score10 == 92);
    }

    /* ---- a new game resets the counts where kills resets ---- */
    /* (checked in the GAME OVER block above: A at GAME OVER clears kills
     * and dome_hits with the score, lives and cracks.) */

    if (!fails)
        printf("test_rules: all passed\n");
    return fails != 0;
}
