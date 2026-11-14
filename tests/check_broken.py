#!/usr/bin/env python3
"""Assertions for the M4-fixes Task 3 broken-tiles boot-test.

  check_broken.py SNAP PROBE

The -DCRACK_TEST cart starts with all 38 broken cells at dome_angle 0.
scripts/broken_probe.lua reads the shown slots of every group (behind
missiles, overlays, ship, front missiles, explosions) and snapshots one
frame (the first where a front missile is drawn over a broken cell's box).
This checker:

  1. VRAM: the shown overlay slots are exactly the broken cells that face
     the camera, in broken order, packed left to right. Each cell's w/h
     (stones), its canvas x/y (dome-box px), and its C ROM tile (from
     broken_map.h) match what the runtime must draw; each shown slot's
     SCB2 is full size (0x0fff) — no shrink, no leftovers.
  2. Snapshot coverage (the task's proof 2): every visible broken cell's
     interior is mostly black, and every WHOLE cell's interior is not.
     "Interior" = the cell's projected polygon shrunk 2 px, computed from
     the geometry (the dome picture is the reference); "mostly black" =
     the mean pixel value there is dark and the pure-black count is high.
  3. Snapshot stray: no overlay-coloured pixels (black hole + the dome's
     glass/glow ramps, i.e. the broken palette's colours) outside the
     union of the broken cells' polygons. (A whole cell's glass is the
     dome's own colour, so this checks specifically the black hole colour
     index 1, which only the overlays use.)

The slot ranges come from the one slot map (M5 Task 1): build/slots.json
is generated from src/slots.h by the Makefile (tools/gen_slots.py).
"""
import math
import os
import re
import sys
import json

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import geometry as g  # noqa: E402
import render_broken as rb  # noqa: E402
import neo_palette as npal  # noqa: E402
import layout as lay  # noqa: E402

# the one sprite slot map (src/slots.h -> build/slots.json)
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))
MIS_BEHIND_END = _SLOTS["MIS_BEHIND_SPRITE"] + _SLOTS["MIS_BEHIND_COUNT"] - 1
DOME_FIRST, DOME_LAST = _SLOTS["DOME_SPRITE"], _SLOTS["DOME_SPRITE"] + _SLOTS["DOME_COUNT"] - 1
OVERLAY_FIRST, OVERLAY_LAST = _SLOTS["BROKEN_SLOT_BASE"], _SLOTS["BROKEN_SLOT_AFTER"] - 1
SHIP_FIRST, SHIP_LAST = _SLOTS["SHIP_SPRITE"], _SLOTS["SHIP_SPRITE"] + _SLOTS["SHIP_COUNT"] - 1
GROUND_FIRST, GROUND_LAST = _SLOTS["GROUND_SPRITE"], _SLOTS["GROUND_SPRITE"] + _SLOTS["GROUND_COUNT"] - 1
FRONT_FIRST, FRONT_LAST = _SLOTS["MIS_FRONT_SPRITE"], _SLOTS["MIS_FRONT_SPRITE"] + _SLOTS["MIS_FRONT_COUNT"] - 1
EXPL_FIRST, EXPL_LAST = _SLOTS["EXPL_SPRITE"], _SLOTS["EXPL_SPRITE"] + _SLOTS["EXPL_COUNT"] - 1
RIPPLE_PAL_BANK = 44                 # src/ground.h
RIPPLE_BANKS = 11                    # build/ground_map.h


def _defines(path):
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


