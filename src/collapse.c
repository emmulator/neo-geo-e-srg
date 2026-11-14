/* collapse.c: see collapse.h. The fireball's and the fragments' words, the
 * puffs of the shake and the plumes of smoke from the ruin, all staged in
 * RAM by collapse_prepare and written in vblank by collapse_commit (as the
 * props after Task 18), so no collapse slot is rewritten while the raster
 * is inside it.
 *
 * The fire columns are independent sprites: column c sits at
 * fire_x + c * (hz + 1), its own SCB2 (hz << 8 | v), SCB3 (Y and height)
 * and SCB4. A column whose fire_mask bit is 0 is SCB3 0 (it is empty in
 * that picture and would only cost sprites on its lines).
 *
 * The fragments are NFRAGS (49 in Task V2's generator) independent full-size
 * columns (one tile wide,
 * frag_rows tall) in the dome's own bank (PAL_DOME): the glass cut from
 * view 0. Their placement is SCB3/SCB4 from frag_x/frag_y, hidden = SCB3 0;
 * their SCB1 is rewritten when the whole-piece flip changes or the piece is
 * first shown. A V flip reverses a 2-tile fragment's rows (bottom tile in
 * row 0) as well as setting the attribute's V bit.
 *
 * Task C4 adds the puffs and the smoke. The puffs are NPUFFS (5) small
 * full-size 2 x 2-tile bursts shown during the shake (f 0..40) in the
 * fire's bank PAL_FIRE: puff n shows picture i = (f - puff_f0[n]) /
 * PUFF_STEP while 0 <= i < PUFF_FRAMES, at (puff_x[n], puff_y[n]), in the
 * slot pair n % 3 (six slots, at most three puffs at once). From the burst
 * (f 41) every puff is hidden. The smoke is NPLUMES (6) plumes of
 * SMOKE_COLS x SMOKE_ROWS (2 x 7) tiles in their own bank PAL_SMOKE, each
 * an 8-picture loop. Per plume and g the header gives smoke_pic (0xff = not
 * started), smoke_dx, smoke_lines, smoke_v (SCB2 0x0f00 | v) and smoke_h
 * (SCB3 height); per scene step a it gives the plume's foot x/y and whether
 * it is in front of the ruin (smoke_front). From SMOKE_T on the tables
 * repeat every SMOKE_PERIOD from SMOKE_LOOP. Each frame the plumes take the
 * next free FRONT pair of the overlay range's six columns when their front
 * bit is set, else the next free BACK pair right below DOME_SPRITE; the
 * columns are independent (col c at left + 16 c).
 *
 * The collapse keeps its own g (Task C4): g = collapse_frac -
 * COLLAPSE_SHAKE while the dome death runs, then one more every frame while
 * dome_draw_gone (the dome-death GAME OVER). The GAME OVER starts when
 * dead_t reaches 0 (g 77), so collapse_frac is 0 from then on; the A
 * restart ends the smoke (the dome is whole again and the overlay range is
 * the cracks' again).
 *
 * The one-time SCB1 blanking (the rows the hardware may sample below a
 * shrunk fire column, the fragments' rows, the twelve smoke columns' rows
 * 7..31 and the puffs' rows 2..31) is spread over the shake's frames
 * f 0..40, puffs first (they first show at f 14): 56 rows a frame, 2214
 * rows in all, so
 * no collapse frame's commit is over ~600 words. The old C2/C3 whole-frame
 * blanking (2046 words on f 0) is gone; the C2/C3 word proofs still hold
 * because every row is blank before the burst (f 41).
 *
 * The pictures are swapped by the CPU, never by the LSPC's auto-animation
 * (one global counter cannot give each plume its own phase): a plume's
 * picture changes every 3 frames, so a frame writes at most 6 plumes x 2
 * columns x 7 tile words = 84 tile words (plus the columns' placement).
 */
#include <ngdevkit/neogeo.h>
#include "collapse.h"
#include "dome.h"            /* COLLAPSE_TILE_BASE, PAL_DOME, dome_draw_gone */
#include "slots.h"           /* COLLAPSE_FIRE/FRAG/SMOKE/PUFF_SPRITE/COUNT */

/* Task C2/C3/C4's generated tables: the fireball's, the fragments', the
 * puffs' and the smoke's pictures, palettes and per-g words. */
#include "collapse_map.h"

#ifdef SOUND_TEST
/* The -DSOUND_TEST carts (the M7 sound tests) never play the collapse.
 * Keep this object free of BSS: their RAM log lives in flow.o, and the
 * MVS BIOS's garbage at an address shifted by collapse.o's RAM passes the
 * sound probe's sanity gates. The normal cart and every other test cart
 * link the real implementation below. */
void collapse_init(void)
{
}

void collapse_prepare(const rules_t *r, u8 angle)
{
    (void)r;
    (void)angle;
}

void collapse_commit(void)
{
}

#else
/* the hardware can sample SCB1 rows up to 31 (see lessons.md, "The Neo Geo
 * vertical zoom table"): every row the picture does not fill must be blank */
#define FIRE_SCB1_ROWS 32
#define FRAG_SCB1_ROWS 32
#define PUFF_SCB1_ROWS 32
#define SMOKE_SCB1_ROWS 32

/* Task V1: the plumes' twelve independent columns are split over two
 * ranges: SMOKE_BACK_SPRITE (right below the dome, so the ruin draws over
 * them) and COLLAPSE_SMOKE_SPRITE (the overlay range, in front). The
 * combined index 0..SMOKE_BACK_COUNT-1 is the back range and the rest the
 * front one; smoke_slot_num maps it to the real sprite slot. */
