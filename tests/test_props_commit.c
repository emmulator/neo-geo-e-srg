/* test_props_commit: src/props.c's prepare/commit against a VRAM model
 * (tests/host_vram). The attract demo (P1) may skip props_commit on a heavy
 * frame and props_prepare on another; the words staged by a prepare must
 * survive until a commit writes them. After every commit, every slot's
 * words and every shown prop's palette bank must equal what the layout of
 * the LAST prepared (angle, whole) draws:
 *   - a shown slot: SCB1 rows 0..PROP_MAX_ROWS-1 (picture rows, then the
 *     blank tile), SCB2, SCB3, SCB4;
 *   - an unused slot: SCB3 0;
 *   - a shown prop's bank: prop_pal[i][d], entries 1 and 13 from
 *     prop_shadow[d][foot row clamped to 0..223], d = whole && prop_dark.
 * The frames walk the angle in steps of -3..3 (and stay put), toggle the
 * whole state now and then, and skip prepares (1 in 5) and commits (2 in
 * 5) from a fixed LCG, like the demo's budget on heavy frames. */
#include <stdio.h>
#include <stdlib.h>
#include "props.h"

u16 host_vram[0x10000];
u16 host_vram_addr;
u16 host_vram_mod;
u16 host_palbanks[256 * 16];

u16 *host_vram_next(void)
{
    u16 *p = &host_vram[host_vram_addr];
    host_vram_addr = (u16)(host_vram_addr + host_vram_mod);
    return p;
}

static u32 seed = 12345;
static unsigned rnd(unsigned n)
{
    seed = seed * 1103515245u + 12345u;
    return (seed >> 16) % n;
}

static const prop_pic_t *pic_of(u8 prop, u8 lod)
{
    if (prop_kind[prop] == 0)
        return &prop_tree_pic[prop_shape[prop]][lod];
    return &prop_rock_pic[prop_shape[prop]][lod];
}

static unsigned fails;

static void expect(u16 got, u16 want, const char *what, unsigned frame,
                   unsigned a, unsigned b)
{
    if (got == want)
        return;
    if (fails < 10)
        printf("frame %u: %s %u/%u: 0x%04x, want 0x%04x\n",
               frame, what, a, b, (unsigned)got, (unsigned)want);
    fails++;
}

static void check_pool(const prop_slot_t *cur, u16 base, u8 count,
                       unsigned frame)
{
    u8 k, r;

    for (k = 0; k < count; k++) {
        u16 slot = (u16)(base + k);
        if (!cur[k].shown) {
            expect(host_vram[ADDR_SCB3 + slot], 0, "stopped SCB3", frame, slot, 0);
            continue;
        }
        const prop_pic_t *pic = pic_of(cur[k].prop, cur[k].lod);
        u16 attr = (u16)((PROP_PAL_BANK + cur[k].prop) << 8);
        for (r = 0; r < PROP_MAX_ROWS; r++) {
            u16 t = r < pic->rows ? (u16)(PROP_TILE_BASE + cur[k].tile + r) : 0;
            expect(host_vram[ADDR_SCB1 + slot * 64 + 2 * r], t, "SCB1 tile", frame, slot, r);
            expect(host_vram[ADDR_SCB1 + slot * 64 + 2 * r + 1], attr, "SCB1 attr", frame, slot, r);
        }
        expect(host_vram[ADDR_SCB2 + slot], cur[k].scb2, "SCB2", frame, slot, 0);
        expect(host_vram[ADDR_SCB3 + slot], cur[k].scb3, "SCB3", frame, slot, 0);
        expect(host_vram[ADDR_SCB4 + slot], cur[k].scb4, "SCB4", frame, slot, 0);
    }
}

static void check(u8 da, u8 whole, unsigned frame)
{
    prop_slot_t back[PROP_BACK_SLOTS], front[PROP_FRONT_SLOTS];
    u8 i, k;

    props_layout(da, back, front);
    check_pool(back, PROP_SPRITE, PROP_BACK_COUNT, frame);
    check_pool(front, PROP_FRONT_SPRITE, PROP_FRONT_COUNT, frame);
    for (i = 0; i < NPROPS; i++) {
        if (!prop_se[i][da])
            continue;
        u8 d = (u8)(whole && prop_dark[i][da]);
        s16 y = prop_y[i][da];
        y = y < 0 ? 0 : y > 223 ? 223 : y;
        for (k = 0; k < 16; k++) {
            u16 want = prop_pal[i][d][k];
            if (k == 1)
                want = prop_shadow[d][y][0];
            else if (k == 13)
                want = prop_shadow[d][y][1];
            expect(host_palbanks[(PROP_PAL_BANK + i) * 16 + k], want,
                   "palette", frame, i, k);
        }
    }
}

int main(void)
{
    unsigned frame, commits = 0, skipped_commits = 0, staged_over = 0;
    int da = 37;
    u8 whole = 1, prepared_da = 37, prepared_whole = 1, pending = 0;

    props_show((u8)da);
    check((u8)da, 1, 0);
    for (frame = 1; frame <= 20000; frame++) {
        /* the vblank: the commit, unless the budget skips it */
        if (rnd(5) < 2) {
            skipped_commits++;
        } else {
            props_commit();
            commits++;
            check(prepared_da, prepared_whole, frame);
            pending = 0;
        }
        /* the frame's work: move, then the prepare unless skipped */
        da = (da + (int)rnd(7) - 3 + PROP_NDA) % PROP_NDA;
        if (rnd(100) == 0)
            whole = (u8)!whole;
        if (rnd(5) != 0) {
            if (pending)
                staged_over++;
            props_prepare((u8)da, whole);
            prepared_da = (u8)da;
            prepared_whole = whole;
            pending = 1;
        }
    }
    printf("test_props_commit: %u frames, %u commits, %u skipped, "
           "%u prepares over an uncommitted one, %u mismatches\n",
           frame - 1, commits, skipped_commits, staged_over, fails);
    return fails != 0;
}
