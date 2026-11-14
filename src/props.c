/* props.c: see props.h. The placement is props_layout()'s (Tasks 11 and
 * 15), generated into build/props_table.h at build time by
 * tests/props_table_gen.c; this file only holds the table's words and, in
 * vblank, writes them.
 *
 * Task 18 split the per-frame update in two. props_prepare compares the
 * table row for this frame's angle with the row of the last prepared angle
 * and marks the slot words, tiles and palette entries that must change,
 * with no VRAM or palette writes. props_commit writes those changes, and
 * the flow loop calls it right after ng_wait_vblank() (before game_frame),
 * so a tree's sprite is never rewritten while the raster is inside that
 * tree. props_show / props_hide still write directly (they run outside play
 * frames).
 *
 * A prop's sprite columns are independent (never a sticky chain): the
 * layout gives each column its own SCB2/SCB3/SCB4, and the columns are
 * hz + 1 px apart. SCB1 rows are the props part's tiles (part base +
 * first + col * rows + r), in the prop's own palette bank; rows past the
 * picture are blanked to transparent tile 0, because vertical shrink does
 * not shorten a sprite (see mis_gfx.c): the hardware still draws
 * height x 16 lines and samples rows top-down (up to row 15 for a box of
 * PROP_MAX_ROWS tiles), so a taller picture left in the same slot would
 * otherwise show below a shrunk one.
 *
 * A picture is at most PROP_MAX_ROWS (5) rows, so no write ever puts a tile
 * in rows 5..15. Those rows are blanked once per slot, on its first write
 * since the props were shown; after that a rewrite is only the picture's
 * rows plus the blank rows below it, up to row 4 — the only rows a picture
 * can ever occupy.
 *
 * Both pools (the back one before the dome, the front one after the broken
 * overlays) are handled the same way. Task P2's Option 1 keeps the memo as
 * the last prepared angle: its table row is in ROM, so prepare compares the
 * two rows directly and copies nothing. A prop that changes pool leaves its
 * old pool slot behind: if no other prop took it, its SCB3 is zeroed here,
 * so nothing stale draws.
 *
 * SCB1 is rewritten only when a slot's (prop, LOD, column) changed: the
 * tile numbers depend on nothing else, so a frame that only moves a prop
 * writes no tiles. SCB2/3/4 are written for every slot in use whose
 * placement changed (3 words per slot; the layout follows the camera), and
 * SCB3 0 for a slot that just stopped being used. The latest prepared table
 * row supplies the words.
 *
 * Task 14: a shown prop's palette variant is d = dome_whole && prop_dark[i][da]
 * (dome_whole = dome_is_whole(&rules)). Its bank is prop_pal[i][d], with
 * entries 1 and 13 from prop_shadow[d][y] (y the foot's row, clamped to
 * 0..223). The bank's 16 words are written only when d changes; entries 1
 * and 13 are written when d or the foot's row changes, and on no other
 * frame. So a prop darkens as it passes through the dome's shadow, and
 * goes lit again the moment the dome is no longer drawn whole.
 */
#include <ngdevkit/neogeo.h>
#include "props.h"
#include "props_table.h"     /* Task P2: props_layout() at every angle, in ROM */

#define PROP_BLANK_TILE 0    /* CROM's zero padding: fully transparent */

/* Task P2's Option 1: the memo is the last prepared angle, not a copy of
 * its layout. That row is already in ROM (build/props_table.h), so the
 * prepare compares prop_table_*[last_angle] with prop_table_*[dome_angle]
 * directly and stores no per-slot struct. One dirty array per kind of
 * write (tiles, SCB2/3/4, SCB3 0 for a stopped slot), for each pool; the
 * commit writes from the latest prepared row. */
