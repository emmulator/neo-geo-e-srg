/* broken_tiles_dump.c: print every stone of every (cell, view) picture with
 * the C ROM tile number the RUNTIME fetches for it, so a host test can decode
 * the built cartridge C ROM at exactly those numbers and compare each tile
 * with the stone render_bitmap(cell, view) drew.
 *
 * The tile numbers come from the real code path: this links src/cracks.c and
 * calls broken_place (the same function the game's broken_place runs), then
 * applies the same fetch expression the hardware half of draw() uses for the
 * picture's stone grid:
 *
 *   tile(cell, view, r, c) = pl->tile + r * pl->w + c
 *
 * where pl->w is the picture's stone width (the picture's tiles are a dense
 * w x h block; keeping the expression here identical to draw()'s is what the
 * test checks against the ROM, so a drift in either direction fails it).
 *
 * Output (stdout):
 *   P <cell> <view> <w> <h> <x> <y> <tile>      picture metadata (facing only)
 *   S <cell> <view> <r> <c> <tile>              one line per stone
 */
#include <stdio.h>
#include "cracks.h"
#include "broken_map.h"

/* the stub registers the headers point the game's writes at (never read;
 * the modules link so broken_place — the pure half — runs) */
volatile u16 host_vram_addr, host_vram_rw, host_vram_mod;
volatile u16 host_palbanks[16 * 16];

int main(void)
{
    u16 cell, v, r, c;

    for (cell = 0; cell < 76; cell++) {
        for (v = 0; v < BROKEN_VIEWS; v++) {
            broken_place_t pl;
            broken_place((u8)cell, (u8)v, &pl);
            if (pl.tile == 0)
                continue;               /* faces away: nothing the runtime draws */
            printf("P %u %u %u %u %d %d %u\n",
                   (unsigned)cell, (unsigned)v, (unsigned)pl.w,
                   (unsigned)pl.h, (int)pl.x, (int)pl.y, (unsigned)pl.tile);
            for (r = 0; r < pl.h; r++) {
                for (c = 0; c < pl.w; c++) {
                    /* draw()'s fetch: the picture's first tile + r * width + c */
                    printf("S %u %u %u %u %u\n", (unsigned)cell, (unsigned)v,
                           (unsigned)r, (unsigned)c,
                           (unsigned)(pl.tile + r * pl.w + c));
                }
            }
        }
    }
    return 0;
}
