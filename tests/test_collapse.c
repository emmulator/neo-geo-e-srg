/* host unit tests for the collapse state machine (src/rules.c:
 * collapse_state / collapse_frac / the effect getters, M4 Task 4). Written
 * from the Vectrex's collapse_update (vectrex-e-srg v1.0.0, e-srg.c)
 * with the plan's x 59/50: shake the dome's columns harder and harder, then
 * let them fall and spread apart while the palette fades (dim), then gone,
 * within the 100-frame death (118 Neo frames). The collapse only runs while
 * the ship is dead and the death was a dome death, exactly as the Vectrex
 * gates it (dead_t && dome_dead).
 *
 * The numbers, on the Vectrex then scaled:
 *   COLLAPSE_SHAKE = 35 x 59/50 = 41.3 -> 41 frames of shaking
 *   COLLAPSE_GONE  = 85 x 59/50 = 100.3 -> 100 frames: from then the dome
 *     is not drawn (DEAD_FRAMES 118: the last 18 frames it is simply gone,
 *     as on the Vectrex)
 * So f = 0..40 shakes (shake ramps 3, 7, 15, 31 at f = 8, 16, 26), and
 * g = f - 41 = 0..58 is the fall: burst = g*3 (the runs fly apart),
 * fall = the Vectrex's incremental sum of g>>3 capped at 120, dim = g (the
 * palette fade runs the whole fall and reaches black as it ends). At
 * f >= 100 every effect is 0 and the dome is not drawn — the Vectrex
 * zeroes its four effect variables whenever the collapse is off or done. */
#include <stdio.h>
#include "rules.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* one frame of the game the way main.c runs it (no input) */
static void frame(rules_t *r, ship_t *s, mis_t *m)
{
    u8 busy = rules_begin(r, s, m, 0);

    if (!r->dead_t && !r->game_over)
        ship_frame(s, 0, 0);
    mis_update(m, s, r, 0, busy);
    rules_end(r, s, m);
}

static void crack(rules_t *r, ship_t *s, u8 c)
{
    ship_set_broken(s, c);
    r->broken[r->nbroken++] = c;
}

/* 38 whole cells to crack without collapsing anything early (test_rules.c) */
static const u8 whole38[38] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
    19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 33, 34, 35,
    37, 38, 40
};

static void dome_death(rules_t *r, ship_t *s, mis_t *m)
{
    u8 i;

    rules_reset(r);
    ship_reset(s);
    mis_reset(m);
    m->spawn_timer = 255;
    for (i = 0; i < 38; i++)
        crack(r, s, whole38[i]);
    frame(r, s, m);
    CHECK(r->dead_t == DEAD_FRAMES && r->dome_dead == 1 && r->integ_pct == 0);
}

/* the Vectrex's fall accumulator, applied to g = 0..gmax (e-srg.c:
 * if (fall + (g >> 3) <= 120) fall += g >> 3, each g) */
static u8 vectrex_fall(u8 gmax)
{
    u8 g, fall = 0;

    for (g = 0; g <= gmax; g++)
        if (fall + (g >> 3) <= 120)
            fall = (u8)(fall + (g >> 3));
    return fall;
}

