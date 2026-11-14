/* mis_sim: src/ship.c + src/missiles.c + src/radar.c driven from stdin, for
 * tests/test_missile_play.py.
 *   "B cell"           mark cell broken
 *   "input pressed"    one frame (bios_p1current, bios_p1change, decimal)
 * After each frame prints the ship's cell and move_left, then spawn_timer,
 * kills, score10, the hits (ring:phi:r) and landings, then each object's
 * state kind ring phi life r, then the frame's sound-event bitmask (M7:
 * 1 fire, 2 hit, 4 crack — 0 none), then the radar's lock line (locked,
 * lock_t, ellipse_bright, and each blip's shown/locked — M5 Task 3, the
 * lock state the model compares). */
#include <stdio.h>
#include "ship.h"
#include "missiles.h"
#include "radar.h"

int main(void)
{
    ship_t s;
    mis_t m;
    radar_t radar;
    char line[64];
    unsigned a, b, i;

    ship_reset(&s);
    mis_reset(&m);
    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "B %u", &a) == 1)
            ship_set_broken(&s, (u8)a);
        else if (sscanf(line, "%u %u", &a, &b) == 2) {
            ship_frame(&s, (u8)a, (u8)b);
            mis_frame(&m, &s, (u8)b);
            printf("%u %u | %u %u %u %lu |", s.cell, s.move_left, m.spawn_timer, m.kills,
                   m.dome_hits, (unsigned long)m.score10);
            for (i = 0; i < m.nhit; i++)
                printf(" h%u:%u:%ld", m.hit[i].ring, m.hit[i].phi, (long)m.hit[i].r);
            for (i = 0; i < m.nland; i++)
                printf(" l%u", m.land_cell[i]);
            printf(" |");
            for (i = 0; i < NOBJ; i++)
                printf(" %u %u %u %u %u %ld", m.obj[i].state, m.obj[i].kind, m.obj[i].ring,
                       m.obj[i].phi, m.obj[i].life, (long)m.obj[i].r);
            printf(" | %u\n", m.sfx);
            radar_frame(&radar, &m, &s);    /* the lock state, after the move
                                             * and the missile update (the
                                             * Vectrex's lock_update) */
            printf("r %u %u %u |", radar.locked, radar.lock_t, radar.ellipse_bright);
            for (i = 0; i < NMIS; i++)
                printf(" %u %u", radar.blip[i].shown, radar.blip[i].locked);
            printf("\n");
        }
    }
    return 0;
}
