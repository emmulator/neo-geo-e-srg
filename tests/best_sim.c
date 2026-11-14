/* best_sim: drive src/best.c from stdin, for tests/test_best.py.
 * The struct is serialized as exactly its 18 memory bytes in the 68000's
 * order (big-endian; the plan: "write the host sim so it gives the same
 * bytes"), one line of hex per state. Operations, one per line:
 *   R            best_reset
 *   U <lvl> <s>  best_update(level, score); prints "changed=" + return
 *   V            best_valid; prints "valid=" + return
 *   H            prints the state's 18 bytes as 18 "%02x " + "(18 bytes)"
 *   L <18 hex>   loads 18 bytes (big-endian) into the struct
 */
#include <stdio.h>
#include <stdlib.h>
#include "best.h"

/* the 18 bytes the 68000 stores: packed struct, big-endian fields */
static void get_bytes(const best_t *b, u8 out[18])
{
    u32 v;
    u8 i;

    v = b->magic;
    out[0] = (u8)(v >> 24); out[1] = (u8)(v >> 16);
    out[2] = (u8)(v >> 8);  out[3] = (u8)v;
    for (i = 0; i < BEST_NLEVELS; i++) {
        v = b->score10[i];
        out[4 + 4 * i] = (u8)(v >> 24);
        out[5 + 4 * i] = (u8)(v >> 16);
        out[6 + 4 * i] = (u8)(v >> 8);
        out[7 + 4 * i] = (u8)v;
    }
    out[16] = (u8)(b->sum >> 8);
    out[17] = (u8)b->sum;
}

static void put_bytes(best_t *b, const u8 in[18])
{
    u8 i;

    b->magic = ((u32)in[0] << 24) | ((u32)in[1] << 16)
             | ((u32)in[2] << 8) | in[3];
    for (i = 0; i < BEST_NLEVELS; i++)
        b->score10[i] = ((u32)in[4 + 4 * i] << 24)
                      | ((u32)in[5 + 4 * i] << 16)
                      | ((u32)in[6 + 4 * i] << 8) | in[7 + 4 * i];
    b->sum = (u16)(((u16)in[16] << 8) | in[17]);
}

int main(void)
{
    char line[128];
    char op;
    best_t b;
    u8 bytes[18];
    u8 i;

    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, " %c", &op) != 1) {
            fprintf(stderr, "bad line: %s", line);
            return 2;
        }
        if (op == 'R')
            best_reset(&b);
        else if (op == 'U') {
            unsigned level;
            unsigned long score;
            if (sscanf(line, " U %u %lu", &level, &score) != 2) {
                fprintf(stderr, "bad U: %s", line);
                return 2;
            }
            printf("changed=%u\n", best_update(&b, (u8)level, (u32)score));
        } else if (op == 'V')
            printf("valid=%u\n", best_valid(&b));
        else if (op == 'H') {
            get_bytes(&b, bytes);
            for (i = 0; i < 18; i++)
                printf("%02x%s", bytes[i], i < 17 ? " " : "");
            printf(" (%u bytes)\n", (unsigned)sizeof b);
        } else if (op == 'L') {
            unsigned v[18];
            if (sscanf(line, " L %x %x %x %x %x %x %x %x %x %x %x %x "
                             "%x %x %x %x %x %x",
                       &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6],
                       &v[7], &v[8], &v[9], &v[10], &v[11], &v[12], &v[13],
                       &v[14], &v[15], &v[16], &v[17]) != 18) {
                fprintf(stderr, "bad L: %s", line);
                return 2;
            }
            for (i = 0; i < 18; i++)
                bytes[i] = (u8)v[i];
            put_bytes(&b, bytes);
        } else {
            fprintf(stderr, "bad op: %s", line);
            return 2;
        }
    }
    return 0;
}
