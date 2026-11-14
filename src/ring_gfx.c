/* ring_gfx.c: see ring_gfx.h. The ring is 38 sprites: the 37 glyph
 * positions in the slots' draw order (ring_order, back lowest) and the
 * pointer in the last slot, above the ring. The glyph's tile is the part's
 * position tile; its palette bank is PAL_RING_BASE + ring_kind (0 back dim,
 * 1 front gold, 2 the front letter at rest hot). Each glyph is one 16x16
 * tile, so SCB3's height is 1. The pointer blinks every 8 entry frames.
 *
 * The per-frame drawing is table-index-only arithmetic (16-bit; no divide,
 * no libgcc). It stages the whole ring when the phase changes and only the
 * pointer when its blink toggles; at rest (a held ring) nothing is written.
 * ring_gfx_init/ring_gfx_hide write directly (outside play frames).
 */
#include <ngdevkit/neogeo.h>
#include "ring_gfx.h"
#include "slots.h"
#include "dome.h"
/* the ring's tile numbers, its palettes and the precomputed per-phase
 * geometry. The generated headers are static const; the ring uses all of
 * ring_map's tables except ring_code, so silence that one warning. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-const-variable"
#include "collapse_map.h"
#include "ring_map.h"
#pragma GCC diagnostic pop

/* the collapse part is the last before the ring (Makefile CROM parts), so
 * the ring's first tile starts right after it. src/dome.h's
 * COLLAPSE_TILE_BASE is BAND_TILE_BASE + BAND_TILES. */
#define RING_TILE_BASE (COLLAPSE_TILE_BASE + COLLAPSE_TILES)

/* the staged ring words, one entry per slot: slot j shows position
 * ring_order[phase][j] (the pointer is slot 37). */
static u16 pend_tile[RING_COUNT];
static u16 pend_attr[RING_COUNT];
static u16 pend_scb2[RING_COUNT];
static u16 pend_scb3[RING_COUNT];
static u16 pend_scb4[RING_COUNT];

/* K2: the flying letter's staged words (the one FLY_SPRITE slot). */
static u16 pend_fly_tile;
static u16 pend_fly_attr;
static u16 pend_fly_scb2;
static u16 pend_fly_scb3;
static u16 pend_fly_scb4;

static u8 last_phase;              /* 0xff: nothing staged yet */
static u8 last_pointer;            /* 0xff: nothing staged yet */
static u16 last_fly_key;           /* 0: hidden and already written */
static u8 all_dirty;               /* stage the 37 glyphs + pointer */
static u8 pointer_dirty;           /* stage only the pointer */
static u8 fly_dirty;               /* stage/write the flying letter */
static u8 pal_dirty;               /* the three palette banks */

static void ring_hide_slots(void)
{
    u16 s;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + RING_SPRITE);
    /* the flyer's slot is the one right after the ring (FLY_SPRITE =
     * RING_SPRITE + RING_COUNT), so the same run hides it too. */
    for (s = 0; s < RING_COUNT + FLY_COUNT; s++)
        *REG_VRAMRW = 0;
}

/* K2: stage the flyer's words; its key is fly_t, fly_k and the initial
 * slot, so every flight frame re-stages it and the landing (key 0) hides
 * it. The tile is the picked position's ring tile in the hot kind-2
 * palette. */
static void stage_fly(const entry_t *e)
{
    u8 slot, f;
    u16 key = 0;

    if (e->fly_t > 0) {
        slot = (u8)(e->ninit - 1);
        f = (u8)(e->fly_t - 1);
        key = (u16)(((u16)e->fly_t << 8)
                    | ((u16)e->fly_k << 2) | slot);
        pend_fly_tile = (u16)(RING_TILE_BASE + e->fly_k);
        pend_fly_attr = (u16)((PAL_RING_BASE + 2) << 8);
        pend_fly_scb2 = fly_scb2[f];
        pend_fly_scb3 = (u16)(((u16)(496 - fly_y[slot][f]) << 7) | 1);
        pend_fly_scb4 = (u16)((u16)fly_x[slot][f] << 7);
    } else {
        pend_fly_scb3 = 0;          /* landed/ended: hidden */
    }
    if (key != last_fly_key) {
        last_fly_key = key;
        fly_dirty = 1;
    }
}

void ring_gfx_hide(void)
{
    ring_hide_slots();
    last_phase = 0xff;
    last_pointer = 0xff;
    last_fly_key = 0;               /* the flyer is hidden above */
    all_dirty = 0;
    pointer_dirty = 0;
    fly_dirty = 0;
}

