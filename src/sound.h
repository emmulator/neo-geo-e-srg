/* sound.h: the cart's sound commands and the 68k -> Z80 driver interface
 * (M7 Task 1). See src/sound.c.
 *
 * The nullsound driver in the M ROM takes one command byte at a time at
 * REG_SOUND (0x320000): the cart writes a command, the Z80 queues it in a
 * 64-entry FIFO and acknowledges it by writing `cmd | 0x80` back to the
 * same port. The 68000 reads the port to see that acknowledgement and only
 * then sends the next command, so two sounds in one frame both play.
 *
 * Commands:
 *   3          reset the driver (sent once at flow_run entry)
 *   4..8       play the Vectrex effects (sound/user_commands.s)
 */
#ifndef SOUND_H
#define SOUND_H
#include <ngdevkit/types.h>

#define SND_RESET 3
#define SND_FIRE  4        /* a bullet fires                (channel 0) */
#define SND_JUMP  5        /* a jump starts                 (channel 0) */
#define SND_HIT   6        /* a missile is shot down        (channel 2) */
#define SND_CRACK 7        /* a missile breaks a fresh cell (channel 2) */
#define SND_PIP   8        /* the radar's lock-on pip       (channel 1) */

/* reset the sound driver: command 3, sent once at flow entry */
void sound_reset(void);

/* send one command and wait for the Z80's `cmd | 0x80` acknowledgement.
 * Returns 1 when acknowledged, 0 when the bounded wait ran out. Callers
 * must not send the next command before an acknowledgement, or the FIFO
 * can drop it. */
u8 sound_cmd(u8 cmd);

#endif
