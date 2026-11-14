/* radar_sim: drive src/radar.c's pure functions for tests/test_radar.py.
 *   radar_sim pos   every distinct blip over the task's full grid (every
 *                   ring, phi 0..239, dome_angle 0..239 in steps of 7,
 *                   r 0..6.0 radii in steps of 0.05, locked and not): the
 *                   duplicates collapse because a blip depends only on
 *                   j = (phi + dome_angle) mod 240, so the records are
 *                   "P ring j k locked sx sy h hx hy" (k = the r step
 *                   0..120, r = round(k * 0.05 * 2^19)).
 *   radar_sim wrap  every (phi, dome_angle) pair of that grid:
 *                   "W phi da j" — the C's own radar_j, held to
 *                   (phi + da) mod 240 exactly by the tests.
 * (The harness builds for the host only; the 16-bit-maths rule applies to
 * the 68k build of src/radar.c, so this file is free to use u32.) */
#include <stdio.h>
#include "radar.h"
#include "radar_tables.h"

#define PHS 240
#define KMAX 120      /* r = k * 0.05 radii, 0..6.0 */

static radar_blip_t b;

static u32 r_of_k(unsigned k)
{
    return (262144u * k + 5u) / 10u;    /* round-half-up(k * 0.05 * 2^19) */
}

static void pos(void)
{
    static u8 seen[RADAR_RINGS][2][PHS][KMAX + 1];   /* (ring, locked, j, k) */
    unsigned ring, phi, da, k, l;

    for (ring = 0; ring < RADAR_RINGS; ring++)
        for (phi = 0; phi < PHS; phi++)
            for (da = 0; da < PHS; da += 7)
                for (k = 0; k <= KMAX; k++)
                    for (l = 0; l < 2; l++) {
                        u8 j = radar_j((u8)phi, (u8)da);
                        if (seen[ring][l][j][k])
                            continue;
                        seen[ring][l][j][k] = 1;
                        radar_blip(&b, (u8)ring, j, (s32)r_of_k(k), (u8)l);
                        printf("P %u %u %u %u %d %d %u %d %d\n",
                               ring, j, k, l, b.sx, b.sy, b.h, b.hx, b.hy);
                    }
}

static void wrap(void)
{
    unsigned phi, da;

    for (phi = 0; phi < PHS; phi++)
        for (da = 0; da < PHS; da += 7)
            printf("W %u %u %u\n", phi, da, radar_j((u8)phi, (u8)da));
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: radar_sim pos|wrap\n");
        return 2;
    }
    if (argv[1][0] == 'p')
        pos();
    else
        wrap();
    return 0;
}
