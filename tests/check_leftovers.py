#!/usr/bin/env python3
"""Assertions for the M3 "no leftovers below a shrunk sprite" fix.

  check_leftovers.py SNAP PROBE
    SNAP   a MAME snapshot PNG taken by scripts/leftover_probe.lua on a
           frame that shows a shrunk bullet
    PROBE  the probe's dump (scripts/leftover_probe.lua OUT): per sample
           frame F, one S line per shown slot with SCB2/SCB3/SCB4, the
           palette attribute of SCB1 row 0, and SCB1 tile numbers 0..31.

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
     tiles). A bullet must actually be visible inside its box. The radar
     headings are excluded from the pixel box: their colours (the radar's
     palette) are neither red nor the bullet's, so they cannot trip the stray-pixel
     test, and their shrunk 1-line box is unlike the missiles'.
"""
import json
import os
import sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
# the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.json
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))
MIS_BEHIND_END = _SLOTS["MIS_BEHIND_SPRITE"] + _SLOTS["MIS_BEHIND_COUNT"] - 1
FRONT_END = _SLOTS["MIS_FRONT_SPRITE"] + _SLOTS["MIS_FRONT_COUNT"] - 1
EXPL_END = _SLOTS["EXPL_SPRITE"] + _SLOTS["EXPL_COUNT"] - 1
RADAR_START = _SLOTS["RADAR_SPRITE"]

# A blank tile is any of the CROM zero-padding tiles 0..255 (BIOS-reserved,
# all transparent); every game tile starts at 4672 (build/missile_map.h).
BLANK_LIMIT = 256
PICTURE_ROWS = (1, 2, 4)

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
            slot, scb2, scb3, scb4, attr = int(p[1]), int(p[2], 16), int(p[3], 16), int(p[4], 16), int(p[5], 16)
            tiles = [int(t, 16) for t in p[6:]]
            frames[-1][1].append(dict(
                slot=slot, x=scb4 >> 7, y=496 - (scb3 >> 7),
                rows_h=scb3 & 0x3f, hz=(scb2 >> 8) & 0x0f, vz=scb2 & 0xff,
                palette=attr >> 8, tiles=tiles, rows=picture_rows(tiles),
                radar=slot >= RADAR_START))
    # columns: the number of shown slots in the same 4-slot group (behind,
    # front and explosion ranges are separate groups; each radar slot is its
    # own 1-column group)
    for _f, slots in frames:
        by_group = {}
        for s in slots:
            if s["slot"] <= MIS_BEHIND_END:
                g = ("B", (s["slot"] - _SLOTS["MIS_BEHIND_SPRITE"]) // 4)
            elif s["slot"] <= FRONT_END:
                g = ("F", (s["slot"] - _SLOTS["MIS_FRONT_SPRITE"]) // 4)
            elif s["slot"] <= EXPL_END:
                g = ("E", (s["slot"] - _SLOTS["EXPL_SPRITE"]) // 4)
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


# the bullet's on-screen colours (M8 art pass: a pale tracer, no longer
# green): exactly the RGBs MAME shows for its palette entries
# (neo_palette.neo_rgb of render_missiles' words), less any colour another
# sprite palette also shows (the explosion's pale end, the missile's core,
# the ship's highlight)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import neo_palette as _np  # noqa: E402


def _rgb_set(pal):
    return {tuple(_np.neo_rgb(_np.rm.neo(c))) for c in pal[1:]}


_BULLET_RGB = (_rgb_set(_np.rm.BULLET)
               - _rgb_set(_np.rm.EXPLOSION) - _rgb_set(_np.rm.MISSILE)
               - {tuple(int(v) for v in c) for c in _np.ship_palette_rgb()})


def _green(px):
    """a bullet pixel (the name dates from the green bullets)"""
    return tuple(px[:3]) in _BULLET_RGB


def check_picture(snap_png, slots, failures):
    im = Image.open(snap_png).convert("RGB")
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0              # the snapshot may be scaled
    pix = im.load()

    red_boxes, green_boxes = [], []
    for s in slots:
        if s["radar"]:                          # the radar headings: their
            continue                            # palette is neither red nor
        if s["rows"] not in DRAW_H:             # green; no pixel box applies
            continue
        x0, x1 = s["x"], s["x"] + s["cols"] * (s["hz"] + 1) - 1
        y0, y1 = s["y"], s["y"] + draw_h(s["rows"], s["vz"]) - 1
        (green_boxes if s["palette"] == 4 else red_boxes).append((x0, y0, x1, y1))

    def outside(x, y, boxes):
        return not any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in boxes)

    stray_red = stray_green = 0
    for py in range(h):
        for px in range(w):
            c = pix[px, py]
            if _red(c) and outside(px / sx, py / sy, red_boxes):
                stray_red += 1
            elif _green(c) and outside(px / sx, py / sy, green_boxes):
                stray_green += 1
    if stray_green:
        failures.append(f"snapshot: {stray_green} bullet (green) pixels outside"
                        " every bullet box")
    if stray_red:
        failures.append(f"snapshot: {stray_red} missile (red) pixels outside"
                        " every missile box")

    in_box = 0
    for x0, y0, x1, y1 in green_boxes:
        for py in range(max(0, int(y0 * sy)), min(h, int((y1 + 1) * sy))):
            for px in range(max(0, int(x0 * sx)), min(w, int((x1 + 1) * sx))):
                if _green(pix[px, py]):
                    in_box += 1
    if in_box < 5:
        failures.append(f"snapshot: only {in_box} bullet pixels inside the bullet"
                        " boxes; the snapshot frame did not show a bullet")


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    frames = parse(probe)
    failures = []
    ns = check_rows(frames, failures)

    snap_n = None
    for line in open(probe):
        if line.startswith("SNAP "):
            snap_n = int(line.split()[1])
    if snap_n is None:
        failures.append("probe never snapshotted a frame with a bullet")
    else:
        slots = next((sl for fr, sl in frames if fr == snap_n), None)
        if slots is None:
            failures.append(f"snapshot frame {snap_n} has no VRAM block")
        else:
            check_picture(snap_png, slots, failures)
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
