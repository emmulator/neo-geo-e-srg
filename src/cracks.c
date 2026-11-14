/* cracks.c: see cracks.h. Every broken cell facing the camera shows its
 * broken-window overlay: the pre-rendered picture of the cell at the
 * current dome rotation, drawn as full-size 16x16 sprite tiles (stones) at
 * the picture's canvas offset — the cell's own outline in the dome
 * picture, turning with the dome. The middle is black and jagged glass
 * fragments in the dome's colours cling to the cell's edges.
 *
 * The art is indexed by (cell, view) where view is the dome's 48-step
 * rotation (broken_map.h; tools/render_broken.py). The dome turns 240
 * steps; the 5-fold symmetry maps (cell, dome_angle) to (permuted cell,
 * dome_angle mod 48), so the runtime looks the art up through broken_perm:
 *
 *   art_cell = broken_perm applied floor(dome_angle / 48) times to cell
 *   view     = dome_angle mod 48
 *
 * The pure half (broken_place) is host-tested by tests/test_broken.c; the
 * hardware half writes the sprite registers (boot-tested). Each stone is a
 * full-size tile: no SCB2 shrink, no leftover rows, so the overlay covers
 * the cell's outline exactly as the art does (the geometry half proves the
 * art covers the cell in the dome picture).
 *
 * Leftovers: the stones are never shrunk, so the hardware draws each as a
 * full 16x16 tile and the M3/M4 "rows below the picture" reach does not
 * exist. Every stone tile of a shown picture is written every frame; a
 * hidden cell's run gets SCB3 height 0. */
#include <ngdevkit/neogeo.h>
#include "cracks.h"
#include "broken_map.h"
#include "dome.h"

/* the number of slots the overlays own (the ship and everything in front
 * come after; see the header's constraint record) */
#define BROKEN_SLOTS ((u16)(BROKEN_SLOT_AFTER - BROKEN_SLOT_BASE))

/* Task C2: while a dome death's collapse runs (and under the dome death's
 * GAME OVER) the collapse owns the overlay range: the fireball, fragments,
 * smoke and puffs live there, so the range is hidden ONCE on the first such
 * frame and then left alone until the dome is whole again. The next whole
 * frame's normal draw rewrites the range, its tail hidden, as before. The
 * flag is reset by cracks_init / cracks_show_empty (the title hides the
 * range every frame) and by every whole frame. */
static u8 collapse_owned;

/* clear a run of overlay slots: SCB3 = 0 (height 0: not drawn) */
static void hides(u16 slot, u8 n)
{
    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = ADDR_SCB3 + slot;
    while (n--)
        *REG_VRAMRW = 0;
}

void cracks_init(void)
{
    u8 i;

    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_BROKEN * 16 + i] = broken_pal[i];
    MMAP_PALBANK1[PAL_BROKEN * 16] = 0x8000;
    hides(BROKEN_SLOT_BASE, (u8)BROKEN_SLOTS);
    collapse_owned = 0;
}

void cracks_show_empty(void)
{
    hides(BROKEN_SLOT_BASE, (u8)BROKEN_SLOTS);
    collapse_owned = 0;
}

/* the pure half: what cell's overlay at dome view `view` (0..47) must
 * hold, from the tables. The caller maps the dome_angle to a view and an
 * art cell through broken_perm first. */
void broken_place(u8 cell, u8 view, broken_place_t *out)
{
    const s16 *b = broken_cell[cell][view];

    out->w = (u8)b[0];
    out->h = (u8)b[1];
    out->x = b[2];                  /* s16 canvas offset in the dome box */
    out->y = b[3];
    if (b[0] == 0) {                    /* faces away: nothing to draw */
        out->tile = 0;
        return;
    }
    out->tile = (u16)(BROKEN_TILE_BASE + broken_tile0[cell]
                      + broken_view_t0[cell][view]);
}

/* write one cell's overlay at its slot run (slot0 .. slot0 + w - 1):
 * the w x h stones, full size, at the canvas offset (x, y) in the dome
 * box. The stones are CONSECUTIVE C ROM tiles: the picture's tile stream
 * was emitted in exactly this order (tools/render_broken.py), so the tile
 * at pl->tile + r * w + c holds stone (r, c) — see cracks.h's constraint
 * record (and test_broken_rom, which decodes the built ROM at these
 * numbers and proves it for every stone). */
