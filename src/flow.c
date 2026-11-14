/* flow.c: the game's top-level flow (M6 Task 1). See flow.h.
 *
 * The cart now boots to a title instead of straight into a game, exactly
 * as the Vectrex does. The three states and the transition are described in
 * flow.h; here is the concrete shape of each frame.
 *
 * The title (Task 1's single page): the dome turns one step every 4
 * Vectrex frames (the Vectrex's title_spin), and every other game sprite
 * (the stars, the ship, the missiles and explosions, the broken overlays,
 * the radar) has SCB3 height 0 — hidden (the Vectrex's title draws only
 * the dome). The fix layer, blank from boot, shows page 0 as title.h lays
 * it out (M8 art pass): the "E-SRG" logo on rows 2..5, the level and its
 * best on rows 7 and 9, and under the dome "PRESS START" on row 27,
 * alternating with "B TO CHANGE LEVEL"; the MVS countdown (after a coin)
 * is on row 28, under the prompt. The HUD rows are not drawn.
 *
 * Start (bios_user_mode becomes 2): clear the fix layer, run hud_init,
 * ship_reset / mis_reset / rules_reset, and set hud_framecnt to 0, so the
 * first game frame is 1. The game loop body that follows is exactly the
 * pre-M6 main loop (rules, ship, missiles, cracks, stars, radar, HUD), with
 * the per-frame test hooks, unchanged.
 *
 * GAME OVER: within GAME_OVER_WAIT (295) frames A restarts a new game (the
 * rules' A-restart in rules_begin); when the window expires the cart sets
 * bios_player_mod1 = 0, records the "open the title on HIGH SCORES" byte in
 * backup RAM (Task 3 reads it; Task 1's single-page title ignores it), and
 * returns from flow_run, so main() returns to the BIOS and the BIOS calls
 * main() again — each entry is one title plus one game session.
 *
 * hud_framecnt (src/hud.c) is NOT the cart frame counter any more; it is
 * the number of frames of this game session: 0 on the title, 1 on the first
 * game frame after Start, kept counting through an A-restart, and reset on
 * the next Start. Every MAME probe's fc-keyed numbers stay valid because
 * the game has always begun at fc 1. */
#include <string.h>
#include <ngdevkit/neogeo.h>
#include <ngdevkit/ng-video.h>
#include <ngdevkit/bios-ram.h>
#include <ngdevkit/backup-ram.h>
#include "flow.h"
#include "fix.h"
#include "dome.h"
#include "ship.h"
#include "ship_gfx.h"
#include "missiles.h"
#include "mis_gfx.h"
#include "rules.h"
#include "cracks.h"
#include "hud.h"
#include "stars.h"
#include "radar.h"
#include "radar_gfx.h"
#include "title.h"
#include "best.h"
#include "card.h"
#include "sound.h"
#include "cells.h"                    /* CELL_START (the RADAR_TEST hook) */
#include "missiles_tables.h"          /* mis_r_spawn / mis_cell_ring / phi */

static ship_t ship;
static mis_t mis;
static rules_t rules;
static radar_t radar;               /* the radar's lock state, carried per frame */

/* M7 Task 2: the pip's frame counter. It is 0 on the lock's FIRST frame and
 * counts to 19 then wraps (no %: a u8 % 20 would be a 32-bit __modsi3 call
 * in per-frame code); the pip sounds when it is 0 while the radar is
 * locked, so the pips come every 20 frames from the lock's start (2 radar
 * blink cycles: RADAR_BLINK 5 x 2 x 2 — the port's 2/16 Vectrex pips at
 * 59/50). Reset when not locked. */
static u8 game_pip_t;

typedef enum { FLOW_TITLE, FLOW_GAME, FLOW_GAMEOVER_WAIT } flow_state_t;

static flow_state_t flow;
static u16 gameover_wait;           /* the FLOW_GAMEOVER_WAIT countdown */

/* the backup-RAM "the next title opens its HIGH SCORES page" byte (Task 3
 * reads it; Task 1's single-page title ignores it). It lives in _backup_ram
 * so it outlives the entry, and, on MVS, is saved by the BIOS to saveram
 * when it next enters attract mode. Set right before flow_run returns. */
static u8 _backup_ram flow_open_highscores;

/* M6 Task 7: the chosen level, EASY 0 / NORMAL 1 / HARD 2, in _backup_ram
 * next to flow_open_highscores so it outlives an entry — the title's B
 * press changes it and game_begin reads it. flow_level_valid is the
 * companion marker byte: the task's "backup RAM starts as garbage on a new
 * MVS board" guard. In MAME the backup-RAM block on a FRESH boot (a new
 * MVS board, and the AES's RAM) reads 0x00 — which would be a valid EASY
 * (0) — so a single byte cannot tell "fresh 0" from "chosen EASY". The
 * marker is written at the same time as the level: fresh/garbage memory
 * has marker 0 != FLOW_LEVEL_MAGIC, so the entry opens on NORMAL; once the
 * player (or a return) wrote a level, the pair stays valid across entries
 * (which is the whole point of _backup_ram). */
#define FLOW_LEVEL_MAGIC 0x53
static u8 _backup_ram flow_level;
static u8 _backup_ram flow_level_valid;

/* M6 Task 9: the per-level high-score table, in _backup_ram next to
 * flow_level so it outlives an entry — and, on MVS, the whole persistence
 * there is: the BIOS saves the _backup_ram block to MAME's
 * -nvram_directory when it next enters attract mode, so a value written
 * before flow_run returns survives a power-off. On AES the backup RAM is
 * per-boot only (Task 10 adds the memory card). flow_best is aligned(2) so
 * the struct sits on even addresses; best_t itself is packed, so nothing
 * may take a u32* into one of its members (a 32-bit read at an odd address
 * is a 68000 address error): flow_best_get copies the three score10s into
 * a plain u32[3] first, and best.c/best.h touch the struct field by field,
 * whose byte/word accesses are safe at any alignment. */
static best_t _backup_ram __attribute__((aligned(2))) flow_best;

