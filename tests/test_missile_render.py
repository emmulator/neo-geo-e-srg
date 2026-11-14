"""The missile and explosion sheets, their tile map and their place in the C ROM."""
import os
import re

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
B = os.path.join(ROOT, "build")
A = os.path.join(B, "assets")
H = open(os.path.join(B, "missile_map.h")).read()
SIZES = [("l", 64, 48), ("m", 32, 24), ("s", 16, 12)]
N = 12 * 25                                      # rings x views


def ints(name):
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % re.escape(name), H, re.S).group(1)
    return [int(n) for n in re.findall(r"-?\d+", body)]


def sheet(name, box):
    im = Image.open(os.path.join(A, name + ".gif"))
    assert im.mode == "P" and np.array(im).max() < 16
    a = np.array(im)
    assert a.shape[1] == box
    return [a[i * box:(i + 1) * box] for i in range(a.shape[0] // box)]


def test_every_dart_fits_its_box_with_the_tip_on_it():
    tips = ints("mis_tip")
    assert len(tips) == 3 * N * 3
    for s, (name, box, length) in enumerate(SIZES):
        views = sheet("mis_" + name, box)
        assert len(views) == N
        for i, a in enumerate(views):
            assert (a > 0).sum() > length, f"{name} {i}: almost empty"
            edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
            assert (edge == 0).all(), f"{name} {i}: touches the box"
            tx, ty, used = tips[(s * N + i) * 3:(s * N + i) * 3 + 3]
            assert 0.6 * length <= used <= length, f"{name} {i}: drawn {used} px long"
            near = a[max(0, ty - 2):ty + 3, max(0, tx - 2):tx + 3]
            assert (near > 0).any(), f"{name} {i}: nothing at the tip ({tx}, {ty})"


def test_views_widen_toward_the_side():
    # seen from the front (view 0) a dart is foreshortened; side-on (view 12) it is long
    a = sheet("mis_l", 64)
    for ring in (4, 8):
        front, side = a[ring * 25], a[ring * 25 + 12]
        assert np.ptp(np.nonzero(side)[1]) > np.ptp(np.nonzero(front)[1])


def test_explosion_frames():
    frames = sheet("expl", 64)
    assert len(frames) == 16
    lit = [(f > 0).sum() for f in frames]
    assert all(n > 20 for n in lit)
    spread = [np.ptp(np.nonzero(f)[1]) for f in frames]
    assert spread[-1] > spread[0]                # the fragments fly out


def test_tiles_follow_the_ship_in_c_rom():
    base = ints("mis_tile_base")
    assert base == [4672, 4672 + N * 16, 4672 + N * 20]
    expl = int(re.search(r"#define EXPL_TILE_BASE (\d+)", H).group(1))
    assert expl == 4672 + N * 21
    rom = open(os.path.join(B, "rom", "esrg-c1.c1"), "rb").read()
    for name, first in (("mis_l", base[0]), ("mis_m", base[1]), ("mis_s", base[2]), ("expl", expl)):
        part = open(os.path.join(A, name + ".c1"), "rb").read()
        assert rom[first * 64:first * 64 + len(part)] == part, name
    assert (expl + 16 * 16) * 64 <= len(rom)


def test_palettes():
    for name in ("mis_pal", "bul_pal", "expl_pal"):
        p = re.search(r"%s\[16\] = \{(.*?)\}" % name, H).group(1).split(",")
        assert len(p) == 16 and p[0].strip() == "0x8000"
