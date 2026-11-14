"""The ship's sprite sheet, its tile map and its place in the C ROM."""
import os
import re

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
B = os.path.join(ROOT, "build")
SHEET = os.path.join(B, "assets", "ship.gif")
HEADER = os.path.join(B, "ship_map.h")
S, V = 32, 48


def views():
    im = Image.open(SHEET)
    assert im.mode == "P" and im.size == (S, S * V)
    a = np.array(im)
    return [a[v * S:(v + 1) * S] for v in range(V)]


def header_ints(name):
    text = open(HEADER).read()
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % name, text, re.S).group(1)
    return [int(n) for n in re.findall(r"-?\d+", body)]


def test_sheet_is_16_colours():
    assert np.array(Image.open(SHEET)).max() < 16


def test_every_view_has_a_ship_clear_of_the_sprite_edges():
    for v, a in enumerate(views()):
        assert (a > 0).sum() > 60, f"view {v}: almost no ship"
        edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        assert (edge == 0).all(), f"view {v}: the ship touches the sprite's edge"


def test_ship_is_symmetric():
    # it stands on the front meridian, nose toward the peak, lit from the mirror plane
    for v, a in enumerate(views()):
        assert (a != a[:, ::-1]).mean() < 0.01, f"view {v} lopsided"


def test_lower_latitudes_sit_lower():
    oy = header_ints("ship_oy")
    assert len(oy) == V
    assert all(b >= a for a, b in zip(oy, oy[1:]))
    assert oy[0] < 0 < oy[-1] < 128 - S + 8      # peak pokes above the box; the rim stays in it


def test_tiles_follow_the_dome_in_c_rom():
    text = open(HEADER).read()
    base = int(re.search(r"#define SHIP_TILE_BASE (\d+)", text).group(1))
    assert base == 256 + 48 * 11 * 8                     # right after the dome's tiles
    tiles = header_ints("ship_tile")
    assert len(tiles) == V * 2 * 2 and min(tiles) == base and max(tiles) == base + V * 4 - 1
    assert tiles[(5 * 2 + 1) * 2 + 0] == base + (5 * 2 + 0) * 2 + 1   # view 5, column 1, row 0
    dome_c1 = os.path.getsize(os.path.join(B, "assets", "dome.c1"))
    assert dome_c1 == (base - 256) * 64
    ship_c1 = open(os.path.join(B, "assets", "ship.c1"), "rb").read()
    assert len(ship_c1) == V * 4 * 64
    rom = open(os.path.join(B, "rom", "esrg-c1.c1"), "rb").read()
    assert rom[base * 64:base * 64 + len(ship_c1)] == ship_c1
