/* hud.c: see hud.h. The pure half (hud_rows) is exactly the text the fix
 * layer must show — tests/hud_model.py builds the same rows from the model
 * of the rules and holds the C to them. The hardware half writes the rows
 * hud_rows produces to FIXMAP, redrawing a line only when the value it
 * shows changed since the last frame (the Vectrex's integ_shown /
 * lives_shown / score_shown), and the GAME OVER line only when game_over
 * changed.
 *
 * Every commit reads the rules as they are at the end of the frame and
 * compares against what was shown last frame — the draw-always-decides-on-
 * the-display-frame rule, so a value that changes twice between two draws
 * still ends up shown and nothing is drawn twice for one change.
 *
 * Writing: FIXMAP is column-major (address = FIXMAP + col*32 + row; one
 * write, VRAMMOD 32, steps a column right) and tile = ASCII (S ROM), so a
 * row of text is 40 consecutive writes from (0, row). The three readouts
 * redraw only their cells in the lower right — the integrity's
 * cols 32..37, the lives' cols 32..36, the score's centred 15..25 band
 * (never the whole row: a length change blanks the cells a shorter number
 * leaves behind, and they all sit inside the band) — and the GAME OVER row
 * is rewritten whole, because a new game (1 -> 0) must blank its centred
 * text.
 *
 * The "shown" state lives in .bss, so it starts at 0 no matter what; the
 * `have_*` flags make the first hud_frame draw every line even if the
 * value happens to equal the .bss zero.
 */
#include <string.h>
#include <ngdevkit/neogeo.h>
#include "hud.h"
#include "fix.h"

#define FIX_ENTRY(pal, tile) ((u16)(((u16)(pal) << 12) | (tile)))

/* the icons (S ROM tiles past the ASCII range, generate_srom.py): the
 * lives' little ships and the integrity's little dome. The font's text
 * uses colour index 1 too, so PAL_HUD draws both. */
#define ICON_SHIP 128
#define ICON_DOME 129

static u8 have_integ, have_lives, have_score, have_go;   /* 0: never drawn */
static u8 shown_integ, shown_lives, shown_go;
static u32 shown_score;
u32 hud_dbg_events;                  /* commit count since boot (see hud.h) */
u32 hud_framecnt;                    /* game-session frames (see hud.h) */

/* a whole row of spaces (HUD_COLS + 1 chars), what hud_clear writes: a
 * shared constant beats allocating and filling a 41-byte row per call */
static const char spaces[HUD_COLS + 1] = {
    [0 ... HUD_COLS - 1] = ' ', 0
};

/* digits of v as a string, no leading zeros ("0" for 0) */
static void digits_of(char digits[HUD_SCORE_W + 1], u32 v)
{
    char tmp[HUD_SCORE_W + 1];
    u8 i, n = 0;

    if (v == 0)
        tmp[n++] = '0';
    while (v) {
        tmp[n++] = (char)('0' + (u8)(v % 10));
        v /= 10;
    }
    for (i = 0; i < n; i++)              /* tmp[n-1] is the most significant */
        digits[i] = tmp[n - 1 - i];
    digits[n] = 0;
}

/* a value right-aligned so its last digit is at column `end`, no leading
 * zeros: the columns before it stay spaces. */
static void value(char *row, u32 v, u8 end)
{
    char digits[HUD_SCORE_W + 1];
    u8 i, n = 0;

    if (v == 0)
        digits[n++] = '0';
    while (v) {
        digits[n++] = (char)('0' + (u8)(v % 10));
        v /= 10;
    }
    for (i = 0; i < n; i++)              /* digits[n-1] is the most significant */
        row[(u8)(end - n + 1) + i] = digits[n - 1 - i];
}

