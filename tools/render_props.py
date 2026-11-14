#!/usr/bin/env python3
"""render_props.py HEADER.h PROPS_C1 PROPS_C2 [--preview PNG --over SNAPSHOT [--angles A,B,..]]

Trees and rocks on the ground around the dome (the dome-scenery plan's
props task). The camera orbits the dome, so things standing on the ground
must move with it: NPROPS props stand at fixed points of the ground plane
(the height of the dome's flat base), and each frame each one is projected
with the dome's own camera (geometry.project, the step = dome_angle) to a
screen position and a size. Near ones swing past the dome's sides, far ones
drift across the back slower than the mountains, and on the near side they
slide under the console. The props draw in two pools, each far to near:
the BACK pool under the dome (every prop, at most angles) and the FRONT
pool over the dome and its overlays, under the ship (prop_front: a prop in
front of the dome's centre whose crown or stone covers the dome on screen,
so a near tree passes in front of the dome's base). A front-pool prop's
own shadow never touches the dome (asserted below): the shadow is part of
its sprite and would paint darkened grass over the glass.

Each prop is a tree (3 shapes) or a rock (4 shapes), drawn with the dome's
light (render_dome.LIGHT, from the upper left) and with its own shadow on
the grass, long and to the right like the dome's. A picture is drawn at
three sizes (LODS: 24, 48, 96 px per world unit, the dome's radius being 1
unit); a prop of size se px/unit uses the smallest LOD >= se, shrunk by
the hardware (k = se / LOD). se is clamped to 96 (only the nearest props,
already sliding under the console, would be larger).

The palette indices (each prop has its own palette bank: the colours are
its own palette swap, and entries 1 and 13 follow the grass under it):

    0          transparent
    1          the prop's shadow, core: the grass at the prop's base row,
               darkened (prop_shadow[]: per screen row, written per frame)
    2, 3, 4    tree: the trunk, dark .. light
    5 .. 12    tree: the leaves, dark .. light
    2 .. 5     rock: the stone, dark .. light
    13         the shadow's soft edge (prop_shadow[], half as dark)
    14, 15     unused

The header (build/props_map.h):

    NPROPS, NDA (240), PROP_NLOD (3), prop_lod_ppu[3] (24, 48, 96)
    PROP_TILES     the props part's tiles
    PROP_SLOTS     the most sprite columns the props use at once (any angle)
    PROP_BACK_SLOTS, PROP_FRONT_SLOTS   the same for each pool alone
    pic[] per (shape, lod): cols, rows, the first tile (relative to the
               props part, column by column, top to bottom), and the
               anchor ax, ay: the picture pixel that is the prop's foot
    prop_kind/shape[NPROPS]  0 tree / 1 rock; the shape (0..2 / 0..3)
    prop_pal[NPROPS][2][16]  the prop's palette: [0] lit, [1] in the
               dome's shadow (entries 1 and 13 are 0 here: the runtime
               writes them from prop_shadow)
    prop_x[NPROPS][NDA]      s16 the foot's screen x
    prop_y[NPROPS][NDA]      s16 the foot's screen y (GROUND_Y up; below
               the screen when only the top shows)
    prop_se[NPROPS][NDA]     u8  px per world unit; 0 = not drawn (off
               screen, behind the camera, or entirely below the screen)
    prop_dark[NPROPS][NDA]   u8  1 = the foot is in the dome's shadow
    prop_front[NPROPS][NDA]  u8  1 = drawn in the front pool (over the dome)
    prop_shadow[2][224][2]   u16 entries 1 and 13 per foot row y:
               [0] on lit grass, [1] inside the dome's shadow
    PROP_WORST_LINE          the most prop sprites on one scanline

The generator's numbers (per-line load, slots) are for the hardware's
column rule: a picture of `cols` columns at LOD L drawn for size se uses
all `cols` columns, each horizontally shrunk to hz = round(16 k) - 1 (k =
se / L): drawn width (hz + 1) px, columns placed hz + 1 px apart; vertical
shrink v = round(256 k) - 1 (clamped to 255); the foot at (x, y) puts the
picture's top-left at (x - round(ax k), y - round(ay k)).
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
import render_console as rc  # noqa: E402  (the preview's cover)
import render_dome as rd  # noqa: E402
import render_scenery as rs  # noqa: E402
from render_scenery import GROUND_Y, SCREEN_H, SCREEN_W, TILE, encode_tile, rgb_to_neo15  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from layout import d as lay  # noqa: E402  (DOME_X, DOME_Y from src/dome.h)

NDA = g.STEPS                       # 240 dome angles
LODS = (24, 48, 96)                 # px per world unit
SE_MAX = LODS[-1]
SS = 4                              # supersampling

TREE_H = 0.6                        # a tree's height (world units) at size 1
ROCK_H = 0.1
# the pictures' world boxes (x0, x1, y0, y1) around the foot (0, 0): the
# shadow reaches right and a little down
TREE_BOX = (-0.31, 0.62, -0.13, 0.61)
ROCK_BOX = (-0.19, 0.25, -0.05, 0.11)
SH_LEN = 0.6                        # the shadow's length, of the dome-light length
SHADOW_CORE, SHADOW_EDGE = 0.55, 0.3    # how far toward render_scenery.SHADOW_RGB
DARK_MIX = 0.45                     # a prop in the dome's shadow: its colours
                                    # this far toward SHADOW_RGB

L = rd.LIGHT / np.linalg.norm(rd.LIGHT)   # x right, y up, z toward the camera


def ramp(c0, c1, n):
    return [tuple(int(round(a + (b - a) * k / (n - 1))) for a, b in zip(c0, c1)) for k in range(n)]


LEAVES = [                          # the trees' palette swaps (weights below)
    ramp((20, 52, 18), (170, 210, 70), 8),      # fresh yellow-green
    ramp((14, 44, 18), (110, 175, 60), 8),      # mid green
    ramp((8, 32, 18), (70, 130, 55), 8),        # deep forest green
    ramp((30, 40, 14), (150, 160, 60), 8),      # olive
    ramp((40, 40, 10), (210, 170, 50), 8),      # turning gold (rare)
]
LEAF_WEIGHTS = (.25, .3, .2, .17, .08)
TRUNKS = [ramp((40, 24, 12), (110, 72, 40), 3), ramp((36, 28, 20), (96, 80, 62), 3)]
STONES = [
    ramp((52, 54, 56), (196, 196, 188), 4),     # grey
    ramp((58, 50, 44), (190, 174, 152), 4),     # brown-grey
    ramp((84, 66, 42), (226, 200, 146), 4),     # sandstone
    ramp((44, 54, 40), (162, 172, 140), 4),     # mossy
]
NTREES, NROCKS = 3, 4


def grid(box, ppu):
    """the picture's size in tiles, the foot's pixel, and the supersampled
    world coordinates of every sub-pixel centre."""
    x0, x1, y0, y1 = box
    cols = math.ceil((x1 - x0) * ppu / TILE)
    rows = math.ceil((y1 - y0) * ppu / TILE)
    ax = int(round(-x0 * ppu))
    ay = rows * TILE - int(round(-y0 * ppu)) - 1          # the foot's row
    w, h = cols * TILE * SS, rows * TILE * SS
    X = ((np.arange(w) + 0.5) / SS - ax - 0.5) / ppu
    Y = (ay + 0.5 - (np.arange(h) + 0.5) / SS) / ppu
    X, Y = np.meshgrid(X, Y)
    return cols, rows, ax, ay, X, Y


def down(a, rows, cols):
    return a.reshape(rows * TILE, SS, cols * TILE, SS).mean((1, 3))


def value_noise(seed, X, Y, cell, ch=1):
    """noise fixed in world units (the same at every LOD): a random value per
    cell, nearest."""
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 1, (64, 64, ch))
    i = np.floor(X / cell).astype(int) % 64
    j = np.floor(Y / cell).astype(int) % 64
    return n[j, i]


def shadow_indices(out, X, Y, rows, cols, hgt, rad):
    """the prop's own shadow on the ground (indices 1 core, 13 edge) where
    the picture is still empty: an ellipse from just left of the foot to the
    shadow of the crown's centre, to the right (the dome's light)."""
    k = math.hypot(L[0], L[2]) / L[1]
    off = hgt * 0.62 * k * SH_LEN
    sx0, sx1 = -rad * 0.3, off + rad
    rx, ry = (sx1 - sx0) / 2, rad * 0.4
    cy = -off * 0.1
    e = ((X - (sx0 + sx1) / 2) / rx) ** 2 + ((Y - cy) / ry) ** 2
    core = down((e < 0.55).astype(float), rows, cols) >= 0.5
    edge = down((e < 1.0).astype(float), rows, cols) >= 0.5
    out[(out == 0) & edge] = 13
    out[(out == 13) & core] = 1


def tree_picture(shape, ppu):
    """(picture, cols, rows, ax, ay) of tree `shape` at ppu px per unit."""
    cols, rows, ax, ay, X, Y = grid(TREE_BOX, ppu)
    f = TREE_H / 3.3                                    # the crown's own units
    U, V = X / f, Y / f
    rng = np.random.default_rng(shape + 1)
    S = [(0.0, 2.05, 0.0, 1.05)]
    for _ in range(int(rng.integers(5, 8))):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.45, 0.8)
        S.append((r * math.cos(a), 2.05 + rng.uniform(-0.3, 0.6), r * math.sin(a), rng.uniform(0.55, 0.78)))
    depth = np.full(U.shape, -1e9)
    idx = np.zeros(U.shape, np.int8)
    N = np.zeros(U.shape + (3,))
    for cx, cy, cz, r in S:
        dx, dy = U - cx, V - cy
        d2 = r * r - dx * dx - dy * dy
        z = cz + np.sqrt(np.maximum(d2, 0))
        m = (d2 > 0) & (z > depth)
        depth[m] = z[m]
        idx[m] = 1
        N[m] = np.stack([dx[m], dy[m], (z - cz)[m]], -1) / r
    tw = 0.13 + 0.10 * np.clip(1 - V / 0.35, 0, 1)
    tm = (np.abs(U) < tw) & (V > 0) & (V < 1.5) & (idx == 0)
    idx[tm] = 2
    nx = np.clip(U / tw, -1, 1)
    N[tm] = np.stack([nx[tm], np.zeros(tm.sum()), np.sqrt(1 - nx[tm] ** 2)], -1)
    leaf = idx == 1
    N[leaf] = N[leaf] + 0.45 * value_noise(shape + 50, U, V, 0.14, 3)[leaf]
    N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-6)
    lam = np.clip(N @ L, 0, 1)
    ao = np.clip(0.45 + 0.55 * (V - 1.1) / 1.9, 0.45, 1.0)
    val = (0.32 + 0.68 * lam) * np.where(leaf, ao, 1.0)
    cov_l = down(leaf.astype(float), rows, cols)
    cov_t = down((idx == 2).astype(float), rows, cols)
    v = down(np.where(idx > 0, val, 0), rows, cols) / np.maximum(down((idx > 0).astype(float), rows, cols), 1e-6)
    out = np.zeros(v.shape, np.uint8)
    lm = cov_l >= 0.5
    tmk = (cov_t >= 0.5) & ~lm
    dith = np.random.default_rng(shape + 99 + ppu).random(v.shape)
    out[lm] = 5 + np.clip((v[lm] * 8 + dith[lm] - 0.5).astype(int), 0, 7)
    out[tmk] = 2 + np.clip((v[tmk] * 3).astype(int), 0, 2)
    edge = lm & ~(np.roll(lm, 1, 0) & np.roll(lm, -1, 0) & np.roll(lm, 1, 1) & np.roll(lm, -1, 1))
    out[edge] = np.minimum(out[edge], 6)
    out[edge & (v < 0.55)] = 5
    shadow_indices(out, X, Y, rows, cols, TREE_H, 0.21)
    return out, cols, rows, ax, ay


def rock_picture(shape, ppu):
    """(picture, cols, rows, ax, ay) of rock `shape`: one rounded, lumpy
    boulder, sometimes with one or two small stones beside it."""
    cols, rows, ax, ay, X, Y = grid(ROCK_BOX, ppu)
    f = ROCK_H / 0.66
    U, V = X / f, Y / f
    rng = np.random.default_rng(shape + 900)
    stones = [(rng.uniform(-0.15, 0.15), rng.uniform(0.5, 0.62), rng.uniform(0.5, 0.66))]
    for _ in range(int(rng.integers(0, 3))):
        stones.append((rng.choice([-1, 1]) * rng.uniform(0.5, 0.7),
                       rng.uniform(0.26, 0.36), rng.uniform(0.24, 0.32)))
    lump = value_noise(shape + 950, U, V, 0.12)[..., 0]
    depth = np.full(U.shape, -1e9)
    N = np.zeros(U.shape + (3,))
    hit = np.zeros(U.shape, bool)
    for i, (cx, rx, ry) in enumerate(stones):
        dx, dy = (U - cx) / rx, V / ry
        d2 = 1 - dx * dx - dy * dy + 0.08 * lump
        z = np.sqrt(np.maximum(d2, 0)) * min(rx, ry) + (0.1 if i == 0 else 0.3)
        m = (d2 > 0) & (V >= 0.02) & (z > depth)
        depth[m] = z[m]
        hit |= m
        n = np.stack([dx / rx, dy / ry, np.sqrt(np.maximum(d2, 1e-3)) / min(rx, ry)], -1)
        N[m] = n[m]
    N = N + 0.12 * value_noise(shape + 960, U, V, 0.1, 3)
    N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-6)
    val = 0.32 + 0.68 * np.clip(N @ L, 0, 1)
    cov = down(hit.astype(float), rows, cols)
    v = down(np.where(hit, val, 0), rows, cols) / np.maximum(cov, 1e-6)
    out = np.zeros(v.shape, np.uint8)
    m = cov >= 0.5
    dith = np.random.default_rng(shape + 7 + ppu).random(v.shape)
    out[m] = 2 + np.clip((v[m] * 4 + (dith[m] - 0.5) * 0.3).astype(int), 0, 3)
    edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
    out[edge & (out > 3)] -= 1
    out[edge & (np.arange(out.shape[0])[:, None] >= ay - 1)] = 2
    width = max(abs(c) + rx for c, rx, _ in stones) * f
    shadow_indices(out, X, Y, rows, cols, ROCK_H, width)
    return out, cols, rows, ax, ay


def pictures():
    """{(kind, shape, lod): (picture, cols, rows, ax, ay)}"""
    out = {}
    for lod, ppu in enumerate(LODS):
        for s in range(NTREES):
            out[(0, s, lod)] = tree_picture(s, ppu)
        for s in range(NROCKS):
            out[(1, s, lod)] = rock_picture(s, ppu)
    return out


def _prop(rng, R, th, kind, size=None):
    o = dict(R=R, th=th, kind=kind)
    o['shape'] = int(rng.integers(0, NROCKS)) if kind else int(rng.integers(0, NTREES))
    o['pal'] = int(rng.integers(0, len(STONES))) if kind else int(rng.choice(len(LEAVES), p=LEAF_WEIGHTS))
    o['trunk'] = int(rng.integers(0, len(TRUNKS)))
    o['size'] = float(size if size is not None else rng.uniform(0.75, 1.0))
    return o


def _grove(rng, R, th, ntrees, nrocks, spread, out, pals=None):
    """a cluster around the ground point at (R, th): trees scattered within
    about `spread` world units of it, kept 0.17 apart, sharing one to three
    greens; rocks around its edge."""
    cx, cz = R * math.sin(th), -R * math.cos(th)
    pals = pals or [int(rng.choice(len(LEAVES), p=LEAF_WEIGHTS)) for _ in range(2)]
    pts, tries = [], 0
    while len(pts) < ntrees and tries < 500:
        tries += 1
        dx, dz = rng.normal(0, spread, 2)
        if all(math.hypot(dx - a, dz - b) > 0.17 for a, b in pts):
            pts.append((dx, dz))
    for dx, dz in pts:
        x, z = cx + dx, cz + dz
        o = _prop(rng, math.hypot(x, z), math.atan2(x, -z), 0, rng.uniform(0.7, 1.05))
        o['pal'] = pals[int(rng.integers(0, len(pals)))]
        out.append(o)
    for _ in range(nrocks):
        a = rng.uniform(0, 2 * math.pi)
        d = spread * rng.uniform(1.2, 2.0)
        x, z = cx + d * math.cos(a), cz + d * math.sin(a)
        out.append(_prop(rng, math.hypot(x, z), math.atan2(x, -z), 1))


def props():
    """the props, grouped the way trees and rocks grow (the user's pick,
    10-25, of four mockups): a wood along the far side (two overlapping
    clumps, its greens mid and deep), a small copse close to the dome (at 1.8, where its
    nearest tree passes in front of the dome's base), a
    rock outcrop opposite it, one lone tree, and (10-25, for the
    shadow task) a second lone tree at 1.35, near enough to pass through the
    dome's shadow (angles 81..108) and in front of the dome (26..72). (R, th): the ground point's
    distance from the dome's centre (world units, the dome's radius 1) and
    its angle (0 = straight behind the dome at dome angle 0)."""
    rng = np.random.default_rng(23)
    objs = []
    _grove(rng, 3.7, 5.9, 6, 0, 0.35, objs, pals=[1, 2])
    _grove(rng, 3.4, 0.5, 5, 1, 0.3, objs, pals=[2, 1, 3])
    _grove(rng, 1.8, 2.0, 3, 0, 0.14, objs)
    _grove(rng, 2.4, 3.6, 0, 5, 0.12, objs)
    objs.append(_prop(rng, 2.9, 2.8, 0, 1.0))
    objs.append(_prop(rng, 1.35, 4.4, 0, 0.85))     # the tree in the dome's shadow
    return objs


Y0 = math.cos(math.radians(g.CAP_DEG))     # the ground: the dome's base plane
FIT = g.fit()


def place(o, da):
    """(x, y, se) of prop o's foot at dome angle da (floats; se px per world
    unit, before the clamp), or None behind the camera."""
    P = np.array([[o['R'] * math.sin(o['th']), Y0, -o['R'] * math.cos(o['th'])]])
    raw, w = g.project(P, da)
    pos, fwd, _, _ = g.camera()
    z = (w[0] - pos) @ fwd
    if z < 0.3:
        return None
    px = g.to_px(raw, FIT)[0]
    return lay.DOME_X + px[0], lay.DOME_Y + px[1], FIT[0] / z * o['size'], w[0][2] > 0


def lod_of(se):
    return next(i for i, p in enumerate(LODS) if p >= se)


def drawn(o, da, pics):
    """the prop as the runtime draws it: (x, y, se, lod, left, top, right,
    bottom) in screen px (ints; se clamped), or None if not drawn."""
    p = place(o, da)
    if p is None:
        return None
    x, y, se, _ = p
    se = min(se, SE_MAX)
    X, Y, SE = int(round(x)), int(round(y)), max(1, int(round(se)))
    lod = lod_of(SE)
    _, cols, rows, ax, ay = pics[(o['kind'], o['shape'], lod)]
    k = SE / LODS[lod]
    hz = max(0, int(round(16 * k)) - 1)
    v = min(255, max(0, int(round(256 * k)) - 1))
    left, top = X - int(round(ax * k)), Y - int(round(ay * k))
    right = left + cols * (hz + 1) - 1
    bottom = top + int(rows * TILE * (v + 1) / 256) - 1
    if right < 0 or left > SCREEN_W - 1 or top > SCREEN_H - 1 or Y < GROUND_Y:
        return None
    return X, Y, SE, lod, left, top, right, bottom


def sprite_pixels(o, dr, pics):
    """the prop's on-screen opaque pixels as (ys, xs, index) arrays: its
    columns shrunk the way compose() draws them."""
    X, Y, SE, lod, left, top, right, bottom = dr
    pic, cols, rows, ax, ay = pics[(o['kind'], o['shape'], lod)]
    k = SE / LODS[lod]
    hz = max(0, int(round(16 * k)) - 1)
    v = min(255, max(0, int(round(256 * k)) - 1))
    h = int(rows * TILE * (v + 1) / 256)
    sy = (np.arange(h) * 256 // (v + 1)).clip(0, rows * TILE - 1)
    sx = np.concatenate([c * TILE + np.arange(hz + 1) * 16 // (hz + 1) for c in range(cols)])
    idx = pic[sy][:, sx]
    yy, xx = np.nonzero(idx)
    ys, xs = top + yy, left + xx
    ok = (ys >= 0) & (ys < SCREEN_H) & (xs >= 0) & (xs < SCREEN_W)
    return ys[ok], xs[ok], idx[yy, xx][ok]


def in_front(o, da, dr, pics, dome):
    """1 if the prop draws in the front pool at da: in front of the dome's
    centre, and its crown or stone (not its shadow, indices 1 and 13)
    covers the dome on screen."""
    if not place(o, da)[3]:
        return 0
    ys, xs, idx = sprite_pixels(o, dr, pics)
    body = (idx != 1) & (idx != 13)
    return int(dome[ys[body], xs[body]].any())


def palette(o, dark):
    pal = [(0, 0, 0)] * 16
    if o['kind'] == 0:
        pal[2:5] = TRUNKS[o['trunk']]
        pal[5:13] = LEAVES[o['pal']]
    else:
        pal[2:6] = STONES[o['pal']]
    if dark:
        pal = [tuple(int(round(c + (s - c) * DARK_MIX)) for c, s in zip(col, rs.SHADOW_RGB)) for col in pal]
    words = [0x8000] + [rgb_to_neo15(c) for c in pal[1:]]
    words[1] = words[13] = 0                     # written by the runtime
    return words, pal


def shadow_colours():
    """[lit/in-dome-shadow][y] -> ((r,g,b) core, edge): the grass's mean
    colour on row y (its lit pixels, or its pixels in the dome's shadow),
    darkened toward SHADOW_RGB."""
    pic = rs.ground_picture()
    pal = np.array(rs.palette_rgb(), float)
    sh = rs.shadow_mask()
    out = [[None] * SCREEN_H, [None] * SCREEN_H]
    for y in range(SCREEN_H):
        if y < GROUND_Y:
            out[0][y] = out[1][y] = ((0, 0, 0), (0, 0, 0))
            continue
        row = pic[y - GROUND_Y]
        for d in (0, 1):
            m = sh[y] if d else ~sh[y]
            if not m.any():
                m = np.ones(SCREEN_W, bool)
            c = pal[row[m]].mean(0)
            if d and not sh[y].any():
                c = c + (rs.SHADOW_RGB - c) * rs.SHADOW_MIX
            out[d][y] = tuple(tuple(int(round(v)) for v in c + (rs.SHADOW_RGB - c) * a)
                              for a in (SHADOW_CORE, SHADOW_EDGE))
    return out


def dome_mask():
    """(SCREEN_H, SCREEN_W) bool: the dome on screen at any angle (it is
    round): its cap above the base plane, projected with its camera and
    fit, sampled densely, one pixel of margin."""
    th, ph = np.meshgrid(np.linspace(0, math.radians(g.CAP_DEG), 120), np.linspace(0, 2 * math.pi, 480))
    P = np.stack([np.sin(th) * np.cos(ph), np.cos(th), np.sin(th) * np.sin(ph)], -1).reshape(-1, 3)
    px = g.to_px(g.project(P, 0)[0], FIT)
    m = np.zeros((SCREEN_H, SCREEN_W), bool)
    xs = np.floor(lay.DOME_X + px[:, 0]).astype(int)
    ys = np.floor(lay.DOME_Y + px[:, 1]).astype(int)
    for y in np.unique(ys):
        row = xs[ys == y]
        m[y, max(0, row.min() - 1):min(SCREEN_W, row.max() + 2)] = True
    return m


def dome_silhouette(snapshot):
    """(preview / proof only) the dome's pixels in a game snapshot: the
    blue-ish pixels in the dome box, filled row by row."""
    a = np.asarray(snapshot).astype(int)
    blue = (a[..., 2] > a[..., 1] + 10) & (a[..., 2] > a[..., 0])
    m = np.zeros(blue.shape, bool)
    for y in range(lay.DOME_Y - 4, min(SCREEN_H, lay.DOME_Y + lay.DOME_H + 4)):
        xs = np.nonzero(blue[y, lay.DOME_X - 6:lay.DOME_X + lay.DOME_W + 6])[0]
        if len(xs) > 3:
            m[y, lay.DOME_X - 6 + xs.min():lay.DOME_X - 6 + xs.max() + 1] = True
    return m


def compose(base, da, objs, pics, shadow, dome):
    """(preview) the frame at dome angle da: the props far to near over the
    base frame, under the dome and the console."""
    frame = base.copy()
    darkm = rs.shadow_mask()
    con = rc.console_picture() != 0
    dmask = dome_mask()
    vis = []
    for o in objs:
        dr = drawn(o, da, pics)
        if dr:
            vis.append((in_front(o, da, dr, pics, dmask), dr[1], dr, o))
    for front, _, (X, Y, SE, lod, left, top, right, bottom), o in sorted(vis, key=lambda q: q[:2]):
        cover = con if front else dome | con
        pic, cols, rows, ax, ay = pics[(o['kind'], o['shape'], lod)]
        dark = bool(darkm[min(Y, SCREEN_H - 1), min(max(X, 0), SCREEN_W - 1)])
        _, pal = palette(o, dark)
        sc = shadow[1 if dark else 0][min(Y, SCREEN_H - 1)]
        pal[1], pal[13] = sc
        lut = np.array(pal, np.uint8)
        k = SE / LODS[lod]
        hz = max(0, int(round(16 * k)) - 1)
        v = min(255, max(0, int(round(256 * k)) - 1))
        h = int(rows * TILE * (v + 1) / 256)
        ys = (np.arange(h) * 256 // (v + 1)).clip(0, rows * TILE - 1)
        for c in range(cols):
            xs = c * TILE + (np.arange(hz + 1) * 16 // (hz + 1))
            sub = pic[ys][:, xs]
            for yy in range(h):
                for xx in range(hz + 1):
                    sy, sx = top + yy, left + c * (hz + 1) + xx
                    if 0 <= sy < SCREEN_H and 0 <= sx < SCREEN_W and sub[yy, xx] and not cover[sy, sx]:
                        frame[sy, sx] = lut[sub[yy, xx]]
    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("c1")
    ap.add_argument("c2")
    ap.add_argument("--preview")
    ap.add_argument("--over", help="a 320x224 game snapshot for the preview")
    ap.add_argument("--angles", default="0,30,60,90")
    args = ap.parse_args()

    pics = pictures()
    objs = props()
    keys = sorted(pics, key=lambda k: (k[0], k[1], k[2]))
    first, n = {}, 0
    c1, c2 = bytearray(), bytearray()
    for key in keys:
        pic, cols, rows, _, _ = pics[key]
        first[key] = n
        for c in range(cols):
            for r in range(rows):
                a, b = encode_tile(pic[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE])
                c1 += a
                c2 += b
                n += 1
    open(args.c1, "wb").write(bytes(c1))
    open(args.c2, "wb").write(bytes(c2))

    darkm = rs.shadow_mask()
    X = np.zeros((len(objs), NDA), int)
    Y = np.zeros((len(objs), NDA), int)
    SE = np.zeros((len(objs), NDA), int)
    D = np.zeros((len(objs), NDA), int)
    F = np.zeros((len(objs), NDA), int)
    slots = back_slots = front_slots = worst_line = 0
    dome = dome_mask()
    for da in range(NDA):
        lines = np.zeros(SCREEN_H, int)
        cols_now = [0, 0]                       # back, front
        for i, o in enumerate(objs):
            dr = drawn(o, da, pics)
            if not dr:
                continue
            x, y, se, lod, left, top, right, bottom = dr
            X[i, da], Y[i, da], SE[i, da] = x, y, se
            D[i, da] = int(darkm[min(y, SCREEN_H - 1), min(max(x, 0), SCREEN_W - 1)])
            cols = pics[(o['kind'], o['shape'], lod)][1]
            F[i, da] = in_front(o, da, dr, pics, dome)
            cols_now[F[i, da]] += cols
            if F[i, da]:
                # the front pool draws over the dome: its shadow (part of
                # its sprite) must never touch the dome
                ys, xs, idx = sprite_pixels(o, dr, pics)
                sh = (idx == 1) | (idx == 13)
                assert not dome[ys[sh], xs[sh]].any(), (i, da)
            lines[max(0, top):min(SCREEN_H, bottom + 1)] += cols
        slots = max(slots, sum(cols_now))
        back_slots = max(back_slots, cols_now[0])
        front_slots = max(front_slots, cols_now[1])
        worst_line = max(worst_line, int(lines.max()))
    assert Y[SE > 0].min() >= GROUND_Y
    assert np.abs(X).max() < 32767

    shadow = shadow_colours()
    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/render_props.py: do not edit */\n")
        w("#ifndef PROPS_MAP_H\n#define PROPS_MAP_H\n")
        w(f"#define NPROPS {len(objs)}\n#define PROP_NDA {NDA}\n#define PROP_NLOD {len(LODS)}\n")
        w(f"#define PROP_TILES {n}\n#define PROP_SLOTS {slots}\n#define PROP_WORST_LINE {worst_line}\n")
        w(f"#define PROP_BACK_SLOTS {back_slots}\n#define PROP_FRONT_SLOTS {front_slots}\n")
        w(f"#define PROP_NTREES {NTREES}\n#define PROP_NROCKS {NROCKS}\n")
        w("static const u8 prop_lod_ppu[PROP_NLOD] = {" + ", ".join(map(str, LODS)) + "};\n")
        w("/* pictures: [kind 0 tree / 1 rock][shape][lod]; a picture's tiles are the\n"
          " * props part's first .. + cols * rows - 1, column by column, top to\n"
          " * bottom; (ax, ay) is the foot's pixel in the full-size picture */\n")
        w("typedef struct { u8 cols, rows; u16 first; u8 ax, ay; } prop_pic_t;\n")
        for kind, nshapes, name in ((0, NTREES, "prop_tree_pic"), (1, NROCKS, "prop_rock_pic")):
            w(f"static const prop_pic_t {name}[{nshapes}][PROP_NLOD] = {{\n")
            for s in range(nshapes):
                w("  {" + ", ".join(
                    f"{{{pics[(kind, s, l)][1]}, {pics[(kind, s, l)][2]}, {first[(kind, s, l)]}, "
                    f"{pics[(kind, s, l)][3]}, {pics[(kind, s, l)][4]}}}" for l in range(len(LODS))) + "},\n")
            w("};\n")
        w("static const u8 prop_kind[NPROPS] = {" + ", ".join(str(o['kind']) for o in objs) + "};\n")
        w("static const u8 prop_shape[NPROPS] = {" + ", ".join(str(o['shape']) for o in objs) + "};\n")
        w("/* [prop][0 lit / 1 in the dome's shadow][16]; entries 1 and 13 are\n"
          " * the runtime's (prop_shadow) */\n")
        w("static const u16 prop_pal[NPROPS][2][16] = {\n")
        for o in objs:
            w("  {" + ", ".join("{" + ", ".join(f"0x{v:04x}" for v in palette(o, d)[0]) + "}" for d in (0, 1)) + "},\n")
        w("};\n")
        for name, arr, typ in (("prop_x", X, "s16"), ("prop_y", Y, "s16"), ("prop_se", SE, "u8"), ("prop_dark", D, "u8"),
                               ("prop_front", F, "u8")):
            w(f"static const {typ} {name}[NPROPS][PROP_NDA] = {{\n")
            for row in arr:
                w("  {" + ",".join(str(int(v)) for v in row) + "},\n")
            w("};\n")
        w("/* [0 lit grass / 1 the dome's shadow][screen row][entry 1, entry 13] */\n")
        w("static const u16 prop_shadow[2][224][2] = {\n")
        for d in (0, 1):
            w("  {" + ",".join("{0x%04x,0x%04x}" % tuple(rgb_to_neo15(c) for c in shadow[d][y])
                             for y in range(SCREEN_H)) + "},\n")
        w("};\n#endif\n")

    if args.preview:
        base = np.array(Image.open(args.over).convert("RGB"))
        dome = dome_silhouette(base)
        frames = [compose(base, int(a), objs, pics, shadow, dome) for a in args.angles.split(",")]
        strip = np.concatenate(frames, 0)
        Image.fromarray(strip).resize((SCREEN_W * 3, strip.shape[0] * 3), Image.NEAREST).save(args.preview)


if __name__ == "__main__":
    main()
