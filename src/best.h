/* best.h: the per-level high-score table (M6 Task 8). Pure logic, no
 * hardware: host-built as build/best_sim and held to tests/best_model.py
 * by tests/test_best.py, exactly like title.c. The cart object is built
 * and linked (SRCS picks src/best.c up) but unused until Task 9 keeps
 * flow_best in backup RAM and shows it on the title.
 *
 * The struct is 18 bytes, packed so the 68000's layout (big-endian, no
 * padding) is exactly what the host build sees: u32 magic + u32
 * score10[3] + u16 sum. sum is the 16-bit wrap-around sum of the 16
 * bytes before it, read as bytes in memory order. best.c runs only at
 * GAME OVER and at an entry, never per frame, so its u32 arithmetic
 * (which compiles to libgcc calls on the 68000) is allowed.
 */
#ifndef BEST_H
#define BEST_H
#include <ngdevkit/types.h>

#define BEST_NLEVELS 3
#define BEST_MAGIC   0x45535247UL  /* 'ESRG', ASCII big-endian */

typedef struct {
    u32 magic;          /* BEST_MAGIC: identifies a table, not garbage */
    u32 score10[3];     /* per level (EASY, NORMAL, HARD), score / 10 */
    u16 sum;            /* 16-bit wrap-around byte sum of the 16 bytes above */
} __attribute__((packed)) best_t;

/* a fresh table: magic set, all three scores 0, sum fixed. */
void best_reset(best_t *b);

/* 1 if the magic and the sum are right and every score is <= SCORE_MAX
 * (9,999,999, src/missiles.h), else 0. */
u8 best_valid(const best_t *b);

/* keeps the higher of the stored and given score for that level, fixes
 * the sum when it stores, and returns 1 only if the stored score changed.
 * level > 2 changes nothing and returns 0. */
u8 best_update(best_t *b, u8 level, u32 score10);

#endif