/* M6 Task 10: the AES memory card's "the first-entry LOAD was done" flag,
 * in _backup_ram next to flow_best. On AES the backup RAM is per-boot
 * only — the task's "load on the FIRST entry after power-on only": after
 * the first flow_run of a boot has LOADed the card into flow_best, the
 * flag is set, so the returns of GAME OVERs (which re-enter flow_run
 * without a power-off) never LOAD again (they must not clobber a table
 * the current boot already improves). A fresh boot's backup RAM holds
 * 0x00 (MAME), which reads "not done": the entry LOADs. On MVS the flag
 * stays meaningless (bios_mvs_flag == 0x80: no card). */
static u8 _backup_ram flow_card_loaded;
#define FLOW_CARD_LOADED_MAGIC 0x5c

/* the entry's "the title opened on page 1" flag: flow_open_highscores is a
 * _backup_ram byte that outlives the entry, so it must NOT be zeroed by
 * flow_run itself (that would undo the byte the GAME OVER return just
 * set). flow_run instead reads it into this plain static (.bss, zeroed on
 * every entry), clears the backup byte, and opens the title on page 1 if
 * it was set, page 0 otherwise (M6 Task 7). */
static u8 open_highscores;

/* the title's state: the tile/sprite drawing each frame and the blink. */
static u8 title_dome;      /* the title's dome rotation steps, 0..239 */
static u16 title_dome_t;   /* the dome step's pacing: += 50 a frame, a step per 236 */
static u8 title_fc;        /* title frames since the entry began (the blink) */

/* Task 1: title frames since this entry began, u16: how long the title has
 * been up when Start is pressed, which seeds the missiles' RNG (game_begin).
 * Incremented once per title frame with title_fc, zeroed with the other
 * title counters at each entry. A plain static (.bss): the entry zeroes it
 * explicitly, so a return from a game starts the title's clock again. */
static u16 title_seed_t;

/* Task 1: the seed game_begin gave this game (mis_seed_from(title_seed_t)) —
 * a debug export like rules_dbg_alive, so the MAME probes can start their
 * missile model where the cart's RNG really started (found by nm, read from
 * RAM once the game has begun). The boot_test's checkers compare it; the
 * normal cart contains it (a tiny .bss word, no behaviour). */
u16 mis_seed_used;

/* M6 Task 6: the title's nine pages (title_page 0..8) and the frames spent
 * on the current page (title_t, u16: 0..294 — one page turn every 295
 * title frames, the Vectrex's 250 x 59/50). Plain statics: .bss is zeroed
 * on every BIOS entry, so without Task 7 every entry opens on page 0, t 0.
 * Task 7 opens on the HIGH SCORES page (1) when the GAME OVER return set
 * flow_open_highscores, and the title's B press jumps to page 0. The probe
 * reads both from RAM (nm gives their addresses). */
static u8 title_page;
static u16 title_t;

/* the title's shown fix rows: "call title_rows only when its visible
 * inputs change" (Task 6): the page, the level, the prompt phase (the row-8
 * alternation), the credits value, or the best table (all zeros until
 * Task 8). When one changes, title_rows rebuilds the 28 rows and only the
 * changed rows are written to the fix layer (as hud.c does); on a frame
 * with no change nothing is drawn. 0xff: never drawn — the first title
 * frame draws everything. */
static u8 title_t_shown_page = 0xff;
static u8 title_t_shown_phase;       /* the shown title_prompt_b */
/* M6 Task 7: the title's shown fix rows' shown level (flow_level_get) —
 * the "write only on visible change" invariant extends to the level. */
static u8 title_t_shown_level = 0xff;
static u8 title_t_shown_credits = 0xff;
/* M6 Task 9: the shown rows' best table. A plain static: .bss is zeroed on
 * every entry, so the first title frame of an entry (title_t_shown_page
 * 0xff) redraws anyway, and a GAME OVER's best_update is visible the frame
 * the returned title first draws its page 1 (the shown copy is from the
 * entry's first draw, before any update this entry could make). */
static u32 title_t_shown_best[BEST_NLEVELS];

/* which entry called the flow: 0 = main() (an attract boot), 1 =
 * main_mvs_title() (the post-coin title on MVS) — see src/main.c. A plain
 * static, set at the top of flow_run from the parameter: .bss is zeroed on
 * each entry anyway, so it reads 0 unless main_mvs_title set it (M6 Task 3:
 * the attract title says INSERT COIN, the post-coin one PRESS START). */
static u8 flow_entry;

/* the MVS countdown row's shown state (M6 Task 3): the last
 * compulsion-timer byte row 28 was drawn with. Initialised to 0xff in
 * .data (not .bss): the runtime re-copies .data on every entry, so the
 * first row-28 draw of each entry happens even when the timer reads 0. */
static u8 title_timer_shown = 0xff;

/* the title's rows (TITLE_TOP_ROW..TITLE_BOTTOM_ROW, the page-0 prompt
 * row TITLE_PRESS_ROW) are in title.h */
#define TITLE_BLINK     32       /* frames on / off */

/* M6 Task 6: one page turn every 295 title frames — the Vectrex's
 * TITLE_PAGE_FRAMES 250 x 59/50, the same value as the GAME OVER window
 * (flow.h). The title's C press turns the page on the spot. */
#define TITLE_PAGE_FRAMES 295

/* ===================== test hooks (from main.c) ===================== */

#ifdef CRACK_TEST
/* A test-only build flag (as the Vectrex's CRACK_TEST): the cart starts
 * with a fixed set of broken cells so the MAME boot-test can check the
 * cracks it draws at known screen positions. Called from game_begin after
 * rules_reset (so the reset clears before the seed) — see main.c's flag
 * comment for the full reasoning. Exactly these cells are what
 * tests/check_broken.py expects (BROKEN_TEST_CELLS). */
