/* dome.c: E-SRG's dome as 11 chained sprite columns. The dome is never
 * shrunk, so the columns can be a sticky chain (each one 16 px right of the
 * last) at full size. Showing another view only rewrites the columns' SCB1
 * tile lists. On a dome death (M4 Task 4) the collapse splits the chain:
 * each column gets its own Y and X, shakes harder and harder, then flies
 * apart (burst) and falls (fall) while the palette fades (dim), and past
 * COLLAPSE_GONE the columns are hidden until the respawn's new_dome shows
 * the dome whole again (dome_show with the fresh view). A game-ending dome
 * death (M4-fixes Task 4) never respawns: the rules leave dome_dead and
 * the full broken list set through the GAME OVER, so the drawing must keep
 * the columns hidden (and the overlays hidden) for the whole GAME OVER —
 * the game_over gate below turns the collapse's "gone" state into "stays
 * gone" (dome_draw_gone). */
#include <ngdevkit/neogeo.h>
#include "dome.h"
#include "dome_map.h"

static const u16 dome_pal[16] =
#include "assets/dome.pal"
;

/* the dome's current frame is a "gone" frame: draw nothing. This is the
 * drawing-only half of Task 4's fix (the rules do not change): the rules
 * run the collapse over dead_t && dome_dead, ending in the "gone" frames
 * (collapse_frac >= COLLAPSE_GONE) that hide the columns until the
 * respawn's new_dome. A game-ending dome death has no respawn — rules_end
 * set game_over instead (lives 0), leaving dome_dead set and the broken
 * list full, so the collapse countdown's gone frames come and go and the
 * whole branch would otherwise redraw the dome with every broken cell
 * drawn. Under GAME OVER, gone means GONE: the collapsed columns stay
 * hidden and the overlays are hidden until A starts a new game. The caveat
 * is deliberately narrow: a NON-dome death's GAME OVER has dome_dead 0 and
 * draws the dome whole with its real broken tiles (today's look). */
int dome_draw_gone(const rules_t *r)
{
    if (!r->game_over)
        return 0;
    return r->dome_dead ? 1 : 0;
}

/* ---- the collapse's per-column state (M4 Task 4) ----
 * mode: 0 = whole (the sticky chain, as dome_init set it), 1 = the columns
 * are split (the collapse is drawing them), 2 = hidden (the collapse's
 * gone frames). The collapse splits the chain once (each column gets its
 * own SCB3 Y and SCB4 X — the same "each column its own X" rule the
 * missiles use, because a sticky chain advances a fixed 16 px and cannot
 * move its columns apart), and the whole branch re-chains on the way out
 * (the respawn's new_dome redraws the box, but the chain must exist for
 * the sticky driver to draw it). */
#define DOME_MODE_WHOLE  0
#define DOME_MODE_SPLIT  1
#define DOME_MODE_HIDDEN 2

static u8 mode;

/* the Vectrex's jitter: an 8-bit LCG (seed = seed*13+7), its top bits
 * fed to the shake (the low bits of that multiply repeat quickly) */
static u16 jseed = 0x1234;
static s16 jitter(s16 amp)
{
    jseed = (u16)(jseed * 13 + 7);
    return (s16)(((jseed >> 8) & (u16)amp) - amp / 2);
}

/* ---- the palette fade ----
 * packed15, derived from dome_pal exactly as paltool packed it: the dark
 * bit is the channel's 6th bit (the 4-bit nibble is the top); 0x7fff is
 * (31,31,31), not (15,15,15). The Vectrex dims its brightness
 * (DOME_INTENSITY - dim), 0x6f - 49 stays positive, so on the Neo Geo the
 * fade runs the whole fall: dim 0 (the shake, and the first fall frame)
 * is the full palette, and each dim step scales every nonzero channel
 * toward black by (channel * (COLLAPSE_MAX_DIM - dim)) / COLLAPSE_MAX_DIM,
 * so the collapse ends at the black end of the table. Entry 0
 * stays transparent; dim 0 reproduces the full palette exactly (the
 * rebuilt dome's palette is pristine). */
static u16 fade_ramp[COLLAPSE_MAX_DIM + 1][16];

