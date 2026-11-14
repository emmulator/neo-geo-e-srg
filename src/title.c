/* title.c: the title's eleven pages of fix text, as a pure function of
 * (page, level, t, board, credits) — see title.h. No hardware: this is
 * exactly the text the fix layer must show, and tests/test_title.py
 * holds it to tests/title_model.py (the task's reference, built from the
 * Vectrex's title_screen / text_lines in vectrex-e-srg 1.1.0 and the
 * approved high-score mockup).
 *
 * Pages 1..3 are the high-score boards (high-score boards Task B3): row 6
 * "HIGH SCORES", row 8 the page's level name (EASY/NORMAL/HARD), rows
 * 11..19 step 2 the five entries. An entry is the rank, two spaces, the
 * three initials, then the score right-aligned in a 6-wide field; the
 * whole line is centred with the same (40 - len) / 2 rule as today's best
 * line ("1ST  SRG   50000"). The star/heart initials are stored as codes
 * 1/2; they are copied through so the thick title font (Task B4) draws
 * them from its own glyphs.
 *
 * The "|" block rule: a run of lines starting with "|" (the "|" is not
 * drawn) is one block whose lines all start at the same column — the
 * column that centres the block's longest line, (40 - maxlen) / 2
 * rounded down. Pages 4..10 start their lines on row 6 and step 2 rows per
 * line; an empty string is an empty line that still takes its 2 rows.
 *
 * 32-bit maths: title_rows is only called when its visible inputs change
 * (Task 6), never per frame, so the score's * 10 and digit loops may use
 * u32 (u32 arithmetic compiles to no 32-bit library calls on the 68000).
 * The per-frame code (flow.c) must stay 16-bit; this is not per-frame.
 *
 * High-score boards Task B4: every text row's span includes the cell after
 * its last character (text_span_len). That cell is a space whose left
 * neighbour is the last character, and flow.c draws it with the thick
 * font's space tile for that neighbour, holding the glyph's outline spill.
 * The cap row repeats the line and the span, so it gets the same spill.
 */
#include <string.h>
#include "title.h"


/* the levels' names, as page 0 shows the chosen one (the same array the
 * model keeps) */
static const char *const level_name[3] = { "EASY", "NORMAL", "HARD" };

/* the board entries' ranks, in rank order */
static const char rank_name[TITLE_BOARD_ROWS][4] = {
    "1ST", "2ND", "3RD", "4TH", "5TH"
};

/* pages 4..10, each entry one line (the task's page tables). A line
 * starting with '|' is a block member: consecutive '|' lines form one
 * block (see above). Pages 1..3 are built by board_page_rows, so their
 * slots in this table are unused. */
static const char *const page_controls[] = {
    "CONTROLS", "",
    "|STICK  MOVE",
    "|A      FIRE",
    "|B      JUMP, LEVEL",
    "|C      NEXT PAGE",
    "|START  PLAY", 0
};

static const char *const page_play[] = {
    "DEFEND THE DOME", "",
    "SHOOT MISSILES",
    "BEFORE THEY HIT", "",
    "HITS CRACK TILES", "",
    "JUMP OVER CRACKS", "",
    "AT 0% DOME COLLAPSES", 0
};

static const char *const page_levels[] = {
    "LEVELS", "",
    "A TILE CRACKS WITH",
    "N CRACKED NEIGHBORS", "",
    "|EASY   N = 5",
    "|NORMAL N = 4",
    "|HARD   N = 3", 0
};

static const char *const page_collapse[] = {
    "LEVELS", "",
    "DOME COLLAPSE COSTS", "",
    "|EASY   NOTHING",
    "|NORMAL ONE LIFE",
    "|HARD   THE GAME", "",
    "MISSILES ARE SLOWER ON EASY", 0
};

static const char *const page_score[] = {
    "RADAR", "",
    "BLINKS AND BEEPS",
    "WHEN LOCKED ON", "",
    "SCORE", "",
    "1000 POINTS TIMES",
    "DOME INTEGRITY",
    "PER MISSILE", 0
};

