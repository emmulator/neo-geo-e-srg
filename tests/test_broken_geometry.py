"""The broken-window overlay tables against the exact geometry.

  test_broken_geometry.py   (host, pytest)

Proves the task's geometry requirement: for every view and every cell that
is visible in that view, the overlay picture covers the cell's visible
area in the dome picture (allowing a pixel or so at the outline) and
nothing outside it, using the dome picture itself as the reference.

Specifically:
  1. `broken_cell[cell][view]` matches tools/render_broken.overlay: the
     {w, h} in stones and the canvas offset are what the generator uses to
     draw the (cell, view) picture (0 = faces away).
  2. For every facing (cell, view), the overlay paints every pixel the
     dome draws as the cell's glass, and nothing else: never the outline,
     never a neighbouring cell (the user's 2026-10-16 report).
  3. The picture has a genuine broken hole: black, with shards of glass
     round it, wherever the cell has room for one; and the look survives
     the runtime's 5-fold relabel at dome_angle 48.
  4. The 18 cells on the dome's far side show no overlay at any view.
"""
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import geometry as g  # noqa: E402
import render_broken as rb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
H = open(os.path.join(HERE, "..", "build", "broken_map.h")).read()
DOME = np.array(Image.open(os.path.join(HERE, "..", "build", "assets", "dome.gif")))

VIEWS = g.VIEWS
NCELLS = 76

# ---- parse the generated tables ----

def _int_table(name, dims):
    m = re.search(name + r"\[[^\]]*\](?:\[[^\]]*\])* = \{([\s\S]*?)\};", H)
    assert m, f"table {name} not found"
    body = m.group(1)
    vals = [int(x) for x in re.findall(r"-?\d+", body)]
    n = 1
    for d in dims:
        n *= d
    assert len(vals) == n, f"{name}: {len(vals)} values, want {n}"
    if len(dims) == 1:
        return vals
    if len(dims) == 2:
        return [vals[i * dims[1]:(i + 1) * dims[1]] for i in range(dims[0])]
    return [[vals[(i * dims[1] + j) * dims[2]:(i * dims[1] + j + 1) * dims[2]]
             for j in range(dims[1])] for i in range(dims[0])]


SLOT0 = _int_table("broken_slot0", [NCELLS])
MAXW = _int_table("broken_max_w", [NCELLS])
TILE0 = _int_table("broken_tile0", [NCELLS])
CELL = _int_table("broken_cell", [NCELLS, VIEWS, 4])
VIEW_T0 = _int_table("broken_view_t0", [NCELLS, VIEWS])


def overlay_ref(cell, v):
    """the generator's own overlay (the reference)."""
    o = rb.overlay(cell, v)
    return None if o is None else (o[0], o[1], o[2], o[3])


def _poly_px(cell, v):
    R = rb._ROT[v]
    face = rb._CF[cell][0]
    P = rb._PTS[list(face)] @ R.T
    d = P - rb._POS
    fwd, right, up = rb._CAM[1:]
    z = d @ fwd
    return np.column_stack([rb._FIT[1] + rb._FIT[0] * (d @ right) / z,
                            rb._FIT[2] - rb._FIT[0] * (d @ up) / z])


def poly_mask(poly, W, H, inset=0.0):
    """mask of the polygon, optionally shrunk toward its centroid by `inset`
    px (the coverge check's outline tolerance)."""
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    if inset:
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        sh = [(cx + (x - cx) * (1 - inset / 8), cy + (y - cy) * (1 - inset / 8))
              for x, y in poly]
    else:
        sh = poly
    d.polygon([(float(p[0]), float(p[1])) for p in sh], fill=255)
    return np.asarray(im) > 0


def test_tables_match_the_generator():
    for cell in range(NCELLS):
        for v in range(VIEWS):
            ref = overlay_ref(cell, v)
            got = tuple(CELL[cell][v])
            if ref is None:
                assert got == (0, 0, 0, 0), (cell, v, got)
            else:
                assert got == ref, (cell, v, got, ref)
        # slot layout (per cell, not per view)
        assert SLOT0[cell] == rb._SLOT0[cell], (cell, SLOT0[cell])
        assert MAXW[cell] == rb._MSW[cell], (cell, MAXW[cell])
        assert TILE0[cell] == rb._broken_tile0(cell), (cell, TILE0[cell])

def _dome_box(v, o):
    """the dome picture's palette indices under the (cell, view) canvas
    (-1 outside the dome box)."""
    cw, ch, left, top = o
    dv = DOME[v * g.DOME_H:(v + 1) * g.DOME_H]
    box = np.full((ch * 16, cw * 16), -1, int)
    y0, x0 = max(0, top), max(0, left)
    y1, x1 = min(g.DOME_H, top + ch * 16), min(g.DOME_W, left + cw * 16)
    if y1 > y0 and x1 > x0:
        box[y0 - top:y1 - top, x0 - left:x1 - left] = dv[y0:y1, x0:x1]
    return box


def _erode(m):
    e = m.copy()
    e[1:] &= m[:-1]; e[:-1] &= m[1:]; e[:, 1:] &= m[:, :-1]; e[:, :-1] &= m[:, 1:]
    return e


def _dilate(m):
    d = m.copy()
    d[1:] |= m[:-1]; d[:-1] |= m[1:]; d[:, 1:] |= m[:, :-1]; d[:, :-1] |= m[:, 1:]
    return d


def _facing():
    for cell in range(NCELLS):
        for v in range(VIEWS):
            o = overlay_ref(cell, v)
            if o is not None:
                yield cell, v, o