static void cracks_test_broken(void)
{
    static const u8 set[] = {
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
        36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51,
        52, 53, 54, 55, 56, 57,
    };
    u8 i;

    for (i = 0; i < sizeof set; i++) {
        ship_set_broken(&ship, set[i]);
        rules.broken[rules.nbroken++] = set[i];
    }
}
#endif
#ifdef GAMEOVER_DRAW_TEST
/* A test-only build flag (like CRACK_TEST): the cart is a one-life game
 * scripted so the MAME boot-test can prove the drawing keeps the dome gone
 * after a game-ending dome death, and keeps it with its broken tiles after
 * a non-dome death's GAME OVER. The hook's policy mirrors
 * scripts/gameover_draw_probe.lua and tests/check_gameover_draw.py (the
 * three must stay in lockstep): the game is pinned to ONE life on its first
 * alive frame; `alive` counts consecutive frames the ship is alive and the
 * game is on; from the 10th alive frame of the NEW game (after the probe's
 * A press) the rings-0..4 top-facing cells are seeded broken and from the
 * 11th the ship parks on broken cell 5 (a CELL death); GAME OVER latches
 * `saw_go`. The state is exported in go_test_dbg (bit0 alive, bit1 saw_go,
 * bit2 seeded). */
volatile u8 go_test_dbg;
static u8 go_test_alive;
static u8 go_test_saw_go;
static u8 go_test_seeded;
static const u8 go_test_seed[13] = { 0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 14 };

/* once per frame, before rules_begin: the alive counter, the one-life pin,
 * and the GAME OVER latch */
static void go_test_frame_begin(rules_t *r)
{
    if (!r->dead_t && !r->game_over) {
        if (go_test_alive != 255)
            go_test_alive++;
    } else {
        go_test_alive = 0;
    }
    if (go_test_alive == 1)
        r->lives = 1;                          /* one life: no mid-game respawn */
    if (r->game_over)
        go_test_saw_go = 1;
    go_test_dbg = (u8)((go_test_alive != 0)
                       | (go_test_saw_go ? 2 : 0)
                       | (go_test_seeded ? 4 : 0));
}

/* once per frame, after mis_update and before rules_end: the phase-2 seed
 * and park (see the flag's comment) */
static void go_test_seed_park(rules_t *r, ship_t *s)
{
    u8 i;

    if (go_test_saw_go && go_test_alive == 10 && !go_test_seeded) {
        for (i = 0; i < 13; i++)
            rules_break_cell(r, s, go_test_seed[i]);
        go_test_seeded = 1;
    }
    if (!r->dead_t && !r->game_over) {
        if (go_test_saw_go && go_test_alive >= 11)
            ship_locate(s, 5);                 /* broken: a cell death */
        else
            ship_locate(s, 27);                /* the start cell (whole) */
    }
}
#endif
#ifdef FRAME_MARK
/* A test-only build flag (like CRACK_TEST): the cart records, every frame,
 * the LSPC line counter at the end of the frame's work, so the boot test
 * can measure the worst-case frame time (M4 Task 4). The normal cart does
 * not define it. */
static volatile u16 work_end_mark;
static volatile u16 work_min_mark;
static volatile u16 work_max_mark;
static volatile u8 work_marked;
static volatile u16 work_start_mark;
static u16 lspc_vpos(void)
{
    return (u16)(((*REG_LSPCMODE >> 7) & 0x1FF) - 0x100);
}

static void work_marks_init(void)
{
    work_marked = 0;
    work_min_mark = work_max_mark = work_start_mark = 0;
}
#endif
#ifdef RADAR_TEST
/* A test-only build flag (like CRACK_TEST): forces the FIRST missile of
 * each game to target the ship's start cell (cell 27), so the radar
 * boot-test's lock-on happens with no input, and the SECOND to a ring-4
 * diagonal. See main.c's flag comment (moved here). */
static u8 radar_test_done;
static u8 radar_test_done2;

static void radar_test_spawn(void)
{
    u8 i;

    for (i = 0; i < NMIS; i++) {
        mis_obj_t *o = &mis.obj[i];

        if (o->state == 1 && o->kind == KIND_MISSILE
            && o->r == mis_r_spawn[o->ring]) {
            if (!radar_test_done) {
                o->ring = mis_cell_ring[CELL_START];
                o->phi = mis_cell_phi[CELL_START];
                o->r = mis_r_spawn[o->ring];
                radar_test_done = 1;
                return;
            }
            if (!radar_test_done2) {
                o->ring = mis_cell_ring[25];
                o->phi = mis_cell_phi[25];
                o->r = mis_r_spawn[o->ring];
                radar_test_done2 = 1;
                return;
            }
        }
    }
}
#endif
#ifdef SOUND_TEST
/* A test-only build flag (like CRACK_TEST): the cart scripts the sound
 * pipeline boot-test (M7 Task 1). On the title, at title frames 100, 160,
 * 220, 280 and 340 the hook sends commands 4, 5, 6, 7 and 8 (one per
 * frame), and at title frame 400 it sends 6 and 8 in the SAME frame — the
 * two-sounds-in-one-frame proof, which needs the acknowledgement wait
 * (src/sound.c) before the second send. Every send is recorded with the
 * title frame it was sent on and the acknowledgement result, in a RAM log
 * the probe reads.
 *
 * The sends key on a hook-owned u16 title counter (sound_test_fc), NOT the
 * flow's u8 title_fc (the blink counter — it wraps at 255, and the sends
 * go up to frame 400). Each title_frame runs once per title frame, so the
 * hook counter IS the title frame number. Records are 4 bytes: title
 * frame lo/hi, command, result. */
static volatile u16 sound_test_fc;
static volatile u8 sound_test_log[32];   /* tf_lo tf_hi cmd ok, ... */
static volatile u8 sound_test_n;

/* M7 Task 2: the game-phase send log, for the sound-game boot-test. Every
 * game sound command goes through the same record as the title sends, so
 * the probe can list each send with the game-session frame (hud_framecnt)
 * and the probe can compare the log with the model's predicted commands.
 * Records are the same 4 bytes (frame lo/hi, command, result) in a
 * separate buffer (sound_test_glog / sound_test_gn); the pipeline test's
 * title sends use the title buffer. GN_MAX records = 2048 x 4 = 8 KB:
 * the sound-game run makes 1593 sends (1488 fires + 16 hits + 84 cracks
 * + 5 pips, the centred game's model totals), and the buffer must stay
 * small — the 68k work RAM is only 64 KB and the BSS sits just under its
 * top edge, so an over-large log would push the layout into the MVS
 * BIOS's territory. */
