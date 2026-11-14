/* view_sim: src/mis_view.c on lines "ring j r" from stdin; prints
 * "shown behind x y len4" for tests/test_mis_view.py */
#include <stdio.h>
#include "mis_view.h"

int main(void)
{
    unsigned ring, j;
    long r;
    mis_view_t v;

    while (scanf("%u %u %ld", &ring, &j, &r) == 3) {
        mis_view(&v, (u8)ring, (u8)j, (s32)r);
        printf("%u %u %d %d %u\n", v.shown, v.behind, v.shown ? v.x : 0, v.shown ? v.y : 0, v.shown ? v.len4 : 0);
    }
    return 0;
}
