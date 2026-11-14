/* flow.h: the game's top-level flow (M6 Task 1) — boots to a title, a
 * Start press begins a game, and a spent GAME OVER returns to the title.
 *
 * The flow is a small state machine with three states (src/flow.c):
 *
 *   FLOW_TITLE        the title pages: the dome turning on a black
 *                     backdrop, and the title text. Waits until the BIOS
 *                     sets bios_user_mode 2
 *                     (a Start press, or Start with a credit), which the
 *                     game loop sees next frame.
 *
 *   FLOW_GAME         the current game loop (rules, ship, missiles, radar,
 *                     HUD, all the drawing), running from the first frame
 *                     after Start.
 *
 *   FLOW_GAMEOVER_WAIT  the 295-frame window after a GAME OVER (the
 *                     Vectrex's GAME_OVER_FRAMES 250 x 59/50). Within it A
 *                     restarts a game (the rules' A-restart, as today); when
 *                     it expires the cart returns to the title.
 *
 * The BIOS calls the cart's main() in attract mode; a Start press calls the
 * cart's player_start() from vblank handling (it sets bios_user_mode and
 * bios_player_mod1, both from <ngdevkit/bios-ram.h>), so the loop's next
 * frame leaves FLOW_TITLE for FLOW_GAME. After a game the cart returns from
 * main() having set bios_player_mod1 = 0; the BIOS then calls main() again
 * (about 200 MAME frames later), so each entry is one title + one game.
 *
 * The whole per-entry work (init + the flow loop) belongs to the
 * entry points in src/main.c; flow_run is the loop both main() and
 * main_mvs_title() enter (MVS's becomes different in Task 2).
 */
#ifndef FLOW_H
#define FLOW_H
#include <ngdevkit/types.h>

/* the cart's game-session frame timings (x 59/50 from the Vectrex) */
#define GAME_OVER_WAIT 295        /* 250 Vectrex frames x 59/50: the A-restart
                                   * window after a GAME OVER */

/* the cart's Start hook: the BIOS calls this from vblank when the player
 * presses Start (AES) or Start with a credit (MVS). Sets the BIOS's user
 * mode to 'game' so the loop leaves the title. */
void player_start(void);

/* the flow loop: the one loop main() and main_mvs_title() both enter. It
 * runs forever, driving the title / game / GAME OVER state machine, and
 * only returns to hand control back to the BIOS after a spent GAME OVER.
 * `entry` says which entry called it: 0 = main (an attract boot — on MVS
 * the title says INSERT COIN), 1 = main_mvs_title (after a coin — PRESS
 * START and the compulsion-timer countdown on row 9). It lives in a plain
 * static, set at the top of flow_run: .bss is zeroed on each entry
 * anyway. */
void flow_run(u8 entry);
#endif
