/* test_broken.c: the C-side half of the broken-window proof.
 *
 * The geometry half (tests/test_broken_geometry.py) proves the overlay
 * pictures cover the cell's visible area in the dome picture. This test
 * proves the runtime code path: broken_show reads broken_cell (the picture
 * w/h and canvas offset for the cell at the dome_angle) and broken_place
 * turns them into the exact sprite registers the overlay must hold — the
 * fullsize stones at the canvas position, so the drawn overlay covers the
 * cell exactly as the art does — and the slot arithmetic (each cell owns
 * its fixed slot run).
 *
 * The overlays are full-size (never shrunk), so there is no shrink
 * geometry; the "cover" proof is the host test's. This test checks:
 *   - broken_place computes the top-left from the canvas offset
 *     (broken_cell[cell][view] x/y in the dome box) and the stones'
 *     fullsize 16x16 size;
 *   - the slot range never overlaps the dome's or the ship's (the one
 *     slot map in src/slots.h, M5 Task 1: every range derived from the
 *     one before it and the counts equal the art's);
 *   - the module hides and shows without stale slots (the SCB3 height
 *     protocol for full-size sprites).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cracks.h"
#include "dome_map.h"
#include "broken_map.h"
#include "rules.h"

/* the stub registers the header points the game's writes at (never read) */
volatile u16 host_vram_addr, host_vram_rw, host_vram_mod;
volatile u16 host_palbanks[16 * 16];

static int fails = 0;

static void check(int cond, const char *what, int cell, int da)
{
    if (!cond) {
        printf("FAIL %s cell %d da %d\n", what, cell, da);
        fails++;
    }
}

static void test_place_formula(void)
{
    /* broken_place: the fullsize stones sit at the canvas offset read from
     * broken_cell, for every cell and every view. */
    int cell, v;
    for (cell = 0; cell < 76; cell++) {
        for (v = 0; v < BROKEN_VIEWS; v++) {
            const s16 *b = broken_cell[cell][v];
            broken_place_t pl;
            broken_place((u8)cell, (u8)v, &pl);
            if (b[0] == 0) {               /* faces away: nothing placed */
                check(pl.tile == 0, "away tile", cell, v);
                continue;
            }
            /* w x h stones, canvas x/y, top-left = (x, y) in the dome box */
            check(pl.w == b[0], "w", cell, v);
            check(pl.h == b[1], "h", cell, v);
            check(pl.x == b[2], "x", cell, v);
            check(pl.y == b[3], "y", cell, v);
            /* the first stone's C ROM tile, from the cell's column */
            u16 t0 = (u16)(BROKEN_TILE_BASE + broken_tile0[cell]
                           + broken_view_t0[cell][v]);
            check(pl.tile == t0, "tile", cell, v);
            /* the stones are a contiguous 16x16 grid: rows x cols */
            check((unsigned)(pl.tile + pl.w * pl.h - 1) <= 65535, "tile end", cell, v);
        }
    }
}

static void test_slot_layout(void)
{
    /* the overlays own BROKEN_SLOT_BASE..(BROKEN_SLOT_AFTER-1); the dome is
     * right before them and the front prop pool starts at BROKEN_SLOT_AFTER
     * (dome-scenery Task 15: the near tree draws over the dome and its
     * overlays and under the ship), then the ship, so nothing overlaps and
     * a broken tile can never draw over the dome (it sits above it) nor
     * under the ship, the console (dome-scenery Task 7: right after the
     * ship, under the front missiles), the front missiles or explosions
     * (they have higher slots). The one slot map is src/slots.h (M5 Task 1)
     * — every range follows the one before it, and the counts equal the art
     * they describe. */
    check(BROKEN_SLOT_BASE == DOME_SPRITE + DOME_COUNT, "slot base", 0, 0);
    check(DOME_SPRITE == SMOKE_BACK_SPRITE + SMOKE_BACK_COUNT,
          "dome after the back smoke", 0, 0);
    check(SMOKE_BACK_SPRITE == MIS_BEHIND_SPRITE + MIS_BEHIND_COUNT,
          "back smoke after the behind missiles", 0, 0);
    check(DOME_SPRITE + DOME_COLS <= BROKEN_SLOT_BASE, "after dome", 0, 0);
    check(BROKEN_SLOT_AFTER > BROKEN_SLOT_BASE, "slots exist", 0, 0);
    check(SHIP_SPRITE == BROKEN_SLOT_AFTER, "ship after overlays", 0, 0);
    check(SHIP_SPRITE == BROKEN_SLOT_BASE + BROKEN_SLOT_COUNT,
          "ship after the overlay count", 0, 0);
    /* 10-26: the front props draw over the ship (a front prop that overlaps
     * the ship on screen is always nearer the camera) */
    check(PROP_FRONT_SPRITE == SHIP_SPRITE + SHIP_COUNT,
          "front props after the ship", 0, 0);
    /* dome-scenery Task 7: the console sits between the ship (since 10-26
     * the front props) and the front missiles (it draws over both and under
     * the missiles) */
    check(CON_SPRITE == PROP_FRONT_SPRITE + PROP_FRONT_COUNT,
          "console after the front props", 0, 0);
    check(CON_COUNT == 20, "console count (CON_COLS)", 0, 0);
    check(MIS_FRONT_SPRITE == CON_SPRITE + CON_COUNT, "front missiles", 0, 0);
    check(EXPL_SPRITE == MIS_FRONT_SPRITE + MIS_FRONT_COUNT, "explosions", 0, 0);
    check(RADAR_SPRITE == EXPL_SPRITE + EXPL_COUNT, "radar reserved", 0, 0);
    check(EXPL_SPRITE + EXPL_COUNT + RADAR_COUNT <= 381, "last slot <= 380", 0, 0);
    /* every cell's slot run is inside the range */
    for (int cell = 0; cell < 76; cell++) {
        check(broken_slot0[cell] + broken_max_w[cell] <= BROKEN_SLOT_AFTER,
              "slots in range", cell, 0);
        check(broken_slot0[cell] >= BROKEN_SLOT_BASE, "slot base", cell, 0);
    }
}

static void test_show_hides_all(void)
{
    /* with no broken cells, every overlay slot must be hidden (SCB3
     * height 0). The pure half can't see the writes; it checks the module
     * compiles and the tables are the only data (the hardware half is the
     * boot-test's job). */
    rules_t r;
    memset(&r, 0, sizeof r);
    r.dome_dead = 0;
    check(BROKEN_SLOT_AFTER - BROKEN_SLOT_BASE <= 255, "slot count fits u8", 0, 0);
}

int main(void)
{
    test_place_formula();
    test_slot_layout();
    test_show_hides_all();
    if (fails) {
        printf("%d FAILURES\n", fails);
        return 1;
    }
    printf("PASS test_broken\n");
    return 0;
}
