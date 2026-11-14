/* sound.c: the 68k side of the nullsound driver interface (M7 Task 1).
 *
 * The cart talks to the Z80 sound driver (sound/user_commands.s, linked
 * against nullsound) one command byte at a time through REG_SOUND
 * (0x320000). The Z80 queues each byte in a 64-entry FIFO and writes the
 * acknowledgement `cmd | 0x80` back to the same port; the 68000 must wait
 * for that acknowledgement before sending the next command, or two
 * commands in one frame can be dropped (the FIFO ack is the only back
 * pressure). The bounded wait (SOUND_WAIT_POLLS reads) makes the wait
 * safe even if the driver never answers: a stuck Z80 must not hang the
 * game.
 *
 * sound_reset() sends command 3 (nullsound's reset) once at flow entry,
 * matching the ADPCM-A example's main(). reset and every sound command
 * are sent the same way, so the acknowledgements prove the driver is
 * alive and each command was queued.
 */
#include "sound.h"
#include <ngdevkit/neogeo.h>

#define SOUND_WAIT_POLLS 2000   /* the ack-wait bound (confirmed): a
                                 * command is acknowledged within a few
                                 * hundred polls; 2000 covers any BIOS
                                 * stop-the-68k delay without hanging */

/* poll REG_SOUND until it reads `expected` (or the bound runs out);
 * returns 1 on success. The expected value is this command's own ack
 * (cmd | 0x80), never a plain "any ack": a stale 0x80 from an earlier
 * command can still be sitting in the port. */
static u8 sound_wait(u8 expected)
{
    u16 i;
    volatile u8 *reg = REG_SOUND;

    for (i = 0; i < SOUND_WAIT_POLLS; i++)
        if (*reg == expected)
            return 1;
    return 0;
}

void sound_reset(void)
{
    (void)sound_cmd(SND_RESET);
}

u8 sound_cmd(u8 cmd)
{
    *REG_SOUND = cmd;
    return sound_wait((u8)(cmd | 0x80));
}
