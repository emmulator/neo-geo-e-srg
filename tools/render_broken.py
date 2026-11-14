#!/usr/bin/env python3
"""render_broken.py OUTDIR HEADER.h [--preview PNG]

Pre-renders the broken-window overlays (M4-fixes Task 3): for every cell
and every one of the 48 dome views, a picture of the cell drawn as a
broken window — a black interior with jagged fragments of glass in the
dome's colours still clinging to the cell's edges — in exactly the
projection `tools/render_dome.py` draws the cell on the dome, so the
overlay covers the cell's own outline exactly as the dome picture draws
it, and turns with the dome.

Pictures are made of 16x16 sprite tiles ("stones"), one bitmap per
(cell, view), on the smallest grid of stones that contains the cell's
polygon. Each picture is built from the dome's own pixels for that view
(render_dome.views()): it paints only what the dome draws as the cell's
glass, never the outline and never a neighbour; black where the window
is broken, and the dome's own glass colours where shards still cling to
the edges. The shards are defined on the 3D face (see "The broken-window
art" below), so they foreshorten and turn exactly with the dome.

Tile numbering: the runtime draws a picture's stones as a dense w x h
block in C ROM, tile = BROKEN_TILE_BASE + broken_tile0[cell] +
broken_view_t0[cell][view] + r * w + c (stone row r, column c). The tile
stream this script emits is exactly that order — one four-bit tile per
stone, all 7,909 used stones packed with no gaps — so the tile at every
number the cartridge fetches holds exactly the pixels the picture drew
for that stone (tests/test_broken_rom.py decodes the built ROM and proves
it). Packing the tiles (instead of a tiletool sheet, which numbers tiles
row-major across a whole-sheet rectangle and cannot express a w*h block
whose row stride is the picture's own width) is also what lets CROMSIZE
come back down: the broken tiles now take ~0.51 MB, not the ~1.3 MB of
the old padded sheet.

The header per cell: its fixed sprite-slot run (broken_slot0,
broken_max_w), and per view the picture's w/h in stones, the tile offset
of its first stone (broken_view_t0), and the canvas offset in the dome
box (0 = the cell faces away: no overlay drawn).

Fragments of glass vary per 5-fold orbit (a seeded RNG per orbit, in a
frame tied to the dome's pole), so a cell keeps its exact look when the
runtime switches to its orbit partner's art at every 48th rotation step.
Neighbouring cells come from different orbits, so they don't look alike.
Mirror pairs are different pictures at the same view, so every
(cell, view) picture is stored (no tile sharing).

The overlay is drawn over the dome (slots >= 32, above the dome's
21..31) and under the ship, front missiles and explosions (which get
higher slots), so a broken tile never paints over the ship, a front
missile or an explosion; a missile behind the dome (slots below the
dome's) stays hidden by it.
"""
import argparse
import functools
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
import gen_missiles as gm  # noqa: E402
import render_dome as rd  # noqa: E402
import render_missiles as rm  # noqa: E402
import render_rockets as rr  # noqa: E402  (MIS_FRAMES: the rocket's tile stride)
import render_hovercraft as rs  # noqa: E402

TILE = 16                       # stone size, px

# The broken-window palette: 0 transparent, 1 pure black (the broken
# hole: a real colour the boot-test can count), then dome palette indices
# 1..14 at broken indices 2..15 (dome i -> broken i + 1). An overlay copies
# the dome's own pixels for its glass, so a shard is exactly the colour of
# the cell it clings to. The dome's outline core (15) is not needed: an
# overlay never paints the outline.
_DPAL = rd.PALETTE
BROKEN_PALETTE = [(255, 0, 255), (0, 0, 0)] + [_DPAL[i] for i in range(1, 15)]
GLASS = [2, 3, 4, 5, 6, 7]       # palette indices of the glass ramp (dome 1..6)
BLACK = 1
assert len(BROKEN_PALETTE) == 16

# ---- geometry (the cell pool, exactly as the game numbers cells) ----

_PTS, _EDGES, _FACES = g.build_mesh()
_FIT = g.fit()
_POS = g.camera()[0]
_CAM = g.camera()
_ROT = []
for v in range(g.VIEWS):
    a = 2 * math.pi * v / g.STEPS
    _ROT.append(np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0],
                          [-math.sin(a), 0, math.cos(a)]]))
_CF = g.whole_cells(_PTS, _FACES)    # (face, centre) sorted by -y: index == cell number
_CF.sort(key=lambda fc: -fc[1][1])
assert len(_CF) == 76, "cells changed: the tables below are sized for 76"

