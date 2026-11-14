"""The dome sheet and its tile map header (tools/render_dome.py).

The sheet's size and the header's column/row counts come from the one
size knob in tools/geometry.py (DOME_COLS, DOME_ROWS, DOME_SCALE), read
here from that module, not written down again. The checks are scaled to
the knob's values, so they hold at today's 11x8 and at the temporarily
smaller 10x8 / 0.9 proof.
"""
import os
import re
import sys

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import geometry as g  # noqa: E402

SHEET = os.path.join(ROOT, "build", "assets", "dome.gif")
HEADER = os.path.join(ROOT, "build", "dome_map.h")
W, H, COLS, ROWS, V = g.DOME_W, g.DOME_H, g.DOME_COLS, g.DOME_ROWS, g.VIEWS


def views():
    im = Image.open(SHEET)
    assert im.mode == "P" and im.size == (W, H * V)
    a = np.array(im)
    return [a[v * H:(v + 1) * H] for v in range(V)]


def test_sheet_format_and_palette():
    im = Image.open(SHEET)
    assert im.mode == "P"
    assert np.array(im).max() < 16          # 16 colours: tiletool reads 4-bit indices


def test_every_view_has_a_dome_and_a_clear_outside():
    for v, a in enumerate(views()):
        assert (a > 0).sum() > W * H // 4, f"view {v} nearly empty"
        for y, x in ((0, 0), (0, W - 1)):
            assert a[y, x] == 0, f"view {v}: corner ({x},{y}) not transparent"
        assert (a[:, 0] == 0).all() and (a[:, W - 1] == 0).all(), f"view {v}: touches the side"


def test_views_are_no_longer_mirror_images():
    """Dome-scenery Task 3: the light (render_dome.LIGHT) is off the views'
    mirror plane, so view v and view 48-v are no longer mirror images and
    views() renders each on its own (no mirror averaging). Before the light
    moved they matched to within 1% of their pixels; now a quarter or more
    differ. (The GEOMETRY's mirror symmetry is still true and is checked in
    tests/test_geometry.py::test_view_mirrors; only the shading breaks it.)"""
    vs = views()
    worst = 1.0
    for v in (1, 6, 12, 24):
        a, b = vs[v], vs[(V - v) % V][:, ::-1]
        d = (a != b).mean()
        worst = min(worst, d)
        assert d > 0.05, f"view {v} vs {V - v}: only {d:.3%} differ (still a mirror)"
    # the light itself: upper left (x < 0), slightly behind (z < 0), unit length
    import render_dome as rd
    assert rd.LIGHT[0] < 0 and rd.LIGHT[2] < 0
    assert abs(np.linalg.norm(rd.LIGHT) - 1) < 1e-12
    assert abs(rd.FILL - 0.6) < 1e-12
    print(f"no mirror pair differs less than {worst:.3%}")


def _runs(row):
    """the number of contiguous runs of lit pixels in one row."""
    idx = np.nonzero(row)[0]
    if len(idx) == 0:
        return 0
    return int(1 + (np.diff(idx) > 1).sum())


def _cells_only_view(v):
    """view v drawn from the 76 walkable cells alone (their faces and
    edges), i.e. the picture the dome had before the flat cut's partial
    pieces: the jagged rim."""
    import render_dome as rd
    pts, _edges, faces = g.build_mesh()
    cells = [f for f, _ in g.whole_cells(pts, faces)]
    cell_edges = set()
    for f in cells:
        for k in range(len(f)):
            u, w = f[k], f[(k + 1) % len(f)]
            cell_edges.add((min(u, w), max(u, w)))
    return rd.quantize(rd.render_view(v, pts, sorted(cell_edges), cells, g.fit()))


def test_flat_base_fills_the_jagged_rim():
    """Dome-scenery Task 3 proof 2, as the picture can actually show it.

    The flat cut (CAP_DEG 69.59) leaves 25 partial pieces; drawn as glass
    they fill the gaps the 76 cells alone leave along the bottom. View 0
    drawn from the cells alone has 3 runs in its bottom rows (the old jagged
    rim's separated islands); the full picture has ONE run in every row of
    its lower half, and its bottom row is a single run, 4 px wide. The base
    meets the ground as one unbroken run 64 px wide at its lowest row that
    is at least 60 px wide (y 88), narrowing to the 4 px bottom row - a
    convex silhouette's lowest row is always a tangent, so a 60 px BOTTOM
    row is geometrically impossible; see the commit's Plan-deviation."""
    full = views()[0]
    whole = _cells_only_view(0)
    pts, _edges, faces = g.build_mesh()
    assert g.DOME_COLS == 8 and g.DOME_ROWS == 6 and abs(g.DOME_SCALE - 2 / 3) < 1e-12
    assert len(faces) - len(g.whole_cells(pts, faces)) == 25
    for y in (88, 89, 90):
        assert _runs(whole[y]) >= 2, f"cells-only row {y} has no jagged gap"
        assert _runs(full[y]) == 1, f"flat-base row {y} is not one run"
    for y in range(19, H):                     # the whole lower picture
        assert _runs(full[y]) <= 1, f"view 0 row {y} has a gap"
    bottom = int(np.nonzero(full)[0].max())
    assert _runs(full[bottom]) == 1
    rows = [(y, int(np.nonzero(full[y])[0].max() - np.nonzero(full[y])[0].min() + 1))
            for y in range(H) if full[y].any()]
    wide = [y for y, s in rows if s >= 60]
    assert wide and max(wide) == 88, f"lowest >=60 px row {max(wide) if wide else None}"
    assert dict(rows)[88] == 64
    assert dict(rows)[bottom] == 4
    print(f"view 0 bottom row {bottom}: one run, 4 px; lowest >=60 px row "
          f"y 88 (64 px); widest row {max(s for _, s in rows)} px")