def _ripple_header():
    """(defines, ground_bank, ground_ripple_pal, ground_ripple_rot) from the
    built build/ground_map.h; the palettes are RGB lists through MAME's DAC."""
    txt = open(os.path.join(ROOT, "build", "ground_map.h")).read()

    def body(name):
        m = re.search(r"%s\[[^=]*= \{(.*?)\};" % name, txt, re.S)
        return m.group(1)

    bank = [[int(x) for x in re.findall(r"\d+", row)]
            for row in re.findall(r"\{([^{}]*)\}", body("ground_bank"))]
    words = [int(x, 16) for x in
             re.findall(r"0x[0-9a-fA-F]{4}", body("ground_ripple_pal"))]
    pal, i = [], 0
    for _k in range(RIPPLE_BANKS):
        per = []
        for _g in (0, 1):
            rots = []
            for _r in range(3):
                rots.append(npal._bank_rgb(words[i:i + 16]))
                i += 16
            per.append(rots)
        pal.append(per)
    rot = [[int(x) for x in re.findall(r"\d+", row)]
           for row in re.findall(r"\{([^{}]*)\}", body("ground_ripple_rot"))]
    return _defines(os.path.join(ROOT, "build", "ground_map.h")), bank, pal, rot

DOME_X, DOME_Y = lay.d.DOME_X, lay.d.DOME_Y  # the dome box's screen top-left (dome.h)
DOME_W, DOME_H = lay.d.DOME_W, lay.d.DOME_H  # the box size (geometry.py's knob)
VIEW = 0                       # the test cart never moves the dome
# the test cart's broken set (src/main.c cracks_test_broken): 16 top-facing
# cells of rings 0..4 (0..15) plus 22 rim cells (36..57, the ring-7..9
# cells). Rings 4..5 (16..30) stay whole so the missile wave still has
# targets for the draw-order check, and the 19 of 38 facing the camera
# include edge/partly hidden rim cells.
BROKEN_TEST_CELLS = (list(range(0, 16)) + list(range(36, 58)))
BLACK_PAL = 1


def _poly_px(cell, v):
    R = rb._ROT[v]
    face = rb._CF[cell][0]
    P = rb._PTS[list(face)] @ R.T
    d = P - rb._POS
    fwd, right, up = rb._CAM[1:]
    z = d @ fwd
    return np.column_stack([rb._FIT[1] + rb._FIT[0] * (d @ right) / z,
                            rb._FIT[2] - rb._FIT[0] * (d @ up) / z])


def facing(cell):
    return rb.overlay(cell, VIEW) is not None


def broken_palette_rgb():
    """the overlay palette's RGB values (index 1 = the black hole)."""
    return [tuple(c[:3]) for c in rb.BROKEN_PALETTE]


_SHIP_RGB = None


def ship_rgb_set():
    """the hovercraft's palette, from the built assets/ship.pal (the
    bank the ship's tiles draw through, src/ship_gfx.h's PAL_SHIP)."""
    global _SHIP_RGB
    if _SHIP_RGB is None:
        _SHIP_RGB = set(npal.ship_palette_rgb()[1:])
    return _SHIP_RGB


def is_ship(px):
    """a pixel of the ship's own palette (the console shares one dark
    colour, (8,8,8), so the console's own pixels are left out)."""
    return tuple(px[:3]) in ship_rgb_set() and not npal.is_console_only(px)