#define SMOKE_SLOT_COUNT (SMOKE_BACK_COUNT + COLLAPSE_SMOKE_COUNT)

/* the part's own blank tile (tile 0) at the absolute C ROM number */
#define FIRE_BLANK (COLLAPSE_TILE_BASE + 0)

/* the one-time blanking's rows, in order: puffs (first, they show at f 14),
 * the smoke's rows 7..31, the fireball's rows 10..31 and the fragments'
 * rows 2..31. Task V2's generator keeps 49 fragments (was 43), so the rows
 * are 180 + 300 + 264 + 1470 = 2214 over the shake's f 1..40 (f 0 stages
 * only the initial hidden words) -> 56 a frame (2240, enough). */
#define BLANK_PUFF_ROWS  (COLLAPSE_PUFF_COUNT * (PUFF_SCB1_ROWS - PUFF_ROWS))
#define BLANK_SMOKE_ROWS (SMOKE_SLOT_COUNT * (SMOKE_SCB1_ROWS - SMOKE_ROWS))
#define BLANK_FIRE_ROWS  (FIRE_COLS * (FIRE_SCB1_ROWS - FIRE_ROWS))
#define BLANK_FRAG_ROWS  (NFRAGS * (FRAG_SCB1_ROWS - FRAG_MAX_ROWS))
#define BLANK_ROWS (BLANK_PUFF_ROWS + BLANK_SMOKE_ROWS + BLANK_FIRE_ROWS \
                    + BLANK_FRAG_ROWS)
#define BLANK_PER_FRAME 56

/* the blanking's state: which layer/slot/row the next row belongs to, and
 * the staged chunk (address, tile and attribute per row). */
static u8 blank_layer, blank_slot, blank_row;
static u16 blank_pos;
static u8 blank_n;
static u16 blank_addr[BLANK_PER_FRAME];
static u16 blank_tile[BLANK_PER_FRAME];
static u16 blank_attr[BLANK_PER_FRAME];

/* the fire memo: the last committed words of each column, and the last
 * committed picture (0xff = none). */
static u16 prev_scb2[FIRE_COLS], prev_scb3[FIRE_COLS], prev_scb4[FIRE_COLS];
static u8 prev_pic;

/* the fire staged writes: rows 0..FIRE_ROWS-1 of every column when the
 * picture changed, and the placement words of the columns that changed. */
static u16 pend_tile[FIRE_COLS][FIRE_ROWS];
static u16 pend_scb2[FIRE_COLS], pend_scb3[FIRE_COLS], pend_scb4[FIRE_COLS];
static u8 tile_dirty;
static u8 place_dirty[FIRE_COLS];

/* the fragment memo: the last committed placement and flip, whether the
 * piece was shown, and the staged words. */
static u16 frag_prev_scb3[NFRAGS], frag_prev_scb4[NFRAGS];
static u8 frag_prev_flip[NFRAGS], frag_prev_shown[NFRAGS];
static u16 frag_pend_scb3[NFRAGS], frag_pend_scb4[NFRAGS];
static u16 frag_pend_tile[NFRAGS][FRAG_MAX_ROWS];
static u8 frag_pend_flip[NFRAGS];
static u8 frag_place_dirty[NFRAGS], frag_tile_dirty[NFRAGS];
static u8 frag_any_shown;
static u8 frag_dirty_any;

/* Task C4: the puff memo and staged words. The six slots are three pairs
 * (puff n in pair n % 3), so the placement memo is per slot and the tile
 * memo is per slot (both columns of the pair are staged together). */
static u16 puff_prev_scb2[COLLAPSE_PUFF_COUNT];
static u16 puff_prev_scb3[COLLAPSE_PUFF_COUNT];
static u16 puff_prev_scb4[COLLAPSE_PUFF_COUNT];
static u8 puff_prev_pic[NPUFFS], puff_prev_shown[NPUFFS];
static u16 puff_pend_tile[COLLAPSE_PUFF_COUNT][PUFF_ROWS];
static u16 puff_pend_scb2[COLLAPSE_PUFF_COUNT];
static u16 puff_pend_scb3[COLLAPSE_PUFF_COUNT];
static u16 puff_pend_scb4[COLLAPSE_PUFF_COUNT];
static u8 puff_tile_dirty[COLLAPSE_PUFF_COUNT];
static u8 puff_place_dirty[COLLAPSE_PUFF_COUNT];
static u8 puff_dirty_any;

/* Task C4/V1: the smoke memo and staged words (twelve independent columns,
 * the combined back/front index). smoke_prev_p remembers which plume
 * picture a combined slot last showed (p = 0xff when hidden), so a plume
 * crossing from a back pair to a front pair (or swapping pairs) rewrites the
 * SCB1 tiles of the slot it moves into. */
static u16 smoke_prev_scb2[SMOKE_SLOT_COUNT];
static u16 smoke_prev_scb3[SMOKE_SLOT_COUNT];
static u16 smoke_prev_scb4[SMOKE_SLOT_COUNT];
static u8 smoke_prev_p[SMOKE_SLOT_COUNT];
static u8 smoke_prev_pic_slot[SMOKE_SLOT_COUNT];
static u16 smoke_pend_tile[SMOKE_SLOT_COUNT][SMOKE_ROWS];
static u16 smoke_pend_scb2[SMOKE_SLOT_COUNT];
static u16 smoke_pend_scb3[SMOKE_SLOT_COUNT];
static u16 smoke_pend_scb4[SMOKE_SLOT_COUNT];
static u8 smoke_tile_dirty[SMOKE_SLOT_COUNT];
static u8 smoke_place_dirty[SMOKE_SLOT_COUNT];
static u8 smoke_dirty_any;