#define SOUND_TEST_GN_MAX 2048
static volatile u16 sound_test_gn;
static volatile u8 sound_test_glog[SOUND_TEST_GN_MAX * 4];

static void sound_test_grecord(u16 fc, u8 cmd, u8 ok)
{
    u32 n = sound_test_gn;

    if (n < SOUND_TEST_GN_MAX) {
        sound_test_glog[n * 4] = (u8)(fc & 0xff);
        sound_test_glog[n * 4 + 1] = (u8)(fc >> 8);
        sound_test_glog[n * 4 + 2] = cmd;
        sound_test_glog[n * 4 + 3] = ok;
        sound_test_gn = (u16)(n + 1);
    }
}

/* the game's sound commands through the log (function-local so the 68k
 * tail call is easy); the header's sound_cmd is what it records. */
static u8 sound_test_cmd(u16 fc, u8 cmd)
{
    u8 ok = sound_cmd(cmd);

    sound_test_grecord(fc, cmd, ok);
    return ok;
}

/* the SOUND_TEST game path: every sound the game sends, recorded with the
 * game-session frame (hud_framecnt). The 68k tail-calls the log wrapper
 * (the sound_cmd wait makes the call hot), so this is just the routing. */
static u8 sound_game_cmd(u8 cmd)
{
    return sound_test_cmd((u16)hud_framecnt, cmd);
}

static void sound_test_record(u16 tf, u8 cmd, u8 ok)
{
    if (sound_test_n <= sizeof sound_test_log - 4) {
        sound_test_log[sound_test_n++] = (u8)(tf & 0xff);
        sound_test_log[sound_test_n++] = (u8)(tf >> 8);
        sound_test_log[sound_test_n++] = cmd;
        sound_test_log[sound_test_n++] = ok;
    }
}

/* the SOUND_TEST hook, once per title frame (the first title frame counts 1) */
static void sound_test_frame(void)
{
    u16 tf;

    sound_test_fc++;
    tf = sound_test_fc;
    if (tf == 100) {
        sound_test_record(tf, SND_FIRE, sound_cmd(SND_FIRE));
    } else if (tf == 160) {
        sound_test_record(tf, SND_JUMP, sound_cmd(SND_JUMP));
    } else if (tf == 220) {
        sound_test_record(tf, SND_HIT, sound_cmd(SND_HIT));
    } else if (tf == 280) {
        sound_test_record(tf, SND_CRACK, sound_cmd(SND_CRACK));
    } else if (tf == 340) {
        sound_test_record(tf, SND_PIP, sound_cmd(SND_PIP));
    } else if (tf == 400) {
        /* the two-sounds-in-one-frame proof: hit then pip, each
         * acknowledged before the next send */
        u8 ok6 = sound_cmd(SND_HIT);
        u8 ok8 = sound_cmd(SND_PIP);
        sound_test_record(tf, SND_HIT, ok6);
        sound_test_record(tf, SND_PIP, ok8);
    }
}
#endif

/* ===================== the flow frames ===================== */

/* the title's credits value, exactly as title_rows wants it (Task 5):
 * 0 = AES, 1 = MVS before a coin (the main() attract title), 2 = MVS
 * after a coin (the main_mvs_title() title). */
static u8 title_credits(void)
{
    if (bios_mvs_flag == 0)
        return 0;
    return flow_entry == 0 ? 1 : 2;
}

/* M6 Task 7: the level this entry's title draws and a game begins with.
 * The `valid` marker distinguishes "fresh/garbage backup RAM" (0x00, which
 * would read as a valid EASY) from "a chosen level": the pair is written
 * together on the first B press (and on every B press) and by game_begin.
 * Anything else (a torn write, an old cart's bytes) must never be used —
 * NORMAL is the safe default, and the task's proofs 1 and 3 both require
 * a fresh boot to open on NORMAL. */
static u8 flow_level_get(void)
{
    if (flow_level_valid != FLOW_LEVEL_MAGIC)
        return LEVEL_NORMAL;
    if (flow_level > LEVEL_HARD)
        return LEVEL_NORMAL;
    return flow_level;
}

static void flow_level_set(u8 level)
{
    flow_level = level;
    flow_level_valid = FLOW_LEVEL_MAGIC;
}

/* M6 Task 9: the title's best table as a plain u32[3] — NEVER
 * flow_best.score10 itself (a pointer to a packed member): the 68000
 * faults a 32-bit read at an odd address, and storing after best_update
 * made this a live path every GAME OVER and every entry. The three-word
 * copy costs nothing (title_rows runs only when a visible input changed). */
static void flow_best_get(u32 best[3])
{
    best[0] = flow_best.score10[0];
    best[1] = flow_best.score10[1];
    best[2] = flow_best.score10[2];
}

/* M6 Task 10: the AES memory card. card_load_best / card_save_best live
 * in src/card.c, which owns the BIOS calls; here are the two hooks:
 *
 *  - flow_card_load: at the FIRST flow_run entry of a boot (the
 *    _backup_ram flow_card_loaded flag says it was not done yet — on a
 *    fresh boot the backup RAM reads 0x00), LOAD the saved table into a
 *    temporary; if the load answers OK and best_valid passes, copy it
 *    into flow_best (this boot's table starts from the card). Any other
 *    answer keeps the reset table of this entry. Runs before the entry's
 *    own best_valid check's reset, in the order flow_run calls. Card
 *    calls are entry-time only (never per frame).
 *
 *  - flow_card_save: at GAME OVER when best_update returned 1 (the table
 *    changed), SAVE it; the FORMAT retry on 0x81 lives in card.c. Skips
 *    on MVS (no card there). Runs even when the entry's LOAD already
 *    copied the card — a game that improves on the loaded table must be
 *    saved back. */