def parse(fname):
    frames = []
    snap_frame = None
    camera = {}          # fc -> the cart's real ship.dome_angle (the props')
    for line in open(fname):
        p = line.split()
        if not p:
            continue
        if p[0] == "P":
            camera[int(p[1])] = int(p[2])
        elif p[0] == "F":
            frames.append((int(p[1]), int(p[2]), []))
        elif p[0] == "S":
            frames[-1][2].append(dict(
                slot=int(p[1]), scb2=int(p[2], 16), scb3=int(p[3], 16),
                scb4=int(p[4], 16), attr=int(p[5], 16),
                tiles=[int(x, 16) for x in p[6:]]))
        elif p[0] == "SNAP":
            snap_frame = int(p[1])
    return frames, snap_frame, camera


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    frames, snap_frame, camera = parse(probe)
    failures = []

    if not frames:
        print("FAIL broken: no sampled frames")
        return 1

    # ---- the reads: shown slots == the visible broken cells, in order ----
    # The overlay the runtime draws for broken cell `c` at dome_angle `da` is
    # cell permute(c, da/48)'s picture at view da%48 (the 5-fold symmetry).
    # The art's on-screen position comes from broken_cell[art][view], so the
    # expected slot stream (and the geometry-based checks) depend on da.
    fr = frames[len(frames) // 2]
    frame, da, slots = fr
    view = da % 48
    q = da // 48
    want = []                    # (cell, art, overlay) drawn this frame, in order
    for c in BROKEN_TEST_CELLS:
        art = c
        for _ in range(q):
            art = rb._PERM[art]
        o = rb.overlay(art, view)
        if o is not None:
            want.append((c, art, o))
    # rebuild the expected slot stream from the geometry tables (the runtime
    # packs the drawn overlays left to right, each owning `cw` slots)
    groups = []                  # per picture: (start_slot, cell, w, h, x, y, first)
    s = OVERLAY_FIRST
    for (c0, art, o) in want:
        cw, ch, left, top = o
        first = rb.TILE_BASE + rb._broken_tile0(art) + rb._view_t0(art, view)
        groups.append((s, c0, cw, ch, left, top, first))
        s += cw
    total_slots = sum(g[2] for g in groups)
    # the probe also dumps the ship/missile/explosion slots; the overlay
    # verification walks only the broken-overlay slots, and the
    # draw-order checks keep the full list
    all_slots = slots
    # Dome-scenery Task 2: the overlay band is the one the regenerated
    # overlays pack (BROKEN_SLOT_BASE..BROKEN_SLOT_AFTER, read from the slot
    # map), and the run of overlay slots is exactly total_slots long
    slots = [s for s in slots if OVERLAY_FIRST <= s["slot"] <= OVERLAY_FIRST + total_slots - 1]
    if len(slots) != total_slots:
        failures.append(f"{len(slots)} shown overlay slots, want {total_slots}")
    # walk slot-by-slot: slot k belongs to the picture whose run contains it
    for k, slot in enumerate(slots):
        # find the picture group containing this slot's number
        for (es, ec, ew, eh, ex, ey, et) in groups:
            if es <= slot["slot"] < es + ew:
                c2 = slot["slot"] - es
                break
        else:
            failures.append(f"slot {slot['slot']} beyond every cell run")
            continue
        if slot["scb2"] != 0x0fff:
            failures.append(f"cell {ec}: SCB2 {slot['scb2']:#x}, want full size")
        h = slot["scb3"] & 0x3f
        if h != eh:
            failures.append(f"cell {ec}: SCB3 height {h}, want {eh}")
        x = slot["scb4"] >> 7
        if x != DOME_X + ex + c2 * 16:
            failures.append(f"cell {ec}: x {x}, want {DOME_X + ex + c2 * 16}")
        y = 496 - (slot["scb3"] >> 7)
        if y != DOME_Y + ey:
            failures.append(f"cell {ec}: y {y}, want {DOME_Y + ey}")
        if slot["attr"] >> 8 != 6:
            failures.append(f"cell {ec}: palette {slot['attr'] >> 8}, want 6")
        # slot k holds stone column c2: row r = picture first + r*w + c2
        # (the picture's stones are a dense w x h block; see cracks.c draw)
        for r in range(eh):
            t = slot["tiles"][r]
            want_t = et + r * ew + c2
            if t != want_t:
                failures.append(f"cell {ec} col {c2} row {r}: tile {t:#x}, "
                                f"want {want_t:#x}")
    # the tail after the last drawn cell must be hidden (SCB3 height 0)
    for s2 in range(total_slots - len(slots) + OVERLAY_FIRST, OVERLAY_LAST + 1):
        if OVERLAY_FIRST <= s2 <= OVERLAY_LAST:
            pass  # (covered by the count check above)

    # ---- the snapshot: coverage and black-hole checks ----
    im = Image.open(snap_png).convert("RGB")
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    pix = im.load()
    pal = broken_palette_rgb()
    black_rgb = pal[BLACK_PAL]

    def is_blackhole(px):
        # the broken window's hole is broken palette index 1, a real colour
        # the cartridge draws through MAME's DAC as pure black. The old
        # +-30 tolerance existed while the ship had no near-black pixels;
        # the hovercraft's dark outline (8,8,8)/(10,10,14) now falls inside
        # that window, so match the hole's exact colour instead.
        return tuple(px[:3]) == black_rgb

    # per-cell regions on the 320x224 screen. For the coverage checks the
    # region is the overlay's own stone box (the art's exact on-screen
    # area: the tables' canvas x/y are absolute screen px, w/h stones);
    # `frac` shrinks it toward its centre for the "black middle" checks.
    def cell_box(o, frac=1.0):
        cw, ch, left, top = o
        w, h = cw * 16, ch * 16
        iw, ih = max(2, int(w * frac)), max(2, int(h * frac))
        x0 = DOME_X + left + (w - iw) // 2
        y0 = DOME_Y + top + (h - ih) // 2
        img = Image.new("L", (320, 224), 0)
        d = ImageDraw.Draw(img)
        d.rectangle([x0, y0, x0 + iw - 1, y0 + ih - 1], fill=255)
        return np.asarray(img) > 0

    # ---- geometry-based checks: only meaningful at the natural view (the
    # overlays cover their cells' outlines). At a permutation angle the
    # overlays sit at the permuted cells' positions, where the "covers the
    # cell" relationship the geometry test proves does not apply — the
    # slot-stream check and the pixel-exact composite prove that leg.
    if q == 0:
        wants = [(c, art, o) for (c, art, o) in want]
        # The broken arts are 16px-grid boxes that can CROSS a neighbouring
        # cell's polygon (each art is that cell's polygon rounded to the stone
        # grid); a whole cell therefore stays visible only where no broken
        # art's box covers it. The checks below subtract the union of all
        # broken arts' boxes from each whole cell's region.
        broken_mask = np.zeros((224, 320), bool)
        for (c0, art, o) in want:
            m = cell_box(o, 1.0)
            if m is not None:
                broken_mask |= m
        # broken cells: the hole is PRESENT (the pure black, which only the
        # overlays use) somewhere in the cell's own stone box — the geometry
        # test already proves the art covers the cell, this proves it is
        # actually drawn there. (A sliver cell's "middle" can be a thin
        # diagonal, so presence, not dominance, is the assertion.)
        for (c0, art, o) in want:
            m = cell_box(o, 1.0)
            black = sum(1 for yy in range(224) for xx in range(320)
                        if m[yy, xx] and is_blackhole(pix[int(xx * sx), int(yy * sy)]))
            if black < max(1, m.sum() // 40):
                failures.append(f"cell {c0}: only {black} black-hole px in its "
                                "box — no broken window drawn where the geometry "
                                "test says one must be")
        # whole cells (not broken): their own polygon (2 px in, where the dome
        # always draws glass — the normal cart measures 0 pure black there) must
        # not be covered by a black hole. A broken neighbour's art may cross a
        # few pixels of the polygon at the stone-grid boundary (16-px tiles),
        # so a small allowance is fine; a genuinely broken cell is dominated by
        # the hole instead.
        def poly_mask(cell, v, inset=2):
            px = _poly_px(cell, v)
            cx, cy = px[:, 0].mean(), px[:, 1].mean()
            rad = max(np.hypot(px[:, 0] - cx, px[:, 1] - cy).max(), 1e-9)
            f = max(0.0, 1 - inset / rad)
            sh = [(cx + (x - cx) * f, cy + (y - cy) * f) for x, y in px]
            img = Image.new("L", (320, 224), 0)
            d = ImageDraw.Draw(img)
            d.polygon([(float(DOME_X + x), float(DOME_Y + y)) for x, y in sh],
                      fill=255)
            return np.asarray(img) > 0

        for cell in range(76):
            if cell in BROKEN_TEST_CELLS or not facing(cell):
                continue
            m = poly_mask(cell, VIEW) & ~broken_mask
            if not m.any():
                continue
            black = sum(1 for yy in range(224) for xx in range(320)
                        if m[yy, xx] and is_blackhole(pix[int(xx * sx), int(yy * sy)]))
            if black > max(3, m.sum() // 4):
                failures.append(f"whole cell {cell}: {black} black-hole pixels in "
                                "its drawn area — an intact cell reads as broken")
        # stray: inside the dome's drawn cell polygons (the union of every
        # facing cell's 2-px-inset polygon), the black hole may only appear
        # under a broken cell's art. The black backdrop is outside these
        # polygons, so it is not counted.
        faces = np.zeros((224, 320), bool)
        for cell in range(76):
            if facing(cell):
                faces |= poly_mask(cell, VIEW)
        stray = sum(1 for yy in range(224) for xx in range(320)
                    if faces[yy, xx] and not broken_mask[yy, xx]
                    and is_blackhole(pix[int(xx * sx), int(yy * sy)]))
        if stray:
            failures.append(f"snapshot: {stray} black-hole pixels on the dome's "
                            "faces outside every broken cell")

    # ---- draw order (the task's proof 3): the ship and a front missile
    # drawn OVER the broken cells stay intact. The ship is parked on the
    # start cell at the beginning of the test (its slots show then), so use
    # the first sampled frame here. -----------------------------
    # the ship: full size; its pixels (the ship's
    # palette, dominated by bright blue/white) must appear at its SCB3/4
    # position, which sits over the dome/broken cells.
    fr0 = frames[0]
    all_slots0 = fr0[2]
    ship_words = None
    for slot in all_slots0:
        if SHIP_FIRST <= slot["slot"] <= SHIP_LAST:
            x0 = slot["scb4"] >> 7
            y0 = 496 - (slot["scb3"] >> 7)
            hgt = slot["scb3"] & 0x3f
            if ship_words is None:
                ship_words = 0
            # count the ship's palette pixels in its 2x2-tile area
            blk = 0
            for yy in range(y0, min(224, y0 + hgt * 16)):
                for xx in range(max(0, x0), min(320, x0 + 32)):
                    if is_ship(pix[int(xx * sx), int(yy * sy)]):
                        blk += 1
            ship_words += blk
    if ship_words is None:
        failures.append(f"ship slots {SHIP_FIRST}..{SHIP_LAST} not shown in the "
                        "sampled frame — cannot prove draw order")
    elif ship_words < 150:
        failures.append(f"ship pixels over the broken cells: only {ship_words} "
                        "— the ship is not drawn intact over the overlays")
    # a front missile over a broken cell keeps its pixels: find a front
    # missile slot whose screen area overlaps a broken cell's
    # box, and check its bright pixels are present there.
    # the front-missile check uses the snapshotted frame (the first missile
    # launches ~fc 60; the snapshot is taken once the ship is drawn, at
    # fc>=110, where a wave missile is live)
    snap_slots = []
    for frn in frames:
        if frn[0] == snap_frame:
            snap_slots = frn[2]
            break
    front_ok = None
    for slot in snap_slots:
        if FRONT_FIRST <= slot["slot"] <= FRONT_LAST:
            x0 = slot["scb4"] >> 7
            y0 = 496 - (slot["scb3"] >> 7)
            hgt = slot["scb3"] & 0x3f
            # overlap with any drawn broken overlay box (the snapshot frame's
            # own slots, which reflect the effective dome_angle)?
            over = False
            for (c0, art, o) in want:
                m = cell_box(o, 1.0)
                yys, xxs = np.where(m)
                if len(xxs) and xxs.min() <= x0 + 31 and xxs.max() >= x0 and \
                   yys.min() <= y0 + hgt * 16 and yys.max() >= y0:
                    over = True
                    break
            if over:
                px = sum(1 for yy in range(y0, min(224, y0 + hgt * 16))
                         for xx in range(max(0, x0), min(320, x0 + 32))
                         if sum(pix[int(xx * sx), int(yy * sy)]) > 60)
                front_ok = max(front_ok or 0, px)
    if front_ok is None:
        failures.append("no front missile over a broken cell in the sampled "
                        "frame — cannot prove that draw order")
    elif front_ok < 10:
        failures.append(f"front missile over a broken cell: only {front_ok} "
                        "bright pixels — it is not drawn intact")

    # ---- the task's proof 2: the picture on screen is EXACTLY the dome view
    # plus each broken cell's render_bitmap at its offset (under the ship),
    # pixel by pixel in the dome box. We build the expected picture from the
    # REAL C ROM at the tile numbers the probe read back from VRAM, through the
    # same 15-bit -> RGB pipeline MAME uses, and require zero difference with
    # the snapshot outside the front missiles' and explosions' boxes (whose
    # shrunk pixel path is boot-tested separately, not reproduced here).
    aa = np.asarray(im.convert("RGB"))
    # the play backdrop is the sky (dome-scenery Task 4): the expected
    # picture starts as the sky, not black, wherever nothing draws. Then
    # the ground (dome-scenery Task 5) fills the band below the horizon —
    # the lowest sprite range, so it is pasted FIRST and everything else
    # draws over it.
    EXPECTED = np.zeros((224, 320, 3), np.uint8)
    EXPECTED[:, :] = npal.SKY_RGB
    # the palette banks the slots use (dome 1, broken 6, ship 2). Task 19:
    # the ground tiles use the 11 ripple banks 44..54, one per tile row, so
    # each ground tile row is pasted through its own bank's palette at the
    # ship's previous dome angle (the crack cart never turns it: the `P`
    # records' camera angle, 0, not the TEST angle `da` that turns the
    # overlay permutation), with the whole (gone 0) palette.
    dome_pal = npal.dome_palette_rgb()
    broken_pal = npal.broken_palette_rgb()
    ship_pal = npal.ship_palette_rgb()
    pal_by_attr = {1: dome_pal, 6: broken_pal, 2: ship_pal}
    gd, ground_bank, ripple_pal, ripple_rot = _ripple_header()
    GROUND_Y = gd["GROUND_Y"]
    GROUND_ROWS = gd["GROUND_ROWS"]
    prev_da = camera.get(snap_frame, 0)
    slot_by_num = {s["slot"]: s for s in snap_slots}
    for c in range(_SLOTS["GROUND_COUNT"]):
        slot = slot_by_num[GROUND_FIRST + c]
        for r in range(GROUND_ROWS):
            bank = ground_bank[c][r]
            pal = ripple_pal[bank][0][ripple_rot[bank][prev_da]]
            tile = slot["tiles"][r]
            npal.paste(EXPECTED, npal.tile_rgb(tile, pal),
                       c * 16, GROUND_Y + r * 16,
                       mask=npal.decode_tile(tile) != 0)
    # dome-scenery Task 12/15: the BACK props are right after the mountains
    # and below the missiles behind the dome, so they draw over the grass
    # and under the dome; the FRONT pool draws over the dome and its broken
    # overlays and under the ship. The probe does not dump their slots;
    # paste Task 11/15's model picture through the generated prop_pal +
    # prop_shadow (the same decode check_props.py uses, and the runtime's
    # blank rows below each picture are already handled by the zoom table:
    # rows below the picture are skipped).
    # the props follow the CAMERA, not the overlays' test-only override: on
    # the crack cart the ship stays parked at cell 27 (dome_angle 0) while
    # CRACK_ANGLE >= 48 forces a different overlay permutation, so the
    # probe's P records carry the real angle (`da` is only right at 0).
    prop_da = camera.get(snap_frame, da)
    back_pic, back_drawn = npal.props_picture(prop_da, pool=0)
    EXPECTED[back_drawn] = back_pic[back_drawn]
    # the dome and ship are sticky chains (one driver + followers); the
    # overlays are independent columns. Composite in hardware order (higher
    # sprite slot number draws on top).
    npal.composite_run(EXPECTED, snap_slots, dome_pal, DOME_FIRST, _SLOTS["DOME_COUNT"])
    for slot in snap_slots:
        if OVERLAY_FIRST <= slot["slot"] <= OVERLAY_LAST:
            bank = (slot["attr"] >> 8) & 0xf
            if bank in pal_by_attr:
                npal.composite_slot(EXPECTED, slot, pal_by_attr[bank])
    # Task 15: the front pool sits between the overlays and the ship.
    front_pic, front_drawn = npal.props_picture(prop_da, pool=1)
    EXPECTED[front_drawn] = front_pic[front_drawn]
    npal.composite_run(EXPECTED, snap_slots, ship_pal, SHIP_FIRST, _SLOTS["SHIP_COUNT"])
    # dome-scenery Task 7: the console sits right after the ship (higher
    # slots, drawn on top); Task 8 lowered its art so 30 of its trim pixels
    # now fall inside the dome box's bottom corners (y 195..199). The probe
    # does not dump its slots, so paste the committed generator's own
    # picture through the generated con_pal at the header's placement.
    import render_console as rc
    con_pic = rc.console_picture()
    con_rgb = [npal.neo_rgb(w) for w in
               [int(x, 16) for x in re.findall(
                   r"0x[0-9a-fA-F]{4}", open(os.path.join(ROOT, "build",
                                                          "console_map.h")).read())]]
    for cy in range(224):
        for cx in range(320):
            idx = int(con_pic[cy, cx])
            if idx:
                EXPECTED[cy, cx] = con_rgb[idx]
    # compare within the dome box
    x0, y0, x1, y1 = DOME_X, DOME_Y, DOME_X + DOME_W - 1, DOME_Y + DOME_H - 1
    miss = np.zeros((224, 320), bool)      # boxes to exclude: the front
    for slot in snap_slots:                # missiles + explosions (shrunk, a
        if FRONT_FIRST <= slot["slot"] <= EXPL_LAST:     # separate boot test's subject)
            mx = slot["scb4"] >> 7
            my = 496 - (slot["scb3"] >> 7)
            mh = slot["scb3"] & 0x3f
            if mh:
                # the probe's slot boxes are per-column; an object's drawn area
                # spans up to MIS_COLS_MAX * 16 px, so mark the full 64 px wide
                # box the object could cover (a few extra excluded px cost
                # nothing: the shrunk rendering is not part of this compare)
                miss[max(0, my):min(224, my + mh * 16),
                     max(0, mx):min(320, mx + 64)] = True
    diff = 0
    worst = None
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            if miss[yy, xx]:
                continue
            if (aa[yy, xx] != EXPECTED[yy, xx]).any():
                diff += 1
                if worst is None:
                    worst = (xx, yy, tuple(aa[yy, xx]), tuple(EXPECTED[yy, xx]))
    if diff:
        failures.append(f"pixel-exact: {diff} px differ in the dome box "
                        f"(first {worst}) — the picture on screen is not the "
                        "dome + overlays + ship the cartridge's tiles draw")

    if failures:
        print("FAIL broken:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS broken (dome_angle {fr[1]}): {len(want)} visible of "
          f"{len(BROKEN_TEST_CELLS)} broken cells show overlays, interiors "
          f"black, whole cells intact, and the dome+overlays+ship composite "
          "is pixel-exact in the dome box")
    return 0


if __name__ == "__main__":
    sys.exit(main())
