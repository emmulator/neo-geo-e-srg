/* title.c: the title's nine pages of fix text, as a pure function of
 * (page, level, t, best, credits) — see title.h. No hardware: this is
 * exactly the text the fix layer must show, and tests/test_title.py
 * holds it to tests/title_model.py (the task's reference, built from the
 * Vectrex's title_screen / text_lines in vectrex-e-srg 1.1.0).
 *
 * The "|" block rule: a run of lines starting with "|" (the "|" is not
 * drawn) is one block whose lines all start at the same column — the
 * column that centres the block's longest line, (40 - maxlen) / 2
 * rounded down. Pages other than 0 start their lines on row 6 and step
 * 2 rows per line; an empty string is an empty line that still takes its
 * 2 rows.
 *
 * 32-bit maths: title_rows is only called when its visible inputs change
 * (Task 6), never per frame, so the score's * 10 and digit loops may use
 * u32 (u32 arithmetic compiles to no 32-bit library calls on the 68000).
 * The per-frame code (flow.c) must stay 16-bit; this is not per-frame.
 */
#include <string.h>
#include "title.h"


/* the levels' names, as page 0 shows the chosen one (the same array the
 * model keeps) */
static const char *const level_name[3] = { "EASY", "NORMAL", "HARD" };

/* the pages other than 0, each entry one line (the task's page tables).
 * A line starting with '|' is a block member: consecutive '|' lines form
 * one block (see above). The "BESTk" markers are not text: they draw the
 * k-th level's best score (best[k] x 10) centred on their own line, as
 * the Vectrex's best_draw does on the HIGH SCORES page. */
static const char *const page_best[] = {
    "HIGH SCORES", "",
    "EASY", "BEST0", "",
    "NORMAL", "BEST1", "",
    "HARD", "BEST2", 0
};

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
    "EASY MISSILES ARE SLOWER", 0
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
    "AND DEEPSEEK V4 FLASH", "",
    "(C) 2026", 0
};

static const char *const page_built[] = {
    "BUILT WITH", "",
    "NGDEVKIT: DAMIEN CIABRINI",
    "GCC 15.3",
    "MAME", 0
};

static const char *const *const pages[9] = {
    0, page_best, page_controls, page_play, page_levels, page_collapse,
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

/* a best value as its own centred line: best x 10, no leading zeros
 * ("0" if 0). Runs only on input change (Task 6), so u32 is fine. */
static void centre_best(char *row, u32 v)
{
    char digits[11];
    u8 n = 0, i;

    if (v == 0)
        digits[n++] = '0';
    while (v) {
        digits[n++] = (char)('0' + (u8)(v % 10));
        v /= 10;
    }
    for (i = 0; i < n; i++)          /* digits[n-1] is the most significant */
        row[(TITLE_COLS - n) / 2 + (u8)(n - 1 - i)] = digits[i];
}

/* one page's lines, from row 6 stepping 2 rows per line */
static void page_rows(u8 page, const u32 best[3], char rows[TITLE_ROWS][TITLE_COLS + 1])
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
            }
            l--;                     /* the for's l++ lands on the next line */
        } else if ((*l)[0] == 'B' && (*l)[1] == 'E' && (*l)[2] == 'S'
                   && (*l)[3] == 'T') {
            centre_best(rows[row], (u32)best[(*l)[4] - '0'] * 10);
            row += 2;
        } else if (**l == 0) {
            row += 2;                /* an empty line still takes its 2 rows */
        } else {
            centre(rows[row], *l, page_len(*l));
            row += 2;
        }
    }
}

void title_rows(u8 page, u8 level, u16 t, const u32 best[3], u8 credits,
                char rows[TITLE_ROWS][TITLE_COLS + 1])
{
    u8 i;

    for (i = 0; i < TITLE_ROWS; i++) {
        memset(rows[i], ' ', TITLE_COLS);
        rows[i][TITLE_COLS] = 0;
    }
    if (page == 0) {
        const char *prompt;

        for (i = 0; i < LOGO_ROWS; i++) {
            u8 c;

            for (c = 0; c < LOGO_COLS; c++)
                rows[LOGO_ROW + i][LOGO_COL + c] = (char)(LOGO_FIRST + i * LOGO_COLS + c);
        }
        centre(rows[TITLE_LEVEL_ROW], level_name[level], page_len(level_name[level]));
        centre_best(rows[TITLE_BEST_ROW], (u32)best[level] * 10);
        prompt = title_prompt_b(t) ? "B TO CHANGE LEVEL"
                          : (credits == 1 ? "INSERT COIN" : "PRESS START");
        centre(rows[TITLE_PRESS_ROW], prompt, page_len(prompt));
        return;                      /* row 28 is never written */
    }
    page_rows(page, best, rows);
}