static void flow_card_load(void)
{
    best_t tmp;

    if (bios_mvs_flag != 0)
        return;
    if (flow_card_loaded == FLOW_CARD_LOADED_MAGIC)
        return;
    flow_card_loaded = FLOW_CARD_LOADED_MAGIC;
    if (card_load_best(&tmp))
        flow_best = tmp;
}

static void flow_card_save(void)
{
    if (bios_mvs_flag != 0)
        return;
    card_save_best(&flow_best);
}

/* the title's visible-input change detector: the page, the level, the prompt phase
 * (the row-8 alternation), the credits value and the best table (M6 Task
 * 9: the high scores now draw page 0's row 7 and page 1's three rows, so
 * a best change is a visible change). When none changed, the fix layer
 * already shows the right rows — nothing is written. */
static u8 title_visible_changed(u8 t_phase, u8 credits, const u32 best[3])
{
    u8 i;

    for (i = 0; i < BEST_NLEVELS; i++)
        if (title_t_shown_best[i] != best[i])
            return 1;
    return title_t_shown_page != title_page
        || title_t_shown_level != flow_level_get()
        || title_t_shown_phase != t_phase
        || title_t_shown_credits != credits;
}

/* the fix rows a title page puts text on: page 0's logo, level and best
 * (rows 2..9) and its prompt (row 27); pages 1..8 rows 6..24 (6 + 9 x 2) */
static u8 title_row_used(u8 page, u8 row)
{
    if (page == 0)
        return (u8)(row <= TITLE_BEST_ROW || row == TITLE_PRESS_ROW);
    return (u8)(row >= 6 && row <= 24);
}

/* the incremental fix-layer writer: write to the fix layer only the rows
 * that can differ (as hud.c does). Row 28 is never written here —
 * title_rows leaves it out, and the MVS countdown (flow.c) owns it on
 * every page. */
static void title_draw_rows(u8 credits, const u32 best[3])
{
    char rows[TITLE_ROWS][TITLE_COLS + 1];
    u8 i, all;

    /* the caller only reaches this when a visible input changed (the page,
     * the level, the prompt phase, the credits value, or the best table). Decide
     * which rows differ from the input that changed, not by scanning the
     * previous rows: a byte-wise scan costs ~80 lines of 68k work
     * (measured with the frame-mark phase marks, M6) and is what the
     * "write only the differing rows" rule is really about. title_rows'
     * output differs from the previous frame's in:
     *   - every row, when the page, the level, the credits value or the
     *     best table changed (the page's whole text block is new);
     *   - page 0's prompt row only, when the prompt phase flipped;
     *   - nothing on pages 1..8 (none of their lines reads t).
     * Row 28 stays alone — the MVS countdown (flow.c) owns it, on every
     * page, and title_rows never fills it. */
    all = (title_page != title_t_shown_page
           || flow_level_get() != title_t_shown_level
           || credits != title_t_shown_credits);

    title_rows(title_page, flow_level_get(), title_t, best, credits, rows);
    if (all) {
        /* the rows the new page or the shown one uses (M8 art pass: the
         * logo and the bottom prompt made a page turn rewrite rows 2..27,
         * 209 scanlines; the rest are blank on both pages). At an entry
         * the shown page is 0xff and the fix layer all spaces (main.c's
         * fix_clear), so only the new page's rows are needed. */
        for (i = TITLE_TOP_ROW; i <= TITLE_BOTTOM_ROW; i++)
            if (i != TITLE_COUNTDOWN_ROW
                && (title_row_used(title_page, i)
                    || (title_t_shown_page <= 8
                        && title_row_used(title_t_shown_page, i))))
                fix_text(0, i, PAL_HUD, rows[i]);
    } else if (title_page == 0) {
        fix_text(0, TITLE_PRESS_ROW, PAL_HUD, rows[TITLE_PRESS_ROW]);
    }
}

/* the page's fix rows: title_rows only when a visible input changed (the
 * page, the level, the prompt phase, the credits value, or the best
 * table), and only the changed rows are written. Row 28's countdown stays
 * as Task 3 moved it, on every page. Every frame (title_frame), and once
 * at the entry in a frame of its own before the first title frame
 * (flow_run): the entry's full draw then stays out of the first title
 * frame, which also rebuilds the dome (M8 art pass: together they overran
 * it, and that frame showed the text half drawn). */
static void title_text(void)
{
    u8 s, credits, phase;
    u32 best[BEST_NLEVELS];

    credits = title_credits();
    phase = title_prompt_b(title_t);
    flow_best_get(best);

    if (title_visible_changed(phase, credits, best)) {
        title_draw_rows(credits, best);
        title_t_shown_page = title_page;
        title_t_shown_level = flow_level_get();
        title_t_shown_phase = phase;
        title_t_shown_credits = credits;
        for (s = 0; s < BEST_NLEVELS; s++)
            title_t_shown_best[s] = best[s];
    }
}

