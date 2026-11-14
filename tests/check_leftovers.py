#!/usr/bin/env python3
"""Assertions for the M3 "no leftovers below a shrunk sprite" fix.

  check_leftovers.py SNAP PROBE
    SNAP   a MAME snapshot PNG taken by scripts/leftover_probe.lua on a
           frame that shows a shrunk bullet
    PROBE  the probe's dump (scripts/leftover_probe.lua OUT): per sample
           frame F, one S line per shown slot with SCB2/SCB3/SCB4, its 32
           SCB1 tile numbers and its 32 SCB1 attributes; per frame M lines
           with the missiles' state/ring/phi/r; B lines with the bullets';
           and RPAIR lines for paired rocket snapshots.

Checks:
  1. Rows (VRAM, every sampled frame, every shown slot): the probe planted a
     visible tile in every SCB1 row 0..31 of every missile/bullet/explosion/
     radar-heading slot before the first missile appeared. The game must
     overwrite what it shows, so:
       a. the first `rows` SCB1 rows (rows in {1,2,4}; the radar headings
          are 1-row pictures) hold real picture tiles (tile >= 256, after
          the CROM zero padding),
       b. every SCB1 row from `rows` to 31 is a blank tile (< 256). The
          hardware samples SCB1 rows top-down (the vertical zoom table
          "000-lo.lo" maps screen lines to rows 0..31 of the column; with a
          5-bit row counter that bounds the reach at 31), so blanking the
          whole column below the picture means no leftover can ever show,
          whatever an earlier frame left there.
  2. Picture (the snapshot + that frame's VRAM): no bullet or missile pixels
     lie outside the box its picture should cover, where the box comes from
     the position and shrink read back from SCB3/SCB4/SCB2 (columns are the
     group's shown slots, stepped by hz+1 px; the picture's height is the
     number of screen lines the vertical zoom table gives the picture's
     tiles). A laser bolt must actually be visible inside its box, its
     pixels must equal its bolt tile's colours through the hardware shrink,
     and its head pixel must be on the bullet's point. The radar headings
     are excluded from the pixel box: their colours (the radar's palette)
     are neither red nor the bolt's, so they cannot trip the stray-pixel
     test, and their shrunk 1-line box is unlike the missiles'.
  3. R2 missiles: every displayed missile column's SCB2/SCB3/SCB4 is the old
     dart placement model's, its SCB1 picture tiles are the rocket's
     `tile0 + cell * MIS_FRAMES`, and every SCB1 row (blank rows under the
     picture too) carries palette 3, the 4-frame animation bit (0x0004) and
     the picture's h-flip.
  4. R2 snapshots: the probe's paired snapshots of one front missile are
     compared, pixel for pixel through the hardware shrink, with the rocket
     picture at the LSPC counter read in the probe; two snapshots 4+ frames
     apart must also show different flame pixels at one picture size.
  5. Task H2's bolt: every displayed bullet's SCB1 tile/attributes and
     SCB2/SCB3/SCB4 are the bolt model's (tile = SHIP_BOLT_TILE +
     bolt_angle[ring][q48] * BOLT_FRAMES + shimmer, PAL_SHIP, no flips; head
     pixel on the bullet's point at the dart's shrink), a bullet with
     r < SHIP_MUZZLE_R + BOLT_LEN_R is never shown, two bullets in flight
     shimmer out of step, and a bullet seen across a dome turn changes
     picture with the line.
"""
import glob
import json
import os
import re
import sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
# the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.json
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))
MIS_BEHIND_END = _SLOTS["MIS_BEHIND_SPRITE"] + _SLOTS["MIS_BEHIND_COUNT"] - 1
FRONT_END = _SLOTS["MIS_FRONT_SPRITE"] + _SLOTS["MIS_FRONT_COUNT"] - 1
EXPL_END = _SLOTS["EXPL_SPRITE"] + _SLOTS["EXPL_COUNT"] - 1
RADAR_START = _SLOTS["RADAR_SPRITE"]

# A blank tile is any of the CROM zero-padding tiles 0..255 (BIOS-reserved,
# all transparent); every game tile starts at 4672 (build/missile_map.h).
BLANK_LIMIT = 256
PICTURE_ROWS = (1, 2, 3, 4)         # 3-row pictures are the 2/3 missile

# Task H2: a bullet is the hovercraft's laser bolt, one 16x16 tile chosen
# by its screen azimuth (bolt_angle[ring][q48]) and a two-frame shimmer,
# in PAL_SHIP, drawn by its head pixel (bolt_head) on the bullet's point at
# the old dart's shrink. The model below is that runtime formula; the
# checker holds every displayed SCB word and the snapshot's pixels to it.
sys.path.insert(0, HERE)
import layout as lay  # noqa: E402  (DOME_X/DOME_Y, src/dome.h)

_SHIP_MAP = os.path.join(ROOT, "build", "ship_map.h")
_SHIP_H = os.path.join(ROOT, "src", "ship_gfx.h")
_MISSILE_MAP = os.path.join(ROOT, "build", "missile_map.h")
_MISSILE_TABLES = os.path.join(ROOT, "build", "missiles_tables.h")


def _array(text, name):
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % re.escape(name),
                     text, re.S).group(1)
    return [int(x) for x in re.findall(r"-?\d+", body)]


def _hex_array(text, name):
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % re.escape(name),
                     text, re.S).group(1)
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", body)]


def _define(text, name):
    return int(re.search(r"#define %s\s+(-?\d+)" % re.escape(name),
                         text).group(1))


_SM = open(_SHIP_MAP).read()
_BOLT_TILE = _define(_SM, "SHIP_BOLT_TILE")
_BOLT_ANGLES = _define(_SM, "BOLT_ANGLES")
_BOLT_FRAMES = _define(_SM, "BOLT_FRAMES")
_BOLT_HEAD = _array(_SM, "bolt_head")
_BOLT_ANGLE = _array(_SM, "bolt_angle")
_MUZZLE_R = _define(_SM, "SHIP_MUZZLE_R")
_BOLT_LEN_R = _define(_SM, "BOLT_LEN_R")
_PAL_SHIP = int(re.search(r"#define PAL_SHIP\s+(\d+)",
                          open(_SHIP_H).read()).group(1))
_NBOLT = _BOLT_ANGLES * _BOLT_FRAMES
_BOLT_ATTR = _PAL_SHIP << 8          # PAL_SHIP, no flips, no animation