/* the collapse's own g (Task C4) and whether a collapse (live or its GAME
 * OVER) was active on the previous frame. */
static u16 own_g;
static u8 own_state;          /* 0 idle, 1 collapse, 2 GAME OVER */
static u8 was_active;
/* Task C4: the first collapse frame stages no hidden words (that work, and
 * the first blanking chunk, would push src/cracks.c's one-time overlay hide
 * into the visible lines); collapse_commit writes the initial hidden
 * SCB2/SCB3/SCB4 of every collapse slot directly in that frame's vblank. */
static u8 initial_hides;

/* the combined plume-column index -> the real sprite slot. */
static u16 smoke_slot_num(u8 i)
{
    if (i < SMOKE_BACK_COUNT)
        return (u16)(SMOKE_BACK_SPRITE + i);
    return (u16)(COLLAPSE_SMOKE_SPRITE + (u8)(i - SMOKE_BACK_COUNT));
}

static const u8 blank_count[4] = {
    COLLAPSE_PUFF_COUNT, SMOKE_SLOT_COUNT, FIRE_COLS, NFRAGS
};
static const u8 blank_start[5] = {
    PUFF_ROWS, SMOKE_ROWS, FIRE_ROWS, FRAG_MAX_ROWS, 0
};

void collapse_init(void)
{
    u8 i, c;

    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_FIRE * 16 + i] = fire_pal[i];
    MMAP_PALBANK1[PAL_FIRE * 16] = 0x8000;       /* entry 0: transparent */
    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_SMOKE * 16 + i] = smoke_pal[i];
    MMAP_PALBANK1[PAL_SMOKE * 16] = 0x8000;

    /* Task V1: the back smoke slots are outside the broken overlays' range
     * (which src/cracks.c hides at boot), so hide all twelve plume columns
     * here: SCB3 0 is the hardware's "not drawn". The front six are inside
     * the overlay range and cracks hides them again; this keeps every slot
     * deterministic from boot. */
    *REG_VRAMMOD = 0x200;
    for (i = 0; i < SMOKE_SLOT_COUNT; i++) {
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + smoke_slot_num(i));
        *REG_VRAMRW = 0x0f00;
        *REG_VRAMRW = 0;
        *REG_VRAMRW = 0;
    }

    /* every memo starts at a value the first collapse cannot match, so the
     * first prepare stages the hidden placement and the first pictures. */
    prev_pic = 0xff;
    for (c = 0; c < FIRE_COLS; c++) {
        prev_scb2[c] = 0xffff;
        prev_scb3[c] = 0xffff;
        prev_scb4[c] = 0xffff;
        place_dirty[c] = 0;
    }
    for (c = 0; c < NFRAGS; c++) {
        frag_prev_scb3[c] = 0xffff;
        frag_prev_scb4[c] = 0xffff;
        frag_prev_flip[c] = 0xff;
        frag_prev_shown[c] = 0;
        frag_place_dirty[c] = 0;
        frag_tile_dirty[c] = 0;
    }
    for (c = 0; c < COLLAPSE_PUFF_COUNT; c++) {
        puff_prev_scb2[c] = 0xffff;
        puff_prev_scb3[c] = 0xffff;
        puff_prev_scb4[c] = 0xffff;
        puff_tile_dirty[c] = 0;
        puff_place_dirty[c] = 0;
    }
    for (c = 0; c < NPUFFS; c++) {
        puff_prev_pic[c] = 0xff;
        puff_prev_shown[c] = 0;
    }
    for (c = 0; c < SMOKE_SLOT_COUNT; c++) {
        smoke_prev_scb2[c] = 0xffff;
        smoke_prev_scb3[c] = 0xffff;
        smoke_prev_scb4[c] = 0xffff;
        smoke_prev_p[c] = 0xff;
        smoke_prev_pic_slot[c] = 0xff;
        smoke_tile_dirty[c] = 0;
        smoke_place_dirty[c] = 0;
    }

    own_g = 0;
    own_state = 0;
    was_active = 0;
    initial_hides = 0;
    blank_n = 0;
}

/* reset the memos for a new collapse. They start at the HIDDEN words, not
 * at a "needs a write" sentinel: the first collapse frame stages no hidden
 * words (collapse_commit writes the initial hidden SCB2/SCB3/SCB4 directly
 * in that frame's vblank), so src/cracks.c's overlay hide runs early
 * enough to stay out of the visible lines. The first pictures are staged
 * when they first show. */
static void reset_fire(void)
{
    u8 c;

    prev_pic = 0xff;
    for (c = 0; c < FIRE_COLS; c++) {
        prev_scb2[c] = 0x0fff;
        prev_scb3[c] = 0;
        prev_scb4[c] = 0;
    }
}

static void reset_frag(void)
{
    u8 n;

    for (n = 0; n < NFRAGS; n++) {
        frag_prev_scb3[n] = 0;
        frag_prev_scb4[n] = 0;
        frag_prev_flip[n] = 0xff;
        frag_prev_shown[n] = 0;
    }
    frag_any_shown = 0;
}

static void reset_puffs(void)
{
    u8 c, n;

    for (c = 0; c < COLLAPSE_PUFF_COUNT; c++) {
        puff_prev_scb2[c] = 0x0fff;
        puff_prev_scb3[c] = 0;
        puff_prev_scb4[c] = 0;
    }
    for (n = 0; n < NPUFFS; n++) {
        puff_prev_pic[n] = 0xff;
        puff_prev_shown[n] = 0;
    }
}