static const char *const page_credits[] = {
    "CREDITS", "",
    "GAME DESIGN:",
    "JOHN EMMER", "",
    "IMPLEMENTATION:",
    "CLAUDE OPUS 5.5",
    "AND DEEPSEEK V4.1 FLASH 1017", "",
    "(C) 2026", 0
};

static const char *const page_built[] = {
    "BUILT WITH", "",
    "NGDEVKIT: DAMIEN CIABRINI",
    "GCC 15.3",
    "MAME", 0
};

static const char *const *const pages[TITLE_PAGES] = {
    0, 0, 0, 0,
    page_controls, page_play, page_levels, page_collapse,
    page_score, page_credits, page_built
};

static u16 page_len(const char *s)
{
    u16 n = 0;

    while (s[n])
        n++;
    return n;
}

/* copy text centred in one row: col = (40 - len) / 2, rounded down */
static void centre(char *row, const char *s, u16 len)
{
    u16 i, col = (u16)((TITLE_COLS - len) / 2);

    for (i = 0; i < len; i++)
        row[col + i] = s[i];
}

/* high-score boards Task B4: the fix span of a title text line, including
 * the cell after its last character. That cell is a space whose left
 * neighbour is the line's last character, and it holds that glyph's
 * outline spill into the neighbouring cell (tools/generate_srom.py's
 * title2_cell). The cap row repeats the text row and the same span, so it
 * gets the same spill cell. Empty lines have no characters and no cell
 * after them (flow.c writes nothing there). */
static u8 text_span_len(u16 col, u16 len)
{
    if (len == 0)
        return 0;
    return (u8)(len + ((col + len < TITLE_COLS) ? 1 : 0));
}

/* the decimal digits of v, most significant first; returns the count.
 * Runs only on input change (Task 6), so u32 is fine. */
static u8 score_digits(u32 v, char *out)
{
    char rev[10];
    u8 n = 0, i;

    if (v == 0)
        rev[n++] = '0';
    while (v) {
        rev[n++] = (char)('0' + (u8)(v % 10));
        v /= 10;
    }
    for (i = 0; i < n; i++)          /* rev[n-1] is the most significant */
        out[i] = rev[n - 1 - i];
    return n;
}

/* a best value as its own centred line: score10 x 10, no leading zeros
 * ("0" if 0). Returns the digit count (the P1 span's length). */
static u8 centre_best(char *row, u32 v)
{
    char digits[11];
    u8 n = score_digits(v, digits), i;
    u16 col = (u16)((TITLE_COLS - n) / 2);

    for (i = 0; i < n; i++)
        row[col + i] = digits[i];
    return n;
}

/* one board entry line: rank, two spaces, the three initials, two spaces,
 * then the score right-aligned in TITLE_BOARD_SCORE_WIDTH columns. The
 * star/heart codes (1/2) pass through; other control bytes become spaces
 * so the row stays a valid C string. Returns the line's length. */
static u8 board_entry_line(char *line, u8 e, const board_entry_t *entry)
{
    char digits[11];
    u8 n = score_digits((u32)entry->score10 * 10, digits);
    u8 len = 0, i;

    line[len++] = rank_name[e][0];
    line[len++] = rank_name[e][1];
    line[len++] = rank_name[e][2];
    line[len++] = ' ';
    line[len++] = ' ';
    for (i = 0; i < BOARD_NINIT; i++) {
        u8 b = entry->init[i];

        line[len++] = (char)((b == 1 || b == 2
                              || (b >= 32 && b <= 126)) ? b : ' ');
    }
    line[len++] = ' ';
    line[len++] = ' ';
    for (i = n; i < TITLE_BOARD_SCORE_WIDTH; i++)
        line[len++] = ' ';
    for (i = 0; i < n; i++)
        line[len++] = digits[i];
    line[len] = 0;
    return len;
}

/* pages 1..3: the boards (high-score boards Task B3). Row 6 "HIGH SCORES",
 * row 8 the level's name, rows 11..19 step 2 the five entries; copy_caps
 * repeats each line into the row below (7, 9, 12, 14, 16, 18, 20). */
