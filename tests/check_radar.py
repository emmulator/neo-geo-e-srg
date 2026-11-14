#!/usr/bin/env python3
"""Assertions for the M5 Task 4 radar boot-test (proof 2).

  check_radar.py SNAP PROBE [MIS_ADDR [SHIP_ADDR [FRAMECNT_ADDR]]]

scripts/radar_probe.lua boots the -DRADAR_TEST cart (its first missile of
each game is forced to target the ship's start cell 27, so with no input
the ship rests on that cell and the lock-on happens by itself — see the
flag's comment in src/main.c), plays ~2400 MAME frames, and on every cart
frame reads from RAM and VRAM (see the probe's header for the layout):

  - the ship (cell, move_left, dome_angle) and every missile object;
  - the cart's own radar_t (the static `radar` in main.c): every blip's
    (shown, locked, sx, sy, h, hx, hy) and lock_t/locked/ellipse_bright —
    the exact struct radar_gfx_prepare read; and, on every sample, the
    previous frame's radar_t and blink word (the `b`/`r` lines), because
    Task 18b's commit at the start of frame fc wrote frame fc-1's prepared
    state;
  - every radar sprite slot's VRAM (SCB2/SCB3/SCB4, SCB1 row-0 tile +
    attribute, rows 1/2's attributes, and the whole 32-row SCB1 column);
  - the radar's two palette banks (Task 10): bank 20 entries 0..4 and
    bank 21 entries 0..1, from palette RAM;
  - on the snapshot frame, the fix rows that can overlap the frame's box;
  - a full sprite census (all 381 slots) every 30th frame.

This checker:

  1. proves the cart's radar_t (RAM) equals radar_model.Radar's per-frame
     state on every sampled frame — the RAM readings are the ground truth
     the drawing used (locked, ellipse_bright, every blip's shown/locked);
  2. proves the VRAM at frame fc matches the cart's blips at frame fc-1
     (the prepared state the commit at fc wrote):
       - each shown blip's stick: SCB4 (X = sx - 7 — the line is the art's
         column 7, see radar_gfx.c) and SCB3 (top = sy - 48, height 3)
         within 1 px, and the SCB1 row-0 tile is
         RADAR_STICK_TILE_BASE + (2h + locked) * 3 (tests/test_radar_render.py
         proves the picture at each number has exactly h lit pixels in
         column 7, or 7..8 when locked);
       - each shown blip's heading: SCB2's hz nibble = |dx| - 1, the
         vertical byte = radar_head_vz(|dy|), the SCB1 attr's h-flip bit
         equals the model's hf, and the box (SCB4 X, SCB3 Y) is placed per
         radar_gfx.c's formulas so the drawn staircase's start is the
         stick's top (and its end is within 1 px of (hx, hy) — the formula
         is mirrored here, so an exact match proves the placement);
       - a hidden blip (not shown): both its stick and heading slots' SCB3
         height is 0 (hidden in the same frame);
  3. proves the radar's palette banks (Task 10): bank 20 entries 0..4 are
     radar_pal {0x8000, 0x2d61, 0x0210, 0x3940, 0x4000}, with entry 1
     equal to radar_pal_bright (0x4fc5) exactly when the model's previous
     frame says ellipse_bright and radar_pal[1] (0x2d61) otherwise (the
     commit at fc wrote fc-1's prepared blink) — the blink is exactly that
     one entry; bank 21 entries 0..1 are radar_stick_pal {0x8000, 0x6f42}
     on every sampled frame. Every frame slot's SCB1 rows carry bank 20;
     every shown stick's and heading's carry bank 21;
  4. requires >= 50 sampled frames locked (the test cartridge's first
     missile is in range and aimed at the resting ship for ~580 frames);
  5. Task 10 proof 3: in the snapshot, every frame-picture pixel that no
     other sprite (a shown stick or heading) or fix tile covers shows the
     picture's colour through MAME's DAC (neo_rgb), at least 90% of the
     picture's opaque pixels; and a shown stick's lit pixels are
     radar_stick_pal[1]'s colour;
  6. reports the most sprites on any one line of the radar rows (the
     picture's band, RADAR_CY-49 .. RADAR_CY+8 — 157..214 at CY 206) from
     the full sprite census (the hardware's per-line limit is 96) — the
     "busiest sampled frame".
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import radar_model as rm  # noqa: E402
import layout as lay  # noqa: E402

# the one sprite slot map (src/slots.h -> build/slots.json)
_SLOTS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "build", "slots.json")))

FRAME_SLOTS = 4
# radar_gfx_init: the frame's 4 slots sit at y RADAR_CY-16, height 2. The
# radar's centre comes from src/radar.h (RADAR_CY 206: a literal, moved 22
# px down onto the console's left wing by dome-scenery Task 8 so the disc's
# bottom ends on y 215 with the lives and the score).
FRAME_SCB3 = ((496 - (lay.d.RADAR_CY - 16)) << 7) | 2
NMIS = rm.NMIS
TOL = 1                     # px: the task's bound
MIN_LOCKED = 50             # at least 50 sampled frames locked
RADAR0 = _SLOTS["RADAR_SPRITE"]     # build/slots.json: RADAR_SPRITE (the
                                     # 20 ground + 15 behind missiles + the
                                     # dome's 8 slots + 110 overlays + 2 ship
                                     # + 15 front missiles + 6 explosions;
                                     # the stars' 12 slots are gone, dome-
                                     # scenery Task 4)
# Task 10: the radar's two palette banks' exact words (build/radar_map.h).
# Bank 20: radar_pal (entry 1 the dim rim/roof, 2..4 the disc) and the
# bright blink word for entry 1; bank 21: radar_stick_pal (the sticks' and
# headings' steady red-orange). RADAR_STICK_PAL_BANK is src/radar_gfx.h's.
RADAR_PAL_BANK = 20
RADAR_STICK_PAL_BANK = 21
RADAR_PAL = [0x8000, 0x2d61, 0x0210, 0x3940, 0x4000]
RADAR_STICK_PAL = [0x8000, 0x6f42]
PAL_DIM, PAL_BRIGHT = RADAR_PAL[1], 0x4fc5
def _radar_defines():
    """the generated build/radar_map.h's tile bases, evaluated the way the
    other boot checkers read generated headers. The ship's tiles are part of
    the C ROM before the broken sheet, so the radar's bases follow the ship
    art (the hovercraft's 8 headings are 20,032 tiles, not the old
    pyramid's 192): the checker must not carry the old numbers."""
    out = {}
    txt = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                            "build", "radar_map.h")).read()
    for raw in txt.splitlines():
        m = re.match(r"#define\s+(\w+)\s+(.+)", raw)
        if not m:
            continue
        expr = m.group(2).split("/*")[0].strip()
        for k in sorted(out, key=len, reverse=True):
            expr = re.sub(r"\b%s\b" % k, str(out[k]), expr)
        try:
            out[m.group(1)] = int(eval(expr, {"__builtins__": {}}, {}))
        except (ValueError, NameError, TypeError, SyntaxError):
            pass
    return out