_MT = open(_MISSILE_TABLES).read()
_MM = open(_MISSILE_MAP).read()
_RING_SIN = _array(_MT, "ring_sin")
_RING_COS = _array(_MT, "ring_cos")
_MIS_SIN = _array(_MT, "mis_sin")
_MIS_OCC = _array(_MT, "mis_occ")
_CAM_PY = _define(_MT, "CAM_PY")
_CAM_PZ = _define(_MT, "CAM_PZ")
_CAM_FY = _define(_MT, "CAM_FY")
_CAM_FZ = _define(_MT, "CAM_FZ")
_CAM_UY = _define(_MT, "CAM_UY")
_CAM_UZ = _define(_MT, "CAM_UZ")
_VIEW_S4 = _define(_MT, "VIEW_S4")
_VIEW_OX4 = _define(_MT, "VIEW_OX4")
_VIEW_OY4 = _define(_MT, "VIEW_OY4")
_VIEW_ZMIN = _define(_MT, "VIEW_ZMIN")
_DART_LEN4 = _define(_MT, "DART_LEN4")
_MIS_COLS = _array(_MM, "mis_cols")
_MIS_LEN = _array(_MM, "mis_len")
_MIS_TIP = _array(_MM, "mis_tip")
_MIS_TILE_BASE = _array(_MM, "mis_tile_base")
_MIS_FRAMES = _define(_MM, "MIS_FRAMES")
_MIS_PAL_WORDS = _hex_array(_MM, "mis_pal")
_MIS_VIEWS = 25                    # src/mis_view.h (25 screen azimuths)
_MIS_COLS_MAX = 3                  # src/mis_gfx.h: the groups' stride
_NMIS = 3
_BUL0 = 3                          # src/missiles.h: NMIS 3
_NBUL = 2                          # obj[3..4]
_DOME_X, _DOME_Y = lay.d.DOME_X, lay.d.DOME_Y
_SCREEN_W, _SCREEN_H = 320, 224


def _cdiv(a, b):
    """C's signed integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _mis_view(ring, j, r):
    """src/mis_view.c's fixed-point projection, exactly."""
    rq = r >> 7
    h = (rq * _RING_SIN[ring]) >> 14
    y = (rq * _RING_COS[ring]) >> 14
    x = (h * _MIS_SIN[j]) >> 14
    jc = j - 180 if j + 60 >= 240 else j + 60
    zc = (h * _MIS_SIN[jc]) >> 14
    dy = y - _CAM_PY
    dz = zc - _CAM_PZ
    z = (dy * _CAM_FY + dz * _CAM_FZ) >> 14
    u = (dy * _CAM_UY + dz * _CAM_UZ) >> 14
    jm = 240 - j if j > 120 else j
    behind = 1 if (r >> 7) < _MIS_OCC[ring * 121 + jm] else 0
    if z < _VIEW_ZMIN:
        return {"shown": 0}
    return {"shown": 1, "behind": behind,
            "x": (_VIEW_OX4 + _cdiv(x * _VIEW_S4, z) + 8) >> 4,
            "y": (_VIEW_OY4 - _cdiv(u * _VIEW_S4, z) + 8) >> 4,
            "len4": _cdiv(_DART_LEN4, z)}


def _tip(l, idx):
    b = (l * 300 + idx) * 3
    return _MIS_TIP[b], _MIS_TIP[b + 1], _MIS_TIP[b + 2]


def bullet_model(dome_angle, ring, phi, r, fc, slot):
    """The bolt model for this frame's bullet: the old dart's shrink, the
    picture from the line's screen azimuth (bolt_angle[ring][q48], q48
    before the dart's mirroring) and its two-frame shimmer, its head pixel
    (bolt_head) on the bullet's point. None = not drawn: hidden under the
    muzzle (r < SHIP_MUZZLE_R + BOLT_LEN_R), off screen, or behind the
    camera."""
    j = (phi + dome_angle) % 240
    if r < _MUZZLE_R + _BOLT_LEN_R:
        return None
    v = _mis_view(ring, j, r)
    if not v["shown"]:
        return None
    len4 = v["len4"]
    q48 = (j + 2) // 5
    if q48 >= 48:
        q48 = 0
    angle = _BOLT_ANGLE[ring * 48 + q48]
    q = q48
    if q > 24:                      # the dart's mirrored view: its shrink
        q = 48 - q
    len4 >>= 1
    l = 0
    while l < len(_MIS_COLS) - 1 and len4 < _MIS_LEN[l] * 8:
        l += 1
    tx0, ty0, drawn = _tip(l, ring * 25 + q)
    f = (len4 << 8) // (drawn << 4)
    if f > 256:
        f = 256
    if f < 64:
        f = 64
    hx, hy = _BOLT_HEAD[angle * 2], _BOLT_HEAD[angle * 2 + 1]
    point_x = _DOME_X + v["x"]
    point_y = _DOME_Y + v["y"]
    x = point_x - ((hx * f) >> 8)
    y = point_y - ((hy * f) >> 8)
    fs = (16 * f) >> 8
    if x >= _SCREEN_W or y >= _SCREEN_H or x + fs <= 0 or y + fs <= 0:
        return None
    hz = ((f << 4) + 128) >> 8
    vz = 255 if f > 255 else f - 1
    height = 1
    if hz:
        hz -= 1
    shimmer = (fc + slot) & 1
    return {"behind": v["behind"], "angle": angle, "shimmer": shimmer,
            "hx": hx, "hy": hy, "f": f, "point_x": point_x,
            "point_y": point_y, "x": x, "y": y,
            "tile": _BOLT_TILE + angle * _BOLT_FRAMES + shimmer,
            "scb2": (hz << 8) | vz,
            "scb3": ((((496 - y) & 0xffff) << 7) | height) & 0xffff,
            "scb4": (((x & 0xffff) << 7) & 0xffff)}


def old_missile_base(dome_angle, ring, phi, r):
    """The old dart model's base-slot words for a missile (the size, position
    and shrink are unchanged by R2): the picture is chosen by ring and
    azimuth, shrunk to fit; the tile base is laid out 4 frames per cell.
    None = not drawn."""
    j = (phi + dome_angle) % 240
    v = _mis_view(ring, j, r)
    if not v["shown"]:
        return None
    len4 = v["len4"]
    q = (j + 2) // 5
    if q >= 48:
        q = 0
    hflip = 0
    if q > 24:
        q = 48 - q
        hflip = 1
    l = 0
    while l < len(_MIS_COLS) - 1 and len4 < _MIS_LEN[l] * 8:
        l += 1
    cols = _MIS_COLS[l]
    tx0, ty0, drawn = _tip(l, ring * _MIS_VIEWS + q)
    f = (len4 << 8) // (drawn << 4)
    if f > 256:
        f = 256
    if f < 64:
        f = 64
    size = cols * 16
    tx = (size - 1 - tx0) if hflip else tx0
    ty = ty0                                  # missiles do not v-flip
    x = _DOME_X + v["x"] - ((tx * f) >> 8)
    y = _DOME_Y + v["y"] - ((ty * f) >> 8)
    if (x >= _SCREEN_W or y >= _SCREEN_H
            or x + ((size * f) >> 8) <= 0
            or y + ((size * f) >> 8) <= 0):
        return None
    hz = ((f << 4) + 128) >> 8
    vz = 255 if f > 255 else f - 1
    height = (cols * (vz + 1) + 255) >> 8
    if height == 0:
        height = 1
    if hz:
        hz -= 1
    return {"behind": v["behind"], "cols": cols, "hflip": hflip, "vflip": 0,
            "tile0": (_MIS_TILE_BASE[l]
                      + (ring * _MIS_VIEWS + q) * cols * cols * _MIS_FRAMES),
            "x": x, "y": y, "hz": hz, "vz": vz, "height": height,
            "scb2": (hz << 8) | vz,
            "scb3": ((((496 - y) & 0xffff) << 7) | height) & 0xffff,
            "scb4": (((x & 0xffff) << 7) & 0xffff)}


