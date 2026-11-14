/* test_hud.c: the C-side half of the HUD-layout Task 2 proof, updated for
 * the dome-scenery Task 8 move (the integrity on row 26, the lives and the
 * score sharing row 28).
 *
 * 1. hud_rows is a pure function of the rules state and lays the text out
 *    exactly as hud.h says (the integrity's icon + right-aligned percent +
 *    '%' on row 26, the lives' icon per life and the centred score on row
 *    28, the centred GAME OVER, everything else blank) — the same rows
 *    tests/hud_model.py and the boot test compare. The shared row 28 is
 *    proved cell by cell: the lives' cols 32/34/36 never hold a score digit
 *    and the score's cols 15..24 never hold a life's icon, for every score
 *    length 1..8 and every life count 0..3.
 * 2. The palette and the layout constants are as hud.h records (bank 7
 *    free, the readouts clear of the dome), so the fix layer and the
 *    sprites can never fight over palette RAM.
 * 3. run_boot_script: drive the C's rules (rules_begin/ship_frame/
 *    mis_update/rules_end) exactly as main.c does and print hud_rows per
 *    frame; tests/hud_model.py replays the same script against its model.
 *    Used as the boot probe's reference: the probe's frames are matched
 *    to model frames by the deterministic game the script produces.
 *
 * The "row28" mode prints one row 28 for a given (score10, integ, lives,
 * game over) state, so tests/test_hud_model.py can hold the C and the model
 * to the same row for every score length and life count (proof 2).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ship.h"
#include "missiles.h"
#include "rules.h"
#include "hud.h"
#include "fix.h"
#include "fix_pal.h"

/* the stub registers the headers point the game's writes at (never run) */
volatile u16 host_vram_addr, host_vram_rw, host_vram_mod;
volatile u16 host_palbanks[16 * 16];

#define ICON_SHIP 128
#define ICON_DOME 129

static int fails = 0;

static void check(int cond, const char *what)
{
    if (!cond) {
        printf("FAIL %s\n", what);
        fails++;
    }
}

