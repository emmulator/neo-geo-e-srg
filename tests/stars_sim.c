/* stars_sim: print src/stars.c's stars_pos for tests/test_stars.py.
 *   "all"  one line per (star, dome_angle): "i da x y" for i 0..11,
 *          da 0..239 — the exact integer positions the model must match.
 * (The drawing half compiles against the host register stand-ins; the sim
 * only calls the pure stars_pos.) */
#include <stdio.h>
#include "stars.h"

volatile u16 host_vram_addr, host_vram_rw, host_vram_mod;
volatile u16 host_palbanks[16 * 16];

int main(int argc, char **argv)
{
    u8 i, da;
    u16 x;
    u8 y;
    (void)argv;

    if (argc < 2) {
        fprintf(stderr, "usage: stars_sim all\n");
        return 2;
    }
    for (i = 0; i < NSTARS; i++)
        for (da = 0; da < 240; da++) {
            stars_pos(i, da, &x, &y);
            printf("%u %u %u %u\n", i, da, x, y);
        }
    return 0;
}
