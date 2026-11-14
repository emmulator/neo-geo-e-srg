"""The console's generated header, part and picture (dome-scenery Task 7;
the lower console of Task 8).

  test_console.py   (host, pytest)

tools/render_console.py (the orchestrator's art, committed) writes
build/console_map.h and the C ROM part console.c1/c2, column by column (the
tiles are stored column by column, top to bottom). This test holds the built
header and part to the generator's own numbers:

  1. the header's confirmed numbers (dome-scenery Task 8, the lower console):
     CON_COLS 20, CON_TILES 53, and per column c its top y (176 for the
     wings, columns 0..5 and 13..19; 192 for the strip under the dome,
     6..12), its tile rows (3 or 2) and its first tile in the part;
  2. every column fits the screen exactly: con_top[c] + 16 * con_rows[c]
     == 224 (the screen's bottom line);
  3. con_first is the running sum of con_rows (the tiles are stored column
     by column, top to bottom);
  4. the part is 3392 bytes per plane file (53 tiles x 64 bytes), and two
     runs of the generator write identical bytes;
  5. no opaque pixel of render_console.console_picture() lies above its
     column's top (the picture is fully inside the columns' tile rows), and
     con_pal's used indices (2..6 are drawn; 1 and 7 are no longer drawn,
     so only 2..6 must be real colours) and 8..15 are unused (black).

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
import render_console as rc  # noqa: E402

HEADER = os.path.join(BUILD, "console_map.h")
C1 = os.path.join(BUILD, "assets", "console.c1")
C2 = os.path.join(BUILD, "assets", "console.c2")

WING_TOP = 176
STRIP_TOP = 192
STRIP_COLS = range(6, 13)     # 6..12: the strip under the dome


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


def _array(name):
    txt = open(HEADER).read()
    m = re.search(r"static const u8 %s\[CON_COLS\] = \{(.*?)\};" % name,
                  txt, re.S)
    assert m, f"{name} missing from build/console_map.h"
    vals = [int(x) for x in re.findall(r"\d+", m.group(1))]
    assert len(vals) == 20, (name, len(vals))
    return vals


def _palette(path=HEADER):
    txt = open(path).read()
    m = re.search(r"static const u16 con_pal\[16\] = \{(.*?)\};", txt, re.S)
    assert m, "con_pal missing from build/console_map.h"
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    assert len(words) == 16, len(words)
    return words


def test_header_has_the_confirmed_numbers():
    d = _defines()
    assert d["CON_COLS"] == 20
    assert d["CON_TILES"] == 53
    tops = _array("con_top")
    rows = _array("con_rows")
    first = _array("con_first")
    # columns 6..12 are the strip; every other column is a wing
    assert [c for c in range(20) if tops[c] == STRIP_TOP] == list(STRIP_COLS)
    for c in range(20):
        assert tops[c] == (STRIP_TOP if c in STRIP_COLS else WING_TOP), c
        # rows 3 (the wings) and 2 (the strip)
        assert rows[c] == (3 if c not in STRIP_COLS else 2), c
        assert rows[c] == ((224 - tops[c]) // 16), c
    assert tops == [176] * 6 + [192] * 7 + [176] * 7
    assert rows == [3] * 6 + [2] * 7 + [3] * 7
    assert first == [0, 3, 6, 9, 12, 15, 18, 20, 22, 24, 26, 28, 30, 32,
                     35, 38, 41, 44, 47, 50]
    assert _array("con_top") == [t for _, t, _ in rc.columns()]
    assert _array("con_rows") == [r for _, _, r in rc.columns()]
    # the generator's own column list: (col, top, rows)
    want_first, n = [], 0
    for _, _, r in rc.columns():
        want_first.append(n)
        n += r
    assert _array("con_first") == want_first
    assert n == d["CON_TILES"] == 53


def test_every_column_ends_at_the_screen_bottom():
    tops, rows = _array("con_top"), _array("con_rows")
    for c in range(20):
        assert tops[c] + 16 * rows[c] == 224, (
            f"column {c}: top {tops[c]} + 16 * {rows[c]} != 224")


def test_first_is_the_running_sum_of_rows():
    rows, first = _array("con_rows"), _array("con_first")
    run = 0
    for c in range(20):
        assert first[c] == run, (c, first[c], run)
        run += rows[c]
    assert run == _defines()["CON_TILES"]


def test_palette_has_one_bank_with_the_used_indices():
    """con_pal is unchanged from Task 7: indices 1..7 are real colours; the
    lower console's picture now draws only 2..6 (indices 1 and 7 are no
    longer drawn). 8..15 stay unused (black)."""
    words = _palette()
    assert words[0] == 0x8000                    # index 0: transparent
    for k in range(1, 8):
        assert words[k] != 0x8000, f"console colour {k} is black"
    for k in range(8, 16):
        assert words[k] == 0x8000, f"unused console entry {k} is not black"


def test_the_part_is_3392_bytes_per_file():
    n = rc.CON_TILES if hasattr(rc, "CON_TILES") else 53
    assert n == 53 and n * 64 == 3392
    for plane in (C1, C2):
        assert os.path.getsize(plane) == n * 64, (plane,
                                                  os.path.getsize(plane))


def test_two_generator_runs_write_identical_bytes():
    tmp = os.path.join(BUILD, "con-rerun")
    os.makedirs(tmp, exist_ok=True)
    outs = []
    for i in range(2):
        h = os.path.join(tmp, f"c{i}.h")
        a = os.path.join(tmp, f"c{i}.c1")
        b = os.path.join(tmp, f"c{i}.c2")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                         "render_console.py"), h, a, b], check=True)
        outs.append((open(h, "rb").read(), open(a, "rb").read(),
                     open(b, "rb").read()))
    shutil.rmtree(tmp)
    assert outs[0] == outs[1], "two render_console.py runs differ"
    # and they equal what the Makefile built into build/
    assert outs[0][1] == open(C1, "rb").read()
    assert outs[0][2] == open(C2, "rb").read()


def test_no_opaque_pixel_lies_above_its_column_top():
    pic = rc.console_picture()
    assert pic.shape == (rc.SCREEN_H, rc.SCREEN_W) == (224, 320)
    tops, rows = _array("con_top"), _array("con_rows")
    checked = 0
    for c, top, nrows in zip(range(20), tops, rows):
        blk = pic[top:top + 16 * nrows, c * 16:(c + 1) * 16]
        above = pic[:top, c * 16:(c + 1) * 16]
        assert not above.any(), (
            f"column {c}: {int(above.sum())} opaque pixel(s) above its top "
            f"y {top}")
        # the column's own tiles must hold every opaque pixel of its span
        assert int(blk.sum()) > 0, f"column {c} is empty"
        checked += 1
    assert checked == 20
    # and the columns together hold the whole picture: nothing opaque in the
    # picture falls outside the columns' spans
    mask = np.zeros_like(pic, bool)
    for c, top, nrows in zip(range(20), tops, rows):
        mask[top:top + 16 * nrows, c * 16:(c + 1) * 16] = True
    assert not (pic.astype(bool) & ~mask).any(), (
        "opaque picture pixels fall outside the columns' spans")