/* hud.h's layout, expressed in the same rows the model uses */
static void test_layout(void)
{
    rules_t r;
    mis_t m;
    char rows[HUD_DUMP_ROWS][HUD_COLS + 1];
    int i;

    rules_reset(&r);
    mis_reset(&m);
    hud_rows(&r, &m, rows);
    /* a fresh game: NORMAL, 3 lives, integ 100, score 0 */
    check((u8)rows[HUD_INTEG_ROW][HUD_INTEG_ICON_COL] == ICON_DOME, "integ icon");
    check(rows[HUD_INTEG_ROW][HUD_INTEG_ICON_COL + 1] == ' ', "icon gap");
    check(0 == strncmp(rows[HUD_INTEG_ROW] + HUD_INTEG_END - 2, "100", 3),
          "integ 100");
    check(rows[HUD_INTEG_ROW][HUD_PCT_COL] == '%', "integ %");
    check(rows[HUD_INTEG_ROW][38] == ' ' && rows[HUD_INTEG_ROW][39] == ' ',
          "integ row tail blank");
    check((u8)rows[HUD_LIVES_ROW][HUD_LIVES_COL] == ICON_SHIP
          && (u8)rows[HUD_LIVES_ROW][HUD_LIVES_COL + 2] == ICON_SHIP
          && (u8)rows[HUD_LIVES_ROW][HUD_LIVES_COL + 4] == ICON_SHIP,
          "lives 3 icons");
    check(rows[HUD_SCORE_ROW][(HUD_COLS - 1) / 2] == '0', "score 0 shows 0");
    check(rows[HUD_GAMEOVER_ROW][HUD_GAMEOVER_COL0 - 1] == ' '
          && rows[HUD_GAMEOVER_ROW][HUD_GAMEOVER_COL0 + HUD_GAMEOVER_LEN - 1] == ' ',
          "no GAME OVER while playing");
    check(rows[HUD_GAMEOVER_CAP_ROW][HUD_GAMEOVER_COL0 - 1] == ' '
          && rows[HUD_GAMEOVER_CAP_ROW][HUD_GAMEOVER_COL0 + HUD_GAMEOVER_LEN - 1] == ' ',
          "no GAME OVER cap while playing");
    /* the top of the screen: rows 2..25 (except GAME OVER's row 7) are
     * spaces during play — every column, not just the edges */
    for (i = 0; i < HUD_GAMEOVER_ROW; i++)
        for (int col = 0; col < HUD_COLS; col++)
            check(rows[i][col] == ' ', "top row blank");
    for (i = HUD_GAMEOVER_ROW + 1; i < HUD_INTEG_ROW; i++)
        for (int col = 0; col < HUD_COLS; col++)
            check(rows[i][col] == ' ', "mid row blank");
    for (i = HUD_SCORE_ROW + 1; i < HUD_DUMP_ROWS; i++)
        for (int col = 0; col < HUD_COLS; col++)
            check(rows[i][col] == ' ', "bottom row blank");

    /* a value change moves only the value cells */
    r.integ_pct = 97;
    r.lives = 2;
    m.score10 = 1338;
    hud_rows(&r, &m, rows);
    check(0 == strncmp(rows[HUD_INTEG_ROW] + HUD_INTEG_END - 1, "97", 2),
          "integ 97");
    check((u8)rows[HUD_LIVES_ROW][HUD_LIVES_COL] == ICON_SHIP
          && (u8)rows[HUD_LIVES_ROW][HUD_LIVES_COL + 2] == ICON_SHIP
          && rows[HUD_LIVES_ROW][HUD_LIVES_COL + 4] == ' ', "lives 2 icons");
    /* 1338 * 10 = 13380, centred at (40 - 5) / 2 = 17 */
    check(0 == strncmp(rows[HUD_SCORE_ROW] + (HUD_COLS - 5) / 2, "13380", 5),
          "score 13380 centred");

    /* a lost life leaves a space, not a stale icon */
    r.lives = 1;
    hud_rows(&r, &m, rows);
    check((u8)rows[HUD_LIVES_ROW][HUD_LIVES_COL] == ICON_SHIP
          && rows[HUD_LIVES_ROW][HUD_LIVES_COL + 2] == ' '
          && rows[HUD_LIVES_ROW][HUD_LIVES_COL + 4] == ' ', "lives 1");

    /* the score cap: 9,999,999 / 10 x 10 = 99,999,990, 8 columns wide,
     * centred at (40 - 8) / 2 = 16 */
    m.score10 = 9999999;
    hud_rows(&r, &m, rows);
    check(0 == strncmp(rows[HUD_SCORE_ROW] + (HUD_COLS - 8) / 2, "99999990", 8),
          "score cap 99999990 centred");

    /* GAME OVER centred on row 7; Task G1's cap row 8 repeats its
     * characters (the thick font's cap tile draws the outline's bottom row) */
    r.game_over = 1;
    hud_rows(&r, &m, rows);
    check(0 == strncmp(rows[HUD_GAMEOVER_ROW] + HUD_GAMEOVER_COL0,
                       "GAME OVER", 9), "GAME OVER centred");
    check(0 == strncmp(rows[HUD_GAMEOVER_CAP_ROW] + HUD_GAMEOVER_COL0,
                       "GAME OVER", 9), "GAME OVER cap centred");
    check(0 == strncmp(rows[HUD_GAMEOVER_CAP_ROW], rows[HUD_GAMEOVER_ROW],
                       HUD_COLS + 1), "GAME OVER cap repeats the text row");
    check(rows[HUD_GAMEOVER_ROW][HUD_GAMEOVER_COL0 + 9] == ' '
          && rows[HUD_GAMEOVER_CAP_ROW][HUD_GAMEOVER_COL0 + 9] == ' ',
          "GAME OVER span's spill cell is a blank character");

    /* the palette banks and layout constraints recorded in hud.h:
     * Task 9 gives the in-play HUD its own bank 11 (PAL_HUD_PLAY), beside
     * the title's PAL_HUD 7; both are free (the fix layer's palettes are
     * sprite banks 0..15; 0 text, 1 dome, 2 ship, 3 missile, 4 bullet,
     * 5 explosion, 6 cracks, 8 ground, 9 mountains, 10 console). */
    check(PAL_HUD == 7, "palette bank 7");
    check(PAL_HUD_PLAY == 11, "in-play palette bank 11");
    check(HUD_INTEG_ROW == 26 && HUD_LIVES_ROW == 28 && HUD_SCORE_ROW == 28
          && HUD_GAMEOVER_ROW == 7, "layout rows");
    check(HUD_INTEG_ICON_COL == 32 && HUD_INTEG_END == 36 && HUD_PCT_COL == 37
          && HUD_LIVES_COL == 32 && HUD_LIVES_STEP == 2 && HUD_DUMP_ROWS == 30,
          "layout columns");
    check(HUD_GAMEOVER_COL0 == 15 && HUD_GAMEOVER_LEN == 10
          && HUD_GAMEOVER_CAP_ROW == HUD_GAMEOVER_ROW + 1,
          "GAME OVER layout (cols 15..24, row 8 cap)");
}

