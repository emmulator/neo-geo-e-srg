/* entry_sim: drive src/entry.c from stdin, for tests/test_entry.py.
 * One line per operation:
 *   B                 entry_begin; prints the state
 *   F cur change      entry_frame(cur, change); prints the state
 *   W k               test setup: at rest on position k (phase = target =
 *                     k * RING_SUB)
 *   P phase           test setup: at rest on phase (0..RING_PHASES-1)
 *   D base            prints "angle=" + entry_dome_angle(base)
 *   S                 prints the state
 * The state line is "phase target ninit i0 i1 i2 hold dir done sfx fly_t
 * fly_k" (decimal).
 */
#include <stdio.h>
#include "entry.h"
#include "ring_map.h"

static void print_state(const entry_t *e)
{
    printf("%u %u %u %u %u %u %u %u %u %u %u %u\n", e->phase, e->target,
           e->ninit, e->init[0], e->init[1], e->init[2], e->hold, e->dir,
           e->done, e->sfx, e->fly_t, e->fly_k);
}

int main(void)
{
    entry_t e;
    char line[128];
    char op;

    entry_begin(&e);
    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, " %c", &op) != 1) {
            fprintf(stderr, "bad line: %s", line);
            return 2;
        }
        if (op == 'B') {
            entry_begin(&e);
            print_state(&e);
        } else if (op == 'F') {
            unsigned cur, change;

            if (sscanf(line, " F %u %u", &cur, &change) != 2) {
                fprintf(stderr, "bad F: %s", line);
                return 2;
            }
            entry_frame(&e, (u8)cur, (u8)change);
            print_state(&e);
        } else if (op == 'W') {
            unsigned k;

            if (sscanf(line, " W %u", &k) != 1) {
                fprintf(stderr, "bad W: %s", line);
                return 2;
            }
            e.phase = e.target = (u8)((k * RING_SUB) % RING_PHASES);
            e.hold = 0;
            e.dir = 0;
            print_state(&e);
        } else if (op == 'P') {
            unsigned p;

            if (sscanf(line, " P %u", &p) != 1) {
                fprintf(stderr, "bad P: %s", line);
                return 2;
            }
            e.phase = e.target = (u8)(p % RING_PHASES);
            e.hold = 0;
            e.dir = 0;
            print_state(&e);
        } else if (op == 'D') {
            unsigned base;

            if (sscanf(line, " D %u", &base) != 1) {
                fprintf(stderr, "bad D: %s", line);
                return 2;
            }
            printf("angle=%u\n", entry_dome_angle(&e, (u8)base));
        } else if (op == 'S') {
            print_state(&e);
        } else {
            fprintf(stderr, "bad op: %s", line);
            return 2;
        }
    }
    return 0;
}