def test_overlay_covers_the_cells_glass():
    """every pixel the dome draws as this cell's glass (palette 1..8: glass,
    back edges seen through it, the outline's faint halo), at least 1 px in
    from the cell's outline, is painted by the overlay."""
    checked = 0
    for cell, v, o in _facing():
        cw, ch, left, top = o
        bmp = rb.render_bitmap(cell, v, o)
        box = _dome_box(v, o)
        poly = poly_mask([(p[0] - left, p[1] - top) for p in _poly_px(cell, v)],
                         cw * 16, ch * 16)
        want = _erode(poly) & (box >= 1) & (box <= 8)
        missed = int((want & (bmp == 0)).sum())
        assert missed <= 1, (cell, v, missed, int(want.sum()))
        checked += 1
    assert checked >= 2000


def test_overlay_never_paints_outside_the_cell():
    """the user's 2026-10-16 report: overlays spilled onto the neighbouring
    tiles. An overlay may only paint the dome's glass pixels (1..8) of its
    own cell: never the outline (9..15), never outside the dome, and never
    more than the 1 px boundary ambiguity outside the cell's polygon."""
    for cell, v, o in _facing():
        cw, ch, left, top = o
        bmp = rb.render_bitmap(cell, v, o)
        box = _dome_box(v, o)
        poly = poly_mask([(p[0] - left, p[1] - top) for p in _poly_px(cell, v)],
                         cw * 16, ch * 16)
        painted = bmp > 0
        on_outline = int((painted & ((box < 1) | (box > 8))).sum())
        outside = int((painted & ~_dilate(poly)).sum())
        assert on_outline == 0, (cell, v, on_outline)
        assert outside == 0, (cell, v, outside)


def test_every_visible_cell_has_a_broken_hole():
    """a cell with room for it shows a black hole with glass round it: any
    cell with >= 12 px of visible glass has black; a big cell (>= 150 px)
    is at least a quarter black and keeps at least a tenth as shards."""
    big = 0
    for cell, v, o in _facing():
        bmp = rb.render_bitmap(cell, v, o)
        area = int((bmp > 0).sum())
        black = int((bmp == rb.BLACK).sum())
        shards = area - black
        if area >= 12:
            assert black >= 1, (cell, v, area)
        if area >= 150:
            big += 1
            assert black >= 0.25 * area, (cell, v, black, area)
            assert shards >= 0.10 * area, (cell, v, shards, area)
    assert big >= 500


def test_the_look_survives_the_symmetry_jump():
    """the runtime shows perm^q(cell)'s art at dome_angle 48q + r, so a cell
    must look the same drawn as itself at view 47 and as its orbit partner
    one step on (view 0, after the 72-degree relabel): the pattern lives on
    the face and is seeded per orbit. Check it by the hole's share of the
    cell, which barely moves in one step if the pattern is continuous."""
    jumps = 0
    for cell in range(NCELLS):
        a = overlay_ref(cell, 47)
        b = overlay_ref(rb._PERM[cell], 0)
        if a is None or b is None:
            continue
        ba = rb.render_bitmap(cell, 47, a)
        bb = rb.render_bitmap(rb._PERM[cell], 0, b)
        if (ba > 0).sum() < 150:
            continue
        fa = (ba == rb.BLACK).sum() / (ba > 0).sum()
        fb = (bb == rb.BLACK).sum() / (bb > 0).sum()
        assert abs(fa - fb) < 0.06, (cell, fa, fb)
        jumps += 1
    assert jumps >= 10


def test_far_side_cells_show_nothing():
    for cell in range(NCELLS):
        for v in range(VIEWS):
            ref = overlay_ref(cell, v)
            if ref is None:
                assert CELL[cell][v] == [0, 0, 0, 0], (cell, v)
    # and they exist: the 18 back cells never face
    never = [c for c in range(NCELLS) if all(overlay_ref(c, v) is None for v in range(VIEWS))]
    assert len(never) >= 10, never


def test_fragment_variation_between_cells():
    # neighbouring cells at the same view have different pictures
    for v in (0, 23):
        for c in range(NCELLS - 1):
            a = overlay_ref(c, v)
            b = overlay_ref(c + 1, v)
            if a is None or b is None:
                continue
            ba = rb.render_bitmap(c, v, a)
            bb = rb.render_bitmap(c + 1, v, b)
            assert not (ba.shape == bb.shape and np.array_equal(ba, bb)), (c, v)


def test_tile_layout_is_contiguous_and_in_bounds():
    # per cell: the view tiles are consecutive in the cell's tile run
    base = rb.TILE_BASE
    for cell in range(NCELLS):
        for v in range(VIEWS):
            o = overlay_ref(cell, v)
            if o is None:
                assert VIEW_T0[cell][v] == 0
                continue
            t0 = TILE0[cell] + VIEW_T0[cell][v]
            n = o[0] * o[1]
            # the picture's w*h stones are consecutive (the runtime's fetch
            # is t0 + r*w + c, so the stream must not interleave anything)
            assert t0 + n <= TILE0[cell] + sum(
                (rb.overlay(cell, vv)[1] * rb.overlay(cell, vv)[0]
                 if rb.overlay(cell, vv) else 0)
                for vv in range(VIEWS)), (cell, v)
            # within the C ROM: the last broken tile is
            # BROKEN_TILE_BASE + total tiles - 1
            assert base + t0 + n <= rb.TILE_BASE + rb.N_TILES, (cell, v)