def parse_bullets(fname):
    """{frame: (fc, dome_angle, [bullet dicts])} from the probe's B records."""
    out = {}
    for line in open(fname):
        if not line.startswith("B "):
            continue
        p = line.split()
        n, fc, da = int(p[1]), int(p[2]), int(p[3])
        bullets, k = [], 4
        for _ in range(_NBUL):
            i, state, ring, phi = (int(p[k]), int(p[k + 1]),
                                   int(p[k + 2]), int(p[k + 3]))
            r = int(p[k + 4])
            b = [int(x, 16) for x in p[k + 5:k + 9]]
            f = [int(x, 16) for x in p[k + 9:k + 13]]
            bullets.append({"i": i, "state": state, "ring": ring,
                            "phi": phi, "r": r, "b": b, "f": f})
            k += 13
        out[n] = (fc, da, bullets)
    return out


def parse_missiles(fname):
    """{frame: (dome_angle, [missile dicts])} from the probe's M records."""
    out = {}
    for line in open(fname):
        if not line.startswith("M "):
            continue
        p = line.split()
        n, da = int(p[1]), int(p[2])
        missiles, k = [], 3
        for _ in range(_NMIS):
            i, state, kind, ring, phi, r = (int(p[k]), int(p[k + 1]),
                                            int(p[k + 2]), int(p[k + 3]),
                                            int(p[k + 4]), int(p[k + 5]))
            missiles.append({"i": i, "state": state, "kind": kind,
                             "ring": ring, "phi": phi, "r": r})
            k += 6
        out[n] = (da, missiles)
    return out


def parse_rocket_pairs(fname):
    """The RPAIR records: two snapshots of the same front missile, with the
    LSPC animation counter read at each snapshot."""
    pairs = []
    for line in open(fname):
        if not line.startswith("RPAIR "):
            continue
        p = line.split()
        pairs.append({"seq1": int(p[1]), "seq2": int(p[2]),
                      "f1": int(p[3]), "f2": int(p[4]),
                      "c1": int(p[5], 16), "c2": int(p[6], 16),
                      "obj": int(p[7])})
    return pairs


def parse_ship(fname):
    """{frame: (scb3_0, scb2_0, scb2_1, scb4_0, t00, t01, t10, t11)}."""
    out = {}
    for line in open(fname):
        if line.startswith("H "):
            p = line.split()
            out[int(p[1])] = tuple(int(x, 16) for x in p[2:])
    return out

# The Neo Geo's vertical zoom table (the "000-lo.lo" part of the AES BIOS)
# samples SCB1 rows from the sprite's top. For a column of `rows` picture
# tiles and a vertical zoom byte vz, the picture (tiles 0..rows-1) fills the
# first DRAW_H[rows][vz] screen lines. The table is decoded from that ROM
# (rows 1,2,4; vz 63..255, the game's whole shrink range: f = vz+1 = 64..256
# with the code's vz = f-1). Values are line counts, inclusive.
DRAW_H = {
    1: [(63, 64, 4), (65, 80, 5), (81, 96, 6), (97, 112, 7), (113, 128, 8),
        (129, 144, 9), (145, 160, 10), (161, 176, 11), (177, 192, 12),
        (193, 208, 13), (209, 224, 14), (225, 240, 15), (241, 255, 16)],
    2: [(63, 64, 8), (65, 72, 9), (73, 80, 10), (81, 88, 11), (89, 96, 12),
        (97, 104, 13), (105, 112, 14), (113, 120, 15), (121, 128, 16),
        (129, 136, 17), (137, 144, 18), (145, 152, 19), (153, 160, 20),
        (161, 168, 21), (169, 176, 22), (177, 184, 23), (185, 192, 24),
        (193, 200, 25), (201, 208, 26), (209, 216, 27), (217, 224, 28),
        (225, 232, 29), (233, 240, 30), (241, 248, 31), (249, 255, 32)],
    4: [(63, 64, 16), (65, 68, 17), (69, 72, 18), (73, 76, 19), (77, 80, 20),
        (81, 84, 21), (85, 88, 22), (89, 92, 23), (93, 96, 24), (97, 100, 25),
        (101, 104, 26), (105, 108, 27), (109, 112, 28), (113, 116, 29),
        (117, 120, 30), (121, 124, 31), (125, 128, 32), (129, 132, 33),
        (133, 136, 34), (137, 140, 35), (141, 144, 36), (145, 148, 37),
        (149, 152, 38), (153, 156, 39), (157, 160, 40), (161, 164, 41),
        (165, 168, 42), (169, 172, 43), (173, 176, 44), (177, 180, 45),
        (181, 184, 46), (185, 188, 47), (189, 192, 48), (193, 196, 49),
        (197, 200, 50), (201, 204, 51), (205, 208, 52), (209, 212, 53),
        (213, 216, 54), (217, 220, 55), (221, 224, 56), (225, 228, 57),
        (229, 232, 58), (233, 236, 59), (237, 240, 60), (241, 244, 61),
        (245, 248, 62), (249, 252, 63), (253, 255, 64)],
}


def draw_h(rows, vz):
    for a, b, h in DRAW_H[rows]:
        if a <= vz <= b:
            return h
    raise AssertionError(f"vz {vz} outside the game's shrink range 63..255")


def blank(t):
    return t < BLANK_LIMIT


def picture_rows(tiles):
    rows = 0
    while rows < len(tiles) and not blank(tiles[rows]):
        rows += 1
    return rows