void ring_gfx_init(void)
{
    ring_gfx_hide();
    pal_dirty = 1;
    all_dirty = 1;
}

static void stage_all(u8 phase, u8 pointer)
{
    u8 j, pos;
    u16 tile;

    for (j = 0; j < RING_N; j++) {
        pos = ring_order[phase][j];
        tile = (u16)(RING_TILE_BASE + pos);
        pend_tile[j] = tile;
        pend_attr[j] = (u16)((PAL_RING_BASE + ring_kind[phase][pos]) << 8);
        pend_scb2[j] = ring_scb2[phase][pos];
        pend_scb3[j] = (u16)(((u16)(496 - ring_y[phase][pos]) << 7) | 1);
        pend_scb4[j] = (u16)((u16)ring_x[phase][pos] << 7);
    }

    /* the pointer: the last slot, the hot front palette, full size, one
     * tile high; hidden when the blink is off. */
    pend_tile[RING_N] = (u16)(RING_TILE_BASE + RING_POINTER);
    pend_attr[RING_N] = (u16)((PAL_RING_BASE + 2) << 8);
    pend_scb2[RING_N] = 0x0fff;
    pend_scb3[RING_N] = pointer
        ? (u16)(((u16)(496 - RING_POINTER_Y) << 7) | 1) : 0;
    pend_scb4[RING_N] = (u16)((u16)RING_POINTER_X << 7);
}

void ring_gfx_prepare(const entry_t *e, u16 frame)
{
    u8 phase = e->phase;
    u8 pointer = (u8)((frame >> 3) & 1);

    stage_fly(e);                   /* K2: moves every flight frame */
    if (phase != last_phase) {
        stage_all(phase, pointer);
        last_phase = phase;
        last_pointer = pointer;
        all_dirty = 1;
        pointer_dirty = 0;
        return;
    }
    if (pointer != last_pointer) {
        last_pointer = pointer;
        pend_scb3[RING_N] = pointer
            ? (u16)(((u16)(496 - RING_POINTER_Y) << 7) | 1) : 0;
        pointer_dirty = 1;
    }
}

static void write_slot_scb1(u8 j)
{
    u16 s = (u16)(RING_SPRITE + j);

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB1 + s * 64);
    *REG_VRAMRW = pend_tile[j];
    *REG_VRAMRW = pend_attr[j];
}

void ring_gfx_commit(void)
{
    u8 k, i;

    if (pal_dirty) {
        for (k = 0; k < 3; k++) {
            u16 bank = (u16)(PAL_RING_BASE + k);

            for (i = 0; i < 16; i++)
                MMAP_PALBANK1[bank * 16 + i] = ring_pal[k][i];
        }
        pal_dirty = 0;
    }

    if (all_dirty) {
        for (k = 0; k < RING_COUNT; k++) {
            write_slot_scb1(k);
            /* the auto-increment does not skip from SCB4 back to SCB2, so
             * each slot's three SCB2/3/4 words start from its own address
             * (as radar_gfx.c does). */
            *REG_VRAMMOD = 0x200;
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + RING_SPRITE + k);
            *REG_VRAMRW = pend_scb2[k];
            *REG_VRAMRW = pend_scb3[k];
            *REG_VRAMRW = pend_scb4[k];
        }
        all_dirty = 0;
        pointer_dirty = 0;
    } else if (pointer_dirty) {
        write_slot_scb1(RING_N);
        *REG_VRAMMOD = 0x200;
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + RING_SPRITE + RING_N);
        *REG_VRAMRW = pend_scb2[RING_N];
        *REG_VRAMRW = pend_scb3[RING_N];
        *REG_VRAMRW = pend_scb4[RING_N];
        pointer_dirty = 0;
    }

    /* K2: the flying letter, its own slot above the ring; one tile, so its
     * SCB1 row is one tile/attr pair. */
    if (fly_dirty) {
        *REG_VRAMMOD = 1;
        *REG_VRAMADDR = (u16)(ADDR_SCB1 + (u16)FLY_SPRITE * 64);
        *REG_VRAMRW = pend_fly_tile;
        *REG_VRAMRW = pend_fly_attr;
        *REG_VRAMMOD = 0x200;
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + FLY_SPRITE);
        *REG_VRAMRW = pend_fly_scb2;
        *REG_VRAMRW = pend_fly_scb3;
        *REG_VRAMRW = pend_fly_scb4;
        fly_dirty = 0;
    }
}