void hud_rows(const rules_t *r, const mis_t *m, char rows[HUD_DUMP_ROWS][HUD_COLS + 1])
{
    u8 k, i;

    for (k = 0; k < HUD_DUMP_ROWS; k++) {
        for (i = 0; i < HUD_COLS; i++)
            rows[k][i] = ' ';
        rows[k][HUD_COLS] = 0;
    }
    /* row 24: the integrity — ICON_DOME at col 32, the value right-aligned
     * to end at col 36, '%' at 37 ("100%" fills cols 34..37) */
    rows[HUD_INTEG_ROW][HUD_INTEG_ICON_COL] = (char)ICON_DOME;
    value(rows[HUD_INTEG_ROW], r->integ_pct, HUD_INTEG_END);
    rows[HUD_INTEG_ROW][HUD_PCT_COL] = '%';
    /* row 26: the lives — one ICON_SHIP per life at cols 32, 34, 36 (life
     * 1 at col 32), a space for each lost one. Lives never exceed 3
     * (rules.c: set to 3, only decremented). */
    for (i = 0; i < 3; i++)
        rows[HUD_LIVES_ROW][HUD_LIVES_COL + i * HUD_LIVES_STEP] =
            i < r->lives ? (char)ICON_SHIP : ' ';
    /* row 28: the score with the Vectrex's trailing 0 (a kill scores
     * integrity x 1000, so the score is always whole thousands; "0" when
     * 0), centred: col = (40 - len) / 2, rounded down, the title's rule.
     * The digits are written over the spaces the initial clear left (and
     * the whole row is rewritten on a change, so a shorter number can
     * never leave old cells behind). */
    {
        char digits[HUD_SCORE_W + 1];
        u8 n;

        digits_of(digits, (u32)m->score10 * 10);
        n = (u8)strlen(digits);
        for (i = 0; i < n; i++)
            rows[HUD_SCORE_ROW][(u8)((HUD_COLS - n) / 2) + i] = digits[i];
    }
    /* row 7: GAME OVER, centred, only while the game is over */
    if (r->game_over)
        for (i = 0; i < 9; i++)
            rows[HUD_GAMEOVER_ROW][(u8)((HUD_COLS - 9) / 2) + i] = "GAME OVER"[i];
}

/* the per-row builders hud_frame uses: each fills row `row` with the
 * spaces + the changed cells, exactly as hud_rows would (they must never
 * drift — hud_rows IS the model the boot test holds the C to, so the same
 * little pieces build both). Building only the row(s) whose value changed
 * keeps a score-only frame at the old cost (one 41-byte row + a short
 * write) instead of filling all 30 rows for it. */
static void fill_blank(char *line)
{
    u8 i;

    for (i = 0; i < HUD_COLS; i++)
        line[i] = ' ';
    line[HUD_COLS] = 0;
}

static void build_integ_row(char *line, const rules_t *r)
{
    fill_blank(line);
    line[HUD_INTEG_ICON_COL] = (char)ICON_DOME;
    value(line, r->integ_pct, HUD_INTEG_END);
    line[HUD_PCT_COL] = '%';
}

static void build_lives_row(char *line, const rules_t *r)
{
    u8 i;

    fill_blank(line);
    for (i = 0; i < 3; i++)
        line[HUD_LIVES_COL + i * HUD_LIVES_STEP] =
            i < r->lives ? (char)ICON_SHIP : ' ';
}

static void build_score_row(char *line, const mis_t *m)
{
    char digits[HUD_SCORE_W + 1];
    u8 i, n;

    fill_blank(line);
    digits_of(digits, (u32)m->score10 * 10);
    n = (u8)strlen(digits);
    for (i = 0; i < n; i++)
        line[(u8)((HUD_COLS - n) / 2) + i] = digits[i];
}

static void build_go_row(char *line, const rules_t *r)
{
    u8 i;

    fill_blank(line);
    if (r->game_over)
        for (i = 0; i < 9; i++)
            line[(u8)((HUD_COLS - 9) / 2) + i] = "GAME OVER"[i];
}
/* write a whole 40-tile row from (0, row) */
static void write_row(u8 row, const char *line)
{
    u8 i;

    *REG_VRAMADDR = (u16)(ADDR_FIXMAP + row);        /* col 0 of the row */
    *REG_VRAMMOD = 32;
    for (i = 0; i < HUD_COLS; i++)
        *REG_VRAMRW = FIX_ENTRY(PAL_HUD, (u8)line[i]);
    *REG_VRAMMOD = 1;
}

/* write the columns col0 .. col0+len-1 of one row (the readouts' cells in
 * the lower right; the score's write band HUD_SCORE_COL0 .. +HUD_SCORE_W,
 * which covers every position the centred number can take — a length
 * change both draws the new digits and blanks the cells a shorter number
 * leaves behind, all inside the band) */
