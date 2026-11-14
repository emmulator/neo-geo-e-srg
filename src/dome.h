/* dome.h: the pre-rendered dome (11 sprite columns of 8 tiles), and its
 * collapse (M4 Task 4). The dome is never shrunk, so the columns are a
 * sticky chain (each one 16 px right of the last); showing another view
 * only rewrites the columns' SCB1 tile lists. On a dome death the collapse
 * shakes the columns harder and harder, then flies them apart and falls
 * while the palette fades; the dome then is gone until the respawn's
 * new_dome, which shows it whole again. The effect values come from the
 * rules (rules.h: collapse_state / collapse_frac / collapse_shake /
 * collapse_burst / collapse_fall / collapse_dim), the drawing lives here.
 *
 * Constraint record (the plan's style): during the collapse (state 2) the
 * dome's eleven columns are split from their sticky chain: each gets its
 * own SCB3 (Y) and SCB4 (X), so they can shake, spread and fall
 * independently — the same "each column its own X" rule the missiles use
 * (a sticky chain advances a fixed 16 px and cannot move its columns
 * apart). The dome is never shrunk, so SCB2 stays 0x0fff and the columns
 * keep their full 16x16 tiles; the spread and fall are pure translation
 * in X and Y. Only the collapse writes these registers; the fixed (state
 * 1) dome keeps its chain.
 */
#ifndef DOME_H
#define DOME_H
#include <ngdevkit/types.h>
#include "rules.h"

#define PAL_DOME    1        /* palette bank */
#include "slots.h"           /* DOME_SPRITE: the one slot map (M5 Task 1) */
#define DOME_X      72       /* top-left of the 176x128 box, screen pixels */
#define DOME_Y      72       /* the box's top; the dome's lowest lit pixel
                              * is DOME_Y + 126 (y 198 today) */

/* the collapse's per-column spread (px) away from the middle, so the
 * columns fly apart on both sides of the box while bursting: column c
 * drifts (c - (DOME_COLS-1)/2) * burst / 2. (The Vectrex's runs fly apart
 * from their anchor as the position scale under them goes wrong.) */
#define COLLAPSE_SPREAD 2

void dome_init(void);
void dome_show(u8 view);     /* 0 .. DOME_VIEWS-1 */

/* once per frame, after the rules; draws the dome for the frame:
 * state 1 (whole, or the collapse over) shows view; state 2 (collapsing)
 * splits the columns apart per the collapse_* values and fades the
 * palette. The gone frames (state 1, collapse_frac >= COLLAPSE_GONE)
 * hide the columns (SCB3 height 0), which is what "gone until the new
 * dome" means.
 *
 * The drawing-only half of M4-fixes Task 4's fix (the rules do not
 * change): is this frame a "the dome stays gone" frame — a GAME OVER that
 * a DOME death ended. The rules' collapse countdown ends in the gone
 * frames that hide the columns until the respawn, but a game-ending dome
 * death has no respawn: rules_end set game_over (lives 0) leaving
 * dome_dead and the broken list set, so without this gate the whole
 * branch would redraw the dome with every broken cell drawn through the
 * GAME OVER. A non-dome death's GAME OVER (dome_dead 0) keeps drawing the
 * dome with its broken tiles — the "today's look" case. */
int dome_draw_gone(const rules_t *r);    /* 1: keep the dome hidden this frame */

void dome_collapse(const rules_t *r, u8 view);

/* hide the whole dome, its own way (M6 Task 6): SCB3 height 0 on EVERY
 * column and the mode HIDDEN, so the next page-0 frame's dome_collapse
 * re-chains the whole box (it calls dome_rechain when the mode isn't
 * WHOLE) — never zero only the driver's SCB3, which would leave the
 * followers' sticky bit drawing a half dome (Task 1's lesson). */
void dome_title_hide(void);
#endif
