/* demo.c: the attract mode's recorded game (Attract Task A3). See demo.h.
 *
 * The generated header names its input table `demo_input`; this file also
 * defines the interface function demo_input(), so the include renames the
 * table to demo_script for the duration of the include (the header itself
 * stays the orchestrator's, untouched).
 *
 * The game state (ship / mis / rules) lives in src/flow.c; the demo resets
 * it and flow.c runs game_frame with the bytes this file returns. The demo
 * never calls best_update or flow_level_set: only the game state is reset
 * to DEMO_LEVEL / DEMO_SEED. */
#include <ngdevkit/neogeo.h>
#include <ngdevkit/bios-ram.h>
#include "demo.h"
#include "ship.h"
#include "missiles.h"
#include "rules.h"

#define demo_input demo_script
#include "demo_map.h"
#undef demo_input

/* src/flow.c's game state (not static: the demo resets it). */
extern ship_t ship;
extern mis_t mis;
extern rules_t rules;

static u16 demo_fc;             /* the next script frame to play (0-based) */
static u16 demo_epoch;          /* how many restarts have happened */
static u16 demo_run;            /* the input run being played */
static u8 demo_left;            /* frames left in the current run */
static u8 demo_cur;             /* the run's current-input byte */
static u8 demo_prev;            /* the previous frame's current byte */
static u8 demo_on;              /* 1: the demo is running */

volatile u16 demo_dbg_fc;
volatile u16 demo_dbg_epoch;
volatile u16 demo_dbg_hash_epoch;
volatile u16 demo_dbg_hash_fc;
volatile u32 demo_dbg_hash_done;
volatile u32 demo_dbg_hash;

/* P1: FNV-1a's 32-bit multiply is a libgcc __mulsi3 call on the 68000, so
 * the per-frame hash now mixes with a shift-and-add multiply (x33), which
 * covers the same fields in the same order. The checker's Python replay
 * mixes the same fields with the same expression, so one 32-bit word still
 * covers every frame the cart ran (the MAME notifier can miss a frame, the
 * cart cannot). */
#define HASH_BASE 2166136261u
static u32 demo_hash;

static u32 hash_mix(u32 h, u32 v)
{
    h ^= v;
    h *= 33u;                 /* gcc emits shifts/adds, not __mulsi3 */
    return h;
}

void demo_restart(void)
{
    demo_fc = 0;
    demo_run = 0;
    demo_left = 0;
    demo_cur = 0;
    demo_prev = 0;
    demo_on = 1;
    demo_dbg_hash_epoch = demo_epoch;
    demo_dbg_hash_done = demo_hash;
    demo_hash = HASH_BASE;          /* the new epoch's accumulator */
    demo_dbg_hash = demo_hash;
    demo_epoch++;
    demo_dbg_epoch = demo_epoch;
    demo_dbg_fc = 0;
    demo_dbg_hash_fc = 0;

    ship_reset(&ship);
    mis_reset(&mis);
    rules_reset(&rules);
    rules.level = DEMO_LEVEL;       /* NORMAL: the design's call */
    mis.level = DEMO_LEVEL;
    mis.rng = DEMO_SEED;            /* the fixed demo seed */
}

void demo_input(u8 *cur, u8 *pressed)
{
    if (demo_left == 0) {
        if (demo_run < DEMO_RUNS) {
            demo_cur = demo_script[demo_run][0];
            demo_left = demo_script[demo_run][1];
            demo_run++;
        } else {
            demo_cur = 0;           /* past the script: no input */
            demo_left = 1;
        }
    }
    *cur = demo_cur;
    *pressed = (u8)(demo_cur & ~demo_prev);
    demo_prev = demo_cur;
    demo_left--;
    demo_fc++;
    demo_dbg_fc = demo_fc;
}

void demo_hash_frame(void)
{
    u32 h = demo_hash;
    u8 i;

    h = hash_mix(h, rules.level);
    h = hash_mix(h, rules.nbroken);
    h = hash_mix(h, rules.lives);
    h = hash_mix(h, rules.integ_pct);
    h = hash_mix(h, rules.dead_t);
    h = hash_mix(h, rules.dome_dead);
    h = hash_mix(h, rules.game_over);
    h = hash_mix(h, ship.dome_angle);
    h = hash_mix(h, ship.lat);
    h = hash_mix(h, ship.cell);
    h = hash_mix(h, ship.move_left);
    h = hash_mix(h, ship.lift);
    h = hash_mix(h, ship.jumped);
    for (i = 0; i < (u8)sizeof(ship.broken); i++)
        h = hash_mix(h, ship.broken[i]);
    h = hash_mix(h, mis.rng);
    h = hash_mix(h, mis.spawn_timer);
    h = hash_mix(h, mis.level);
    h = hash_mix(h, mis.kills);
    h = hash_mix(h, mis.dome_hits);
    h = hash_mix(h, mis.score10);
    h = hash_mix(h, mis.fire_req);
    /* mis.sfx is the frame's sound-event byte, not game state: the
     * host model (hud_model.frame_model) does not clear it each frame, so
     * it is deliberately outside this state hash. */
    for (i = 0; i < NMIS; i++) {
        h = hash_mix(h, mis.obj[i].state);
        h = hash_mix(h, mis.obj[i].kind);
        h = hash_mix(h, mis.obj[i].ring);
        h = hash_mix(h, mis.obj[i].phi);
        h = hash_mix(h, mis.obj[i].life);
        h = hash_mix(h, (u32)mis.obj[i].r);
        h = hash_mix(h, (u32)mis.obj[i].dr);
    }
    demo_hash = h;
    demo_dbg_hash = h;
    demo_dbg_hash_fc = demo_dbg_fc;
}

u8 demo_active(void)
{
    return (u8)(demo_on && bios_user_mode != 2);
}
