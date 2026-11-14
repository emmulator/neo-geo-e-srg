import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
SHEET = os.path.join(ROOT, "build", "assets", "dome.gif")
HEADER = os.path.join(ROOT, "build", "dome_map.h")
W, H, V = 176, 128, 48


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


def test_mirror_views_match():
    vs = views()
    for v in (1, 6, 12, 24):
        a, b = vs[v], vs[(V - v) % V][:, ::-1]
        assert (a != b).mean() < 0.01, f"view {v} vs {V - v}: {(a != b).mean():.3%} differ"


def test_header_tiles_match_the_sheet():
    text = open(HEADER).read()
    assert "#define DOME_TILE_BASE 256" in text
    nums = [int(n) for n in re.findall(r"\b\d+\b", text.split("=", 1)[1])]
    assert len(nums) == V * 11 * 8
    assert min(nums) == 256 and max(nums) == 256 + V * 88 - 1
    # view 0, column 3, row 2 = sheet tile (row-major over 11 tiles per row)
    assert nums[(0 * 11 + 3) * 8 + 2] == 256 + 2 * 11 + 3


def test_c1_c2_hold_every_tile():
    c1 = os.path.getsize(os.path.join(ROOT, "build", "assets", "dome.c1"))
    assert c1 == V * 88 * 64
