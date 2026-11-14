#!/usr/bin/env python3
"""render_mountains.py HEADER.h MTN_C1 MTN_C2 [--preview PNG]

The dome-scenery plan's mountains: a 960 px panorama standing on the
horizon (its bottom row is y GROUND_Y - 1, the row above the grass), which
scrolls sideways as the dome turns. 960 px is one full turn of the dome
(dome_angle 0..239, 4 px a step), so the picture wraps: column 959
continues into column 0 with no seam (every random field here is periodic
in x). 960 is about the rate the dome's camera gives the true horizon (969
px a turn at the screen's centre), so the nearer layers move less: the band
of towns and forests (tools/render_band.py, 768) and the far trees (about
550). It was 640 until the band came.

Two ranges, far to near, in one 16-colour palette:

    index 0        transparent (the sky shows through)
    1, 2, 3        the far range: lit, middle, shaded
    4, 5           snow on the far peaks: lit, shaded
    6, 7, 8        the near hills: lit, middle, shaded
    9, 10          the grass at the horizon (render_scenery's two farthest
                   shades): the hills' foot is grass, speckled like the
                   ground's top rows, so the band meets the grass with no seam
    11..15         unused (black)

The far range is pale and blue-grey (distance); the hills are dark green
like the grass at the horizon (render_scenery.GRASS_FAR). Faces turned
toward the left are lit, as the dome is (render_dome.LIGHT comes from the
upper left): a pixel is lit where its shading field rises to the right.

The picture is MTN_COLS x MTN_ROWS 16x16 tiles (960 x 48 px, its top row at
y MTN_Y). The header (build/mountain_map.h) gives the size and place, the
palette and the tiles' order: tile (col, row) is the sheet's tile number
col * MTN_ROWS + row, counted from the first tile of the mountain part (the
C side adds the part's C ROM base), as the ground's.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_scenery import (GROUND_Y, SCREEN_W, TILE, encode_tile,  # noqa: E402
                            rgb_to_neo15, shades)

MTN_W = 960                         # one turn of the dome: 240 steps x 4 px
MTN_ROWS = 3                        # 48 px: the tallest peak is 45 px
MTN_H = MTN_ROWS * TILE
MTN_COLS = MTN_W // TILE            # 60
MTN_Y = GROUND_Y - MTN_H            # 52: the bottom row sits on the horizon
SEED = 4

PALETTE = [
    (255, 0, 255),                                   # 0: transparent (key)
    (156, 178, 200), (130, 152, 182), (104, 124, 160),   # far: lit, mid, shade
    (238, 244, 250), (180, 194, 218),                # snow: lit, shade
    (72, 110, 84), (56, 92, 70), (42, 74, 56),       # hills: lit, mid, shade
] + [tuple(c) for c in shades()[:2]] + [(0, 0, 0)] * 5   # 9, 10: the grass


def smooth_wrap(a, r, ry=None):
    """three box-blur passes: radius r in x (wrapping), ry in y (clamped)."""
    ry = r if ry is None else ry
    for _ in range(3):
        a = sum(np.roll(a, s, 1) for s in range(-r, r + 1)) / (2 * r + 1)
        p = np.pad(a, ((ry, ry), (0, 0)), mode="edge")
        a = sum(p[ry + s:ry + s + a.shape[0]] for s in range(-ry, ry + 1)) / (2 * ry + 1)
    return a


def noise2(rng, scales):
    """(MTN_H, MTN_W) smooth noise, periodic in x: sum of amp * blur(r)."""
    out = np.zeros((MTN_H, MTN_W))
    for r, amp in scales:
        out += amp * smooth_wrap(rng.normal(0, 1, (MTN_H, MTN_W)), r)
    return out


def peaks(rng, npeaks, hmin, hmax, slope, rounded):
    """a range's height per column: the upper envelope of npeaks evenly
    spread (jittered) peaks, each a cone or a rounded bump, wrapping."""
    xs = (np.arange(npeaks) + rng.uniform(-0.35, 0.35, npeaks)) * MTN_W / npeaks
    hs = rng.uniform(hmin, hmax, npeaks)
    sl = slope * rng.uniform(0.75, 1.3, npeaks)
    col = np.arange(MTN_W)
    d = (col[None, :] - xs[:, None] + MTN_W / 2) % MTN_W - MTN_W / 2
    if rounded:
        prof = hs[:, None] * np.exp(-(d * sl[:, None] / hs[:, None]) ** 2)
    else:
        prof = hs[:, None] - np.abs(d) * sl[:, None]
    return prof.max(0)


def grounded(inside):
    """keep only the part of a mask joined to the bottom row, column by
    column (no floating specks above a gap)."""
    return np.cumprod(inside[::-1], 0)[::-1].astype(bool)


def ddx(f):
    return np.roll(f, -1, 1) - np.roll(f, 1, 1)


def mountain_picture():
    """(MTN_H, MTN_W) palette indices, row 0 at y MTN_Y."""
    rng = np.random.default_rng(SEED)
    up = (MTN_H - 1 - np.arange(MTN_H))[:, None].astype(float)  # px above the horizon
    col = np.arange(MTN_W)

    # the far range: tall cones over a continuous low ridge
    far = peaks(rng, 16, 22, 45, 0.62, False)        # 11 per 640 px
    far = np.maximum(far, 15 + 3 * np.sin(col / MTN_W * 2 * np.pi * 3))
    n = noise2(rng, [(6, 6.0), (2, 2.0), (1, 0.8)])
    surf_f = far[None, :] + n * np.clip(up / 30, 0.35, 1.0)
    inside_f = grounded(surf_f > up)
    # its shading field: the profile plus gullies (detail stretched downhill)
    g = sum(a * smooth_wrap(rng.normal(0, 1, (MTN_H, MTN_W)), r, 3 * r)
            for r, a in ((1, 5.0), (2, 7.0)))
    ridge_f = ddx(far[None, :] + g)

    # the near hills: rounded bumps with a tree line along the top
    near = np.maximum(peaks(rng, 26, 8, 18, 0.9, True), 5)    # 17 per 640 px
    m = noise2(rng, [(3, 2.0), (1, 0.9)])
    trees = 1.8 * np.abs(smooth_wrap(rng.normal(0, 1, (MTN_H, MTN_W)), 1, 0))
    inside_n = grounded(near[None, :] + m + trees > up)
    inside_n[up[:, 0] < 2] = True                 # the foot is unbroken
    ridge_n = ddx(near[None, :] + 3.0 * smooth_wrap(rng.normal(0, 1, (MTN_H, MTN_W)), 1, 2))

    img = np.zeros((MTN_H, MTN_W), np.uint8)
    kf = np.where(ridge_f > 0.6, 1, np.where(ridge_f < -0.6, 3, 2))
    img[inside_f] = kf[inside_f]
    snowline = 27 + 9 * smooth_wrap(rng.normal(0, 1, (1, MTN_W)), 3)[0]
    snow = inside_f & (up > snowline[None, :]) & (surf_f - up < 9)
    img[snow & (kf == 1)] = 4
    img[snow & (kf != 1)] = 5
    kn = np.where(ridge_n > 0.35, 6, np.where(ridge_n < -0.35, 8, 7))
    img[inside_n] = kn[inside_n]
    # the foot: grass. The bottom FOOT rows are all grass and the hills
    # dither into it over the FOOT rows above, speckled with the ground's
    # two horizon shades the way its own top rows are.
    FOOT = 3
    grass = np.where(rng.random((MTN_H, MTN_W)) < 0.35, 10, 9)
    p_grass = np.clip((2 * FOOT - up) / FOOT, 0, 1)        # 1 at the bottom
    to_grass = (rng.random((MTN_H, MTN_W)) < p_grass) & inside_n
    img[to_grass] = grass[to_grass]
    return img


def tiles(pic):
    """the tiles in the header's order: column by column, top to bottom."""
    return [pic[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE]
            for c in range(MTN_COLS) for r in range(MTN_ROWS)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("c1")
    ap.add_argument("c2")
    ap.add_argument("--preview")
    args = ap.parse_args()

    pic = mountain_picture()
    c1, c2 = bytearray(), bytearray()
    for t in tiles(pic):
        a, b = encode_tile(t)
        c1 += a
        c2 += b
    open(args.c1, "wb").write(bytes(c1))
    open(args.c2, "wb").write(bytes(c2))

    packed = [0x8000] + [rgb_to_neo15(c) for c in PALETTE[1:]]
    with open(args.header, "w") as h:
        h.write("/* generated by tools/render_mountains.py: do not edit */\n")
        h.write("#ifndef MOUNTAIN_MAP_H\n#define MOUNTAIN_MAP_H\n")
        h.write(f"#define MTN_Y {MTN_Y}\n#define MTN_W {MTN_W}\n#define MTN_COLS {MTN_COLS}\n"
                f"#define MTN_ROWS {MTN_ROWS}\n#define MTN_TILES {MTN_COLS * MTN_ROWS}\n")
        h.write("/* tile (col, row): the mountain part's tile col * MTN_ROWS + row */\n")
        h.write("static const u16 mtn_pal[16] = {\n  "
                + ", ".join(f"0x{w:04x}" for w in packed) + "\n};\n")
        h.write("#endif\n")
    if args.preview:
        rgb = np.array(PALETTE, np.uint8)[pic]
        rgb[pic == 0] = (117, 182, 233)            # the sky as MAME shows it
        Image.fromarray(rgb).resize((MTN_W * 3, MTN_H * 3), Image.NEAREST).save(args.preview)


if __name__ == "__main__":
    main()
