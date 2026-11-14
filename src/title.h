/* title.h: the title's nine pages of fix text (M6 Task 5). Pure logic,
 * no hardware: host-built as build/title_sim and held to
 * tests/title_model.py by tests/test_title.py, exactly like hud_rows.
 * Task 6 draws the rows to the fix layer; until then the cart does not
 * call title_rows (the object is built and linked but unused).
 *
 * Page 0 (the dome page; the M8 art pass, after the Vectrex's title):
 *   rows 2..5  the "E-SRG" logo: LOGO_COLS x LOGO_ROWS fix tiles from
 *              LOGO_FIRST (tools/generate_srom.py draws them), row by row,
 *              from col LOGO_COL; the row's characters are the tile codes
 *   row 7  the level name: "EASY", "NORMAL" or "HARD"
 *   row 9  the level's best score, best[level] * 10 (ends at y 63, above
 *          the lifted dome's top, DOME_Y 72)
 *   row 27 under the dome: "B TO CHANGE LEVEL" when title_prompt_b(t),
 *          else "PRESS START" (AES, or MVS with a credit) / "INSERT COIN"
 *          (MVS before a coin)
 *   the other rows blank.
 *   row 28 never written here (the MVS countdown owns it: flow.c, cols
 *   19..20 -- under the prompt, on every page).
 * Pages 1..8: each line a string, centred unless it starts with "|" — a
 * run of "|"-prefixed lines (the "|" is not drawn) is one block whose
 * lines all start at the same column, which centres the longest line
 * (the Vectrex's \x01 column rule). Page lines start on row 6 and step
 * 2 rows per line; an empty string is an empty line that still takes its
 * 2 rows. Rows are 40 chars, NUL-terminated, spaces where empty.
 */
#ifndef TITLE_H
#define TITLE_H
#include <ngdevkit/types.h>

#define TITLE_COLS 40
#define TITLE_ROWS 30

/* the MVS countdown's fix position (HUD-layout Task 3): the two BCD timer
 * digits sit at row 28, cols 19..20 — under the dome, on every page (pages
 * 1..8 end on row 24; title_rows never writes row 28). flow.c draws them;
 * the tests read the constants from this header (tests/layout.py). */
#define TITLE_COUNTDOWN_ROW 28

/* the title logo's fix tiles (tools/generate_srom.py reads these) and the
 * page-0 rows; TITLE_TOP_ROW..TITLE_BOTTOM_ROW is every row a page writes */
#define LOGO_FIRST  130
#define LOGO_COLS   16
#define LOGO_ROWS   4
#define LOGO_COL    12
#define LOGO_ROW    2
#define TITLE_LEVEL_ROW  7
#define TITLE_BEST_ROW   9
#define TITLE_PRESS_ROW  27
#define TITLE_TOP_ROW    2
#define TITLE_BOTTOM_ROW 27
#define TITLE_COUNTDOWN_COL 19

/* page 0's prompt swap: the Vectrex shows "B TO CHANGE LEVEL" while its
 * title_t & 64 (64 of every 128 of its 50 Hz frames). In Vectrex frames
 * that is floor(t * 50 / 59) & 64 for the Neo Geo's t (0..294); without a
 * division, per frame: on from t 76, off from 152, on again from 227. */
static inline u8 title_prompt_b(u16 t)
{
    return (u8)((t >= 76 && t < 152) || t >= 227);
}

/* writes the fix rows 0..29 as 40-char, NUL-terminated strings (spaces
 * where empty; rows 28/29 stay blank). credits: 0 = AES, 1 = MVS before a
 * coin, 2 = MVS after a coin. best is the per-level high-score table
 * (score10: shown x 10). */
void title_rows(u8 page, u8 level, u16 t, const u32 best[3], u8 credits,
                char rows[TITLE_ROWS][TITLE_COLS + 1]);
#endif