static void reset_smoke(void)
{
    u8 c;

    for (c = 0; c < SMOKE_SLOT_COUNT; c++) {
        smoke_prev_scb2[c] = 0x0f00;
        smoke_prev_scb3[c] = 0;
        smoke_prev_scb4[c] = 0;
        smoke_prev_p[c] = 0xff;
        smoke_prev_pic_slot[c] = 0xff;
    }
}

/* restart the one-time blanking for a new collapse. */
static void reset_blank(void)
{
    blank_layer = 0;
    blank_slot = 0;
    blank_row = PUFF_ROWS;
    blank_pos = 0;
    blank_n = 0;
}

/* stage BLANK_PER_FRAME rows of the one-time blanking, in order. The
 * mapping is incremental (no divide): puffs 2..31, smoke 7..31, fire
 * 10..31, fragments 2..31. */
static void stage_blank_rows(void)
{
    u8 n = 0;

    while (n < BLANK_PER_FRAME && blank_pos < BLANK_ROWS) {
        u16 slot, attr;

        switch (blank_layer) {
        case 0:  slot = (u16)(COLLAPSE_PUFF_SPRITE + blank_slot);
                 attr = PAL_FIRE << 8;  break;
        case 1:  slot = smoke_slot_num(blank_slot);
                 attr = PAL_SMOKE << 8; break;
        case 2:  slot = (u16)(COLLAPSE_FIRE_SPRITE + blank_slot);
                 attr = PAL_FIRE << 8;  break;
        default: slot = (u16)(COLLAPSE_FRAG_SPRITE + blank_slot);
                 attr = PAL_DOME << 8;  break;
        }
        blank_addr[n] = (u16)(ADDR_SCB1 + slot * 64 + blank_row * 2);
        blank_tile[n] = FIRE_BLANK;
        blank_attr[n] = attr;
        n++;
        blank_pos++;

        blank_row++;
        if (blank_row >= 32) {
            blank_slot++;
            if (blank_slot >= blank_count[blank_layer]) {
                blank_layer++;
                blank_slot = 0;
            }
            blank_row = blank_start[blank_layer];
        }
    }
    blank_n = n;
}

/* stage one fire column's placement words only when they differ from the
 * last commit's (the memo is updated here, as the props' prepare does). */
static void stage_place(u8 c, u16 scb2, u16 scb3, u16 scb4)
{
    if (scb2 == prev_scb2[c] && scb3 == prev_scb3[c] && scb4 == prev_scb4[c])
        return;
    pend_scb2[c] = scb2;
    pend_scb3[c] = scb3;
    pend_scb4[c] = scb4;
    place_dirty[c] = 1;
    prev_scb2[c] = scb2;
    prev_scb3[c] = scb3;
    prev_scb4[c] = scb4;
}

/* stage one fragment's placement (SCB3/SCB4) when it changed. */
static void stage_frag_place(u8 n, u16 scb3, u16 scb4)
{
    if (scb3 == frag_prev_scb3[n] && scb4 == frag_prev_scb4[n])
        return;
    frag_pend_scb3[n] = scb3;
    frag_pend_scb4[n] = scb4;
    frag_place_dirty[n] = 1;
    frag_dirty_any = 1;
    frag_prev_scb3[n] = scb3;
    frag_prev_scb4[n] = scb4;
}

/* stage a fragment's SCB1 rows 0..FRAG_MAX_ROWS-1 with the whole-piece
 * flip: the attribute carries the H/V bits, and a V flip reverses a 2-tile
 * piece's rows (bottom tile in row 0). A 1-tile piece's unused second row
 * is the part's blank tile. */
static void stage_frag_tiles(u8 n, u8 flip)
{
    u8 r, rows = frag_rows[n];
    u8 v = (u8)(flip & 2);

    for (r = 0; r < FRAG_MAX_ROWS; r++) {
        u16 t;
        if (r < rows)
            t = frag_tile[n][v ? (u8)(rows - 1 - r) : r];
        else
            t = 0;
        frag_pend_tile[n][r] = (u16)(COLLAPSE_TILE_BASE + t);
    }
    frag_pend_flip[n] = flip;
    frag_tile_dirty[n] = 1;
    frag_dirty_any = 1;
    frag_prev_flip[n] = flip;
}

/* Task C4: stage one puff slot's placement (SCB2/3/4) when it changed. */
static void stage_puff_place(u8 slot, u16 scb2, u16 scb3, u16 scb4)
{
    if (scb2 == puff_prev_scb2[slot] && scb3 == puff_prev_scb3[slot]
        && scb4 == puff_prev_scb4[slot])
        return;
    puff_pend_scb2[slot] = scb2;
    puff_pend_scb3[slot] = scb3;
    puff_pend_scb4[slot] = scb4;
    puff_place_dirty[slot] = 1;
    puff_dirty_any = 1;
    puff_prev_scb2[slot] = scb2;
    puff_prev_scb3[slot] = scb3;
    puff_prev_scb4[slot] = scb4;
}

/* Task C4: stage both columns of a puff pair's 2 x 2-tile picture. */
static void stage_puff_tiles(u8 pair, u8 pic)
{
    u8 col, r;

    for (col = 0; col < PUFF_COLS; col++) {
        u8 slot = (u8)(pair * PUFF_COLS + col);
        for (r = 0; r < PUFF_ROWS; r++)
            puff_pend_tile[slot][r] = (u16)(COLLAPSE_TILE_BASE
                                            + puff_tile[pic][col][r]);
        puff_tile_dirty[slot] = 1;
    }
    puff_dirty_any = 1;
}