static void fade_table_init(void)
{
    u8 dim, i;

    for (dim = 0; dim <= COLLAPSE_MAX_DIM; dim++) {
        for (i = 0; i < 16; i++) {
            u16 c = dome_pal[i];
            u8 r5 = (u8)(((c >> 8) & 0x0f) * 2 + ((c >> 14) & 1));
            u8 g5 = (u8)(((c >> 4) & 0x0f) * 2 + ((c >> 13) & 1));
            u8 b5 = (u8)((c & 0x0f) * 2 + ((c >> 12) & 1));

            r5 = (u8)((r5 * (COLLAPSE_MAX_DIM - dim)) / COLLAPSE_MAX_DIM);
            g5 = (u8)((g5 * (COLLAPSE_MAX_DIM - dim)) / COLLAPSE_MAX_DIM);
            b5 = (u8)((b5 * (COLLAPSE_MAX_DIM - dim)) / COLLAPSE_MAX_DIM);
            fade_ramp[dim][i] = (u16)((((r5 & 1) << 14) | ((r5 >> 1) << 8))
                                      | (((g5 & 1) << 13) | ((g5 >> 1) << 4))
                                      | (((b5 & 1) << 12) | (b5 >> 1))
                                      | ((((r5 >> 1) | (g5 >> 1) | (b5 >> 1)) == 0) ? 0x8000 : 0));
        }
        fade_ramp[dim][0] = 0x8000;              /* entry 0 stays transparent */
    }
}

void dome_init(void)
{
    u8 i, c;

    fade_table_init();
    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_DOME * 16 + i] = dome_pal[i];
    MMAP_PALBANK1[PAL_DOME * 16] = 0x8000;      /* entry 0: transparent */

    *REG_VRAMMOD = 0x200;                        /* SCB2 -> SCB3 -> SCB4 */
    for (c = 0; c < DOME_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB2 + DOME_SPRITE + c;
        *REG_VRAMRW = 0x0fff;                    /* full size */
        if (c == 0) {
            *REG_VRAMRW = (u16)(((496 - DOME_Y) << 7) | DOME_ROWS);
            *REG_VRAMRW = (u16)(DOME_X << 7);
        } else {
            *REG_VRAMRW = 1 << 6;                /* sticky: follows column c-1 */
            /* the sticky column's own SCB4 is read by nothing (it inherits
             * the driver's X), but write its box X anyway: the VRAM then
             * holds the whole box deterministically, so the boot-test can
             * prove "the rebuilt dome's VRAM matches a fresh dome's" word
             * for word (an un-written SCB4 would carry whatever the BIOS
             * init left in VRAM — a value that differs per boot and after
             * the collapse's split). */
            *REG_VRAMRW = (u16)((DOME_X + (s16)c * 16) << 7);
        }
    }
    mode = DOME_MODE_WHOLE;
    dome_show(0);
}

void dome_show(u8 view)
{
    u8 c, r;

    *REG_VRAMMOD = 1;
    for (c = 0; c < DOME_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB1 + (DOME_SPRITE + c) * 64;
        for (r = 0; r < DOME_ROWS; r++) {
            *REG_VRAMRW = dome_tile[view][c][r];
            *REG_VRAMRW = (u16)(PAL_DOME << 8);
        }
    }
}

/* re-establish the sticky chain (the whole box): SCB2 full size, slot 21's
 * SCB3 at DOME_Y with DOME_ROWS, and EVERY column's SCB4 at its box X
 * (DOME_X + c*16 — the split gave each column its own SCB4, and a sticky
 * column that follows the driver inherits its X from the slot before it, so
 * the chain's own SCB4 words are read by nothing and would otherwise keep
 * the split's Xs — the "rebuilt dome's VRAM matches a fresh dome's" check
 * must see the box Xs again). SCB1 is written by dome_show. */
static void dome_rechain(void)
{
    u8 c;

    *REG_VRAMMOD = 0x200;
    for (c = 0; c < DOME_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB2 + DOME_SPRITE + c;
        *REG_VRAMRW = 0x0fff;                    /* full size */
        if (c == 0) {
            *REG_VRAMRW = (u16)(((496 - DOME_Y) << 7) | DOME_ROWS);
            *REG_VRAMRW = (u16)(DOME_X << 7);
        } else {
            *REG_VRAMRW = 1 << 6;                /* sticky: follows column c-1 */
            *REG_VRAMRW = (u16)((DOME_X + (s16)c * 16) << 7);
        }
    }
}

/* split the chain: every column gets its own SCB3 (Y) and SCB4 (X), at its
 * place in the whole box, so the collapse can move them independently. Each
 * column c sits at DOME_X + c*16, the middle of the burst's spread. */