int main(void)
{
    rules_t r;
    ship_t s;
    mis_t m;
    u8 f;

    /* ---- the collapse phases over a dome death's DEAD_FRAMES ----
     * f = DEAD_FRAMES - dead_t: f = 0 on the death frame itself (rules_end
     * just set dead_t = DEAD_FRAMES; its countdown comes next frame), and
     * the collapse RAN already on that frame — the Vectrex's gate is
     * dead_t && dome_dead, and dead_t is set by the death — so the death
     * frame draws the dome with the first shake, f = 0. The collapse is
     * off — the draw flag 1, every effect 0 — only away from a dome
     * death, e.g. between deaths or on a non-dome death. */
    dome_death(&r, &s, &m);
    CHECK(collapse_state(&r) == 2 && collapse_frac(&r) == 0);
    for (f = 1; f < DEAD_FRAMES; f++) {
        u8 fr = collapse_frac(&r);

        if (fr < COLLAPSE_SHAKE) {
            CHECK(collapse_state(&r) == 2);
            CHECK(collapse_shake(&r) == (fr < 8 ? 3 : fr < 16 ? 7 : fr < 26 ? 15 : 31));
            CHECK(collapse_burst(&r) == 0 && collapse_fall(&r) == 0 && collapse_dim(&r) == 0);
        } else if (fr < COLLAPSE_GONE) {
            u8 g = (u8)(fr - COLLAPSE_SHAKE);

            CHECK(collapse_state(&r) == 2);
            CHECK(collapse_shake(&r) == 31);
            CHECK(collapse_burst(&r) == (u8)(g * 3));
            CHECK(collapse_fall(&r) == vectrex_fall(g));
            CHECK(collapse_dim(&r) == g);
        } else {
            CHECK(collapse_state(&r) == 1);          /* gone: not drawn */
            CHECK(collapse_shake(&r) == 0 && collapse_burst(&r) == 0
                  && collapse_fall(&r) == 0 && collapse_dim(&r) == 0);
        }
        rules_begin(&r, &s, &m, 0);              /* step the countdown */
        CHECK(collapse_frac(&r) == (u8)(fr + 1));
    }
    /* the loop stepped 117 of the 118 countdown frames (dead_t = 1 left);
     * the 118th is the respawn: the collapse is off again and the dome is
     * whole (the rebuild happened in respawn) */
    CHECK(r.dead_t == 1 && r.dome_dead == 1);
    rules_begin(&r, &s, &m, 0);                  /* the last countdown frame */
    CHECK(r.dead_t == 0 && r.dome_dead == 1 && r.nbroken == 0);
    CHECK(collapse_state(&r) == 1 && collapse_frac(&r) == 0);

    /* ---- the C's fall must be the Vectrex's accumulator at every g ----
     * (a closed form is fine, but it must agree with e-srg.c's increment
     * sum of g>>3, capped at 120, for every g the fall runs) */
    dome_death(&r, &s, &m);
    for (f = 0; f < COLLAPSE_GONE + 5; f++) {
        u8 fr = collapse_frac(&r);

        if (fr >= COLLAPSE_SHAKE && fr < COLLAPSE_GONE)
            CHECK(collapse_fall(&r) == vectrex_fall((u8)(fr - COLLAPSE_SHAKE)));
        rules_begin(&r, &s, &m, 0);
    }

    /* ---- the dim is the fade's position in the fall, straight g ----
     * (dim = 0 while shaking, 1..58 over the fall, reaching the black end
     * of the palette table exactly as the fall ends at f = 99) */
    dome_death(&r, &s, &m);
    rules_begin(&r, &s, &m, 0);              /* f = 1: still shaking */
    CHECK(collapse_dim(&r) == 0);
    for (f = 0; f < COLLAPSE_SHAKE - 1; f++)
        rules_begin(&r, &s, &m, 0);          /* to f = 41: the fall starts */
    CHECK(collapse_frac(&r) == COLLAPSE_SHAKE && collapse_dim(&r) == 0);
    rules_begin(&r, &s, &m, 0);              /* f = 42: g = 1 */
    CHECK(collapse_dim(&r) == 1);
    for (f = 0; f < COLLAPSE_GONE - 42 - 1; f++)
        rules_begin(&r, &s, &m, 0);          /* to f = 99: the fall's last */
    CHECK(collapse_frac(&r) == COLLAPSE_GONE - 1);
    CHECK(collapse_dim(&r) == COLLAPSE_GONE - COLLAPSE_SHAKE - 1);

    /* ---- not a dome death: no collapse, the countdown still runs ----
     * (the ship dies on a broken cell; the dome stays whole and upright) */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    m.spawn_timer = 255;
    crack(&r, &s, 27);
    frame(&r, &s, &m);
    CHECK(r.dead_t == DEAD_FRAMES && r.dome_dead == 0);
    CHECK(collapse_state(&r) == 1 && collapse_frac(&r) == 0);
    CHECK(collapse_shake(&r) == 0 && collapse_burst(&r) == 0
          && collapse_fall(&r) == 0 && collapse_dim(&r) == 0);

    if (!fails)
        printf("test_collapse: all passed\n");
    return fails != 0;
}