/* Task C4: hide all six puff slots (the burst, and out of the collapse). */
static void hide_puffs(void)
{
    u8 pair, col, n;

    for (n = 0; n < NPUFFS; n++) {
        puff_prev_shown[n] = 0;
        puff_prev_pic[n] = 0xff;
    }
    for (pair = 0; pair < 3; pair++) {
        for (col = 0; col < PUFF_COLS; col++)
            stage_puff_place((u8)(pair * PUFF_COLS + col), 0x0fff, 0, 0);
    }
}

/* Task C4: the shake's puffs, at displayed f. Puff n shows picture i while
 * 0 <= i < PUFF_FRAMES; only the three pairs used by a shown puff are
 * placed, the others are hidden. */
static void show_puffs(u8 f)
{
    u8 used[3] = { 0, 0, 0 };
    u8 n, pair, col;

    for (n = 0; n < NPUFFS; n++) {
        u8 i = 0xff;

        if (f >= puff_f0[n]) {
            u8 d = (u8)(f - puff_f0[n]);
            i = (u8)(d / PUFF_STEP);
            if (i >= PUFF_FRAMES)
                i = 0xff;
        }
        if (i == 0xff) {
            puff_prev_shown[n] = 0;
            puff_prev_pic[n] = 0xff;
            continue;
        }
        pair = n;
        if (pair >= 3)
            pair = (u8)(pair - 3);       /* n % 3, n < NPUFFS (5) */
        used[pair] = 1;
        for (col = 0; col < PUFF_COLS; col++) {
            u8 slot = (u8)(pair * PUFF_COLS + col);
            stage_puff_place(slot, 0x0fff,
                             (u16)(((496 - puff_y[n]) << 7) | PUFF_ROWS),
                             (u16)(((puff_x[n] + col * 16) & 0x1ff) << 7));
        }
        if (!puff_prev_shown[n] || puff_prev_pic[n] != i)
            stage_puff_tiles(pair, i);
        puff_prev_shown[n] = 1;
        puff_prev_pic[n] = i;
    }
    for (pair = 0; pair < 3; pair++) {
        if (used[pair])
            continue;
        for (col = 0; col < PUFF_COLS; col++)
            stage_puff_place((u8)(pair * PUFF_COLS + col), 0x0fff, 0, 0);
    }
}

/* Task C4/V1: stage one smoke column's placement (SCB2/3/4) when it
 * changed. `i` is the combined back/front index. */
static void stage_smoke_place(u8 i, u16 scb2, u16 scb3, u16 scb4)
{
    if (scb2 == smoke_prev_scb2[i] && scb3 == smoke_prev_scb3[i]
        && scb4 == smoke_prev_scb4[i])
        return;
    smoke_pend_scb2[i] = scb2;
    smoke_pend_scb3[i] = scb3;
    smoke_pend_scb4[i] = scb4;
    smoke_place_dirty[i] = 1;
    smoke_dirty_any = 1;
    smoke_prev_scb2[i] = scb2;
    smoke_prev_scb3[i] = scb3;
    smoke_prev_scb4[i] = scb4;
}

/* Task C4/V1: hide all twelve smoke columns. */
static void hide_smoke(void)
{
    u8 i;

    for (i = 0; i < SMOKE_SLOT_COUNT; i++) {
        stage_smoke_place(i, 0x0f00, 0, 0);
        smoke_prev_p[i] = 0xff;
        smoke_prev_pic_slot[i] = 0xff;
    }
}

/* Task C4/V1: the smoke at the scene's angle `angle` and the collapse's own
 * g (wrapped from SMOKE_T on, as today). Each plume p takes the next free
 * FRONT pair of columns when bit p of smoke_front[angle] is set, else the
 * next free BACK pair; the pairs are two independent columns each, in the
 * two slot ranges. A plume that has not started (smoke_pic 0xff) leaves its
 * pair hidden, and any pair the assignment does not fill is hidden too
 * (SCB3 0). */
static u16 smoke_s2[SMOKE_SLOT_COUNT];   /* the staged words */
static u16 smoke_s3[SMOKE_SLOT_COUNT];
static u16 smoke_s4[SMOKE_SLOT_COUNT];