def parse(fname):
    """list of (frame, [slot dicts]); slot dict: slot, x, y (screen), cols,
    rows (picture rows), rows_h, hz, vz, palette, tiles[32]. The radar
    headings are flagged with `radar` (the picture check skips them)."""
    frames = []
    for line in open(fname):
        if line.startswith("F "):
            frames.append([int(line.split()[1]), []])
        elif line.startswith("S "):
            p = line.split()
            slot, scb2, scb3, scb4 = (int(p[1]), int(p[2], 16), int(p[3], 16),
                                      int(p[4], 16))
            tiles = [int(t, 16) for t in p[5:37]]
            attrs = [int(t, 16) for t in p[37:69]]
            frames[-1][1].append(dict(
                slot=slot, scb2=scb2, scb3=scb3, scb4=scb4,
                x=scb4 >> 7, y=496 - (scb3 >> 7),
                rows_h=scb3 & 0x3f, hz=(scb2 >> 8) & 0x0f, vz=scb2 & 0xff,
                palette=attrs[0] >> 8, attr=attrs[0], hflip=attrs[0] & 1,
                tiles=tiles, attrs=attrs,
                rows=picture_rows(tiles), radar=slot >= RADAR_START))
    # columns: the number of shown slots in the same 4-slot group (behind,
    # front and explosion ranges are separate groups; each radar slot is its
    # own 1-column group)
    for _f, slots in frames:
        by_group = {}
        # Dome-scenery Task 2: each missile/explosion group is as wide as
        # its picture, MIS_COLS_MAX (3 columns now; it was 4 at the full
        # dome), and the explosion is NEXPL x EXPL_COLS = 6 slots wide
        for s in slots:
            if s["slot"] <= MIS_BEHIND_END:
                g = ("B", (s["slot"] - _SLOTS["MIS_BEHIND_SPRITE"]) // 3)
            elif s["slot"] <= FRONT_END:
                g = ("F", (s["slot"] - _SLOTS["MIS_FRONT_SPRITE"]) // 3)
            elif s["slot"] <= EXPL_END:
                g = ("E", (s["slot"] - _SLOTS["EXPL_SPRITE"]) // 3)
            else:
                g = ("R", s["slot"])          # each radar slot its own column
            by_group.setdefault(g, []).append(s)
        for group in by_group.values():
            n = len(group)
            for s in group:
                s["cols"] = n
    return frames


def check_rows(frames, failures):
    ns = 0
    for _frame, slots in frames:
        for s in slots:
            ns += 1
            t = s["tiles"]
            rows = s["rows"]
            if rows < 1:
                failures.append(f"slot {s['slot']}: the planted garbage was never"
                                f" overwritten (SCB1 row 0 is tile {t[0]:#x})")
                continue
            if rows not in PICTURE_ROWS:
                # e.g. the old code: rows 0..cols-1 hold the picture, then the
                # planted garbage that was never blanked, so the leading
                # non-blank run runs to the end of the column
                failures.append(
                    f"slot {s['slot']}: {rows} non-blank SCB1 rows (expected"
                    f" 1..4); rows below the picture were never blanked")
                continue
            for r in range(rows, 32):
                if not blank(t[r]):
                    failures.append(
                        f"slot {s['slot']}: SCB1 row {r} below the {rows}-row"
                        f" picture is tile {t[r]:#x}, not blank "
                        f"(vz {s['vz']}, height {s['rows_h']}: the hardware can"
                        " sample this row and would draw it)")
                    break
    return ns


def _red(px):
    r, g, b = px[:3]
    return r > 180 and r - g > 100 and abs(g - b) < 40


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import neo_palette as _np  # noqa: E402
import render_radar as _rr  # noqa: E402  (the hardware's exact zoom tables)


def _rgb_set(pal):
    return {tuple(_np.neo_rgb(_np.rm.neo(c))) for c in pal[1:]}


# the rocket palette (build/missile_map.h's mis_pal), exactly as the hardware
# shows it; R2 moved the missile from the dart palette to this one.
_MIS_PAL_RGB = [tuple(_np.neo_rgb(w)) for w in _MIS_PAL_WORDS]


_BOLT_RGB = None


def bolt_rgb():
    """The bolt's on-screen colours (all its tiles' indices through PAL_SHIP),
    less any colour another sprite/scenery palette also shows: the ship
    itself shares PAL_SHIP, so its own pixels are excluded by the ship mask
    below, not by removing its colours here."""
    global _BOLT_RGB
    if _BOLT_RGB is None:
        idx = set()
        for k in range(_NBOLT):
            idx |= set(_np.decode_tile(_BOLT_TILE + k).flatten().tolist())
        idx.discard(0)
        pal = _np.ship_palette_rgb()
        rgb = {tuple(pal[i]) for i in idx}
        others = set()
        others |= set(_MIS_PAL_RGB[1:]) | _rgb_set(_np.rm.EXPLOSION)
        others |= set(_np.dome_palette_rgb()) | set(_np.broken_palette_rgb())
        for p in _np.ground_palettes_rgb():
            others |= set(p)
        others |= _np.mountain_rgb_set() | _np.band_rgb_set()
        others |= _np.console_rgb_set() | _np.prop_rgb_set()
        others |= _np.radar_rgb_set() | _np.radar_stick_rgb_set()
        _BOLT_RGB = rgb - others
    return _BOLT_RGB


def _at(im, x, y):
    w, h = im.size
    return tuple(im.getpixel((int(x * w / _SCREEN_W),
                              int(y * h / _SCREEN_H)))[:3])


def bolt_pixels(tile, hz, vz, x, y):
    """(screen x, y, palette index) of the bolt's opaque pixels through the
    hardware's shrink, exactly as the props checker decodes it: the
    vertical zoom table picks (SCB1 row, art row) per screen line, and the
    horizontal one samples (hz+1) art columns."""
    pic = _np.decode_tile(tile)
    out = []
    for line in range(16):                    # one picture row
        b = _rr._ZOOM_Y[(vz << 8) | (line & 0xff)]
        row, artrow = b >> 4, b & 0x0f
        if row >= 1:
            continue
        sy = y + line
        for j, artcol in enumerate(_rr.ZOOM_X_COLS[hz]):
            idx = int(pic[artrow][artcol])
            if idx:
                out.append((x + j, sy, idx))
    return out


def ship_mask(h):
    """(320, 224) bool of the ship's non-transparent pixels at the snapshot
    frame, from the probe's H record (the 2 x 2 sticky picture) and the same
    exact zoom decode. The bolt shares PAL_SHIP with the ship, so these
    pixels are excluded from the bolt's stray test."""
    mask = np.zeros((_SCREEN_H, _SCREEN_W), bool)
    if h is None:
        return mask
    scb3_0, scb2_0, scb2_1, scb4_0, t00, t01, t10, t11 = h
    height = scb3_0 & 0x3f
    if height == 0:
        return mask
    y = 496 - (scb3_0 >> 7)
    x0 = scb4_0 >> 7
    cols = ((x0, [t00, t01], (scb2_0 >> 8) & 0x0f, scb2_0 & 0xff),
            (x0 + 16, [t10, t11], (scb2_1 >> 8) & 0x0f, scb2_1 & 0xff))
    for x, tiles, hz, vz in cols:
        for line in range(height * 16):
            b = _rr._ZOOM_Y[(vz << 8) | (line & 0xff)]
            row, artrow = b >> 4, b & 0x0f
            if row >= len(tiles):
                continue
            sy = y + line
            if sy < 0 or sy >= _SCREEN_H:
                continue
            pic = _np.decode_tile(tiles[row])
            for j, artcol in enumerate(_rr.ZOOM_X_COLS[hz]):
                if pic[artrow][artcol]:
                    sx = x + j
                    if 0 <= sx < _SCREEN_W:
                        mask[sy, sx] = True
    return mask


def bullet_bases(i):
    """The behind/front base slots of bullet i (obj[MIS 3 + i])."""
    return (_SLOTS["MIS_BEHIND_SPRITE"] + (_BUL0 + i) * _MIS_COLS_MAX,
            _SLOTS["MIS_FRONT_SPRITE"] + (_BUL0 + i) * _MIS_COLS_MAX)


def check_bullet_words(probe, frames, failures):
    """Task H2 proof 1: every displayed bullet's SCB1 tile/attributes and
    SCB2/SCB3/SCB4 are the bolt model's; a bullet with r below the muzzle is
    never shown; two bullets in flight shimmer out of step; a bullet seen
    across a dome turn changes picture with the line. The probe's B record
    at frame N holds the words committed from frame N-1's prepare, so the
    model uses N-1's state/fc."""
    B = parse_bullets(probe)
    by_frame = {fr: slots for fr, slots in frames}
    compared = tile_compared = attr_rows = 0
    word_bad = tile_bad = attr_bad = hidden_bad = churn_bad = 0
    shimmer_seen = {0: set(), 1: set()}
    two_frames = []
    turn_pairs = []
    below_bullets = turn_frames = 0
    drawn_prev = {0: None, 1: None}
    for n in sorted(B):
        if n - 1 not in B:
            continue
        prev_fc, prev_da, prev = B[n - 1]
        _fc, _da, cur = B[n]
        sampled = n in by_frame
        by_slot = {s["slot"]: s for s in by_frame.get(n, [])}
        drawn = []
        for i in range(_NBUL):
            old, c = prev[i], cur[i]
            below = old["state"] == 1 and old["r"] < _MUZZLE_R + _BOLT_LEN_R
            if below:
                below_bullets += 1
            model = (bullet_model(prev_da, old["ring"], old["phi"],
                                  old["r"], prev_fc, i)
                     if old["state"] == 1 else None)
            behind_base, front_base = bullet_bases(i)
            if model is None:
                shown = [b for b in (behind_base, front_base) if b in by_slot]
                if ((c["b"][1] & 0x3f) != 0 or (c["f"][1] & 0x3f) != 0
                        or shown):
                    hidden_bad += 1
                    if hidden_bad <= 8:
                        failures.append(
                            f"bullet {i} at frame {n}: the model says hidden"
                            f" (r {old['r']}, muzzle threshold"
                            f" {_MUZZLE_R + _BOLT_LEN_R}) but the base slot"
                            f" heights are {c['b'][1] & 0x3f} /"
                            f" {c['f'][1] & 0x3f} and S shows {shown}")
                drawn_prev[i] = None
                continue
            w = c["b"] if model["behind"] else c["f"]
            other = c["f"] if model["behind"] else c["b"]
            compared += 1
            if (w[0] != model["scb2"] or w[1] != model["scb3"]
                    or w[2] != model["scb4"]):
                word_bad += 1
                if word_bad <= 8:
                    failures.append(
                        f"bullet {i} at frame {n}: SCB2/3/4"
                        f" {w[0]:04x}/{w[1]:04x}/{w[2]:04x}, bolt model"
                        f" {model['scb2']:04x}/{model['scb3']:04x}/"
                        f"{model['scb4']:04x}")
            if (other[1] & 0x3f) != 0:
                word_bad += 1
                if word_bad <= 8:
                    failures.append(
                        f"bullet {i} at frame {n}: the unused set's base"
                        f" height is {other[1] & 0x3f}, not 0")
            tile_compared += 1
            if w[3] != model["tile"]:
                tile_bad += 1
                if tile_bad <= 8:
                    failures.append(
                        f"bullet {i} at frame {n}: tile {w[3]:#x}, want bolt"
                        f" {model['tile']:#x} (angle {model['angle']},"
                        f" shimmer {model['shimmer']}, fc {prev_fc})")
            shimmer = w[3] - (_BOLT_TILE + model["angle"] * _BOLT_FRAMES)
            if shimmer not in (0, 1):
                tile_bad += 1
                if tile_bad <= 8:
                    failures.append(
                        f"bullet {i} at frame {n}: tile {w[3]:#x} is not"
                        f" angle {model['angle']}'s two bolt frames")
            else:
                shimmer_seen[i].add(shimmer)
            # the sampled frame's S record: words, attributes, picture tile
            if sampled:
                used_base = behind_base if model["behind"] else front_base
                s = by_slot.get(used_base)
                if s is None:
                    word_bad += 1
                    if word_bad <= 8:
                        failures.append(
                            f"bullet {i} at frame {n}: its used base slot"
                            f" {used_base} is not shown")
                else:
                    if (s["scb2"], s["scb3"], s["scb4"]) != (
                            model["scb2"], model["scb3"], model["scb4"]):
                        word_bad += 1
                        if word_bad <= 8:
                            failures.append(
                                f"bullet {i} at frame {n}: slot {used_base}"
                                f" SCB2/3/4 {s['scb2']:04x}/{s['scb3']:04x}/"
                                f"{s['scb4']:04x}, bolt model"
                                f" {model['scb2']:04x}/{model['scb3']:04x}/"
                                f"{model['scb4']:04x}")
                    if s["tiles"][0] != model["tile"]:
                        tile_bad += 1
                        if tile_bad <= 8:
                            failures.append(
                                f"bullet {i} at frame {n}: slot {used_base}"
                                f" SCB1 row 0 is {s['tiles'][0]:#x}, want"
                                f" bolt {model['tile']:#x}")
                    for r in range(32):
                        attr_rows += 1
                        if s["attrs"][r] != _BOLT_ATTR:
                            attr_bad += 1
                            if attr_bad <= 8:
                                failures.append(
                                    f"bullet {i} at frame {n}: slot"
                                    f" {used_base} row {r} attributes"
                                    f" {s['attrs'][r]:#x}, want PAL_SHIP no"
                                    f" flips {_BOLT_ATTR:#x}")
                for base in (behind_base, front_base):
                    for col in range(_MIS_COLS_MAX):
                        if base + col == used_base:
                            continue
                        if base + col in by_slot:
                            hidden_bad += 1
                            if hidden_bad <= 8:
                                failures.append(
                                    f"bullet {i} at frame {n}: unused slot"
                                    f" {base + col} is shown")
            if drawn_prev[i] is not None:
                pn, pda, pangle, ptile = drawn_prev[i]
                if n == pn + 1 and prev_da != pda:
                    turn_frames += 1
                    if pangle != model["angle"]:
                        turn_pairs.append((i, pn, n, pda, prev_da, pangle,
                                           model["angle"], ptile, w[3]))
            drawn_prev[i] = (n, prev_da, model["angle"], w[3])
            drawn.append((i, w[3], shimmer, model["angle"], prev_da))
        if len(drawn) == 2:
            two_frames.append((n, drawn[0], drawn[1]))
    # the two-bullet shimmer proof (Review Focus 4)
    if not two_frames:
        churn_bad += 1
        failures.append("no frame showed two bolts in flight: Review Focus 4"
                        " is unproved")
    same = [(n, a, b) for n, a, b in two_frames if a[2] == b[2]]
    if same:
        churn_bad += 1
        failures.append(
            f"{len(same)} frame(s) showed two bolts at the same shimmer"
            f" (first frame {same[0][0]}: shimmer {same[0][1][2]} and"
            f" {same[0][2][2]})")
    for n, a, b in two_frames[:1]:
        print(f"two bolts at frame {n}: tiles {a[1]:#x} and {b[1]:#x}"
              f" (shimmer {a[2]} and {b[2]})")
    for i in range(_NBUL):
        if shimmer_seen[i] != {0, 1}:
            churn_bad += 1
            failures.append(
                f"bullet slot {i}: shimmer frames seen"
                f" {sorted(shimmer_seen[i])}, want both 0 and 1")
    # a bullet below the muzzle must have been seen hidden (proof 3's
    # mutation: with the threshold removed these frames show it)
    if not below_bullets:
        hidden_bad += 1
        failures.append("no bullet was ever below the muzzle: the hidden"
                        " threshold was not exercised")
    if not turn_frames:
        churn_bad += 1
        failures.append("no bullet was seen across a dome turn: Review"
                        " Focus 1 is unproved")
    elif not turn_pairs:
        churn_bad += 1
        failures.append(f"{turn_frames} bullet frame(s) crossed a dome turn"
                        " but its picture angle never changed")
    for i, pn, n, pda, da, pangle, angle, ptile, tile in turn_pairs[:1]:
        print(f"bullet {i} across a dome turn frames {pn}->{n}: dome"
              f" {pda}->{da}, picture angle {pangle}->{angle}, tile"
              f" {ptile:#x}->{tile:#x}")
    return (compared, tile_compared, attr_rows, len(two_frames), word_bad,
            tile_bad, attr_bad, hidden_bad, churn_bad, below_bullets)


def check_missile_words(probe, frames, failures):
    """R2 proof 2: every displayed missile's SCB1 column words and
    SCB2/SCB3/SCB4 equal the old dart placement model; the picture rows are
    the rocket's tile base + cell*4, and every row (blank rows included)
    carries palette 3 with the 4-frame animation bit (0x0004) and the
    picture's h-flip. The probe's S record at frame N holds the words
    committed from N-1's prepare, so the model uses M[N-1]'s state."""
    M = parse_missiles(probe)
    by_frame = {fr: slots for fr, slots in frames}
    compared = tile_rows = attr_rows = 0
    word_bad = tile_bad = attr_bad = hidden_bad = 0
    for n in sorted(M):
        if n - 1 not in M or n not in by_frame:
            continue
        prev_da, prev = M[n - 1]
        by_slot = {s["slot"]: s for s in by_frame[n]}
        for i in range(_NMIS):
            old = prev[i]
            model = (old_missile_base(prev_da, old["ring"], old["phi"],
                                      old["r"])
                     if old["state"] == 1 and old["kind"] == 0 else None)
            behind_base = _SLOTS["MIS_BEHIND_SPRITE"] + i * _MIS_COLS_MAX
            front_base = _SLOTS["MIS_FRONT_SPRITE"] + i * _MIS_COLS_MAX
            if model is None:
                for base in (behind_base, front_base):
                    for c in range(_MIS_COLS_MAX):
                        if base + c in by_slot:
                            hidden_bad += 1
                            if hidden_bad <= 8:
                                failures.append(
                                    f"missile {i} at frame {n}: the model says"
                                    f" hidden but slot {base + c} is shown")
                continue
            base = front_base if not model["behind"] else behind_base
            other = behind_base if not model["behind"] else front_base
            for c in range(_MIS_COLS_MAX):
                if other + c in by_slot:
                    hidden_bad += 1
                    if hidden_bad <= 8:
                        failures.append(
                            f"missile {i} at frame {n}: the unused set's slot"
                            f" {other + c} is shown")
            group = []
            for c in range(model["cols"]):
                s = by_slot.get(base + c)
                if s is None:
                    hidden_bad += 1
                    if hidden_bad <= 8:
                        failures.append(
                            f"missile {i} at frame {n}: slot {base + c} of a"
                            f" {model['cols']}-column picture is missing")
                else:
                    group.append(s)
            exp_attr = ((3 << 8) | 0x0004 | model["hflip"])
            for c, s in enumerate(group):
                compared += 1
                exp_scb4 = ((((model["x"] + c * (model["hz"] + 1)) & 0xffff)
                             << 7) & 0xffff)
                if (s["scb2"], s["scb3"], s["scb4"]) != (
                        model["scb2"], model["scb3"], exp_scb4):
                    word_bad += 1
                    if word_bad <= 8:
                        failures.append(
                            f"missile {i} col {c} at frame {n}: SCB2/3/4"
                            f" {s['scb2']:04x}/{s['scb3']:04x}/"
                            f"{s['scb4']:04x}, old model"
                            f" {model['scb2']:04x}/{model['scb3']:04x}/"
                            f"{exp_scb4:04x}")
                sc = (model["cols"] - 1 - c) if model["hflip"] else c
                for r in range(32):
                    if r < model["cols"]:
                        want_tile = (model["tile0"]
                                     + (r * model["cols"] + sc) * _MIS_FRAMES)
                    else:
                        want_tile = 0
                    tile_rows += 1
                    if s["tiles"][r] != want_tile:
                        tile_bad += 1
                        if tile_bad <= 8:
                            failures.append(
                                f"missile {i} col {c} row {r} at frame {n}:"
                                f" tile {s['tiles'][r]:#x}, want"
                                f" {want_tile:#x}")
                    attr_rows += 1
                    if s["attrs"][r] != exp_attr:
                        attr_bad += 1
                        if attr_bad <= 8:
                            failures.append(
                                f"missile {i} col {c} row {r} at frame {n}:"
                                f" attr {s['attrs'][r]:#x}, want"
                                f" {exp_attr:#x} (palette 3, anim bit 2,"
                                f" hflip {model['hflip']})")
    return (compared, tile_rows, attr_rows, word_bad, tile_bad, attr_bad,
            hidden_bad)


def rocket_group(slots, obj):
    """The front missile object's shown slots, in column order."""
    base = _SLOTS["MIS_FRONT_SPRITE"] + obj * _MIS_COLS_MAX
    return sorted((s for s in slots if base <= s["slot"] < base + _MIS_COLS_MAX),
                  key=lambda s: s["slot"])


def rocket_pixels(group, counter):
    """(screen x, y, palette index, picture row, picture col) of the rocket
    picture's opaque pixels through the hardware shrink. The SCB1 words hold
    frame 0; the LSPC replaces each tile's low 2 bits with its counter."""
    frame = counter & 3
    cols = len(group)
    out = []
    for c, s in enumerate(group):
        sc = (cols - 1 - c) if s["hflip"] else c
        for line in range(s["rows_h"] * 16):
            b = _rr._ZOOM_Y[(s["vz"] << 8) | (line & 0xff)]
            row, artrow = b >> 4, b & 0x0f
            if row >= s["rows"]:
                continue
            tile = (s["tiles"][row] & ~3) | frame
            pic = _np.decode_tile(tile)
            sy = s["y"] + line
            if sy < 0 or sy >= _SCREEN_H:
                continue
            for j, artcol in enumerate(_rr.ZOOM_X_COLS[s["hz"]]):
                if s["hflip"]:              # SCB1 bit 0 mirrors each tile
                    artcol = 15 - artcol
                idx = int(pic[artrow][artcol])
                if idx:
                    sx = s["x"] + j
                    if 0 <= sx < _SCREEN_W:
                        out.append((sx, sy, idx, row * 16 + artrow,
                                    sc * 16 + artcol))
    return out


def check_rocket_snapshots(snap_png, probe, frames, failures):
    """R2 proofs 3 and 4: a snapshot's missile pixels equal the rocket
    picture at the LSPC counter the probe read, and two snapshots 4+ frames
    apart show different flame pixels on the same missile."""
    snapdir = os.path.join(os.path.dirname(os.path.abspath(snap_png)), "snap")
    files = sorted(glob.glob(os.path.join(snapdir, "**", "*.png"),
                             recursive=True))
    by_frame = {fr: slots for fr, slots in frames}
    pairs = parse_rocket_pairs(probe)
    if not pairs:
        failures.append("the probe took no pair of rocket snapshots")
        return 0, 0, 0
    clean = []
    best = None
    for pair in pairs:
        if pair["f2"] - pair["f1"] < 4:
            failures.append(
                f"rocket snapshots {pair['seq1']}/{pair['seq2']} are only"
                f" {pair['f2'] - pair['f1']} frames apart")
            continue
        if pair["seq1"] >= len(files) or pair["seq2"] >= len(files):
            failures.append(
                f"rocket snapshots {pair['seq1']}/{pair['seq2']}: only"
                f" {len(files)} PNGs in {snapdir}")
            continue
        slots1 = by_frame.get(pair["f1"])
        slots2 = by_frame.get(pair["f2"])
        if slots1 is None or slots2 is None:
            failures.append(
                f"rocket snapshots {pair['seq1']}/{pair['seq2']}: no VRAM"
                f" block at frames {pair['f1']}/{pair['f2']}")
            continue
        g1 = rocket_group(slots1, pair["obj"])
        g2 = rocket_group(slots2, pair["obj"])
        if not g1 or not g2:
            failures.append(
                f"rocket snapshots {pair['seq1']}/{pair['seq2']}: missile"
                f" {pair['obj']} is not in the front slots at both frames")
            continue
        im1 = Image.open(files[pair["seq1"]]).convert("RGB")
        im2 = Image.open(files[pair["seq2"]]).convert("RGB")
        compared = mismatches = 0
        first = None
        for im, g, c in ((im1, g1, pair["c1"]), (im2, g2, pair["c2"])):
            for x, y, idx, _r, _cc in rocket_pixels(g, c):
                want = _MIS_PAL_RGB[idx]
                got = _at(im, x, y)
                compared += 1
                if got != want:
                    mismatches += 1
                    if first is None:
                        first = (x, y, got, want, c & 3)
        if compared < 5:                          # an off-screen snapshot:
            continue                              # not a proof, not a failure
        info = {"pair": pair, "compared": compared, "mismatches": mismatches,
                "g1": g1, "g2": g2, "im1": im1, "im2": im2,
                "flame1": flame_local(g1, pair["c1"]),
                "flame2": flame_local(g2, pair["c2"])}
        if mismatches == 0:
            clean.append(info)
        if best is None or mismatches < best["mismatches"]:
            best = info
        if first is not None and mismatches and len(pairs) <= 1:
            failures.append(
                f"rocket snapshot pair {pair['seq1']}/{pair['seq2']}:"
                f" {mismatches} of {compared} missile pixels differ from the"
                f" rocket picture at counter {pair['c1'] & 3}/{pair['c2'] & 3}"
                f" (first {first})")
    if not clean:
        if best is not None:
            failures.append(
                f"no rocket snapshot pair matches the picture at its LSPC"
                f" counter (best: {best['mismatches']} of"
                f" {best['compared']} pixels differ, counters"
                f" {best['pair']['c1'] & 3}/{best['pair']['c2'] & 3})")
        else:
            failures.append("no rocket snapshot showed any missile pixels")
        return 0, 0, 0
    use = clean[0]
    flick = None
    for info in clean:
        # only compare pairs at the same picture size: a missile that shrinks
        # a level between the snapshots has a different art, so its flame
        # pixels would differ even if the animation never advanced.
        if len(info["g1"]) != len(info["g2"]):
            continue
        if info["flame1"] and info["flame2"] and info["flame1"] != info["flame2"]:
            flick = info
            break
    if flick is None:
        failures.append(
            f"the {len(clean)} clean rocket snapshot pair(s) at one picture"
            f" size show the same flame pixels; the flame did not flicker")
        return use["compared"], use["mismatches"], 0
    changed = len(flick["flame1"] ^ flick["flame2"])
    print(f"rocket snapshots frames {flick['pair']['f1']}->{flick['pair']['f2']}:"
          f" {flick['compared']} pixels matched the rocket picture at LSPC"
          f" counters {flick['pair']['c1'] & 3}/{flick['pair']['c2'] & 3};"
          f" {changed} flame pixels differ")
    return use["compared"], use["mismatches"], changed


def flame_local(group, counter):
    """the rocket picture's flame pixels in picture-local coordinates
    (row*16+artrow, col*16+artcol), from the whole art frame the LSPC's
    counter selects. It ignores where the sprite is clipped on screen, so
    two different counters are compared by their flame art, not by how much
    of the missile happened to be visible."""
    frame = counter & 3
    cols = len(group)
    out = set()
    for c, s in enumerate(group):
        sc = (cols - 1 - c) if s["hflip"] else c
        for row in range(s["rows"]):
            pic = _np.decode_tile((s["tiles"][row] & ~3) | frame)
            for artrow in range(16):
                for artcol in range(16):
                    if 11 <= int(pic[artrow][artcol]) <= 15:
                        out.add((row * 16 + artrow, sc * 16 + artcol))
    return out


def check_picture(snap_png, slots, ship_h, models, failures):
    im = Image.open(snap_png).convert("RGB")
    w, h = im.size
    sx, sy = w / _SCREEN_W, h / _SCREEN_H    # the snapshot may be scaled
    pix = im.load()

    red_boxes, bullet_slots = [], []
    for s in slots:
        if s["radar"]:                          # the radar headings: their
            continue                            # palette is neither red nor
        if s["rows"] not in DRAW_H:             # a bolt's; no box applies
            continue
        x0, x1 = s["x"], s["x"] + s["cols"] * (s["hz"] + 1) - 1
        y0, y1 = s["y"], s["y"] + draw_h(s["rows"], s["vz"]) - 1
        if _BOLT_TILE <= s["tiles"][0] < _BOLT_TILE + _NBOLT:
            bullet_slots.append(s)
        else:
            red_boxes.append((x0, y0, x1, y1))

    def outside(x, y, boxes):
        return not any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in boxes)

    # Task H1: the hovercraft's cherry paint and tail lights are bright red
    # too (the spider's furnace orange was not), and so is the laser bolt.
    # The missile-red test therefore leaves out the ship's own
    # non-transparent pixels and the bolts' drawn pixels, both of which are
    # separately checked below. The claim still holds for the missiles: no
    # red outside their boxes that is not the ship or a bolt.
    mask = ship_mask(ship_h)
    bolt_xy = set()
    for s in bullet_slots:
        for x, y, _idx in bolt_pixels(s["tiles"][0], s["hz"], s["vz"],
                                      s["x"], s["y"]):
            if 0 <= x < _SCREEN_W and 0 <= y < _SCREEN_H:
                bolt_xy.add((x, y))
    stray_red = 0
    for py in range(h):
        for px in range(w):
            x, y = int(px * _SCREEN_W / w), int(py * _SCREEN_H / h)
            if _red(pix[px, py]) and outside(px / sx, py / sy, red_boxes) \
               and not mask[y, x] and (x, y) not in bolt_xy:
                stray_red += 1
    if stray_red:
        failures.append(f"snapshot: {stray_red} missile (red) pixels outside"
                        " every missile box, the bolts and the ship")

    # Task H2 proof 2: the snapshot's bolt pixels are exactly the bolt
    # tile's colours through the hardware's shrink, and the head pixel is on
    # the bullet's point (the model's SCB4/SCB3 place it there).
    expected = {}
    compared = mismatches = head_checked = 0
    first = None
    for s in bullet_slots:
        model = models.get(s["slot"])
        if model is None:
            failures.append(
                f"snapshot: slot {s['slot']} shows bolt tile"
                f" {s['tiles'][0]:#x} but the previous frame's bullet model"
                " has no such slot")
            continue
        head_x = s["x"] + ((model["hx"] * model["f"]) >> 8)
        head_y = s["y"] + ((model["hy"] * model["f"]) >> 8)
        if (head_x, head_y) != (model["point_x"], model["point_y"]):
            failures.append(
                f"snapshot: slot {s['slot']}'s head pixel ({head_x},{head_y})"
                f" is not on the bullet's point"
                f" ({model['point_x']},{model['point_y']})")
            continue
        head_checked += 1
    for s in bullet_slots:
        for x, y, idx in bolt_pixels(s["tiles"][0], s["hz"], s["vz"],
                                     s["x"], s["y"]):
            if not (0 <= x < _SCREEN_W and 0 <= y < _SCREEN_H):
                continue
            expected[(x, y)] = idx
            want = tuple(_np.ship_palette_rgb()[idx])
            got = _at(im, x, y)
            compared += 1
            if got != want:
                mismatches += 1
                if first is None:
                    first = (x, y, got, want)
    if compared < 5:
        failures.append(f"snapshot: only {compared} bolt pixels in the"
                        " bullet boxes; the snapshot frame did not show a"
                        " bolt")
    if mismatches:
        failures.append(f"snapshot: {mismatches} of {compared} bolt"
                        f" pixels differ from the tile's colours (first"
                        f" {first})")

    stray_ball = 0
    for py in range(h):
        for px in range(w):
            if tuple(pix[px, py]) not in bolt_rgb():
                continue
            x, y = int(px * _SCREEN_W / w), int(py * _SCREEN_H / h)
            if (x, y) not in expected and not mask[y, x]:
                stray_ball += 1
    if stray_ball:
        failures.append(f"snapshot: {stray_ball} bolt-coloured pixels"
                        " outside every bolt's pixels and the ship")
    return compared, mismatches, stray_ball, head_checked


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    frames = parse(probe)
    ships = parse_ship(probe)
    failures = []
    ns = check_rows(frames, failures)
    (compared, tile_compared, attr_rows, two_n, word_bad, tile_bad,
     attr_bad, hidden_bad, churn_bad,
     below_bullets) = check_bullet_words(probe, frames, failures)
    print(f"bullets: {compared} displayed slots held to the bolt model"
          f" ({word_bad} word mismatches), {tile_compared} tiles"
          f" ({tile_bad} mismatches), {attr_rows} attributes"
          f" ({attr_bad} mismatches), {hidden_bad} hidden failures,"
          f" {two_n} frames with two bolts, {below_bullets} bullet-frames"
          f" below the muzzle ({churn_bad} shimmer/turn failures)")

    (mcols, mtiles, mattrs, mword, mtile, mattr,
     mhidden) = check_missile_words(probe, frames, failures)
    print(f"missiles: {mcols} displayed columns held to the old obj_draw"
          f" model ({mword} word mismatches), {mtiles} SCB1 tiles"
          f" ({mtile} mismatches), {mattrs} attributes ({mattr} mismatches),"
          f" {mhidden} hidden-slot failures")

    rpix, rmis, rflame = check_rocket_snapshots(snap_png, probe, frames,
                                                failures)
    print(f"rocket snapshots: {rpix} missile pixels compared ({rmis}"
          f" mismatches), {rflame} flame pixels changed")

    snap_n = None
    for line in open(probe):
        if line.startswith("SNAP "):
            snap_n = int(line.split()[1])
    if snap_n is None:
        failures.append("probe never snapshotted a frame with a bullet")
    else:
        slots = next((sl for fr, sl in frames if fr == snap_n), None)
        B = parse_bullets(probe)
        models = {}
        if snap_n - 1 not in B:
            failures.append(f"snapshot frame {snap_n} has no previous bullet"
                            " frame to model")
        else:
            fc, prev_da, prev = B[snap_n - 1]
            for i in range(_NBUL):
                old = prev[i]
                model = (bullet_model(prev_da, old["ring"], old["phi"],
                                      old["r"], fc, i)
                         if old["state"] == 1 else None)
                if model is not None:
                    behind_base, front_base = bullet_bases(i)
                    models[behind_base if model["behind"] else front_base] = model
        if slots is None:
            failures.append(f"snapshot frame {snap_n} has no VRAM block")
        else:
            c, m, stray, heads = check_picture(
                snap_png, slots, ships.get(snap_n), models, failures)
            print(f"snapshot frame {snap_n}: {c} bolt pixels compared"
                  f" ({m} mismatches), {stray} stray bolt pixels, {heads}"
                  f" heads on the bullet's point")
    if ns == 0:
        failures.append("no shown missile/bullet/explosion slot was ever sampled")

    if failures:
        print("FAIL leftovers:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS leftovers: {ns} shown slots checked, snapshot clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
