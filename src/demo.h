/* demo.h: the attract mode's self-playing game (Attract Task A3).
 *
 * The title keeps its pages and timing, but behind it the game's own state
 * (rules, ship, missiles, radar, scenery) runs game_frame with a recorded
 * input script (build/demo_map.h, from the orchestrator's tools/gen_demo.py)
 * and a fixed seed. The demo is the real game, deterministic and identical
 * every cycle.
 *
 * Interface:
 *   demo_restart()   the script to frame 0 and the game state to a fresh
 *                    NORMAL game seeded DEMO_SEED. flow.c calls it whenever
 *                    page 0 begins (the cycle wrapping, a B press, an entry
 *                    from GAME OVER or the BIOS).
 *   demo_input()     this frame's BIOS-style current byte and its pressed
 *                    edge (current & ~previous), then advance.
 *   demo_active()    1 while the demo is running (the title, not a game).
 *
 * The demo never calls best_update and never writes flow_level: a demo
 * restart sets only the game state, not the player's chosen level.
 */
#ifndef DEMO_H
#define DEMO_H
#include <ngdevkit/types.h>

void demo_restart(void);
void demo_input(u8 *cur, u8 *pressed);
u8 demo_active(void);

/* Attract Task A3's frame-by-frame proof: hash the game state after each
 * demo frame into a rolling 32-bit FNV-1a accumulator; the boot-test's
 * checker computes the same hash from the host model over all 3245 frames.
 * The MAME frame notifier can miss a cart frame (it can read before the
 * cart advances), so the hash covers every frame the cart actually ran. */
void demo_hash_frame(void);

/* Debug exports for the MAME demo probe (like mis_seed_used): the script
 * frame just played (1..DEMO_FRAMES), the restart's ordinal (1, 2, ...) and
 * the previous restart's completed frame hash (done_epoch / done_hash).
 * They are tiny .bss words with no behaviour in the normal cart. */
extern volatile u16 demo_dbg_fc;
extern volatile u16 demo_dbg_epoch;
extern volatile u16 demo_dbg_hash_epoch;
extern volatile u16 demo_dbg_hash_fc;   /* the frame demo_dbg_hash covers */
extern volatile u32 demo_dbg_hash_done;
extern volatile u32 demo_dbg_hash;
#endif
