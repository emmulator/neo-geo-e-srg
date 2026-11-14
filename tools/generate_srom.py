#!/usr/bin/env python3
"""
Generate SROM (fixed layer tile) data for Neo Geo ROM.
The S-ROM format uses 8x8 pixel tiles with 4-bit color depth.
Each tile is 32 bytes, organized as 8 horizontal rows of 4 bytes each.
Each byte encodes two pixels: high nibble = pixels 4-7, low nibble = pixels 0-3
"""

import os


# 4x7 ASCII font bitmaps stored as 8-row tuples (row 7 is always 0 = descender/empty).
#
# Each row value is a 4-bit mask: bit3=col0 (leftmost), bit2=col1, bit1=col2, bit0=col3.
# A set bit means that pixel is ON (color index 1 = white from palette).
#
# Quick reference for common values:
#   15=XXXX  14=XXX.  13=XX.X  12=XX..
#   11=X.XX  10=X.X.   9=X..X   8=X...
#    7=.XXX   6=.XX.   5=.X.X   4=.X..
#    3=..XX   2=..X.   1=...X   0=....
ASCII_FONTS = {
    ' ': ( 0,  0,  0,  0,  0,  0,  0, 0),
    '!': ( 4,  4,  4,  4,  4,  0,  4, 0),  # .X.. repeated, gap, dot
    '"': (10, 10,  0,  0,  0,  0,  0, 0),  # X.X. twice at top
    '#': (10, 15, 10, 10, 15, 10,  0, 0),
    '$': ( 6, 11,  8,  6,  1, 13,  6, 0),  # S with center bar
    '%': ( 9,  1,  2,  4,  8,  9,  0, 0),
    '&': ( 6,  9, 10,  4, 11,  9,  6, 0),
    '\'':( 4,  4,  0,  0,  0,  0,  0, 0),
    '(': ( 2,  4,  8,  8,  8,  4,  2, 0),  # ..X. .X.. X... — curves right
    ')': ( 4,  2,  1,  1,  1,  2,  4, 0),
    '*': ( 0,  9,  6, 15,  6,  9,  0, 0),
    '+': ( 0,  4,  4, 15,  4,  4,  0, 0),
    ',': ( 0,  0,  0,  0,  4,  4,  8, 0),  # drops below baseline
    '-': ( 0,  0,  0, 15,  0,  0,  0, 0),
    '.': ( 0,  0,  0,  0,  0,  4,  4, 0),
    '/': ( 1,  1,  2,  4,  8,  8,  0, 0),
    '0': ( 6,  9,  9,  9,  9,  9,  6, 0),  # .XX. X..X ... X..X .XX.
    '1': ( 6,  4,  4,  4,  4,  4, 15, 0),  # .XX. top serif, .X.. stem, XXXX base
    '2': ( 6,  9,  1,  2,  4,  8, 15, 0),
    '3': ( 7,  1,  1,  7,  1,  1,  7, 0),  # .XXX — right-anchored
    '4': ( 9,  9, 15,  1,  1,  1,  1, 0),
    '5': (15,  8,  8, 14,  1,  1, 14, 0),
    '6': ( 6,  8,  8, 14,  9,  9,  6, 0),
    '7': (15,  1,  2,  4,  4,  4,  4, 0),
    '8': ( 6,  9,  9,  6,  9,  9,  6, 0),
    '9': ( 6,  9,  9,  7,  1,  1,  6, 0),
    ':': ( 0,  4,  4,  0,  4,  4,  0, 0),
    ';': ( 0,  4,  4,  0,  4,  4,  8, 0),
    '<': ( 2,  4,  8,  4,  2,  0,  0, 0),
    '=': ( 0,  0, 15,  0, 15,  0,  0, 0),
    '>': ( 4,  2,  1,  2,  4,  0,  0, 0),
    '?': ( 6,  9,  1,  2,  2,  0,  2, 0),
    '@': ( 6,  9, 11, 11, 10,  8,  6, 0),
    'A': ( 6,  9,  9, 15,  9,  9,  9, 0),  # .XX. top, XXXX crossbar
    'B': (14,  9,  9, 14,  9,  9, 14, 0),  # XXX. bumps, open right
    'C': ( 6,  9,  8,  8,  8,  9,  6, 0),  # .XX. X... X... X... .XX.
    'D': (14,  9,  9,  9,  9,  9, 14, 0),  # XXX. ... XXX.
    'E': (15,  8,  8, 14,  8,  8, 15, 0),  # XXXX top/bot, XXX. mid
    'F': (15,  8,  8, 14,  8,  8,  8, 0),
    'G': ( 6,  9,  8, 11,  9,  9,  7, 0),  # C shape + right inner bar
    'H': ( 9,  9,  9, 15,  9,  9,  9, 0),  # X..X bars, XXXX crossbar
    'I': (14,  4,  4,  4,  4,  4, 14, 0),  # XXX. serifs, .X.. stem
    'J': ( 3,  1,  1,  1,  9,  9,  6, 0),  # ..XX top, curves left at bottom
    'K': ( 9, 10, 12,  8, 12, 10,  9, 0),  # X..X X.X. XX.. — diagonal
    'L': ( 8,  8,  8,  8,  8,  8, 15, 0),  # X... stem, XXXX base
    'M': ( 9, 15, 15,  9,  9,  9,  9, 0),  # X..X peaks XXXX XXXX
    'N': ( 9, 13, 13, 11, 11,  9,  9, 0),  # X..X XX.X XX.X X.XX X.XX X..X
    'O': ( 6,  9,  9,  9,  9,  9,  6, 0),  # .XX. oval
    'P': (14,  9,  9, 14,  8,  8,  8, 0),  # P bump top half only
    'Q': ( 6,  9,  9,  9, 11,  9,  7, 0),  # O with tail bottom-right
    'R': (14,  9,  9, 14, 10,  9,  9, 0),  # P + diagonal leg
    'S': ( 7,  8,  8,  6,  1,  1, 14, 0),  # .XXX top, .XX. mid, XXX. bot
    'T': (15,  4,  4,  4,  4,  4,  4, 0),  # XXXX top, .X.. stem
    'U': ( 9,  9,  9,  9,  9,  9,  6, 0),  # X..X bars, .XX. base
    'V': ( 9,  9,  9,  9,  6,  6,  6, 0),  # X..X → .XX. converge
    'W': ( 9,  9,  9, 11, 15, 13,  9, 0),  # X..X → X.XX → XXXX → XX.X
    'X': ( 9,  9,  6,  6,  6,  9,  9, 0),  # X..X cross .XX.
    'Y': ( 9,  9,  6,  4,  4,  4,  4, 0),  # X..X → .XX. → .X.. stem
    'Z': (15,  1,  2,  4,  8,  8, 15, 0),  # XXXX ...X ..X. .X.. X... XXXX
    '[': ( 6,  4,  4,  4,  4,  4,  6, 0),  # .XX. .X.. .X.. .XX.
    '\\':(8,  8,  4,  4,  2,  1,  1, 0),
    ']': ( 6,  2,  2,  2,  2,  2,  6, 0),
    '^': ( 4, 10,  0,  0,  0,  0,  0, 0),  # .X.. X.X.
    '_': ( 0,  0,  0,  0,  0,  0, 15, 0),
    '`': ( 8,  4,  0,  0,  0,  0,  0, 0),  # X... .X.. (top-left tick)
    'a': ( 0,  0,  7,  9,  7,  9,  7, 0),  # open top, .XXX arcs
    'b': ( 8,  8, 14,  9,  9,  9, 14, 0),  # X... stem + bump
    'c': ( 0,  0,  6,  9,  8,  9,  6, 0),
    'd': ( 1,  1,  7,  9,  9,  9,  7, 0),  # ...X stem + bump
    'e': ( 0,  0,  6,  9, 15,  8,  6, 0),  # crossbar then cut top-right
    'f': ( 3,  4,  4, 14,  4,  4,  4, 0),  # ..XX hook, .X.. stem, XXX. bar
    'g': ( 0,  0,  7,  9,  9,  7,  1,  6), # descends: ...X then .XX.
    'h': ( 8,  8, 14,  9,  9,  9,  9, 0),
    'i': ( 0,  4,  0,  4,  4,  4,  6, 0),  # dot, gap, stem
    'j': ( 0,  2,  0,  2,  2,  2, 10,  4), # dot, stem, hook, descends
    'k': ( 8,  9, 10, 12, 10,  9,  9, 0),
    'l': ( 4,  4,  4,  4,  4,  4,  6, 0),  # .X.. stem, .XX. base
    'm': ( 0,  0, 10, 15,  9,  9,  9, 0),  # X.X. XXXX X..X
    'n': ( 0,  0, 14,  9,  9,  9,  9, 0),
    'o': ( 0,  0,  6,  9,  9,  9,  6, 0),
    'p': ( 0,  0, 14,  9,  9, 14,  8,  8), # descends X...
    'q': ( 0,  0,  7,  9,  9,  7,  1,  1), # descends ...X
    'r': ( 0,  0, 11, 12,  8,  8,  8, 0),  # X.XX XX.. — hooked arm
    's': ( 0,  0,  7,  8,  6,  1, 14, 0),
    't': ( 4,  4, 15,  4,  4,  4,  3, 0),  # .X.. stem, XXXX bar, ..XX base
    'u': ( 0,  0,  9,  9,  9,  9,  7, 0),
    'v': ( 0,  0,  9,  9,  9,  6,  6, 0),
    'w': ( 0,  0,  9,  9, 11, 15,  9, 0),
    'x': ( 0,  0,  9,  6,  6,  6,  9, 0),
    'y': ( 0,  0,  9,  9,  7,  1,  6, 0),  # descends into .XX. (j-curve)
    'z': ( 0,  0, 15,  2,  4,  8, 15, 0),
    '{': ( 3,  4,  4,  8,  4,  4,  3, 0),  # ..XX .X.. X... .X.. ..XX
    '|': ( 4,  4,  4,  4,  4,  4,  4, 0),
    '}': (12,  2,  2,  1,  2,  2, 12, 0),  # XX.. ..X. ...X ..X. XX..
    '~': ( 0,  6,  9,  0,  0,  0,  0, 0),
}


