#!/usr/bin/env python3
"""render_stars.py — the M5 Task 2 star field's tables.

    render_stars.py HEADER [TILE_C1 TILE_C2]

The 12 stars of the Vectrex's stars.s table (v1.0.0), mapped to the Neo
Geo screen by the task's formulas:

    x0 = round((x_v + 128) * 320 / 256)
    y  = round((DOME_Y - 4) - (y_v - 8) * 60 / 103)

`round` is round-half-up on the exact rational (what C's round() does for
these positive values): x0 = (5*(x_v+128)+2)//4, y = (DOME_Y-4) -
(120*(y_v-8)+103)//206. The band's bottom is DOME_Y - 4 (just above the
dome box's top), so when the HUD layout plan lifts the dome, the stars
lift with it — the band is y 8..68 at DOME_Y 72. The ties are stars 4 and 8
(x_v 42 and -6 -> 212.5 and 152.5): half-up gives 213 and 153.
tests/stars_model.py states this and holds the C to it; the generated
header's tables ARE the model's x0/y, so the check is against the same
numbers the cartridge compiles.

Each frame's x is (x0 - round(dome_angle * 320 / 240)) mod 320, one screen
width per dome turn, leftward as dome_angle grows. The generated header
carries only the per-star rest positions (x0, y); the per-frame formula
lives in the runtime (src/stars.c stars_pos), so the header is the art's
table and the code is the motion.

With TILE_C1/TILE_C2 the star's picture (one 16x16 tile: a 2x2 px dot at
the top-left in colour index 1 — so the sprite's X/Y ARE the dot's) is
written as new CROM content, one tile after the broken sheet (tile
BROKEN_TILE_BASE + BROKEN_TILES = 19137 today): u16 low bytes c1, high
bytes c2, then a star palette (index 1 = (120, 130, 160)) as a C array
emitted into the header. The tile numbers follow the C ROM layout
(tiletool's encode_crom_tile byte order, as tools/render_broken.py).

When only the header is requested, the header's STAR_TILE_BASE matches the
previous build; a build that reconverges the parts must regenerate it (the
Makefile's dependency on a stars stamp covers that).
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_broken as rb  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tests"))
import layout as lay  # noqa: E402

STARS = [(44, 29), (41, -50), (111, -11), (67, 119), (13, 42),
         (93, -81), (27, -34), (13, 71), (89, -6), (60, -124),
         (87, 28), (73, -52)]        # (y, x) Vectrex units, stars.s v1.0.0
COL = (120, 130, 160)                # the star's colour (the task's)
TILE = 16

# the star band's bottom is just above the dome box (the box's top, minus
# 4): the source of truth is src/dome.h's DOME_Y, read by tests/layout.py.
DOME_Y = lay.d.DOME_Y
BAND_BOTTOM = DOME_Y - 4            # 68 today


def x0(i):
    return (5 * (STARS[i][1] + 128) + 2) // 4


def y(i):
    return BAND_BOTTOM - (120 * (STARS[i][0] - 8) + 103) // 206


def neo(col):
    """ngdevkit paltool's rgb24_to_packed15 (as tools/render_missiles.py)."""
    r, g, b = [c >> 2 for c in col]
    dark = 1 if ((r & 1) + (g & 1) + (b & 1)) == 0 else 0
    r, g, b = r >> 1, g >> 1, b >> 1
    lsb = ((r & 1) << 2) | ((g & 1) << 1) | (b & 1)
    r, g, b = r >> 1, g >> 1, b >> 1
    return (dark << 15) | (lsb << 12) | (r << 8) | (g << 4) | b


def star_palette():
    """the star's palette bank: entry 0 transparent, entry 1 the star's
    (120, 130, 160), the rest unused. One bank per star (each star has its
    own palette, so a star's dot can never be recoloured by another)."""
    pal = [0x8000] + [neo(COL)] + [0] * 14
    return pal