static void show_smoke(u8 angle, u16 g)
{
    u8 i, p, c, fp = 0, bp = 0;
    u16 gg = g;
    u8 want_p[SMOKE_SLOT_COUNT], want_pic[SMOKE_SLOT_COUNT];
    u8 want_col[SMOKE_SLOT_COUNT];

    if (gg >= SMOKE_T)
        gg = (u16)(SMOKE_LOOP + (gg - SMOKE_LOOP) % SMOKE_PERIOD);

    /* every column starts hidden this frame; the plumes below fill their
     * assigned pairs */
    for (i = 0; i < SMOKE_SLOT_COUNT; i++) {
        smoke_s2[i] = 0x0f00;
        smoke_s3[i] = 0;
        smoke_s4[i] = 0;
        want_p[i] = 0xff;
        want_pic[i] = 0xff;
        want_col[i] = 0;
    }

    for (p = 0; p < NPLUMES; p++) {
        u8 pic = smoke_pic[p][gg];
        u8 slot0;
        s16 left, top;

        if (smoke_front[angle] & (1u << p)) {
            slot0 = (u8)(SMOKE_BACK_COUNT + fp * SMOKE_COLS);
            fp++;
        } else {
            slot0 = (u8)(bp * SMOKE_COLS);
            bp++;
        }
        if (pic == 0xff)
            continue;               /* not started: its pair stays hidden */

        left = (s16)(smoke_foot_x[angle][p] + smoke_dx[p][gg]
                     - SMOKE_COLS * 8);
        top = (s16)(smoke_foot_y[angle][p] - smoke_lines[p][gg]);
        for (c = 0; c < SMOKE_COLS; c++) {
            i = (u8)(slot0 + c);
            smoke_s2[i] = (u16)(0x0f00 | smoke_v[p][gg]);
            smoke_s3[i] = (u16)(((496 - top) << 7) | smoke_h[p][gg]);
            smoke_s4[i] = (u16)(((left + (s16)c * 16) & 0x1ff) << 7);
            want_p[i] = p;
            want_pic[i] = pic;
            want_col[i] = c;
        }
    }

    /* stage each column's words and the SCB1 tiles when its plume or
     * picture changed (a crossing into another pair included). */
    for (i = 0; i < SMOKE_SLOT_COUNT; i++) {
        stage_smoke_place(i, smoke_s2[i], smoke_s3[i], smoke_s4[i]);
        if (want_p[i] == smoke_prev_p[i]
            && want_pic[i] == smoke_prev_pic_slot[i])
            continue;
        if (want_p[i] != 0xff) {
            u8 r;

            for (r = 0; r < SMOKE_ROWS; r++)
                smoke_pend_tile[i][r] = (u16)(COLLAPSE_TILE_BASE
                    + smoke_tile[want_p[i]][want_pic[i]][want_col[i]][r]);
            smoke_tile_dirty[i] = 1;
            smoke_dirty_any = 1;
        }
        smoke_prev_p[i] = want_p[i];
        smoke_prev_pic_slot[i] = want_pic[i];
    }

    /* unused pairs are hidden (the header always sets three front bits, so
     * normally nothing is left over) */
    for (; fp < COLLAPSE_SMOKE_COUNT / SMOKE_COLS; fp++) {
        u8 slot0 = (u8)(SMOKE_BACK_COUNT + fp * SMOKE_COLS);
        for (c = 0; c < SMOKE_COLS; c++)
            stage_smoke_place((u8)(slot0 + c), 0x0f00, 0, 0);
    }
    for (; bp < SMOKE_BACK_COUNT / SMOKE_COLS; bp++) {
        u8 slot0 = (u8)(bp * SMOKE_COLS);
        for (c = 0; c < SMOKE_COLS; c++)
            stage_smoke_place((u8)(slot0 + c), 0x0f00, 0, 0);
    }
}

