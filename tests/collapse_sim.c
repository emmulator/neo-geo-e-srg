/* collapse_sim: src/ship.c + src/missiles.c + src/rules.c driven from
 * stdin, for tests/test_collapse_model.py — replay the collapse state
 * machine and the model beside each other, exactly as rules_sim does for
 * the rules.
 *   "GO"         break 38 cells (a dome death happens at the next rules_end)
 *   "CELLDEATH"  break the cell the ship rests on (a plain death: no collapse)
 *   "0 0"        one no-input frame (bios_p1current, bios_p1change)
 * after each frame prints:
 *   C dead_t nbroken dome_dead lives game_over | state frac shake burst fall dim
 * state: collapse_state (1 off / 2 during); frac: collapse_frac; then the
 * four effect values (shake, burst, fall, dim). */
#include <stdio.h>
#include "ship.h"
#include "missiles.h"
#include "rules.h"

static u8 is_broken(const ship_t *s, u8 c)
{
    return (u8)(s->broken[c >> 3] & (1 << (c & 7)));
}

/* 38 whole cells to crack without collapsing anything early */
static const u8 whole38[38] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
    19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 33, 34, 35,
    37, 38, 40
};

int main(void)
{
    ship_t s;
    mis_t m;
    rules_t r;
    char line[64];
    unsigned a, b;

    ship_reset(&s);
    mis_reset(&m);
    rules_reset(&r);
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == 'G') {                    /* "GO": a dome death */
            u8 i;

            for (i = 0; i < 38; i++)
                if (!is_broken(&s, whole38[i]))
                    rules_break_cell(&r, &s, whole38[i]);
            continue;
        }
        if (line[0] == 'C') {                    /* "CELLDEATH" */
            rules_break_cell(&r, &s, s.cell);
            continue;
        }
        if (sscanf(line, "%u %u", &a, &b) == 2) {
            u8 busy, st, fr, shake, burst, fall, dim;

            busy = rules_begin(&r, &s, &m, (u8)b);
            if (!busy)
                ship_frame(&s, (u8)a, (u8)b);
            mis_update(&m, &s, &r, (u8)b, busy);
            rules_end(&r, &s, &m);
            st = collapse_state(&r);
            fr = collapse_frac(&r);
            shake = collapse_shake(&r);
            burst = collapse_burst(&r);
            fall = collapse_fall(&r);
            dim = collapse_dim(&r);
            printf("C %u %u %u %u %u | %u %u %u %u %u %u\n", r.dead_t, r.nbroken,
                   r.dome_dead, r.lives, r.game_over, st, fr, shake, burst, fall, dim);
        }
    }
    return 0;
}
