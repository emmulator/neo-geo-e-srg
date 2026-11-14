"""The mountains' generated header, part and scroll model (dome-scenery Task 16).

  test_mountains.py   (host, pytest)

tools/render_mountains.py (the orchestrator's art, committed) writes
build/mountain_map.h and the C ROM part mountain.c1/c2, column by column
(tile (col, row) = col * MTN_ROWS + row, as the ground's). This test holds
the built header and part to the generator's own numbers:

  1. the header's confirmed numbers: MTN_Y 52 (the bottom row sits on the
     horizon at GROUND_Y 100), MTN_W 960, MTN_COLS 60, MTN_ROWS 3,
     MTN_TILES 180, and mtn_pal (0 transparent, 1..10 used, 11..15 unused);
  2. the part is 11520 bytes per plane file (180 tiles x 64 bytes), and two
     runs of the generator write identical bytes;
  3. the picture: every pixel of its bottom row is opaque, its top row is
     empty, and the silhouette height changes by at most 2 px between
     neighbouring columns, including 959 -> 0 (the panorama wraps);
  4. the scroll model (tests/mountains_model.py): mtn_scroll(da) =
     da * 960 / 240 = 4 * da equals the C formula (4 * da) for all 240
     dome angles, and the model's driver X and per-column tile numbers
     come from it.

The art is the orchestrator's: this test re-runs the committed generator's
own picture rather than carrying a copy of its numbers. The header/part it
checks are the ones the Makefile built into build/.
"""
import os
import re
import shutil
import subprocess
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BUILD = os.path.join(ROOT, "build")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_mountains as rm  # noqa: E402
import mountains_model as mm  # noqa: E402

HEADER = os.path.join(BUILD, "mountain_map.h")
C1 = os.path.join(BUILD, "assets", "mountain.c1")
C2 = os.path.join(BUILD, "assets", "mountain.c2")


def _defines(path=HEADER):
    """evaluate the header's #defines in order."""
    out = {}
    for raw in open(path):
        m = re.match(r"#define\s+(\w+)\s+(.+)", raw)
        if not m:
            continue
        name, expr = m.group(1), m.group(2).split("/*")[0].strip()
        for k in sorted(out, key=len, reverse=True):
            expr = re.sub(r"\b%s\b" % k, str(out[k]), expr)
        try:
            out[name] = int(eval(expr, {"__builtins__": {}}, {}))
        except (ValueError, NameError, TypeError, SyntaxError):
            pass
    return out


def _palette(path=HEADER):
    txt = open(path).read()
    m = re.search(r"static const u16 mtn_pal\[16\] = \{(.*?)\};", txt, re.S)
    assert m, "mtn_pal missing from build/mountain_map.h"
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    assert len(words) == 16, len(words)
    return words


def test_header_has_the_confirmed_numbers():
    d = _defines()
    ground_y = _defines(os.path.join(BUILD, "ground_map.h"))["GROUND_Y"]
    assert d["MTN_Y"] == 52
    assert d["MTN_W"] == 960
    assert d["MTN_COLS"] == 60
    assert d["MTN_ROWS"] == 3
    assert d["MTN_TILES"] == d["MTN_COLS"] * d["MTN_ROWS"] == 180
    assert d["MTN_Y"] + d["MTN_ROWS"] * 16 == ground_y, (
        "the mountains' bottom row must sit on the horizon (GROUND_Y)")
    # the header's numbers equal the generator's own
    assert (d["MTN_Y"], d["MTN_W"], d["MTN_COLS"], d["MTN_ROWS"]) \
        == (rm.MTN_Y, rm.MTN_W, rm.MTN_COLS, rm.MTN_ROWS)


def test_palette_has_one_bank_with_the_used_indices():
    words = _palette()
    assert words[0] == 0x8000                    # index 0: transparent
    # indices 1..10 are real colours (9, 10: the horizon grass); 11..15 are
    # unused (0x8000 there is black, never drawn: no tile uses them)
    for k in range(1, 11):
        assert words[k] != 0x8000, f"mountain colour {k} is black"
    for k in range(11, 16):
        assert words[k] == 0x8000, f"unused mountain entry {k} is not black"