/* the per-frame title body */
static void title_frame(void)
{
    u8 view, s;
    u8 lvl = flow_level_get();

    title_fc++;
    title_seed_t++;
    title_t++;
    if (title_t >= TITLE_PAGE_FRAMES) {  /* one page turn every 295 title
                                          * frames (the Vectrex's 250 x
                                          * 59/50) */
        title_t = 0;
        if (++title_page > 8)
            title_page = 0;
    }
    if ((bios_p1change & CNT_C) && title_t != 0) {   /* C turns the page
                                          * on the spot; the frame that just
                                          * auto-turned (title_t 0, the
                                          * page already advanced) does not
                                          * double-turn */
        title_t = 0;
        if (++title_page > 8)
            title_page = 0;
    }
    /* M6 Task 7: B changes the level (EASY -> NORMAL -> HARD -> EASY) and
     * jumps the title back to page 0 with title_t 0 — the Vectrex's
     * "B TO CHANGE LEVEL". The title only cycles visibly when the new
     * level's name row differs from the old one's; a page-0 B press hits
     * the "B TO CHANGE LEVEL" prompt (title_prompt_b set) without changing the
     * drawn level, so the reset would flip the prompt row off (confusing)
     * and the task's "page 0, title_t 0" after a B would make the press
     * invisible. Only reset the page/t on a press that changes the drawn
     * level: on page 0 with the prompt phase clear, a B still changes the level byte
     * (and the prompt was off), but the page-0/t-0 reset flag is skipped —
     * the level change itself is the visible effect there, and the checker
     * keys its page-0/t-0 gate on the B presses that produced one. */
    if (bios_p1change & CNT_B) {
        u8 next = (u8)(lvl + 1);

        if (next >= LEVELS)          /* EASY -> NORMAL -> HARD -> EASY: a
                                      * conditional wrap, never a modulo
                                      * (a % would be a 32-bit __modsi3
                                      * call in per-frame code) */
            next = 0;
        if (next != lvl) {
            flow_level_set(next);
            if (title_page != 0 || title_prompt_b(title_t)) {
                title_page = 0;
                title_t = 0;
            }
        }
    }
    title_dome_t += 50;                  /* the Vectrex's title_spin: one */
    if (title_dome_t >= 4 * 59) {        /* step every 4 of its 50 Hz frames */
        title_dome_t -= 4 * 59;          /* (every 4.72 frames here) */
        if (++title_dome >= 240)
            title_dome = 0;
    }
    /* hide everything but the dome: the ship, the missiles and
     * explosions, the broken overlays and the radar all get SCB3 height 0
     * (the task's proof (a)); the stars too, below. The
     * missiles/explosions/radar were left hidden by their *_init, but the
     * hide is unconditional so the check holds however the entry got here. */
    ship_gfx_hide();
    cracks_show_empty();
    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + MIS_BEHIND_SPRITE);
    for (s = 0; s < MIS_BEHIND_COUNT; s++)
        *REG_VRAMRW = 0;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + MIS_FRONT_SPRITE);
    for (s = 0; s < MIS_FRONT_COUNT; s++)
        *REG_VRAMRW = 0;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + EXPL_SPRITE);
    for (s = 0; s < EXPL_COUNT; s++)
        *REG_VRAMRW = 0;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + SHIP_SPRITE);
    for (s = 0; s < SHIP_COUNT; s++)
        *REG_VRAMRW = 0;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + RADAR_SPRITE);
    for (s = 0; s < RADAR_COUNT; s++)
        *REG_VRAMRW = 0;

    /* the dome on page 0 only (Task 6): on pages 1..8 the dome is hidden
     * with its own hide (dome_title_hide: every column's SCB3 zeroed, the
     * mode HIDDEN); on page 0 dome_collapse re-chains a hidden dome by
     * itself (its mode isn't WHOLE, so it runs dome_rechain + dome_show)
     * and dome_show draws the current view's tiles. The rules are at their
     * entry zero, so collapse_state is 1 (whole). The stars are hidden on
     * every page (M8 art pass: the Vectrex's title draws no stars). */
    view = (u8)(title_dome % 48);
    if (title_page == 0) {
        dome_collapse(&rules, view);
        dome_show(view);
    } else {
        dome_title_hide();
    }
    stars_hide();                       /* the Vectrex's title draws no stars */

    title_text();

    /* row 28, the MVS countdown: only after a coin (main_mvs_title() set
     * flow_entry 1). The BIOS's compulsion timer is BCD seconds; its high
     * nibble then its low nibble ('0' + n) go in cols 19 and 20 — call it
     * 0x30 -> "30" through 0x00 -> "00". Rewritten only when the value
     * changes (the Vectrex draws on change); title_timer_shown's 0xff
     * initialiser lives in .data, which the runtime re-copies on every
     * entry, so the first row-28 draw of an entry always happens. Row 28
     * stays blank on AES and before a coin. On page 0 row 27 holds the
     * prompt (the title's own line) — the countdown sits under it, on
     * every page. */
    if (flow_entry == 1) {
        u8 t = (u8)(bios_compulsion_timer & 0xff);

        if (t != title_timer_shown) {
            char s[3];

            s[0] = (char)('0' + (t >> 4));
            s[1] = (char)('0' + (t & 0x0f));
            s[2] = 0;
            fix_text(TITLE_COUNTDOWN_COL, TITLE_COUNTDOWN_ROW, PAL_HUD, s);
            title_timer_shown = t;
        }
    }
#ifdef SOUND_TEST
    sound_test_frame();      /* the M7 Task 1 test sends, on title frames */
#endif
}

/* enter FLOW_GAME after a Start: clear the fix layer, run hud_init (which
 * draws the HUD's constant rows), reset the game's state, and reset the
 * game-session frame counter so the first game frame is 1. */
static void game_begin(void)
{
    hud_clear();                 /* blank the title rows + reset the HUD state */
    hud_init();                  /* the HUD's constant rows (labels, title, help) */
    /* the title's hide zeroed every ship and radar slot's SCB3, including
     * the words only these inits write: the ship's sticky follower (the
     * "only the left half" bug) and the radar frame's 4 slots. Rewrite
     * them before the first game frame. */
    ship_gfx_init();
    radar_gfx_init();
    ship_reset(&ship);
    mis_reset(&mis);
    /* Task 1: every game seeds the missiles' RNG from the title's time, so
     * no two Starts launch the same targets in the same order. (The Vectrex
     * 1.1.0 seeded it once, at power-on.) mis_seed_from never returns 0. */
    mis.rng = mis_seed_from(title_seed_t);
    mis_seed_used = mis.rng;
    rules_reset(&rules);
    /* M6 Task 7: the game runs at the level the title chose. rules_reset
     * sets NORMAL, so the chosen level is written here, and mis.level with
     * it (EASY's missiles fly at 0.75x — missiles.c reads mis.level).
     * rules_begin's new_game copies r->level into m->level on an A-restart
     * (rules.c), so the restart keeps the level of its own accord; the
     * explicit write makes the first game's missiles agree too. The pair
     * is (re)written to backup RAM here as well, so a game that began
     * (however the level was chosen) pins the marker-and-level pair. */
    rules.level = flow_level_get();
    mis.level = rules.level;
    flow_level_set(rules.level);
#ifdef CRACK_TEST
    cracks_test_broken();        /* the 38 broken cells, before the first
                                  * rules_end: the integrity and the HUD see
                                  * them (as main.c did at entry) */
#endif
}

