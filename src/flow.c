/* flow.c: the game's top-level flow (M6 Task 1). See flow.h.
 *
 * The cart now boots to a title instead of straight into a game, exactly
 * as the Vectrex does. The three states and the transition are described in
 * flow.h; here is the concrete shape of each frame.
 *
 * The title (Task 1's single page): the dome turns one step every 4
 * Vectrex frames (the Vectrex's title_spin), and every other game sprite
 * (the ship, the missiles and explosions, the broken overlays, the radar)
 * has SCB3 height 0 — hidden (the Vectrex's title draws only the dome).
 * The backdrop is black on the title (dome-scenery Task 4: the stars are
 * retired and the sky is the backdrop in play only).
 * The fix layer, blank from boot, shows page 0 as title.h lays
 * it out (M8 art pass + attract Task A1's caps): the "E-SRG" logo on rows
 * 2..5, the level and its best on rows 7 and 9 (their cap rows 8 and 10),
 * and above the console "PRESS START" on row 21 (its cap row 22),
 * alternating with "B TO CHANGE LEVEL"; the MVS countdown (after a coin)
 * is on row 28, below the prompt. The HUD rows are not drawn.
 *
 * Start (bios_user_mode becomes 2): clear the fix layer, run hud_init,
 * ship_reset / mis_reset / rules_reset, and set hud_framecnt to 0, so the
 * first game frame is 1, and the backdrop becomes the sky. The game loop
 * body that follows is exactly the pre-M6 main loop (rules, ship, missiles,
 * cracks, radar, HUD), with the per-frame test hooks, unchanged.
 *
 * GAME OVER: within GAME_OVER_WAIT (295) frames A restarts a new game (the
 * rules' A-restart in rules_begin); when the window expires the cart sets
 * bios_player_mod1 = 0, records the "open the title on HIGH SCORES" byte in
 * backup RAM (Task 3 reads it; Task 1's single-page title ignores it), and
 * returns from flow_run, so main() returns to the BIOS and the BIOS calls
 * main() again — each entry is one title plus one game session. The
 * backdrop goes back to black on the way out, and every entry sets it
 * black again before the title's first frame (dome-scenery Task 4).
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
#include "radar.h"
#include "radar_gfx.h"
#include "ring_gfx.h"
#include "ground.h"
#include "mountains.h"
#include "band.h"
#include "console.h"
#include "props.h"
#include "collapse.h"
#include "title.h"
#include "demo.h"
#include "board.h"
#include "card.h"
#include "sound.h"
#include "softdip.h"
#include "cells.h"                    /* CELL_START (the RADAR_TEST hook) */
#include "missiles_tables.h"          /* mis_r_spawn / mis_cell_ring / phi */

/* P1: title.c's span-returning row builder. title.h stays the host model's
 * interface (title_rows); only the cart needs the spans. Task B3: the
 * boards need all five entries, so the rows are built from the packed
 * board_t (flow_board) instead of just its top entries. */
void title_rows_spans(u8 page, u8 level, u16 t, const board_t *board,
                      u8 credits, char rows[TITLE_ROWS][TITLE_COLS + 1],
                      u8 sp_col[TITLE_ROWS], u8 sp_len[TITLE_ROWS]);

/* Attract Task A3: the demo resets the game state, so ship / mis / rules are
 * file-global (src/demo.c declares them extern). Everything else in the
 * cart still reaches them only through this file. */
ship_t ship;
mis_t mis;
rules_t rules;
static radar_t radar;               /* the radar's lock state, carried per frame */

/* R1: the frame-to-frame sound state (src/sound.h): the scuttle's spin
 * period and the lock pip's 0..19 counter. It is reset by game_begin and
 * by the demo's restart, so a new game's spin starts its period afresh and
 * the pips come every 20 frames from the lock's first frame. */
static sound_state_t game_sound_state;

/* Attract Task A3: the shown dome view, shared by the demo and the game.
 * It must reset when a new game starts (the demo may have turned the dome)
 * and when the demo restarts, so the first frame draws the new state's view
 * instead of keeping the previous one. */
static u8 game_view = 255;

/* dome-scenery Task 4: the backdrop (palette RAM's last entry) is the sky in
 * play and black on the title. The sky is RGB (120, 176, 228) packed exactly
 * as generate_srom.py's neo_colour packs a colour (each channel to 5 bits,
 * the low bits in 14..12, the upper nibbles in 11..8 / 7..4 / 3..0, dark bit
 * 0): 0x47be, which MAME's resistor-network DAC renders as (117, 182, 233).
 * src/main.c's palettes_init writes black at boot; here every entry sets
 * black again, every game start sets the sky, and the GAME OVER return sets
 * black before it leaves. */
#define COL_SKY 0x47be
#define COL_BLACK 0x0000

static void backdrop(u16 colour)
{
    *((volatile u16 *)0x401ffe) = colour;
}

typedef enum {
    FLOW_TITLE, FLOW_GAME, FLOW_GAMEOVER_WAIT, FLOW_ENTRY
} flow_state_t;

static flow_state_t flow;
static u16 gameover_wait;           /* the FLOW_GAMEOVER_WAIT countdown */
/* high-score boards Task B6: the GAME OVER text frames counted from the
 * frame it was first seen (the current frame included), independent of
 * gameover_wait so the non-qualifying 295-frame window's timing does not
 * move. A qualifying game enters FLOW_ENTRY after this many. */
#define GAME_OVER_TEXT_FRAMES 118
static u16 gameover_shown;

/* high-score boards Task B6: the entry screen's state. entry_rank is the
 * board_rank computed on the GAME OVER frame (BOARD_NENTRIES when the score
 * does not qualify); entry_qualifies is that test. entry_score10 is
 * mis.score10 then. entry_base_angle is the GAME OVER dome angle, the base
 * entry_dome_angle turns from. entry_fc counts the FLOW_ENTRY frames (the
 * pointer/blink phase, as the mockup's t). go_suppress_a masks A from
 * rules_begin for a qualifying GAME OVER (no A-restart on the way to the
 * entry; a non-qualifying window keeps today's A-restart). */
static entry_t entry_state;
static u8 entry_rank;
static u8 entry_qualifies;
static u32 entry_score10;
static u8 entry_base_angle;
static u16 entry_fc;
static u8 go_suppress_a;

/* the entry screen's six fix rows (2..7): text rows 2/4/6 and their caps
 * 3/5/7, each the full 40 columns (the commit writes every cell, so the
 * old GAME OVER row 7 is cleared). */
static char entry_text[7][TITLE_COLS + 1];   /* rows 2..7 and the
                                              * row-8 blank (G1) */
static u8 entry_text_dirty[7];

/* high-score boards Task B3: the backup-RAM page the next title opens on
 * (0 = the dome page; 1..3 = EASY/NORMAL/HARD's board). It lives in
 * _backup_ram so it outlives the entry, and, on MVS, is saved by the BIOS
 * to saveram when it next enters attract mode. Set right before flow_run
 * returns: the board page of the game's level. */
static u8 _backup_ram flow_open_page;
/* high-score boards Task B6: the new entry's rank + 1 on the board page the
 * title opens on, or 0 for none. flow_run reads it with flow_open_page and
 * clears it; the returned title then hides that rank's row (and its cap)
 * every other 16 frames. Only the END path sets it, so a non-qualifying
 * GAME OVER's return (which sets only flow_open_page) has no blink. */
static u8 _backup_ram flow_open_rank;

/* M6 Task 7: the chosen level, EASY 0 / NORMAL 1 / HARD 2, in _backup_ram
 * next to flow_open_page so it outlives an entry — the title's B
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

/* high-score boards Task B2: the five-entry per-level board, in _backup_ram
 * next to flow_level so it outlives an entry — and, on MVS, the whole
 * persistence there is: the BIOS saves the _backup_ram block to MAME's
 * -nvram_directory when it next enters attract mode, so a value written
 * before flow_run returns survives a power-off. On AES the backup RAM is
 * per-boot only (the memory card is the persistence). flow_board is
 * aligned(2) so the struct sits on even addresses; board_t itself is
 * packed, so nothing may take a u32* into one of its members (a 32-bit
 * read at an odd address is a 68000 address error): flow_board_get copies
 * each level's top score10 into a plain u32[3] first, and board.c/board.h
 * touch the struct field by field, whose byte/word accesses are safe at
 * any alignment. */
static board_t _backup_ram __attribute__((aligned(2))) flow_board;

/* high-score boards Task B2: the AES memory card's "the first-entry LOAD
 * was done" flag, in _backup_ram next to flow_board. On AES the backup RAM
 * is per-boot only — the task's "load on the FIRST entry after power-on
 * only": after the first flow_run of a boot has LOADed the card into
 * flow_board, the flag is set, so the returns of GAME OVERs (which re-enter
 * flow_run without a power-off) never LOAD again (they must not clobber a
 * board the current boot already improves). A fresh boot's backup RAM holds
 * 0x00 (MAME), which reads "not done": the entry LOADs. On MVS the flag
 * stays meaningless (bios_mvs_flag == 0x80: no card). */