static u8 tile_back[PROP_BACK_SLOTS];
static u8 tile_front[PROP_FRONT_SLOTS];
static u8 place_back[PROP_BACK_SLOTS];
static u8 place_front[PROP_FRONT_SLOTS];
static u8 stop_back[PROP_BACK_SLOTS];
static u8 stop_front[PROP_FRONT_SLOTS];

/* the pending palette writes: a whole bank when the variant changed, or
 * entries 1/13 when only the foot's row changed. The new variant/row are
 * already in pal_variant/shadow_y, which props_commit reads. */
static u8 pal_full[NPROPS];
static u8 pal_shadow[NPROPS];

/* each prop's last written shadow row (0xff = never, so a show writes it)
 * and its last written palette variant (0 = lit, 1 = in the dome's shadow;
 * props_show writes variant 0 for every bank, so 0 is the starting value) */
static u8 shadow_y[NPROPS];
static u8 pal_variant[NPROPS];

/* slots whose rows 5..15 have already been blanked since the props were
 * shown (the first write is the full column, after that only rows 0..4) */
static u8 cleared_back[PROP_BACK_SLOTS];
static u8 cleared_front[PROP_FRONT_SLOTS];

/* the last prepared dome angle and dome whole/gone state; at the same angle
 * with the same state nothing a prop draws changes (the generated table is
 * a pure function of the angle and the palette variant follows (angle,
 * whole)), so the whole frame is skipped. props_dbg_last_angle is the
 * non-static copy the MAME demo probe reads (like src/demo.c's
 * demo_dbg_*): proof P2 that the demo prepares every frame's angle. */
u8 props_dbg_last_angle;
static u8 last_whole;
static u8 angle_ready;

static const prop_pic_t *pic_of(u8 prop, u8 lod)
{
    if (prop_kind[prop] == 0)
        return &prop_tree_pic[prop_shape[prop]][lod];
    return &prop_rock_pic[prop_shape[prop]][lod];
}

/* write pool slot k (absolute VRAM slot) SCB1: its picture rows in the
 * prop's bank, every row below the picture blanked. Rows
 * 5..PROP_SCB1_ROWS-1 (which no picture ever fills) are blanked on the
 * slot's first write only. */
static void write_tiles(u8 k, u16 slot, const prop_slot_t *s, u8 *cleared)
{
    const prop_pic_t *pic = pic_of(s->prop, s->lod);
    u16 attr = (u16)((PROP_PAL_BANK + s->prop) << 8);
    u8 r, last = cleared[k] ? PROP_MAX_ROWS : PROP_SCB1_ROWS;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB1 + slot * 64);
    for (r = 0; r < last; r++) {
        if (r < pic->rows)
            *REG_VRAMRW = (u16)(PROP_TILE_BASE + s->tile + r);
        else
            *REG_VRAMRW = PROP_BLANK_TILE;
        *REG_VRAMRW = attr;
    }
    cleared[k] = 1;
}

/* one pool's prepare: compare this frame's table row with the row of the
 * last prepared angle and mark the three kinds of write (SCB1, SCB2/3/4,
 * SCB3 0) in the pending arrays. The previous row is in ROM, never copied.
 * The marks only accumulate (only commit_pool clears them): a skipped
 * commit keeps its writes pending, and a second prepare must not drop the
 * first one's — a slot then showed one prop's old SCB1 at another's place.
 * force marks every shown slot on the first frame after a show/hide. */
static void prepare_pool(const prop_slot_t *cur, const prop_slot_t *prev,
                         u8 *tile, u8 *place, u8 *stop, u8 count, u8 force)
{
    u8 k;

    for (k = 0; k < count; k++) {
        if (cur[k].shown) {
            if (force || !prev[k].shown || prev[k].prop != cur[k].prop
                || prev[k].lod != cur[k].lod || prev[k].col != cur[k].col) {
                tile[k] = 1;
                stop[k] = 0;
            }
            if (force || !prev[k].shown || prev[k].scb2 != cur[k].scb2
                || prev[k].scb3 != cur[k].scb3
                || prev[k].scb4 != cur[k].scb4) {
                place[k] = 1;
                stop[k] = 0;
            }
        } else if (!force && prev[k].shown) {
            stop[k] = 1;
            tile[k] = 0;
            place[k] = 0;
        }
    }
}

