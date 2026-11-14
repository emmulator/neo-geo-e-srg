/* title_sim: drive src/title.c from stdin, for tests/test_title.py.
 * One line per call: "page level t credits <126 board bytes as hex>"
 * where the hex is the packed board_model.Board image (big-endian, as the
 * 68000 stores it). The bytes are decoded field by field into the host's
 * board_t (whose u32s are little-endian), then the TITLE_ROWS rows
 * title_rows produced are printed, one per line. */
#include <stdio.h>
#include <string.h>
#include "title.h"

int main(void)
{
    char line[512];
    unsigned page, level, t, credits;
    board_t b;
    char rows[TITLE_ROWS][TITLE_COLS + 1];
    u8 i, l, e, j;

    while (fgets(line, sizeof line, stdin)) {
        u8 image[sizeof b];
        int off = 0;

        if (sscanf(line, "%u %u %u %u %n", &page, &level, &t, &credits,
                   &off) != 4) {
            fprintf(stderr, "bad line: %s", line);
            return 2;
        }
        {
            char *s = line + off;

            for (i = 0; i < sizeof image; i++) {
                unsigned v;
                int n = 0;

                while (*s == ' ')
                    s++;
                if (sscanf(s, "%2x%n", &v, &n) != 1) {
                    fprintf(stderr, "bad board byte %u: %s", i, line);
                    return 2;
                }
                image[i] = (u8)v;
                s += n;
            }
        }
        /* decode the 68000's big-endian entry fields into the host struct */
        memset(&b, 0, sizeof b);
        for (l = 0; l < BOARD_NLEVELS; l++) {
            for (e = 0; e < BOARD_NENTRIES; e++) {
                const u8 *p = image + 4 + (l * BOARD_NENTRIES + e) * 8;

                for (j = 0; j < BOARD_NINIT; j++)
                    b.entry[l][e].init[j] = p[j];
                b.entry[l][e].pad = 0;
                b.entry[l][e].score10 = ((u32)p[4] << 24)
                    | ((u32)p[5] << 16) | ((u32)p[6] << 8) | (u32)p[7];
            }
        }
        title_rows((u8)page, (u8)level, (u16)t, &b, (u8)credits, rows);
        for (i = 0; i < TITLE_ROWS; i++)
            printf("%s\n", rows[i]);
    }
    return 0;
}
