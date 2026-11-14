#!/usr/bin/env python3
"""render_ripple.py HEADER.h GROUND_C1 GROUND_C2 [--preview GIF]

The grass's ripple (the dome-scenery plan's Task 19): the ground's texture
slides with the camera as the dome turns, by palette rotation alone. No
sprite moves and no tile is rewritten. This replaces render_scenery.py's
ground part (the same block of GROUND_COLS x GROUND_ROWS tiles at y
GROUND_Y) and writes the same header, build/ground_map.h, with the ripple's
tables added. render_scenery.ground_picture() stays the grass's picture
(the props' shadow colours and the mountains' foot read it); this module
only re-indexes it.

Each 16-px tile row r is snapped to its two most common shades, a and b (a
pixel takes the nearer of the two), and keeps its dome-shadow twin. Each
pixel also gets a ripple phase p 0..2, which steps every RIPPLE_D px:

    across rows (every row but the three beside the dome):
        p = floor((x + gy(y)) / D) mod 3, gy a small wave in y, so the
        9-px ripple is not straight stripes
    up-down rows (SIDE_ROWS, y 148..195, beside the dome, where the ground
        moves mostly toward or away from the camera):
        p = floor((y + gx(x)) / D) mod 3

So a tile's pixel index is 1 + 6 * slot + 3 * twin + p (1..12; slot 0 = a,
1 = b; twin 1 = in the dome's shadow).

Every tile row is one palette BANK (the up-down rows are two: the left half,
columns 0..9, and the right, 10..19, which move opposite ways): RIPPLE_BANKS
banks, tile (col, row) in bank ground_bank[col][row]. Bank k's entry for
(slot, twin, p) is the shade's colour times 1 + AMP * WAVE[(p + o) mod 3]
(WAVE = +1, 0, -1; AMP 2.5%), through the hardware's 15-bit format, where
o is the bank's rotation 0..2. Rotating o by one slides the bank's ripple
by D px.

Each bank turns at the speed its visible grass (not under the dome or the
console) really moves, in px per dome step: the mean over its pixels, from
the dome's own camera (sideways for the across rows, up-down for the
others). The rotation at dome angle da is o = round(-v * da / D) mod 3. v
is snapped to a multiple of 3 * D / 240 so that o(240) = o(0): a whole
turn ends where it began, with no jump at the wrap.

The header adds:

    RIPPLE_BANKS                  the banks (11)
    ground_bank[GROUND_COLS][GROUND_ROWS]   u8: a tile's bank 0..RIPPLE_BANKS-1
    ground_ripple_pal[RIPPLE_BANKS][2][3][16]  u16: [k][0 dome whole /
                                  1 dome gone (each twin = its plain shade)]
                                  [rotation o][entry]; entry 0 is 0x8000,
                                  13..15 unused (black)
    ground_ripple_rot[RIPPLE_BANKS][240]  u8: o at each dome angle

and keeps render_scenery's ground_pal / ground_pal_noshadow (the plain
grass, before the ripple) for the checkers that read them.
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
import render_scenery as rs  # noqa: E402
import render_console as rc  # noqa: E402
from render_scenery import (GROUND_COLS, GROUND_ROWS, GROUND_Y, NSHADES,  # noqa: E402
                            SCREEN_H, SCREEN_W, TILE, encode_tile, rgb_to_neo15)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from layout import d as lay  # noqa: E402

NDA = g.STEPS                       # 240
NPH = 3                             # ripple phases
RIPPLE_D = 3                        # px per phase: a 9-px ripple
AMP = 0.025                         # +-2.5% brightness (the user's pick, 10-25)
WAVE = (1.0, 0.0, -1.0)
SIDE_ROWS = (3, 4, 5)               # y 148..195: up-down, two banks each
V_STEP = NPH * RIPPLE_D / NDA       # 0.0375 px a step: whole turns end in phase


def gy(y):
    return 2.5 * np.sin(y / 2.3) + 1.2 * np.sin(y / 0.9 + 1.0)


def banks():
    """[(row, cols, axis)] per bank: axis 0 across, 1 up-down."""
    out = []
    for r in range(GROUND_ROWS):
        if r in SIDE_ROWS:
            out.append((r, range(0, 10), 1))
            out.append((r, range(10, 20), 1))
        else:
            out.append((r, range(0, 20), 0))
    return out


def cover():
    """(SCREEN_H, SCREEN_W) bool: the ground hidden under the dome or the
    console (render_props.dome_mask: the dome at any angle)."""
    import render_props as rp
    return rp.dome_mask() | (rc.console_picture() != 0)


def speed_maps():
    """(across, up-down): per screen pixel of the ground, px per dome step,
    NaN where no ground point lands (from the dome's camera at da 0 -> 1)."""
    f = g.fit()
    y0 = math.cos(math.radians(g.CAP_DEG))
    xs, zs = np.meshgrid(np.linspace(-8, 8, 1600), np.linspace(-14, 2.3, 2000))
    P = np.stack([xs.ravel(), np.full(xs.size, y0), zs.ravel()], 1)
    pos, fwd, _, _ = g.camera()
    P = P[((P - pos) @ fwd) > 0.3]
    a = g.to_px(g.project(P, 0)[0], f)
    b = g.to_px(g.project(P, 1)[0], f)
    X = np.floor(lay.DOME_X + a[:, 0]).astype(int)
    Y = np.floor(lay.DOME_Y + a[:, 1]).astype(int)
    sel = (X >= 0) & (X < SCREEN_W) & (Y >= GROUND_Y) & (Y < SCREEN_H)
    out = []
    for axis in (0, 1):
        sp = np.full((SCREEN_H, SCREEN_W), np.nan)
        sp[Y[sel], X[sel]] = (b[:, axis] - a[:, axis])[sel]
        out.append(sp)
    return out


def bank_speeds():
    """per bank: the mean speed of its visible grass, snapped to V_STEP."""
    sp = speed_maps()
    cov = cover()
    out = []
    for r, cols, axis in banks():
        m = np.zeros((SCREEN_H, SCREEN_W), bool)
        y1 = min(SCREEN_H, GROUND_Y + (r + 1) * TILE)
        m[GROUND_Y + r * TILE:y1, cols.start * TILE:cols.stop * TILE] = True
        v = sp[axis][m & ~cov]
        v = v[~np.isnan(v)]
        mean = float(v.mean()) if len(v) else 0.0
        out.append(round(mean / V_STEP) * V_STEP)
    return out


def ripple_picture():
    """(GROUND_ROWS*16, SCREEN_W) indices 1..12, the two main shades per row
    [(a, b)], and the bank of each tile [col][row]."""
    pic = rs.ground_picture()
    H = GROUND_ROWS * TILE
    twin = (pic > NSHADES).astype(int)
    shade = np.where(twin == 1, pic - NSHADES, pic)
    yy, xx = np.mgrid[0:H, 0:SCREEN_W]
    across = np.floor((xx + gy(yy)) / RIPPLE_D).astype(int) % NPH
    updown = np.floor((yy + gy(xx)) / RIPPLE_D).astype(int) % NPH
    out = np.zeros(pic.shape, np.uint8)
    maj = []
    bank_of = np.zeros((GROUND_COLS, GROUND_ROWS), int)
    for k, (r, cols, axis) in enumerate(banks()):
        for c in cols:
            bank_of[c, r] = k
    for r in range(GROUND_ROWS):
        rows = slice(r * TILE, (r + 1) * TILE)
        blk = shade[rows]
        vals, cnt = np.unique(blk, return_counts=True)
        a, b = sorted(vals[np.argsort(cnt)[-2:]]) if len(vals) > 1 else (vals[0], vals[0])
        maj.append((int(a), int(b)))
        slot = np.where(np.abs(blk - a) <= np.abs(blk - b), 0, 1)
        ph = updown[rows] if r in SIDE_ROWS else across[rows]
        out[rows] = 1 + 6 * slot + 3 * twin[rows] + ph
    return out, maj, bank_of


def bank_palettes(maj):
    """[bank][0 whole / 1 gone][o][16] words."""
    pal = rs.palette_rgb()
    out = []
    for r, _cols, _axis in banks():
        a, b = maj[r]
        per = []
        for gone in (0, 1):
            rots = []
            for o in range(NPH):
                w = [0x8000] + [0] * 15
                for slot, s in enumerate((a, b)):
                    for tw in (0, 1):
                        base = np.array(pal[s + (NSHADES if tw and not gone else 0)], float)
                        for p in range(NPH):
                            c = np.clip(base * (1 + AMP * WAVE[(p + o) % NPH]), 0, 255)
                            w[1 + 6 * slot + 3 * tw + p] = rgb_to_neo15(tuple(int(round(v)) for v in c))
                rots.append(w)
            per.append(rots)
        out.append(per)
    return out


def rotations(speeds):
    return [[int(round(-v * da / RIPPLE_D)) % NPH for da in range(NDA)] for v in speeds]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("c1")
    ap.add_argument("c2")
    ap.add_argument("--preview", help="an animated GIF of the ground alone over a whole turn")
    args = ap.parse_args()

    pic, maj, bank_of = ripple_picture()
    speeds = bank_speeds()
    pals = bank_palettes(maj)
    rots = rotations(speeds)
    for k, rot in enumerate(rots):
        # a whole turn ends where it began
        assert int(round(-speeds[k] * NDA / RIPPLE_D)) % NPH == rot[0], k
    c1, c2 = bytearray(), bytearray()
    for t in rs.tiles(pic):
        a, b = encode_tile(t)
        c1 += a
        c2 += b
    open(args.c1, "wb").write(bytes(c1))
    open(args.c2, "wb").write(bytes(c2))

    plain = rs.palette_rgb()
    packed = [0x8000] + [rgb_to_neo15(c) for c in plain[1:]]
    noshadow = list(packed)
    for k in range(1, NSHADES + 1):
        noshadow[k + NSHADES] = packed[k]
    nb = len(banks())
    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/render_ripple.py: do not edit */\n")
        w("#ifndef GROUND_MAP_H\n#define GROUND_MAP_H\n")
        w(f"#define GROUND_Y {GROUND_Y}\n#define GROUND_COLS {GROUND_COLS}\n"
          f"#define GROUND_ROWS {GROUND_ROWS}\n#define GROUND_TILES {GROUND_COLS * GROUND_ROWS}\n"
          f"#define GROUND_NSHADES {NSHADES}\n#define RIPPLE_BANKS {nb}\n#define RIPPLE_NROT {NPH}\n")
        w("/* tile (col, row): the ground part's tile col * GROUND_ROWS + row */\n")
        w("/* the plain grass before the ripple (render_scenery's palette) */\n")
        w("static const u16 ground_pal[16] = {\n  " + ", ".join(f"0x{v:04x}" for v in packed) + "\n};\n")
        w("static const u16 ground_pal_noshadow[16] = {\n  " + ", ".join(f"0x{v:04x}" for v in noshadow) + "\n};\n")
        w("/* tile (col, row)'s ripple bank */\n")
        w("static const u8 ground_bank[GROUND_COLS][GROUND_ROWS] = {\n")
        for c in range(GROUND_COLS):
            w("  {" + ", ".join(str(int(bank_of[c, r])) for r in range(GROUND_ROWS)) + "},\n")
        w("};\n")
        w("/* [bank][0 dome whole / 1 dome gone][rotation][entry] */\n")
        w(f"static const u16 ground_ripple_pal[RIPPLE_BANKS][2][RIPPLE_NROT][16] = {{\n")
        for per in pals:
            w("  {" + ", ".join("{" + ", ".join("{" + ", ".join(f"0x{v:04x}" for v in rot) + "}"
                                                for rot in gone) + "}" for gone in per) + "},\n")
        w("};\n")
        w("/* the bank's rotation at each dome angle; speeds (px a step): "
          + ", ".join(f"{v:+.4f}" for v in speeds) + " */\n")
        w(f"static const u8 ground_ripple_rot[RIPPLE_BANKS][{NDA}] = {{\n")
        for rot in rots:
            w("  {" + ",".join(map(str, rot)) + "},\n")
        w("};\n#endif\n")

    if args.preview:
        from neo_palette import neo_rgb
        frames = []
        for da in range(NDA):
            img = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
            img[:GROUND_Y] = (117, 182, 233)
            for c in range(GROUND_COLS):
                for r in range(GROUND_ROWS):
                    y0 = GROUND_Y + r * TILE
                    if y0 >= SCREEN_H:
                        continue
                    k = bank_of[c, r]
                    lut = np.array([neo_rgb(v) for v in pals[k][0][rots[k][da]]], np.uint8)
                    t = pic[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE][:SCREEN_H - y0]
                    img[y0:y0 + len(t), c * TILE:(c + 1) * TILE] = lut[t]
            frames.append(Image.fromarray(img))
        frames[0].save(args.preview, save_all=True, append_images=frames[1:], duration=20, loop=0)
    print("banks", nb, "speeds", [round(v, 4) for v in speeds])


if __name__ == "__main__":
    main()