static u8 _backup_ram flow_card_loaded;
#define FLOW_CARD_LOADED_MAGIC 0x5c

/* the entry's "which page the title opens on" byte: flow_open_page is a
 * _backup_ram byte that outlives the entry, so it must NOT be zeroed by
 * flow_run itself (that would undo the byte the GAME OVER return just
 * set). flow_run instead reads it into this plain static (.bss, zeroed on
 * every entry), clears the backup byte, and opens the title on that page
 * (0 for a fresh boot, 1..3 for a returned game's board page; M6 Task 7 /
 * high-score boards Task B3). */
static u8 open_page;

/* the title's state: the fix text's blink/counters. Attract Task A2 draws
 * the game's own scene behind the title: the dome is at the fresh game's
 * view 0, so the old title_dome spin is gone. */
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

/* M6 Task 6 / high-score boards Task B3: the title's TITLE_PAGES pages
 * (title_page 0..10: page 0 the dome, 1..3 the EASY/NORMAL/HARD boards,
 * 4..10 the old info pages) and the frames spent on the current page
 * (title_t, u16: 0..294 — one page turn every 295 title frames, the
 * Vectrex's 250 x 59/50). Plain statics: .bss is zeroed on every BIOS
 * entry, so without Task 7 every entry opens on page 0, t 0. Task 7 / B3
 * open on the returned game's level's board page (1..3) when the GAME OVER
 * return set flow_open_page, and the title's B press jumps to page 0. The
 * probe reads both from RAM (nm gives their addresses). */
static u8 title_page;
static u16 title_t;

/* the title's shown fix rows: "call title_rows only when its visible
 * inputs change" (Task 6): the page, the level, the prompt phase (the
 * prompt's t & 64 alternation), the credits value, or the boards' top
 * entries. When one changes, title_rows rebuilds all 30 rows
 * and only the changed rows are written to the fix layer (as hud.c does);
 * on a frame with no change nothing is drawn. Attract Task A1: every text
 * line's cap row (the row below it) is written with TITLE2_CAP_BASE tiles.
 * 0xff: never drawn — the first title frame draws everything. */
static u8 title_t_shown_page = 0xff;
static u8 title_t_shown_phase;       /* the shown title_prompt_b */
/* M6 Task 7: the title's shown fix rows' shown level (flow_level_get) —
 * the "write only on visible change" invariant extends to the level. */
static u8 title_t_shown_level = 0xff;
static u8 title_t_shown_credits = 0xff;
/* high-score boards Task B2: the shown rows' top entries (each level's
 * board entry 0's score10). A plain static: .bss is zeroed on every entry,
 * so the first title frame of an entry (title_t_shown_page 0xff) redraws
 * anyway, and a GAME OVER's board_insert is visible the frame the returned
 * title first draws its page 1 (the shown copy is from the entry's first
 * draw, before any update this entry could make). */
static u32 title_t_shown_best[BOARD_NLEVELS];

/* high-score boards Task B6: the returned title's new-entry blink. When the
 * END path set flow_open_rank, the title opens on that board page and hides
 * the new entry's row (and its cap) every other 16 title frames, exactly
 * the mockup's (t >> 4) & 1. title_blink_text keeps the row's drawn text so
 * showing it again needs no 30-row rebuild (and cannot clobber the sound
 * confirmation's pending rows). title_blink_active clears when the page
 * turns away: only the first page after END blinks. */
static u8 title_blink_page;         /* 1..3, or 0 when there is none */
static u8 title_blink_rank;         /* 0..4 */
static u8 title_blink_active;
static u8 title_blink_hidden;       /* the last staged blink phase */
static char title_blink_text[2][TITLE_COLS + 1];

/* Attract Task A2: the title's fix writes are staged by title_stage() and
 * written by title_commit() in the frame's vblank block. Each dirty row
 * carries its tile base and its 40-character text; row 28's countdown is
 * staged separately so it can be written last (it owns cols 19..20). */
static u8 title_dirty[TITLE_ROWS];
static u16 title_dirty_base[TITLE_ROWS];
static char title_pending[TITLE_ROWS][TITLE_COLS + 1];
/* P1: the column span each pending row's text occupies, and the span the
 * fix layer currently shows. title_commit() writes the union of the old and
 * new spans, so a page turn writes only the cells that can carry text. */
static u8 title_pending_col[TITLE_ROWS];
static u8 title_pending_len[TITLE_ROWS];
static u8 title_shown_col[TITLE_ROWS];
static u8 title_shown_len[TITLE_ROWS];
static char title_countdown_pending[3];
static u8 title_countdown_dirty;
static u8 title_countdown_on;        /* the timer is a live BCD 00..99 */

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

/* Attract D1: the AES demo-sound confirmation. A title D press sets the
 * frame count to 120 and the state it confirms; title_stage() writes "DEMO
 * SOUND ON"/"DEMO SOUND OFF" over page 0's prompt row 21 (and its cap row
 * 22) until the count runs out, then the page's own rows return. shown is
 * 0 (none), 1 (ON) or 2 (OFF), so a second press inside the 120 frames
 * updates the message instead of being masked by it. */
#define TITLE_SOUND_MSG_FRAMES 120
static u8 title_sound_msg_ticks;
static u8 title_sound_msg_on;       /* the setting the message shows */
static u8 title_sound_msg_shown;    /* 0 none, 1 ON, 2 OFF */

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
/* Task 18: the vpos right after props_commit, so the tear probe can state
 * the frame's start-to-commit-end. */
static volatile u16 work_commit_mark;