_RD = _radar_defines()
STICK_BASE = _RD["RADAR_STICK_TILE_BASE"]
HEAD_BASE = _RD["RADAR_HEAD_TILE_BASE"]
# the task's radar rows: the picture's band (the frame spans RADAR_CY-16 ..
# RADAR_CY+15, the sticks +48, the spot up to ~+10 — 157..214 at CY 206,
# moved down by dome-scenery Task 8 onto the console's left wing). The band
# follows the header's RADAR_CY, like FRAME_SCB3 above.
RADAR_Y0, RADAR_Y1 = lay.d.RADAR_CY - 49, lay.d.RADAR_CY + 8

# the C's radar_t / radar_blip_t layout (src/radar.h + m68k ABI, checked
# against the ELF's DWARF; the probe reads the same offsets)
BLIP = 12
BLIP_SHOWN, BLIP_LOCKED = 0, 1
BLIP_SX, BLIP_SY, BLIP_H = 2, 4, 6
BLIP_HX, BLIP_HY = 8, 10

# radar_head_vz (src/radar_gfx.c): the vertical byte that draws exactly dy
# box lines
HEAD_VZ = [1, 1, 17, 33, 49, 65, 81, 97, 113, 129, 145, 161, 177, 193,
           209, 225, 241]


def parse(fname):
    """(records, samples, snap_fix) — samples: {fc: {ship, objs, blips,
    radar, slots, pal, pal20, pal21, columns, census}}; snap_fix: {row:
    [tile 0..39]} on the snapshot frame."""
    records = []
    samples = {}
    snap_fix = {}
    cur = None
    census = None

    def new_sample(fc):
        nonlocal cur, census
        cur = {"ship": None, "objs": [None] * 5, "blips": [None] * 3,
               "radar": None, "slots": {}, "pal": None,
               "prev_blips": [None] * 3, "prev_radar": None,
               "pal20": {}, "pal21": {}, "columns": {}, "census": census}
        samples[fc] = cur
        census = None

    for raw in open(fname, "rb"):
        line = raw.decode("ascii", "replace").strip()
        if not line:
            continue
        p = line.split()
        if p[0] == "I":
            records.append(tuple(int(x) for x in p[1:5]))
        elif p[0] == "A":
            new_sample(int(p[1]))
            cur["ship"] = tuple(int(x) for x in p[2:5])
        elif p[0] == "O" and cur is not None:
            cur["objs"][int(p[2])] = tuple(int(x) for x in p[3:])
        elif p[0] == "B" and cur is not None:
            cur["blips"][int(p[2])] = tuple(int(x) for x in p[3:])
        elif p[0] == "b" and cur is not None:
            cur["prev_blips"][int(p[2])] = tuple(int(x) for x in p[3:])
        elif p[0] == "r" and cur is not None:
            cur["prev_radar"] = tuple(int(x) for x in p[2:5])
        elif p[0] == "R" and cur is not None:
            cur["radar"] = tuple(int(x) for x in p[2:5])
        elif p[0] == "T" and cur is not None:
            # Task 10: slot, attr, tile0, scb2, scb3, scb4, attr_row1,
            # attr_row2
            cur["slots"][int(p[2])] = (int(p[3], 16), int(p[4], 16),
                                       int(p[5], 16), int(p[6], 16),
                                       int(p[7], 16), int(p[8], 16),
                                       int(p[9], 16))
        elif p[0] == "K" and cur is not None:
            cur["columns"][int(p[2])] = [int(x, 16) for x in p[3:35]]
        elif p[0] == "Q" and cur is not None:
            cur["pal20"][int(p[2])] = int(p[3], 16)
        elif p[0] == "V" and cur is not None:
            cur["pal21"][int(p[2])] = int(p[3], 16)
        elif p[0] == "P" and cur is not None:
            cur["pal"] = int(p[2], 16)
        elif p[0] == "F":
            snap_fix[int(p[2])] = [int(x) for x in p[3:43]]
        elif p[0] == "W" and cur is not None:
            census = {}
        elif p[0] == "w" and census is not None:
            census[int(p[1])] = (int(p[2], 16), int(p[3], 16))
    return records, samples, snap_fix


