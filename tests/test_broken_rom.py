"""Every overlay stone is the tile its picture says — against the real ROM.

  test_broken_rom.py   (host, pytest)

This is the task's proof 1: a test reads the built `broken.c1`/`broken.c2`
and, for every (cell, view) the header says is drawn and every stone of the
picture, decodes the tile at the number the RUNTIME computes and compares it
with the stone `render_bitmap(cell, view)` drew (the intended art).

The runtime tile numbers come from the real C code path: tests/
broken_tiles_dump (`broken_place` + `draw`'s fetch expression, compiled from
src/cracks.c against the generated tables) prints each stone's tile number.
That exercises the same tables and the same formula the cartridge runs, so a
drift in the C or in the generator fails this test.

Tile decode: each C ROM tile is 64 bytes per plane file (4 bitplanes of
16x16 at 1 bit/px; c1 holds planes 0-1, c2 planes 2-3), exactly as
tiletool.py's decode_crom_tile (ngdevkit tools) defines it — reimplemented
here so the test does not depend on the tool's import path.

Before the fix this test must fail: across all (cell, view) pictures only a
handful of stones (today 108 of 7,909 — the top-left stone of pictures whose
row offset is 0) land on the tile the sheet really holds; afterwards, 0 of
7,909 mismatch.
"""
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import geometry as g  # noqa: E402
import render_broken as rb  # noqa: E402

BUILD = os.path.join(ROOT, "build")
C1 = os.path.join(BUILD, "assets", "broken.c1")
C2 = os.path.join(BUILD, "assets", "broken.c2")
DUMP = os.path.join(BUILD, "broken_tiles_dump")
SHEET_W = sum(rb._MSW)          # the sheet's width in stones (tiletool numbers
                                # tiles row-major across it)
_SKT = rb.TILE_BASE             # the C ROM tile where the broken sheet starts
                                # (BROKEN_TILE_BASE: tile numbering continues
                                # from the previous sheets')


def _decode_tile(c1, c2, tile):
    """the tile's 16x16 index array from the two plane files (tiletool's
    decode_crom_tile layout). The 4 8x8 sub-tiles are stored in file order
    at flat offsets (8,136,0,128); sub-tile i's row y lives at byte
    2*(8*i + y) of each file (its two planes)."""
    p1 = c1[tile * 64:(tile + 1) * 64]
    p2 = c2[tile * 64:(tile + 1) * 64]
    out = np.zeros((16, 16), np.uint8)
    for i, off in enumerate((8, 136, 0, 128)):
        sy, sx = off // 16, off % 16            # (row, col) of its top-left
        for y in range(8):
            b0 = p1[2 * (8 * i + y)]
            b1 = p1[2 * (8 * i + y) + 1]
            b2 = p2[2 * (8 * i + y)]
            b3 = p2[2 * (8 * i + y) + 1]
            for x in range(8):
                px = (b0 >> x & 1) | ((b1 >> x & 1) << 1) | \
                     ((b2 >> x & 1) << 2) | ((b3 >> x & 1) << 3)
                out[sy + y][sx + x] = px
    return out


def _dump_lines():
    """run the host dump binary; returns (pictures, stones) parsed from it."""
    if not os.path.exists(DUMP):
        pytest_fail = f"{DUMP} missing — run make first"
        raise SystemExit(pytest_fail)
    out = subprocess.run([DUMP], capture_output=True, text=True, check=True).stdout
    pics, stones = [], []
    for line in out.splitlines():
        p = line.split()
        if p[0] == "P":
            pics.append(tuple(int(x) for x in p[1:]))
        elif p[0] == "S":
            stones.append(tuple(int(x) for x in p[1:]))
    return pics, stones


def _expected_stone(cell, v, r, c):
    """the stone render_bitmap drew, as the runtime reads it (row r, col c)."""
    o = rb.overlay(cell, v)
    bmp = rb.render_bitmap(cell, v, o)
    return bmp[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16]


def test_every_stone_matches_the_sheet():
    """decode the real ROM at the numbers the runtime fetches; each must hold
    exactly the pixels render_bitmap drew for that stone."""
    c1 = open(C1, "rb").read()
    c2 = open(C2, "rb").read()

    # the file space: tile N is at byte N*64; the sheet's tile _SKT is the
    # first broken tile in the file (the C ROM's global numbering, matching
    # BROKEN_TILE_BASE, minus the file's offset where that equals 0)
    # broken.c1 begins with the broken sheet's tile 0 at byte 0, so the
    # broken sheet tile index is just its offset / 64; the runtime adds
    # _SKT (= BROKEN_TILE_BASE) on top, so a stone's sheet-relative index is
    # tile - _SKT.
    total = 0
    mismatches = []
    pics, stones = _dump_lines()
    assert len(stones) == sum(pic[2] * pic[3] for pic in pics), \
        "probe output malformed"   # stones == sum of the pictures' w*h
    for cell, v, r, c, tile in stones:
        total += 1
        sheet_ix = tile - _SKT
        got = _decode_tile(c1, c2, sheet_ix)
        want = _expected_stone(cell, v, r, c)
        if not np.array_equal(got, want):
            mismatches.append((cell, v, r, c, tile))
    assert total > 7000, f"only {total} stones checked — the dump is incomplete"
    if mismatches:
        raise AssertionError(
            f"{len(mismatches)} stone mismatches of {total} (first: "
            f"cell/view/r/c/tile {mismatches[0]}) — the cartridge fetches "
            "tiles that do not hold the picture's stones")
    print(f"PASS: all {total} stones the runtime fetches hold the "
          f"render_bitmap() pixels")


def test_sheet_has_no_large_blank_tails():
    """the fix bundles the pictures tightly: the sheet's tile count is close
    to the used stones, not the 20,735 padded places the old layout left
    mostly empty (the C ROM size decision). Allow the small slack the w*h
    tiling needs (a picture's last half-used stone rows/cols are still
    materialised as full tiles)."""
    ntiles = rb.N_TILES          # the generator's own packed tile count
    assert ntiles < 10000, f"sheet still has {ntiles} tile places"
    assert ntiles >= 7909, f"packed sheet reports {ntiles}, fewer than the used stones"