static void work_marks_init(void)
{
    work_marked = 0;
    work_min_mark = work_max_mark = work_start_mark = 0;
    work_commit_mark = 0;
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
 * pipeline boot-test (M7 Task 1, R1). On the title, at title frames 100,
 * 160, 220, 280, 340 and 460 the hook sends commands 4, 5, 6, 7, 8 and 9
 * (one per frame), and at title frame 400 it sends 6 and 8 in the SAME
 * frame — the two-sounds-in-one-frame proof, which needs the
 * acknowledgement wait (src/sound.c) before the second send. Every send is
 * recorded with the title frame it was sent on and the acknowledgement
 * result, in a RAM log the probe reads.
 *
 * The sends key on a hook-owned u16 title counter (sound_test_fc), NOT the
 * flow's u8 title_fc (the blink counter — it wraps at 255, and the sends
 * go up to frame 460). Each title_frame runs once per title frame, so the
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
    } else if (tf == 460) {
        sound_test_record(tf, SND_MOVE, sound_cmd(SND_MOVE));
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

/* high-score boards Task B2: each level's top entry score10 as a plain
 * u32[3] — NEVER flow_board.entry[level][0].score10 directly (a pointer to
 * a packed member): the 68000 faults a 32-bit read at an odd address, and
 * storing after board_insert made this a live path every GAME OVER and
 * every entry. The three-word copy costs nothing (title_rows runs only when
 * a visible input changed). */
static void flow_board_get(u32 best[3])
{
    u8 level;

    for (level = 0; level < BOARD_NLEVELS; level++)
        best[level] = flow_board.entry[level][0].score10;
}

/* high-score boards Task B2: the AES memory card. card_load_board /
 * card_save_board live in src/card.c, which owns the BIOS calls; here are
 * the two hooks:
 *
 *  - flow_card_load: at the FIRST flow_run entry of a boot (the
 *    _backup_ram flow_card_loaded flag says it was not done yet — on a
 *    fresh boot the backup RAM reads 0x00), LOAD the saved board into a
 *    temporary; if the load answers OK and board_valid passes, copy it
 *    into flow_board (this boot's board starts from the card). Any other
 *    answer keeps the reset board of this entry (an old 'ESRG' table is
 *    one of those: board_valid rejects its magic). Runs before the entry's
 *    own board_valid check's reset, in the order flow_run calls. Card
 *    calls are entry-time only (never per frame).
 *
 *  - flow_card_save: at GAME OVER when the game's qualifying score was
 *    inserted, SAVE the board; the FORMAT retry on 0x81 lives in card.c.
 *    Skips on MVS (no card there). Runs even when the entry's LOAD already
 *    copied the card — a game that improves on the loaded board must be
 *    saved back. */
static void flow_card_load(void)
{
    board_t tmp;

    if (bios_mvs_flag != 0)
        return;
    if (flow_card_loaded == FLOW_CARD_LOADED_MAGIC)
        return;
    flow_card_loaded = FLOW_CARD_LOADED_MAGIC;
    if (card_load_board(&tmp))
        flow_board = tmp;
}

static void flow_card_save(void)
{
    if (bios_mvs_flag != 0)
        return;
    card_save_board(&flow_board);
}

/* the title's visible-input change detector: the page, the level, the prompt phase
 * (the prompt's t & 64 alternation), the credits value and the boards' top
 * entries (high-score boards Task B2: page 0's row 9 and page 1's three rows
 * draw those, so a board change is a visible change). When none changed, the
 * fix layer already shows the right rows — nothing is written. */
static u8 title_visible_changed(u8 t_phase, u8 credits, const u32 best[3])
{
    u8 i;

    for (i = 0; i < BOARD_NLEVELS; i++)
        if (title_t_shown_best[i] != best[i])
            return 1;
    return title_t_shown_page != title_page
        || title_t_shown_level != flow_level_get()
        || title_t_shown_phase != t_phase
        || title_t_shown_credits != credits;
}

/* the S ROM tile base a title page uses on one row: 0 for page 0's logo
 * rows (the row's characters are the tile codes), TITLE2_ROW_BASE for a
 * text line, TITLE2_CAP_BASE for its cap row, and TITLE_ROW_NONE for a row
 * the page leaves blank. Pages 4..10 put a line on every even row 6..24
 * and its caps on the odd row below (7..25); page 0 has the logo 2..5, the
 * level 7/8, the best 9/10 and the prompt 21/22 (attract Task A1). Pages
 * 1..3 (the boards, Task B3) put "HIGH SCORES" on row 6 and the level on
 * row 8 (each cap one row below), then the five entries on rows 11..19
 * step 2 with their caps on rows 12..20 (every odd row is an entry, every
 * even row from 12 to 20 its cap). */
#define TITLE_ROW_NONE 0xffff

static u16 title_row_base(u8 page, u8 row)
{
    if (page == 0) {
        if (row >= LOGO_ROW && row < LOGO_ROW + LOGO_ROWS)
            return 0;
        if (row == TITLE_LEVEL_ROW || row == TITLE_BEST_ROW
            || row == TITLE_VER_ROW || row == TITLE_PRESS_ROW)
            return fix_thick_row_base();
        if (row == TITLE_LEVEL_ROW + 1 || row == TITLE_BEST_ROW + 1
            || row == TITLE_VER_ROW + 1 || row == TITLE_PRESS_ROW + 1)
            return fix_thick_cap_base();
        return TITLE_ROW_NONE;
    }
    if (page <= 3) {
        if (row == TITLE_BOARD_HEADER_ROW || row == TITLE_BOARD_LEVEL_ROW)
            return fix_thick_row_base();
        if (row == TITLE_BOARD_HEADER_ROW + 1
            || row == TITLE_BOARD_LEVEL_ROW + 1)
            return fix_thick_cap_base();
        if (row >= TITLE_BOARD_FIRST_ROW
            && row < TITLE_BOARD_FIRST_ROW
                         + TITLE_BOARD_ROWS * TITLE_BOARD_STEP)
            return ((row - TITLE_BOARD_FIRST_ROW) & 1)
                ? fix_thick_cap_base() : fix_thick_row_base();
        return TITLE_ROW_NONE;
    }
    if (row >= 6 && row <= 24 && ((row - 6) & 1) == 0)
        return fix_thick_row_base();
    if (row >= 7 && row <= 25 && ((row - 7) & 1) == 0)
        return fix_thick_cap_base();
    return TITLE_ROW_NONE;
}

/* the fix rows a title page uses (see title_row_base) */
static u8 title_row_used(u8 page, u8 row)
{
    return (u8)(title_row_base(page, row) != TITLE_ROW_NONE);
}

/* Attract Task A2: stage the title's fix rows instead of writing them in
 * title_frame. The visible-change decision and the rows written are exactly
 * the pre-A2 incremental writer's: all rows when the page/level/credits/board
 * table changed, else page 0's prompt row and its cap row when the prompt
 * phase flipped. Only dirty rows are kept, so title_commit() writes only
 * what changed. Row 28 is never staged here; the MVS countdown has its own
 * staging below and is committed last. */
static void title_stage_rows(u8 credits, const board_t *board)
{
    u8 i, all;

    /* The caller only reaches this when a visible input changed (the page,
     * the level, the prompt phase, the credits value, or the boards' top
     * entries). title_rows' output differs from the previous frame's in:
     *   - every row used by the new or the shown page, when the page, the
     *     level, the credits value or the board top entries changed;
     *   - page 0's prompt row and its cap row, when the prompt phase
     *     flipped;
     *   - nothing on pages 4..10 (none of their lines reads t), and nothing
     *     on the board pages 1..3 (their five entries do not read t).
     * A row only the shown page used is blank on the new page, drawn with
     * base 0 (ASCII space). */
    all = (title_page != title_t_shown_page
           || flow_level_get() != title_t_shown_level
           || credits != title_t_shown_credits);

    if (all) {
        title_rows_spans(title_page, flow_level_get(), title_t, board, credits,
                         title_pending, title_pending_col, title_pending_len);
        for (i = TITLE_TOP_ROW; i <= TITLE_BOTTOM_ROW; i++)
            if (i != TITLE_COUNTDOWN_ROW
                && (title_row_used(title_page, i)
                    || (title_t_shown_page < TITLE_PAGES
                        && title_row_used(title_t_shown_page, i)))) {
                u16 base = title_row_base(title_page, i);

                if (base == TITLE_ROW_NONE)
                    base = 0;       /* blank on the new page (ASCII space) */
                title_dirty[i] = 1;
                title_dirty_base[i] = base;
            }
    } else if (title_page == 0) {
        /* only page 0's prompt reads t, so a phase flip on the other pages
         * changes no row: do not rebuild the 30 rows (the demo's frame
         * budget; the board defaults make the rebuild costly). */
        title_rows_spans(title_page, flow_level_get(), title_t, board, credits,
                         title_pending, title_pending_col, title_pending_len);
        title_dirty[TITLE_PRESS_ROW] = 1;
        title_dirty_base[TITLE_PRESS_ROW] = fix_thick_row_base();
        title_dirty[TITLE_PRESS_ROW + 1] = 1;
        title_dirty_base[TITLE_PRESS_ROW + 1] = fix_thick_cap_base();
    } else if (title_sound_msg_shown) {
        /* the AES confirmation is ending on this frame: rebuild the page's
         * rows so the commit's restore of rows 21/22 has the page's text,
         * not the message's. The message-end path in title_stage marks
         * those rows dirty after this. */
        title_rows_spans(title_page, flow_level_get(), title_t, board, credits,
                         title_pending, title_pending_col, title_pending_len);
    }
}

/* the MVS countdown's two BCD digits, staged separately (row 28, cols
 * 19..20). Only after a coin (flow_entry 1). The BIOS compulsion timer is
 * BCD seconds; its high nibble then its low nibble ('0' + n) go in cols 19
 * and 20 — called 0x30 -> "30" through 0x00 -> "00". Rewritten only when
 * the value changes; title_timer_shown's 0xff initialiser lives in .data,
 * which the runtime re-copies on every entry, so the first row-28 draw of
 * an entry always happens. */
static void title_stage_countdown(void)
{
    u8 t;

    if (flow_entry != 1) {
        title_countdown_on = 0;
        return;
    }
    t = (u8)(bios_compulsion_timer & 0xff);
    /* a live countdown is BCD 00..99; the pre-coin BIOS value is not */
    title_countdown_on = (u8)(t <= 0x99 && (t >> 4) <= 9 && (t & 0x0f) <= 9);
    if (t != title_timer_shown) {
        title_countdown_pending[0] = (char)('0' + (t >> 4));
        title_countdown_pending[1] = (char)('0' + (t & 0x0f));
        title_countdown_pending[2] = 0;
        title_countdown_dirty = 1;
        title_timer_shown = t;
    }
}

/* Attract D1: the confirmation's two rows, "DEMO SOUND ON" / "DEMO SOUND
 * OFF" centred on row 21 (the prompt row) and copied to its cap row 22 (the
 * cap tiles draw the glyph's bottom outline row, as title_rows does). */
static void title_sound_msg_rows(char rows[TITLE_ROWS][TITLE_COLS + 1],
                                 u8 on)
{
    const char *m = on ? "DEMO SOUND ON" : "DEMO SOUND OFF";
    u8 n = 0, col, i;

    while (m[n])
        n++;
    col = (u8)((TITLE_COLS - n) / 2);
    for (i = 0; i < TITLE_COLS; i++)
        rows[TITLE_PRESS_ROW][i] = ' ';
    rows[TITLE_PRESS_ROW][TITLE_COLS] = 0;
    for (i = 0; i < n; i++)
        rows[TITLE_PRESS_ROW][col + i] = m[i];
    for (i = 0; i <= TITLE_COLS; i++)
        rows[TITLE_PRESS_ROW + 1][i] = rows[TITLE_PRESS_ROW][i];
    /* P1: the confirmation's own span (the page's rows are wider/narrower
     * than the message, so the commit writes the union of the two). */
    /* B4: the cell after the last character holds its outline spill. */
    title_pending_col[TITLE_PRESS_ROW] = col;
    title_pending_len[TITLE_PRESS_ROW] =
        (u8)(n + ((col + n < TITLE_COLS) ? 1 : 0));
    title_pending_col[TITLE_PRESS_ROW + 1] = col;
    title_pending_len[TITLE_PRESS_ROW + 1] =
        (u8)(n + ((col + n < TITLE_COLS) ? 1 : 0));
}

/* the page's fix rows: title_rows only when a visible input changed (the
 * page, the level, the prompt phase, the credits value, or the best
 * table), and only the changed rows are staged. Every title frame, and once
 * at the entry before the first title frame. Attract D1: while the AES
 * confirmation is up, row 21/22 carry the message instead of the page's
 * rows (a page change in that window still writes the rest of the page);
 * when it ends, the page's own rows 21/22 are put back. */
static void title_stage(void)
{
    u8 s, credits, phase, want, changed;
    u32 best[BOARD_NLEVELS];

    credits = title_credits();
    phase = title_prompt_b(title_t);
    want = (u8)(title_sound_msg_ticks
                ? (title_sound_msg_on ? 1 : 2) : 0);
    /* high-score boards Task B2/B3: the board can change only when the cart
     * enters (a card load or a backup-RAM reset) — the GAME OVER insert
     * happens before the return's entry. The first title frame of an entry
     * reads it (title_t_shown_page is 0xff in .data, re-copied by the
     * runtime); every later title frame reuses the shown copy, so the
     * per-frame path does not read the backup-RAM board (the demo's frame
     * budget). A title frame can never see a board change while it is up:
     * the only writer is the GAME OVER path, which leaves the title for a
     * game first. */
    if (title_t_shown_page >= TITLE_PAGES) {
        flow_board_get(best);
    } else {
        for (s = 0; s < BOARD_NLEVELS; s++)
            best[s] = title_t_shown_best[s];
    }

    changed = title_visible_changed(phase, credits, best);
    if (changed || want != title_sound_msg_shown) {
        title_stage_rows(credits, &flow_board);
        if (want) {
            /* the confirmation wins row 21/22 over the page's rows */
            title_sound_msg_rows(title_pending, (u8)(want == 1));
            title_dirty[TITLE_PRESS_ROW] = 1;
            title_dirty_base[TITLE_PRESS_ROW] = fix_thick_row_base();
            title_dirty[TITLE_PRESS_ROW + 1] = 1;
            title_dirty_base[TITLE_PRESS_ROW + 1] = fix_thick_cap_base();
        } else if (title_sound_msg_shown) {
            /* the confirmation ended: put the page's own rows back */
            title_dirty[TITLE_PRESS_ROW] = 1;
            title_dirty_base[TITLE_PRESS_ROW] =
                title_row_base(title_page, TITLE_PRESS_ROW);
            title_dirty[TITLE_PRESS_ROW + 1] = 1;
            title_dirty_base[TITLE_PRESS_ROW + 1] =
                title_row_base(title_page, TITLE_PRESS_ROW + 1);
        }
        title_sound_msg_shown = want;
        if (changed) {
            title_t_shown_page = title_page;
            title_t_shown_level = flow_level_get();
            title_t_shown_phase = phase;
            title_t_shown_credits = credits;
            for (s = 0; s < BOARD_NLEVELS; s++)
                title_t_shown_best[s] = best[s];
        }
    }
    title_stage_countdown();
}

/* Attract Task A2: the title's fix writes, in the frame's vblank block.
 * Only rows staged by title_stage() are written; the countdown is last so
 * it wins the two cells it shares with the HUD's score (row 28 cols 19..20,
 * score "0" at col 19 — the countdown owns them after a coin).
 * P1: a row is written from the left edge of the old row's span to the
 * right edge of the new one, so a page turn writes only the cells that can
 * carry text, and the cells the old page leaves behind are blanked. */
static void title_commit(void)
{
    u8 i;

    for (i = TITLE_TOP_ROW; i <= TITLE_BOTTOM_ROW; i++)
        if (title_dirty[i]) {
            u8 a = TITLE_COLS, b = 0;
            u8 c0 = title_shown_col[i], l0 = title_shown_len[i];
            u8 c1 = title_pending_col[i], l1 = title_pending_len[i];

            if (l0) {
                if (c0 < a)
                    a = c0;
                if ((u8)(c0 + l0) > b)
                    b = (u8)(c0 + l0);
            }
            if (l1) {
                if (c1 < a)
                    a = c1;
                if ((u8)(c1 + l1) > b)
                    b = (u8)(c1 + l1);
            }
            if (b > a)
                fix_span(i, title_dirty_base[i], title_pending[i],
                               a, (u8)(b - a));
            title_shown_col[i] = c1;
            title_shown_len[i] = l1;
            title_dirty[i] = 0;
        }
    /* Attract Task A3: the demo's HUD row 28 was written just before this
     * commit, so a live countdown must rewrite its two cells every frame,
     * not only when the timer changes, or the demo's score clobbers them. */
    if (title_countdown_dirty || title_countdown_on) {
        fix_text(TITLE_COUNTDOWN_COL, TITLE_COUNTDOWN_ROW, PAL_HUD,
                 title_countdown_pending);
        title_countdown_dirty = 0;
    }
}

/* high-score boards Task B6: the entry screen. The six fix rows use the
 * same thick title font as the title (Task B4): row 2 NEW HIGH SCORE, row
 * 4 "<LEVEL>  <RANK>  <SCORE>", row 6 the initials, each text row with its
 * cap row below (3, 5, 7), the mockup's layout. The commit writes the whole
 * 40-column rows, so the old GAME OVER row 7 (the initials' cap) is
 * cleared. The next initial's slot blinks every 16 entry frames, the
 * mockup's (t >> 4) & 1. */
static const char *const entry_level_name[LEVELS] = {
    "EASY", "NORMAL", "HARD"
};
static const char *const entry_rank_name[BOARD_NENTRIES] = {
    "1ST", "2ND", "3RD", "4TH", "5TH"
};

static void entry_centre(const char *s, char *row)
{
    u8 n = 0, col, i;

    while (s[n])
        n++;
    for (i = 0; i < TITLE_COLS; i++)
        row[i] = ' ';
    row[TITLE_COLS] = 0;
    col = (u8)((TITLE_COLS - n) / 2);
    for (i = 0; i < n; i++)
        row[col + i] = s[i];
}

/* the displayed score (score10 x 10) as digits; entry-time only, so the
 * 68000's u32 divide calls (libgcc) are allowed here. */
static void entry_score_text(char *out, u32 score10)
{
    char tmp[12];
    u32 v = score10 * 10;
    u8 n = 0, i;

    if (v == 0)
        tmp[n++] = '0';
    while (v) {
        tmp[n++] = (char)('0' + (u8)(v % 10));
        v /= 10;
    }
    for (i = 0; i < n; i++)
        out[i] = tmp[n - 1 - i];
    out[n] = 0;
}

/* row 6: the entered initials and the next slot's blink (the mockup's
 * "A B _", a space between each pair). K2: while a letter is flying its
 * cell is blank and the blinking "_" is not drawn, so the row shows
 * ninit - 1 letters; once it lands the row shows all ninit again. */
static void entry_build_initials(void)
{
    char s[6];
    u8 n = 0, i, shown, flying;

    flying = (u8)(entry_state.fly_t > 0);
    shown = (u8)(entry_state.ninit - flying);
    for (i = 0; i < ENTRY_INIT_MAX; i++) {
        if (i < shown)
            s[n++] = (char)entry_state.init[i];
        else if (!flying && i == entry_state.ninit)
            s[n++] = ((entry_fc >> 4) & 1) ? '_' : ' ';
        else
            s[n++] = ' ';
        if (i < ENTRY_INIT_MAX - 1)
            s[n++] = ' ';
    }
    s[n] = 0;
    entry_centre(s, entry_text[4]);
    memcpy(entry_text[5], entry_text[4], TITLE_COLS + 1);
}

/* build rows 2..7 from the GAME OVER frame's level/rank/score and the empty
 * initials; the caller then stages every row. */
static void entry_text_begin(void)
{
    char line[24], score[12];
    const char *lv = entry_level_name[(rules.level < LEVELS)
                                      ? rules.level : LEVEL_NORMAL];
    const char *rk = entry_rank_name[(entry_rank < BOARD_NENTRIES)
                                     ? entry_rank : BOARD_NENTRIES - 1];
    u8 p = 0, i;

    entry_centre("NEW HIGH SCORE", entry_text[0]);
    memcpy(entry_text[1], entry_text[0], TITLE_COLS + 1);
    while (*lv)
        line[p++] = *lv++;
    line[p++] = ' ';
    line[p++] = ' ';
    while (*rk)
        line[p++] = *rk++;
    line[p++] = ' ';
    line[p++] = ' ';
    entry_score_text(score, entry_score10);
    for (i = 0; score[i]; i++)
        line[p++] = score[i];
    line[p] = 0;
    entry_centre(line, entry_text[2]);
    memcpy(entry_text[3], entry_text[2], TITLE_COLS + 1);
    entry_build_initials();
    /* Task G1: row 8 was GAME OVER's cap row; the entry owns rows 2..7 and
     * must blank row 8 from its first committed frame. */
    for (i = 0; i < TITLE_COLS; i++)
        entry_text[6][i] = ' ';
    entry_text[6][TITLE_COLS] = 0;
    for (i = 0; i < 7; i++)
        entry_text_dirty[i] = 1;
}

/* write the entry screen's staged fix rows in vblank (full 40-column rows,
 * as the title font's cap spill needs). */
static void entry_text_commit(void)
{
    u8 i;

    for (i = 0; i < 7; i++)
        if (entry_text_dirty[i]) {
            u16 base;

            if (i == 6)
                base = 0;               /* row 8: the GAME OVER cap's blank */
            else
                base = (i & 1) ? fix_thick_cap_base() : fix_thick_row_base();
            fix_span((u8)(2 + i), base, entry_text[i], 0, TITLE_COLS);
            entry_text_dirty[i] = 0;
        }
}

/* high-score boards Task B6: capture the returned page's new-entry row (and
 * its cap) from the rows title_stage() just built, so the blink can put the
 * text back without rebuilding 30 rows. */
static void title_blink_capture(void)
{
    u8 row;

    if (!title_blink_active)
        return;
    row = (u8)(TITLE_BOARD_FIRST_ROW
               + title_blink_rank * TITLE_BOARD_STEP);
    memcpy(title_blink_text[0], title_pending[row], TITLE_COLS + 1);
    memcpy(title_blink_text[1], title_pending[row + 1], TITLE_COLS + 1);
    title_blink_hidden = 0;
}

/* stage the new entry's row hidden/shown every other 16 title frames. The
 * span is the row's text span; blanking its cells with base 0 (ASCII
 * space) clears it, and the copied text puts it back. */
static void title_stage_blink(void)
{
    u8 row, hidden, i;

    if (!title_blink_active || title_page != title_blink_page)
        return;
    hidden = (u8)((title_fc >> 4) & 1);
    if (hidden == title_blink_hidden)
        return;
    row = (u8)(TITLE_BOARD_FIRST_ROW
               + title_blink_rank * TITLE_BOARD_STEP);
    if (hidden) {
        for (i = 0; i < TITLE_COLS; i++)
            title_pending[row][i] = ' ';
        title_pending[row][TITLE_COLS] = 0;
        memcpy(title_pending[row + 1], title_pending[row], TITLE_COLS + 1);
    } else {
        memcpy(title_pending[row], title_blink_text[0], TITLE_COLS + 1);
        memcpy(title_pending[row + 1], title_blink_text[1], TITLE_COLS + 1);
    }
    title_dirty[row] = 1;
    title_dirty_base[row] = hidden ? 0 : title_row_base(title_page, row);
    title_dirty[row + 1] = 1;
    title_dirty_base[row + 1] =
        hidden ? 0 : title_row_base(title_page, row + 1);
    title_blink_hidden = hidden;
}

/* one FLOW_ENTRY frame: the ring machine, the dome/scenery at its angle and
 * the ring sprites. The HUD is not touched (it stays as at GAME OVER), no
 * ship/missiles/radar are prepared, and the scene's staged groups are
 * committed in the loop's vblank block like the game's. */
static void entry_screen_frame(void)
{
    u8 a, v, old_ninit, old_hidden, old_flying, flying;

    old_ninit = entry_state.ninit;
    old_hidden = (u8)((entry_fc >> 4) & 1);
    old_flying = (u8)(entry_state.fly_t > 0);
    entry_fc++;
    entry_frame(&entry_state, bios_p1current, bios_p1change);
    /* the picker's sounds, after the machine: type/back/bell then the
     * tick, so a pick on the arrival frame sends both (type on channel 4,
     * tick on 3) and a held turn's tick never lands on the same channel as
     * that frame's type. */
    if (entry_state.sfx & ENTRY_SFX_TYPE)
        sound_cmd(SND_TYPE);
    if (entry_state.sfx & ENTRY_SFX_BACK)
        sound_cmd(SND_BACK);
    if (entry_state.sfx & ENTRY_SFX_BELL)
        sound_cmd(SND_BELL);
    if (entry_state.sfx & ENTRY_SFX_TICK)
        sound_cmd(SND_TICK);
    a = entry_dome_angle(&entry_state, entry_base_angle);
    ship.dome_angle = a;
    v = (u8)(a % 48);
    dome_collapse(&rules, v);
    if (v != game_view && collapse_state(&rules) != 2) {
        dome_show(v);
        game_view = v;
    }
    collapse_prepare(&rules, a);
    cracks_show(&rules, a);
    ground_frame(&rules);
    ground_prepare(a, (u8)dome_is_whole(&rules));
    props_prepare(a, (u8)dome_is_whole(&rules));
    ring_gfx_prepare(&entry_state, entry_fc);
    /* K2: the row shows ninit - (flying ? 1 : 0) letters; rebuild when that
     * shown count changes (ninit changed or the flight started/landed) and,
     * while not flying, when the next slot's blink toggles. */
    flying = (u8)(entry_state.fly_t > 0);
    if (old_ninit != entry_state.ninit || old_flying != flying
        || (!flying && old_hidden != (u8)((entry_fc >> 4) & 1))) {
        entry_build_initials();
        entry_text_dirty[4] = 1;
        entry_text_dirty[5] = 1;
    }
}

/* Attract Task A3: the demo runs on the normal cart and the FRAME_MARK
 * build. The test-only carts (SOUND_TEST, RADAR_TEST, GAMEOVER_DRAW_TEST,
 * CRACK_TEST) keep the pre-A3 title scene: their hooks assume the title is
 * a fixed fresh game and would corrupt or be corrupted by a running demo.
 * A4 replaces this with the MVS DEMO SOUND DIP's gate. */
#if defined(SOUND_TEST) || defined(GAMEOVER_DRAW_TEST) || defined(RADAR_TEST) \
    || defined(CRACK_TEST) || defined(STATIC_TITLE)
#define DEMO_TITLE 0
#else
#define DEMO_TITLE 1
#endif

#if defined(FRAME_MARK)
/* the LSPC line counter (0..263, with 256..263 read as -8..-1), used by the
 * FRAME_MARK build's work marks. Not compiled into the other carts. */
static u16 lspc_vpos(void)
{
    return (u16)(((*REG_LSPCMODE >> 7) & 0x1FF) - 0x100);
}
#endif

static void game_frame_in(u8 cur, u8 cur_chg, u8 count); /* below: the frame body */

#if DEMO_TITLE
/* restart the demo: the script to frame 0 and the game state to a fresh
 * NORMAL game seeded DEMO_SEED (src/demo.c), plus the drawing/sound state
 * words the game path owns (the dome view and the scuttle/pip state). */
static void demo_begin(void)
{
    memset(&game_sound_state, 0, sizeof game_sound_state);
    game_view = 255;
    demo_restart();
    /* the demo's ship is reset to the start cell (demo_restart's
     * ship_reset): a restart must start at REST, not the pose the previous
     * cycle ended in (Review Focus 3's rule, applied to the demo). */
    ship_gfx_anim_reset();
}
#endif

/* the per-frame title body */
static void title_frame(void)
{
    u8 lvl = flow_level_get();
    u8 restart_demo = 0;

    title_fc++;
    title_seed_t++;
    title_t++;
    if (title_t >= TITLE_PAGE_FRAMES) {  /* one page turn every 295 title
                                          * frames (the Vectrex's 250 x
                                          * 59/50) */
        title_t = 0;
        if (++title_page >= TITLE_PAGES)
            title_page = 0;
        /* the cycle wrapped: page 0 begins, so the demo restarts */
        if (title_page == 0)
            restart_demo = 1;
    }
    if ((bios_p1change & CNT_C) && title_t != 0) {   /* C turns the page
                                          * on the spot; the frame that just
                                          * auto-turned (title_t 0, the
                                          * page already advanced) does not
                                          * double-turn */
        title_t = 0;
        if (++title_page >= TITLE_PAGES)
            title_page = 0;
        /* a C wrap to page 0 restarts the demo as the timer's wrap does:
         * the script is one 11-page cycle long, so without the restart it
         * ran out mid-cycle and the demo's ship froze */
        if (title_page == 0)
            restart_demo = 1;
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
            /* a B press restarts the demo (the design's "B pressed during
             * the demo -> the level changes, page 0, the demo restarts") */
            restart_demo = 1;
        }
    }
    /* Attract D1: on AES, a D press on any title page toggles the demo
     * sound and shows the confirmation for 120 frames. bios_p1change is the
     * press edge, so holding D does not flicker the setting; on MVS the
     * operator's DIP decides and D does nothing. START (the flow's Start
     * hook) and B/C keep working while the confirmation shows. */
    if (bios_mvs_flag == 0 && (bios_p1change & CNT_D)) {
        softdip_demo_sound_toggle();
        title_sound_msg_on = softdip_demo_sound();
        title_sound_msg_ticks = TITLE_SOUND_MSG_FRAMES;
    }
    /* high-score boards Task B6: the new entry's blink is for the first
     * page after END only; a page turn (or B's jump to page 0) ends it. */
    if (title_blink_active && title_page != title_blink_page)
        title_blink_active = 0;
#if !DEMO_TITLE
    (void)restart_demo;   /* the test carts compile the demo out */
#endif
#if DEMO_TITLE
    if (restart_demo)
        demo_begin();
#endif
    /* Attract Task A2: the title stands over the game's own scene. A3: the
     * scene is the demo's, advanced one frame below. title_stage() stages
     * the fix rows for the next vblank; the demo's game frame stages the
     * scene's own commits for it too. Attract D1: the confirmation's 120
     * frames are counted after staging, so the message stays on the fix
     * layer for 120 frames and the prompt is staged on the next one. */
    title_stage();
    title_stage_blink();
    if (title_sound_msg_ticks)
        title_sound_msg_ticks--;

#ifdef SOUND_TEST
    sound_test_frame();      /* the M7 Task 1 test sends, on title frames */
#endif

#if DEMO_TITLE
    /* Attract Task A3: run the real game frame with the demo's input in
     * place of the BIOS's. The game-session counter must stay 0 on the
     * title (every boot-test's page/Start gate keys on it): count 0 takes
     * the hud_demo_stage path, which never touches hud_framecnt or
     * hud_dbg_events. The demo has its own frame counter (demo_dbg_fc). */
    {
        u8 cur, pressed;

        demo_input(&cur, &pressed);
        /* count 0: the demo draws the HUD's changed rows but does not
         * advance hud_framecnt / hud_dbg_events — the title must be
         * indistinguishable from a title frame even to a probe that
         * samples mid-frame. */
        game_frame_in(cur, pressed, 0);
        demo_hash_frame();          /* the per-frame proof's rolling hash */
    }
#endif
}

