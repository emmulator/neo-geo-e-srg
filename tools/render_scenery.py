#!/usr/bin/env python3
"""render_scenery.py HEADER.h GROUND_C1 GROUND_C2 [--preview PNG]

The dome-scenery plan's ground: grass from the horizon (y GROUND_Y) to the
bottom of the screen, darker toward the horizon, with the dome's shadow cast
on it by the dome's light (render_dome.LIGHT).

The picture is one static block of GROUND_COLS x GROUND_ROWS 16x16 tiles
(320 x 128 px, its top row at y GROUND_Y; the rows below y 223 are off
screen), drawn in one 16-colour palette:

    index 0          transparent (never used by the grass)
    1..NSHADES       the grass, far (dark) to near (light)
    NSHADES+1 ..     the same shades in the dome's shadow ("twins"):
      2*NSHADES      shade k's twin is index k + NSHADES

The shadow is static art (the dome is round, so its shadow does not change
as it turns), but it must vanish while the dome is gone: the C side then
writes ground_pal_noshadow (each twin entry = its plain shade) instead of
ground_pal, so the shadow costs no sprites.

The shadow is computed, not painted: a point on the ground plane (the
height of the dome's flat base, polar angle geometry.CAP_DEG) is in shadow
if the ray from it toward the light hits the dome's sphere above the base,
or if it is under the dome. The points are projected with the dome's own
camera and fit, so the shadow sits exactly under the dome at (DOME_X,
DOME_Y) from src/dome.h.

The header (build/ground_map.h) gives the block's size and place, the
palettes and the tiles' order: tile (col, row) is the sheet's tile number
col * GROUND_ROWS + row, counted from the first tile of the ground part
(the C side adds the part's C ROM base).
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
import render_dome as rd  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from layout import d as lay  # noqa: E402  (DOME_X, DOME_Y from src/dome.h)

TILE = 16
SCREEN_W, SCREEN_H = 320, 224
GROUND_Y = 100                      # the horizon: the grass's top row
GROUND_COLS = SCREEN_W // TILE      # 20: the block is static, no scroll
GROUND_ROWS = 8                     # 128 px: y 100..227 (224..227 off screen)
NSHADES = 7

GRASS_FAR = np.array((28, 66, 30), float)     # at the horizon
GRASS_NEAR = np.array((92, 150, 60), float)   # at the bottom of the screen
GRADIENT_GAMMA = 0.8                # t ** 0.8: the darkening eases in
SHADOW_RGB = np.array((18, 38, 20), float)
SHADOW_MIX = 0.6                    # a twin = 60% of the way to SHADOW_RGB
TEXTURE = 0.75                      # noise amplitude, in shades
SEED = 5
SHADOW_SOFT = 1.2                   # px: the shadow's edge, blurred then dithered


def rgb_to_neo15(rgb):
    """ngdevkit paltool's rgb24_to_packed15 (as render_radar.py)."""
    r, gg, b = [int(c) >> 2 for c in rgb]
    dark = 1 if ((r & 1) + (gg & 1) + (b & 1)) == 0 else 0
    r, gg, b = r >> 1, gg >> 1, b >> 1
    lsb = ((r & 1) << 2) | ((gg & 1) << 1) | (b & 1)
    r, gg, b = r >> 1, gg >> 1, b >> 1
    return (dark << 15) | (lsb << 12) | (r << 8) | (gg << 4) | b


def shades():
    """the NSHADES grass colours, far (index 1) to near."""
    return [tuple(int(round(v)) for v in GRASS_FAR + (GRASS_NEAR - GRASS_FAR) * k / (NSHADES - 1))
            for k in range(NSHADES)]


def twins():
    return [tuple(int(round(v)) for v in np.array(c) + (SHADOW_RGB - np.array(c)) * SHADOW_MIX)
            for c in shades()]


def palette_rgb():
    """16 RGB entries: 0 transparent (key colour), shades, twins, unused."""
    pal = [(255, 0, 255)] + shades() + twins()
    return pal + [(0, 0, 0)] * (16 - len(pal))


def shadow_mask():
    """(SCREEN_H, SCREEN_W) bool: ground pixels in the dome's shadow (or
    under the dome), from the dome's light, camera and fit."""
    y0 = math.cos(math.radians(g.CAP_DEG))        # the base's height
    L = rd.LIGHT / np.linalg.norm(rd.LIGHT)
    xs, zs = np.meshgrid(np.linspace(-4, 4, 1400), np.linspace(-4, 4, 1400))
    P = np.stack([xs.ravel(), np.full(xs.size, y0), zs.ravel()], 1)
    b = 2 * P @ L
    c = (P * P).sum(1) - 1
    disc = b * b - 4 * c
    far_hit = (-b + np.sqrt(np.maximum(disc, 0))) / 2
    hit = (disc > 0) & (far_hit > 0)              # the ray meets the sphere ...
    # ... above the base: the nearer hit point's height (the ray goes up)
    near_t = np.maximum((-b - np.sqrt(np.maximum(disc, 0))) / 2, 0)
    hit &= (P[:, 1] + far_hit * L[1] > y0) | (P[:, 1] + near_t * L[1] > y0)
    under = (P[:, 0] ** 2 + P[:, 2] ** 2) <= 1 - y0 * y0
    G = P[hit | under]
    raw, _ = g.project(G, 0)
    px = g.to_px(raw, g.fit())
    m = np.zeros((SCREEN_H, SCREEN_W), bool)
    X = np.floor(lay.DOME_X + px[:, 0]).astype(int)
    Y = np.floor(lay.DOME_Y + px[:, 1]).astype(int)
    ok = (X >= 0) & (X < SCREEN_W) & (Y >= GROUND_Y) & (Y < SCREEN_H)
    m[Y[ok], X[ok]] = True
    # close the sampling's pinholes: a 3x3 dilation, then a 3x3 erosion
    from PIL import ImageFilter   # noqa: E402  (only here)
    im = Image.fromarray(m.astype(np.uint8) * 255)
    im = im.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    m = np.asarray(im) > 127
    m[:GROUND_Y] = False
    return m