def _heading_placement(sx, sy, h, hx, hy):
    """the heading box (bx, by) and the model's hf/hz/vz — radar_gfx.c's
    formulas, mirrored exactly."""
    tx, ty = sx, sy - h
    adx = abs(hx - tx)
    ady = abs(hy - ty)
    if adx == 0 and ady == 0:
        return None             # no line: the stick's top IS the centre
    hf = 1 if ((hx < tx) ^ (hy < ty)) else 0
    hz = adx - 1 if adx else 0
    bx = tx if hy >= ty else hx
    by = ty if hy >= ty else hy
    if hf and adx:
        bx -= adx - 1
    return bx, by, hf, hz, adx, ady


class _Ship:
    """the radar_model.Radar.frame shim: it reads only cell and left."""
    def __init__(self, cell, left):
        self.cell, self.left = cell, left


def _heading_drawn(art, adx, ady, hf):
    """the heading sprite's drawn lit box pixels [(line, col)] in box coords
    (y down), from the heading tile `art` and the hardware's zoom tables —
    the same decode tests/test_radar_render.py's sim_draw uses. A dy=0
    heading is a one-line horizontal run, as its art row holds."""
    import render_radar as rr
    hz = max(0, adx - 1)
    cols = rr.ZOOM_X_COLS[hz]
    if ady == 0:
        rows = [rr._ZOOM_Y[(1 << 8) | 0] & 0x0f]
    else:
        _vz, rows = rr._VZ_FOR_DY[ady]
    out = []
    for line, r in enumerate(rows):
        for i, c in enumerate(cols):
            ac = c if not hf else 15 - c
            if art[r][ac]:
                out.append((line, i))
    return out


def _fix_opaque_mask(snap_fix, y0, y1):
    """(h, w) bool for lines y0..y1 of the screen: does the fix layer draw a
    lit pixel there? `snap_fix` is {row: [tile 0..39]} from the probe's F
    lines; fix row r covers screen y 8r-16..8r-9, col c x 8c..8c+7. The
    tiles decode from the assembled S ROM (a tile's palette index 0 is
    transparent)."""
    import numpy as np
    import os
    s1 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                           "build", "rom", "esrg-s1.s1"), "rb").read()
    h, w = y1 - y0, 320
    mask = np.zeros((h, w), bool)
    for r, tiles in snap_fix.items():
        ry = 8 * r - 16
        for c in range(min(40, len(tiles))):
            raw = s1[tiles[c] * 32:(tiles[c] + 1) * 32]
            idx = np.zeros((8, 8), np.uint8)
            i = 0
            for xa, xb in ((4, 5), (6, 7), (0, 1), (2, 3)):
                for yy in range(8):
                    b = raw[i]
                    i += 1
                    idx[yy][xa] = b & 0xf
                    idx[yy][xb] = (b >> 4) & 0xf
            if not idx.any():
                continue
            for yy in range(8):
                sy = ry + yy
                if sy < y0 or sy >= y1:
                    continue
                for xx in range(8):
                    if idx[yy][xx]:
                        sx = c * 8 + xx
                        if 0 <= sx < w:
                            mask[sy - y0, sx] = True
    return mask