void collapse_prepare(const rules_t *r, u8 angle)
{
    u8 f = collapse_frac(r);
    u8 live = (u8)(r->dead_t && r->dome_dead);
    u8 gone = (u8)dome_draw_gone(r);
    u8 active = (u8)(live && f >= COLLAPSE_SHAKE);
    u8 shake = (u8)(live && f < COLLAPSE_SHAKE);
    u8 was = was_active;              /* the previous frame's state */
    u8 c, n;

    /* the common non-collapse frame: nothing was shown since the last
     * collapse and the memos are already hidden, so return before the
     * reset loops: the overlays, ship and props run later in game_frame
     * and must keep their old timing. */
    if (!live && !gone && !was_active)
        return;

    /* clear the staged flags (the helpers set them again) */
    tile_dirty = 0;
    for (c = 0; c < FIRE_COLS; c++)
        place_dirty[c] = 0;
    frag_dirty_any = 0;
    for (n = 0; n < NFRAGS; n++) {
        frag_place_dirty[n] = 0;
        frag_tile_dirty[n] = 0;
    }
    puff_dirty_any = 0;
    for (c = 0; c < COLLAPSE_PUFF_COUNT; c++) {
        puff_place_dirty[c] = 0;
        puff_tile_dirty[c] = 0;
    }
    smoke_dirty_any = 0;
    for (c = 0; c < SMOKE_SLOT_COUNT; c++) {
        smoke_place_dirty[c] = 0;
        smoke_tile_dirty[c] = 0;
    }
    blank_n = 0;

    /* the collapse's own g: collapse_frac - COLLAPSE_SHAKE while the dome
     * death runs, then one more every frame under its GAME OVER. */
    if (live) {
        own_g = (u16)(f >= COLLAPSE_SHAKE
                      ? f - COLLAPSE_SHAKE : 0);
        own_state = 1;
    } else if (gone) {
        if (own_state == 1 || own_state == 2)
            own_g++;
        else
            own_g = (u16)(DEAD_FRAMES - COLLAPSE_SHAKE);   /* 77 */
        own_state = 2;
    } else {
        own_state = 0;
    }
    was_active = (u8)(live || gone);

    /* a new collapse: reset the memos and the blanking schedule. The memos
     * start at the hidden words; collapse_commit writes those words for
     * every collapse slot in this frame's vblank (initial_hides), so the
     * prepare stays short enough for cracks_show to hide the overlays
     * before the visible lines. */
    if (live && f == 0) {
        reset_fire();
        reset_frag();
        reset_puffs();
        reset_smoke();
        reset_blank();
        initial_hides = 1;
    }

    /* the one-time blanking, spread over the shake's f 1..40: 52 rows a
     * frame (2080 > the 2049 rows), puffs first (they first show at f 14). */
    if (live && f >= 1 && f < COLLAPSE_SHAKE)
        stage_blank_rows();

    /* the fireball: hidden before the burst and after FIRE_T. */
    if (active && own_g < FIRE_T) {
        u16 s2 = fire_scb2[own_g];
        u8 hz = (u8)(s2 >> 8);
        s16 x = fire_x[own_g], y = fire_y[own_g];
        u16 mask = fire_mask[own_g];
        u8 pic = fire_pic[own_g];

        if (pic != prev_pic) {
            for (c = 0; c < FIRE_COLS; c++) {
                u8 rr;
                for (rr = 0; rr < FIRE_ROWS; rr++)
                    pend_tile[c][rr] = (u16)(COLLAPSE_TILE_BASE
                                             + fire_tile[pic][c][rr]);
            }
            tile_dirty = 1;
            prev_pic = pic;
        }
        for (c = 0; c < FIRE_COLS; c++) {
            u16 scb3 = (mask & (1u << c))
                ? (u16)(((496 - y) << 7) | fire_h[own_g]) : 0;
            u16 scb4 = (u16)(((x + (s16)c * (s16)(hz + 1)) & 0x1ff) << 7);

            stage_place(c, s2, scb3, scb4);
        }
    } else {
        for (c = 0; c < FIRE_COLS; c++)
            stage_place(c, 0x0fff, 0, 0);
    }

    /* the fragments: hidden before launch and after they leave the screen;
     * their SCB1 is rewritten only when the whole-piece flip changes or the
     * piece is first shown. */
    if (active && own_g < FRAG_T) {
        u8 any = 0;
        for (n = 0; n < NFRAGS; n++) {
            s16 x = frag_x[n][own_g], y = frag_y[n][own_g];
            u8 hidden = (u8)(x == COLLAPSE_HIDE || y == COLLAPSE_HIDE);
            u16 scb3 = 0, scb4 = 0;

            if (!hidden) {
                scb3 = (u16)(((496 - y) << 7) | frag_rows[n]);
                scb4 = (u16)(((x & 0x1ff) << 7));
                any = 1;
            }
            stage_frag_place(n, scb3, scb4);
            if (!hidden) {
                u8 flip = frag_flip[n][own_g];
                if (!frag_prev_shown[n] || flip != frag_prev_flip[n])
                    stage_frag_tiles(n, flip);
                frag_prev_shown[n] = 1;
            } else {
                frag_prev_shown[n] = 0;
            }
        }
        frag_any_shown = any;
    } else {
        /* hidden before launch, after FRAG_T and out of the collapse: the
         * placement memo makes this write only on the transitions (and on
         * f 0, where the sentinel reset hides every slot; the SCB2 reset
         * is what C3's word proof expects). */
        for (n = 0; n < NFRAGS; n++) {
            stage_frag_place(n, 0, 0);
            frag_prev_shown[n] = 0;
        }
        frag_any_shown = 0;
    }

    /* Task C4: the shake's puffs, then (from the burst on) hidden. */
    if (shake)
        show_puffs(f);
    else
        hide_puffs();

    /* Task C4/V1: the smoke from the ruin, through the dome-death GAME
     * OVER; the A restart (or the rebuild) hides it. On the last death
     * frame before a rebuild, hide it a frame early: cracks_show is
     * already hiding the FRONT smoke in the overlay range on that frame,
     * and the BACK smoke below DOME must go with it (otherwise only the
     * back half of the ring would survive the rebuild frame). A
     * game-ending death (lives 0) keeps the smoke through GAME OVER. On
     * the first frame after the collapse, the FRONT slots are hidden by
     * cracks_show's direct overlay hide; the BACK slots are outside that
     * range, so hide their SCB3 directly on that same frame. */
    if (live && r->dead_t == 1 && r->lives > 0) {
        hide_smoke();
    } else if (live || gone) {
        show_smoke(angle, own_g);
    } else {
        hide_smoke();
        if (was) {
            *REG_VRAMMOD = 0x200;
            for (c = 0; c < SMOKE_BACK_COUNT; c++) {
                *REG_VRAMADDR = (u16)(ADDR_SCB3 + SMOKE_BACK_SPRITE + c);
                *REG_VRAMRW = 0;
            }
        }
    }
}