# The game's text font (M8 art pass): 5 x 7, in the title logo's squared
# style. These glyphs replace the 4 x 7 ASCII_FONTS above for every
# character they cover (the rest — lowercase and rare punctuation, which
# the game never prints — keep the old glyphs). Each glyph is lit from the
# top like the logo: rows 0-1 colour 1, rows 2-3 colour 2, rows 4-5
# colour 3, row 6 colour 4, with a 1-pixel drop shadow (colour 5) down and
# to the right. '#' = on.
FONT57 = {
' ': [".....",".....",".....",".....",".....",".....","....."],
'A': [".###.","#...#","#...#","#####","#...#","#...#","#...#"],
'B': ["####.","#...#","#...#","####.","#...#","#...#","####."],
'C': [".####","#....","#....","#....","#....","#....",".####"],
'D': ["####.","#...#","#...#","#...#","#...#","#...#","####."],
'E': ["#####","#....","#....","####.","#....","#....","#####"],
'F': ["#####","#....","#....","####.","#....","#....","#...."],
'G': [".####","#....","#....","#.###","#...#","#...#",".###."],
'H': ["#...#","#...#","#...#","#####","#...#","#...#","#...#"],
'I': ["#####","..#..","..#..","..#..","..#..","..#..","#####"],
'J': ["..###","...#.","...#.","...#.","...#.","#..#.",".##.."],
'K': ["#...#","#..#.","#.#..","##...","#.#..","#..#.","#...#"],
'L': ["#....","#....","#....","#....","#....","#....","#####"],
'M': ["#...#","##.##","#.#.#","#.#.#","#...#","#...#","#...#"],
'N': ["#...#","##..#","#.#.#","#.#.#","#..##","#...#","#...#"],
'O': [".###.","#...#","#...#","#...#","#...#","#...#",".###."],
'P': ["####.","#...#","#...#","####.","#....","#....","#...."],
'Q': [".###.","#...#","#...#","#...#","#.#.#","#..#.",".##.#"],
'R': ["####.","#...#","#...#","####.","#..#.","#...#","#...#"],
'S': [".####","#....","#....",".###.","....#","....#","####."],
'T': ["#####","..#..","..#..","..#..","..#..","..#..","..#.."],
'U': ["#...#","#...#","#...#","#...#","#...#","#...#",".###."],
'V': ["#...#","#...#","#...#","#...#","#...#",".#.#.","..#.."],
'W': ["#...#","#...#","#...#","#.#.#","#.#.#","##.##","#...#"],
'X': ["#...#","#...#",".#.#.","..#..",".#.#.","#...#","#...#"],
'Y': ["#...#","#...#",".#.#.","..#..","..#..","..#..","..#.."],
'Z': ["#####","....#","...#.","..#..",".#...","#....","#####"],
'0': [".###.","#...#","#..##","#.#.#","##..#","#...#",".###."],
'1': ["..#..",".##..","..#..","..#..","..#..","..#..",".###."],
'2': [".###.","#...#","....#","...#.","..#..",".#...","#####"],
'3': ["####.","....#","....#",".###.","....#","....#","####."],
'4': ["#...#","#...#","#...#","#####","....#","....#","....#"],
'5': ["#####","#....","#....","####.","....#","....#","####."],
'6': [".###.","#....","#....","####.","#...#","#...#",".###."],
'7': ["#####","....#","...#.","..#..","..#..","..#..","..#.."],
'8': [".###.","#...#","#...#",".###.","#...#","#...#",".###."],
'9': [".###.","#...#","#...#",".####","....#","....#",".###."],
'-': [".....",".....",".....","####.",".....",".....","....."],
':': [".....","..#..","..#..",".....","..#..","..#..","....."],
'.': [".....",".....",".....",".....",".....","..#..","..#.."],
',': [".....",".....",".....",".....","..#..","..#..",".#..."],
'%': ["##..#","##..#","...#.","..#..",".#...","#..##","#..##"],
'(': ["...#.","..#..",".#...",".#...",".#...","..#..","...#."],
')': [".#...","..#..","...#.","...#.","...#.","..#..",".#..."],
'=': [".....",".....","#####",".....","#####",".....","....."],
'!': ["..#..","..#..","..#..","..#..","..#..",".....","..#.."],
'?': [".###.","#...#","....#","...#.","..#..",".....","..#.."],
'\'':["..#..","..#..",".....",".....",".....",".....","....."],
'/': ["....#","....#","...#.","..#..",".#...","#....","#...."],
'+': [".....","..#..","..#..","#####","..#..","..#..","....."],
'<': ["...#.","..#..",".#...","#....",".#...","..#..","...#."],
'>': [".#...","..#..","...#.","....#","...#.","..#..",".#..."],
'_': [".....",".....",".....",".....",".....",".....","#####"],
}


