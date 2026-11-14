import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import geometry as g  # noqa: E402

PTS, EDGES, FACES = g.build_mesh()
FIT = g.fit()


def _key(x, y):
    """the endpoint ordering key: rounded so an exact mirror tie (a segment
    on the centre line, where the reflected x is 64.0 + a 1-ULP error) orders
    the same on both sides. The segments still compare to 1e-6 px."""
    return (round(float(x), 6), round(float(y), 6))


def segs(step, mirror=False):
    """visible edges of a view as an array [n, 4] (x0, y0, x1, y1), endpoints ordered."""
    raw, world = g.project(PTS, step)
    px = g.to_px(raw, FIT)
    out = []
    for i, j in g.visible_edges(EDGES, FACES, world):
        a, b = px[i].copy(), px[j].copy()
        if mirror:
            a[0], b[0] = g.DOME_W - a[0], g.DOME_W - b[0]
        if _key(b[0], b[1]) < _key(a[0], a[1]):
            a, b = b, a
        out.append([a[0], a[1], b[0], b[1]])
    return np.array(out)


def same_segments(A, B, tol=1e-6):
    """the two segment sets match one to one within tol (order-free)."""
    if A.shape != B.shape:
        return False
    used = np.zeros(len(B), bool)
    for s in A:
        d = np.abs(B - s).max(axis=1)
        d[used] = np.inf
        k = d.argmin()
        if d[k] > tol:
            return False
        used[k] = True
    return True


def test_mesh_has_a_flat_base_but_still_76_cells():
    """Dome-scenery Task 3: the flat cut at CAP_DEG 69.59 makes build_mesh()
    return the 76 whole cells plus 25 partial pieces (101 faces, 300 edges),
    while the walkable cells (make_cells, whole_cells) are still the same 76
    Vectrex cells."""
    assert len(FACES) == 101 and len(EDGES) == 300
    cells = g.whole_cells(PTS, FACES)
    assert len(cells) == 76
    peak = max((f for f, _ in cells), key=lambda f: PTS[f].mean(axis=0)[1])
    assert len(peak) == 5


def test_views_repeat_every_48_steps():
    for s in (0, 7, 23, 47):
        assert same_segments(segs(s), segs(s + g.VIEWS))


def test_view_mirrors():
    # view v and view 48 - v are left/right mirror images
    for v in (1, 5, 13, 24):
        assert same_segments(segs(v), segs(g.VIEWS - v, mirror=True))


def test_fit_fits_the_box():
    # the render's size is DOME_SCALE times the reference box's, NOT the box's
    # (tests/test_dome_size.py proves that relationship); here: inside the box
    # with MARGIN each side, centred, sitting on the bottom margin.
    # the fit is the one from the 76-cell mesh (the task keeps it), so measure
    # the fit's own points, not the partial pieces below the cut
    cells = g.whole_cells(PTS, FACES)
    used = sorted({i for f, _ in cells for i in f})
    allpx = np.vstack([g.to_px(g.project(PTS[used], s)[0], FIT) for s in range(g.VIEWS)])
    m = g.MARGIN
    assert allpx[:, 0].min() >= m - 1e-6 and allpx[:, 0].max() <= g.DOME_W - m + 1e-6
    assert allpx[:, 1].min() >= m - 1e-6 and allpx[:, 1].max() <= g.DOME_H - m + 1e-6
    assert abs(g.DOME_W - allpx[:, 0].max() - allpx[:, 0].min()) < 1e-6  # centred
    assert allpx[:, 1].max() >= g.DOME_H - m - 1e-6                     # sits on the bottom


def test_legacy_light_is_in_the_mirror_plane():
    """g.LIGHT is the ship's and missiles' legacy upper-behind light, which
    stays in the mesh's mirror plane (their pictures do not change). The
    DOME's light is render_dome.LIGHT, off that plane (Task 3)."""
    assert abs(g.LIGHT[0]) < 1e-12 and abs(np.linalg.norm(g.LIGHT) - 1) < 1e-12


def test_front_faces_are_about_half():
    world = g.project(PTS, 0)[1]
    n = len(g.front_faces(FACES, world))
    assert 30 <= n <= 60
