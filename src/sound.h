/* sound.h: the cart's sound commands, the 68k -> Z80 driver interface
 * (M7 Task 1) and the game's per-frame command decision. See src/sound.c.
 *
 * The nullsound driver in the M ROM takes one command byte at a time at
 * REG_SOUND (0x320000): the cart writes a command, the Z80 queues it in a
 * 64-entry FIFO and acknowledges it by writing `cmd | 0x80` back to the
 * same port. The 68000 reads the port to see that acknowledgement and only
 * then sends the next command, so two sounds in one frame both play.
 *
 * Commands:
 *   3          reset the driver (sent once at flow_run entry)
 *   4..9       play the spider's effects (sound/user_commands.s)
 *   10..13     the initials picker's effects (sound/user_commands.s)
 *
 * The per-frame choice lives here, not in flow.c, so the host test can
 * drive the real decision beside the Python model (tests/sound_model.py):
 * sound_frame_cmds() is the one game_sound() body. */
#ifndef SOUND_H
#define SOUND_H
#include <ngdevkit/types.h>
#include "ship.h"                /* SHIP_MOVE_FRAMES (the scuttle's period) */
#include "missiles.h"            /* SFX_FIRE / SFX_HIT / SFX_CRACK */

#define SND_RESET 3
#define SND_FIRE  4        /* a bullet fires                (channel 3) */
#define SND_JUMP  5        /* a jump starts                 (channel 0) */
#define SND_HIT   6        /* a missile is shot down        (channel 2) */
#define SND_CRACK 7        /* a missile breaks a fresh cell (channel 2) */
#define SND_PIP   8        /* the radar's lock-on pip       (channel 1) */
#define SND_MOVE  9        /* a cell step or a spin's step  (channel 0) */
#define SND_TICK  10       /* a letter reaches the ring's front (channel 3) */
#define SND_TYPE  11       /* a letter is picked            (channel 4) */
#define SND_BELL  12       /* END                            (channel 5) */
#define SND_BACK  13       /* the erase arrow removes one   (channel 4) */

/* the scuttle's period and the lock pip's counter, kept from frame to frame
 * (a plain .bss static in flow.c; the host test has its own) */
typedef struct {
    u8 spin_t;          /* frames until the next spin scuttle (0 = not armed) */
    u8 spin_was;        /* the ship spun last frame */
    u8 pip_t;           /* the lock pip's counter: 0..19 */
} sound_state_t;

/* the frame's inputs to the choice */
typedef struct {
    u8 jumped;          /* ship.jumped: a jump started this frame */
    u8 move_left;       /* ship.move_left */
    u8 mlen;            /* ship.mlen */
    u8 spinning;        /* ship.spinning: held at the peak this frame */
    u8 sfx;             /* mis.sfx: SFX_FIRE / SFX_HIT / SFX_CRACK */
    u8 died;            /* rules_end returned 1 this frame */
    u8 alive;           /* !rules.dead_t && !rules.game_over (after rules_end) */
    u8 dead_t;          /* rules.dead_t */
    u8 dome_dead;       /* rules.dome_dead */
    u8 collapse_frac;   /* collapse_frac(&rules): the collapse's age */
    u8 locked;          /* radar.locked */
} sound_frame_t;

#define SOUND_CMDS_MAX 6

/* the frame's command list, in the Vectrex's order: jump, fire, the
 * death/hit/crack, the scuttle, the collapse rumble, the pip. The scuttle
 * plays on a walk's first frame (move_left == mlen == SHIP_MOVE_FRAMES),
 * and while spinning at the peak on the spin's first frame and every
 * SHIP_MOVE_FRAMES frames after; it is never sent on a jump's frame or
 * while the ship is dead. The collapse's 5 beats are HIT (the death, frame
 * 0), CRACK (9), HIT (18), CRACK (27), HIT (36). */
static inline u8 sound_frame_cmds(sound_state_t *st,
                                  const sound_frame_t *f,
                                  u8 out[SOUND_CMDS_MAX])
{
    u8 n = 0, scuttle = 0;

    if (f->jumped)
        out[n++] = SND_JUMP;
    if (f->sfx & SFX_FIRE)
        out[n++] = SND_FIRE;
    if (f->died)
        out[n++] = SND_HIT;
    else if (f->sfx & SFX_CRACK)
        out[n++] = SND_CRACK;
    else if (f->sfx & SFX_HIT)
        out[n++] = SND_HIT;

    if (f->alive) {
        if (f->move_left == SHIP_MOVE_FRAMES
            && f->mlen == SHIP_MOVE_FRAMES)
            scuttle = 1;             /* a walk's first frame */
        else if (f->spinning) {
            if (!st->spin_was || st->spin_t == 0) {
                scuttle = 1;
                st->spin_t = SHIP_MOVE_FRAMES;
            } else if (--st->spin_t == 0) {
                scuttle = 1;
                st->spin_t = SHIP_MOVE_FRAMES;
            }
        } else {
            st->spin_t = 0;
        }
    } else {
        st->spin_t = 0;
    }
    st->spin_was = f->spinning;
    if (scuttle && !f->jumped)
        out[n++] = SND_MOVE;

    if (f->dead_t && f->dome_dead) {
        if (f->collapse_frac == 9 || f->collapse_frac == 27)
            out[n++] = SND_CRACK;
        else if (f->collapse_frac == 18 || f->collapse_frac == 36)
            out[n++] = SND_HIT;
    }

    if (f->locked) {
        if (st->pip_t == 0)
            out[n++] = SND_PIP;
        if (++st->pip_t == 20)       /* 20 frames: 2 blink cycles */
            st->pip_t = 0;
    } else {
        st->pip_t = 0;
    }
    return n;
}

/* reset the sound driver: command 3, sent once at flow entry */
void sound_reset(void);

/* send one command and wait for the Z80's `cmd | 0x80` acknowledgement.
 * Returns 1 when acknowledged, 0 when the bounded wait ran out. Callers
 * must not send the next command before an acknowledgement, or the FIFO
 * can drop it. */
u8 sound_cmd(u8 cmd);

#endif
