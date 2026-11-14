"""The towns-and-forests band's generated header, part and scroll model
(dome-scenery Task 17).

  test_band.py   (host, pytest)

tools/render_band.py (the orchestrator's art, committed) writes
build/band_map.h and the C ROM part band.c1/c2, column by column (tile
(col, row) = col * BAND_ROWS + row, as the mountains'). This test holds the
built header and part to the generator's own numbers:

  1. the header's confirmed numbers: BAND_Y 68 (the bottom row sits on the
     horizon at GROUND_Y 100), BAND_W 768, BAND_COLS 48, BAND_ROWS 2,
     BAND_TILES 96, and band_pal (0 transparent, 1..12 used, 13..15 unused);
  2. the part is 6144 bytes per plane file (96 tiles x 64 bytes), and two
     runs of the generator write identical bytes;
  3. the scroll model (tests/band_model.py): band_scroll(da) =
     round(da * 768 / 240) equals the C formula (16 * da + 2) / 5 for all
     240 dome angles, and the model's driver X and per-column tile numbers
     come from it; the window and tiles wrap at 48.

The art is the orchestrator's: this test re-runs the committed generator's
own picture rather than carrying a copy of its numbers. The header/part it
checks are the ones the Makefile built into build/.
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BUILD = os.path.join(ROOT, "build")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_band as rb  # noqa: E402
import band_model as bm  # noqa: E402

HEADER = os.path.join(BUILD, "band_map.h")
C1 = os.path.join(BUILD, "assets", "band.c1")
C2 = os.path.join(BUILD, "assets", "band.c2")


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
    m = re.search(r"static const u16 band_pal\[16\] = \{(.*?)\};", txt, re.S)
    assert m, "band_pal missing from build/band_map.h"
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    assert len(words) == 16, len(words)
    return words


def test_header_has_the_confirmed_numbers():
    d = _defines()
    ground_y = _defines(os.path.join(BUILD, "ground_map.h"))["GROUND_Y"]
    assert d["BAND_Y"] == 68
    assert d["BAND_W"] == 768
    assert d["BAND_COLS"] == 48
    assert d["BAND_ROWS"] == 2
    assert d["BAND_TILES"] == d["BAND_COLS"] * d["BAND_ROWS"] == 96
    assert d["BAND_Y"] + d["BAND_ROWS"] * 16 == ground_y, (
        "the band's bottom row must sit on the horizon (GROUND_Y)")
    # the header's numbers equal the generator's own
    assert (d["BAND_Y"], d["BAND_W"], d["BAND_COLS"], d["BAND_ROWS"]) \
        == (rb.BAND_Y, rb.BAND_W, rb.BAND_COLS, rb.BAND_ROWS)


def test_palette_has_one_bank_with_the_used_indices():
    words = _palette()
    assert words[0] == 0x8000                    # index 0: transparent
    # indices 1..12 are real colours (11, 12: the horizon grass); 13..15 are
    # unused (0x8000 there is black, never drawn: no tile uses them)
    for k in range(1, 13):
        assert words[k] != 0x8000, f"band colour {k} is black"
    for k in range(13, 16):
        assert words[k] == 0x8000, f"unused band entry {k} is not black"


def test_the_part_is_6144_bytes_per_file():
    n = rb.BAND_COLS * rb.BAND_ROWS          # BAND_TILES: 96
    assert n == 96 and n * 64 == 6144
    for plane in (C1, C2):
        assert os.path.getsize(plane) == n * 64, (
            plane, os.path.getsize(plane))


def test_two_generator_runs_write_identical_bytes():
    tmp = os.path.join(BUILD, "band-rerun")
    os.makedirs(tmp, exist_ok=True)
    outs = []
    for i in range(2):
        h = os.path.join(tmp, f"m{i}.h")
        a = os.path.join(tmp, f"m{i}.c1")
        b = os.path.join(tmp, f"m{i}.c2")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                         "render_band.py"), h, a, b], check=True)
        outs.append((open(h, "rb").read(), open(a, "rb").read(),
                     open(b, "rb").read()))
    shutil.rmtree(tmp)
    assert outs[0] == outs[1], "two render_band.py runs differ"
    # and they equal what the Makefile built into build/
    assert outs[0][1] == open(C1, "rb").read()
    assert outs[0][2] == open(C2, "rb").read()


def test_the_scroll_model_agrees_with_the_c_formula():
    for da in range(240):
        assert bm.band_scroll(da) == bm.c_scroll(da), da
        assert 0 <= bm.band_scroll(da) <= 765
    # the extremes: da 0 -> 0, da 239 -> 765, da 240 would be 768
    assert bm.band_scroll(0) == 0
    assert bm.band_scroll(239) == 765
    # 768/240 = 3.2, never an exact half; the integer form rounds the same
    assert bm.band_scroll(1) == 3 and bm.c_scroll(1) == 3
    assert bm.c_scroll(140) == 448 and bm.c_scroll(141) == 451


def test_the_model_driver_and_column_tiles_come_from_the_scroll():
    # the driver X is -(s & 15) as a 9-bit value; column k's panorama
    # column wraps at 48 by a conditional subtract
    for da in (0, 1, 15, 60, 119, 120, 140, 141, 239):
        s = bm.band_scroll(da)
        assert bm.driver_x(s) == (0 if s % 16 == 0 else 512 - s % 16)
        seen = [bm.column_panorama(s, k) for k in range(bm.BAND_SHOWN)]
        # 21 columns cover 320 px at any 16-px phase; each is the window's
        # next panorama column, wrapping at 48 by one conditional subtract
        assert seen == [((s >> 4) + k) % 48 for k in range(bm.BAND_SHOWN)]
        # every tile comes from the panorama column, top then bottom row
        for k in range(bm.BAND_SHOWN):
            p = bm.column_panorama(s, k)
            assert bm.column_tiles(s, k, 0) == [p * 2, p * 2 + 1]
    # the wrap the boot checker pins: da >= 140, the window crosses 48
    s = bm.band_scroll(140)
    assert (s >> 4) + 20 >= 48
    # the boot checker's WINDOW frame: a wrap WITH a scroll phase
    s = bm.band_scroll(141)
    assert (s >> 4) + 20 >= 48 and s & 15 != 0
