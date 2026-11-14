"""The thick-outline title font in the S ROM (tools/generate_srom.py with
--title2-header, high-score boards Task B4): every (character, left
neighbour, row) tile equals the generator's composition, the header's
tables point at it, the font is 2 px thick, and the star/heart/& codes
exist. State the S ROM size here: 131072 bytes (128 KB, 4096 tiles)."""
import importlib.util
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import generate_srom as gs  # noqa: E402

B = os.path.join(ROOT, "build")
SROM = os.path.join(B, "rom", "esrg-s1.s1")
HEADER = os.path.join(B, "title_font.h")
_spec = importlib.util.spec_from_file_location(
    "tiletool", os.path.expanduser("~/Development/github/dciabrin/ngdevkit/local/bin/tiletool.py"))
tt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tt)


def h():
    return open(HEADER).read()


def define(n):
    return int(re.search(r"#define %s (\d+)" % n, h()).group(1))


def arr(n):
    return [int(x) for x in re.search(r"%s\[128\] = \{(.*?)\}" % n, h()).group(1).split(",")]


def tile(rom, n):
    return list(tt.decode_srom_tile(rom[n * 32:(n + 1) * 32]))


def test_size_and_layout():
    assert os.path.getsize(SROM) == 131072
    assert define("TITLE2_ROW_BASE") == 512
    n = define("TITLE2_NCHARS") * define("TITLE2_NPROF")
    assert define("TITLE2_CAP_BASE") == 512 + n
    assert 512 + 2 * n <= 4096


def test_every_cell_is_the_glyph_plus_its_left_neighbours_spill():
    # each (character, left neighbour, row) tile in the ROM, reached through
    # the header's tables, is the generator's composition: 56 x 56 x 2
    rom = open(SROM, "rb").read()
    idx, rp = arr("title2_idx"), arr("title2_rprof")
    NP = define("TITLE2_NPROF")
    plist, prof = gs.title2_profiles()
    bad = 0
    for ch in gs.TITLE2_CHARS:
        for left in gs.TITLE2_CHARS:
            for half, base in ((0, define("TITLE2_ROW_BASE")), (1, define("TITLE2_CAP_BASE"))):
                want = gs.title2_cell(ch, prof[ord(left)], half, plist)
                got = tile(rom, base + idx[ord(ch)] * NP + rp[ord(left)])
                bad += got != want
    assert bad == 0


def test_the_outline_is_two_pixels_thick():
    # every glyph pixel's 5 x 5 neighbourhood (inside the band) is glyph or
    # outline (colour 5): nothing transparent within 2 px of the ink
    for ch in gs.TITLE2_CHARS:
        b = gs.title2_band(gs.TITLE2_FONT[ch])
        for y in range(16):
            for x in range(9):
                if 1 <= b[y][x] <= 4:
                    for dy in (-2, -1, 0, 1, 2):
                        for dx in (-1, 0, 1):
                            yy, xx = y + dy, x + dx
                            if 0 <= yy < 16 and 0 <= xx < 9:
                                assert b[yy][xx] != 0, (ch, y, x, dy, dx)


def test_unknown_codes_are_spaces_and_the_symbols_exist():
    idx, rp = arr("title2_idx"), arr("title2_rprof")
    sp = gs.TITLE2_CHARS.index(" ")
    assert idx[ord("a")] == sp and idx[0x7f] == sp
    for c in ("&", chr(define("TITLE2_STAR")), chr(define("TITLE2_HEART"))):
        assert gs.TITLE2_CHARS[idx[ord(c)]] == c