/* enter FLOW_GAME after a Start: clear the fix layer, run hud_init (which
 * draws the HUD's constant rows), reset the game's state, and reset the
 * game-session frame counter so the first game frame is 1. */
static void game_begin(void)
{
    go_suppress_a = 0;
    backdrop(COL_SKY);           /* in play the backdrop is the sky (the
                                  * stars are retired) */
    hud_clear();                 /* blank the title rows + reset the HUD state */
    hud_init();                  /* the HUD's constant rows (labels, title, help) */
    /* the title's hide zeroed every ship and radar slot's SCB3, including
     * the words only these inits write: the ship's sticky follower (the
     * "only the left half" bug) and the radar frame's 4 slots. Rewrite
     * them before the first game frame. mis_gfx_hide clears the missiles'
     * memo too (the title's hide already zeroed the slots), so the first
     * game frame's prepare writes full columns. */
    ship_gfx_init();
    radar_gfx_init();
    mis_gfx_hide();
    /* dome-scenery Task 5: the ground block and its palette are (re)written
     * once at every game start — the title hid the block and the palette
     * is not the game's. Task 19: it is shown at the reset ship's angle,
     * with every ripple bank whole. */
    ship_reset(&ship);
    /* Attract Task A3: the demo may have turned the dome; force the new
     * game's first game frame to draw the reset ship's view. R1: the sound
     * state starts afresh too (the scuttle's spin period and the pip's
     * counter). */
    game_view = 255;
    memset(&game_sound_state, 0, sizeof game_sound_state);
    ground_show(ship.dome_angle);
    mountains_show(ship.dome_angle); /* dome-scenery Task 6: the mountains
                                      * are shown with the ground, already
                                      * scrolled to the reset ship's angle
                                      * (the first game frame's
                                      * mountains_frame keeps it in step) */
    band_show(ship.dome_angle);      /* dome-scenery Task 17: the band is
                                      * shown with the mountains, already
                                      * scrolled to the reset ship's angle
                                      * (the first game frame's band_frame
                                      * keeps it in step) */
    console_show();                  /* dome-scenery Task 7: the panel is
                                      * written ONCE here (nothing per frame) */
    props_show(ship.dome_angle);     /* dome-scenery Task 12: the props are
                                      * shown with the ground, at the reset
                                      * ship's angle; Task P2's table is
                                      * already in ROM */
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

/* M7 Task 2 / R1: the frame's sound commands, after the frame's logic.
 * The choice lives in src/sound.h's sound_frame_cmds so the host test drives
 * the same code beside tests/sound_model.py. The Vectrex plays jump, fire,
 * hit and crack (e-srg.c sound_update), the scuttle for the spider, and the
 * pip (lock_update) at the moments the game events happen; here the events
 * (ship.jumped, mis.sfx, the ship's step/spin, the collapse's phase, the
 * radar's lock) become the driver commands in the Vectrex's order: jump,
 * fire, then the missiles — a hit and a crack in the same frame send the
 * crack (break_tile zeroes snd_hit; e-srg.c's `if (snd_hit && snd_crack) ...
 * 0`), and a jump and a fire cannot start in the same frame (fire waits
 * for the ship to rest). The scuttle is sent on a walk's first frame and on
 * a peak spin's first frame and every SHIP_MOVE_FRAMES after; it never
 * takes channel 0 from a jump. The collapse's rumble beats alternate the
 * two explosions: HIT at the death (frame 0), CRACK at 9, HIT at 18, CRACK
 * at 27, HIT at 36. The title sends none (title_frame has no sound step).
 * Every command goes through the same acknowledged sound_cmd, so two
 * sounds in one frame both play. */
static void game_sound(u8 died)
{
    sound_frame_t fr;
    u8 cmds[SOUND_CMDS_MAX];
    u8 n, i;

    fr.jumped = ship.jumped;
    fr.move_left = ship.move_left;
    fr.mlen = ship.mlen;
    fr.spinning = ship.spinning;
    fr.sfx = mis.sfx;
    fr.died = died;
    fr.alive = (u8)(!rules.dead_t && !rules.game_over);
    fr.dead_t = rules.dead_t;
    fr.dome_dead = rules.dome_dead;
    fr.collapse_frac = collapse_frac(&rules);
    fr.locked = radar.locked;
    n = sound_frame_cmds(&game_sound_state, &fr, cmds);

#ifdef SOUND_TEST
#define SND_CMD(c) sound_game_cmd(c)
#else
#define SND_CMD(c) sound_cmd(c)
#endif
    for (i = 0; i < n; i++)
        SND_CMD(cmds[i]);
#undef SND_CMD
}

/* the current game loop body, one frame (rules, ship, missiles, cracks,
 * radar, HUD — the pre-M6 main loop, with the test hooks). `cur` / `cur_chg`
 * are the BIOS current and change bytes; the game path passes bios_p1*, the
 * title's demo passes the script's. */
static void game_frame_in(u8 cur, u8 cur_chg, u8 count)
{
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
    /* the MVS player's A is masked (no free fire); the demo is not a
     * player and its recorded script must play identically on AES and
     * MVS, so count 0 keeps the A edge. */
    pressed = cur_chg;
    if (count && bios_mvs_flag == 0x80)
        pressed &= (u8)~CNT_A;
    e = rules_begin(&rules, &ship, &mis, pressed);
    if (!e)                             /* the game play turn */
        ship_frame(&ship, cur, cur_chg);
    mis_update(&mis, &ship, &rules, cur_chg, e);
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
    if (count)
        hud_frame(&rules, &mis);
    else
        hud_demo_stage(&rules, &mis);
    v = (u8)(ship.dome_angle % 48);
    dome_collapse(&rules, v);
    if (v != game_view && collapse_state(&rules) != 2) {
        dome_show(v);
        game_view = v;
    }
    collapse_prepare(&rules, ship.dome_angle); /* the collapse redo's Task C2: stage the
                                      * fireball's words (previous frame's g)
                                      * into RAM; collapse_commit writes them
                                      * in the next vblank */
    if (!rules.dead_t && !rules.game_over)
        ship_gfx_prepare(&ship, (u8)(mis.sfx & SFX_FIRE));
    else
        ship_gfx_hide();
    mis_gfx_prepare(&mis, ship.dome_angle);  /* dome-scenery Task 18b: stage
                                              * the missile/explosion words
                                              * into RAM; the commit writes
                                              * them in the next vblank */
    cracks_show(&rules, ship.dome_angle);
    ground_frame(&rules);            /* dome-scenery Task 5: the bank-8
                                      * whole/gone marker, written directly
                                      * when it changes (the props/ground
                                      * probes read the current state) */
    ground_prepare(ship.dome_angle, (u8)dome_is_whole(&rules));
                                     /* dome-scenery Task 19: stage the
                                      * ripple banks whose rotation (or the
                                      * whole/gone state) changed into RAM;
                                      * ground_commit writes them in the
                                      * next frame's vblank. The ripple
                                      * shows the previous frame's angle,
                                      * like the props after Task 18. */
    props_prepare(ship.dome_angle, (u8)dome_is_whole(&rules));
                                     /* dome-scenery Task 12/14/18: the props'
                                      * placement (SCB1 only when a slot's
                                      * picture changes) and their palette
                                      * variant: dark in the dome's shadow
                                      * only while the dome is drawn whole.
                                      * Prepared into RAM; props_commit
                                      * writes it in the next frame's
                                      * vblank. */
    radar_frame(&radar, &mis, &ship);
    radar_gfx_prepare(&radar);       /* dome-scenery Task 18b: stage the
                                      * sticks/headings/blink into RAM; the
                                      * commit writes them in the next vblank */
    /* Attract Task A4/D1: the title's demo (count 0) plays its effects only
     * when the demo-sound gate is open: the MVS "DEMO SOUND" soft DIP (OFF
     * by default), or the AES title D toggle (silent at power-on). A real
     * game (count 1) is never gated, so it still sounds with the gate shut. */
    if (count || softdip_demo_sound())
        game_sound(died);            /* M7 Task 2: the frame's sound commands */
}

/* the game path: the BIOS's own input bytes (the pre-A3 body, unchanged).
 * Task B6: a qualifying GAME OVER masks A from rules_begin until the entry
 * begins, so no A-restart interrupts the 118-frame text; a non-qualifying
 * window leaves go_suppress_a 0 and keeps today's A-restart. */
static void game_frame(void)
{
    u8 pressed = bios_p1change;

    if (go_suppress_a)
        pressed &= (u8)~CNT_A;
    game_frame_in(bios_p1current, pressed, 1);
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
    u8 open_rank;

#ifdef FRAME_MARK
    work_marks_init();
#endif
    flow_entry = entry;                 /* 0: main (attract boot); 1:
                                         * main_mvs_title (post-coin, MVS) */
    fix_thick_init();                   /* B4/G1: the thick font's tile offsets */
    /* high-score boards Task B6: hide the ring (the previous entry may have
     * left it up) and stage its palette banks; the entry screen re-stages
     * them for every phase. */
    ring_gfx_init();
    entry_qualifies = 0;
    entry_rank = BOARD_NENTRIES;
    entry_score10 = 0;
    entry_base_angle = 0;
    entry_fc = 0;
    gameover_shown = 0;
    go_suppress_a = 0;
    /* dome-scenery Task 4: the title keeps its black backdrop. main.c's
     * palettes_init already set it black at boot; set it on every entry
     * too, so a GAME OVER return (and any BIOS entry) starts from black. */
    backdrop(COL_BLACK);
    /* M7 Task 1: the sound driver (M ROM) is reset once at entry, as the
     * ADPCM-A example's main() does. sound_reset goes through the same
     * acknowledged path as every other command, so a driver that never
     * answers is never silently swallowed — but it is the first command
     * sent and the FIFO is empty, so there is no ordering hazard. */
    sound_reset();
    /* high-score boards Task B2: the AES memory card. The first entry of a
     * boot LOADs the card's board into flow_board (flow_card_loaded says it
     * was done); this must run BEFORE the entry's board_valid reset below —
     * a loaded valid board is kept, a fresh/garbage one (or an old 'ESRG'
     * table) is reset here. */
    flow_card_load();
    /* high-score boards Task B2: every entry re-checks the backup-RAM
     * board: fresh/garbage backup RAM (a new MVS board, the AES's per-boot
     * RAM) is not valid (board_valid rejects the magic/sum, and an old
     * 'ESRG' best table's magic), so it is reset to the five default
     * entries here; a valid board is kept, which is the whole point (on MVS
     * it was saved by the BIOS on the last attract entry and survives
     * power-off). board.c's field accesses are byte/word safe at any
     * alignment. */
    if (!board_valid(&flow_board))
        board_reset(&flow_board);
    /* M6 Task 7 / high-score boards Task B3: the entry's title page — the
     * played level's board page (1..3) after a spent GAME OVER (the return
     * set flow_open_page), page 0 otherwise (a fresh boot, or a normal Start
     * return). The backup byte outlives the entry and must not be zeroed
     * here (that would undo the GAME OVER return's byte); read it into the
     * plain static, then clear it so the NEXT entry (after the next game)
     * opens on page 0 again. */
    open_page = flow_open_page;
    flow_open_page = 0;
    open_rank = flow_open_rank;
    flow_open_rank = 0;
    title_blink_active = 0;
    title_blink_page = 0;
    title_blink_rank = 0;
    if (open_page >= 1 && open_page <= 3
        && open_rank >= 1 && open_rank <= BOARD_NENTRIES) {
        title_blink_page = open_page;
        title_blink_rank = (u8)(open_rank - 1);
        title_blink_active = 1;
    }
    flow = FLOW_TITLE;
    title_fc = 0;
    title_seed_t = 0;
    title_page = (u8)(open_page < TITLE_PAGES ? open_page : 0);
    title_t = 0;
    gameover_wait = 0;
    /* Attract Task A3: a GAME OVER return reaches this entry with the
     * game's hud_framecnt still set; the title is not a game session, so
     * reset it here (the demo saves/restores it around its own frames). */
    hud_framecnt = 0;
    memset(title_dirty, 0, sizeof title_dirty);
    title_countdown_dirty = 0;
    /* P1: on this entry's first title commit the old span is the whole row,
     * so the first page blanks the stale cells the BIOS/HUD left outside
     * the page's text; after that the shown spans are the page's own. */
    {
        u8 i;

        for (i = 0; i < TITLE_ROWS; i++) {
            title_shown_col[i] = 0;
            title_shown_len[i] = TITLE_COLS;
        }
    }

    /* Attract Task A2: the title stands over the game's scene at a fresh
     * game's state — the same state game_begin sets up before its first
     * play frame (ship on the start cell, no missiles, whole dome, score
     * 0), with the title's chosen level. The title's own dome spin is
     * gone: view 0, as in play. */
    ship_reset(&ship);
    mis_reset(&mis);
    rules_reset(&rules);
    rules.level = flow_level_get();
    mis.level = rules.level;
    radar_frame(&radar, &mis, &ship);

    ng_wait_vblank();                   /* (a stale flag at entry: skip it) */

    /* The scene is shown in two vblanks, so the entry's heavy VRAM work
     * fits between them and the first title frame still starts at the same
     * MAME frame as before Task A2 (the title's time, which seeds the next
     * game, is unchanged). Part 1: the backdrop and the wide scenery. */
    backdrop(COL_SKY);
    ground_show(ship.dome_angle);
    mountains_show(ship.dome_angle);
    band_show(ship.dome_angle);
    console_show();

    ng_wait_vblank();                   /* part 2, from the next vblank */

    props_show(ship.dome_angle);
    dome_collapse(&rules, 0);
    dome_show(0);
    ship_gfx_init();
    ship_gfx_show(ship.lat, ship.lift, 0);   /* REST (picture 0) */
    radar_gfx_init();
    radar_frame(&radar, &mis, &ship);
    radar_gfx_prepare(&radar);
    mis_gfx_hide();
    cracks_show_empty();
    collapse_prepare(&rules, 0);

    /* the HUD's two rows at a fresh game's values: integrity 100% (row 26)
     * and score 0 + three lives (row 28), in the in-play amber. Drawn once
     * here; the title never writes them again. */
    {
        char hud[HUD_DUMP_ROWS][HUD_COLS + 1];

        hud_rows(&rules, &mis, hud);
        fix_text(0, HUD_INTEG_ROW, PAL_HUD_PLAY, hud[HUD_INTEG_ROW]);
        fix_text(0, HUD_LIVES_ROW, PAL_HUD_PLAY, hud[HUD_LIVES_ROW]);
    }

    /* The scene's two-vblank setup costs two MAME frames before the loop's
     * first title_frame. title_t and title_seed_t are the title's own frame
     * count (page timing, prompt phase, and the Start's missile seed), so
     * account for those two frames: the first title_frame then starts at
     * title frame 3, exactly as the pre-A2 light entry did. */
    title_t = 2;
    title_seed_t = 2;

#if DEMO_TITLE
    /* Attract Task A3: every entry from the BIOS (a fresh boot or a GAME
     * OVER return) starts the demo from its first frame. */
    demo_begin();
#endif

    title_stage();                      /* staged for the first vblank */
    title_blink_capture();              /* B6: the returned page's new row */

    /* Task P2: the props table made props_show cheap, so this entry
     * reached the loop two MAME frames earlier than HEAD: title_t was 7 at
     * MAME 31 (HEAD 5) and a fixed-MAME Start saw title_seed_t 577 (HEAD
     * 575). The title's own frame count and the flow-return proof's first
     * sampled title_t are calibrated to HEAD's entry, so wait the two
     * frames props_show used to take. The Start is pressed on the title
     * count, but the title's own timing must not move. */
    ng_wait_vblank();
    ng_wait_vblank();

    for (;;) {
        ng_wait_vblank();
#ifdef FRAME_MARK
        work_start_mark = lspc_vpos();       /* vblank return: the frame's start */
#endif
        /* Attract Task A2: title_commit() writes the rows staged by the
         * previous title frame. The staging runs after the commits (in the
         * switch below), so a page turn's 960 writes still fit the vblank
         * and land before the rows they change; the drawn text is one
         * vblank behind the RAM state, as the scene's staged groups are. */
        /* On the Start frame game_begin() rewrites the whole scene and
         * clears the fix layer below, so none of the title's staged commits
         * are needed — and running them would overrun the vblank before the
         * game's first frame (the pre-A2 loop skipped its commits here too).
         * Otherwise: the title's staged fix rows go first, so a page turn's
         * rows are written before the raster reaches them. */
        if (!(flow == FLOW_TITLE && bios_user_mode == 2)) {
            /* dome-scenery Tasks 18/18b and attract Task A2: the prepared
             * VRAM and palette writes go right after vblank, before the
             * frame body, on title frames too (the title's scene is the
             * game's scene). The order follows the draw positions: the
             * missiles reach the top of the screen, the mountains start at
             * line 52, the band at 68, the props at 83, the radar is at the
             * bottom — so a group drawn higher is written first. The
             * mountains and band are the two per-frame driver writes the
             * tear leg found inside their own spans; they are moved here
             * too, so they show the previous frame's dome angle (Task 18's
             * one-frame lag; their probes record the displayed angle). */
            mis_gfx_commit();
            mountains_frame(ship.dome_angle);
            band_frame(ship.dome_angle);
            /* Attract Task A2: then the title's staged fix rows. On a page
             * turn they must be written before the raster reaches their
             * rows; they are top-down from the vblank, so they can follow
             * the mountains and band (both start lower than the title's
             * top rows) without delaying those groups past their own
             * scanlines. At a Start, game_begin() rewrites the scene and
             * clears the fix layer: the title's staged rows are dropped
             * rather than written (the write would overrun the vblank
             * before the game's first frame). On a game frame title_dirty
             * is clear, so this is a no-op. B4's page-turn fix writes are
             * wide; writing them after mountains/band keeps the mountain
             * SCB4 write ahead of line 52 while the fix layer still lands
             * before its rows. */
            if (flow == FLOW_TITLE && bios_user_mode != 2) {
                /* Attract Task A3: the demo's staged HUD rows go in this
                 * vblank before title_commit(), so the MVS countdown's two
                 * cells win over the demo's score. */
                hud_demo_commit();
                title_commit();
            }
            /* Task G1: the switch below enters FLOW_ENTRY this frame, and
             * the entry's first frame must not show GAME OVER's cap row 8.
             * Blank it now, in vblank, before the raster reaches it; row 7
             * stays GAME OVER until entry_text_commit writes the entry's
             * own rows in the next vblank (its initials cap). */
            if (flow == FLOW_GAMEOVER_WAIT && rules.game_over
                && entry_qualifies && gameover_shown >= GAME_OVER_TEXT_FRAMES)
                fix_text(HUD_GAMEOVER_COL0, HUD_GAMEOVER_CAP_ROW, PAL_HUD,
                         "          ");
            if (flow == FLOW_ENTRY)
                entry_text_commit();
            ring_gfx_commit();
            props_commit();
            collapse_commit();        /* the collapse redo's Task C2: the
                                       * fireball's staged words, next to
                                       * the props' */
            ship_gfx_commit();        /* the ship's staged SCB1 (only when
                                       * (lat, frame) changed) and Y */
            ground_commit();          /* dome-scenery Task 19: the staged
                                       * ripple words, right after the
                                       * props' (the grass sits below
                                       * them) */
            radar_gfx_commit();
        }
#ifdef FRAME_MARK
        work_commit_mark = lspc_vpos();
#endif
        switch (flow) {
        case FLOW_TITLE:
            if (bios_user_mode == 2) {       /* a Start press: begin a game */
                game_begin();
                flow = FLOW_GAME;
            } else {
                title_frame();       /* stage the next vblank's rows */
            }
            break;
        case FLOW_GAME:
            if (rules.game_over) {
                /* the frame GAME OVER was first seen: compute the rank now
                 * (the board does not change until END) and start the text
                 * countdown. The current frame's body still runs so the
                 * GAME OVER text draws. Task B6 replaced B2's three-space
                 * insert/save here: a qualifying game goes to FLOW_ENTRY
                 * after GAME_OVER_TEXT_FRAMES, and a non-qualifying game
                 * keeps today's 295-frame window (A restarts).
                 * board_rank's u32 maths is entry-time only. */
                u8 rank = BOARD_NENTRIES;

                entry_score10 = mis.score10;
                if (rules.level < LEVELS)
                    rank = board_rank(&flow_board, rules.level,
                                      entry_score10);
                entry_rank = rank;
                entry_qualifies = (u8)(rank < BOARD_NENTRIES);
                go_suppress_a = entry_qualifies;
                gameover_shown = 1;
                flow = FLOW_GAMEOVER_WAIT;
                gameover_wait = 0;
            }
            game_frame();
            break;
        case FLOW_GAMEOVER_WAIT:
            if (!rules.game_over) {          /* A restarted within the window */
                flow = FLOW_GAME;
                go_suppress_a = 0;
            } else if (entry_qualifies
                       && gameover_shown >= GAME_OVER_TEXT_FRAMES) {
                /* 118 GAME OVER frames are shown: start the entry at the
                 * dome's GAME OVER angle. entry_text_begin stages rows
                 * 2..7; entry_screen_frame draws this frame's ring/scene
                 * (the first commit lands in the next vblank). */
                entry_begin(&entry_state);
                entry_base_angle = ship.dome_angle;
                entry_fc = 0;
                entry_text_begin();
                flow = FLOW_ENTRY;
                go_suppress_a = 0;
                entry_screen_frame();
                break;
            } else if (gameover_wait >= GAME_OVER_WAIT) {
                /* the non-qualifying window is spent: return to the title.
                 * Record the played level's board page (1..3) for the next
                 * entry, tell the BIOS the game is over, and return — the
                 * BIOS calls main() again (~200 MAME frames later), so the
                 * next entry shows the title on that board page. No
                 * flow_open_rank: the board did not change, no row blinks. */
                flow_open_page = (u8)(((rules.level < LEVELS) ? rules.level
                                       : LEVEL_NORMAL) + 1);
                flow_open_rank = 0;
                bios_player_mod1 = 0;
                backdrop(COL_BLACK);            /* the returned title is black */
                return;
            } else {
                gameover_wait++;
                gameover_shown++;
            }
            game_frame();
            break;
        case FLOW_ENTRY:
            entry_screen_frame();
            if (entry_state.done) {
                /* END: put the typed initials (END pads the missing slots
                 * with spaces) and the GAME OVER score on the board, save
                 * it, and return to the played level's board page with the
                 * new entry's row blinking. */
                u8 lvl = (rules.level < LEVELS) ? rules.level : LEVEL_NORMAL;

                board_insert(&flow_board, lvl, entry_rank, entry_state.init,
                             entry_score10);
                flow_card_save();
                flow_open_page = (u8)(lvl + 1);
                flow_open_rank = (u8)((entry_rank < BOARD_NENTRIES)
                                      ? entry_rank + 1 : 0);
                ring_gfx_hide();
                bios_player_mod1 = 0;
                backdrop(COL_BLACK);
                return;
            }
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
