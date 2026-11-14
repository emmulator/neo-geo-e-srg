/* ground.h: the grass (dome-scenery Tasks 5 and 19) — one static block of
 * GROUND_COLS x GROUND_ROWS 16x16 tiles from tools/render_ripple.py, its
 * top at GROUND_Y, in 11 ripple palette banks. The art is the
 * orchestrator's (the generator is never edited for the picture or palette
 * here); this module places it, switches the shadow on and off, and rotates
 * each bank's palette as the camera turns.
 *
 * The block is the LOWEST sprite range (slots.h: GROUND_SPRITE .. +20), so
 * every other sprite draws over it. It is a sticky chain of full-size
 * columns (the ground is never shrunk): column c sits at x = 16c, the
 * driver's SCB3 carries GROUND_Y and GROUND_ROWS, the followers inherit
 * both. ground_show writes the whole block once when a game begins.
 *
 * Task 19: the grass's texture slides as the dome turns, by palette rotation
 * alone — no sprite moves and no tile is rewritten. Tile (col, row)'s SCB1
 * attribute is (RIPPLE_PAL_BANK + ground_bank[col][row]) << 8, so it uses
 * one of the 11 banks 44..54. Each bank's palette is
 * ground_ripple_pal[bank][gone][ground_ripple_rot[bank][dome_angle]], a
 * phase-shifted brightness ramp of the tile row's two shades. ground_prepare
 * stages only the banks whose (rotation, gone) changed — 12 words each — and
 * ground_commit writes them right after the next vblank (as the props after
 * Task 18); a frame whose angle did not change writes nothing. The ripple
 * therefore shows the previous frame's angle, the same one-frame lag the
 * props have. At most 11 x 12 = 132 words are written in one commit (the
 * whole/gone change); bank 8's separate 16-word switch is ground_frame's.
 *
 * Bank 8 (PAL_GROUND) stays the whole/gone marker even though no tile uses
 * it any more: ground_frame still switches it between ground_pal and
 * ground_pal_noshadow exactly as before, because scripts/props_probe.lua,
 * tests/check_props.py and scripts/ground_probe.lua read the dome's
 * whole/gone state from those 16 words and expect it at the frame's end
 * (no one-frame lag). The switch is the dome's own answer (src/dome.c's
 * dome_is_whole), so the ground can never disagree with the dome. The
 * ripple's banks, which do lag, take their whole/gone variant from the
 * same dome_is_whole answer one frame earlier.
 *
 * On the title the block is hidden (SCB3 height 0 on every column:
 * ground_hide at each flow entry), so the title stays black.
 */
#ifndef GROUND_H
#define GROUND_H
#include <ngdevkit/types.h>
#include "rules.h"            /* ground_frame's rules_t */
#include "slots.h"            /* GROUND_SPRITE, GROUND_COUNT */
#include "ground_map.h"       /* GROUND_Y/COLS/ROWS + the palettes (build) */

/* the whole/gone marker bank, kept for the probes/checkers that read it */
#define PAL_GROUND 8

/* the tiles' first ripple bank: the props own 22..43, the collapse will take
 * 55..57 later, so 44..54 are the ripple's */
#define RIPPLE_PAL_BANK 44

/* once when a game begins: the block's SCB1 tiles in their ripple banks,
 * its SCB2 full size, the sticky chain, every ripple bank at `dome_angle`'s
 * rotation (dome whole), and bank 8 holding ground_pal. */
void ground_show(u8 dome_angle);

/* hide every column (SCB3 height 0) — the title, and a fresh entry before
 * any game has begun. */
void ground_hide(void);

/* once per frame in play, after the rules/dome draw: the bank-8 whole/gone
 * switch, written directly only when the state changes (the old Task 5
 * behaviour; the probes/checkers read the current state here). */
void ground_frame(const rules_t *r);

/* once per play frame where ground_frame runs: decide for each ripple bank
 * whether its (rotation, gone) changed since the last commit and stage its
 * 12 words (entries 1..12) in RAM. It writes no palette and no VRAM. */
void ground_prepare(u8 dome_angle, u8 dome_whole);

/* right after ng_wait_vblank on every play frame: write what ground_prepare
 * staged (only the words that changed). */
void ground_commit(void);
#endif
