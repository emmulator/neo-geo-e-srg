"""The high-score initials ring's art (tools/render_ring.py, 10-29): its
sheet, palettes and precomputed geometry, and (high-score boards Task B6)
the sheet's place in the built C ROM after the last art part.

The first five checks are the orchestrator's staged checks, renamed into
tests/ by Task B6; the sixth proves the Makefile packs the sheet into the C
ROM at RING_TILE_BASE, where src/ring_gfx.c fetches it.
"""
import os
import re

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
B = os.path.join(ROOT, "build")
SHEET = os.path.join(B, "assets", "ring.gif")
HEADER = os.path.join(B, "ring_map.h")
CROM1 = os.path.join(B, "rom", "esrg-c1.c1")
CROM2 = os.path.join(B, "rom", "esrg-c2.c2")
N, SUB = 37, 6


def header():
    return open(HEADER).read()


def define(name):
    return int(re.search(r"#define %s (-?\d+)" % name, header()).group(1))


def table(name):
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % name, header(), re.S).group(1)
    return [int(n, 0) for n in re.findall(r"-?(?:0x)?[0-9a-fA-F]+", body)]


def tiles():
    a = np.array(Image.open(SHEET))
    assert a.shape == (16 * (N + 1), 16)
    return [a[i * 16:(i + 1) * 16] for i in range(N + 1)]


def _header_define(name):
    """a #define's integer value from the generated map headers (the tile
    bases are built from the headers' own numbers; tests/test_slots.py
    proves the part order)."""
    for fname in sorted(os.listdir(B)):
        if not fname.endswith("_map.h"):
            continue
        txt = open(os.path.join(B, fname)).read()
        m = re.search(r"#define %s (\d+)\b" % re.escape(name), txt)
        if m:
            return int(m.group(1))
    raise AssertionError(f"no #define {name} in build/*_map.h")


def ring_tile_base():
    """the assembled C ROM's first ring tile: after the collapse part (the
    Makefile's CROM1_PARTS order). Mirrors src/ring_gfx.c's
    COLLAPSE_TILE_BASE + COLLAPSE_TILES, with the chain of part bases from
    the generated headers."""
    radar_head_base = (_header_define("RADAR_FRAME_TILE_BASE")
                       + _header_define("RADAR_FRAME_TILES")
                       + _header_define("RADAR_STICK_TILES") * 3)
    collapse_base = (radar_head_base
                     + _header_define("RADAR_HEAD_TILES")
                     + _header_define("GROUND_TILES")
                     + _header_define("MTN_TILES")
                     + _header_define("CON_TILES")
                     + _header_define("PROP_TILES")
                     + _header_define("BAND_TILES"))
    return collapse_base + _header_define("COLLAPSE_TILES")


def _decode_crom_tile(c1, c2, tile):
    """tiletool's 16x16 C ROM tile decode: 64 bytes per plane file, the 4
    8x8 sub-tiles at flat offsets (8,136,0,128), each row's two planes at
    2*(8*i+y). Reimplemented here as tests/test_broken_rom.py does."""
    p1 = c1[tile * 64:(tile + 1) * 64]
    p2 = c2[tile * 64:(tile + 1) * 64]
    out = np.zeros((16, 16), np.uint8)
    for i, off in enumerate((8, 136, 0, 128)):
        sy, sx = off // 16, off % 16
        for y in range(8):
            b0 = p1[2 * (8 * i + y)]
            b1 = p1[2 * (8 * i + y) + 1]
            b2 = p2[2 * (8 * i + y)]
            b3 = p2[2 * (8 * i + y) + 1]
            for x in range(8):
                out[sy + y][sx + x] = ((b0 >> x & 1)
                                       | ((b1 >> x & 1) << 1)
                                       | ((b2 >> x & 1) << 2)
                                       | ((b3 >> x & 1) << 3))
    return out


def test_sheet_glyphs_have_ink_and_outline():
    for i, t in enumerate(tiles()):
        assert t.max() < 16
        if i == 26:                           # the space: tested below
            continue
        assert ((t >= 2) & (t <= 6)).sum() >= 3, f"tile {i}: no glyph"
        assert (t == 1).any(), f"tile {i}: no outline"
        edge = np.concatenate([t[0], t[-1], t[:, 0], t[:, -1]])
        # the outlined 10 x 14 glyph fills the tile's height: only the
        # outline may reach the edge, never the glyph's colours
        assert ((edge == 0) | (edge == 1)).all(), f"tile {i}: glyph on its edge"


def test_the_space_is_blank():
    # position 26 is the space: an empty tile
    assert (tiles()[26] == 0).all()


def test_codes():
    codes = table("ring_code")
    assert len(codes) == N
    assert codes[:26] == list(range(65, 91))
    assert codes[26:33] == [32, 46, 33, 63, 45, 38, 39]
    assert codes[33:35] == [1, 2]                     # TITLE2_STAR, TITLE2_HEART
    assert codes[35:] == [define("RING_ERASE"), define("RING_END")]


def test_geometry():
    x, y, s, k, o = (table(n) for n in ("ring_x", "ring_y", "ring_scb2", "ring_kind", "ring_order"))
    P = define("RING_PHASES")
    assert P == N * SUB and len(x) == len(y) == len(s) == len(k) == len(o) == P * N
    for p in range(P):
        row = slice(p * N, (p + 1) * N)
        assert sorted(o[row]) == list(range(N)), p          # a back-to-front permutation
        kinds = k[row]
        if p % SUB == 0:
            assert kinds.count(2) == 1 and kinds[p // SUB] == 2, p   # the front letter at rest is hot
            assert s[row][p // SUB] == 0x0FFF                         # at full size
        else:
            assert kinds.count(2) == 0, p
        # the drawing order runs back to front: the last drawn is the front
        assert o[row][-1] in (p // SUB, (p // SUB + 1) % N)
        for i in range(N):
            assert 0 <= x[row][i] <= 320 - 16 and 40 <= y[row][i] <= 130, (p, i)
            assert 0x0600 <= s[row][i] <= 0x0FFF, (p, i)


def test_at_most_14_ring_letters_on_a_line():
    # measured 10-29 (the mockup's geometry): the tilt spreads the letters
    y, s = table("ring_y"), table("ring_scb2")
    worst = 0
    for p in range(define("RING_PHASES")):
        cnt = [0] * 224
        for i in range(N):
            h = round(16 * ((s[p * N + i] & 255) + 1) / 256)
            for line in range(y[p * N + i], y[p * N + i] + h):
                cnt[line] += 1
        worst = max(worst, max(cnt))
    assert worst <= 14, worst


def test_the_sheet_is_in_the_c_rom_after_the_last_part():
    """the assembled C ROM holds the ring sheet at RING_TILE_BASE: every one
    of the 38 tiles decodes to the sheet's own pixels (Task B6's Makefile
    proof; src/ring_gfx.c fetches RING_TILE_BASE + position)."""
    base = ring_tile_base()
    c1 = open(CROM1, "rb").read()
    c2 = open(CROM2, "rb").read()
    assert len(c1) == len(c2) == 4194304, "the C ROMs are not the 4 MB build"
    for i, want in enumerate(tiles()):
        got = _decode_crom_tile(c1, c2, base + i)
        assert np.array_equal(got, want), (
            f"ring tile {i} at C ROM tile {base + i} does not match "
            "build/assets/ring.gif — the sheet is not packed where "
            "src/ring_gfx.c fetches it")
    print(f"PASS: all {N + 1} ring tiles at C ROM tile {base} match the sheet")
