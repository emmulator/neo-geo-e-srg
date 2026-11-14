"""The dome's one size knob (the dome-scenery plan, Task 1).

  test_dome_size.py   (host, pytest)

`tools/geometry.py` holds the dome's size in ONE place:
DOME_COLS, DOME_ROWS and DOME_SCALE, with
    DOME_W = 16 * DOME_COLS   and   DOME_H = 16 * DOME_ROWS.

The dome's render is DOME_SCALE times the scale that fills the reference
11x8 (176x128) box, NOT the scale that fills the actual box. That is how
the full-size dome (DOME_COLS 11, DOME_ROWS 8, DOME_SCALE 1) and Dome-
scenery Task 2's 2/3 dome (8x6 with DOME_SCALE 2/3) both come out right:
  - the widest view spans DOME_SCALE * (REF_W - 2*MARGIN) px, whatever
    the box;
  - the render is centred in the box and sits on its bottom margin;
  - changing the box alone does not change the render's size;
  - a box too small for the scaled render is refused by fit()'s assertion.

These checks are relative to the knob's values, so they hold for the
temporary 0.9 / 10-column proof too. The absolute "no visible change"
proof is the ROM hash / boot-test, not a test asserting today's literals.
"""
import os
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import geometry as g  # noqa: E402


def raw_all():
    """the 76 walkable cells' points, projected: Task 3's fit() takes its
    reference scale from the cells, not from the picture's partial pieces."""
    pts, _, faces = g.build_mesh()
    used = sorted({i for f, _ in g.whole_cells(pts, faces) for i in f})
    return np.vstack([g.project(pts[used], s)[0] for s in range(g.VIEWS)])


REF_SCALE = (g.REF_W / 2 - g.MARGIN) / np.abs(raw_all()[:, 0]).max()


def fit_px():
    allraw = raw_all()
    return allraw, g.to_px(allraw, g.fit())


def test_the_knob_is_the_only_size_definition():
    assert g.DOME_W == 16 * g.DOME_COLS
    assert g.DOME_H == 16 * g.DOME_ROWS
    assert g.REF_W == 16 * 11 and g.REF_H == 16 * 8     # the reference box
    assert abs(REF_SCALE - 205.97094534617796) < 1e-9   # today's full-box fit


def test_task_2_knob_values():
    """Dome-scenery Task 2's build: an 8x6 box (128x96 px) at 2/3 of the
    full-box fit, with DOME_X 96 / DOME_Y 104 (the user's choice: the base
    sits just above the score row). The numbers are the task's, and
    tests/layout.py reads them for every checker."""
    assert g.DOME_COLS == 8
    assert g.DOME_ROWS == 6
    assert abs(g.DOME_SCALE - 2.0 / 3.0) < 1e-12
    assert g.DOME_W == 128 and g.DOME_H == 96
    import layout
    assert layout.d.DOME_X == 96 and layout.d.DOME_Y == 104


def test_fit_is_the_scale_times_the_reference_box():
    scale = g.fit()[0]
    assert abs(scale - g.DOME_SCALE * REF_SCALE) < 1e-9
    m = g.MARGIN
    allraw, px = fit_px()
    # the render's own size: DOME_SCALE times the full box's dome
    width = (allraw[:, 0].max() - allraw[:, 0].min()) * scale
    height = (allraw[:, 1].max() - allraw[:, 1].min()) * scale
    assert abs((px[:, 0].max() - px[:, 0].min()) - width) < 1e-6
    assert abs((px[:, 1].max() - px[:, 1].min()) - height) < 1e-6
    # inside the box with MARGIN each side; centred; on the bottom margin
    assert px[:, 0].min() >= m - 1e-6 and px[:, 0].max() <= g.DOME_W - m + 1e-6
    assert px[:, 1].min() >= m - 1e-6 and px[:, 1].max() <= g.DOME_H - m + 1e-6
    assert abs(px[:, 0].min() - (g.DOME_W - width) / 2) < 1e-6
    assert abs(g.DOME_W - px[:, 0].max() - px[:, 0].min()) < 1e-6
    assert abs(px[:, 1].max() - (g.DOME_H - m)) < 1e-6


def test_the_box_alone_does_not_size_the_dome():
    """Two different boxes big enough for the render: the same scale."""
    saved = (g.DOME_COLS, g.DOME_ROWS, g.DOME_W, g.DOME_H, g.DOME_SCALE)
    try:
        g.DOME_SCALE = 0.8
        g.DOME_COLS, g.DOME_ROWS = 10, 7
        g.DOME_W, g.DOME_H = 16 * 10, 16 * 7
        a = g.fit()[0]
        g.DOME_COLS, g.DOME_W = 9, 16 * 9
        b = g.fit()[0]
        assert abs(a - b) < 1e-12
        assert abs(a - 0.8 * REF_SCALE) < 1e-9
    finally:
        (g.DOME_COLS, g.DOME_ROWS, g.DOME_W, g.DOME_H,
         g.DOME_SCALE) = saved


def test_a_box_too_small_for_the_scaled_dome_is_refused():
    saved = (g.DOME_COLS, g.DOME_ROWS, g.DOME_W, g.DOME_H, g.DOME_SCALE)
    try:
        g.DOME_SCALE = 1.0
        g.DOME_COLS, g.DOME_ROWS = 8, 5
        g.DOME_W, g.DOME_H = 16 * 8, 16 * 5
        try:
            g.fit()
        except AssertionError:
            pass
        else:
            raise AssertionError("fit() accepted a box too small for the dome")
    finally:
        (g.DOME_COLS, g.DOME_ROWS, g.DOME_W, g.DOME_H,
         g.DOME_SCALE) = saved