def _cell_poly_px_at(cell, steps):
    a = 2 * math.pi * steps / g.STEPS
    R = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0],
                  [-math.sin(a), 0, math.cos(a)]])
    f = _CF[cell][0]
    P = _PTS[list(f)] @ R.T
    d = P - _POS
    fwd, right, up = _CAM[1:]
    z = d @ fwd
    return np.column_stack([_FIT[1] + _FIT[0] * (d @ right) / z,
                            _FIT[2] - _FIT[0] * (d @ up) / z])

# The 5-fold symmetry: the dome picture at rotation step s == at step s+48k
# with the cells relabelled by the 72-degree permutation r72. A cell's
# picture at dome_angle s therefore equals the permuted cell's picture at
# view s mod 48, so the art stores only the 48 views and the runtime maps
# (cell, s) -> (r72^(s/48)(cell), s mod 48). _PERM[c] is r72(c).
_PERM = [0] * 76
for c in range(76):
    P48 = _cell_poly_px_at(c, 48)
    for d in range(76):
        if P48.shape == _cell_poly_px_at(d, 0).shape and \
           np.allclose(np.sort(P48, axis=0), np.sort(_cell_poly_px_at(d, 0), axis=0), atol=1e-4):
            _PERM[c] = d
            break
assert len(set(_PERM)) == 76 and _PERM[0] == 0


def _face_normal(P, f):
    r = list(f)
    n = sum(np.cross(P[k], P[(k + 1) % len(r)]) for k in range(len(r)))
    if n @ P.mean(axis=0) < 0:
        n = -n
    return n / np.linalg.norm(n)


@functools.lru_cache(maxsize=None)   # pure; the tables and tests call it ~1e5 times
def overlay(cell, v):
    """(cw, ch, left, top) of the (cell, view) picture in the dome box,
    or None if the cell faces away (no overlay drawn)."""
    R = _ROT[v]
    face = _CF[cell][0]
    P = _PTS[list(face)] @ R.T
    d = P - _POS
    fwd, right, up = _CAM[1:]
    z = d @ fwd
    px = np.column_stack([_FIT[1] + _FIT[0] * (d @ right) / z,
                          _FIT[2] - _FIT[0] * (d @ up) / z])
    if _face_normal(P, face) @ (_POS - P.mean(axis=0)) <= 0:
        return None
    x0, x1 = px[:, 0].min(), px[:, 0].max()
    y0, y1 = px[:, 1].min(), px[:, 1].max()
    cw = max(1, math.ceil((x1 - x0) / TILE))
    ch = max(1, math.ceil((y1 - y0) / TILE))
    left = round((x0 + x1) / 2 - cw * TILE / 2)
    top = round((y0 + y1) / 2 - ch * TILE / 2)
    return cw, ch, left, top


def _max_stone_w(cell):
    m = 1
    for v in range(g.VIEWS):
        o = overlay(cell, v)
        if o:
            m = max(m, o[0])
    return m


_MSW = [_max_stone_w(c) for c in range(76)]
_MH = []
for cell in range(76):
    m = 1
    for v in range(g.VIEWS):
        o = overlay(cell, v)
        if o:
            m = max(m, o[1])
    _MH.append(m)
def _view_t0(cell, v):
    """the tile offset (in tiles) of cell's picture at view v inside the
    cell's packed tile run (the runtime's broken_view_t0 table). The run
    holds the facing pictures' w*h stones back to back, so the offset is
    the sum of the earlier views' stone counts."""
    t = 0
    for vv in range(v):
        o = overlay(cell, vv)
        if o:
            t += o[0] * o[1]
    return t


# ---- the sprite slot map (M5 Task 1) ----
# src/slots.h is THE slot map; the Makefile generates build/slots.json from
# it (tools/gen_slots.py). The overlays' run starts at BROKEN_SLOT_BASE and
# this generator's art pack ends at SLOT_AFTER; a drift from the header's
# BROKEN_SLOT_COUNT is caught here (and by tests/test_slots.py).
import json as _json
_SLOTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                           "build", "slots.json")
if os.path.exists(_SLOTS_PATH):
    with open(_SLOTS_PATH) as _sf:
        _SLOTS = _json.load(_sf)
    _run = int(_SLOTS["BROKEN_SLOT_BASE"])
else:
    raise RuntimeError(
        "build/slots.json missing: run the Makefile (it generates the slot "
        "map from src/slots.h before render_broken)")

