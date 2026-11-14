/* fix.c: the fix layer is column-major: address = FIXMAP + col * 32 + row.
 *
 * Task B4's thick title font table lives here (moved out of flow.c by Task
 * G1) so flow.c's title/entry and hud.c's GAME OVER share one table and one
 * formula; see fix.h. The per-cell writer is the static inline there, so the
 * title's inlined loop keeps its pre-G1 frame time. */
#include <ngdevkit/neogeo.h>
#include "fix.h"
#include "title_font.h"      /* generated: TITLE2_* and the per-cell tables */

#define FIX_ENTRY(pal, tile) ((u16)(((u16)(pal) << 12) | (tile)))

/* each character's tile offset and its own spill profile packed into one
 * word (high 16 = title2_idx[c] * TITLE2_NPROF, low 8 = title2_rprof[c]),
 * built once per entry from the generated header. The inline writer then
 * does one long table load and carries the previous character's profile,
 * instead of a 68000 multiply (MULU.W is 38-70 cycles) and a second table
 * load; the title page turns and prompt flips sit on the demo's tightest
 * frames. 128 u32 = 512 bytes. */
u32 fix_title2_pair[128];
u16 fix_row_base_value;
u16 fix_cap_base_value;

void fix_thick_init(void)
{
    u8 i;

    fix_row_base_value = TITLE2_ROW_BASE;
    fix_cap_base_value = TITLE2_CAP_BASE;
    for (i = 0; i < 128; i++)
        fix_title2_pair[i] = ((u32)((u16)title2_idx[i] * TITLE2_NPROF) << 16)
                             | (u32)title2_rprof[i];
}

void fix_clear(void)
{
    u16 i;

    *REG_VRAMADDR = ADDR_FIXMAP;
    *REG_VRAMMOD = 1;
    for (i = 0; i < FIX_COLS * FIX_ROWS; i++)
        *REG_VRAMRW = FIX_ENTRY(0, ' ');
}

void fix_text(u8 col, u8 row, u8 pal, const char *s)
{
    *REG_VRAMADDR = ADDR_FIXMAP + ((u16)col << 5) + row;
    *REG_VRAMMOD = 32;                   /* next column, same row */
    while (*s)
        *REG_VRAMRW = FIX_ENTRY(pal, (u8)*s++);
}

void fix_center(u8 row, u8 pal, const char *s)
{
    u8 n = 0;
    const char *p = s;

    while (*p++)
        n++;
    fix_text((u8)((FIX_COLS - n) / 2), row, pal, s);
}