/* one pool's commit: SCB1 for the slots whose picture changed, then the
 * old per-changed-slot SCB2/3/4 write (three words at one address for each
 * slot whose placement changed) and SCB3 0 for the slots that stopped.
 * The latest prepared table row supplies the words. The dirty arrays are
 * cleared so a later commit cannot repeat them. */
static void commit_pool(const prop_slot_t *cur, u8 *tile, u8 *place,
                        u8 *stop, u8 *cleared, u16 base, u8 count)
{
    u8 k;

    for (k = 0; k < count; k++) {
        if (tile[k])
            write_tiles(k, (u16)(base + k), &cur[k], cleared);
        tile[k] = 0;
    }

    *REG_VRAMMOD = 0x200;
    for (k = 0; k < count; k++) {
        if (!place[k])
            continue;
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + base + k);
        *REG_VRAMRW = cur[k].scb2;
        *REG_VRAMRW = cur[k].scb3;
        *REG_VRAMRW = cur[k].scb4;
        place[k] = 0;
    }

    *REG_VRAMMOD = 1;
    for (k = 0; k < count; k++) {
        if (!stop[k])
            continue;
        *REG_VRAMADDR = (u16)(ADDR_SCB3 + base + k);
        *REG_VRAMRW = 0;
        stop[k] = 0;
    }
}

/* prepare the palette writes: each shown prop's variant and foot row, with
 * the same memo rules the old props_frame used. */
static void prepare_palette(u8 dome_angle, u8 dome_whole)
{
    u8 i;

    for (i = 0; i < NPROPS; i++) {
        s16 y;
        u8 d;

        /* the marks accumulate like the pools' (commit_palette clears
         * them): a skipped commit's bank or rows stay pending */
        if (!prop_se[i][dome_angle])
            continue;
        d = (u8)(dome_whole && prop_dark[i][dome_angle]);
        y = prop_y[i][dome_angle];
        if (y < 0)
            y = 0;
        else if (y > 223)
            y = 223;
        if (d != pal_variant[i]) {
            pal_full[i] = 1;
            pal_variant[i] = d;
            shadow_y[i] = (u8)y;
        } else if (shadow_y[i] != (u8)y) {
            pal_shadow[i] = 1;
            shadow_y[i] = (u8)y;
        }
    }
}

/* write the prepared palette changes: a whole bank then entries 1/13 for a
 * variant change, entries 1/13 only for a foot-row change. */
static void commit_palette(void)
{
    u8 i, k;

    for (i = 0; i < NPROPS; i++) {
        if (pal_full[i]) {
            for (k = 0; k < 16; k++)
                MMAP_PALBANK1[(PROP_PAL_BANK + i) * 16 + k]
                    = prop_pal[i][pal_variant[i]][k];
            MMAP_PALBANK1[(PROP_PAL_BANK + i) * 16 + 1]
                = prop_shadow[pal_variant[i]][shadow_y[i]][0];
            MMAP_PALBANK1[(PROP_PAL_BANK + i) * 16 + 13]
                = prop_shadow[pal_variant[i]][shadow_y[i]][1];
            pal_full[i] = 0;
        } else if (pal_shadow[i]) {
            MMAP_PALBANK1[(PROP_PAL_BANK + i) * 16 + 1]
                = prop_shadow[pal_variant[i]][shadow_y[i]][0];
            MMAP_PALBANK1[(PROP_PAL_BANK + i) * 16 + 13]
                = prop_shadow[pal_variant[i]][shadow_y[i]][1];
            pal_shadow[i] = 0;
        }
    }
}

