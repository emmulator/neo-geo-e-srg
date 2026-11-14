/* dome.h: the pre-rendered dome (8 sprite columns of 6 tiles, the
 * dome-scenery plan's 2/3 size), and its collapse (M4 Task 4, the redo's
 * Task C1). The dome is never shrunk, so the columns are a sticky chain
 * (each one 16 px right of the last); showing another view only rewrites the
 * columns' SCB1 tile lists. On a dome death the collapse shakes the columns
 * harder and harder (f 0..COLLAPSE_SHAKE-1); from COLLAPSE_SHAKE on the
 * dome's own 8 columns show the ruin from RUIN_VIEWS (48) views, one per
 * scene step a % RUIN_VIEWS, until the respawn's new_dome shows
 * the dome whole again. A game-ending dome death keeps the ruin for the
 * whole GAME OVER (dome_draw_gone), until A starts a new game. The effect
 * values come from the rules (rules.h: collapse_state / collapse_frac /
 * collapse_shake / collapse_burst / collapse_fall / collapse_dim), the
 * drawing lives here; burst/fall/dim are no longer drawn (Tasks C2-C4 use
 * the rest of the generated collapse tables).
 *
 * Constraint record (the plan's style): during the shake the dome's eight
 * columns are split from their sticky chain: each gets its own SCB3 (Y) and
 * SCB4 (X), so they can shake independently — the same "each column its own
 * X" rule the missiles use (a sticky chain advances a fixed 16 px and cannot
 * move its columns apart). The dome is never shrunk, so SCB2 stays 0x0fff
 * and the columns keep their full 16x16 tiles. The ruin is again a sticky
 * chain at the box, exactly the way dome_rechain builds it. Only the
 * collapse writes these registers; the fixed (state 1) dome keeps its chain.
 */
#ifndef DOME_H
#define DOME_H
#include <ngdevkit/types.h>
#include "rules.h"
#include "band.h"            /* BAND_TILE_BASE + BAND_TILES: the collapse follows */

#define PAL_DOME    1        /* palette bank */
#define PAL_RUIN    55       /* the ruin's bank (props 22..43, ripple 44..54) */
#include "slots.h"           /* DOME_SPRITE: the one slot map (M5 Task 1) */
#define DOME_X      96       /* top-left of the 128x96 box, screen pixels:
                              * centred on the 320-wide screen */
#define DOME_Y      104      /* the box's top; the dome's lowest lit pixel
                              * is DOME_Y + 94 (y 198: just above the score
                              * row, which starts at y 208) */

/* the collapse part's first tile in the assembled C ROM: the Makefile emits
 * the collapse LAST, after the band, so it starts at BAND_TILE_BASE +
 * BAND_TILES. The generated header's ruin_tile numbers are relative to this
 * part (0 is the part's own blank tile). */
#define COLLAPSE_TILE_BASE (BAND_TILE_BASE + BAND_TILES)

/* the collapse's per-column spread (px) away from the middle, so the
 * columns fly apart on both sides of the box while bursting: column c
 * drifts (c - (DOME_COLS-1)/2) * burst / 2. (The Vectrex's runs fly apart
 * from their anchor as the position scale under them goes wrong.)
 * COLLAPSE_SPREAD is the divisor: it stays 2, and collapse_burst's g * 3 ->
 * g * 2 alone scales the spread by 2/3 (Dome-scenery Task 2's review: a
 * divisor of 1 had made the spread 4/3 of the full dome's). */
#define COLLAPSE_SPREAD 2

void dome_init(void);
void dome_show(u8 view);     /* 0 .. DOME_VIEWS-1 (ignored while the ruin holds) */

/* once per frame, after the rules; draws the dome for the frame:
 * state 1 (whole, or the collapse over) shows view; the collapse's shake
 * (f 0..COLLAPSE_SHAKE-1) splits the columns and shakes them; from
 * COLLAPSE_SHAKE on (and under a dome death's GAME OVER) the dome's own 8
 * columns show the ruin picture, re-chained at the box, until the respawn
 * (or A) draws the view whole again. */
int dome_draw_gone(const rules_t *r);    /* 1: the dome-death GAME OVER holds the ruin */

/* the drawing's own "the dome is drawn whole this frame" answer, the one
 * the ground's shadow switch reads (dome-scenery Task 5): 1 while
 * dome_collapse draws the whole chain (the rules' state 1 and the
 * collapse's frac below COLLAPSE_GONE, and not a game-ending dome death,
 * dome_draw_gone), 0 from the collapse's first split on, through the ruin,
 * and under a game-ending dome death's GAME OVER. It is derived exactly
 * like dome_collapse's own branch order, so the grass's shadow and the dome
 * can never disagree (tests/test_go_dome.c holds the pair). */
int dome_is_whole(const rules_t *r);

void dome_collapse(const rules_t *r, u8 view);

/* hide the whole dome, its own way (M6 Task 6): SCB3 height 0 on EVERY
 * column and the mode HIDDEN, so the next page-0 frame's dome_collapse
 * re-chains the whole box (it calls dome_rechain when the mode isn't
 * WHOLE) — never zero only the driver's SCB3, which would leave the
 * followers' sticky bit drawing a half dome (Task 1's lesson). The title
 * still uses this; a collapse no longer does. */
void dome_title_hide(void);
#endif
