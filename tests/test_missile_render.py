"""The rocket sheets (tools/render_rockets.py), their tile map, the flame's
4-frame auto-animation layout and their place in the C ROM; the explosion,
unchanged."""
import os
import re
import sys

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import geometry as g  # noqa: E402  (the missile tile base follows the dome's)
import render_hovercraft as rs  # noqa: E402  (the ship's tile count, before the missiles)
B = os.path.join(ROOT, "build")
A = os.path.join(B, "assets")
H = open(os.path.join(B, "missile_map.h")).read()
SIZES = [("l", 48, 32), ("m", 32, 16), ("s", 16, 8)]
N = 12 * 25                                      # rings x views
F = 4                                            # flame frames
BODY = (2, 10)                                   # palette: whites 2..6, red trim 7..10
FLAME = (11, 15)


def ints(name):
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % re.escape(name), H, re.S).group(1)
    return [int(n) for n in re.findall(r"-?\d+", body)]


def pictures(name, box):
    """[picture][frame] -> box x box index arrays, reassembled from the
    64-px sheet (tile row i = tile i's 4 frames)."""
    im = Image.open(os.path.join(A, name + ".gif"))
    assert im.mode == "P"
    a = np.array(im)
    assert a.max() < 16 and a.shape[1] == 16 * F
    cols = box // 16
    tiles = a.reshape(-1, 16, F, 16).transpose(0, 2, 1, 3)    # [tile][frame][16][16]
    assert len(tiles) == N * cols * cols
    out = []
    for p in range(N):
        t = tiles[p * cols * cols:(p + 1) * cols * cols].reshape(cols, cols, F, 16, 16)
        out.append([t[:, :, f].transpose(0, 2, 1, 3).reshape(box, box) for f in range(F)])
    return out


def in_(a, rng):
    return (a >= rng[0]) & (a <= rng[1])


def test_every_rocket_fits_its_box_with_the_nose_on_the_tip():
    tips = ints("mis_tip")
    assert len(tips) == 3 * N * 3
    for li, (name, box, length) in enumerate(SIZES):
        pics = pictures("mis_" + name, box)
        for i, frames in enumerate(pics):
            tx, ty, used = tips[(li * N + i) * 3:(li * N + i + 1) * 3]
            for f, a in enumerate(frames):
                edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
                assert (edge == 0).all(), f"{name} {i} frame {f}: touches the box"
            body = in_(frames[0], BODY)
            # a rocket flying straight away shows mostly its flame
            seen = body | in_(frames[0], FLAME)
            assert seen.sum() >= 0.75 * length, f"{name} {i}: almost nothing drawn"
            # the body is mis_len long unless the rocket and its flame would
            # not fit: never longer, and at least half
            assert 0.5 * length <= used <= length, f"{name} {i}: drawn {used} px long"
            # the nose is drawn there, or hidden behind the flame (tail-on)
            near = seen[max(0, ty - 1):ty + 2, max(0, tx - 1):tx + 2]
            assert near.any(), f"{name} {i}: nothing at the nose ({tx}, {ty})"


def test_only_the_flame_flickers():
    """the 4 frames share the body (whites, red trim) pixel for pixel except
    where a frame's flame covers it (a rocket flying away from the camera
    shows its flame in front), and the flame changes between frames."""
    for name, box, _ in SIZES:
        changed = 0
        for i, frames in enumerate(pictures("mis_" + name, box)):
            fl = [in_(fr, FLAME) for fr in frames]
            anyfl = np.logical_or.reduce(fl)
            for _ in range(2):                      # and 2 px around it: an edge pixel
                pad = np.pad(anyfl, 1)              # partly under the flame can flip
                anyfl = anyfl | pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
            b0 = np.where(in_(frames[0], BODY) & ~anyfl, frames[0], 0)
            for f in range(1, F):
                bf = np.where(in_(frames[f], BODY) & ~anyfl, frames[f], 0)
                # (measured 10-26: 7 of 900 views have 1 pixel where a fin's
                # edge meets the flame's flicker)
                assert (b0 != bf).sum() <= 1, f"{name} {i} frame {f}: the body moved"
            changed += any((fl[0] != fl[f]).any() for f in range(1, F))
        # the flame is visible and flickers in nearly every view; at 16 px a
        # nose-on view can hide it (measured 10-26: 264 of 300 at 16 px)
        need = (N * 8) // 10 if box == 16 else (N * 9) // 10
        assert changed >= need, f"{name}: the flame flickers in only {changed} of {N}"


def test_the_body_is_outlined_and_trimmed_red():
    """every body pixel is ringed (outline or flame, never bare background:
    a tail-on rocket can be ringed by its flame alone);
    nearly every view shows red trim (a tail-on view can hide the nose and
    see the fins edge-on) and is mostly white."""
    for name, box, _ in SIZES[:2]:
        red = white = 0
        for i, frames in enumerate(pictures("mis_" + name, box)):
            a = frames[0]
            body = in_(a, BODY)
            pad = np.pad(body, 1)
            nb = pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
            rim = nb & (a == 0)
            assert not rim.any(), f"{name} {i}: a body pixel touches the background, unoutlined"
            red += bool(in_(a, (7, 10)).any())
            white += bool(in_(a, (2, 6)).sum() > in_(a, (7, 10)).sum() // 2)
        assert red >= (N * 9) // 10, f"{name}: red trim in only {red} of {N} views"
        # mostly white, except near tail-on (the fins seen from behind)
        assert white >= (N * 9) // 10, f"{name}: mostly white in only {white} of {N} views"


def test_the_animation_layout():
    """each tile's 4 frames are 4 consecutive tile numbers from a multiple of
    4 (the LSPC replaces the low 2 bits with its counter)."""
    base = ints("mis_tile_base")
    assert all(b % F == 0 for b in base)
    assert re.search(r"#define MIS_FRAMES\s+4\b", H)


def test_explosion_frames():
    im = Image.open(os.path.join(A, "expl.gif"))
    a = np.array(im)
    frames = [a[i * 48:(i + 1) * 48] for i in range(a.shape[0] // 48)]
    assert len(frames) == 16
    assert all((f > 0).sum() > 20 for f in frames)
    spread = [np.ptp(np.nonzero(f)[1]) for f in frames]
    assert spread[-1] > spread[0]                # the fragments fly out


def test_tiles_follow_the_ship_in_c_rom():
    base = ints("mis_tile_base")
    first = 256 + g.VIEWS * g.DOME_COLS * g.DOME_ROWS + rs.TILES
    assert base == [first, first + N * 9 * F, first + N * 13 * F]
    expl = int(re.search(r"#define EXPL_TILE_BASE (\d+)", H).group(1))
    assert expl == first + N * 14 * F
    rom = open(os.path.join(B, "rom", "esrg-c1.c1"), "rb").read()
    for name, start in (("mis_l", base[0]), ("mis_m", base[1]), ("mis_s", base[2]), ("expl", expl)):
        part = open(os.path.join(A, name + ".c1"), "rb").read()
        assert rom[start * 64:start * 64 + len(part)] == part, name
    assert (expl + 16 * 16) * 64 <= len(rom)


def test_palettes():
    for name in ("mis_pal", "bul_pal", "expl_pal"):
        p = re.search(r"%s\[16\] = \{(.*?)\}" % name, H).group(1).split(",")
        assert len(p) == 16 and p[0].strip() == "0x8000"
    p = re.search(r"mis_pal\[16\] = \{(.*?)\}", H).group(1).split(",")
    assert int(p[1], 16) & 0x0fff == 0           # the outline is black
