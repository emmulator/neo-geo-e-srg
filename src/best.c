/* best.c: the per-level high-score table (M6 Task 8). Pure logic, no
 * hardware: host-built as build/best_sim and held to tests/best_model.py.
 *
 * Runs only at GAME OVER and at an entry, never per frame, so the 32-bit
 * arithmetic here is allowed (u32 / and * compile to __udivsi3 /
 * __umodsi3 / __mulsi3 calls on the 68000; the per-frame code in flow.c
 * must stay 16-bit).
 *
 * The sum covers the 16 bytes before it (magic + score10, in memory
 * order, big-endian on the 68000), wrapping at 16 bits: a valid table is
 * the magic, scores <= SCORE_MAX, and the right sum. The struct is
 * packed (best.h) so the host build lays it out exactly as the 68000
 * does, and the sum is computed byte-wise so the bytes are the same on
 * either endianness.
 */
#include <string.h>
#include "best.h"
#include "missiles.h"              /* SCORE_MAX */

/* the 16 bytes the sum covers, as a byte run in memory order. The
 * struct is packed, so this is exactly the 16 bytes before b->sum. */
static u16 best_sum_bytes(const best_t *b)
{
    const u8 *p = (const u8 *)b;
    u16 sum = 0;
    u8 i;

    for (i = 0; i < 16; i++)
        sum = (u16)(sum + p[i]);
    return sum;
}

void best_reset(best_t *b)
{
    memset(b, 0, sizeof *b);
    b->magic = BEST_MAGIC;
    b->sum = best_sum_bytes(b);
}

u8 best_valid(const best_t *b)
{
    u8 i;

    if (b->magic != BEST_MAGIC)
        return 0;
    for (i = 0; i < BEST_NLEVELS; i++)
        if (b->score10[i] > SCORE_MAX)
            return 0;
    return b->sum == best_sum_bytes(b);
}

u8 best_update(best_t *b, u8 level, u32 score10)
{
    if (level >= BEST_NLEVELS)
        return 0;
    if (score10 <= b->score10[level])
        return 0;                  /* equal and lower change nothing */
    b->score10[level] = score10;
    b->sum = best_sum_bytes(b);
    return 1;
}