def test_light_from_the_upper_left_is_brighter_on_the_left():
    """Dome-scenery Task 3 proof 3: view 0's cells left of centre are
    brighter than right of centre. The shade is round(5*(0.6 + 0.4*max(0,
    n . LIGHT))); the mean is taken per visible walkable cell (the 76, not
    the picture's partial pieces), split by the cell's projected centroid
    x < DOME_W/2, and cross-checked on the sheet's glass pixels."""
    import render_dome as rd
    pts, _edges, faces = g.build_mesh()
    _raw, world = g.project(pts, 0)
    px = g.to_px(_raw, g.fit())
    left, right = [], []
    for face, _c in g.whole_cells(pts, faces):
        n = g.face_normal(world, face)
        pos = g.camera()[0]
        if n @ (pos - world[list(face)].mean(axis=0)) <= 0:
            continue                            # back face: not drawn
        shade = round(5 * (rd.FILL + (1 - rd.FILL) * max(0.0, float(n @ rd.LIGHT))))
        (left if px[list(face)][:, 0].mean() < g.DOME_W / 2 else right).append(shade)
    assert left and right
    ml, mr = float(np.mean(left)), float(np.mean(right))
    assert ml > mr + 0.5, f"left mean {ml:.4f} is not clearly brighter than right {mr:.4f}"
    p = views()[0]
    cx = g.DOME_W // 2
    glass = (p >= 1) & (p <= 6)
    pl = float(p[:, :cx][glass[:, :cx]].mean())
    pr = float(p[:, cx:][glass[:, cx:]].mean())
    assert pl > pr, f"sheet glass: left {pl:.4f} not brighter than right {pr:.4f}"
    print(f"cell mean shade left of centre {ml:.4f} ({len(left)} cells) > right "
          f"{mr:.4f} ({len(right)} cells); sheet glass means {pl:.4f} vs {pr:.4f}")


def test_header_tiles_match_the_sheet():
    text = open(HEADER).read()
    assert "#define DOME_TILE_BASE 256" in text
    assert f"#define DOME_COLS {COLS}" in text
    assert f"#define DOME_ROWS {ROWS}" in text
    nums = [int(n) for n in re.findall(r"\b\d+\b", text.split("=", 1)[1])]
    assert len(nums) == V * COLS * ROWS
    ntiles = COLS * ROWS
    assert min(nums) == 256 and max(nums) == 256 + V * ntiles - 1
    # view 0, column 3, row 2 = sheet tile (row-major over COLS tiles per row)
    assert nums[(0 * COLS + 3) * ROWS + 2] == 256 + 2 * COLS + 3


def lit_bboxes():
    """the lit (palette index > 0) bounding box of every picture in the
    sheet: [(width, height)] across all views."""
    out = []
    for a in views():
        ys, xs = np.nonzero(a)
        out.append((int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)))
    return out


def test_task_2_dome_is_two_thirds_of_the_full_box():
    """Dome-scenery Task 2 proof 2 (the dome part): at DOME_SCALE 2/3 the
    pictures are 2/3 of the full-box pictures (+/-2 px). The full-box lit
    width is REF_W - 2*MARGIN = 172 px and its height 125 px (measured on
    2026-10-22 from the 11x8 sheet: x 1..174, y 2..126); 2/3 of each is
    ~114.7 x 83.3 px. The sheet's own lit box is the render's, measured
    from the generated sheet, not the box."""
    assert g.DOME_COLS == 8 and g.DOME_ROWS == 6
    assert abs(g.DOME_SCALE - 2 / 3) < 1e-12
    bb = lit_bboxes()
    w = max(b[0] for b in bb)
    h = max(b[1] for b in bb)
    assert abs(w - 2 / 3 * 172) <= 2, f"widest view {w} px, want {2 / 3 * 172:.1f} +/- 2"
    assert abs(h - 2 / 3 * 125) <= 2, f"tallest view {h} px, want {2 / 3 * 125:.1f} +/- 2"
    # the render sits in the box, clear of every edge
    for a in views():
        assert (np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]) == 0).all()


def test_c1_c2_hold_every_tile():
    c1 = os.path.getsize(os.path.join(ROOT, "build", "assets", "dome.c1"))
    assert c1 == V * COLS * ROWS * 64
