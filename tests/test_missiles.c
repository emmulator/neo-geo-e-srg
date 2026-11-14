/* host unit tests for src/missiles.c */
#include <stdio.h>
#include "ship.h"
#include "missiles.h"
#include "rules.h"               /* LEVEL_EASY (rules.h includes missiles.h) */
#include "cells.h"
#include "missiles_tables.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

static void frames(mis_t *m, ship_t *s, int n)
{
    while (n--) {
        ship_frame(s, 0, 0);
        mis_frame(m, s, 0);
    }
}

/* run until the first launch; returns the frame it came on */
static int first_launch(mis_t *m, ship_t *s)
{
    int f;

    for (f = 1; f < 1000; f++) {
        frames(m, s, 1);
        if (m->obj[0].state == 1)
            return f;
    }
    return -1;
}

int main(void)
{
    ship_t s;
    mis_t m;
    mis_obj_t *o, *b;
    u8 k, ring, phi;
    int f;
    unsigned i;
    static const u32 at[5] = { 0, 1000, 2500, 5000, 10000 };

    /* nothing flies at first; the first missile comes after SPAWN_FIRST frames */
    ship_reset(&s);
    mis_reset(&m);
    CHECK(m.spawn_timer == SPAWN_FIRST && m.kills == 0 && m.score10 == 0);
    f = first_launch(&m, &s);
    CHECK(f == SPAWN_FIRST + 1);
    o = &m.obj[0];
    CHECK(o->kind == KIND_MISSILE && o->ring < WAVE_RINGS);
    CHECK(o->r == mis_r_spawn[o->ring] - mis_dr[0] || o->r == mis_r_spawn[o->ring]);
    CHECK(o->dr == mis_dr[0]);

    /* the speed steps by score */
    for (k = 0; k < 5; k++) {
        ship_reset(&s);
        mis_reset(&m);
        m.score10 = at[k];
        first_launch(&m, &s);
        CHECK(m.obj[0].dr == mis_dr[k]);
        if (k) {
            ship_reset(&s);
            mis_reset(&m);
            m.score10 = at[k] - 1;
            first_launch(&m, &s);
            CHECK(m.obj[0].dr == mis_dr[k - 1]);
        }
    }

    /* a missile lands when it reaches the dome: its cell is reported */
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    o = &m.obj[0];
    o->state = 1; o->kind = KIND_MISSILE; o->ring = 4; o->phi = mis_cell_phi[mis_ring_end[3] + 2];
    o->dr = mis_dr[0]; o->r = MIS_R_LAND + mis_dr[0] + 1;
    frames(&m, &s, 1);
    CHECK(o->state == 1 && m.nland == 0);
    frames(&m, &s, 1);
    CHECK(o->state == 0 && m.nland == 1 && m.land_cell[0] == mis_ring_end[3] + 2);

    /* A fires along the ship's cell's line; a second shot waits for a slot */
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    ship_frame(&s, 0, 0);
    mis_frame(&m, &s, CNT_A);
    b = &m.obj[NMIS];
    ring = mis_cell_ring[CELL_START];
    phi = mis_cell_phi[CELL_START];
    CHECK(b->state == 1 && b->kind == KIND_BULLET && b->ring == ring && b->phi == phi);
    CHECK(b->r == BUL_R0 + BUL_DR && b->life == bul_life[ring] - 1);
    mis_frame(&m, &s, CNT_A);
    CHECK(m.obj[NMIS + 1].state == 1);
    mis_frame(&m, &s, CNT_A);                     /* both busy: dropped */
    CHECK(m.fire_req == 0);
    frames(&m, &s, bul_life[ring]);               /* they run out */
    CHECK(m.obj[NMIS].state == 0 && m.obj[NMIS + 1].state == 0);

    /* fire pressed while moving: the shot waits for the landing */
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    ship_frame(&s, CNT_UP, 0);
    mis_frame(&m, &s, CNT_A);
    CHECK(m.fire_req == 1 && m.obj[NMIS].state == 0);
    frames(&m, &s, SHIP_MOVE_FRAMES);
    CHECK(s.move_left == 0 && m.fire_req == 0 && m.obj[NMIS].state == 1);
    CHECK(m.obj[NMIS].ring == mis_cell_ring[s.cell] && m.obj[NMIS].phi == mis_cell_phi[s.cell]);

    /* a hit: a missile on the ship's line meets the bullet where their
     * distances cross; it scores 1000 points x integrity (100%) */
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    o = &m.obj[0];
    o->state = 1; o->kind = KIND_MISSILE; o->ring = ring; o->phi = phi;
    o->dr = mis_dr[0]; o->r = 2 * MIS_R_LAND;
    ship_frame(&s, 0, 0);
    mis_frame(&m, &s, CNT_A);
    CHECK(m.obj[NMIS].life == BUL_LIFE_FAR - 1);  /* a missile on its line: it flies on */
    for (f = 0; f < 200 && o->state; f++)
        frames(&m, &s, 1);
    CHECK(o->state == 0 && m.obj[NMIS].state == 0);
    CHECK(m.nhit == 1 && m.hit[0].ring == ring && m.hit[0].phi == phi);
    CHECK(m.kills == 1 && m.score10 == 100 && m.nland == 0);

    /* a missile on another cell's line (same ring) is not hit: it lands */
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    k = (u8)(CELL_START == mis_ring_end[ring - 1] ? CELL_START + 1 : CELL_START - 1);
    CHECK(mis_cell_ring[k] == ring);
    o = &m.obj[0];
    o->state = 1; o->kind = KIND_MISSILE; o->ring = ring; o->phi = mis_cell_phi[k];
    o->dr = mis_dr[0]; o->r = 2 * MIS_R_LAND;
    ship_frame(&s, 0, 0);
    mis_frame(&m, &s, CNT_A);
    for (f = 0; f < 200 && o->state == 1; f++)
        frames(&m, &s, 1);
    CHECK(m.kills == 0 && m.nland == 1 && m.land_cell[0] == k);
    CHECK(m.dome_hits == 1);               /* the landing counts: a hit on the dome */

    /* ---- the target-opening rule (the Vectrex v1.0.1 hits rule (#1),
     * 2026-10-17): missiles target rings 0..4 until 6 kills or 6 hits on
     * the dome that broke a whole cell this game, whichever comes first
     * (missiles.h LOW_RINGS_AT; a landing on a cell that broke after the
     * missile launched does not count). ---- */

    /* with 5 kills and 5 hits the targets stay in rings 0..4 (every pick
     * is from the wave) */
    ship_reset(&s);
    mis_reset(&m);
    m.kills = 5;
    m.dome_hits = LOW_RINGS_AT - 1;
    f = first_launch(&m, &s);
    CHECK(f != -1 && m.obj[0].state == 1 && m.obj[0].ring < WAVE_RINGS);

    /* the 6th kill opens every ring: with the whole wave broken a launch
     * still succeeds, on a ring-5+ cell */
    ship_reset(&s);
    mis_reset(&m);
    for (i = 0; i < mis_ring_end[WAVE_RINGS - 1]; i++)
        ship_set_broken(&s, i);
    m.kills = LOW_RINGS_AT;
    m.dome_hits = 0;
    f = first_launch(&m, &s);
    CHECK(f != -1 && m.obj[0].state == 1 && m.obj[0].ring >= WAVE_RINGS);

    /* the 6th hit opens them too, with fewer than 6 kills: the whole wave
     * broken and 5 kills, which on v1.0.0 stalls forever (no free target),
     * must launch on a ring-5+ cell once 6 missiles hit the dome */
    ship_reset(&s);
    mis_reset(&m);
    for (i = 0; i < mis_ring_end[WAVE_RINGS - 1]; i++)
        ship_set_broken(&s, i);
    m.kills = LOW_RINGS_AT - 1;
    m.dome_hits = LOW_RINGS_AT;
    f = first_launch(&m, &s);
    CHECK(f != -1 && m.obj[0].state == 1 && m.obj[0].ring >= WAVE_RINGS);

    /* one short of the rule (the whole wave broken, 5 kills, 5 hits) there
     * is still nothing to launch at */
    ship_reset(&s);
    mis_reset(&m);
    for (i = 0; i < mis_ring_end[WAVE_RINGS - 1]; i++)
        ship_set_broken(&s, i);
    m.kills = LOW_RINGS_AT - 1;
    m.dome_hits = LOW_RINGS_AT - 1;
    f = first_launch(&m, &s);
    CHECK(f == -1);

    /* ---- the EASY speed table (v1.1.0): EASY's missiles fly at 0.75x of
     * NORMAL/HARD's at every speed step (the Vectrex's speed_easy, a
     * quarter slower, through the same x 50/59 formula) ---- */
    for (k = 0; k < MIS_SPEEDS; k++) {
        ship_reset(&s);
        mis_reset(&m);
        m.level = LEVEL_EASY;
        m.score10 = at[k];
        first_launch(&m, &s);
        CHECK(m.obj[0].dr == mis_dr_easy[k]);
        CHECK(mis_dr_easy[k] < mis_dr[k]);       /* a quarter slower */
    }

    /* a new game (mis_reset) clears both counts with the rest of the game */
    ship_reset(&s);
    mis_reset(&m);
    m.kills = LOW_RINGS_AT;
    m.dome_hits = LOW_RINGS_AT;
    mis_reset(&m);
    CHECK(m.kills == 0 && m.dome_hits == 0);

    /* ---- Task 1: the game's seed from the title's time ----
     * mis_seed_from is RNG_SEED ^ frames, and RNG_SEED instead if that is 0
     * (xorshift16 never leaves 0: a 0 seed would make every rand8 return 0).
     * The SEED lines let tests/test_mis_seed.py compare the C against
     * tests/mis_model.py's mirror over the same frames. */
    {
        static const u16 seed_frames[] = {
            0, 1, 0x0002, 0x00ff, 0x0100, 0x1234, 0xACE1, 0xFFFE, 0xFFFF
        };

        for (i = 0; i < sizeof seed_frames / sizeof seed_frames[0]; i++) {
            u16 f = seed_frames[i], want = (u16)(RNG_SEED ^ f);

            if (want == 0)
                want = RNG_SEED;
            CHECK(mis_seed_from(f) == want);
            CHECK(mis_seed_from(f) != 0);   /* xorshift16 must never be seeded 0 */
            printf("SEED %u %u\n", (unsigned)f, (unsigned)mis_seed_from(f));
        }
        /* the two frames that would give 0 both fall back to RNG_SEED */
        CHECK(mis_seed_from(0) == RNG_SEED);
        CHECK(mis_seed_from(RNG_SEED) == RNG_SEED);
    }

    if (!fails)
        printf("test_missiles: all passed\n");
    return fails != 0;
}