void props_show(u8 dome_angle)
{
    u8 i, k;

    for (i = 0; i < NPROPS; i++) {
        for (k = 0; k < 16; k++)
            MMAP_PALBANK1[(PROP_PAL_BANK + i) * 16 + k] = prop_pal[i][0][k];
        pal_variant[i] = 0;          /* every bank starts lit */
        shadow_y[i] = 0xff;          /* the first frame writes entries 1/13 */
        pal_full[i] = 0;
        pal_shadow[i] = 0;
    }
    for (k = 0; k < PROP_BACK_SLOTS; k++) {
        cleared_back[k] = 0;         /* blank rows 5..15 once more */
        tile_back[k] = place_back[k] = stop_back[k] = 0;
    }
    for (k = 0; k < PROP_FRONT_SLOTS; k++) {
        cleared_front[k] = 0;
        tile_front[k] = place_front[k] = stop_front[k] = 0;
    }
    angle_ready = 0;                 /* the first frame must draw */
    props_prepare(dome_angle, 1);    /* shown with the dome whole */
    props_commit();                  /* outside a play frame: write at once */
}

void props_hide(void)
{
    u8 k;

    *REG_VRAMMOD = 1;
    for (k = 0; k < PROP_BACK_SLOTS; k++) {
        *REG_VRAMADDR = (u16)(ADDR_SCB3 + PROP_SPRITE + k);
        *REG_VRAMRW = 0;                        /* height 0: not drawn */
        cleared_back[k] = 0;
        tile_back[k] = place_back[k] = stop_back[k] = 0;
    }
    for (k = 0; k < PROP_FRONT_SLOTS; k++) {
        *REG_VRAMADDR = (u16)(ADDR_SCB3 + PROP_FRONT_SPRITE + k);
        *REG_VRAMRW = 0;
        cleared_front[k] = 0;
        tile_front[k] = place_front[k] = stop_front[k] = 0;
    }
    angle_ready = 0;
    for (k = 0; k < NPROPS; k++) {
        shadow_y[k] = 0xff;
        pal_full[k] = 0;
        pal_shadow[k] = 0;
    }
}

void props_prepare(u8 dome_angle, u8 dome_whole)
{
    const prop_slot_t *prev;
    u8 force;

    /* the same angle with the same whole/gone state draws the same words:
     * nothing to write. The state is part of the key because the palette
     * variant follows (angle, whole), not the angle alone. */
    if (angle_ready && props_dbg_last_angle == dome_angle
        && last_whole == dome_whole)
        return;
    /* only the whole/gone state changed (the collapse's first split, the
     * dome coming back): the slots are the same words, so only the palette
     * prepare below runs. Re-running the layout here landed on the
     * collapse's heaviest frame (review of Task 14: worst span 177 -> see
     * the commit). */
    if (!angle_ready || props_dbg_last_angle != dome_angle) {
        force = (u8)!angle_ready;
        prev = prop_table_back[props_dbg_last_angle];
        prepare_pool(prop_table_back[dome_angle], prev, tile_back,
                     place_back, stop_back, PROP_BACK_COUNT, force);
        prev = prop_table_front[props_dbg_last_angle];
        prepare_pool(prop_table_front[dome_angle], prev, tile_front,
                     place_front, stop_front, PROP_FRONT_COUNT, force);
    }
    angle_ready = 1;
    props_dbg_last_angle = dome_angle;
    last_whole = dome_whole;
    prepare_palette(dome_angle, dome_whole);
}

void props_commit(void)
{
    commit_pool(prop_table_back[props_dbg_last_angle], tile_back, place_back,
                stop_back, cleared_back, PROP_SPRITE, PROP_BACK_COUNT);
    commit_pool(prop_table_front[props_dbg_last_angle], tile_front,
                place_front, stop_front, cleared_front, PROP_FRONT_SPRITE,
                PROP_FRONT_COUNT);
    commit_palette();
}
