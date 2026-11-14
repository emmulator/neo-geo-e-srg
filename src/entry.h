/* entry.h: the high-score initials ring's state machine (high-score boards
 * Task B5). Pure logic, no hardware: host-built as build/entry_sim and held
 * to tests/entry_model.py by tests/test_entry.py. Task B6 draws the ring,
 * the dome and the scene from entry_t.
 *
 * The ring has RING_N positions (A-Z, space, . ! ? - & ', a star, a heart,
 * the erase arrow and END; build/ring_map.h's ring_code) and RING_SUB
 * animation phases per position, so RING_PHASES = RING_N * RING_SUB. Phase
 * p shows the ring turned p / RING_SUB positions: position k is at the
 * front when p = k * RING_SUB (entry_begin starts at 0, A at the front).
 *
 * Inputs are the Neo Geo's bios_p1current and bios_p1change: cur is the
 * held buttons (CNT_*), change the newly pressed ones. A held left/right
 * steps at once and repeats after ENTRY_REPEAT_FIRST frames, then every
 * ENTRY_REPEAT_EVERY. A picks the front position, but only at rest; the
 * third initial turns the ring to END; the ring still turns after it (so
 * the player can step back to ERASE and fix a typo), but A on a letter
 * does nothing while three are stored, so a fourth letter cannot happen;
 * END finishes, padding the missing initials with spaces. ERASE removes the last initial. B does nothing. Once done
 * the machine freezes. Each frame's sound events are reported in sfx: a
 * tick when a move leaves the phase on a position (so a held turn ticks
 * once per position and the jump's two sub-steps never tick twice), a type
 * on an appended letter, a backspace only when an erase removed one, and
 * the bell on END.
 *
 * K2: a picked letter's copy flies to its initials slot. A pick of a letter
 * sets fly_k = the position and fly_t = 1 on the pick frame; each later
 * frame increments fly_t, and the frame it would pass FLY_FRAMES (the
 * generated ring header's 20) it becomes 0 (landed). A new letter pick while
 * flying, an erase or END ends the flight first (fly_t 0) then applies as
 * today (a new letter starts its own flight). src/ring_gfx.c draws the copy
 * at FLY_SPRITE while fly_t > 0; src/flow.c blanks its initials cell.
 *
 * entry_dome_angle returns the dome angle for the ring's phase: base minus
 * (the dome turns with the ring, as Right spins it in play) the phase's share of one full 240-step turn, rounded as
 * (phase * 240 + RING_PHASES / 2) / RING_PHASES. The 37 positions are
 * exactly one turn, so a full left (or right) hold returns the dome to its
 * starting angle.
 */
#ifndef ENTRY_H
#define ENTRY_H
#include <ngdevkit/types.h>

#define ENTRY_INIT_MAX     3    /* the three initials */
#define ENTRY_REPEAT_FIRST 16   /* held frames before a direction repeats */
#define ENTRY_REPEAT_EVERY 8    /* held frames between repeats after that */
#define ENTRY_DIR_JUMP     3    /* dir: the jump to END, two sub-steps a
                                 * frame (twice a turn's rate, 10-30) */

/* entry_t.sfx: this frame's sound events (src/flow.c sends the commands).
 * Cleared at the start of every entry_frame, a done one included. */
#define ENTRY_SFX_TICK 1        /* a move left the phase on a position */
#define ENTRY_SFX_TYPE 2        /* A appended an initial */
#define ENTRY_SFX_BACK 4        /* A on ERASE removed an initial */
#define ENTRY_SFX_BELL 8        /* A on END */

typedef struct {
    u8 phase;       /* 0..RING_PHASES-1: the ring's animated phase */
    u8 target;      /* 0..RING_PHASES-1: where it is turning to; a
                     * multiple of RING_SUB */
    u8 ninit;       /* 0..ENTRY_INIT_MAX: initials entered so far */
    u8 init[ENTRY_INIT_MAX]; /* the initials; the unused bytes are 0 until
                              * END pads them with spaces */
    u8 hold;        /* frames since the last step of a held direction */
    u8 dir;         /* 0 none, 1 right, 2 left: the direction being held;
                     * ENTRY_DIR_JUMP: the third initial's turn to END */
    u8 done;        /* END was pressed: the entry is finished */
    u8 sfx;         /* this frame's ENTRY_SFX_* bits; cleared every frame */
    u8 fly_t;       /* frames of the flight shown so far; 0 = none (K2) */
    u8 fly_k;       /* the picked position the flying letter came from */
} entry_t;

/* start the entry: phase 0 (A at the front), no initials */
void entry_begin(entry_t *e);

/* one frame: cur = bios_p1current, change = bios_p1change */
void entry_frame(entry_t *e, u8 cur, u8 change);

/* the dome angle for the ring's current phase (base + its share of a turn) */
u8 entry_dome_angle(const entry_t *e, u8 base);

#endif
