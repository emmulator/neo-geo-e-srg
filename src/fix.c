/* fix.c: the fix layer is column-major: address = FIXMAP + col * 32 + row. */
#include <ngdevkit/neogeo.h>
#include "fix.h"

#define FIX_ENTRY(pal, tile) ((u16)(((u16)(pal) << 12) | (tile)))

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
