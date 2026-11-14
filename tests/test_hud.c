/* test_hud.c: the C-side half of the HUD-layout Task 2 proof.
 *
 * 1. hud_rows is a pure function of the rules state and lays the text out
 *    exactly as hud.h says (the integrity's icon + right-aligned percent +
 *    '%' in the lower right, the lives' icon per life, the centred score,
 *    the centred GAME OVER, everything else blank) — the same rows tests/
 *    hud_model.py and the boot test compare.
 * 2. The palette and the layout constants are as hud.h records (bank 7
 *    free, the readouts clear of the dome), so the fix layer and the
 *    sprites can never fight over palette RAM.
 * 3. run_boot_script: drive the C's rules (rules_begin/ship_frame/
 *    mis_update/rules_end) exactly as main.c does and print hud_rows per
 *    frame; tests/hud_model.py replays the same script against its model.
 *    Used as the boot probe's reference: the probe's frames are matched
 *    to model frames by the deterministic game the script produces.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ship.h"
#include "missiles.h"
#include "rules.h"
#include "hud.h"
#include "fix.h"

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
    check(rows[HUD_GAMEOVER_ROW][15] == ' ' && rows[HUD_GAMEOVER_ROW][24] == ' ',
          "no GAME OVER while playing");
    /* the top of the screen: rows 0..23 (except GAME OVER's row 7) are
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

    /* GAME OVER centred on its row */
    r.game_over = 1;
    hud_rows(&r, &m, rows);
    check(0 == strncmp(rows[HUD_GAMEOVER_ROW] + 15, "GAME OVER", 9),
          "GAME OVER centred");

    /* the palette bank and layout constraints recorded in hud.h */
    check(PAL_HUD == 7, "palette bank 7");
    check(HUD_INTEG_ROW == 24 && HUD_LIVES_ROW == 26 && HUD_SCORE_ROW == 28
          && HUD_GAMEOVER_ROW == 7, "layout rows");
    check(HUD_INTEG_ICON_COL == 32 && HUD_INTEG_END == 36 && HUD_PCT_COL == 37
          && HUD_LIVES_COL == 32 && HUD_LIVES_STEP == 2 && HUD_DUMP_ROWS == 30,
          "layout columns");
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

int main(int argc, char **argv)
{
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
    if (fails) {
        printf("%d FAILURES\n", fails);
        return 1;
    }
    printf("PASS test_hud\n");
    return 0;
}
