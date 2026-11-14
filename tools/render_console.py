#!/usr/bin/env python3
"""render_console.py HEADER.h CON_C1 CON_C2 [--preview PNG [--over SNAPSHOT]]

The console: a dark control panel across the bottom of the screen, angled
up on both sides of the dome, so the player seems to sit at a desk in front
of it (the dome-scenery plan's console task). The radar sits on its left
wing, the integrity and lives on its right wing, the score in a slot in
the strip under the dome.

The shape (screen px, symmetric about x 160): the wings' top edge is at
y WING_Y from the screen's sides in to x EDGE_X0 (and 319 - EDGE_X0), then
slopes down to the strip's top, y STRIP_Y, at x EDGE_X1 (and 319 -
EDGE_X1); the strip runs under the dome between them to the bottom.

The picture is drawn in 16-px columns, each its own sprite (not a sticky
chain: the columns have different heights, and a column only spans the
tile rows it needs, which keeps the per-scanline sprite count down):

    the wing columns (0..5 and 13..19): tile rows from y WING_TOP
    the strip columns (6..12):          tile rows from y STRIP_TOP

both down to the bottom of the screen (y 223: the last row ends at 223,
224 - WING_TOP and 224 - STRIP_TOP are multiples of 16, so the rows tile
exactly to 224).

Everything on the panel lines up on one bottom line, y 215: the radar's
disc (src/radar.h RADAR_CY 206 + RY 8.4), the lives (fix row 28) and the
score (fix row 28); the integrity is fix row 26.

One 16-colour palette:

    0        transparent
    1, 2, 3  the body: deep (unused today), base, the bevel's lit face
    4        seams and recesses (near black)
    5, 6, 7  amber: the trim, its dim under-line, bright (unused today)
    8..15    unused (black)

The header (build/console_map.h) gives, per column, its top y and its tile
rows, and where its tiles start in the console part (the tiles are stored
column by column, top to bottom; the C side adds the part's C ROM base),
and the palette.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_scenery import SCREEN_H, SCREEN_W, TILE, encode_tile, rgb_to_neo15  # noqa: E402

WING_Y = 182            # the wings' top edge: 6 px over the HUD's display
EDGE_X0 = 80            # where the left wing's edge starts to slope down
EDGE_X1 = 104           # ... and where it meets the strip
STRIP_Y = 202           # the strip's top edge: under the dome's lowest pixel (198)
WING_TOP = 176          # the wing columns' first tile row (<= WING_Y)
STRIP_TOP = 192         # the strip columns' first tile row (<= STRIP_Y)
COLS = SCREEN_W // TILE
STRIP_COLS = range(EDGE_X1 // TILE, (SCREEN_W - EDGE_X1) // TILE)     # 6..12

PALETTE = [
    (255, 0, 255),                              # 0: transparent (key)
    (12, 11, 10), (22, 20, 18), (40, 36, 32),   # body: deep, base, bevel
    (4, 4, 4),                                  # seams, recesses
    (255, 140, 30), (130, 62, 10), (255, 200, 96),   # amber: trim, dim, bright
] + [(0, 0, 0)] * 8


def edge_y(x):
    """the panel's top edge at column x (float), symmetric about the centre."""
    x = np.minimum(x, SCREEN_W - 1 - x)
    t = np.clip((x - EDGE_X0) / (EDGE_X1 - EDGE_X0), 0, 1)
    return WING_Y + t * (STRIP_Y - WING_Y)