static void dome_split(void)
{
    u8 c;

    *REG_VRAMMOD = 0x200;
    for (c = 0; c < DOME_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB2 + DOME_SPRITE + c;
        *REG_VRAMRW = 0x0fff;                    /* SCB2: full size */
        *REG_VRAMRW = (u16)(((496 - DOME_Y) << 7) | DOME_ROWS);   /* SCB3 */
        *REG_VRAMRW = (u16)((DOME_X + (s16)c * 16) << 7);         /* SCB4 */
    }
    mode = DOME_MODE_SPLIT;
}

/* draw the split columns for this collapse frame: column c sits at
 *   x = DOME_X + c*16 + (c - 5) * (burst / 2)   (spread apart, both sides)
 *   y = DOME_Y + fall - shake/2 ± jitter(shake)  (the shake, per column)
 * and the whole thing sinks `fall` px (the Vectrex's lift move: down).
 * The dome is never shrunk, so SCB2 stays full size and the columns keep
 * their full 16x16 tiles; the spread and fall are pure translation. */
static void dome_collapse_draw(const rules_t *r)
{
    u8 c, i;
    s16 shake = (s16)collapse_shake(r);
    s16 burst = (s16)collapse_burst(r);
    s16 yoff = (s16)(DOME_Y + (s16)collapse_fall(r) - shake / 2);

    *REG_VRAMMOD = 0x200;
    for (c = 0; c < DOME_COLS; c++) {
        s16 x = (s16)(DOME_X + (s16)c * 16
                      + (s16)(c - (DOME_COLS - 1) / 2) * (burst / COLLAPSE_SPREAD));
        s16 y = (s16)(yoff + jitter(shake));

        *REG_VRAMADDR = ADDR_SCB3 + DOME_SPRITE + c;
        *REG_VRAMRW = (u16)(((496 - y) << 7) | DOME_ROWS);
        *REG_VRAMRW = (u16)(x << 7);
    }
    /* the palette fade to this frame's dim */
    for (i = 1; i < 16; i++)
        MMAP_PALBANK1[PAL_DOME * 16 + i] = fade_ramp[collapse_dim(r)][i];
}

/* hide the columns (SCB3 height 0): the "gone" frames, after the collapse */
static void dome_hide(void)
{
    u8 c;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = ADDR_SCB3 + DOME_SPRITE;
    for (c = 0; c < DOME_COLS; c++)
        *REG_VRAMRW = 0;
    mode = DOME_MODE_HIDDEN;
}

/* M6 Task 6: the title hides the dome on pages 1..8 with this — the very
 * same hide the collapse's gone frames use. dome_collapse with the rules
 * at their entry zero (state 1 whole) then re-chains the box on the next
 * page-0 frame: mode is HIDDEN, so it runs dome_rechain + dome_show.
 * Mutation (b) — zeroing only the driver's SCB3 (the followers keep their
 * sticky bit) — was seen to fail the wrapped-page-0 checks and was
 * reverted (the driver's height 0 and the 67-vs-15186 pixels). */
void dome_title_hide(void)
{
    dome_hide();
}

/* restore the full palette (the collapse faded it; the rebuilt dome and
 * the collapse's shake frames must show the pristine colours) */
static void dome_pal_restore(void)
{
    u8 i;

    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_DOME * 16 + i] = dome_pal[i];
    MMAP_PALBANK1[PAL_DOME * 16] = 0x8000;
}

void dome_collapse(const rules_t *r, u8 view)
{
    if (dome_draw_gone(r)) {
        /* a game-ending dome death: the dome never comes back on its own.
         * The collapse already hid the columns (dome_hide set mode HIDDEN
         * and SCB3 0) before game_over turned on; keep them hidden (the
         * whole branch must not re-chain and redraw them), and restore the
         * palette (the collapse's fade left it dark — the palette is not
         * dome-coloured any more, and the next frames draw nothing from
         * it). */
        dome_pal_restore();
        return;
    }
    if (collapse_state(r) != 2) {
        /* whole, or the collapse is over */
        if (collapse_frac(r) >= COLLAPSE_GONE) {
            dome_hide();
            return;
        }
        if (mode != DOME_MODE_WHOLE) {
            dome_pal_restore();              /* the collapse faded it */
            dome_rechain();                  /* restore the chain (also from hidden) */
            dome_show(view);                 /* and the view's tiles */
            mode = DOME_MODE_WHOLE;
        }
        return;
    }

    /* the collapse is running */
    if (mode == DOME_MODE_WHOLE)
        dome_split();                        /* split the chain once */
    else if (mode == DOME_MODE_HIDDEN) {     /* (cannot happen: gone is state 1) */
        dome_split();
    }
    dome_collapse_draw(r);
}