/* Task 9 proof 1, updated by attract Task A1: the header's two fix
 * palettes. fix_pal (PAL_HUD 7) is the title's gold palette — 1..4 the HUD
 * amber gradient, 5 the black outline, 6..9 the logo's gold gradient —
 * exactly the 16 words generate_srom.py writes; fix_pal_amber (the in-play
 * HUD, PAL_HUD_PLAY 11) keeps today's amber 1..5 and old blue 6..9. The
 * two share entries 1..4 (the title's fill is the HUD's amber gradient);
 * entry 5 (title black vs the HUD's brown shadow) and 6..9 (gold vs the
 * old logo blues) differ. Both start with the transparent 0x8000. */
static void test_fix_palettes(void)
{
    static const u16 want_fix[16] = {
        0x8000, 0x6fd9, 0x7fb5, 0x7f92, 0x4e71, 0x0000, 0x5fe8, 0x6fb5,
        0x1f92, 0x6c61, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    };
    static const u16 want_amber[5] = {
        0x6fd9, 0x7fb5, 0x7f92, 0x4e71, 0x2410,
    };
    int i;

    for (i = 0; i < 16; i++)
        check(fix_pal[i] == want_fix[i], "fix_pal word");
    for (i = 0; i < 5; i++)
        check(fix_pal_amber[i + 1] == want_amber[i], "fix_pal_amber 1..5");
    check(fix_pal_amber[0] == fix_pal[0], "fix_pal_amber entry 0");
    /* The title's fill is the HUD's amber gradient (entries 1..4); the
     * title's outline (5) is black, the HUD's shadow is its brown. The
     * logo's gold (6..9) is the title's; the HUD keeps the old blues. */
    for (i = 1; i <= 4; i++)
        check(fix_pal_amber[i] == fix_pal[i], "fix_pal_amber shares the amber");
    check(fix_pal[5] == 0x0000, "the title's outline 5 is black");
    check(fix_pal_amber[5] != fix_pal[5], "the HUD's shadow differs from black");
    for (i = 6; i <= 9; i++)
        check(fix_pal_amber[i] != fix_pal[i], "fix_pal_amber keeps its old blues");
    for (i = 10; i < 16; i++)
        check(fix_pal_amber[i] == fix_pal[i], "fix_pal_amber same 10..15");
    check(sizeof fix_pal / sizeof fix_pal[0] == 16, "fix_pal 16 words");
    check(sizeof fix_pal_amber / sizeof fix_pal_amber[0] == 16,
          "fix_pal_amber 16 words");
}

/* drive the C's game one frame (the same order main.c and hud_sim use) */
static void game_frame(ship_t *s, mis_t *m, rules_t *r, u8 inp, u8 pressed)
{
    u8 busy = rules_begin(r, s, m, pressed);

    if (!busy)
        ship_frame(s, inp, pressed);
    mis_update(m, s, r, pressed, busy);
    rules_end(r, s, m);
}

/* the shared row-28 proof: for every score length 1..8 and every life
 * count 0..3, the C's hud_rows puts the score inside its cols 15..24 band
 * (centred) and the lives' icons on cols 32, 34, 36, and neither write ever
 * lands in the other's cells. Prints each state's row 28 as
 * "R28 <score10> <integ> <lives> <go> <40 chars>" so the Python model
 * compares whole rows (tests/test_hud_model.py). */
static void row28_table(void)
{
    static const u32 scores[] = {0, 1, 12, 123, 1234, 12345, 123456, 1234567};
    rules_t r;
    mis_t m;
    char rows[HUD_DUMP_ROWS][HUD_COLS + 1];
    unsigned si, lives;

    rules_reset(&r);
    mis_reset(&m);
    for (si = 0; si < sizeof scores / sizeof scores[0]; si++) {
        for (lives = 0; lives <= 3; lives++) {
            int col;

            m.score10 = scores[si];
            r.lives = (u8)lives;
            hud_rows(&r, &m, rows);
            /* the lives' three cells and the score's band never cross */
            for (col = 0; col < HUD_COLS; col++) {
                int in_lives = col == HUD_LIVES_COL
                    || col == HUD_LIVES_COL + HUD_LIVES_STEP
                    || col == HUD_LIVES_COL + 2 * HUD_LIVES_STEP;
                int in_score = col >= HUD_SCORE_COL0
                    && col < HUD_SCORE_COL0 + HUD_SCORE_W;
                char ch = rows[HUD_SCORE_ROW][col];

                if (in_lives && !in_score && lives && ch == (char)ICON_SHIP)
                    continue;                 /* a life's icon: fine */
                if (in_score && !in_lives
                    && (ch == ' ' || (ch >= '0' && ch <= '9')))
                    continue;                 /* a score cell: digit or blank */
                if (ch == ' ')
                    continue;                 /* any other cell is blank */
                printf("FAIL shared row 28: score10 %u lives %u col %d is %d\n",
                       scores[si], lives, col, (int)(u8)ch);
                fails++;
            }
            printf("R28 %u %u %u %u %s\n", scores[si], r.integ_pct, lives,
                   (unsigned)r.game_over, rows[HUD_SCORE_ROW]);
        }
    }
}

