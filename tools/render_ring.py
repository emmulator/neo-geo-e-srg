#!/usr/bin/env python3
"""render_ring.py SHEET.gif HEADER.h [--preview PNG]

The high-score initials ring (design docs/superpowers/specs/
2026-10-29-high-score-boards-design.md; the user's pick, 10-29: letters
only, the whole ring). E-SRG is a retro arcade video game; this is its
high-score entry art.

37 positions, in order: A-Z, space, . ! ? - & ', a star, a heart, the erase
arrow and END. Each is one 16 x 16 sprite tile: the game's 5 x 7 font
(tools/generate_srom.py FONT57, plus the board font's &, star and heart)
doubled to 10 x 14 with a 1-px black outline; END is small caps. Tile
RING_N is the pointer, a small white triangle under the front letter.

Colours (one 16-colour palette, three variants): 1 the outline, 2..6 the
glyph's top-to-bottom ramp. ring_pal[kind] is the palette for kind 0 (the
back half: dim gold), 1 (the front half: gold) and 2 (the front letter at
rest: white-hot; the pointer uses it too).

The ring's geometry is precomputed, so the runtime does no trigonometry:
the ring turns in RING_SUB steps per position (an animated step), so
RING_PHASES = RING_N * RING_SUB phases; phase p shows the ring turned p /
RING_SUB positions (position k at the front when p = k * RING_SUB). For
each phase and position: the sprite's screen x/y (top-left, screen pixels),
its SCB2 shrink word, its palette kind, and the positions' back-to-front
order (draw ring_order[p][0] in the lowest slot). Ring centre (160, 94),
radii 94 x 23 (the mockup's), the front at the ellipse's bottom; shrink
0.45 at the back to 1.0 at the front.

HEADER (build/ring_map.h): RING_N, RING_SUB, RING_PHASES, RING_TILES,
RING_POINTER (tile of the pointer), RING_ERASE / RING_END (the codes of the
last two positions), ring_code[RING_N] (the code a picked position stores:
ASCII, or TITLE2_STAR / TITLE2_HEART for the star and the heart),
ring_pal[3][16], ring_x/ring_y[RING_PHASES][RING_N] (s16), ring_scb2
[RING_PHASES][RING_N] (u16), ring_kind[RING_PHASES][RING_N] (u8),
ring_order[RING_PHASES][RING_N] (u8), RING_POINTER_X / RING_POINTER_Y.
Tile numbers are relative to the ring's C ROM part (0..RING_TILES-1).
TILES (this module) is the part's tile count.

The flying letter (the user's pick 10-30, "floaty", from the mockup
https://claude.ai/artifact/1tkdUiELoYjaNsXuFGqdVp): a picked letter's tile
leaves the ring's front (centre 160, 117) and lands on its initials slot
(the title font's glyph centre: x 140 + 16 slot, y 37 for row 6, columns
17/19/21) over FLY_FRAMES frames, on a quadratic curve through (sx + 0.15
(ex - sx), ey + 6), eased in and out (quadratic), shrinking from 1.0 to
0.68 (the title glyph's size). Frame f (1..FLY_FRAMES) is fly_x/fly_y
[slot][f - 1] (top-left, screen px) and fly_scb2[f - 1]; the white-hot
palette (kind 2). Header: FLY_FRAMES, fly_x/fly_y[3][FLY_FRAMES] (s16),
fly_scb2[FLY_FRAMES] (u16)."""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_srom as gs  # noqa: E402

ERASE, END = 0xfe, 0xff
RING = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + [' ', '.', '!', '?', '-', '&', "'",
                                              chr(gs.TITLE2_STAR), chr(gs.TITLE2_HEART), ERASE, END]
