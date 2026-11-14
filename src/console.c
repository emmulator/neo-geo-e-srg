/* console.c: see console.h. The panel is CON_COLS independent full-size
 * sprites (not a sticky chain: the wings' and the strip's columns have
 * different tops and heights, which a chain cannot carry). Column c sits at
 * x 16c, its own SCB3 top con_top[c] and con_rows[c] tiles tall, and its
 * SCB1 rows are the console part's con_first[c] .. + con_rows[c] - 1 tiles in
 * palette bank PAL_CON (10). Written once at a game start; nothing per frame.
 */
#include <ngdevkit/neogeo.h>
#include "console.h"

void console_show(void)
{
    u8 c, r, i;

    *REG_VRAMMOD = 0x200;
    for (c = 0; c < CON_COLS; c++) {
        /* the column's SCB1 tiles, top to bottom, in bank PAL_CON */
        *REG_VRAMMOD = 1;
        *REG_VRAMADDR = (u16)(ADDR_SCB1 + (CON_SPRITE + c) * 64);
        for (r = 0; r < con_rows[c]; r++) {
            *REG_VRAMRW = (u16)(CON_TILE_BASE + con_first[c] + r);
            *REG_VRAMRW = (u16)(PAL_CON << 8);
        }
        /* its own SCB2/SCB3/SCB4: full size, Y con_top[c] with con_rows[c]
         * tiles (sticky bit clear — each column is its own sprite), x 16c */
        *REG_VRAMMOD = 0x200;
        *REG_VRAMADDR = (u16)(ADDR_SCB2 + CON_SPRITE + c);
        *REG_VRAMRW = 0x0fff;                            /* full size */
        *REG_VRAMRW = (u16)(((496 - con_top[c]) << 7) | con_rows[c]);
        *REG_VRAMRW = (u16)((s16)(c * 16) << 7);
    }
    /* the palette bank: the panel's own colours */
    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_CON * 16 + i] = con_pal[i];
}

void console_hide(void)
{
    u8 c;

    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = (u16)(ADDR_SCB3 + CON_SPRITE);
    for (c = 0; c < CON_COLS; c++)
        *REG_VRAMRW = 0;                         /* height 0: not drawn */
}