# the per-cell slot runs: the pack starts at the map's BROKEN_SLOT_BASE and
# spans the 76 cells' widest pictures (SLOT_AFTER = where the ship starts)
_SLOT0 = []
for c in range(76):
    _SLOT0.append(_run)
    _run += _MSW[c]
SLOT_AFTER = _run
assert SLOT_AFTER - int(_SLOTS["BROKEN_SLOT_BASE"]) == \
    int(_SLOTS["BROKEN_SLOT_COUNT"]), (SLOT_AFTER, _SLOTS)


# the per-cell picture row sums (for the packed tile stream's bookkeeping)
_HSUM = [0] * 76
for c in range(76):
    for v in range(g.VIEWS):
        o = overlay(c, v)
        if o:
            _HSUM[c] += o[1]

# ---- C ROM layout ----
_MIS_BASE = rs.TILE_BASE + rs.TILES
_MIS_N = len(gm.tables()["th"]) * rm.VIEWS
# the C ROM's tile numbering: dome (256, its size from geometry.py's knob),
# ship, missiles (l 16 rings-views rows, m 4, s 1, per view), explosions,
# then the broken tiles. The parts are concatenated back to back (the
# Makefile writes them with no pad), so the first broken tile number is
# exactly the sum of the preceding parts' tiles; at the 11x8 box that is
# 718592 bytes = 11228 tiles, matching the file offsets the Makefile
# assembles. The host tests decode the built ROM at these numbers, so the
# value must stay equal to the file layout.
# the missile sheets' tiles per view: mis_l 3x3 = 9, mis_m 2x2 = 4, mis_s
# 1x1 = 1 (the levels' boxes are 2/3 since Dome-scenery Task 2), each cell
# holding MIS_FRAMES (4) flame frames since the rockets task; the explosion
# is rm.EXPL_BOX^2 / 16^2 tiles per frame
TILE_BASE = _MIS_BASE + _MIS_N * (9 + 4 + 1) * rr.FRAMES \
    + rm.EXPL_FRAMES * (rm.EXPL_BOX // 16) ** 2

# ---- the art ----

# The broken-window art (2026-10-16 redesign). Three rules, each fixing
# something the user saw:
# 1. An overlay only paints pixels the DOME draws as this cell's own glass
#    (dome palette 1..7, pixel centre inside the cell's polygon). The dome's
#    outline (glow/core, palette 8..15) and the neighbouring cells are never
#    touched, so nothing spills and the outline stays the dome's own.
# 2. The shards are defined on the 3D face, not per picture: each pixel's
#    ray is cast back onto the face plane, and "glass or hole" depends only
#    on where that point lies on the face. The shape foreshortens and turns
#    exactly with the dome; nothing flips from view to view.
# 3. The pattern is seeded per 5-fold ORBIT, in a frame tied to the dome's
#    pole (invariant under the dome's rotation). At dome_angle 48q+r the
#    runtime shows the art of perm^q(cell), an orbit partner, so the cell
#    keeps its exact look across the 48-step boundaries. The pole cell (the
#    orbit's only fixed point) gets a 5-fold symmetric pattern.

_DOME_VIEWS = None


def _dome_view(v):
    global _DOME_VIEWS
    if _DOME_VIEWS is None:
        _DOME_VIEWS = rd.views()
    return _DOME_VIEWS[v]


def _orbit_id(cell):
    o = {cell}
    x = _PERM[cell]
    while x != cell:
        o.add(x)
        x = _PERM[x]
    return min(o)


@functools.lru_cache(maxsize=None)
def _band(orbit):
    """the glass band per orbit: (angles, depths), periodic piecewise-linear
    control points. depth = the fraction of the way from the outline to the
    face centre that is still glass at that angle."""
    rng = np.random.default_rng(orbit * 7919 + 13)

    def teeth(k, span):
        # alternate deep shards (points of glass reaching into the hole)
        # and shallow notches, at irregular angles: a jagged break
        a = np.sort(rng.uniform(0, span, k))
        dep = np.where(np.arange(k) % 2 == 0,
                       rng.uniform(0.32, 0.62, k), rng.uniform(0.07, 0.17, k))
        return a, dep

    if orbit == 0:                      # the pole pentagon: 5-fold symmetric
        a, dep = teeth(4, 2 * math.pi / 5)
        ang = np.concatenate([a + j * 2 * math.pi / 5 for j in range(5)])
        return ang, np.tile(dep, 5)
    return teeth(2 * int(rng.integers(6, 9)), 2 * math.pi)


def _band_at(orbit, theta):
    ang, dep = _band(orbit)
    a = np.concatenate([ang - 2 * math.pi, ang, ang + 2 * math.pi])
    d = np.concatenate([dep, dep, dep])
    return np.interp(np.mod(theta, 2 * math.pi), a, d)


def _shade(cell, v):
    P = _PTS[list(_CF[cell][0])] @ _ROT[v].T
    n = _face_normal(P, _CF[cell][0])
    return round(5 * max(0.0, float(n @ g.LIGHT)))


HILITE = 11          # broken palette = dome glow 10: the shards' broken edge catches the light


def render_bitmap(cell, v, o):
    """the (cell, view) picture: (ch*16, cw*16) palette-index array."""
    cw, ch, left, top = o
    W, H = cw * TILE, ch * TILE
    face = _CF[cell][0]
    P = _PTS[list(face)] @ _ROT[v].T
    n = _face_normal(P, face)
    C = P.mean(axis=0)
    # the face frame: u points toward the dome's pole along the face
    # (rotation-invariant), w completes it. The pole cell has no such
    # direction; it uses the rotated x axis, and its 5-fold pattern makes
    # the 72-degree jump invisible.
    upw = np.array([0.0, 1.0, 0.0])
    u = upw - n * (upw @ n)
    if np.linalg.norm(u) < 1e-6:
        u = _ROT[v] @ np.array([1.0, 0.0, 0.0])
        u = u - n * (u @ n)
    u /= np.linalg.norm(u)
    w = np.cross(n, u)
    loc = np.column_stack([(P - C) @ u, (P - C) @ w])      # polygon, face frame

    # pixel centres -> rays -> points on the face plane -> face frame
    fwd, right, up = _CAM[1:]
    ys, xs = np.mgrid[0:H, 0:W]
    X = left + xs + 0.5
    Y = top + ys + 0.5
    dirs = (fwd[None, None] + right[None, None] * ((X - _FIT[1]) / _FIT[0])[..., None]
            - up[None, None] * ((Y - _FIT[2]) / _FIT[0])[..., None])
    t = ((C - _POS) @ n) / (dirs @ n)
    q = _POS[None, None] + dirs * t[..., None] - C
    a, b = q @ u, q @ w
    theta = np.arctan2(b, a)

    # inside the polygon (convex) and its radius at each angle
    inside = np.ones((H, W), bool)
    k = len(loc)
    e0, e1 = loc[1] - loc[0], loc[2] - loc[1]
    sgn = np.sign(e0[0] * e1[1] - e0[1] * e1[0])
    for i in range(k):
        p0, p1 = loc[i], loc[(i + 1) % k]
        e = p1 - p0
        inside &= sgn * (e[0] * (b - p0[1]) - e[1] * (a - p0[0])) >= 0
    # radial fraction: point / boundary along the same ray from the centre
    rad = np.full((H, W), np.inf)
    for i in range(k):
        p0, p1 = loc[i], loc[(i + 1) % k]
        e = p1 - p0
        # solve s*(a,b) = p0 + t*e for s (boundary at s = 1/frac)
        den = a * e[1] - b * e[0]
        with np.errstate(divide="ignore", invalid="ignore"):
            s_ = (p0[0] * e[1] - p0[1] * e[0]) / den
            tt = (p0[0] * b - p0[1] * a) / den
        ok = (s_ > 0) & (tt >= -1e-9) & (tt <= 1 + 1e-9)
        rad = np.where(ok, np.minimum(rad, s_), rad)
    frac = np.where(np.isfinite(rad), 1.0 / np.maximum(rad, 1e-9), 0.0)

    # rule 1: only the dome's own glass pixels of this cell
    dv = _dome_view(v)
    box = np.zeros((H, W), np.uint8)
    y0, x0 = max(0, top), max(0, left)
    y1, x1 = min(g.DOME_H, top + H), min(g.DOME_W, left + W)
    if y1 > y0 and x1 > x0:
        box[y0 - top:y1 - top, x0 - left:x1 - left] = dv[y0:y1, x0:x1]
    glass_px = (box >= 1) & (box <= 8)      # glass, back edges, the outline's faint halo
    mine = glass_px & inside & (t[...] > 0)

    band = _band_at(_orbit_id(cell), theta)
    hole = mine & (frac < 1.0 - band)
    out = np.zeros((H, W), np.uint8)
    out[mine] = box[mine] + 1                       # dome i -> broken i + 1
    # the shards' broken edge catches the light: glass next to the hole
    nb = np.zeros_like(hole)
    nb[1:] |= hole[:-1]; nb[:-1] |= hole[1:]
    nb[:, 1:] |= hole[:, :-1]; nb[:, :-1] |= hole[:, 1:]
    out[mine & ~hole & nb] = HILITE
    out[hole] = BLACK
    return out


def _broken_tile0(cell):
    """the tile offset (in the broken tile stream) of the cell's first
    picture's first stone. The stream is per cell: every facing (cell, view)
    picture's w*h stones back to back (cells in order)."""
    t = 0
    for cc in range(cell):
        for v in range(g.VIEWS):
            o = overlay(cc, v)
            if o:
                t += o[0] * o[1]
    return t


# the C ROM file layout needs N_TILES up front (the .c1/.c2 sizes); the
# pictures themselves are drawn below (the tile stream's data).
def _overlay_count():
    n = 0
    for c in range(76):
        for v in range(g.VIEWS):
            o = overlay(c, v)
            if o:
                n += o[0] * o[1]
    return n


N_TILES = _overlay_count()


# The C ROM 16x16 tile layout (tiletool.py's encode/decode_crom_tile):
# the tile's 4 8x8 sub-tiles are serialised in the file order offset 8
# (top-right), 136 (bottom-right), 0 (top-left), 128 (bottom-left). For
# each 8x8, the file holds 8 rows of 2 bytes (the file's two bitplanes),
# each byte a row's 8 pixels LSB-first. encode_tile returns the two
# files' bytes (64 each); decode_tile (tests/test_broken_rom.py) inverts.
def encode_tile(stone):
    c1 = bytearray(64)
    c2 = bytearray(64)
    pos = 0
    for off in (8, 136, 0, 128):        # 8x8 sub-tile corner offset
        sy, sx = off // 16, off % 16    # (row, col) of its top-left
        for y in range(8):
            p0 = p1 = p2 = p3 = 0
            for x in range(8):
                px = int(stone[sy + y][sx + x])
                p0 |= (px & 1) << x
                p1 |= ((px >> 1) & 1) << x
                p2 |= ((px >> 2) & 1) << x
                p3 |= ((px >> 3) & 1) << x
            c1[pos] = p0
            c1[pos + 1] = p1
            c2[pos] = p2
            c2[pos + 1] = p3
            pos += 2
    return bytes(c1), bytes(c2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("header")
    ap.add_argument("--preview")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    c1 = bytearray()
    c2 = bytearray()
    view_t0 = []
    for cell in range(76):
        row = []
        y = 0
        for v in range(g.VIEWS):
            o = overlay(cell, v)
            if o is None:
                row.append(0)
                continue
            cw, ch, left, top = o
            row.append(_view_t0(cell, v))     # the packed tile offset
            bmp = render_bitmap(cell, v, o)
            assert bmp.shape == (ch * TILE, cw * TILE), (cell, v, o)
            for r in range(ch):
                for c in range(cw):
                    h1, h2 = encode_tile(
                        bmp[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE])
                    c1 += h1
                    c2 += h2
            y += ch
        view_t0.append(row)
    assert len(c1) == len(c2) == N_TILES * 64, (len(c1), N_TILES)

    # the visual strip (--preview): the pictures laid out in a grid the eye
    # can read — NOT the C ROM layout (the ROM's tiles are packed per the
    # runtime's fetch order, so they are not a readable rectangle).
    if args.preview:
        cells_pv = min(8, 76)
        views_pv = min(6, g.VIEWS)
        cells = [0, 1, 2, 5, 8, 15, 36, 45][:cells_pv]
        views = [0, 1, 2, 5, 11, 23][:views_pv]
        w_all = sum(overlay(c, v)[0] for c in cells for v in views
                    if overlay(c, v)) * TILE + cells_pv * 2
        h_all = sum(overlay(c, v)[1] for c in cells for v in views
                    if overlay(c, v)) * TILE + views_pv * 2
        strip = np.full((h_all, w_all), 0, np.uint8)
        xo = yo = 0
        for c in cells:
            yo = 0
            for v in views:
                o = overlay(c, v)
                if o is None:
                    continue
                bmp = render_bitmap(c, v, o)
                strip[yo:yo + bmp.shape[0], xo:xo + bmp.shape[1]] = bmp
                yo += bmp.shape[0] + 2
            xo += max((overlay(c, vv)[0] for vv in views if overlay(c, vv)),
                      default=1) * TILE + 2
        trim = strip[:yo + 1, :xo]
        pv = Image.fromarray(trim, "P")
        pv.putpalette([c for rgb in BROKEN_PALETTE for c in rgb])
        pv.convert("RGB").resize((trim.shape[1] * 3, trim.shape[0] * 3),
                                 Image.NEAREST).save(args.preview)

    # ---- the header ----
    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/render_broken.py: do not edit */\n"
          "#ifndef BROKEN_MAP_H\n#define BROKEN_MAP_H\n")
        w(f"#define BROKEN_VIEWS {g.VIEWS}\n")
        w(f"#define BROKEN_TILE_BASE {TILE_BASE}\n")
        # the slot map is src/slots.h (M5 Task 1): the base and after are
        # defined there, not here; the module-level assert above already
        # proved the generator's pack ends exactly at BROKEN_SLOT_AFTER
        
        w("/* the 5-fold cell permutation: a cell's picture at dome_angle =\n"
          "   q*48 + r is broken_perm^q(cell) at view r (the art stores the\n"
          "   48 views; the runtime maps (cell, dome_angle) through this). */\n")
        w("static const u8 broken_perm[76] = {" + ", ".join(map(str, _PERM)) + "};\n")
        w("static const u16 broken_slot0[76] = {" + ", ".join(map(str, _SLOT0)) + "};\n")
        w("static const u8 broken_max_w[76] = {" + ", ".join(map(str, _MSW)) + "};\n")
        w("static const u16 broken_tile0[76] = {\n  ")
        for cell in range(76):
            w(("  " if cell else "") + str(_broken_tile0(cell))
              + ("," if cell + 1 < 76 else "\n"))
        w("};\n")
        w("/* broken_view_t0[cell][view]: the picture's tile offset (in tiles)\n"
          "   inside the cell's tile run; 0 when the cell faces away. The\n"
          "   picture's stones are CONSECUTIVE tiles: tile =\n"
          "   BROKEN_TILE_BASE + broken_tile0[cell] + broken_view_t0[cell][view]\n"
          "   + r * w + c, for stone row r (0..h-1) and stone column c\n"
          "   (0..w-1) of the picture {w, h, ...} (see broken_cell). The tile\n"
          "   stream in broken.c1/c2 is exactly this order, so every tile the\n"
          "   cartridge fetches holds the picture's stone (test_broken_rom). */\n")
        w("static const u16 broken_view_t0[76][%d] = {\n" % g.VIEWS)
        for cell in range(76):
            w("  {" + ", ".join(map(str, view_t0[cell])) + "},\n")
        w("};\n")
        w("/* broken_cell[cell][view]: {w, h, canvas x, canvas y} in stones\n"
          "   and dome-box px; {0,0,0,0} = the cell faces away. The canvas\n"
          "   x/y are signed (the dome box is DOME_W px wide, its y origin is\n"
          "   above the top row), so the array is s16. */\n")
        w("static const s16 broken_cell[76][%d][4] = {\n" % g.VIEWS)
        for cell in range(76):
            row = []
            for v in range(g.VIEWS):
                o = overlay(cell, v)
                if o is None:
                    row.append("{0,0,0,0}")
                else:
                    row.append("{%d,%d,%d,%d}" % o)
            w("  {" + ", ".join(row) + "},\n")
        w("};\n")
        w("static const u16 broken_pal[16] = {0x8000, "
          + ", ".join("0x%04x" % rm.neo(c) for c in BROKEN_PALETTE[1:]) + "};\n")
        w(f"#define BROKEN_TILES {N_TILES}   /* the tile count in broken.c1/c2 "
          "(7909 stones packed) */\n")
        w("#endif\n")

    # ---- the C ROM payloads ----
    # Each tile is 32 bytes per plane file (planes 0-1 in c1, 2-3 in c2), the
    # same encoding tiletool.py would write for a sheet laid out in exactly
    # the stream's order (which no tiletool sheet can be: the row-major
    # numbering cannot express a w x h block whose row stride is the
    # picture's own width). The Makefile concatenates these files with the
    # other sheets', so a tile's byte offset in the C ROM = its number * 64.
    for name, data in (("broken.c1", bytes(c1)), ("broken.c2", bytes(c2))):
        with open(os.path.join(args.outdir, name), "wb") as f:
            f.write(data)


if __name__ == "__main__":
    main()