N = len(RING)
SUB = 6                                  # animation steps per position
PHASES = N * SUB
CX, CY, RX, RY = 160, 94, 94, 23
S_BACK = 0.45
TILES = N + 1
ARROW = [".....", "..#..", ".#...", "#####", ".#...", "..#..", "....."]
END_SMALL = ["###.#..#.##.", "#...##.#.#.#", "##..#.##.#.#", "#...#..#.#.#", "###.#..#.##."]
POINTER = ["#####", ".###.", "..#.."]
RAMPS = {   # kind -> the glyph ramp 2..6 (top to bottom)
    0: [(201, 168, 104), (184, 143, 72), (156, 115, 52), (128, 90, 36), (102, 69, 20)],
    1: [(255, 243, 200), (255, 222, 150), (255, 190, 92), (255, 156, 44), (232, 116, 20)],
    2: [(255, 255, 255), (255, 255, 255), (255, 246, 208), (255, 224, 138), (255, 192, 74)],
}


def glyph_rows(item):
    if item == ERASE:
        return ARROW, 2
    if item == END:
        return END_SMALL, 1
    return gs.TITLE2_FONT[item], 2


def tile(rows, sc):
    """16 x 16 indices: the glyph at scale sc, centred, ramp 2..6 by row,
    1-px black outline (colour 1) on its 8-neighbourhood."""
    h, w = len(rows) * sc, len(rows[0]) * sc
    oy, ox = (16 - h) // 2, (16 - w) // 2
    ink = np.zeros((16, 16), bool)
    out = np.zeros((16, 16), np.uint8)
    for y in range(h):
        for x in range(w):
            if rows[y // sc][x // sc] == '#':
                ink[oy + y, ox + x] = True
                out[oy + y, ox + x] = 2 + min(4, y * 5 // h)
    ring = np.zeros_like(ink)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ring |= np.roll(np.roll(ink, dy, 0), dx, 1)
    out[ring & ~ink] = 1
    return out


def sheet():
    tiles = [tile(*glyph_rows(it)) for it in RING] + [tile(POINTER, 1)]
    return np.vstack(tiles)


def geometry():
    xs, ys, scb2, kind, order = [], [], [], [], []
    for p in range(PHASES):
        pos = p / SUB
        row_x, row_y, row_s, row_k, zs = [], [], [], [], []
        for i in range(N):
            d = (i - pos) % N
            if d > N / 2:
                d -= N
            a = 2 * math.pi * d / N
            z = math.cos(a)
            s = S_BACK + (1 - S_BACK) * (z + 1) / 2
            hz = max(0, min(15, round(16 * s) - 1))
            v = max(0, min(255, round(256 * s) - 1))
            w, h = hz + 1, round(16 * (v + 1) / 256)
            cx, cy = CX + RX * math.sin(a), CY + RY * z
            row_x.append(int(round(cx - w / 2)))
            row_y.append(int(round(cy - h / 2)))
            row_s.append((hz << 8) | v)
            rest_front = p % SUB == 0 and i == p // SUB
            row_k.append(2 if rest_front else (1 if z >= 0 else 0))
            zs.append((z, i))
        xs.append(row_x); ys.append(row_y); scb2.append(row_s); kind.append(row_k)
        order.append([i for _, i in sorted(zs)])
    return xs, ys, scb2, kind, order


FLY_FRAMES = 20
FLY_S1 = 0.68


def fly_tables():
    xs, ys, scb2 = [[], [], []], [[], [], []], []
    for f in range(1, FLY_FRAMES + 1):
        t = f / FLY_FRAMES
        e = 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
        s = 1 - (1 - FLY_S1) * e
        hz = max(0, min(15, round(16 * s) - 1))
        v = max(0, min(255, round(256 * s) - 1))
        w, h = hz + 1, round(16 * (v + 1) / 256)
        scb2.append((hz << 8) | v)
        for slot in range(3):
            sx, sy, ex, ey = CX, CY + RY, 140 + 16 * slot, 37
            cx, cy = sx + (ex - sx) * 0.15, ey + 6
            u = 1 - e
            x = u * u * sx + 2 * u * e * cx + e * e * ex
            y = u * u * sy + 2 * u * e * cy + e * e * ey
            xs[slot].append(int(round(x - w / 2)))
            ys[slot].append(int(round(y - h / 2)))
    return xs, ys, scb2


def neo(rgb):
    return gs.neo_colour(rgb)


def palettes():
    out = []
    for k in (0, 1, 2):
        pal = [0x8000, neo((0, 0, 0))] + [neo(c) for c in RAMPS[k]] + [0] * 9
        out.append(pal)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("header")
    ap.add_argument("--preview")
    args = ap.parse_args()
    sh = sheet()
    im = Image.fromarray(sh, "P")
    flat = [0, 0, 0, 0, 0, 0] + [c for rgb in RAMPS[1] for c in rgb] + [0] * (3 * 249)
    flat[3:6] = [0, 0, 0]
    im.putpalette(flat[:768])
    im.save(args.sheet)
    xs, ys, scb2, kind, order = geometry()

    def table(name, ctype, rows):
        return (f"static const {ctype} {name}[RING_PHASES][RING_N] = {{\n" +
                ",\n".join("  {" + ",".join(map(str, r)) + "}" for r in rows) + "\n};\n")
    codes = [ERASE if it == ERASE else END if it == END else ord(it) for it in RING]
    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/render_ring.py: do not edit */\n"
          f"#define RING_N {N}\n#define RING_SUB {SUB}\n#define RING_PHASES {PHASES}\n"
          f"#define RING_TILES {TILES}\n#define RING_POINTER {N}\n"
          f"#define RING_ERASE {ERASE}\n#define RING_END {END}\n"
          f"#define RING_POINTER_X {CX - 8}\n#define RING_POINTER_Y {CY + RY + 9}\n"
          "/* the code a picked position stores */\n"
          f"static const u8 ring_code[RING_N] = {{{','.join(map(str, codes))}}};\n"
          "/* palettes: kind 0 back (dim), 1 front (gold), 2 the front letter at rest (hot) */\n"
          "static const u16 ring_pal[3][16] = {\n" +
          ",\n".join("  {" + ",".join("0x%04x" % c for c in p) + "}" for p in palettes()) + "\n};\n")
        w(table("ring_x", "s16", xs) + table("ring_y", "s16", ys) + table("ring_scb2", "u16", scb2) +
          table("ring_kind", "u8", kind) + table("ring_order", "u8", order))
        fx, fy, fs = fly_tables()
        w("/* the flying letter: frame f (1..FLY_FRAMES) of a pick into slot s */\n"
          f"#define FLY_FRAMES {FLY_FRAMES}\n"
          "static const s16 fly_x[3][FLY_FRAMES] = {\n" + ",\n".join("  {" + ",".join(map(str, r)) + "}" for r in fx) + "\n};\n"
          "static const s16 fly_y[3][FLY_FRAMES] = {\n" + ",\n".join("  {" + ",".join(map(str, r)) + "}" for r in fy) + "\n};\n"
          "static const u16 fly_scb2[FLY_FRAMES] = {" + ",".join(map(str, fs)) + "};\n")
    if args.preview:
        bg = Image.open(args.preview).convert("RGB") if os.path.exists(args.preview) else Image.new("RGB", (320, 224), (60, 110, 60))
        a = np.array(bg)
        for i in order[0]:
            t = sh[i * 16:(i + 1) * 16]
            hz, v = scb2[0][i] >> 8, scb2[0][i] & 255
            wpx, hpx = hz + 1, max(1, round(16 * (v + 1) / 256))
            small = np.array(Image.fromarray(t).resize((wpx, hpx), Image.NEAREST))
            ramp = RAMPS[kind[0][i]]
            for yy in range(hpx):
                for xx in range(wpx):
                    c = small[yy, xx]
                    if c:
                        Y, X = ys[0][i] + yy, xs[0][i] + xx
                        if 0 <= Y < 224 and 0 <= X < 320:
                            a[Y, X] = (0, 0, 0) if c == 1 else ramp[c - 2]
        Image.fromarray(a).resize((960, 672), Image.NEAREST).save(args.preview + ".out.png")


if __name__ == "__main__":
    main()