/* M7 Task 2: the frame's sound commands, after the frame's logic. The
 * Vectrex plays jump, fire, hit and crack (e-srg.c sound_update) and the
 * pip (lock_update) at the moments the game events happen; here the
 * events (ship.jumped, mis.sfx, the collapse's phase, the radar's lock)
 * become the driver commands, in the Vectrex's order: input/jump, fire,
 * then the missiles — a hit and a crack in the same frame send the crack
 * (break_tile zeroes snd_hit; e-srg.c's `if (snd_hit && snd_crack) ...
 * 0`), and a jump and a fire cannot start in the same frame (fire waits
 * for the ship to rest). The rumble is the hit sample repeated while the
 * collapse shakes, every 9 frames from the death (the port's 41-frame
 * shake: f = 0, 9, 18, 27, 36 of collapse_frac). The title sends none
 * (title_frame has no sound step). Every command goes through the same
 * acknowledged sound_cmd, so two sounds in one frame both play. */
static void game_sound(u8 died)
{
    u8 f = collapse_frac(&rules);

#ifdef SOUND_TEST
#define SND_CMD(c) sound_game_cmd(c)
#else
#define SND_CMD(c) sound_cmd(c)
#endif
    if (ship.jumped)
        SND_CMD(SND_JUMP);
    if (mis.sfx & SFX_FIRE)
        SND_CMD(SND_FIRE);
    if (died)                           /* the ship's explosion: the hit */
        SND_CMD(SND_HIT);               /* (e-srg.c kill_ship's explode_at,
                                         * after break_tile: it beats the
                                         * frame's crack; on a dome death it
                                         * is the rumble's first beat too) */
    else if (mis.sfx & SFX_CRACK)       /* the same-frame rule: a crack */
        SND_CMD(SND_CRACK);             /* takes channel C over a hit */
    else if (mis.sfx & SFX_HIT)
        SND_CMD(SND_HIT);
    /* the collapse's rumble: the shake's 5 beats at f = 0, 9, 18, 27, 36
     * of the DOME collapse (dome_dead). collapse_frac returns 0 for a
     * plain cell death too (no dome collapse: no shake, no rumble), so
     * the gate must require dome_dead — otherwise f is 0 the whole cell
     * death and the rumble would sound every frame. */
    if (rules.dead_t && rules.dome_dead
        && (f == 9 || f == 18 || f == 27 || f == 36))
        SND_CMD(SND_HIT);
    if (radar.locked) {
        if (game_pip_t == 0)
            SND_CMD(SND_PIP);
        if (++game_pip_t == 20)         /* 20 frames: 2 blink cycles */
            game_pip_t = 0;
    } else {
        game_pip_t = 0;
    }
#undef SND_CMD
}

/* the current game loop body, one frame (rules, ship, missiles, cracks,
 * stars, radar, HUD — the pre-M6 main loop, with the test hooks). */
static void game_frame(void)
{
    static u8 view = 255;
    u8 v, e, pressed, died = 0;

#ifdef GAMEOVER_DRAW_TEST
    go_test_frame_begin(&rules);
#endif
    /* M6 Task 4: on MVS, A at GAME OVER must not restart the game — a new
     * game needs a credit. The A-restart lives in rules.c's rules_begin
     * (`pressed & CNT_A`); gate it here from flow.c, without touching
     * rules.c, by not passing A to it on MVS (bios_mvs_flag is 0x80 on MVS,
     * 0x00 on AES): an A press during the 295-frame GAME OVER window never
     * reaches rules_begin's restart check, so the window always expires and
     * the cart returns to the title. AES is unchanged. The true change byte
     * still goes to mis_update below — A as "fire" is a game play input, not
     * a restart, and masking it would break firing. The 16-bit rule holds:
     * one compare and one AND, no library calls. */
    pressed = (u8)(bios_p1change & ~(bios_mvs_flag == 0x80 ? CNT_A : 0));
    e = rules_begin(&rules, &ship, &mis, pressed);
    if (!e)                             /* the game play turn */
        ship_frame(&ship, bios_p1current, bios_p1change);
    mis_update(&mis, &ship, &rules, bios_p1change, e);
#ifdef RADAR_TEST
    if (rules.game_over) {           /* an A-restart's first missile locks again */
        radar_test_done = 0;
        radar_test_done2 = 0;
    }
    radar_test_spawn();              /* after mis_update: its first launch */
#endif
#ifdef GAMEOVER_DRAW_TEST
    go_test_seed_park(&rules, &ship);       /* before rules_end */
#endif
#ifdef CRACK_TEST
    /* the test cart's 38 broken cells would trigger a dome death on the
     * first rules_end (which clears the missiles and hides the overlays);
     * keep the test scene stable: rules_end sees a whole dome, then the 38
     * broken cells are restored for the draw. */
    {
        u16 save_n = rules.nbroken;
        rules.nbroken = 0;
        ship_locate(&ship, 27);  /* whole mid-dome cell: no death, no clear */
        rules_end(&rules, &ship, &mis);
        rules.nbroken = save_n;
        rules.dead_t = 0;
        rules.game_over = 0;
    }
#else
    died = (u8)rules_end(&rules, &ship, &mis);
#endif
    if (died) {                         /* the ship explodes where it rested */
        s16 ex, ey;                     /* (e-srg.c kill_ship's explode_at) */

        ship_gfx_centre(ship.lat, &ex, &ey);
        mis_gfx_explode_at(ex, ey);
    }
    hud_frame(&rules, &mis);
    v = (u8)(ship.dome_angle % 48);
    dome_collapse(&rules, v);
    if (v != view && collapse_state(&rules) != 2) {
        dome_show(v);
        view = v;
    }
    if (!rules.dead_t && !rules.game_over)
        ship_gfx_show(ship.lat, ship.lift);
    else
        ship_gfx_hide();
    mis_gfx_show(&mis, ship.dome_angle);
    cracks_show(&rules, ship.dome_angle);
    stars_show(ship.dome_angle);
    radar_frame(&radar, &mis, &ship);
    radar_gfx_show(&radar);
    game_sound(died);                /* M7 Task 2: the frame's sound commands */
}