def check_snapshot_pixels(snap_png, snap_fc, samples, snap_fix, failures):
    """Proof 3 (Task 10): in the snapshot, the frame's 64 x 32 box shows
    neo_rgb of frame_picture()'s colours on every pixel no other sprite or
    fix tile covers; and one shown stick's lit pixels are radar_stick_pal[1]'s
    colour. Returns (compared, matched, opaque_picture, stick_px) for the
    report."""
    import sys
    import numpy as np
    from PIL import Image
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "tools"))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import render_radar as rr
    import neo_palette as npal

    s = samples.get(snap_fc)
    if s is None:
        failures.append(f"SNAP frame {snap_fc}: no sampled VRAM/RAM state")
        return 0, 0, 0, 0
    # the picture, its palette RGBs and the frame's on-screen box
    pic = rr.frame_picture()
    pal_rgb = [tuple(npal.neo_rgb(w)) for w in RADAR_PAL]
    cx, cy = lay.d.RADAR_CX, lay.d.RADAR_CY
    x0, y0 = cx - 32, cy - 16
    h, w = pic.shape

    # ---- the masks: what draws OVER the frame's own picture ----
    # The radar occupies the topmost slot range. Its own sticks and headings
    # are above the frame's 4 slots; every other sprite (front missiles,
    # explosions) is below them and draws UNDER the picture. The fix layer
    # draws over everything. So mask the sticks'/headings' ACTUAL lit pixels
    # (from their pictures and the zoom tables), plus the fix layer's opaque
    # pixels, and compare the rest.
    sprite_mask = np.zeros((h, w), bool)
    for k in range(NMIS):
        b = s["prev_blips"][k]
        if b is None or not b[0]:
            continue
        _shown, locked, sx, sy, hgt, hx, hy = b
        # the stick's picture: art column 7 (7..8 locked), bottom hgt rows,
        # at the runtime's box (sx-7, sy-48) — what the VRAM places.
        art = rr.stick_bitmap(hgt, bool(locked))
        bx, by = sx - 7, sy - rr.STICK_H
        for yy in range(rr.STICK_H):
            for xx in range(16):
                if art[yy, xx]:
                    px, py = bx + xx - x0, by + yy - y0
                    if 0 <= px < w and 0 <= py < h:
                        sprite_mask[py, px] = True
        hp = _heading_placement(sx, sy, hgt, hx, hy)
        if hp is None:
            continue
        hbx, hby, hf, _hz, adx, ady = hp
        head = rr.heading_art(adx, ady, hf)
        for line, col in _heading_drawn(head, adx, ady, hf):
            px, py = hbx + col - x0, hby + line - y0
            if 0 <= px < w and 0 <= py < h:
                sprite_mask[py, px] = True
    # the fix layer's lit pixels (the probe's snap_fix rows are exactly the
    # ones that can cover the 64 x 32 box)
    fix_mask = _fix_opaque_mask(snap_fix, y0, y0 + h) if snap_fix else \
        np.zeros((h, w), bool)

    im = Image.open(snap_png).convert("RGB")
    iw, ih = im.size
    opaque = int((pic != 0).sum())
    compared = matched = 0
    mism = []
    for yy in range(h):
        for xx in range(w):
            idx = int(pic[yy, xx])
            if idx == 0:
                continue
            if sprite_mask[yy, xx] or fix_mask[yy, xx]:
                continue
            got = tuple(im.getpixel((int((x0 + xx) * iw / 320),
                                     int((y0 + yy) * ih / 224)))[:3])
            compared += 1
            if got == pal_rgb[idx]:
                matched += 1
            elif len(mism) < 10:
                mism.append((x0 + xx, y0 + yy, idx, got, pal_rgb[idx]))
    need = int(opaque * 0.90)
    if compared < need:
        failures.append(f"SNAP frame {snap_fc}: only {compared} of the "
                        f"picture's {opaque} opaque px are uncovered "
                        f"(want >= 90% = {need})")
    if matched != compared:
        failures.append(f"SNAP frame {snap_fc}: {compared - matched} of "
                        f"{compared} uncovered picture px mismatch "
                        f"neo_rgb: {mism[:5]}")

    # ---- one shown stick's lit pixels are radar_stick_pal[1] ----
    stick_col = tuple(npal.neo_rgb(RADAR_STICK_PAL[1]))
    stick_px = stick_ok = 0
    for k in range(NMIS):
        b = s["prev_blips"][k]
        if b is None or not b[0]:
            continue
        slot = RADAR0 + FRAME_SLOTS + k * 5
        st = s["slots"].get(slot)
        if st is None:
            continue
        _attr, tile0, _scb2, scb3, scb4, _a1, _a2 = st
        art = rr.stick_bitmap(b[4], bool(b[1]))
        sx = scb4 >> 7
        sy = 496 - (scb3 >> 7)
        # the picture is the tile at RADAR_STICK_TILE_BASE + (2h+locked)*3,
        # 3 tiles tall; its lit art pixels are the bottom `h` rows of col 7
        # (7..8 when locked)
        for yy in range(16 * 3):
            for xx in range(16):
                if not art[yy, xx]:
                    continue
                px = sx + xx
                py = sy + yy
                if not (0 <= px < 320 and 0 <= py < 224):
                    continue
                got = tuple(im.getpixel((int(px * iw / 320),
                                         int(py * ih / 224)))[:3])
                stick_px += 1
                if got == stick_col:
                    stick_ok += 1
        break
    if stick_px < 5:
        failures.append(f"SNAP frame {snap_fc}: no shown stick's lit pixels "
                        "could be sampled")
    elif stick_ok != stick_px:
        failures.append(f"SNAP frame {snap_fc}: {stick_px - stick_ok} of "
                        f"{stick_px} stick pixels are not "
                        f"radar_stick_pal[1] {stick_col}")
    return compared, matched, opaque, stick_px