def test_the_part_is_11520_bytes_per_file():
    n = rm.MTN_COLS * rm.MTN_ROWS          # MTN_TILES: 180
    assert n == 180 and n * 64 == 11520
    for plane in (C1, C2):
        assert os.path.getsize(plane) == n * 64, (
            plane, os.path.getsize(plane))


def test_two_generator_runs_write_identical_bytes():
    tmp = os.path.join(BUILD, "mtn-rerun")
    os.makedirs(tmp, exist_ok=True)
    outs = []
    for i in range(2):
        h = os.path.join(tmp, f"m{i}.h")
        a = os.path.join(tmp, f"m{i}.c1")
        b = os.path.join(tmp, f"m{i}.c2")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                         "render_mountains.py"), h, a, b], check=True)
        outs.append((open(h, "rb").read(), open(a, "rb").read(),
                     open(b, "rb").read()))
    shutil.rmtree(tmp)
    assert outs[0] == outs[1], "two render_mountains.py runs differ"
    # and they equal what the Makefile built into build/
    assert outs[0][1] == open(C1, "rb").read()
    assert outs[0][2] == open(C2, "rb").read()


def test_the_picture_bottom_is_opaque_top_empty_and_wraps_smoothly():
    pic = rm.mountain_picture()
    assert pic.shape == (rm.MTN_H, rm.MTN_W) == (48, 960)
    assert (pic[-1] != 0).all(), "the bottom row must be opaque in all 960 columns"
    assert (pic[0] == 0).all(), "the top row must be empty"
    # the silhouette: the topmost opaque pixel per column; its height above
    # the bottom changes by at most 2 px between neighbours, 959 -> 0 too
    tops = []
    for c in range(rm.MTN_W):
        nz = np.nonzero(pic[:, c])[0]
        assert len(nz), f"column {c} is empty (the bottom row is opaque)"
        tops.append(int(nz[0]))
    heights = [rm.MTN_H - t for t in tops]
    worst = 0
    worst_at = -1
    for c in range(rm.MTN_W):
        d = abs(heights[c] - heights[(c + 1) % rm.MTN_W])
        if d > worst:
            worst, worst_at = d, c
    assert worst <= 2, (f"silhouette height jumps {worst} px at column "
                        f"{worst_at} -> {worst_at + 1}")


def test_the_scroll_model_agrees_with_the_c_formula():
    for da in range(240):
        assert mm.mtn_scroll(da) == mm.c_scroll(da), da
        assert 0 <= mm.mtn_scroll(da) <= 956
    # the extremes: da 0 -> 0, da 239 -> 956, da 240 would be 960
    assert mm.mtn_scroll(0) == 0
    assert mm.mtn_scroll(239) == 956
    # 960/240 is exactly 4: every step is 4 px, no rounding and no divide
    assert mm.mtn_scroll(1) == 4 and mm.c_scroll(1) == 4
    assert mm.c_scroll(159) == 636 and mm.c_scroll(160) == 640


def test_the_model_driver_and_column_tiles_come_from_the_scroll():
    # the driver X is -(s & 15) as a 9-bit value; column k's panorama
    # column wraps at 60 by a conditional subtract
    for da in (0, 1, 15, 60, 119, 120, 150, 239):
        s = mm.mtn_scroll(da)
        assert mm.driver_x(s) == (0 if s % 16 == 0 else 512 - s % 16)
        seen = [mm.column_panorama(s, k) for k in range(mm.MTN_SHOWN)]
        # 21 columns cover 320 px at any 16-px phase; each is the window's
        # next panorama column, wrapping at 60 by one conditional subtract
        assert seen == [((s >> 4) + k) % 60 for k in range(mm.MTN_SHOWN)]
    # the wrap the boot checker pins: da >= 160, the window crosses 60
    s = mm.mtn_scroll(160)
    assert (s >> 4) + 20 >= 60
    # the boot checker's WINDOW frame: a wrap WITH a scroll phase
    s = mm.mtn_scroll(161)
    assert (s >> 4) + 20 >= 60 and s & 15 != 0