static void board_page_rows(u8 page, const board_t *board,
                            char rows[TITLE_ROWS][TITLE_COLS + 1],
                            u8 text[TITLE_ROWS],
                            u8 sp_col[TITLE_ROWS], u8 sp_len[TITLE_ROWS])
{
    u8 level = (u8)(page - 1);
    u8 e;
    u16 n;
    u16 row = TITLE_BOARD_FIRST_ROW;

    n = page_len("HIGH SCORES");
    centre(rows[TITLE_BOARD_HEADER_ROW], "HIGH SCORES", n);
    text[TITLE_BOARD_HEADER_ROW] = 1;
    sp_col[TITLE_BOARD_HEADER_ROW] = (u8)((TITLE_COLS - n) / 2);
    sp_len[TITLE_BOARD_HEADER_ROW] = text_span_len(sp_col[TITLE_BOARD_HEADER_ROW], n);

    n = page_len(level_name[level]);
    centre(rows[TITLE_BOARD_LEVEL_ROW], level_name[level], n);
    text[TITLE_BOARD_LEVEL_ROW] = 1;
    sp_col[TITLE_BOARD_LEVEL_ROW] = (u8)((TITLE_COLS - n) / 2);
    sp_len[TITLE_BOARD_LEVEL_ROW] = text_span_len(sp_col[TITLE_BOARD_LEVEL_ROW], n);

    for (e = 0; e < TITLE_BOARD_ROWS; e++, row += TITLE_BOARD_STEP) {
        char line[32];
        u8 len = board_entry_line(line, e, &board->entry[level][e]);

        centre(rows[row], line, len);
        text[row] = 1;
        sp_col[row] = (u8)((TITLE_COLS - len) / 2);
        sp_len[row] = text_span_len(sp_col[row], len);
    }
}

/* one page's lines, from row 6 stepping 2 rows per line (pages 4..10).
 * Every line marks its row in text[]; title_rows copies each such row into
 * its cap row. sp_col/sp_len carry the columns the row's text occupies
 * (P1's span writer): 0 where the line is blank. */
static void page_rows(u8 page, char rows[TITLE_ROWS][TITLE_COLS + 1],
                      u8 text[TITLE_ROWS],
                      u8 sp_col[TITLE_ROWS], u8 sp_len[TITLE_ROWS])
{
    const char *const *l;
    u16 row = 6;                     /* pages start their lines on row 6 */
    u16 i;

    for (l = pages[page]; *l; l++) {
        if ((*l)[0] == '|') {
            /* one block: find its span, centre the longest line */
            const char *const *m = l;
            u16 maxlen = 0, col;

            for (; *m && (*m)[0] == '|'; m++) {
                u16 n = page_len(*m + 1);
                if (n > maxlen)
                    maxlen = n;
            }
            col = (u16)((TITLE_COLS - maxlen) / 2);
            for (; l != m; l++, row += 2) {
                u16 n = page_len(*l + 1);
                for (i = 0; i < n; i++)
                    rows[row][col + i] = (*l)[1 + i];
                text[row] = 1;
                sp_col[row] = (u8)col;
                sp_len[row] = text_span_len(sp_col[row], n);
            }
            l--;                     /* the for's l++ lands on the next line */
        } else if (**l == 0) {
            text[row] = 1;           /* an empty line still takes its 2 rows */
            sp_col[row] = 0;
            sp_len[row] = 0;
            row += 2;
        } else {
            u16 n = page_len(*l);
            centre(rows[row], *l, n);
            text[row] = 1;
            sp_col[row] = (u8)((TITLE_COLS - n) / 2);
            sp_len[row] = text_span_len(sp_col[row], n);
            row += 2;
        }
    }
}

/* attract Task A1: every text line's row r is copied into its cap row
 * r + 1. The cap tile's row 0 is the glyph's bottom outline row, so the
 * row's characters repeat the text (the same spaces included); flow.c
 * draws that row with the thick font's cap tiles (TITLE2_CAP_BASE, high-
 * score boards Task B4). The cap row's span is the text row's span, so it
 * gets the same cell after the line's last character. */