# the fix palette for the text, the icons and the logo (PAL_HUD): index ->
# RGB. 1..4 the font's top-lit gradient (1 also draws the icons and the old
# glyphs), 5 its shadow (also the logo's darkest fill), 6..9 the logo's fill
# from top to bottom (the dome's blues).
FIX_RGB = {
    1: (217, 247, 255), 2: (176, 233, 247), 3: (138, 211, 241), 4: (86, 182, 225),
    5: (22, 65, 117),
    6: (86, 182, 225), 7: (52, 152, 203), 8: (38, 117, 169), 9: (22, 86, 138),
}
ROW_COLOUR = (1, 1, 2, 2, 3, 3, 4)
SHADOW = 5


def font57_to_pixels(glyph):
    """a FONT57 glyph to a 64-pixel array: the gradient, then the shadow
    wherever the shadowed pixel is not itself part of the glyph."""
    px = [0] * 64
    for r in range(7):
        for c in range(5):
            if glyph[r][c] == '#' and r + 1 < 8 and c + 1 < 8:
                px[(r + 1) * 8 + c + 1] = SHADOW
    for r in range(7):
        for c in range(5):
            if glyph[r][c] == '#':
                px[r * 8 + c] = ROW_COLOUR[r]
    return px


# The title logo (M8 art pass): "E-SRG" in the FONT57 letterforms, each
# glyph pixel a 4 x 4 block, the letters one block apart. Every block pixel
# with no letter pixel above or to its left is lit (colour 1), one with none
# below or to its right takes the edge colour (3), and the inside is the
# fill, darkening from top to bottom (6..9). It is cut into LOGO_COLS x
# LOGO_ROWS fix tiles from LOGO_FIRST, row by row (src/title.h has the same
# numbers; title_rows writes the tile codes as the row's characters).
def _title_h(name):
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', 'src', 'title.h')) as f:
        return int(re.search(r'#define %s\s+(\d+)' % name, f.read()).group(1))


