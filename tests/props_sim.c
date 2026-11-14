/* props_sim: print src/props_layout.c's two pools for every dome angle, for
 * tests/test_props.py. One line per slot:
 *
 *   da pool k shown prop lod col scb2 scb3 scb4 tile
 *
 * pool 0 is the back pool (PROP_BACK_SLOTS slots), pool 1 the front pool
 * (PROP_FRONT_SLOTS slots). The fields are exactly prop_slot_t's;
 * tests/props_model.py derives the same words from build/props_map.h and
 * tools/render_props.drawn(). */
#include <stdio.h>
#include "props_layout.h"

int main(void)
{
    prop_slot_t back[PROP_BACK_SLOTS];
    prop_slot_t front[PROP_FRONT_SLOTS];
    unsigned da, k;

    for (da = 0; da < PROP_NDA; da++) {
        props_layout((u8)da, back, front);
        for (k = 0; k < PROP_BACK_SLOTS; k++)
            printf("%u %u %u %u %u %u %u %u %u %u %u\n", da, 0u, k,
                   (unsigned)back[k].shown, (unsigned)back[k].prop,
                   (unsigned)back[k].lod, (unsigned)back[k].col,
                   (unsigned)back[k].scb2, (unsigned)back[k].scb3,
                   (unsigned)back[k].scb4, (unsigned)back[k].tile);
        for (k = 0; k < PROP_FRONT_SLOTS; k++)
            printf("%u %u %u %u %u %u %u %u %u %u %u\n", da, 1u, k,
                   (unsigned)front[k].shown, (unsigned)front[k].prop,
                   (unsigned)front[k].lod, (unsigned)front[k].col,
                   (unsigned)front[k].scb2, (unsigned)front[k].scb3,
                   (unsigned)front[k].scb4, (unsigned)front[k].tile);
    }
    return 0;
}
