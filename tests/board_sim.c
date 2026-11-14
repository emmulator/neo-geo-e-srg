/* board_sim: drive src/board.c from stdin, for tests/test_board.py.
 * The struct is serialized as exactly its 126 memory bytes in the 68000's
 * order (big-endian; the plan: "write the host sim so it gives the same
 * bytes"), one line of hex per state. Operations, one per line:
 *   R                          board_reset
 *   K <lvl> <s>                board_rank(level, score); prints "rank=" + return
 *   I <lvl> <rank> <b0> <b1> <b2> <s>
 *                              board_insert(level, rank, {b0,b1,b2}, score)
 *   V                          board_valid; prints "valid=" + return
 *   H                          prints the state's 126 bytes as 126 "%02x "
 *   L <126 hex>                loads 126 bytes (big-endian) into the struct
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "board.h"

/* the 126 bytes the 68000 stores: packed struct, big-endian fields. The
 * init bytes and the pad are single bytes (same either way). */
static void get_bytes(const board_t *b, u8 out[126])
{
    u8 level, e, j, k = 0;
    u32 v;

    v = b->magic;
    out[k++] = (u8)(v >> 24); out[k++] = (u8)(v >> 16);
    out[k++] = (u8)(v >> 8);  out[k++] = (u8)v;
    for (level = 0; level < BOARD_NLEVELS; level++) {
        for (e = 0; e < BOARD_NENTRIES; e++) {
            for (j = 0; j < BOARD_NINIT; j++)
                out[k++] = b->entry[level][e].init[j];
            out[k++] = b->entry[level][e].pad;
            v = b->entry[level][e].score10;
            out[k++] = (u8)(v >> 24); out[k++] = (u8)(v >> 16);
            out[k++] = (u8)(v >> 8);  out[k++] = (u8)v;
        }
    }
    out[k++] = (u8)(b->sum >> 8);
    out[k++] = (u8)b->sum;
}

static void put_bytes(board_t *b, const u8 in[126])
{
    u8 level, e, j, k = 0;

    b->magic = ((u32)in[0] << 24) | ((u32)in[1] << 16)
             | ((u32)in[2] << 8) | in[3];
    k = 4;
    for (level = 0; level < BOARD_NLEVELS; level++) {
        for (e = 0; e < BOARD_NENTRIES; e++) {
            for (j = 0; j < BOARD_NINIT; j++)
                b->entry[level][e].init[j] = in[k++];
            b->entry[level][e].pad = in[k++];
            b->entry[level][e].score10 = ((u32)in[k] << 24)
                                       | ((u32)in[k + 1] << 16)
                                       | ((u32)in[k + 2] << 8) | in[k + 3];
            k += 4;
        }
    }
    b->sum = (u16)(((u16)in[k] << 8) | in[k + 1]);
}

/* "L <126 hex>": parse the hex bytes after the op */
static int load_bytes(board_t *b, const char *line)
{
    const char *p = strchr(line, 'L');
    u8 in[126];
    int i;

    if (!p)
        return 0;
    p++;
    for (i = 0; i < 126; i++) {
        char *end;
        unsigned long v = strtoul(p, &end, 16);

        if (end == p)
            return 0;
        in[i] = (u8)v;
        p = end;
    }
    put_bytes(b, in);
    return 1;
}

int main(void)
{
    char line[1024];
    char op;
    board_t b;
    u8 bytes[126];
    u8 i;

    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, " %c", &op) != 1) {
            fprintf(stderr, "bad line: %s", line);
            return 2;
        }
        if (op == 'R')
            board_reset(&b);
        else if (op == 'K') {
            unsigned level;
            unsigned long score;
            if (sscanf(line, " K %u %lu", &level, &score) != 2) {
                fprintf(stderr, "bad K: %s", line);
                return 2;
            }
            printf("rank=%u\n", board_rank(&b, (u8)level, (u32)score));
        } else if (op == 'I') {
            unsigned level, rank;
            unsigned i0, i1, i2;
            unsigned long score;
            u8 init[BOARD_NINIT];
            if (sscanf(line, " I %u %u %x %x %x %lu",
                       &level, &rank, &i0, &i1, &i2, &score) != 6) {
                fprintf(stderr, "bad I: %s", line);
                return 2;
            }
            init[0] = (u8)i0; init[1] = (u8)i1; init[2] = (u8)i2;
            board_insert(&b, (u8)level, (u8)rank, init, (u32)score);
        } else if (op == 'V')
            printf("valid=%u\n", board_valid(&b));
        else if (op == 'H') {
            get_bytes(&b, bytes);
            for (i = 0; i < 126; i++)
                printf("%02x%s", bytes[i], i < 125 ? " " : "");
            printf(" (%u bytes)\n", (unsigned)sizeof b);
        } else if (op == 'L') {
            if (!load_bytes(&b, line)) {
                fprintf(stderr, "bad L: %s", line);
                return 2;
            }
        } else {
            fprintf(stderr, "bad op: %s", line);
            return 2;
        }
    }
    return 0;
}
