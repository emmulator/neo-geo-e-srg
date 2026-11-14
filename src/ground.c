/* ground.c: see ground.h. The block is a sticky chain of GROUND_COLS
 * full-size 16-px columns at y GROUND_Y; the tiles come from the ground
 * part of the C ROM, right after the radar's. Task 19: every tile row uses
 * one of the 11 ripple palette banks (44..54), and the per-frame work is
 * only palette rotation: ground_prepare stages the banks whose (rotation,
 * gone) changed into RAM, ground_commit writes them in the next vblank.
 * Bank 8 stays the whole/gone marker, switched directly by ground_frame
 * (see ground.h).
 */
#include <ngdevkit/neogeo.h>
#include "ground.h"
#include "dome.h"             /* dome_is_whole: the shadow switch reads the
                               * drawing's own whole/gone answer */
#include "radar_map.h"        /* RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES: the
                               * ground part's first C ROM tile */

/* the ground part's first tile in the assembled C ROM: the Makefile emits
 * the C ROM parts in CROM1_PARTS order (dome, ship, missiles, broken,
 * radar's frame/sticks/headings, then the ground), so the ground starts
 * exactly where the radar's headings end. The header's tile numbers are
 * relative to this part (tile (col, row) = col * GROUND_ROWS + row); every
 * fetch below adds this base. */
#define GROUND_TILE_BASE (RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES)

/* 1 while bank 8 holds ground_pal (the dome drawn whole), 0 while it holds
 * ground_pal_noshadow. Initialised to 1 in .data: the runtime copies .data
 * on every BIOS entry, so ground_show's palette write is matched by the
 * first game frame's "no change" (the block and its palette are both
 * (re)written at a game start anyway). */
static u8 shadow_on = 1;

/* each ripple bank's staged entries 1..12 and the banks whose (rotation,
 * gone) changed since the last commit; the memo of each bank's last
 * prepared rotation, and the last prepared gone state (1 = dome gone). */
static u16 pend[RIPPLE_BANKS][12];
static u8 dirty[RIPPLE_BANKS];
static u8 last_rot[RIPPLE_BANKS];
static u8 ripple_gone;

void ground_show(u8 dome_angle)
{
    u8 c, r, k, i;

    /* the block's SCB1 columns: GROUND_ROWS tiles each, top to bottom, each
     * row in its own ripple bank */
    *REG_VRAMMOD = 1;
    for (c = 0; c < GROUND_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB1 + (GROUND_SPRITE + c) * 64;
        for (r = 0; r < GROUND_ROWS; r++) {
            *REG_VRAMRW = (u16)(GROUND_TILE_BASE + c * GROUND_ROWS + r);
            *REG_VRAMRW = (u16)((RIPPLE_PAL_BANK + ground_bank[c][r]) << 8);
        }
    }
    /* the sticky chain: the driver's SCB3 at GROUND_Y with GROUND_ROWS
     * tiles tall, every follower inherits Y and height and sits 16 px to
     * the right (so column c is at x = 16c). Full size, never shrunk. */
    *REG_VRAMMOD = 0x200;
    for (c = 0; c < GROUND_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB2 + GROUND_SPRITE + c;
        *REG_VRAMRW = 0x0fff;                    /* full size */
        if (c == 0) {
            *REG_VRAMRW = (u16)(((496 - GROUND_Y) << 7) | GROUND_ROWS);
            *REG_VRAMRW = 0;                     /* x = 0: column 0 */
        } else {
            *REG_VRAMRW = 1 << 6;                /* sticky: follows c-1 */
            *REG_VRAMRW = (u16)((s16)c * 16 << 7);
        }
    }
    /* every ripple bank at the show's angle, the dome whole */
    for (k = 0; k < RIPPLE_BANKS; k++) {
        const u16 *pal = ground_ripple_pal[k][0][ground_ripple_rot[k][dome_angle]];
        for (i = 0; i < 16; i++)
            MMAP_PALBANK1[(RIPPLE_PAL_BANK + k) * 16 + i] = pal[i];
        last_rot[k] = ground_ripple_rot[k][dome_angle];
        dirty[k] = 0;
    }
    ripple_gone = 0;
    /* the whole/gone marker bank */
    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_GROUND * 16 + i] = ground_pal[i];
    shadow_on = 1;
}

void ground_hide(void)
{
    u8 c;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = ADDR_SCB3 + GROUND_SPRITE;
    for (c = 0; c < GROUND_COLS; c++)
        *REG_VRAMRW = 0;                         /* height 0: not drawn */
}

/* the shadow switch (Task 5, unchanged for Task 19): the bank holds
 * ground_pal while the dome is drawn whole and ground_pal_noshadow
 * otherwise (the collapse from its first split on, the gone frames, and a
 * game-ending dome death's GAME OVER — dome_is_whole is the drawing's own
 * answer to that, so the ground can never disagree with the dome). Write
 * the 16 words only when the state changes; a play frame costs one
 * compare. The probes/checkers read this current state, so it is NOT
 * staged into ground_prepare/ground_commit's one-frame lag. */
void ground_frame(const rules_t *r)
{
    const u16 *pal;
    u8 i, whole = (u8)dome_is_whole(r);

    if (whole == shadow_on)
        return;
    shadow_on = whole;
    pal = whole ? ground_pal : ground_pal_noshadow;
    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_GROUND * 16 + i] = pal[i];
}

/* the ripple's prepare (Task 19, as the props after Task 18): stage only
 * the banks whose rotation changed, and all of them when the dome's
 * whole/gone state changed. Nothing here touches the palette or VRAM. */
void ground_prepare(u8 dome_angle, u8 dome_whole)
{
    u8 k, i, rot;
    u8 gone = (u8)(dome_whole ? 0 : 1);
    u8 gone_changed = (u8)(gone != ripple_gone);

    for (k = 0; k < RIPPLE_BANKS; k++) {
        dirty[k] = 0;
        rot = ground_ripple_rot[k][dome_angle];
        if (rot != last_rot[k] || gone_changed) {
            const u16 *pal = ground_ripple_pal[k][gone][rot];
            for (i = 0; i < 12; i++)
                pend[k][i] = pal[i + 1];         /* entries 1..12 */
            dirty[k] = 1;
            last_rot[k] = rot;
        }
    }
    ripple_gone = gone;
}

void ground_commit(void)
{
    u8 k, i;

    for (k = 0; k < RIPPLE_BANKS; k++) {
        if (!dirty[k])
            continue;
        for (i = 0; i < 12; i++)
            MMAP_PALBANK1[(RIPPLE_PAL_BANK + k) * 16 + 1 + i] = pend[k][i];
        dirty[k] = 0;
    }
}
