/* title.h: the title's eleven pages of fix text (M6 Task 5; high-score
 * boards Task B3). Pure logic, no hardware: host-built as build/title_sim
 * and held to tests/title_model.py by tests/test_title.py, exactly like
 * hud_rows. Task 6 draws the rows to the fix layer.
 *
 * Page 0 (the dome page; the M8 art pass, after the Vectrex's title):
 *   rows 2..5  the "E-SRG" logo: LOGO_COLS x LOGO_ROWS fix tiles from
 *              LOGO_FIRST (tools/generate_srom.py draws them), row by row,
 *              from col LOGO_COL; the row's characters are the tile codes
 *   row 7  the level name: "EASY", "NORMAL" or "HARD"
 *   row 8  the level row's caps: the same characters, drawn by the cap
 *          tiles (their row 0 is the glyphs' bottom outline row)
 *   row 9  the level's board's top entry, top.score10 * 10 (ends at y 63,
 *          above the lifted dome's top, DOME_Y 72)
 *   row 10 the best row's caps (the same characters)
 *   row 21 above the console: "B TO CHANGE LEVEL" when title_prompt_b(t),
 *          else "PRESS START" (AES, or MVS with a credit) / "INSERT COIN"
 *          (MVS before a coin)
 *   row 22 the prompt's caps (the same characters)
 *   the other rows blank.
 *   row 28 never written here (the MVS countdown owns it: flow.c, cols
 *   19..20, on every page).
 * Pages 1..3: the high-score boards, one per difficulty (EASY, NORMAL,
 * HARD):
 *   row 6  "HIGH SCORES"
 *   row 8  the level's name
 *   rows 11..19 step 2  the five entries: the rank ("1ST".."5TH"), two
 *          spaces, the three initials, then the score right-aligned in a
 *          6-wide field, the whole entry centred like the mockup's board
 *          line ("1ST  SRG   50000"; the score's field is right-aligned,
 *          the line is centred with the same column rule as today's best
 *          line). The star/heart initials are stored as their codes (1/2)
 *          and print as those codes; B4's title font draws them, until then
 *          the old title font's tiles 1/2 are blank.
 *   every line's cap row repeats its characters (rows 7, 9 and 12, 14,
 *   16, 18, 20); row 10 is blank.
 * Pages 4..10: each line a string, centred unless it starts with "|" — a
 * run of "|"-prefixed lines (the "|" is not drawn) is one block whose
 * lines all start at the same column, which centres the longest line
 * (the Vectrex's \x01 column rule). Page lines start on row 6 and step
 * 2 rows per line; an empty string is an empty line that still takes its
 * 2 rows. Every line's row r gets its caps in row r + 1 (the blank row
 * between lines), with the same characters: the cap tile draws the glyph's
 * bottom outline row. Rows are 40 chars, NUL-terminated, spaces where
 * empty.
 */
#ifndef TITLE_H
#define TITLE_H
#include <ngdevkit/types.h>
#include "board.h"

#define TITLE_COLS 40
#define TITLE_ROWS 30
#define TITLE_PAGES 11

/* the MVS countdown's fix position (HUD-layout Task 3): the two BCD timer
 * digits sit at row 28, cols 19..20 — under the dome, on every page (the
 * title never writes row 28). flow.c draws them; the tests read the
 * constants from this header (tests/layout.py). */
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
#define TITLE_VER_ROW    24
/* the release, shown on page 0 as "V" + this on row TITLE_VER_ROW (its caps
 * on the row below), in the thick text font, centred */
#define E_SRG_VERSION "2.0.0"
#define TITLE_PRESS_ROW  21
#define TITLE_TOP_ROW    2
#define TITLE_BOTTOM_ROW 25
#define TITLE_COUNTDOWN_COL 19

/* high-score boards Task B3: the three board pages' layout and the score
 * field's right-aligned width (the mockup's padStart(6); a longer score
 * keeps all its digits). Pages 1..3 are EASY, NORMAL and HARD. */
#define TITLE_BOARD_HEADER_ROW 6
#define TITLE_BOARD_LEVEL_ROW  8
#define TITLE_BOARD_FIRST_ROW  11
#define TITLE_BOARD_STEP       2
#define TITLE_BOARD_ROWS       5
#define TITLE_BOARD_SCORE_WIDTH 6

/* attract Task A1: the OLD 1-px-outline title glyph blocks. TITLE_FONT_BASE
 * + c is the FONT57 glyph c (cols 1..5, rows 1..7, filled with the 1..4
 * amber gradient, colour 5 on its 8-neighbourhood outline); TITLE_CAP_BASE
 * + c is its cap tile (row 0 = the outline's bottom row, rows 1..7 blank).
 * tools/generate_srom.py reads these for the old blocks and leaves them
 * byte-identical (the host tests still check them), but the cart's title no
 * longer draws them: high-score boards Task B4 moved the row writer to the
 * thick-outline font from tile 512 (build/title_font.h, TITLE2_ROW_BASE /
 * TITLE2_CAP_BASE). The HUD's glyphs stay at tiles 0..127 and the logo at
 * 130..193. */
#define TITLE_FONT_BASE  200
#define TITLE_CAP_BASE   328

/* page 0's prompt swap: the Vectrex shows "B TO CHANGE LEVEL" while its
 * title_t & 64 (64 of every 128 of its 50 Hz frames). In Vectrex frames
 * that is floor(t * 50 / 59) & 64 for the Neo Geo's t; without a
 * division, per frame: on from t 76, off from 152, on again from 227. */
static inline u8 title_prompt_b(u16 t)
{
    return (u8)((t >= 76 && t < 152) || t >= 227);
}

/* writes the fix rows 0..29 as 40-char, NUL-terminated strings (spaces
 * where empty; rows 28/29 stay blank). Every text line's row r is copied
 * into its cap row r + 1 (the same characters; flow.c draws it with the
 * cap tiles of the thick font, TITLE2_CAP_BASE). credits: 0 = AES, 1 =
 * MVS before a coin, 2 = MVS after a coin. board is the five-entry per-level high-score board: page 0 shows
 * its top entry for the level, pages 1..3 show EASY/NORMAL/HARD's five
 * entries (score10 x 10, high-score boards Task B3). */
void title_rows(u8 page, u8 level, u16 t, const board_t *board, u8 credits,
                char rows[TITLE_ROWS][TITLE_COLS + 1]);
#endif