void collapse_commit(void)
{
    u8 c, rr, n, i;

    /* ---- the first collapse frame's hidden words, written directly in
     * this vblank (src/cracks.c hid the overlay range on the previous
     * frame, so no slot is visible): every collapse slot's SCB2/SCB3/SCB4
     * is reset to its hidden value. This keeps collapse_prepare's f 0
     * short, so cracks_show hides the overlays before the visible lines. */
    if (initial_hides) {
        *REG_VRAMMOD = 0x200;
        for (c = 0; c < FIRE_COLS; c++) {
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + COLLAPSE_FIRE_SPRITE + c);
            *REG_VRAMRW = 0x0fff;
            *REG_VRAMRW = 0;
            *REG_VRAMRW = 0;
        }
        for (n = 0; n < NFRAGS; n++) {
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + COLLAPSE_FRAG_SPRITE + n);
            *REG_VRAMRW = 0x0fff;       /* full size: C3's word proof */
            *REG_VRAMRW = 0;
            *REG_VRAMRW = 0;
        }
        for (c = 0; c < COLLAPSE_PUFF_COUNT; c++) {
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + COLLAPSE_PUFF_SPRITE + c);
            *REG_VRAMRW = 0x0fff;
            *REG_VRAMRW = 0;
            *REG_VRAMRW = 0;
        }
        for (c = 0; c < SMOKE_SLOT_COUNT; c++) {
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + smoke_slot_num(c));
            *REG_VRAMRW = 0x0f00;       /* full width, no shrink */
            *REG_VRAMRW = 0;
            *REG_VRAMRW = 0;
        }
        initial_hides = 0;
    }

    /* ---- the one-time blanking first: rows below the pictures, never
     * visible while the slot is hidden during the shake ---- */
    if (blank_n) {
        *REG_VRAMMOD = 1;
        for (i = 0; i < blank_n; i++) {
            *REG_VRAMADDR = blank_addr[i];
            *REG_VRAMRW = blank_tile[i];
            *REG_VRAMRW = blank_attr[i];
        }
        blank_n = 0;
    }

    /* ---- the fragments (a fragment can be as high as line 45; the
     * fireball never starts above line 80) ---- */
    if (frag_dirty_any) {
        /* the pieces' rows, when a flip changed or the piece is first shown */
        *REG_VRAMMOD = 1;
        for (n = 0; n < NFRAGS; n++) {
            if (!frag_tile_dirty[n])
                continue;
            *REG_VRAMADDR = (u16)(ADDR_SCB1
                                  + (COLLAPSE_FRAG_SPRITE + n) * 64);
            for (rr = 0; rr < FRAG_MAX_ROWS; rr++) {
                *REG_VRAMRW = frag_pend_tile[n][rr];
                *REG_VRAMRW = (u16)((PAL_DOME << 8) | frag_pend_flip[n]);
            }
            frag_tile_dirty[n] = 0;
        }

        /* SCB2 -> SCB3 -> SCB4 for the fragments whose placement changed.
         * The full-size SCB2 is written with the hide/show, so C3's
         * "SCB2 0x0fff" holds from the collapse's first hidden frame on. */
        *REG_VRAMMOD = 0x200;
        for (n = 0; n < NFRAGS; n++) {
            if (!frag_place_dirty[n])
                continue;
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + COLLAPSE_FRAG_SPRITE + n);
            *REG_VRAMRW = 0x0fff;
            *REG_VRAMRW = frag_pend_scb3[n];
            *REG_VRAMRW = frag_pend_scb4[n];
            frag_place_dirty[n] = 0;
        }
        frag_dirty_any = 0;
    }

    /* ---- then the smoke and the puffs (under the fireball) ---- */
    if (smoke_dirty_any) {
        *REG_VRAMMOD = 1;
        for (c = 0; c < SMOKE_SLOT_COUNT; c++) {
            if (!smoke_tile_dirty[c])
                continue;
            *REG_VRAMADDR = (u16)(ADDR_SCB1 + smoke_slot_num(c) * 64);
            for (rr = 0; rr < SMOKE_ROWS; rr++) {
                *REG_VRAMRW = smoke_pend_tile[c][rr];
                *REG_VRAMRW = (u16)(PAL_SMOKE << 8);
            }
            smoke_tile_dirty[c] = 0;
        }
        *REG_VRAMMOD = 0x200;
        for (c = 0; c < SMOKE_SLOT_COUNT; c++) {
            if (!smoke_place_dirty[c])
                continue;
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + smoke_slot_num(c));
            *REG_VRAMRW = smoke_pend_scb2[c];
            *REG_VRAMRW = smoke_pend_scb3[c];
            *REG_VRAMRW = smoke_pend_scb4[c];
            smoke_place_dirty[c] = 0;
        }
        smoke_dirty_any = 0;
    }

    if (puff_dirty_any) {
        *REG_VRAMMOD = 1;
        for (c = 0; c < COLLAPSE_PUFF_COUNT; c++) {
            if (!puff_tile_dirty[c])
                continue;
            *REG_VRAMADDR = (u16)(ADDR_SCB1
                                  + (COLLAPSE_PUFF_SPRITE + c) * 64);
            for (rr = 0; rr < PUFF_ROWS; rr++) {
                *REG_VRAMRW = puff_pend_tile[c][rr];
                *REG_VRAMRW = (u16)(PAL_FIRE << 8);
            }
            puff_tile_dirty[c] = 0;
        }
        *REG_VRAMMOD = 0x200;
        for (c = 0; c < COLLAPSE_PUFF_COUNT; c++) {
            if (!puff_place_dirty[c])
                continue;
            *REG_VRAMADDR = (u16)(ADDR_SCB2 + COLLAPSE_PUFF_SPRITE + c);
            *REG_VRAMRW = puff_pend_scb2[c];
            *REG_VRAMRW = puff_pend_scb3[c];
            *REG_VRAMRW = puff_pend_scb4[c];
            puff_place_dirty[c] = 0;
        }
        puff_dirty_any = 0;
    }

    /* ---- then the fireball ---- */

    /* the picture's rows, rewritten only when fire_pic changed */
    if (tile_dirty) {
        *REG_VRAMMOD = 1;
        for (c = 0; c < FIRE_COLS; c++) {
            *REG_VRAMADDR = (u16)(ADDR_SCB1
                                  + (COLLAPSE_FIRE_SPRITE + c) * 64);
            for (rr = 0; rr < FIRE_ROWS; rr++) {
                *REG_VRAMRW = pend_tile[c][rr];
                *REG_VRAMRW = (u16)(PAL_FIRE << 8);
            }
        }
        tile_dirty = 0;
    }

    /* SCB2 -> SCB3 -> SCB4 for the columns whose words changed */
    *REG_VRAMMOD = 0x200;
    for (c = 0; c < FIRE_COLS; c++) {
        if (!place_dirty[c])
            continue;
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + COLLAPSE_FIRE_SPRITE + c);
        *REG_VRAMRW = pend_scb2[c];
        *REG_VRAMRW = pend_scb3[c];
        *REG_VRAMRW = pend_scb4[c];
        place_dirty[c] = 0;
    }
}
#endif /* SOUND_TEST */