static void copy_caps(char rows[TITLE_ROWS][TITLE_COLS + 1],
                      const u8 text[TITLE_ROWS],
                      u8 sp_col[TITLE_ROWS], u8 sp_len[TITLE_ROWS])
{
    u8 i;

    for (i = 0; i < TITLE_ROWS - 1; i++)
        if (text[i]) {
            memcpy(rows[i + 1], rows[i], TITLE_COLS + 1);
            sp_col[i + 1] = sp_col[i];
            sp_len[i + 1] = sp_len[i];
        }
}

/* P1: the rows plus the column span each row's text occupies, so flow.c
 * can write only the cells a page (and the page it replaces) can show.
 * title_rows keeps the old signature for the host model's test. */
void title_rows_spans(u8 page, u8 level, u16 t, const board_t *board,
                      u8 credits, char rows[TITLE_ROWS][TITLE_COLS + 1],
                      u8 sp_col[TITLE_ROWS], u8 sp_len[TITLE_ROWS])
{
    u8 text[TITLE_ROWS];
    u8 i;

    memset(text, 0, sizeof text);
    for (i = 0; i < TITLE_ROWS; i++) {
        memset(rows[i], ' ', TITLE_COLS);
        rows[i][TITLE_COLS] = 0;
        sp_col[i] = 0;
        sp_len[i] = 0;
    }
    if (page == 0) {
        const char *prompt;

        for (i = 0; i < LOGO_ROWS; i++) {
            u8 c;

            for (c = 0; c < LOGO_COLS; c++)
                rows[LOGO_ROW + i][LOGO_COL + c] = (char)(LOGO_FIRST + i * LOGO_COLS + c);
            sp_col[LOGO_ROW + i] = LOGO_COL;
            sp_len[LOGO_ROW + i] = LOGO_COLS;
        }
        {
            u16 n = page_len(level_name[level]);
            centre(rows[TITLE_LEVEL_ROW], level_name[level], n);
            text[TITLE_LEVEL_ROW] = 1;
            sp_col[TITLE_LEVEL_ROW] = (u8)((TITLE_COLS - n) / 2);
            sp_len[TITLE_LEVEL_ROW] = text_span_len(sp_col[TITLE_LEVEL_ROW], n);
        }
        {
            u8 n = centre_best(rows[TITLE_BEST_ROW],
                               (u32)board->entry[level][0].score10 * 10);
            text[TITLE_BEST_ROW] = 1;
            sp_col[TITLE_BEST_ROW] = (u8)((TITLE_COLS - n) / 2);
            sp_len[TITLE_BEST_ROW] = text_span_len(sp_col[TITLE_BEST_ROW], n);
        }
        {
            u16 n = page_len("V" E_SRG_VERSION);
            centre(rows[TITLE_VER_ROW], "V" E_SRG_VERSION, n);
            text[TITLE_VER_ROW] = 1;
            sp_col[TITLE_VER_ROW] = (u8)((TITLE_COLS - n) / 2);
            sp_len[TITLE_VER_ROW] = text_span_len(sp_col[TITLE_VER_ROW], n);
        }
        prompt = title_prompt_b(t) ? "B TO CHANGE LEVEL"
                          : (credits == 1 ? "INSERT COIN" : "PRESS START");
        {
            u16 n = page_len(prompt);
            centre(rows[TITLE_PRESS_ROW], prompt, n);
            text[TITLE_PRESS_ROW] = 1;
            sp_col[TITLE_PRESS_ROW] = (u8)((TITLE_COLS - n) / 2);
            sp_len[TITLE_PRESS_ROW] = text_span_len(sp_col[TITLE_PRESS_ROW], n);
        }
    } else if (page <= 3) {
        board_page_rows(page, board, rows, text, sp_col, sp_len);
    } else {
        page_rows(page, rows, text, sp_col, sp_len);
    }
    copy_caps(rows, text, sp_col, sp_len);  /* row 28 is never written */
}

void title_rows(u8 page, u8 level, u16 t, const board_t *board, u8 credits,
                char rows[TITLE_ROWS][TITLE_COLS + 1])
{
    u8 col[TITLE_ROWS], len[TITLE_ROWS];

    title_rows_spans(page, level, t, board, credits, rows, col, len);
}
