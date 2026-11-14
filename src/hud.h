/* hud.h: the in-game HUD and GAME OVER on the fix layer (HUD-layout Task 2).
 *
 * Layout (fix layer, 40 cols x 32 rows of 8x8 tiles; fix row r is drawn at
 * screen y 8*r - 16, so row 2 is the top line and row 29 the bottom one):
 * the screen is arranged like the Vectrex's — the score centred under the
 * dome, the integrity and the lives in the lower right, across from the
 * radar in the lower left, and nothing at the top during play:
 *
 *     row 24:  "  <dome> 100%"   the integrity: ICON_DOME (tile 129) at
 *                                col 32, the value right-aligned so its
 *                                last digit is at col 36, '%' at col 37
 *                                ("100%" fills cols 34..37, "5%" cols
 *                                36..37)
 *     row 26:  "  <ship><ship><ship>"   the lives: one ICON_SHIP (tile
 *                                128) per life at cols 32, 34 and 36 (life
 *                                1 at col 32), a space for each lost one
 *     row 28:  "      13380     "   the score, centred: the number
 *                                (score10 x 10, no leading zeros, "0" at
 *                                the start) at col (40 - len) / 2, rounded
 *                                down, the title's rule. No label; when
 *                                the score's length changes the row is
 *                                cleared first so a shorter number leaves
 *                                nothing behind.
 *     row 7:   "   GAME OVER   "  centred, only while r->game_over (above
 *                                the dome: screen y 40..47)
 *
 * Rows 0..23 (except row 7's GAME OVER) hold only spaces during play.
 * Every line is redrawn only when its value changes (the Vectrex's
 * integ_shown / lives_shown / score_shown), and a new game (A at GAME
 * OVER, seen as game_over 1 -> 0) forces the GAME OVER row (it must
 * blank). The icons are S ROM tiles past the ASCII range (generate_srom.py,
 * already committed): 128 ICON_SHIP, 129 ICON_DOME; the font's text uses
 * colour index 1 too, so PAL_HUD draws both.
 *
 * The text a state should show is hud_rows (pure, no hardware): 30 rows of
 * 40 chars covering fix rows 0..29 (what the boot test decodes and checks).
 * tests/hud_model.py builds the same rows from the model of the rules and
 * holds the C to them; the MAME boot test compares FIXMAP with them.
 *
 * Palette bank: PAL_HUD = 7 (free; 0 text, 1 dome, 2 ship, 3 missile,
 * 4 bullet, 5 explosion, 6 cracks).
 */
#ifndef HUD_H
#define HUD_H
#include <ngdevkit/types.h>
#include "rules.h"

#define PAL_HUD 7

#define HUD_GAMEOVER_ROW 7
#define HUD_INTEG_ROW    24          /* fix rows, 0-based (FIXMAP row = y/8) */
#define HUD_LIVES_ROW    26
#define HUD_SCORE_ROW    28
#define HUD_DUMP_ROWS    30          /* rows 0..29, what the boot test checks */

#define HUD_ICON_ROW     24          /* the icons' row offset inside the */
#define HUD_INTEG_ICON_COL 32        /* integrity: ICON_DOME at col 32, the */
#define HUD_INTEG_END    36          /* value's last digit at col 36, '%' */
#define HUD_PCT_COL      37          /* at 37 */
#define HUD_LIVES_COL    32          /* the lives: ICON_SHIP at cols 32, */
#define HUD_LIVES_STEP   2           /* 34, 36 (life 1 at col 32), a space */
                                    /* for each lost one */
#define HUD_SCORE_W      10          /* the score's column width */
#define HUD_SCORE_COL0   15          /* the score's write band: the centred
                                      * number (len 1..8, capped at
                                      * 99999990) sits inside cols 15..24,
                                      * so a change writes 15..25 (11 cells
                                      * — one past the longest end) and never
                                      * the whole row: the per-change cost
                                      * stays under the old 10-col band's. */
#define HUD_SCORE_MAX_DISPLAY 99999990       /* score10 x 10, capped */

#define HUD_COLS 40

/* the pure half (host-tested): the 30 rows of text the rules' state must
 * show. rows[r] is a HUD_COLS + 1 char line (NUL-terminated). */
void hud_rows(const rules_t *r, const mis_t *m, char rows[HUD_DUMP_ROWS][HUD_COLS + 1]);

/* the hardware half */
void hud_palette_init(void);       /* the PAL_HUD text palette only, for the
                                    * title's rows (which draw no HUD rows) */
void hud_init(void);                /* the palette only now: there are no
                                    * constant HUD rows any more (the task
                                    * removed the labels, "E-SRG" and the
                                    * help line), so hud_init has nothing
                                    * to draw and exists to keep the call
                                    * sites honest */
void hud_clear(void);               /* blank every fix row in the HUD's span
                                    * (fix rows 0..29 — the title only ever
                                    * writes rows 4..24 and the MVS countdown
                                    * row 9, so blanking the span covers the
                                    * title's rows too) + reset the HUD's
                                    * shown state and the game-session frame
                                    * counter. Called once on a Start from
                                    * the title, so the next hud_frame
                                    * redraws everything and the session's
                                    * first game frame is 1. Under
                                    * fix_clear (all 32 rows) this was the
                                    * heaviest frame of the Start (1280
                                    * FIXMAP words); the span keeps it to
                                    * 1200 and never exceeds the title's own
                                    * rows. */
void hud_frame(const rules_t *r, const mis_t *m);  /* redraw what changed */

/* how many line-commits hud_frame has made since boot (one per drawn
 * change of integrity / lives / score / game over; the first frame draws
 * all four). A debug export: the MAME probe compares it with the model's
 * own count to prove the HUD redraws only when a value changes. */
extern u32 hud_dbg_events;

/* the number of frames of THIS GAME SESSION (incremented by hud_frame once
 * per game frame): 0 on the title, 1 on the first game frame after Start,
 * kept counting through an A-restart, and reset (by hud_clear) on the next
 * Start. A debug export: the MAME probe records it with each input
 * read-back so tests/check_hud.py can replay the model on exactly the
 * frames the game ran — the probe has no other measure of "game session
 * frame". */
extern u32 hud_framecnt;
#endif