def ground_picture():
    """(GROUND_ROWS*16, SCREEN_W) palette indices, row 0 at y GROUND_Y."""
    H = GROUND_ROWS * TILE
    rng = np.random.default_rng(SEED)
    noise = rng.random((H, SCREEN_W))
    # grass blades: a little vertical smear so the texture reads as grass
    noise = (noise + np.roll(noise, 1, 0) + np.roll(noise, 2, 0)) / 3
    y = np.arange(H)[:, None]
    t = np.clip(y / (SCREEN_H - 1 - GROUND_Y), 0, 1) ** GRADIENT_GAMMA
    v = t * (NSHADES - 1) + TEXTURE * (noise - 0.5) * 2
    dither = rng.random((H, SCREEN_W))
    k = np.clip(np.floor(v + dither), 0, NSHADES - 1).astype(np.uint8)
    idx = k + 1
    sh = shadow_mask()[GROUND_Y:GROUND_Y + H] if GROUND_Y + H <= SCREEN_H else \
        np.vstack([shadow_mask()[GROUND_Y:], np.zeros((GROUND_Y + H - SCREEN_H, SCREEN_W), bool)])
    # a soft edge: blur the mask a little and dither its edge band
    from PIL import ImageFilter   # noqa: E402
    soft = np.asarray(Image.fromarray(sh.astype(np.uint8) * 255)
                      .filter(ImageFilter.GaussianBlur(SHADOW_SOFT))) / 255.0
    sh = soft > rng.random(soft.shape)
    idx[sh] += NSHADES
    return idx


def encode_tile(img):
    """one 16x16 tile's c1/c2 bytes (render_radar.py's order: 8x8
    sub-tiles at offsets 8, 136, 0, 128, each row two bytes, LSB first)."""
    c1, c2 = bytearray(64), bytearray(64)
    pos = 0
    for off in (8, 136, 0, 128):
        sy, sx = off // 16, off % 16
        for yy in range(8):
            p0 = p1 = p2 = p3 = 0
            for xx in range(8):
                px = int(img[sy + yy][sx + xx])
                p0 |= (px & 1) << xx
                p1 |= ((px >> 1) & 1) << xx
                p2 |= ((px >> 2) & 1) << xx
                p3 |= ((px >> 3) & 1) << xx
            c1[pos], c1[pos + 1], c2[pos], c2[pos + 1] = p0, p1, p2, p3
            pos += 2
    return bytes(c1), bytes(c2)


def tiles(pic):
    """the tiles in the header's order: column by column, top to bottom."""
    return [pic[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE]
            for c in range(GROUND_COLS) for r in range(GROUND_ROWS)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("c1")
    ap.add_argument("c2")
    ap.add_argument("--preview")
    args = ap.parse_args()

    pic = ground_picture()
    c1, c2 = bytearray(), bytearray()
    for t in tiles(pic):
        a, b = encode_tile(t)
        c1 += a
        c2 += b
    open(args.c1, "wb").write(bytes(c1))
    open(args.c2, "wb").write(bytes(c2))

    pal = palette_rgb()
    packed = [0x8000] + [rgb_to_neo15(c) for c in pal[1:]]
    noshadow = list(packed)
    for k in range(1, NSHADES + 1):
        noshadow[k + NSHADES] = packed[k]
    with open(args.header, "w") as h:
        h.write("/* generated by tools/render_scenery.py: do not edit */\n")
        h.write("#ifndef GROUND_MAP_H\n#define GROUND_MAP_H\n")
        h.write(f"#define GROUND_Y {GROUND_Y}\n#define GROUND_COLS {GROUND_COLS}\n"
                f"#define GROUND_ROWS {GROUND_ROWS}\n#define GROUND_TILES {GROUND_COLS * GROUND_ROWS}\n"
                f"#define GROUND_NSHADES {NSHADES}\n")
        h.write("/* tile (col, row): the ground part's tile col * GROUND_ROWS + row */\n")
        h.write("static const u16 ground_pal[16] = {\n  "
                + ", ".join(f"0x{w:04x}" for w in packed) + "\n};\n")
        h.write("/* the dome gone: each shadow twin (index k + GROUND_NSHADES) = shade k */\n")
        h.write("static const u16 ground_pal_noshadow[16] = {\n  "
                + ", ".join(f"0x{w:04x}" for w in noshadow) + "\n};\n")
        h.write("#endif\n")
    if args.preview:
        rgb = np.array(pal, np.uint8)[pic]
        img = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        img[:, :] = (117, 182, 233)                 # the sky as MAME shows it
        img[GROUND_Y:] = rgb[:SCREEN_H - GROUND_Y]
        Image.fromarray(img).resize((SCREEN_W * 3, SCREEN_H * 3), Image.NEAREST).save(args.preview)


if __name__ == "__main__":
    main()