/* Task G1: "GAME OVER" centred on row 7, its cap row 8, as the shared
 * thick-font writer would draw it. Prints one line per row:
 *   GOFONT <row> <tile> x HUD_GAMEOVER_LEN
 * (base = TITLE2_ROW_BASE on row 7, TITLE2_CAP_BASE on row 8; the left
 * neighbour of the first cell is a space and the span includes the cell
 * after the last character, exactly as hud.c's fix_span call.) */
static void go_font_table(void)
{
    char line[HUD_COLS + 1];
    u8 row, col, i;

    for (i = 0; i < HUD_COLS; i++)
        line[i] = ' ';
    line[HUD_COLS] = 0;
    for (i = 0; i < 9; i++)
        line[HUD_GAMEOVER_COL0 + i] = "GAME OVER"[i];
    for (row = HUD_GAMEOVER_ROW; row <= HUD_GAMEOVER_CAP_ROW; row++) {
        u16 base = (row == HUD_GAMEOVER_ROW)
            ? fix_thick_row_base() : fix_thick_cap_base();

        printf("GOFONT %u", row);
        for (col = HUD_GAMEOVER_COL0; col < HUD_GAMEOVER_COL0 + HUD_GAMEOVER_LEN; col++) {
            char left = col ? line[col - 1] : ' ';
            printf(" %u", (unsigned)fix_thick_tile(base, (u8)line[col],
                                                   (u8)left));
        }
        printf("\n");
    }
}

/* Task G1: hud_rows' rows 7/8 for game_over 0 and 1, for tests/
 * test_hud_model.py. */
static void gameover_rows_table(void)
{
    rules_t r;
    mis_t m;
    char rows[HUD_DUMP_ROWS][HUD_COLS + 1];
    unsigned go;

    rules_reset(&r);
    mis_reset(&m);
    for (go = 0; go <= 1; go++) {
        r.game_over = (u8)go;
        hud_rows(&r, &m, rows);
        printf("GO %u %s\n", go, rows[HUD_GAMEOVER_ROW]);
        printf("GO8 %u %s\n", go, rows[HUD_GAMEOVER_CAP_ROW]);
    }
}

int main(int argc, char **argv)
{
    fix_thick_init();                  /* Task G1: the shared writer's table */
    /* Task G1: the thick font's GAME OVER tiles and hud_rows' rows 7/8. */
    if (argc > 1 && strcmp(argv[1], "gofont") == 0) {
        go_font_table();
        return 0;
    }
    if (argc > 1 && strcmp(argv[1], "go") == 0) {
        gameover_rows_table();
        return 0;
    }
    /* the shared-row table: "R28 <score10> <integ> <lives> <go> <row>"
     * for every score length and life count (tests/test_hud_model.py). */
    if (argc > 1 && argv[1][0] == 'r') {
        row28_table();
        if (fails) {
            printf("%d FAILURES\n", fails);
            return 1;
        }
        return 0;
    }
    /* with a script: print hud_rows per frame for tests/hud_model.py.
     * Lines: "level n", then "input pressed" frames. */
    if (argc > 1 && argv[1][0] == 's') {
        ship_t s;
        mis_t m;
        rules_t r;
        char line[64];
        char rows[HUD_DUMP_ROWS][HUD_COLS + 1];
        unsigned a, b, k;

        ship_reset(&s);
        mis_reset(&m);
        rules_reset(&r);
        while (fgets(line, sizeof line, stdin)) {
            if (sscanf(line, "level %u", &a) == 1)
                r.level = (u8)a;
            else if (sscanf(line, "%u %u", &a, &b) == 2) {
                game_frame(&s, &m, &r, (u8)a, (u8)b);
                hud_rows(&r, &m, rows);
                printf("HU");
                for (k = 0; k < HUD_DUMP_ROWS; k++)
                    printf(" %s", rows[k]);
                printf("\n");
            }
        }
        return 0;
    }

    test_layout();
    test_fix_palettes();
    if (fails) {
        printf("%d FAILURES\n", fails);
        return 1;
    }
    printf("PASS test_hud\n");
    return 0;
}
