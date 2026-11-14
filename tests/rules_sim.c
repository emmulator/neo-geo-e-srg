/* rules_sim: src/ship.c + src/missiles.c + src/rules.c + src/radar.c driven
 * from stdin, for tests/test_rules_play.py.
 *   "B cell"           a missile reached the dome: break the cell
 *   "L cell"           a missile reached the dome: break the cell
 *   "level n"          set the rules' level (0 easy, 1 normal, 2 hard)
 *   "input pressed"    one frame (bios_p1current, bios_p1change, decimal)
 * after the frame prints, for the model to compare:
 *   b dead_t nbroken lives integ game_over | cell left
 *   l nld cell... | timer kills score10 | obj... (each: state kind ring phi life r) | sfx
 *   e dead_t nbroken integ dome_dead lives game_over | died
 *   r locked lock_t bright | per blip: shown locked      (M5 Task 3)
 */
#include <stdio.h>
#include "ship.h"
#include "missiles.h"
#include "rules.h"
#include "radar.h"

int main(void)
{
    ship_t s;
    mis_t m;
    rules_t r;
    radar_t radar;
    char line[64];
    unsigned a, b, i;

    ship_reset(&s);
    mis_reset(&m);
    rules_reset(&r);
    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "B %u", &a) == 1 || sscanf(line, "L %u", &a) == 1)
            rules_break_cell(&r, &s, (u8)a);
        else if (sscanf(line, "level %u", &a) == 1) {
            r.level = (u8)a;
            m.level = r.level;           /* EASY's missiles fly at 0.75x */
        }
        else if (sscanf(line, "%u %u", &a, &b) == 2) {
            u8 died, busy;

            busy = rules_begin(&r, &s, &m, (u8)b);
            if (!busy)                       /* the Vectrex's else-branch: the play turn */
                ship_frame(&s, (u8)a, (u8)b);
            mis_update(&m, &s, &r, (u8)b, busy);
            died = (u8)rules_end(&r, &s, &m);
            printf("b %u %u %u %u %u | %u %u |", r.dead_t, r.nbroken, r.lives,
                   r.integ_pct, r.game_over, s.cell, s.move_left);
            for (i = 0; i < r.nbroken; i++)
                printf(" %u", r.broken[i]);
            printf("\n");
            printf("l %u", m.nland);
            for (i = 0; i < m.nland && i < NMIS; i++)
                printf(" %u", m.land_cell[i]);
            printf(" | %u %u %u %lu |", m.spawn_timer, m.kills, m.dome_hits,
                   (unsigned long)m.score10);
            for (i = 0; i < NOBJ; i++)
                printf(" %u %u %u %u %u %ld", m.obj[i].state, m.obj[i].kind,
                       m.obj[i].ring, m.obj[i].phi, m.obj[i].life, (long)m.obj[i].r);
            printf(" | %u\n", m.sfx);   /* M7: the frame's sound-event bitmask */
            printf("e %u %u %u %u %u %u | %u\n", r.dead_t, r.nbroken, r.integ_pct,
                   r.dome_dead, r.lives, r.game_over, died);
            radar_frame(&radar, &m, &s);    /* the lock state, after the
                                             * frame's logic (the Vectrex's
                                             * lock_update after game_step) */
            printf("r %u %u %u |", radar.locked, radar.lock_t, radar.ellipse_bright);
            for (i = 0; i < NMIS; i++)
                printf(" %u %u", radar.blip[i].shown, radar.blip[i].locked);
            printf("\n");
        }
    }
    return 0;
}