static void draw(u16 slot0, const broken_place_t *pl)
{
    u8 r, c;
    u16 attr = (u16)(PAL_BROKEN << 8);
    s16 sy = (s16)(DOME_Y + pl->y);   /* the tables' canvas x/y are in the
                                          * dome box (128x96 px, dome.h's
                                          * DOME_X/DOME_Y at its top-left) */
    s16 sx = (s16)(DOME_X + pl->x);

    *REG_VRAMMOD = 1;
    for (r = 0; r < pl->h; r++) {
        for (c = 0; c < pl->w; c++) {
            *REG_VRAMADDR = ADDR_SCB1 + (slot0 + c) * 64 + r * 2;
            *REG_VRAMRW = (u16)(pl->tile + r * pl->w + c);
            *REG_VRAMRW = attr;
        }
    }
    *REG_VRAMMOD = 0x200;
    for (c = 0; c < pl->w; c++) {
        *REG_VRAMADDR = ADDR_SCB2 + slot0 + c;
        *REG_VRAMRW = 0x0fff;                               /* full size */
        *REG_VRAMRW = (u16)(((496 - sy) << 7) | pl->h);     /* h tiles tall */
        *REG_VRAMRW = (u16)((sx + (s16)c * 16) << 7);
    }
}

/* apply the 5-fold permutation q times to a cell */
static u8 permute(u8 cell, u8 q)
{
    while (q--)
        cell = broken_perm[cell];
    return cell;
}

#ifdef CRACK_TEST
/* test-only dome-angle override for the MAME boot-test's permutation
 * coverage (the task's proof 2 needs a dome_angle >= 48). The test cart
 * parks the ship on the start cell (dome_angle 0) every frame and
 * src/main.c is not part of this task's files, so the probe sets this
 * byte instead; cracks_show then uses it as the dome_angle (the same
 * angle the dome_collapse/dome_show half uses via the real
 * ship.dome_angle, which the probe also writes through the cart's BSS
 * `ship`). 0xFF = unset: run normally. The checker keeps the probe and
 * this byte in lockstep. */
volatile u8 cracks_test_angle = 0xFF;

static u8 effective_angle(u8 dome_angle)
{
    return cracks_test_angle == 0xFF ? dome_angle : cracks_test_angle;
}
#else
#define effective_angle(a) (a)
#endif

void cracks_show(const rules_t *r, u8 dome_angle)
{
    u8 i;
    u16 slots = BROKEN_SLOT_BASE;       /* next free slot in the run */
    u8 view, q;

    dome_angle = effective_angle(dome_angle);
    view = (u8)(dome_angle % BROKEN_VIEWS);
    q = (u8)(dome_angle / BROKEN_VIEWS);

    /* the collapse owns the overlay range from its first frame (the dome
     * death, f 0) on, and a game-ending dome death's GAME OVER keeps it
     * hidden (Task 4's fix: the rules never respawn, so the broken list
     * stays full — the overlays must not redraw the dome's broken cells
     * under GAME OVER). Task C2: hide the range ONCE, on the first such
     * frame, then leave it alone until the dome is whole again; the
     * collapse's fireball, fragments, smoke and puffs are written there. */
    if (dome_draw_gone(r) || (r->dome_dead && r->dead_t)) {
        if (!collapse_owned) {
            hides(BROKEN_SLOT_BASE, (u8)BROKEN_SLOTS);
            collapse_owned = 1;
        }
        return;
    }
    collapse_owned = 0;                 /* the dome is whole: the range is
                                         * the overlays' again */
    for (i = 0; i < r->nbroken && i < 38; i++) {
        u8 cell = r->broken[i];
        u8 art = permute(cell, q);
        const s16 *b = broken_cell[art][view];
        broken_place_t pl;

        if (b[0] == 0)                  /* this cell faces away now */
            continue;
        broken_place(art, view, &pl);
        draw(slots, &pl);
        slots = (u16)(slots + pl.w);
    }
    if (slots < BROKEN_SLOT_AFTER)      /* the tail of the range */
        hides(slots, (u8)(BROKEN_SLOT_AFTER - slots));
}