static void write_span(u8 row, const char *line, u8 col0, u8 len)
{
    u8 i;

    *REG_VRAMADDR = (u16)(ADDR_FIXMAP + ((u16)col0 << 5) + row);
    *REG_VRAMMOD = 32;
    for (i = 0; i < len; i++)
        *REG_VRAMRW = FIX_ENTRY(PAL_HUD, (u8)line[col0 + i]);
    *REG_VRAMMOD = 1;
}

/* the fix palette the S ROM's text, icons and title logo are drawn for
 * (tools/generate_srom.py) */
#include "fix_pal.h"

/* set the HUD text palette (PAL_HUD bank: the font's lit gradient, its
 * shadow and the logo's blues). The title draws its rows
 * with this palette but must NOT draw the HUD's rows (the task's "the HUD
 * rows are not drawn" on the title), so the boot path provisions the
 * palette alone and the Start path needs no rows of its own any more
 * (there are no constant HUD rows): hud_init is kept so the call site in
 * flow.c's game_begin stays honest. */
void hud_palette_init(void)
{
    u8 i;

    for (i = 1; i < 16; i++)
        MMAP_PALBANK1[PAL_HUD * 16 + i] = fix_pal[i];
}

void hud_init(void)
{
    hud_palette_init();
}

/* blank every fix row and reset the HUD's shown state and the game-session
 * frame counter, so the next hud_frame redraws everything and the session's
 * first game frame is numbered 1. Called once at a Start from the title.
 * Blank only the HUD's span (fix rows 0..29, one 40-tile row each): the
 * title only ever writes rows 4..24 (and the MVS countdown on row 9), so
 * the span covers its rows too — a full 40x32 fix_clear would waste 1280
 * FIXMAP words on the very frame (game_begin's first) that the frame mark
 * measures as the heaviest. */
void hud_clear(void)
{
    u8 row;

    for (row = 0; row < HUD_DUMP_ROWS; row++)
        write_row(row, spaces);
    have_integ = have_lives = have_score = have_go = 0;
    shown_integ = shown_lives = shown_go = 0;
    shown_score = 0;
    hud_framecnt = 0;
}

void hud_frame(const rules_t *r, const mis_t *m)
{
    char line[HUD_COLS + 1];

    hud_framecnt++;
    /* draw only what changed (the Vectrex's integ_shown / lives_shown /
     * score_shown). Each changed line is built from the same pieces as
     * hud_rows (fill_blank + the row's cells), written to FIXMAP, and
     * counted in hud_dbg_events. A steady mid-game frame costs nothing. */
    /* the integrity % */
    if (!have_integ || shown_integ != r->integ_pct) {
        have_integ = 1;
        shown_integ = r->integ_pct;
        build_integ_row(line, r);
        write_span(HUD_INTEG_ROW, line, HUD_INTEG_ICON_COL,
                   (u8)(HUD_PCT_COL - HUD_INTEG_ICON_COL + 1));
        hud_dbg_events++;
    }
    /* the lives */
    if (!have_lives || shown_lives != r->lives) {
        have_lives = 1;
        shown_lives = r->lives;
        build_lives_row(line, r);
        write_span(HUD_LIVES_ROW, line, HUD_LIVES_COL,
                   (u8)(3 * HUD_LIVES_STEP));
        hud_dbg_events++;
    }
    /* the score (score10 x 10, the trailing 0 on screen): write the band
     * the centred number can occupy (cols 15..25, HUD_SCORE_COL0 .. +10),
     * not the whole row — a length change both blanks the cells a shorter
     * number leaves behind (they are in the band) and draws the new
     * digits. */
    if (!have_score || shown_score != (u32)m->score10 * 10) {
        have_score = 1;
        shown_score = (u32)m->score10 * 10;
        build_score_row(line, m);
        write_span(HUD_SCORE_ROW, line, HUD_SCORE_COL0, (u8)(HUD_SCORE_W + 1));
        hud_dbg_events++;
    }
    /* GAME OVER: shown whole row, blanked on a new game (1 -> 0) */
    if (!have_go || (u8)(r->game_over != 0) != shown_go) {
        have_go = 1;
        shown_go = (u8)(r->game_over != 0);
        build_go_row(line, r);
        write_row(HUD_GAMEOVER_ROW, line);
        hud_dbg_events++;
    }
}
