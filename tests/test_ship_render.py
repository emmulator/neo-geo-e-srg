"""The player's sprite sheet (the 1950s hovercraft and its laser bolt, 10-28;
8 headings, one per stick direction, 10-28), its tile maps and its place in
the C ROM (H4: the hovercraft faces its way)."""
import json
import os
import re
import sys

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import geometry as g  # noqa: E402  (the dome's tile count: the size knob)
B = os.path.join(ROOT, "build")
SHEET = os.path.join(B, "assets", "ship.gif")
HEADER = os.path.join(B, "ship_map.h")
S, V, F = 32, 48, 13          # 32-px sprite, 48 latitude views, 13 pictures each
NH = 8                        # headings: h = ship_dir / 4 (0 right, 2 up, 4 left, 6 down)
REST, HOVER, JUMP, RECOIL = 0, 1, 5, 9
BOLT_ANGLES, BOLT_FRAMES = 32, 2
NBOLT = BOLT_ANGLES * BOLT_FRAMES
FLASH, CORE = 15, 15          # the muzzle flash and the bolt's core: palette 15
R_UNIT = json.load(open(os.path.join(ROOT, "tools", "vectrex_missiles.json")))["r_unit"]


def sheet():
    im = Image.open(SHEET)
    assert im.mode == "P" and im.size == (S * NH, S * V * F + 16 * (NBOLT // (2 * NH)))
    return np.array(im)


def pictures(h=1):
    """[view][frame] -> 32 x 32 indices, heading h (default: up-right)."""
    a = sheet()[:, h * S:(h + 1) * S]
    return [[a[(v * F + f) * S:(v * F + f + 1) * S] for f in range(F)] for v in range(V)]


def all_pictures():
    """(h, [view][frame]) for every heading."""
    return [(h, pictures(h)) for h in range(NH)]


def every_view():
    """("heading/view", [frame]) for every heading's every view."""
    return [(f"{h}/{v}", row) for h, pics in all_pictures() for v, row in enumerate(pics)]


def bolts():
    """[angle][frame] -> 16 x 16 indices (tile i = row i // 16, column i % 16)."""
    a = sheet()[S * V * F:]
    n = 2 * NH
    tiles = [a[(i // n) * 16:(i // n) * 16 + 16, (i % n) * 16:(i % n) * 16 + 16] for i in range(NBOLT)]
    return [[tiles[ang * BOLT_FRAMES + k] for k in range(BOLT_FRAMES)] for ang in range(BOLT_ANGLES)]


def header():
    return open(HEADER).read()


def define(name):
    return int(re.search(r"#define %s (\d+)" % name, header()).group(1))


def header_ints(name):
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % name, header(), re.S).group(1)
    return [int(n) for n in re.findall(r"-?\d+", body)]


def test_sheet_is_16_colours():
    assert np.array(Image.open(SHEET)).max() < 16


def test_every_picture_has_the_craft_clear_of_the_sprite_edges():
    # every view's 13 pictures draw a craft (measured 10-28: at least 120
    # pixels) that never touches the 32-px box's edge (the scale is the
    # largest that fits every heading and pose: K 1.45; measured 10-28: at
    # least 80 pixels at K 1.45)
    for h, pics in all_pictures():
        for v, row in enumerate(pics):
            for f, a in enumerate(row):
                assert (a > 0).sum() > 70, f"heading {h} view {v} frame {f}: almost no craft"
                edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
                assert (edge == 0).all(), f"heading {h} view {v} frame {f}: touches the sprite's edge"


def test_cherry_two_tone_and_outline():
    # cherry paint (6..8) is the main colour, with chrome (2..5), the cream
    # panel or glass somewhere, and the black outline (1) round it
    for v, row in every_view():
        a = row[REST]
        paint = ((a >= 6) & (a <= 8)).sum()
        assert paint > (a > 0).sum() // 4, f"view {v}: not mostly cherry"
        assert ((a >= 2) & (a <= 5)).any(), f"view {v}: no chrome"
        assert (a == 1).any(), f"view {v}: no outline"


def test_frames_differ():
    # each animation's frames are different pictures (a hover that bobs, a
    # jump that dips and launches, a recoil that pushes down)
    for v, row in every_view():
        for first in (HOVER, JUMP, RECOIL):
            pics = [row[f].tobytes() for f in range(first, first + 4)]
            assert len(set(pics)) >= 3, f"view {v}: frames {first}.. barely change"


def test_the_recoil_flashes_the_muzzle():
    # the muzzle flash (15) is on the recoil's first frame, smaller on its
    # second, and gone at rest
    for v, row in every_view():
        flash = [(row[RECOIL + k] == FLASH).sum() for k in range(4)]
        assert flash[0] > 0 and flash[0] >= flash[1], (v, flash)
        assert (row[REST] == FLASH).sum() < flash[0], (v, flash)


def test_the_dip_and_the_recoil_push_down():
    # the craft's centre height (screen y grows downward): the jump's dip
    # (JUMP) and the recoil's first frame sit at least a pixel below rest in
    # every view, the launch (JUMP + 1) above the dip (the jump's real height
    # is the runtime's lift of the whole sprite, as for the spider)
    for v, row in every_view():
        cy = {f: float(np.nonzero(row[f])[0].mean()) for f in (REST, JUMP, JUMP + 1, RECOIL)}
        assert cy[JUMP] >= cy[REST] + 1, (v, cy)
        assert cy[RECOIL] >= cy[REST] + 1, (v, cy)
        assert cy[JUMP + 1] < cy[JUMP], (v, cy)


def test_lower_latitudes_sit_lower():
    oys = header_ints("ship_oy")
    assert len(oys) == NH * V
    for h, pics in all_pictures():
        oy = oys[h * V:(h + 1) * V]
        assert oy[0] < oy[-1], h                  # the peak is drawn above the rim
        # the rim view's lowest pixel: the craft's tail may hang down the
        # slope past the dome box; the console strip draws over the ship
        # from line 98 (measured 10-28 at K 1.45: line 100 at headings 0,
        # 1, 3 and 4, i.e. 3 px under the console)
        ys, _xs = np.nonzero(pics[-1][REST])
        assert 0 < oy[-1] and oy[-1] + ys.max() <= g.DOME_H + 4, (h, oy[-1], ys.max())


def test_headings_face_their_way():
    # the top-down view low on the dome (view 47): the craft's long axis
    # lies along its heading on screen. Its pixels' principal axis is
    # within 25 degrees of the heading's screen direction (h 0 right, 2 up,
    # 4 left, 6 down; an axis, so modulo 180), and the cockpit glass
    # (palette 11/12) sits forward of the tail (palette fins sit behind):
    # the glass's centre lies ahead of the craft's centre along the heading.
    for h, pics in all_pictures():
        a = pics[-1][REST]
        ys, xs = np.nonzero(a > 1)
        cx, cy = xs.mean(), ys.mean()
        cov = np.cov(np.stack([xs - cx, -(ys - cy)]))
        w, vec = np.linalg.eigh(cov)
        ax = np.degrees(np.arctan2(vec[1, -1], vec[0, -1])) % 180
        want = (45 * h) % 180
        off = min(abs(ax - want), 180 - abs(ax - want))
        assert off < 25, (h, ax, want)
        gy, gx = np.nonzero((a == 11) | (a == 12))
        d = np.radians(45 * h)
        ahead = (gx.mean() - cx) * np.cos(d) - (gy.mean() - cy) * np.sin(d)
        assert ahead > 0.5, (h, ahead)


def test_bolts():
    heads = header_ints("bolt_head")
    assert len(heads) == BOLT_ANGLES * 2
    for ang, frames in enumerate(bolts()):
        for k, b in enumerate(frames):
            assert (b == CORE).sum() >= 3, f"bolt {ang}/{k}: no hot core"
            assert 20 <= (b > 0).sum() <= 90, f"bolt {ang}/{k}: {(b > 0).sum()} px"
            edge = np.concatenate([b[0], b[-1], b[:, 0], b[:, -1]])
            assert (edge == 0).all(), f"bolt {ang}/{k} touches its tile's edge"
        hx, hy = heads[2 * ang], heads[2 * ang + 1]
        near = frames[0][max(0, hy - 2):hy + 3, max(0, hx - 2):hx + 3]
        assert (near > 0).any(), f"bolt {ang}: nothing at the head ({hx}, {hy})"
        assert frames[0].tobytes() != frames[1].tobytes(), f"bolt {ang} does not shimmer"
    # the head points the picture's way: angle 0 right, 8 down, 16 left, 24 up
    for ang, (dx, dy) in ((0, (1, 0)), (8, (0, 1)), (16, (-1, 0)), (24, (0, -1))):
        hx, hy = heads[2 * ang], heads[2 * ang + 1]
        assert (hx - 7.5) * dx + (hy - 7.5) * dy > 2, (ang, hx, hy)


def test_bolt_angle_table():
    rows = re.search(r"bolt_angle\[(\d+)\]\[48\]", header())
    assert rows
    ang = header_ints("bolt_angle")
    assert len(ang) == int(rows.group(1)) * 48 and max(ang) < BOLT_ANGLES
    # on the front meridian (q48 0) the upper rings' bullets fly straight up
    # the screen (24); the lowest rings' come toward the camera and run down (8)
    first = [ang[k * 48] for k in range(int(rows.group(1)))]
    assert first[0] == 24 and first[-1] == 8, first


def test_muzzle_and_bolt_length():
    # the muzzle stands within 0.2 radii of the cell, about at the bullet's
    # start (BUL_R0, 1.12 radii; at K 1.45 the cannon is shorter and the
    # muzzle is 1.117: measured 10-28); the bolt is 0.1..0.4 radii long
    muzzle, length = define("SHIP_MUZZLE_R") / R_UNIT, define("BOLT_LEN_R") / R_UNIT
    assert 1.1 < muzzle < 1.2, muzzle
    assert 0.1 < length < 0.4, length


def test_tiles_follow_the_dome_in_c_rom():
    base = define("SHIP_TILE_BASE")
    assert base == 256 + g.VIEWS * g.DOME_COLS * g.DOME_ROWS
    n = NH * V * F * 4 + NBOLT
    rest = header_ints("ship_tile")
    anim = header_ints("ship_anim_tile")
    assert len(anim) == NH * V * F * 4 and min(anim) == base and max(anim) == base + NH * V * F * 4 - 1
    assert len(set(anim)) == len(anim)
    assert rest == [anim[((h * V + v) * F + REST) * 4 + k]
                    for h in range(NH) for v in range(V) for k in range(4)]
    assert define("SHIP_BOLT_TILE") == base + NH * V * F * 4
    dome_c1 = os.path.getsize(os.path.join(B, "assets", "dome.c1"))
    assert dome_c1 == (base - 256) * 64
    ship_c1 = open(os.path.join(B, "assets", "ship.c1"), "rb").read()
    assert len(ship_c1) == n * 64
    rom = open(os.path.join(B, "rom", "esrg-c1.c1"), "rb").read()
    assert rom[base * 64:base * 64 + len(ship_c1)] == ship_c1