def _radar_region_count(census):
    """the most sprites whose box covers any line in the radar rows
    (RADAR_Y0..RADAR_Y1, the picture's band from src/radar.h's RADAR_CY),
    from every slot's SCB3 (top, height) / SCB4 (X). Sprites with height 0
    are not drawn. Clamped to the band's lines."""
    rows = [0] * (RADAR_Y1 - RADAR_Y0 + 1)
    for scb3, _scb4 in census.values():
        height = scb3 & 0x3f
        if not height:
            continue
        top = 496 - (scb3 >> 7)
        bot = top + height * 16 - 1
        if bot < RADAR_Y0 or top > RADAR_Y1:
            continue
        for y in range(max(RADAR_Y0, top), min(RADAR_Y1, bot) + 1):
            rows[y - RADAR_Y0] += 1
    return max(rows) if rows else 0


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    mis_addr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    ship_addr = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0
    fc_addr = int(sys.argv[5], 0) if len(sys.argv) > 5 else 0
    records, samples, snap_fix = parse(probe)
    failures = []

    if not records:
        failures.append("probe wrote no input records")
        return 1
    if mis_addr == 0 or ship_addr == 0:
        failures.append("no mis/ship RAM addresses (m68k-neogeo-elf-nm failed?)")
        return 1
    if not samples:
        failures.append("probe sampled no frames")
        return 1

    # ---- replay the game from the recorded inputs (as check_hud does), so
    # the radar_model (lock_t, ellipse_bright, blips) runs one step per real
    # cart frame, and validate each sampled frame against it. The RADAR_TEST
    # hook's two forced spawns are applied to the model exactly as the cart's
    # main.c does (the first missile of each game -> the start cell; the
    # second -> ring 4, azimuth 63), so the model's radar == the cart's.
    import mis_model as mmm  # noqa: E402
    import mis_seed  # noqa: E402  (Task 1: the cart's seed)
    import rules_model as rmm  # noqa: E402
    import ship_model as sm  # noqa: E402

    first = None
    for i, (rec, fc, cur, chg) in enumerate(records):
        if fc == 1:
            first = i
            break
    if first is None:
        first = 0
    seed = mis_seed.cart_seed(probe)  # Task 1: the cart's mis_seed_used
    ship, mis, rules = sm.Ship(), mmm.Missiles(seed=seed), rmm.Rules(1)
    print(f"mis_seed_used: {seed:#06x}")
    rmod = rm.Radar()
    rmod.locked = 0                 # game_begin's init state (no blips shown)
    rmod.bright = 0                 # (the first frame's radar_frame sets them)
    n = len(records)
    i = first
    n_locked = 0
    stick_bad = head_bad = hidden_bad = pal_bad = radar_bad = blip_bad = frame_bad = 0
    prev_radar_bad = 0
    stickpal_bad = frame_pal_bad = stick_pal_bad = 0
    busiest = (0, None)
    test_done = test_done2 = 0      # the RADAR_TEST hook's per-game flags

    def radar_test_spawn():
        """mirror src/main.c's radar_test_spawn: the first fresh missile of
        each game is retargeted to the start cell, the second to ring 4 phi
        63 (cell 25)."""
        nonlocal test_done, test_done2
        for k in range(NMIS):
            o = mis.obj[k]
            if o.state == 1 and o.kind == 0 and o.r == mmm.R_SPAWN[o.ring]:
                if not test_done:
                    o.ring, o.phi = mmm.CELL_RING[27], mmm.CELL_PHI[27]
                    o.r = mmm.R_SPAWN[o.ring]
                    test_done = 1
                    return
                if not test_done2:
                    o.ring, o.phi = mmm.CELL_RING[25], mmm.CELL_PHI[25]
                    o.r = mmm.R_SPAWN[o.ring]
                    test_done2 = 1
                    return

    while 0 <= i < n:
        rec, fc, cur, chg = records[i]
        # Task 18b: the VRAM read at the end of cart frame fc holds the
        # radar_gfx_prepare state of frame fc-1 (the commit runs at the
        # start of fc); the RAM radar_t read at fc is the current frame's.
        # The probe records the previous frame's cart radar_t (b/r/p), so
        # the VRAM/palette/pixel checks below use those exact values.
        prev_bright = rmod.bright
        busy = rules.begin(ship, mis, chg)
        if not busy:
            ship.frame(cur, chg)
        if not busy:
            if chg & rmm.A:
                mis.fire_req = 1
            if mis.fire_req and not ship.left:
                mis.fire(ship.cell)
                mis.fire_req = 0
        mis.hits, mis.lands = [], []
        for o in mis.obj:
            if o.state != 1:
                continue
            if o.kind:
                o.r += o.dr
                o.life -= 1
                if o.life == 0:
                    o.state = 0
            else:
                o.r -= o.dr
                if o.r <= mmm.LAND:
                    o.state = 2
        for b in mis.obj[mmm.NMIS:]:
            if b.state != 1:
                continue
            for o in mis.obj[:mmm.NMIS]:
                if o.state == 1 and o.phi == b.phi and o.ring == b.ring and b.r >= o.r:
                    mis.hits.append((o.ring, o.phi, o.r))
                    mis.kills = min(255, mis.kills + 1)
                    mis.score = min(9999999, mis.score + rules.integ)
                    o.state = b.state = 0
                    break
        live = 0
        for o in mis.obj[:mmm.NMIS]:
            if o.state == 2:
                c = mmm.RING_END[o.ring - 1] if o.ring else 0
                while mmm.CELL_PHI[c] != o.phi:
                    c += 1
                mis.lands.append(c)
                if c not in ship.broken:     # a landing that broke a whole cell
                    mis.dome_hits = min(255, mis.dome_hits + 1)
                rules.break_cell(ship, c)
                o.state = 0
            if o.state:
                live += 1
        if not (rules.dead_t or rules.game_over):
            if mis.timer:
                mis.timer -= 1
            elif live >= mmm.V["wave_live"]:
                pass
            else:
                o = next(o for o in mis.obj if not o.state)
                mis.spawn(o, ship.broken)
                mis.timer = ((mmm.V["spawn_gap"] + (mis.rand8() & 63)) * 59 + 25) // 50
        # the RADAR_TEST hook (after mis_update, before rules_end/radar_frame)
        if rules.game_over:
            test_done = test_done2 = 0
        radar_test_spawn()
        rules.end(ship, mis)
        mis.integ = rules.integ

        # the frame's radar (after the logic, as the cart's radar_frame) —
        # advanced EVERY frame so the lock_t/blink counting matches the cart
        sh = _Ship(ship.cell, ship.left)
        rmod.frame(sh, mis)
        if rmod.locked:
            n_locked += 1
        if fc not in samples:
            i += 1
            continue
        s = samples[fc]
        # 1. the cart's radar_t vs the model
        if s["radar"] is not None:
            if s["radar"][1] != rmod.locked:
                radar_bad += 1
                if radar_bad <= 5:
                    failures.append(f"frame {fc}: cart radar.locked "
                                    f"{s['radar'][1]}, model {rmod.locked}")
            if s["radar"][2] != rmod.bright:
                radar_bad += 1
                if radar_bad <= 5:
                    failures.append(f"frame {fc}: cart ellipse_bright "
                                    f"{s['radar'][2]}, model {rmod.bright}")
        # each blip's shown/locked vs the model
        for k in range(NMIS):
            o = mis.obj[k]
            want_shown = 1 if (o.state == 1 and o.r < rm.R_LIMIT) else 0
            want_locked = 1 if (want_shown and rmod.locked and
                                o.ring == rm.CELL_RING[ship.cell] and
                                o.phi == rm.CELL_PHI[ship.cell]) else 0
            b = s["blips"][k]
            if b is not None and (b[0] != want_shown or b[1] != want_locked):
                blip_bad += 1
                if blip_bad <= 5:
                    failures.append(f"frame {fc} blip {k}: cart "
                                    f"({b[0]},{b[1]}), model "
                                    f"({want_shown},{want_locked})")

        # 2. the VRAM at fc vs the previous frame's blips (the prepared
        # state the commit wrote at the start of fc)
        for k in range(NMIS):
            b = s["prev_blips"][k]
            if b is None:
                continue
            shown = b[0]
            stick_slot = RADAR0 + FRAME_SLOTS + k * 5
            head_slot = stick_slot + 1
            st = s["slots"].get(stick_slot)
            hd = s["slots"].get(head_slot)
            if not shown:
                if st is not None and (st[3] & 0x3f):
                    hidden_bad += 1
                    if hidden_bad <= 5:
                        failures.append(f"frame {fc} blip {k}: hidden stick "
                                        f"SCB3 {st[3]:#06x}")
                if hd is not None and (hd[3] & 0x3f):
                    hidden_bad += 1
                    if hidden_bad <= 5:
                        failures.append(f"frame {fc} blip {k}: hidden heading "
                                        f"SCB3 {hd[3]:#06x}")
                continue
            if st is None or hd is None:
                failures.append(f"frame {fc} blip {k}: shown but no slot read")
                continue
            _attr_s, _t0_s, _scb2_s, scb3_s, scb4_s = st[:5]
            attr_h, t0_h, scb2_h, scb3_h, scb4_h = hd[:5]
            sx, sy, h = b[2], b[3], b[4]
            hx, hy = b[5], b[6]
            locked = b[1]
            # stick: X = sx - 7, top at sy - 48, height 3,
            # tile base + (2h+locked)*3
            got_x = scb4_s >> 7
            got_top = 496 - (scb3_s >> 7)
            got_h = scb3_s & 0x3f
            want_tile = STICK_BASE + (2 * h + locked) * 3
            if abs(got_x - (sx - 7)) > TOL or abs(got_top - (sy - 48)) > TOL \
               or got_h != 3 or _t0_s != want_tile:
                stick_bad += 1
                if stick_bad <= 5:
                    failures.append(
                        f"frame {fc} blip {k} stick: VRAM (X {got_x}, top "
                        f"{got_top}, h {got_h}, tile {_t0_s}), want (sx-7 "
                        f"{sx - 7}, sy-48 {sy - 48}, h 3, tile {want_tile})")
            # heading
            hp = _heading_placement(sx, sy, h, hx, hy)
            if hp is None:
                # no line: the heading slot must be hidden
                if hd is not None and (hd[3] & 0x3f):
                    head_bad += 1
                    if head_bad <= 5:
                        failures.append(f"frame {fc} blip {k}: centre-top "
                                        f"has a visible heading "
                                        f"SCB3 {hd[3]:#06x}")
                continue
            bx, by, hf, hz, adx, ady = hp
            got_bx = scb4_h >> 7
            got_by = 496 - (scb3_h >> 7)
            got_bh = scb3_h & 0x3f
            got_hz = (scb2_h >> 8) & 0x0f
            got_vz = scb2_h & 0xff
            want_tile = HEAD_BASE + (ady * 17 + adx) * 2 + hf
            if abs(got_bx - bx) > TOL or abs(got_by - by) > TOL or got_bh != 1 \
               or got_hz != hz or got_vz != HEAD_VZ[ady] \
               or (attr_h & 1) != hf or t0_h != want_tile:
                head_bad += 1
                if head_bad <= 5:
                    failures.append(
                        f"frame {fc} blip {k} heading: VRAM (X {got_bx}, "
                        f"top {got_by}, h {got_bh}, hz {got_hz}, vz "
                        f"{got_vz}, flip {attr_h & 1}, tile {t0_h}), want "
                        f"(bx {bx}, by {by}, h 1, hz {hz}, vz "
                        f"{HEAD_VZ[ady]}, flip {hf}, tile {want_tile})")

        # 3. the frame bank's palette (Task 10): bank 20 entries 0..4 ==
        # radar_pal, entry 1 = dim or bright as the model's blink says; and
        # bank 21 entries 0..1 == radar_stick_pal (steady, never rewritten).
        # Task 18b: VRAM at fc holds frame fc-1's prepared palette, so the
        # probe's previous palette word is what the commit wrote at fc; it
        # must also equal the model's previous bright state.
        if s["pal20"] and s["pal21"]:
            pr = s["prev_radar"]
            if pr is None:
                prev_radar_bad += 1
                if prev_radar_bad <= 5:
                    failures.append(f"frame {fc}: no previous radar record "
                                    "for the lag-aware check")
            else:
                if pr[2] != prev_bright:
                    prev_radar_bad += 1
                    if prev_radar_bad <= 5:
                        failures.append(
                            f"frame {fc}: previous cart ellipse_bright "
                            f"{pr[2]}, model at fc-1 {prev_bright}")
                want = list(RADAR_PAL)
                want[1] = PAL_BRIGHT if prev_bright else PAL_DIM
                got = [s["pal20"].get(e) for e in range(5)]
                if got != want:
                    pal_bad += 1
                    if pal_bad <= 5:
                        failures.append(f"frame {fc}: bank 20 entries 0..4 "
                                        f"{[None if g is None else hex(g) for g in got]}, "
                                        f"want {[hex(w) for w in want]} "
                                        f"(bright at fc-1={prev_bright})")
            if [s["pal21"].get(e) for e in range(2)] != list(RADAR_STICK_PAL):
                stickpal_bad += 1
                if stickpal_bad <= 5:
                    failures.append(f"frame {fc}: bank 21 entries 0..1 "
                                    f"{[s['pal21'].get(e) for e in range(2)]}, "
                                    "want radar_stick_pal")
        # 2b. the slots' palette banks (Task 10): the frame's 4 slots' SCB1
        # rows carry bank RADAR_PAL_BANK; every shown stick and heading slot
        # carries RADAR_STICK_PAL_BANK. Hidden radar slots are not checked
        # (their SCB1 is stale by design).
        for c in range(FRAME_SLOTS):
            slot = RADAR0 + c
            st = s["slots"].get(slot)
            if st is not None:
                # the frame's SCB1 rows 0 and 1 (2 tiles tall) both carry
                # RADAR_PAL_BANK; T's attr/tile0/attr_row1 are those rows
                if (st[0] >> 8) != RADAR_PAL_BANK or (st[5] >> 8) != RADAR_PAL_BANK:
                    frame_pal_bad += 1
                    if frame_pal_bad <= 5:
                        failures.append(
                            f"frame {fc} frame slot {c}: SCB1 palettes "
                            f"{st[0] >> 8}/{st[5] >> 8}, want {RADAR_PAL_BANK}")
        for k in range(NMIS):
            b = s["prev_blips"][k]
            if b is None or not b[0]:
                continue
            stick_slot = RADAR0 + FRAME_SLOTS + k * 5
            # the shown stick is 3 tiles tall and the shown heading 1: every
            # SCB1 row each one's picture uses carries bank 21 (the probe's K
            # line has all 32; row attributes aren't dumped, but attr_row2
            # is the stick's third row and attr/tile0 the firsts)
            for slot, what, rows in ((stick_slot, "stick", 3),
                                     (stick_slot + 1, "heading", 1)):
                st = s["slots"].get(slot)
                col = s["columns"].get(slot)
                if st is None:
                    continue
                # the attribute of every row 0..rows-1 is identical (the
                # runtime writes `PAL << 8`), so row 0's palette is the one
                # for the picture's rows; row 2's attr is dumped for sticks
                if rows == 3 and (st[6] >> 8) != RADAR_STICK_PAL_BANK:
                    stick_pal_bad += 1
                    if stick_pal_bad <= 5:
                        failures.append(
                            f"frame {fc} blip {k} {what} slot {slot}: row-2 "
                            f"SCB1 palette {st[6] >> 8}, want "
                            f"{RADAR_STICK_PAL_BANK}")
                if (st[0] >> 8) != RADAR_STICK_PAL_BANK:
                    stick_pal_bad += 1
                    if stick_pal_bad <= 5:
                        failures.append(
                            f"frame {fc} blip {k} {what} slot {slot}: SCB1 "
                            f"palette {st[0] >> 8}, want {RADAR_STICK_PAL_BANK}")
        # 6. the frame picture's 4 slots keep the SCB3 radar_gfx_init wrote
        # (y CY-16, height 2) on every game frame: nothing else rewrites
        # them, so a title hide that zeroed them left the radar without its
        # frame for the whole game (M6 Task 1)
        if s["census"]:
            for c in range(FRAME_SLOTS):
                scb3 = s["census"][RADAR0 + c][0]
                if scb3 != FRAME_SCB3:
                    frame_bad += 1
                    if frame_bad <= 5:
                        failures.append(f"frame {fc}: radar frame slot {c} "
                                        f"SCB3 {scb3:#06x}, want {FRAME_SCB3:#06x}")
        # 5. the busiest radar row (from this frame's census)
        if s["census"]:
            cnt = _radar_region_count(s["census"])
            if cnt > busiest[0]:
                busiest = (cnt, fc)
        i += 1

    if radar_bad:
        failures.append(f"{radar_bad} radar_t mismatches vs the model")
    if blip_bad:
        failures.append(f"{blip_bad} blip shown/locked mismatches vs the model")
    if stick_bad:
        failures.append(f"{stick_bad} stick slot mismatches")
    if head_bad:
        failures.append(f"{head_bad} heading slot mismatches")
    if hidden_bad:
        failures.append(f"{hidden_bad} hidden blip SCB3 mismatches")
    if pal_bad:
        failures.append(f"{pal_bad} bank 20 / blink mismatches")
    if prev_radar_bad:
        failures.append(f"{prev_radar_bad} previous-frame blink/bright "
                        "mismatches")
    if stickpal_bad:
        failures.append(f"{stickpal_bad} bank 21 (radar_stick_pal) mismatches")
    if frame_pal_bad:
        failures.append(f"{frame_pal_bad} frame slot SCB1 palette mismatches")
    if stick_pal_bad:
        failures.append(f"{stick_pal_bad} stick/heading SCB1 palette mismatches")
    if frame_bad:
        failures.append(f"{frame_bad} radar frame slot SCB3 mismatches")
    if n_locked < MIN_LOCKED:
        failures.append(f"only {n_locked} sampled frames locked, want >= "
                        f"{MIN_LOCKED}")

    snap_fc = None
    for line in open(probe):
        p = line.split()
        if p and p[0] == "SNAP":
            snap_fc = int(p[1])
    if snap_fc is None:
        failures.append("the probe never snapshotted")
    else:
        rr = samples.get(snap_fc, {}).get("radar")
        if rr is not None and rr[1] != 1:
            failures.append(f"SNAP frame {snap_fc}: radar.locked {rr[1]}, want 1")
        # Task 10 proof 3: the box's pixels and a shown stick's colour
        compared, matched, opaque, stick_px = check_snapshot_pixels(
            snap_png, snap_fc, samples, snap_fix, failures)
        snap_proof = (f"snapshot {snap_fc}: {matched}/{compared} uncovered "
                      f"picture px of {opaque} opaque match neo_rgb "
                      f"({100.0 * matched / max(1, compared):.1f}%), a shown "
                      f"stick's {stick_px} lit px are radar_stick_pal[1]")

    if failures:
        print("FAIL radar:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS radar: {len(samples)} samples, {n_locked} locked, "
          f"ellipse palette == the model's bright state, stick/heading "
          f"slots within {TOL} px, hidden blips SCB3 0, busiest radar row "
          f"{busiest[0]} sprites (fc {busiest[1]}); {snap_proof}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
