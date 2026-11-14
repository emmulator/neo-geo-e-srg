/* fix.h: text on the fix layer (40x32 tiles of 8x8; S ROM tile = ASCII code).
 *
 * The thick title font (high-score boards Task B4; GAME OVER Task G1) is
 * written by the one span writer here, not by copies: a text row's tile is
 * TITLE2_ROW_BASE + title2_idx[ch] * TITLE2_NPROF + title2_rprof[left] and
 * its cap row (the row below) uses TITLE2_CAP_BASE the same way, so a glyph's
 * 2-px black outline spills into its right neighbour's cell. The tables live
 * in build/title_font.h (tools/generate_srom.py --title2-header); src/fix.c
 * includes them once, builds the per-character pair table, and exports it,
 * and title/entry/GAME OVER all draw from that one table. The writer is a
 * static inline here (the table/init stay in fix.c) so flow.c's title_commit
 * keeps the same inlined per-cell loop it had before the move: the demo's
 * worst work span must not grow (the frame-mark boot test).
 */
#ifndef FIX_H
#define FIX_H
#include <ngdevkit/neogeo.h>
#include <ngdevkit/types.h>

#define FIX_COLS 40
#define FIX_ROWS 32

/* every thick span is the title/entry/GAME OVER text's bank, PAL_HUD 7, so
 * the writer folds it into the tile word (the old title_fix_span did too);
 * a per-call palette argument would make the 68000 shift/or every cell. */
#define FIX_TEXT_PAL 7

void fix_clear(void);                                   /* every tile blank */
void fix_text(u8 col, u8 row, u8 pal, const char *s);   /* left to right */
void fix_center(u8 row, u8 pal, const char *s);         /* centred on 40 columns */

/* the thick title font's per-character pair (high 16 = idx * NPROF, low 8 =
 * the character's own spill profile), and the row/cap bases; filled once by
 * fix_thick_init (flow_run calls it before the title's first frame). */
extern u32 fix_title2_pair[128];
extern u16 fix_row_base_value;
extern u16 fix_cap_base_value;

void fix_thick_init(void);

static inline u16 fix_thick_row_base(void)
{
    return fix_row_base_value;
}

static inline u16 fix_thick_cap_base(void)
{
    return fix_cap_base_value;
}

/* the pure tile formula: base + the character's glyph offset + the left
 * neighbour's spill profile. */
static inline u16 fix_thick_tile(u16 base, u8 ch, u8 left)
{
    return (u16)(base + (u16)(fix_title2_pair[ch] >> 16)
                 + (u16)(fix_title2_pair[left] & 0xff));
}

/* write the cells col0 .. col0+len-1 of one row in FIX_TEXT_PAL:
 * base 0 means the row's characters are the tile codes (the title's logo and
 * blank rows; TITLE_ROW_NONE 0xffff is the same ASCII-space path), the two
 * thick-font bases select the glyph/spill tables. The span
 * includes the cell after a line's last character, so that glyph's spill is
 * drawn too. FIXMAP is column-major, one write with VRAMMOD 32 steps a
 * column right; the loop carries the previous character's profile instead
 * of a second table load per cell. */
static inline void fix_span(u8 row, u16 base, const char *s, u8 col0, u8 len)
{
    u8 i;

    *REG_VRAMADDR = (u16)(ADDR_FIXMAP + ((u16)col0 << 5) + row);
    *REG_VRAMMOD = 32;
    if (base == fix_row_base_value || base == fix_cap_base_value) {
        u8 prof = (u8)(fix_title2_pair[(u8)(col0 ? s[col0 - 1] : ' ')] & 0xff);

        for (i = 0; i < len; i++) {
            u8 ch = (u8)s[col0 + i];
            u32 pair = fix_title2_pair[ch];

            *REG_VRAMRW = (u16)(((u16)FIX_TEXT_PAL << 12)
                                | (u16)(base + (u16)(pair >> 16) + prof));
            prof = (u8)(pair & 0xff);
        }
    } else {
        for (i = 0; i < len; i++)
            *REG_VRAMRW = (u16)(((u16)FIX_TEXT_PAL << 12)
                                | (u16)(base + (u8)s[col0 + i]));
    }
}
#endif
