/* board.c: the five-entry per-level high-score board (high-score boards
 * Task B1). Pure logic, no hardware: host-built as build/board_sim and held
 * to tests/board_model.py by tests/test_board.py. See board.h for the
 * layout and the rules.
 *
 * The sum is computed byte-wise over the bytes before it, so the host's
 * little-endian fields and the 68000's big-endian ones give the same value
 * (addition is commutative). The explicit pad byte keeps every u32 at an
 * even offset, so the 68000's 32-bit loads and stores never fault.
 */
#include <string.h>
#include "board.h"
#include "missiles.h"             /* SCORE_MAX */

/* the bytes the sum covers: the whole packed struct before sum (124) */
static u16 board_sum_bytes(const board_t *b)
{
    const u8 *p = (const u8 *)b;
    u16 n = (u16)(sizeof *b - sizeof b->sum);
    u16 sum = 0;
    u16 i;

    for (i = 0; i < n; i++)
        sum = (u16)(sum + p[i]);
    return sum;
}

void board_reset(board_t *b)
{
    /* the spec's displayed defaults (50,000 ... 10,000), stored score/10 */
    static const char *const names[BOARD_NENTRIES] = {
        "SRG", "HEX", "DOM", "ZAP", "VEC"
    };
    static const u32 scores[BOARD_NENTRIES] = {
        5000, 4000, 3000, 2000, 1000
    };
    u8 level, e, j;

    memset(b, 0, sizeof *b);
    b->magic = BOARD_MAGIC;
    for (level = 0; level < BOARD_NLEVELS; level++) {
        for (e = 0; e < BOARD_NENTRIES; e++) {
            for (j = 0; j < BOARD_NINIT; j++)
                b->entry[level][e].init[j] = (u8)names[e][j];
            b->entry[level][e].pad = 0;
            b->entry[level][e].score10 = scores[e];
        }
    }
    b->sum = board_sum_bytes(b);
}

u8 board_valid(const board_t *b)
{
    u8 level, e;

    if (b->magic != BOARD_MAGIC)
        return 0;
    if (b->sum != board_sum_bytes(b))
        return 0;
    for (level = 0; level < BOARD_NLEVELS; level++) {
        for (e = 0; e < BOARD_NENTRIES; e++) {
            if (b->entry[level][e].score10 > SCORE_MAX)
                return 0;
            if (e > 0 && b->entry[level][e].score10
                       > b->entry[level][e - 1].score10)
                return 0;          /* not descending */
        }
    }
    return 1;
}

u8 board_rank(const board_t *b, u8 level, u32 score10)
{
    u8 e;

    if (level >= BOARD_NLEVELS)
        return BOARD_NENTRIES;
    for (e = 0; e < BOARD_NENTRIES; e++)
        if (score10 > b->entry[level][e].score10)
            return e;              /* strictly greater: below equals */
    return BOARD_NENTRIES;
}

void board_insert(board_t *b, u8 level, u8 rank, const u8 init[BOARD_NINIT],
                  u32 score10)
{
    u8 e, j;

    if (level >= BOARD_NLEVELS || rank >= BOARD_NENTRIES)
        return;
    for (e = BOARD_NENTRIES - 1; e > rank; e--)
        b->entry[level][e] = b->entry[level][e - 1];
    for (j = 0; j < BOARD_NINIT; j++)
        b->entry[level][rank].init[j] = init[j];
    b->entry[level][rank].pad = 0;
    b->entry[level][rank].score10 = score10;
    b->sum = board_sum_bytes(b);
}
