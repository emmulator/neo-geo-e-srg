/* fix.h: text on the fix layer (40x32 tiles of 8x8; S ROM tile = ASCII code). */
#ifndef FIX_H
#define FIX_H
#include <ngdevkit/types.h>

#define FIX_COLS 40
#define FIX_ROWS 32

void fix_clear(void);                                   /* every tile blank */
void fix_text(u8 col, u8 row, u8 pal, const char *s);   /* left to right */
void fix_center(u8 row, u8 pal, const char *s);         /* centred on 40 columns */
#endif