LOGO_FIRST = _title_h('LOGO_FIRST')
LOGO_COLS = _title_h('LOGO_COLS')
LOGO_ROWS = _title_h('LOGO_ROWS')
LOGO_X0, LOGO_Y0 = 5, 3     # the logo's offset in its tile block (centres it
                            # on the screen: the block starts at x 96, and
                            # clear of the top edge: the block starts at y 0)
LOGO_BLOCK = 4


def logo_pixels():
    """the logo as a (LOGO_ROWS*8) x (LOGO_COLS*8) grid of colour indices."""
    W, H = LOGO_COLS * 8, LOGO_ROWS * 8
    on = [[0] * W for _ in range(H)]
    x0 = LOGO_X0
    for ch in "E-SRG":
        g = FONT57[ch]
        for r in range(7):
            for c in range(5):
                if g[r][c] == '#':
                    for y in range(LOGO_BLOCK):
                        for x in range(LOGO_BLOCK):
                            on[LOGO_Y0 + r * LOGO_BLOCK + y][x0 + c * LOGO_BLOCK + x] = 1
        x0 += 6 * LOGO_BLOCK
    out = [[0] * W for _ in range(H)]
    top = LOGO_Y0
    bot = LOGO_Y0 + 7 * LOGO_BLOCK - 1
    for y in range(H):
        for x in range(W):
            if not on[y][x]:
                continue
            up = on[y - 1][x] if y else 0
            left = on[y][x - 1] if x else 0
            down = on[y + 1][x] if y + 1 < H else 0
            right = on[y][x + 1] if x + 1 < W else 0
            if not up or not left:
                out[y][x] = 1
            elif not down or not right:
                out[y][x] = 3
            else:
                out[y][x] = 6 + min(3, (y - top) * 4 // (bot - top + 1))
    return out


def logo_tiles():
    """the logo's tiles, LOGO_FIRST upward, row by row: (code, 64 pixels)."""
    g = logo_pixels()
    tiles = []
    for tr in range(LOGO_ROWS):
        for tc in range(LOGO_COLS):
            px = [g[tr * 8 + y][tc * 8 + x] for y in range(8) for x in range(8)]
            tiles.append((LOGO_FIRST + tr * LOGO_COLS + tc, px))
    return tiles


def neo_colour(rgb):
    """24-bit RGB -> the Neo Geo's 16-bit colour (the dark bit, then each
    channel's 5 bits: the low bit in 14..12, the top 4 in the nibbles)."""
    r, g, b = (v >> 3 for v in rgb)            # 5 bits each
    dark = 0
    lsb = ((r & 1) << 2) | ((g & 1) << 1) | (b & 1)
    return (dark << 15) | (lsb << 12) | ((r >> 1) << 8) | ((g >> 1) << 4) | (b >> 1)


def write_pal_header(path):
    """the fix palette as a C header: fix_pal[16] (entry 0 transparent)."""
    vals = [0x8000] + [neo_colour(FIX_RGB[i]) if i in FIX_RGB else 0 for i in range(1, 16)]
    with open(path, 'w') as f:
        f.write("/* generated by tools/generate_srom.py: the text/icon/logo fix palette */\n")
        f.write("static const u16 fix_pal[16] = {\n    ")
        f.write(", ".join("0x%04x" % v for v in vals))
        f.write("\n};\n")


def encode_srom_tile(pixels):
    """Encode 8x8 pixel array to Neo Geo SROM tile format (32 bytes).

    pixels: list of 64 ints (row-major), each a 4-bit color index (0-15)
    Output: 32 bytes grouped by column pairs in SROM order:
        Group 0 (bytes  0-7): columns (4,5) for rows 0-7
        Group 1 (bytes  8-15): columns (6,7) for rows 0-7
        Group 2 (bytes 16-23): columns (0,1) for rows 0-7
        Group 3 (bytes 24-31): columns (2,3) for rows 0-7

    Each byte = (pixel_at_col_b << 4) | pixel_at_col_a
    """
    tile = bytearray(32)
    i = 0
    # Column pair order: (4,5), (6,7), (0,1), (2,3)
    for xa, xb in ((4, 5), (6, 7), (0, 1), (2, 3)):
        for y in range(8):
            pixel_a = pixels[y * 8 + xa]
            pixel_b = pixels[y * 8 + xb]
            tile[i] = (pixel_b << 4) | pixel_a
            i += 1
    return bytes(tile)


def bitmask_to_pixels(pattern):
    """Convert 8 rows of 4-bit bitmasks to 64-element pixel array.

    Each row_mask is a byte where bits 3-0 (MSB=left) represent columns 0-3.
    A set bit = color index 1 ("on"), clear bit = color index 0 (transparent).
    Columns 4-7 are always empty (0).

    Args:
        pattern: tuple of 8 ints (one per row), each with bits 3-0 set

    Returns:
        List of 64 ints (row-major pixel array)
    """
    pixels = []
    for row_mask in pattern:
        # Extract bits MSB first (bit 3 = leftmost column)
        for bit in range(3, -1, -1):
            pixels.append(1 if (row_mask >> bit) & 1 else 0)
        # Columns 4-7 are empty
        pixels.extend([0, 0, 0, 0])
    return pixels


# HUD icons past the ASCII range (tile = number), drawn from the Vectrex's
# hud glyphs (vectrex-e-srg tools/gen_dome.py HUD_GLYPHS, a 4 x 6 grid per
# digit) at this font's scale (digits 4 x 7 px): 8-bit rows, bit 7 = the
# leftmost column, colour index 1, row 6 the baseline like the digits.
ICON_SHIP = 128     # a life: "ship" (0,0)-(4,0)-(2,5), filled (an outline
                    # this small reads as a bell; the game's ship is filled)
ICON_DOME = 129     # the integrity's label: "dome", an open arch
ICONS = {
    ICON_SHIP: (0b00000000,
                0b00100000,
                0b00100000,
                0b01110000,
                0b01110000,
                0b11111000,
                0b11111000,
                0b00000000),
    ICON_DOME: (0b00000000,
                0b00000000,
                0b00111000,
                0b01000100,
                0b10000010,
                0b10000010,
                0b10000010,
                0b00000000),
}


def icon_to_pixels(rows):
    """8 rows of 8-bit masks (bit 7 = leftmost) to a 64-pixel array."""
    return [1 if (r >> (7 - x)) & 1 else 0 for r in rows for x in range(8)]


def generate_ascii_tiles(output_path):
    """
    Generate SROM data with ASCII character tiles (codepoints 0-127).
    Uses a simple 5x7 pixel font with 1-pixel border.
    Pads the output to a valid Neo Geo SROM size (at least 16KB).

    Args:
        output_path: Path to write the SROM file
    """
    with open(output_path, 'wb') as f:
        # Generate tiles for ASCII 0-127 (128 characters)
        # Characters 0-31 are control codes, use empty patterns
        for char_code in range(128):
            char = chr(char_code)
            if char_code >= 32 and char in FONT57:
                pixels = font57_to_pixels(FONT57[char])
            elif char_code >= 32 and char in ASCII_FONTS:
                pixels = bitmask_to_pixels(ASCII_FONTS[char])
            else:
                # Control characters (0-31) and unknown: empty space
                pixels = [0] * 64
            f.write(encode_srom_tile(pixels))

        # Tiles 128.. : the HUD icons, the title logo, then zeros up to
        # tile 199
        logo = dict(logo_tiles())
        assert max(logo) < 200
        for code in range(128, 200):
            if code in ICONS:
                f.write(encode_srom_tile(icon_to_pixels(ICONS[code])))
            elif code in logo:
                f.write(encode_srom_tile(logo[code]))
            else:
                f.write(b'\x00' * 32)

    # Pad file to valid SROM size (at least 16KB, must be power of 2)
    min_size = 16384  # 16KB minimum (512 tiles at 32 bytes each)
    current_size = os.path.getsize(output_path)

    if current_size < min_size:
        padding_needed = min_size - current_size
        with open(output_path, 'ab') as f:
            f.write(b'\x00' * padding_needed)
        print(f"Padded SROM from {current_size} to {min_size} bytes")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Generate SROM data for Neo Geo ROM')
    parser.add_argument('-o', '--output', default='empty.s1', help='Output file path')
    parser.add_argument('--ascii', action='store_true', help='Generate ASCII character tiles')
    parser.add_argument('--pal-header', help='also write the fix palette as a C header')

    args = parser.parse_args()

    if not args.ascii:
        parser.error('--ascii is required (only ASCII generation is supported)')

    generate_ascii_tiles(args.output)
    if args.pal_header:
        write_pal_header(args.pal_header)

    print(f"Generated SROM: {args.output}")