def encode_tile():
    """the star tile's c1/c2 bytes (the 2x2 dot at the top-left)."""
    stone = [[0] * TILE for _ in range(TILE)]
    for r in range(2):
        for c in range(2):
            stone[r][c] = 1
    c1 = bytearray(64)
    c2 = bytearray(64)
    pos = 0
    for off in (8, 136, 0, 128):            # 8x8 sub-tile corner offset
        sy, sx = off // 16, off % 16
        for yy in range(8):
            p0 = p1 = p2 = p3 = 0
            for xx in range(8):
                px = stone[sy + yy][sx + xx]
                p0 |= (px & 1) << xx
                p1 |= ((px >> 1) & 1) << xx
                p2 |= ((px >> 2) & 1) << xx
                p3 |= ((px >> 3) & 1) << xx
            c1[pos] = p0
            c1[pos + 1] = p1
            c2[pos] = p2
            c2[pos + 1] = p3
            pos += 2
    return bytes(c1), bytes(c2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("tile_c1", nargs="?")
    ap.add_argument("tile_c2", nargs="?")
    args = ap.parse_args()

    tile_base = rb.TILE_BASE + rb.N_TILES   # one tile after the broken sheet
    table = [(x0(i), y(i)) for i in range(len(STARS))]
    assert len(STARS) == 12
    assert all(0 <= x <= 319 for x, _ in table)
    assert all(BAND_BOTTOM - 60 <= yy <= BAND_BOTTOM for _, yy in table), \
        (BAND_BOTTOM, table)
    assert [x for x, _ in table] == [196, 98, 146, 309, 213, 59,
                                     118, 249, 153, 5, 195, 95]
    assert 0 <= BAND_BOTTOM - max(120 * (s[0] - 8) + 103 for s in STARS) // 206 \
        and BAND_BOTTOM - min(120 * (s[0] - 8) + 103 for s in STARS) // 206 < 320
    assert [yy for _, yy in table] == [BAND_BOTTOM - 21, BAND_BOTTOM - 19,
                                       BAND_BOTTOM - 60, BAND_BOTTOM - 34,
                                       BAND_BOTTOM - 3, BAND_BOTTOM - 50,
                                       BAND_BOTTOM - 11, BAND_BOTTOM - 3,
                                       BAND_BOTTOM - 47, BAND_BOTTOM - 30,
                                       BAND_BOTTOM - 46, BAND_BOTTOM - 38]

    with open(args.header, "w") as h:
        h.write("/* generated by tools/render_stars.py: do not edit */\n")
        h.write("#ifndef STARS_MAP_H\n#define STARS_MAP_H\n")
        h.write("#define STARS_COUNT %d      /* the table's length (the "
                "Vectrex's 12) */\n" % len(STARS))
        h.write("#define STAR_TILE_BASE %d   /* one tile after the broken "
                "sheet (render_broken's TILE_BASE + N_TILES) */\n" % tile_base)
        h.write("/* the 12 stars of the Vectrex stars.s table (v1.0.0), mapped"
                " by the task's\n"
                "   formulas (x0 = round((xv+128)*320/256), y = round((DOME_Y"
                "-4)-(yv-8)*60/103),\n"
                "   round-half-up): x0[star], y[star] */\n")
        h.write("static const u16 star_x0[12] = {"
                + ", ".join(map(str, [x for x, _ in table])) + "};\n")
        h.write("static const u8 star_y[12] = {"
                + ", ".join(map(str, [yy for _, yy in table])) + "};\n")
        h.write("static const u16 star_pal[16] = {"
                + ", ".join("0x%04x" % p for p in star_palette())
                + "};\n")
        h.write("#endif\n")

    if args.tile_c1 and args.tile_c2:
        t1, t2 = encode_tile()
        with open(args.tile_c1, "wb") as f:
            f.write(t1)
        with open(args.tile_c2, "wb") as f:
            f.write(t2)
        print("star tile %d (%d bytes)" % (tile_base, len(t1)))
        print("star palette: 1 = 0x%04x (%s)" % (star_palette()[1], COL))
    print("headers written (%d bytes)" % os.path.getsize(args.header))


if __name__ == "__main__":
    main()