def console_picture():
    """(SCREEN_H, SCREEN_W) palette indices of the whole screen (0 above the
    panel)."""
    H, W = SCREEN_H, SCREEN_W
    img = np.zeros((H, W), np.uint8)
    xs = np.arange(W)
    top = np.round(edge_y(xs)).astype(int)
    yy = np.arange(H)[:, None]
    inside = yy >= top[None, :]
    depth = yy - top[None, :]                       # px below the edge
    img[inside] = 2                                 # one flat body colour
    img[inside & (depth >= 2) & (depth <= 3)] = 3   # the bevel's lit face
    img[inside & (depth == 1)] = 6                  # the trim's dim under-line
    img[inside & (depth == 0)] = 5                  # the amber trim

    def rect(x0, y0, x1, y1, k):
        img[y0:y1 + 1, x0:x1 + 1] = k

    def frame(x0, y0, x1, y1):
        """a window: the body's own colour inside (the HUD sits on the same
        black as the panel), a dark 1-px rim with cut corners, and the
        bevel's lit face along its bottom edge (the light comes from
        above)."""
        rect(x0 + 1, y0, x1 - 1, y0, 4)
        rect(x0, y0 + 1, x0, y1 - 1, 4)
        rect(x1, y0 + 1, x1, y1 - 1, 4)
        rect(x0 + 1, y0 + 1, x1 - 1, y1 - 1, 2)
        rect(x0 + 1, y1, x1 - 1, y1, 3)

    # the right wing's display for the integrity and the lives (fix rows 26
    # and 28: y 192..199 and 208..215, cols 32..37: x 256..303), and the
    # score's slot in the strip (row 28: y 208..215, cols 15..24: x
    # 120..199). The radar on the left wing brings its own disc.
    frame(250, 188, 309, 219)
    frame(116, 205, 203, 219)

    # screws at the wings' outer corners
    for sx, sy in ((4, 186), (W - 5, 186), (4, 219), (W - 5, 219)):
        img[sy, sx] = 4
        img[sy + 1, sx] = 3
    return img


def columns():
    """[(col, top_y, rows)] per column."""
    out = []
    for c in range(COLS):
        top = STRIP_TOP if c in STRIP_COLS else WING_TOP
        out.append((c, top, (SCREEN_H - top) // TILE))
    return out


def tiles(pic):
    out = []
    for c, top, rows in columns():
        for r in range(rows):
            y = top + r * TILE
            out.append(pic[y:y + TILE, c * TILE:(c + 1) * TILE])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("c1")
    ap.add_argument("c2")
    ap.add_argument("--preview")
    ap.add_argument("--over", help="a 320x224 snapshot to draw the panel over")
    args = ap.parse_args()

    pic = console_picture()
    cols = columns()
    assert all(top + rows * TILE == SCREEN_H for _, top, rows in cols)
    # nothing of the panel is outside the columns' tile rows
    for c, top, rows in cols:
        assert not pic[:top, c * TILE:(c + 1) * TILE].any(), c
    c1, c2 = bytearray(), bytearray()
    for t in tiles(pic):
        a, b = encode_tile(t)
        c1 += a
        c2 += b
    open(args.c1, "wb").write(bytes(c1))
    open(args.c2, "wb").write(bytes(c2))

    first, n = [], 0
    for _, _, rows in cols:
        first.append(n)
        n += rows
    packed = [0x8000] + [rgb_to_neo15(c) for c in PALETTE[1:]]
    with open(args.header, "w") as h:
        h.write("/* generated by tools/render_console.py: do not edit */\n")
        h.write("#ifndef CONSOLE_MAP_H\n#define CONSOLE_MAP_H\n")
        h.write(f"#define CON_COLS {COLS}\n#define CON_TILES {n}\n")
        h.write("/* column c: a sprite at x 16c, top y con_top[c], con_rows[c] tiles;\n"
                " * its tiles are the console part's con_first[c] .. + con_rows[c] - 1 */\n")
        for name, vals in (("con_top", [t for _, t, _ in cols]),
                           ("con_rows", [r for _, _, r in cols]),
                           ("con_first", first)):
            h.write(f"static const u8 {name}[CON_COLS] = {{\n  "
                    + ", ".join(str(v) for v in vals) + "\n};\n")
        h.write("static const u16 con_pal[16] = {\n  "
                + ", ".join(f"0x{w:04x}" for w in packed) + "\n};\n")
        h.write("#endif\n")
    if args.preview:
        if args.over:
            rgb = np.array(Image.open(args.over).convert("RGB"))
        else:
            rgb = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
            rgb[:] = (117, 182, 233)
        lut = np.array(PALETTE, np.uint8)
        hud = rgb.copy()
        m = pic != 0
        rgb[m] = lut[pic][m]
        # (a preview only) the fix layer and the radar draw over the panel:
        # put the snapshot's bright blue/white HUD and radar pixels back
        r, g, b = (hud[..., k].astype(int) for k in range(3))
        keep = m & (b > 120) & (b > r + 30) & (g > 80) | m & (r > 200) & (g > 200) & (b > 200)
        rgb[keep] = hud[keep]
        Image.fromarray(rgb).resize((SCREEN_W * 3, SCREEN_H * 3), Image.NEAREST).save(args.preview)


if __name__ == "__main__":
    main()
