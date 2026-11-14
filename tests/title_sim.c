/* title_sim: drive src/title.c from stdin, for tests/test_title.py.
 * One line per call: "page level t best0 best1 best2 credits";
 * prints the 28 rows title_rows produced, one per line. */
#include <stdio.h>
#include "title.h"

int main(void)
{
    char line[64];
    unsigned page, level, t, b0, b1, b2, credits;
    u32 best[3];
    char rows[TITLE_ROWS][TITLE_COLS + 1];
    u8 i;

    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "%u %u %u %u %u %u %u", &page, &level, &t,
                   &b0, &b1, &b2, &credits) != 7) {
            fprintf(stderr, "bad line: %s", line);
            return 2;
        }
        best[0] = (u32)b0;
        best[1] = (u32)b1;
        best[2] = (u32)b2;
        title_rows((u8)page, (u8)level, (u16)t, best, (u8)credits, rows);
        for (i = 0; i < TITLE_ROWS; i++)
            printf("%s\n", rows[i]);
    }
    return 0;
}
