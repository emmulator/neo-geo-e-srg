#!/usr/bin/env python3
"""render_band.py HEADER.h BAND_C1 BAND_C2 [--preview PNG]

A band of distant towns and forests standing on the horizon in front of the
mountains (the dome-scenery plan's band task). Like the mountains it is a
panorama that wraps once per turn of the dome, but a nearer one: the camera
orbits the dome, so nearer things move LESS as it turns. The mountains move
960 px a turn (tools/render_mountains.py), this band BAND_W 768 (3.2 px a
step: s = round(dome_angle * 768 / 240) = (16 * da + 2) / 5, never an exact
half), the far trees about 550 (tools/render_props.py).

Along the panorama: forests (solid stands down to the horizon, their lumpy
tops lit from the left), towns (houses with tiled or slate roofs and a
shaded right side, a church steeple, trees between them) and open fields
(transparent: the mountains' green hills show through). Every colour is
hazed toward the sky by HAZE (they are kilometres away). The foot of each
thing dithers into the grass's two farthest shades, as the mountains' does.

    index 0        transparent
    1, 2, 3        forest: shade, mid, lit
    4, 5           walls: lit, shaded
    6, 7           tiled roofs: lit, shaded
    8, 9           slate roofs and steeples: lit, shaded
    10             windows and doors
    11, 12         the grass at the horizon (render_scenery's two farthest)
    13..15         unused (black)

The picture is BAND_COLS x BAND_ROWS 16x16 tiles (768 x 32 px, its bottom
row on the horizon: BAND_Y = GROUND_Y - 32 = 68). The header
(build/band_map.h) gives the size and place and the palette; tile (col, row)
is the part's tile col * BAND_ROWS + row, as the mountains'.
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_scenery as rs  # noqa: E402
from render_scenery import GROUND_Y, TILE, encode_tile, rgb_to_neo15  # noqa: E402

BAND_W = 768                        # one turn of the dome: 240 steps x 3.2 px
BAND_ROWS = 2
BAND_H = BAND_ROWS * TILE
BAND_COLS = BAND_W // TILE          # 48
BAND_Y = GROUND_Y - BAND_H          # 68
SEED = 5
SKY = np.array((117, 182, 233), float)   # the sky as MAME shows it
HAZE = 0.14                         # toward the sky


def haze(c, k=HAZE):
    return tuple(int(round(v + (s - v) * k)) for v, s in zip(c, SKY))


PALETTE = [(255, 0, 255),
           haze((18, 46, 26)), haze((30, 66, 36)), haze((56, 100, 48)),     # forest
           haze((214, 204, 184)), haze((160, 152, 140)),                    # walls
           haze((168, 84, 60)), haze((116, 60, 46)),                        # tiled roofs
           haze((96, 98, 110)), haze((66, 68, 80)),                         # slate, steeples
           haze((40, 40, 46)),                                              # windows, doors
           ] + [tuple(c) for c in rs.shades()[:2]] + [(0, 0, 0)] * 3        # grass


def band_picture(W=BAND_W, seed=SEED):
    """(BAND_H, W) palette indices, row 0 at y BAND_Y."""
    rng = np.random.default_rng(seed)
    img = np.zeros((BAND_H, W), np.uint8)
    foot = BAND_H - 1                         # the row on the horizon
    # the plan along the panorama: forests, towns, open fields (transparent)
    x = 0
    segs = []
    while x < W - 40:
        kind = rng.choice(['forest', 'town', 'field', 'forest', 'field'], p=[.28, .27, .25, .12, .08])
        n = {'forest': rng.integers(50, 150), 'town': rng.integers(36, 80), 'field': rng.integers(30, 90)}[kind]
        segs.append((kind, x, min(W - 20, x + int(n))))
        x += int(n)
    # forests: rounded crowns along a bumpy top, lit from the left
    def crown(cx, cy, r):
        yy, xx = np.mgrid[0:BAND_H, 0:W]
        dx = (xx - cx + W / 2) % W - W / 2
        d = dx ** 2 + ((yy - cy) * 1.15) ** 2
        m = d <= r * r
        lit = m & (dx < -r * 0.25) & (yy - cy < r * 0.2)
        shade = m & ((dx > r * 0.35) | (yy - cy > r * 0.45))
        img[m & (img == 0)] = 0
        img[m] = 2
        img[lit] = 3
        img[shade] = 1
    for kind, a, b in segs:
        if kind == 'forest':
            # a solid stand: the crowns give its bumpy top and the light on it,
            # everything under the top down to the horizon is foliage
            hmax = rng.uniform(10, 16)
            top = np.full(W, BAND_H, float)
            crowns = []
            for cx in np.arange(a, b, rng.uniform(3.0, 4.2)):
                t = (cx - a) / max(1, b - a)
                h = hmax * (0.35 + 0.65 * math.sin(math.pi * t) ** 0.6) * rng.uniform(0.85, 1.1)
                r = rng.uniform(3.0, 4.4)
                crowns.append((cx + rng.uniform(-1, 1), foot - h + r, r))
            yy, xx = np.mgrid[0:BAND_H, 0:W]
            mass = np.zeros((BAND_H, W), bool)
            for cx, cy, r in crowns:
                dx = (xx - cx + W / 2) % W - W / 2
                inside = dx ** 2 + ((yy - cy) * 1.15) ** 2 <= r * r
                mass |= inside | ((np.abs(dx) <= r * 0.9) & (yy >= cy))
            img[mass] = 2
            # light and shade per crown: the upper left of each is lit, the
            # lower right shaded, and the bottom rows sink into shadow
            for cx, cy, r in crowns:
                dx = (xx - cx + W / 2) % W - W / 2
                inside = dx ** 2 + ((yy - cy) * 1.15) ** 2 <= r * r
                img[inside & (dx < -r * 0.2) & (yy - cy < r * 0.1)] = 3
                img[inside & (dx > r * 0.45) & (yy - cy > -r * 0.2)] = 1
            img[mass & (yy >= foot - 3)] = 1
            speck = mass & (yy < foot - 3) & (rng.random((BAND_H, W)) < 0.12)
            img[speck] = 1
    # towns: houses with pitched roofs, a church or two, behind/among trees
    for kind, a, b in segs:
        if kind != 'town':
            continue
        xs = a
        cx_church = rng.integers(a + 6, b - 6) if rng.random() < 0.7 else None
        while xs < b - 4:
            w = int(rng.integers(5, 11)); h = int(rng.integers(4, 8))
            base = foot - int(rng.integers(0, 2))
            x0, x1 = xs, min(b, xs + w)
            img[base - h:base + 1, x0:x1] = 4
            img[base - h:base + 1, x1 - max(1, w // 3):x1] = 5             # the shaded right side
            if rng.random() < 0.35:                                         # a window or a door
                img[base - 1:base + 1, x0 + 1] = 10
            roof = 6 if rng.random() < 0.65 else 8
            rh = max(2, w // 2)
            for k in range(rh):                                             # a pitched roof
                l, r = x0 + k - 1, x1 - k
                if l < r:
                    img[base - h - 1 - k, max(x0 - 1, l):r + 1] = roof
                    img[base - h - 1 - k, max(l, (l + r) // 2 + 1):r + 1] = roof + 1
            xs = x1 + int(rng.integers(0, 3))
        if cx_church is not None:                                           # a steeple
            c = int(cx_church)
            img[foot - 13:foot + 1, c - 2:c + 2] = 4
            img[foot - 13:foot + 1, c + 1] = 5
            img[foot - 10, c - 1] = 10
            for k in range(8):
                img[foot - 14 - k, c - 2 + (k // 3):c + 2 - (k // 3)] = 8
            img[foot - 14 - 8, c - 1] = 9
        # trees between the houses
        for _ in range(int((b - a) / 10)):
            cx = rng.uniform(a, b)
            crown(cx, foot - rng.uniform(3, 5), rng.uniform(2.4, 3.4))
    # the foot: dither into the grass like the mountains', only under things
    grass = np.where(rng.random((BAND_H, W)) < 0.35, 12, 11)
    up = BAND_H - 1 - np.arange(BAND_H)[:, None]
    p = np.clip((4 - up) / 3, 0, 1)
    to = (rng.random((BAND_H, W)) < p) & (img != 0)
    img[to] = grass[to]
    return img


def tiles(pic):
    """the tiles in the header's order: column by column, top to bottom."""
    return [pic[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE]
            for c in range(BAND_COLS) for r in range(BAND_ROWS)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("c1")
    ap.add_argument("c2")
    ap.add_argument("--preview")
    args = ap.parse_args()

    pic = band_picture()
    assert pic.shape == (BAND_H, BAND_W)
    c1, c2 = bytearray(), bytearray()
    for t in tiles(pic):
        a, b = encode_tile(t)
        c1 += a
        c2 += b
    open(args.c1, "wb").write(bytes(c1))
    open(args.c2, "wb").write(bytes(c2))

    packed = [0x8000] + [rgb_to_neo15(c) for c in PALETTE[1:]]
    with open(args.header, "w") as h:
        h.write("/* generated by tools/render_band.py: do not edit */\n")
        h.write("#ifndef BAND_MAP_H\n#define BAND_MAP_H\n")
        h.write(f"#define BAND_Y {BAND_Y}\n#define BAND_W {BAND_W}\n#define BAND_COLS {BAND_COLS}\n"
                f"#define BAND_ROWS {BAND_ROWS}\n#define BAND_TILES {BAND_COLS * BAND_ROWS}\n")
        h.write("/* tile (col, row): the band part's tile col * BAND_ROWS + row */\n")
        h.write("static const u16 band_pal[16] = {\n  "
                + ", ".join(f"0x{w:04x}" for w in packed) + "\n};\n")
        h.write("#endif\n")
    if args.preview:
        rgb = np.array(PALETTE, np.uint8)[pic]
        rgb[pic == 0] = SKY.astype(np.uint8)
        Image.fromarray(rgb).resize((BAND_W * 3, BAND_H * 3), Image.NEAREST).save(args.preview)


if __name__ == "__main__":
    main()