/* ===================== the entry points ===================== */

/* the cart's Start hook: the BIOS calls it from vblank when the player
 * presses Start (AES) or Start with a credit (MVS); it must set
 * bios_user_mode = 2 and bios_player_mod1 = 1. The loop sees
 * bios_user_mode == 2 on its next frame and leaves the title. */
void player_start(void)
{
    bios_user_mode = 2;
    bios_player_mod1 = 1;
}

/* the flow loop: the one loop main() and main_mvs_title() both enter. */
void flow_run(u8 entry)
{
#ifdef FRAME_MARK
    work_marks_init();
#endif
    flow_entry = entry;                 /* 0: main (attract boot); 1:
                                         * main_mvs_title (post-coin, MVS) */
    /* M7 Task 1: the sound driver (M ROM) is reset once at entry, as the
     * ADPCM-A example's main() does. sound_reset goes through the same
     * acknowledged path as every other command, so a driver that never
     * answers is never silently swallowed — but it is the first command
     * sent and the FIFO is empty, so there is no ordering hazard. */
    sound_reset();
    /* M6 Task 10: the AES memory card. The first entry of a boot LOADs
     * the card's table into flow_best (flow_card_loaded says it was
     * done); this must run BEFORE the entry's best_valid reset below —
     * a loaded valid table is kept, a fresh/garbage one is reset here. */
    flow_card_load();
    /* M6 Task 9: every entry re-checks the backup-RAM high-score table:
     * fresh/garbage backup RAM (a new MVS board, the AES's per-boot RAM)
     * is not a valid table (best_valid rejects the magic/sum), so it is
     * reset to a clean all-zeros table here; a valid table is kept, which
     * is the whole point (on MVS it was saved by the BIOS on the last
     * attract entry and survives power-off). best.c's field accesses are
     * byte/word safe at any alignment. */
    if (!best_valid(&flow_best))
        best_reset(&flow_best);
    /* M6 Task 7: the entry's title page — the HIGH SCORES page (1) after
     * a spent GAME OVER (the return set flow_open_highscores), page 0
     * otherwise (a fresh boot, or a normal Start return). The backup byte
     * outlives the entry and must not be zeroed here (that would undo the
     * GAME OVER return's byte); read it into the plain static, then clear
     * it so the NEXT entry (after the next game) opens on page 0 again. */
    open_highscores = flow_open_highscores;
    flow_open_highscores = 0;
    flow = FLOW_TITLE;
    title_dome = title_dome_t = title_fc = 0;
    title_seed_t = 0;
    title_page = (u8)(open_highscores ? 1 : 0);
    title_t = 0;
    gameover_wait = 0;
    ng_wait_vblank();                   /* (a stale flag at entry: skip it) */
    ng_wait_vblank();                   /* the entry's text, in a frame of */
    title_text();                       /* its own (from a vblank, so it is
                                         * whole by the frame's end), before
                                         * frame 1 rebuilds the dome */
    for (;;) {
        ng_wait_vblank();
#ifdef FRAME_MARK
        work_start_mark = lspc_vpos();       /* vblank return: the frame's start */
#endif
        switch (flow) {
        case FLOW_TITLE:
            if (bios_user_mode == 2) {       /* a Start press: begin a game */
                game_begin();
                flow = FLOW_GAME;
            } else {
                title_frame();
            }
            break;
        case FLOW_GAME:
            if (rules.game_over) {
                /* the frame GAME OVER was first seen: enter the 295-frame
                 * window; the current frame's body still runs so the GAME
                 * OVER text draws, and A can restart within the window. M6
                 * Task 9: the session's final score is entered into the
                 * backup-RAM table NOW, on the frame the game ends (the
                 * task's "at GAME OVER"), before any A-restart could start
                 * a new game and overwrite mis.score10. The window may
                 * then run out (the table is already recorded) or A may
                 * restart (the table keeps the higher of the two games'
                 * scores). Time: entry/return code, never per-frame, so
                 * best_update's u32 maths (libgcc calls on the 68000) is
                 * allowed here. */
                if (rules.level < LEVELS)
                    if (best_update(&flow_best, rules.level, mis.score10))
                        flow_card_save();   /* M6 Task 10: the table
                                             * changed — put it on the
                                             * AES memory card (the
                                             * FORMAT retry lives in
                                             * card.c) */
                flow = FLOW_GAMEOVER_WAIT;
                gameover_wait = 0;
            }
            game_frame();
            break;
        case FLOW_GAMEOVER_WAIT:
            if (!rules.game_over) {          /* A restarted within the window */
                flow = FLOW_GAME;
            } else if (gameover_wait >= GAME_OVER_WAIT) {
                /* the window is spent: return to the title. Record the
                 * "open the HIGH SCORES page" byte for Task 3, tell the
                 * BIOS the game is over, and return — the BIOS calls
                 * main() again (~200 MAME frames later), so the next entry
                 * shows the title. */
                flow_open_highscores = 1;
                bios_player_mod1 = 0;
                return;
            } else {
                gameover_wait++;
            }
            game_frame();
            break;
        }
#ifdef FRAME_MARK
        work_end_mark = lspc_vpos();
        if (!work_marked) {
            work_marked = 1;
            work_min_mark = work_max_mark = work_end_mark;
        } else {
            if (work_end_mark > work_max_mark)
                work_max_mark = work_end_mark;
            if (work_end_mark < work_min_mark)
                work_min_mark = work_end_mark;
        }
#endif
    }
    /*NOTREACHED*/
}
