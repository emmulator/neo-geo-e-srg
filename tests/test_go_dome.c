/* host unit tests for the drawing "dome stays gone" gate and the
 * GAMEOVER_DRAW_TEST hook (M4-fixes Task 4). The rules are pure and the
 * drawing is boot-tested; what the host CAN hold is the gate itself:
 *
 *   - dome_draw_gone (src/dome.c): 1 exactly under a GAME OVER that a DOME
 *     death ended (game_over && dome_dead), 0 under a non-dome death's
 *     GAME OVER (dome_dead 0 — today's look), and 0 before GAME OVER
 *     (the collapse's own gone frames are a different matter: there the
 *     respawn is coming);
 *   - cracks_show's hide path: the overlays are hidden under the same
 *     game-ending dome death's GAME OVER, and shown under a non-dome
 *     death's GAME OVER (the same dome_draw_gone gate).
 *
 * The full frame sequences (the alive counter, the one-life pin, the seed
 * and park, and the two GAME OVER states) are boot-tested by
 * tests/check_gameover_draw.py; this test drives the rules directly. */
#include <stdio.h>
#include <string.h>
#include "rules.h"
#include "dome.h"
#include "cracks.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* the host stubs the hardware-touching modules need (dome.c reads the LSPC
 * registers and the sprite palette banks; the host never runs the draw) */
volatile u16 host_vram_addr, host_vram_rw, host_vram_mod;
volatile u16 host_palbanks[16 * 16];

static void crack(rules_t *r, ship_t *s, u8 c)
{
    ship_set_broken(s, c);
    r->broken[r->nbroken++] = c;
}

/* 38 whole cells to crack without collapsing anything early
 * (test_rules.c's set, minus 27 — the ship rests on the start cell) */
static const u8 whole38[38] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
    19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 33, 34, 35,
    37, 38, 40
};

int main(void)
{
    rules_t r;
    ship_t s;
    mis_t m;
    u8 i;

    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);

    /* ---- a GAME OVER that a DOME death ended keeps the dome gone ----
     * Play the game to game_over with one life and a full 38-cell
     * breakage (the rules_begin countdown with lives 0 sets game_over).
     * The gate must be 1 from the GAME OVER frame on... */
    m.spawn_timer = 255;
    r.lives = 1;                           /* one life: the death ends the game */
    for (i = 0; i < 38; i++)
        crack(&r, &s, whole38[i]);
    CHECK(dome_draw_gone(&r) == 0);        /* not game over yet */
    rules_end(&r, &s, &m);                 /* the dome death lands */
    CHECK(r.dead_t && r.dome_dead == 1 && dome_draw_gone(&r) == 0);
    for (i = 0; i < DEAD_FRAMES; i++)
        rules_begin(&r, &s, &m, 0);        /* the countdown, lives 0 */
    CHECK(r.game_over == 1 && dome_draw_gone(&r) == 1);
    CHECK(dome_draw_gone(&r) == 1);        /* and stays 1 through the GAME OVER */

    /* ---- a NEW game (A) clears the gate ----
     * (rules_begin with game_over and A pressed: new_game) */
    rules_begin(&r, &s, &m, CNT_A);
    CHECK(r.game_over == 0 && r.dome_dead == 1 && r.nbroken == 0);
    CHECK(dome_draw_gone(&r) == 0);        /* the fresh dome draws again */

    /* ---- a NON-dome death's GAME OVER keeps today's look ----
     * The ship dies on a broken cell (dome_dead 0): the gate stays 0, so
     * the dome draws whole with its broken tiles under the GAME OVER. */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    r.lives = 1;
    m.spawn_timer = 255;
    crack(&r, &s, 27);                     /* the start cell breaks */
    rules_end(&r, &s, &m);                 /* resting on it: a cell death */
    CHECK(r.dead_t && r.dome_dead == 0 && dome_draw_gone(&r) == 0);
    for (i = 0; i < DEAD_FRAMES; i++)
        rules_begin(&r, &s, &m, 0);
    CHECK(r.game_over == 1 && r.dome_dead == 0 && dome_draw_gone(&r) == 0);
    CHECK(r.nbroken == 1);                 /* the broken cell stays */

    /* ---- dome_is_whole, the ground's shadow switch (dome-scenery
     * Task 5): the drawing's own answer to "is the whole chain drawn this
     * frame", derived exactly like dome_collapse's branch order. It must
     * be 0 from the collapse's first split on, 0 in the gone frames and
     * under a game-ending dome death's GAME OVER, and 1 while the dome is
     * drawn whole — including a NON-dome death's GAME OVER (the dome is
     * still there). */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    CHECK(dome_is_whole(&r) == 1);         /* a fresh game: whole */
    /* a dome death: the first split */
    m.spawn_timer = 255;
    r.lives = 3;
    for (i = 0; i < 38; i++)
        crack(&r, &s, whole38[i]);
    rules_end(&r, &s, &m);
    CHECK(r.dead_t && r.dome_dead == 1);
    CHECK(dome_is_whole(&r) == 0);         /* the collapse: split */
    /* through the gone frames (f >= COLLAPSE_GONE) */
    for (i = 0; i < 100; i++)
        rules_begin(&r, &s, &m, 0);
    CHECK(collapse_frac(&r) >= COLLAPSE_GONE);
    CHECK(dome_is_whole(&r) == 0);         /* gone */
    /* the respawn brings it back */
    while (r.dead_t)
        rules_begin(&r, &s, &m, 0);
    CHECK(r.dome_dead == 1 && r.dead_t == 0);
    CHECK(dome_is_whole(&r) == 1);         /* rebuilt: whole again */

    /* a game-ending dome death: the gate keeps it gone under GAME OVER */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    r.lives = 1;
    m.spawn_timer = 255;
    for (i = 0; i < 38; i++)
        crack(&r, &s, whole38[i]);
    rules_end(&r, &s, &m);
    CHECK(dome_is_whole(&r) == 0);
    for (i = 0; i < DEAD_FRAMES; i++)
        rules_begin(&r, &s, &m, 0);
    CHECK(r.game_over == 1 && dome_draw_gone(&r) == 1);
    CHECK(dome_is_whole(&r) == 0);         /* hidden through GAME OVER */

    /* a NON-dome death's GAME OVER draws the dome whole */
    rules_reset(&r);
    ship_reset(&s);
    mis_reset(&m);
    r.lives = 1;
    m.spawn_timer = 255;
    crack(&r, &s, 27);
    rules_end(&r, &s, &m);
    for (i = 0; i < DEAD_FRAMES; i++)
        rules_begin(&r, &s, &m, 0);
    CHECK(r.game_over == 1 && r.dome_dead == 0);
    CHECK(dome_is_whole(&r) == 1);         /* the dome is still drawn */

    if (!fails)
        printf("test_go_dome: all passed\n");
    return fails != 0;
}
