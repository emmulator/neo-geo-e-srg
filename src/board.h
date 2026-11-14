/* board.h: the five-entry per-level high-score board (high-score boards
 * Task B1). Pure logic, no hardware: host-built as build/board_sim and held
 * to tests/board_model.py by tests/test_board.py. Task B2 keeps it in
 * flow_board in backup RAM and on the AES memory card.
 *
 * board_t is packed, 126 bytes, and its byte offsets are the same on the
 * 68000 and the host:
 *   0        u32 magic 'ESR2' = 0x45535232, bytes 45 53 52 32
 *   4        entries: BOARD_NLEVELS levels x BOARD_NENTRIES entries, each
 *            entry 8 bytes:
 *              +0  init[3]    the three initials (ASCII, or the title
 *                             font's star/heart codes; spaces pad a short
 *                             name)
 *              +3  pad        0: keeps score10 at an even offset on the
 *                             68000 (a 32-bit access at an odd address
 *                             faults)
 *              +4  u32 score10  the entry's score / 10
 *   124      u16 sum   the 16-bit wrap-around sum of bytes 0..123 (the
 *                      whole board before the sum), byte-wise like the old
 *                      best_t table
 * The 68000's big-endian field bytes and the host's little-endian ones sum
 * to the same value (addition is commutative), so both builds agree on the
 * sum. board.c runs only at GAME OVER, at END and at an entry, never per
 * frame, so its u32 arithmetic (libgcc calls on the 68000) is allowed.
 *
 * The default entries, on every level, are the spec's displayed scores:
 *   SRG 50,000  HEX 40,000  DOM 30,000  ZAP 20,000  VEC 10,000
 * stored as score/10 (5000, 4000, 3000, 2000, 1000) and shown x 10, the
 * title's existing best-line convention.
 */
#ifndef BOARD_H
#define BOARD_H
#include <ngdevkit/types.h>

#define BOARD_NLEVELS 3
#define BOARD_NENTRIES 5
#define BOARD_NINIT   3
#define BOARD_MAGIC   0x45535232UL  /* 'ESR2', ASCII big-endian */

typedef struct {
    u8  init[BOARD_NINIT];  /* the initials; 1/2 = the star/heart codes */
    u8  pad;                /* 0: keeps score10 at an even 68000 address */
    u32 score10;            /* score / 10 */
} __attribute__((packed)) board_entry_t;

typedef struct {
    u32 magic;                                       /* BOARD_MAGIC */
    board_entry_t entry[BOARD_NLEVELS][BOARD_NENTRIES];
    u16 sum;            /* byte sum of everything before it, 16-bit wrap */
} __attribute__((packed)) board_t;

/* a fresh board: magic set, every level's five default entries, sum fixed */
void board_reset(board_t *b);

/* 1 iff the magic and sum are right, every score is <= SCORE_MAX
 * (9,999,999, src/missiles.h), and each level's entries are descending.
 * Initials are any bytes (the title font draws the star/heart codes). */
u8 board_valid(const board_t *b);

/* the rank 0..BOARD_NENTRIES-1 of score10 on that level, or BOARD_NENTRIES
 * when it does not qualify: a score qualifies only if it is strictly
 * greater than an entry, so it goes below equal scores. level >= 3 -> 5. */
u8 board_rank(const board_t *b, u8 level, u32 score10);

/* insert at rank (0..4): shifts the entries below it down, drops the 5th,
 * stores init and score10, and fixes the sum. level >= 3 or rank >= 5
 * leaves the board unchanged. */
void board_insert(board_t *b, u8 level, u8 rank, const u8 init[BOARD_NINIT],
                  u32 score10);

#endif
