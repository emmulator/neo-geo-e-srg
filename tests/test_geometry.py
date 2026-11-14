import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import geometry as g  # noqa: E402

PTS, EDGES, FACES = g.build_mesh()
FIT = g.fit()


def segs(step, mirror=False):
    """visible edges of a view as an array [n, 4] (x0, y0, x1, y1), endpoints ordered."""
    raw, world = g.project(PTS, step)
    px = g.to_px(raw, FIT)
    out = []
    for i, j in g.visible_edges(EDGES, FACES, world):
        a, b = px[i].copy(), px[j].copy()
        if mirror:
            a[0], b[0] = g.DOME_W - a[0], g.DOME_W - b[0]
        if tuple(b) < tuple(a):
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


def test_mesh_matches_the_vectrex_dome():
    assert len(FACES) == 76 and len(EDGES) == 250
    peak = max(FACES, key=lambda f: PTS[f].mean(axis=0)[1])
    assert len(peak) == 5


def test_views_repeat_every_48_steps():
    for s in (0, 7, 23, 47):
        assert same_segments(segs(s), segs(s + g.VIEWS))


def test_view_mirrors():
    # view v and view 48 - v are left/right mirror images
    for v in (1, 5, 13, 24):
        assert same_segments(segs(v), segs(g.VIEWS - v, mirror=True))


def test_fit_fills_the_box():
    allpx = np.vstack([g.to_px(g.project(PTS, s)[0], FIT) for s in range(g.VIEWS)])
    m = g.MARGIN
    assert allpx[:, 0].min() >= m - 1e-6 and allpx[:, 0].max() <= g.DOME_W - m + 1e-6
    assert allpx[:, 1].min() >= m - 1e-6 and allpx[:, 1].max() <= g.DOME_H - m + 1e-6
    assert allpx[:, 0].max() - allpx[:, 0].min() >= g.DOME_W - 2 * m - 1e-6   # uses the width
    assert allpx[:, 1].max() >= g.DOME_H - m - 1e-6                         # sits on the bottom


def test_light_is_in_the_mirror_plane():
    assert abs(g.LIGHT[0]) < 1e-12 and abs(np.linalg.norm(g.LIGHT) - 1) < 1e-12


def test_front_faces_are_about_half():
    world = g.project(PTS, 0)[1]
    n = len(g.front_faces(FACES, world))
    assert 30 <= n <= 60
