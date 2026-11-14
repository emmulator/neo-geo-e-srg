/* ship_sim: drive src/ship.c from stdin, for tests/test_ship_paths.py.
 *   "P cell"           place the ship at rest on cell (clears broken cells)
 *   "B cell"           mark cell broken
 *   "input pressed"    one frame (bios_p1current, bios_p1change, decimal)
 * After each frame prints "cell move_left dome_angle lat lift jumped" (the
 * jumped flag is the M7 sound event: 1 only on the frame a jump started). */
#include <stdio.h>
#include "ship.h"

int main(void)
{
    ship_t s;
    char line[64];
    unsigned a, b;

    ship_reset(&s);
    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "P %u", &a) == 1)
            ship_place(&s, (u8)a);
        else if (sscanf(line, "B %u", &a) == 1)
            ship_set_broken(&s, (u8)a);
        else if (sscanf(line, "%u %u", &a, &b) == 2) {
            ship_frame(&s, (u8)a, (u8)b);
            printf("%u %u %u %u %u %u\n", s.cell, s.move_left, s.dome_angle,
                   s.lat, s.lift, s.jumped);
        }
    }
    return 0;
}
