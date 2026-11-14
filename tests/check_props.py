#!/usr/bin/env python3
"""Assertions for the dome-scenery Task 12/13/14/15 props boot-test.

  check_props.py SNAP PROBE

scripts/props_probe.lua boots the normal cart, plays the centred game (the
same deterministic policy as the console/ground legs) after walking the ship
to the peak and spinning the dome left through the whole turn and back right,
snapshotting the title (fc 0), an early whole-dome play frame (fc 30, before
the first missile), a spin frame where prop 21 is dark (da 90) and a spin
frame where prop 14 is in the FRONT pool (da 189, the ship at the peak). It
dumps, from MAME's own VRAM: both pools' every slot's SCB1 rows 0..4 (tile
and attr), SCB2, SCB3 and SCB4; every prop's palette bank; the ground's
bank; every slot's SCB3/SCB4 for the pixel proof; the slots ABOVE the
snapshot's pool with their tile rows (so the checker can tell a prop pixel a
higher sprite really covers); the fix rows 0..29; and the frame's
ship.dome_angle.

Task 13/14/15 samples: on every play frame whose dome_angle differs from the
previous sampled frame, on every change of the ground's bank (whole ->
not whole at the collapse, and back at the respawn) and every 10 frames while
the dome is not whole, the probe dumps both pools' every slot's SCB1 rows
0..PROP_MAX_ROWS-1 (5), SCB2, SCB3 and SCB4, every shown prop's WHOLE
16-word palette bank and the ground bank (PAL_GROUND 8). This checker:

  1. compares every sampled frame's slot words with tests/props_model.py at
     the PREVIOUS play frame's dome angle (Task 18's one-frame lag: the words
     read at frame N's end were prepared during N-1 and committed at N's
     vblank), pool for pool and slot for slot: every shown slot's SCB1 row
     tile+attr, SCB2, SCB3 and SCB4; unused slots' SCB3 must be 0 (their
     SCB1/SCB2/SCB4 keep the last picture by design — a stopped slot is only
     cleared in SCB3). It proves at least 120 distinct angles were reached
     both ways and states the frames and angles where the front pool is in
     use (at least 20 of da 174..203);
  2. Task 14, whole dome: on every sampled frame whose PREVIOUS frame was
     whole, each shown prop's whole bank equals tests/props_model.py's
     variant for (prev da, whole = 1): prop_pal[i][1] when prop_dark[i][da],
     else [0], with entries 1 and 13 from prop_shadow[1 or 0][foot row]. It
     states the frames, how many had a dark prop (at least 20, including prop
     21 at da 81..108), the banks compared and the mismatches (0);
  3. Task 14, dome not whole: on every sampled frame whose previous frame was
     not whole, every shown prop's bank is variant 0 — even where
     prop_dark[i][da] is 1. It states the frames, one with a shown dark prop,
     the banks compared and the mismatches (0);
  4. at PLAY, compares both pools' slots as above and every shown prop's
     bank against tests/props_model.py's variant for (prev da, prev whole),
     with entries 1 and 13 from prop_shadow[variant][foot row y] (clamped to
     0..223). It proves the frame shows at least 6 props and that the back
     pool is under the dome;
  5. at PLAY, compares every BACK-pool prop pixel that no higher sprite or
     fix tile covers with neo_rgb of the model's (variant) palette. State the count
     (at least 90% of the prop pixels not covered by a higher sprite) and
     the mismatches (0);
  6. Task 14, DARK: the snapshot is triggered at da 90; at its previous
     frame's angle prop 21 is shown and dark. Its uncovered pixels must show
     neo_rgb of prop_pal[21][1] (and of prop_shadow[1][y] for entries 1 and
     13). State the count (at least 50) and the mismatches (0);
  7. at FRONT, the snapshot is triggered at da 189; the pixels over the dome
     use prop 14's previous-frame layout: of its own pixels that land on the
     dome on screen (the generator's dome mask) and that no higher sprite or
     fix tile covers, every snapshot pixel is prop 14's expected colour.
     State the count (at least 30) and the mismatches (0). It also proves the
     ship's own pixels in that frame are the ship's;
  8. the title (fc 0): both pools' slots equal tests/props_model.py's layout
     for the fresh game's start-cell angle (attract Task A2: the props are
     drawn under the title), and at least 6 props are shown;
  9. the sprites-per-scanline census over the leg's run: the worst count on
     any scanline, recounted from the probe's raw worst dump, at or under the
     hardware's 96.

The art is the orchestrator's: this checker re-runs the committed generator
through tests/props_model.py rather than carrying a copy of its numbers.
"""
import json
import os
import re
import sys

import numpy as np
from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import neo_palette as npal     # noqa: E402  (MAME's 15-bit -> RGB pipeline)
import props_model as pm       # noqa: E402  (Task 11/15's model, not the C)
import render_props as rp      # noqa: E402  (the committed art generator)
import render_radar as rr      # noqa: E402  (the hardware's zoom tables:
                               # ZOOM_X_COLS and _ZOOM_Y, decoded from the
                               # AES BIOS's 000-lo.lo in the radar tests)
import ship_model as sm        # noqa: E402  (cell_step[CELL_START], the
                               # angle props_show draws before game frame 1)

SCREEN_W, SCREEN_H = rp.SCREEN_W, rp.SCREEN_H
START_DA = sm.STEP[sm.FIX["cell_start"]]  # game_begin's props_show angle
SCAN_MAX = 96
PROP_PAL_BANK = 22             # src/props.h
PROP_MAX_ROWS = 5              # src/props.h: the largest picture's rows
DARK_DA = 90                   # scripts/props_probe.lua's DARK snapshot
FRONT_DA = 189                 # scripts/props_probe.lua's FRONT snapshot
PAL_GROUND = 8                 # src/ground.h
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))
PROP_BACK0 = _SLOTS["PROP_SPRITE"]
PROP_BACK_COUNT = _SLOTS["PROP_BACK_COUNT"]
PROP_FRONT0 = _SLOTS["PROP_FRONT_SPRITE"]
PROP_FRONT_COUNT = _SLOTS["PROP_FRONT_COUNT"]
POOL0 = ((0, PROP_BACK0, PROP_BACK_COUNT),
         (1, PROP_FRONT0, PROP_FRONT_COUNT))
BACK_END = PROP_BACK0 + PROP_BACK_COUNT - 1
FRONT_END = PROP_FRONT0 + PROP_FRONT_COUNT - 1
SHIP_FIRST = _SLOTS["SHIP_SPRITE"]
SHIP_LAST = SHIP_FIRST + _SLOTS["SHIP_COUNT"] - 1
DOME_FIRST = _SLOTS["DOME_SPRITE"]
BROKEN_AFTER = _SLOTS["BROKEN_SLOT_AFTER"]


def _defines(path):
    """evaluate a generated header's #defines in order (a plain number, or an
    expression over the names defined before it)."""
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


def _ground_words():
    """the generated build/ground_map.h's two ground banks (PAL_GROUND 8):
    ground_pal while the dome is whole, ground_pal_noshadow otherwise. Task
    14's "not whole" is read from this bank, the same way src/ground.c
    switches it."""
    txt = open(os.path.join(ROOT, "build", "ground_map.h")).read()
    out = {}
    for name in ("ground_pal", "ground_pal_noshadow"):
        m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name,
                      txt, re.S)
        assert m, name
        out[name] = [int(x, 16) for x in
                     re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
        assert len(out[name]) == 16, name
    return out["ground_pal"], out["ground_pal_noshadow"]


GROUND_PAL, GROUND_NOSHADOW = _ground_words()
assert GROUND_PAL != GROUND_NOSHADOW, "the two ground banks must differ"


def ground_state(words):
    """1 = ground_pal (the dome is whole), 0 = ground_pal_noshadow (not
    whole), None = neither (a cart that wrote some other bank)."""
    if words == GROUND_PAL:
        return 1
    if words == GROUND_NOSHADOW:
        return 0
    return None


def prev_da(fc, frame_da):
    """the angle props_prepare used on frame fc's PREVIOUS play frame: the
    words read at the end of fc were prepared at fc-1 and committed at fc's
    vblank (Task 18's one-frame lag). Frame 1's words come from game_begin's
    props_show, which drew the reset cell's angle."""
    if fc - 1 in frame_da:
        return frame_da[fc - 1]
    return START_DA


def prev_whole(fc, frame_state):
    """the dome whole/gone state of frame fc-1 (same lag); game_begin shows
    the props with the dome whole."""
    if fc - 1 in frame_state and frame_state[fc - 1] >= 0:
        return frame_state[fc - 1]
    return 1


def crom_tile_base():
    """the props part's first tile in the assembled C ROM: the radar's
    headings + the ground's + the mountains' + the console's tiles (the
    Makefile's CROM1_PARTS order; src/props.h's PROP_TILE_BASE)."""
    radar = _defines(os.path.join(ROOT, "build", "radar_map.h"))
    ground = _defines(os.path.join(ROOT, "build", "ground_map.h"))
    mtn = _defines(os.path.join(ROOT, "build", "mountain_map.h"))
    con = _defines(os.path.join(ROOT, "build", "console_map.h"))
    return (radar["RADAR_HEAD_TILE_BASE"] + radar["RADAR_HEAD_TILES"]
            + ground["GROUND_TILES"] + mtn["MTN_TILES"] + con["CON_TILES"])


def parse(fname):
    """(snaps, da, banks, props, slots, upper, fix, census, worst, angles,
    pals, frame_da, frame_state) from the probe dump.

    props: {tag: {pool: {k: {scb2, scb3, scb4, words}}}} — both pools.
    angles: {fc: {"da": int, "ground": [16 words],
                  "slots": {pool: {k: {...}}}, "banks": {prop: [16
                  words]}}} — the Task 13/14/15 frames.
    pals: {tag: [16 words]} — each snapshot's ground bank (PAL_GROUND 8).
    frame_da / frame_state: {fc: int} for EVERY play frame (the probe's a/h
    records), so a frame's words can be compared with frame fc-1's prepared
    angle and whole state (Task 18's one-frame lag)."""
    snaps, da, banks, props, slots, upper, fix, census, angles, pals = \
        {}, {}, {}, {}, {}, {}, {}, [], {}, {}
    frame_da, frame_state = {}, {}
    worst = None
    with open(fname, encoding="latin-1") as fh:
        for line in fh:
            raw = line.rstrip("\n")
            p = raw.split()
            if not p:
                continue
            if p[0] == "SNAP":
                snaps[p[1]] = (int(p[2]), int(p[3]))
            elif p[0] == "D":
                da[p[1]] = int(p[3])
            elif p[0] == "B":
                banks.setdefault(p[1], {})[int(p[2])] = [
                    int(x, 16) for x in p[3:19]]
            elif p[0] == "P":
                rows = (len(p) - 7) // 2
                words = [(int(p[7 + 2 * r], 16), int(p[8 + 2 * r], 16))
                         for r in range(rows)]
                props.setdefault(p[1], {}).setdefault(int(p[2]), {})[
                    int(p[3])] = {
                        "scb2": int(p[4], 16), "scb3": int(p[5], 16),
                        "scb4": int(p[6], 16), "words": words}
            elif p[0] == "A":
                angles.setdefault(int(p[1]), {"da": int(p[2]),
                                              "slots": {}, "banks": {}})
            elif p[0] == "p":
                rows = (len(p) - 7) // 2
                words = [(int(p[7 + 2 * r], 16), int(p[8 + 2 * r], 16))
                         for r in range(rows)]
                angles.setdefault(int(p[1]), {"da": -1,
                                              "slots": {}, "banks": {}})
                angles[int(p[1])]["slots"].setdefault(int(p[2]), {})[
                    int(p[3])] = {
                        "scb2": int(p[4], 16), "scb3": int(p[5], 16),
                        "scb4": int(p[6], 16), "words": words}
            elif p[0] == "b":
                angles.setdefault(int(p[1]), {"da": -1, "slots": {},
                                              "banks": {}})
                angles[int(p[1])]["banks"][int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
            elif p[0] == "q":
                angles.setdefault(int(p[1]), {"da": -1, "slots": {},
                                              "banks": {}})
                angles[int(p[1])]["banks"][int(p[2])] = [
                    int(x, 16) for x in p[3:19]]
            elif p[0] == "g":
                angles.setdefault(int(p[1]), {"da": -1, "slots": {},
                                              "banks": {}})
                angles[int(p[1])]["ground"] = [
                    int(x, 16) for x in p[2:18]]
            elif p[0] == "a":
                frame_da[int(p[1])] = int(p[2])
            elif p[0] == "h":
                frame_state[int(p[1])] = int(p[2])
            elif p[0] == "PAL":
                pals[p[1]] = [int(x, 16) for x in p[2:18]]
            elif p[0] == "X":
                slots.setdefault(p[1], {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
            elif p[0] == "U":
                upper.setdefault(p[1], []).append({
                    "slot": int(p[2]), "x": int(p[3]), "y": int(p[4]),
                    "h": int(p[5]), "tiles": [int(x, 16) for x in p[6:]]})
            elif p[0] == "F":
                parts = raw.split(" ", 3)
                fix.setdefault(parts[1], {})[int(parts[2])] = parts[3]
            elif p[0] == "CEN":
                census.append((int(p[1]), int(p[2]), int(p[3])))
            elif p[0] == "W":
                worst = (int(p[1]), int(p[2]), int(p[3]), {})
            elif p[0] == "w" and worst is not None:
                worst[3][int(p[1])] = int(p[2], 16)
    return (snaps, da, banks, props, slots, upper, fix, census, worst,
            angles, pals, frame_da, frame_state)


def snap_pngs(snap_png):
    """the MAME-managed snapshot directory's PNGs in order."""
    snap_dir = os.path.join(os.path.dirname(os.path.abspath(snap_png)), "snap")
    if not os.path.isdir(snap_dir):
        return [snap_png]
    pngs = sorted(os.path.join(r, fn) for r, _, fs in os.walk(snap_dir)
                  for fn in fs if fn.endswith(".png"))
    return pngs or [snap_png]


def _at(im, x, y):
    w, h = im.size
    return tuple(im.getpixel((int(x * w / SCREEN_W), int(y * h / SCREEN_H)))[:3])


_ROM = {}


def _rom_files():
    if not _ROM:
        rom = os.path.join(ROOT, "build", "rom")
        _ROM["c1"] = open(os.path.join(rom, "esrg-c1.c1"), "rb").read()
        _ROM["c2"] = open(os.path.join(rom, "esrg-c2.c2"), "rb").read()
        _ROM["s1"] = open(os.path.join(rom, "esrg-s1.s1"), "rb").read()
    return _ROM


def decode_tile(tile):
    c1, c2 = _rom_files()["c1"], _rom_files()["c2"]
    p1 = c1[tile * 64:(tile + 1) * 64]
    p2 = c2[tile * 64:(tile + 1) * 64]
    out = np.zeros((16, 16), np.uint8)
    for i, off in enumerate((8, 136, 0, 128)):
        sy, sx = off // 16, off % 16
        for yy in range(8):
            b0 = p1[2 * (8 * i + yy)]
            b1 = p1[2 * (8 * i + yy) + 1]
            b2 = p2[2 * (8 * i + yy)]
            b3 = p2[2 * (8 * i + yy) + 1]
            for xx in range(8):
                out[sy + yy][sx + xx] = (b0 >> xx & 1) | ((b1 >> xx & 1) << 1) \
                    | ((b2 >> xx & 1) << 2) | ((b3 >> xx & 1) << 3)
    return out


def srom_tile(tile):
    s1 = _rom_files()["s1"]
    raw = s1[tile * 32:(tile + 1) * 32]
    out = np.zeros((8, 8), np.uint8)
    i = 0
    for xa, xb in ((4, 5), (6, 7), (0, 1), (2, 3)):
        for yy in range(8):
            b = raw[i]
            i += 1
            out[yy][xa] = b & 0xf
            out[yy][xb] = (b >> 4) & 0xf
    return out


def upper_opacity_mask(upper):
    """(224, 320) bool: does a slot above the props draw a non-transparent
    pixel at screen (x, y)? The probe resolved each slot's box (sticky
    chains included) and dumped its tile rows; each row's 16x16 tile is
    decoded from the assembled C ROM and pasted at y + row*16, x, clipped to
    the screen."""
    mask = np.zeros((SCREEN_H, SCREEN_W), bool)
    for u in upper:
        x, y, h = u["x"], u["y"], u["h"]
        for r, tile in enumerate(u["tiles"][:h]):
            idx = decode_tile(tile)
            sy, sx = y + r * 16, x
            if sy >= SCREEN_H or sy + 16 <= 0 or sx >= SCREEN_W or sx + 16 <= 0:
                continue
            y0, y1 = max(0, sy), min(SCREEN_H, sy + 16)
            x0, x1 = max(0, sx), min(SCREEN_W, sx + 16)
            mask[y0:y1, x0:x1] |= idx[y0 - sy:y1 - sy,
                                      x0 - sx:x1 - sx] != 0
    return mask


def fix_opacity_mask(fix_rows):
    """(224, 320) bool: does the fix layer draw a lit pixel at screen
    (x, y)? Fix row r is at y 8r-16..8r-9 and col c at x 8c..8c+7."""
    mask = np.zeros((SCREEN_H, SCREEN_W), bool)
    for r, srow in fix_rows.items():
        y0 = 8 * r - 16
        for c in range(min(40, len(srow))):
            idx = srom_tile(ord(srow[c]))
            if not idx.any():
                continue
            y1 = min(SCREEN_H, y0 + 8)
            x1 = min(SCREEN_W, c * 8 + 8)
            if y0 >= SCREEN_H or c * 8 >= SCREEN_W:
                continue
            mask[max(0, y0):y1, c * 8:x1] |= idx[max(0, y0) - y0:
                                                 y1 - y0, :x1 - c * 8] != 0
    return mask


def props_picture(da, pool=None, whole=1, only=None):
    """(RGB image, drawn mask) of the props at da with the Task 14 palette
    variants: each shown prop uses pm.bank(i, da, whole), i.e. variant 1
    when whole and prop_dark, else 0, with entries 1/13 from
    prop_shadow[variant][foot row]. `pool` picks the back (0) or front (1)
    pool, None = both (back first); `only` keeps one prop index. Same
    hardware-zoom decode as neo_palette.props_picture."""
    pics = pm.rp.pictures()
    frame = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
    drawn = np.zeros((SCREEN_H, SCREEN_W), bool)
    back, front = pm.layout(da)
    slots = [s for p in ((back,) if pool == 0 else
                         (front,) if pool == 1 else (back, front))
             for s in p]
    luts = {}
    for slot in slots:
        if not slot[0] or (only is not None and slot[1] != only):
            continue
        _shown, i, lod, _col, scb2, _scb3, _scb4, _tile = slot
        se = pm.SE[i][da]
        hz = (scb2 >> 8) & 0x0f
        v = scb2 & 0xff
        pic, cols, rows, ax, ay = pics[(pm.KIND[i], pm.SHAPE[i], lod)]
        left = pm.X[i][da] - int(round(ax * se / pm.LODS[lod]))
        top = pm.Y[i][da] - int(round(ay * se / pm.LODS[lod]))
        if i not in luts:
            luts[i] = np.array([npal.neo_rgb(w) for w in
                                pm.bank(i, da, whole)], np.uint8)
        lut = luts[i]
        for line in range(rows * 16):
            b = rr._ZOOM_Y[(v << 8) | (line & 0xff)]
            row, artrow = b >> 4, b & 0x0f
            if row >= rows:
                continue
            sy = top + line
            if sy < 0 or sy >= SCREEN_H:
                continue
            for col in range(cols):
                for j, artcol in enumerate(rr.ZOOM_X_COLS[hz]):
                    idx = int(pic[row * 16 + artrow][col * 16 + artcol])
                    if not idx:
                        continue
                    sx = left + col * (hz + 1) + j
                    if sx < 0 or sx >= SCREEN_W:
                        continue
                    frame[sy, sx] = lut[idx]
                    drawn[sy, sx] = True
    return frame, drawn


def expected_slot_words(m, tile_base):
    """a model slot's SCB1 rows 0..PROP_MAX_ROWS-1: the picture's rows in the
    prop's bank, every row below the picture blank tile 0 with the same
    attribute (src/props.c's write_tiles)."""
    _shown, prop, lod, _col, _scb2, _scb3, _scb4, tile = m
    rows = pm.PICS_HEADER[(pm.KIND[prop], pm.SHAPE[prop], lod)][1]
    attr = (PROP_PAL_BANK + prop) << 8
    out = []
    for r in range(PROP_MAX_ROWS):
        if r < rows:
            out.append((tile_base + tile + r, attr))
        else:
            out.append((0, attr))
    return out


def compare_pool(fr_slots, model, label, tile_base, failures, detail_ref):
    """compare one pool's probe slots with the model's; returns
    (compared, bad) and appends the first few mismatches."""
    bad = 0
    compared = 0
    if fr_slots is None or len(fr_slots) != len(model):
        failures.append(f"{label}: {0 if fr_slots is None else len(fr_slots)} "
                        f"slots read, want {len(model)}")
        return 0, 1
    detail = detail_ref[0]
    for k, m in enumerate(model):
        got = fr_slots[k]
        if not m[0]:
            if got["scb3"] != 0:
                if detail < 12:
                    failures.append(f"{label} slot {k}: unused in the model "
                                    f"but SCB3 {got['scb3']:#06x} draws")
                    detail += 1
                bad += 1
            continue
        _shown, prop, lod, col, scb2, scb3, scb4, tile = m
        compared += 1
        for name, want in (("scb2", scb2), ("scb3", scb3),
                           ("scb4", scb4)):
            if got[name] != want:
                if detail < 12:
                    failures.append(
                        f"{label} slot {k} (prop {prop}, lod {lod}, col "
                        f"{col}): {name.upper()} {got[name]:#06x}, want "
                        f"{want:#06x}")
                    detail += 1
                bad += 1
        want_words = expected_slot_words(m, tile_base)
        if got["words"] != want_words:
            if detail < 12:
                failures.append(
                    f"{label} slot {k} (prop {prop}, lod {lod}, col {col}): "
                    f"SCB1 {got['words']}, want {want_words}")
                detail += 1
            bad += 1
    detail_ref[0] = detail
    return compared, bad


def check_angles(angles, frame_da, frame_state, tile_base, failures):
    """Task 13/14/15 proofs 1-2, with Task 18's one-frame lag.

    The probe samples on every play frame whose dome_angle changed (through
    the left spin 0..239 and back right 239..0, plus the climb), on every
    change of the ground's bank, and every 10 frames while the dome is not
    whole. The words read at the end of frame fc were prepared during fc-1
    and committed at fc's vblank, so each A record's slots are compared with
    the model at the PREVIOUS play frame's angle and whole state (frame 1's
    words come from game_begin's props_show). For each frame compare both
    pools' shown slots (SCB1 rows 0..4, SCB2, SCB3, SCB4; unused slots must
    have SCB3 0), and each shown prop's whole 16-word bank against the
    model's variant at that previous state: variant 1 when whole and
    prop_dark, else 0, entries 1/13 from prop_shadow[variant][foot row].

    Proof 1 (whole dome): state the frames, how many had a dark prop (at
    least 20, including prop 21 at da 81..108), the banks compared and the
    mismatches (0). Proof 2 (not whole): state the frames, one with a shown
    dark prop, the banks compared and the mismatches (0).
    """
    frames = sorted(angles)
    if not frames:
        failures.append("the probe wrote no angle frames (A records): the "
                        "props were never checked over the turn")
        return
    cache = {}
    distinct = set()
    bad = 0
    compared_slots = 0
    front_frames = []
    detail_ref = [0]

    whole_frames = []
    whole_dark_frames = []
    dark21_angles = set()
    whole_banks = 0
    whole_bank_bad = 0
    not_whole_frames = []
    not_whole_dark_frames = []
    not_whole_banks = 0
    not_whole_bank_bad = 0

    for fc in frames:
        fr = angles[fc]
        cur_d = fr["da"]
        # Task 18: the words read at fc's end are fc-1's prepared layout.
        d = prev_da(fc, frame_da)
        whole = prev_whole(fc, frame_state)
        if d not in cache:
            cache[d] = pm.layout(d)
        model_back, model_front = cache[d]
        distinct.add(cur_d)
        if sorted(fr["slots"]) != [0, 1]:
            failures.append(f"angle frame fc {fc} (da {cur_d}, prev {d}): "
                            f"pools {sorted(fr['slots'])} read, want both 0 "
                            "and 1")
            bad += 1
            continue
        g = fr.get("ground")
        if g is None:
            failures.append(f"angle frame fc {fc} (da {cur_d}, prev {d}): no "
                            "ground bank (g) record; the whole/not-whole "
                            "state is unproved")
            bad += 1
            continue
        cur_whole = ground_state(g)
        if cur_whole is None:
            failures.append(f"angle frame fc {fc} (da {cur_d}, prev {d}): the "
                            "ground bank is neither ground_pal nor "
                            "ground_pal_noshadow")
            bad += 1
            continue

        shown_props = set()
        for pool, model in ((0, model_back), (1, model_front)):
            name = "back" if pool == 0 else "front"
            compared, nbad = compare_pool(
                fr["slots"].get(pool), model,
                f"angle frame fc {fc} (prev da {d}, prev whole {whole}) "
                f"{name}", tile_base, failures, detail_ref)
            compared_slots += compared
            bad += nbad
            if pool == 1 and any(s[0] for s in model):
                front_frames.append(fc)
        for m in model_back + model_front:
            if m[0]:
                shown_props.add(m[1])

        if whole:
            whole_frames.append(fc)
            if any(pm.variant(i, d, 1) for i in shown_props):
                whole_dark_frames.append(fc)
            if 21 in shown_props and pm.variant(21, d, 1):
                dark21_angles.add(d)
        else:
            not_whole_frames.append(fc)
            if any(pm.SE[i][d] and pm.DARK[i][d] for i in shown_props):
                not_whole_dark_frames.append(fc)

        for prop in sorted(shown_props):
            want = pm.bank(prop, d, whole)
            got = fr["banks"].get(prop)
            if whole:
                whole_banks += 1
            else:
                not_whole_banks += 1
            if got != want:
                if detail_ref[0] < 12:
                    failures.append(
                        f"angle frame fc {fc} (prev da {d}, prev whole "
                        f"{whole}) prop {prop}: bank {got}, want variant "
                        f"{pm.variant(prop, d, whole)} {want}")
                    detail_ref[0] += 1
                if whole:
                    whole_bank_bad += 1
                else:
                    not_whole_bank_bad += 1

    # the turn's two directions: the left spin's frames up to the first
    # da 239, and the right spin's frames from after it down to the next
    # da 0. The climb is part of the left set; the later game frames (after
    # the turn) are not part of the "both ways" count.
    seq = [(fc, angles[fc]["da"]) for fc in frames]
    idx239 = next((i for i, (_fc, d) in enumerate(seq) if d == 239), None)
    left, right = set(), set()
    if idx239 is None:
        failures.append("the probe never sampled da 239: the left spin did "
                        "not go through the whole turn")
    else:
        left = set(d for _fc, d in seq[:idx239 + 1])
        idx0 = next((i for i in range(idx239 + 1, len(seq))
                     if seq[i][1] == 0), None)
        if idx0 is None:
            failures.append("the probe never sampled da 0 after da 239: the "
                            "right spin did not come back")
            right = set(d for _fc, d in seq[idx239 + 1:])
        else:
            right = set(d for _fc, d in seq[idx239 + 1:idx0 + 1])
        both = left & right
        print(f"angle frames: {len(frames)} sampled frames (fc "
              f"{frames[0]}..{frames[-1]}), {len(distinct)} distinct angles "
              f"(da {min(distinct)}..{max(distinct)})")
        print(f"  left spin: {len(left)} angles (da {min(left)}..{max(left)}); "
              f"right spin: {len(right)} angles (da {min(right)}.."
              f"{max(right)}); reached both ways: {len(both)}")
        front_angles = sorted(set(prev_da(fc, frame_da)
                                  for fc in front_frames))
        front_left = sorted(d for d in front_angles if d in left)
        front_right = sorted(d for d in front_angles if d in right)
        print(f"  front pool in use: {len(front_frames)} frames, "
              f"{len(front_angles)} angles "
              f"(da {front_angles[0]}..{front_angles[-1]})" if front_angles
              else "  front pool in use: 0 frames")
        if front_angles:
            print(f"    frames fc {front_frames[0]}..{front_frames[-1]}; "
                  f"left {len(front_left)} angles "
                  f"(da {front_left[0]}..{front_left[-1]}), right "
                  f"{len(front_right)} angles "
                  f"(da {front_right[0]}..{front_right[-1]})"
                  if front_left and front_right else "")
            in_range = set(front_angles) & set(range(174, 204))
            if len(in_range) < 20:
                failures.append(f"the front pool is used at only "
                                f"{len(in_range)} of da 174..203 (need at "
                                "least 20)")
        print(f"  {compared_slots} shown prop slots compared (at each "
              f"frame's previous angle/state): {bad} slot-word mismatches")
        print(f"  whole-dome frames by the previous frame's state: "
              f"{len(whole_frames)}" + (f" (fc {whole_frames[0]}.."
              f"{whole_frames[-1]})" if whole_frames else "")
              + f"; not whole: {len(not_whole_frames)}"
              + (f" (fc {not_whole_frames[0]}.."
                 f"{not_whole_frames[-1]})" if not_whole_frames else ""))
        print(f"    with a dark prop: {len(whole_dark_frames)} frames; "
              f"prop 21 dark at da {min(dark21_angles)}.."
              f"{max(dark21_angles)} ({len(dark21_angles)} angles); "
              f"{whole_banks} banks compared, {whole_bank_bad} mismatches"
              if dark21_angles else
              f"    with a dark prop: {len(whole_dark_frames)} frames; "
              f"prop 21 never dark; {whole_banks} banks compared, "
              f"{whole_bank_bad} mismatches")
        print(f"  not-whole-dome frames: {len(not_whole_frames)}"
              + (f" (fc {not_whole_frames[0]}.."
                 f"{not_whole_frames[-1]})" if not_whole_frames else "")
              + f"; with a shown prop prop_dark=1: "
              f"{len(not_whole_dark_frames)}"
              + (f" (fc {not_whole_dark_frames[0]}.."
                 f"{not_whole_dark_frames[-1]})"
                 if not_whole_dark_frames else "")
              + f"; {not_whole_banks} banks compared, "
              f"{not_whole_bank_bad} mismatches")
        if left != set(range(240)):
            failures.append(f"the left spin did not sample every angle 0..239 "
                            f"({len(left)} sampled)")
        if right != set(range(239)):
            failures.append(f"the right spin did not sample every angle "
                            f"239..0 ({len(right)} sampled)")
        if len(both) < 120:
            failures.append(f"only {len(both)} distinct angles were reached "
                            "both ways (need at least 120)")
        if len(whole_dark_frames) < 20:
            failures.append(f"only {len(whole_dark_frames)} whole-dome "
                            "frames had a dark prop (need at least 20)")
        missing21 = set(range(81, 109)) - dark21_angles
        if missing21:
            failures.append(f"prop 21 was not sampled dark at da "
                            f"{sorted(missing21)[:4]}.. (need all 81..108)")
        if not not_whole_frames:
            failures.append("the probe sampled no frame with the dome not "
                            "whole (ground_pal_noshadow): the collapse was "
                            "not covered")
        if not not_whole_dark_frames:
            failures.append("no not-whole frame had a shown prop with "
                            "prop_dark=1: the dark-vs-not-whole proof was not "
                            "exercised (da 0 has prop 14 dark)")
    if bad:
        failures.append(f"the angle frames' prop slots: {bad} mismatches")
    if whole_bank_bad:
        failures.append(f"the whole-dome frames' shown props' banks: "
                        f"{whole_bank_bad} mismatches")
    if not_whole_bank_bad:
        failures.append(f"the not-whole frames' shown props' banks: "
                        f"{not_whole_bank_bad} mismatches")


def check_dark(snaps, da, banks, props, upper, fix, pals, imgs, tile_base,
               frame_da, frame_state, failures):
    """Task 14 proof 3, with Task 18's one-frame lag: the DARK snapshot is
    triggered at da 90; the words and pixels it contains were prepared at
    the previous play frame's angle/state. At that angle prop 21 is dark and
    shown; its uncovered pixels show neo_rgb of prop_pal[21][1] (entries 1
    and 13 from prop_shadow[1][y]). State the count (at least 50) and the
    mismatches (0)."""
    tag = "DARK"
    if tag not in snaps:
        return
    fc = snaps[tag][1]
    cur_d = da.get(tag, -1)
    if cur_d != DARK_DA:
        failures.append(f"the DARK snapshot is at da {cur_d}, not DARK_DA "
                        f"{DARK_DA}")
        return
    d = prev_da(fc, frame_da)
    whole = prev_whole(fc, frame_state)
    if not pm.SE[21][d] or not pm.DARK[21][d]:
        failures.append(f"at the previous frame's da {d} prop 21 is not "
                        f"shown and dark (se {pm.SE[21][d]}, "
                        f"dark {pm.DARK[21][d]})")
        return
    g = pals.get(tag)
    if g is None:
        failures.append("the DARK snapshot wrote no ground PAL record")
        return
    if ground_state(g) != 1:
        failures.append(f"the DARK snapshot's ground bank is not ground_pal "
                        f"({g}); the dome should be whole there")

    # the snapshot's whole banks: prop 21 must be variant 1 at prev da
    want = pm.bank(21, d, whole)
    got = banks.get(tag, {}).get(21)
    y = max(0, min(SCREEN_H - 1, pm.Y[21][d]))
    if got != want:
        failures.append(f"DARK prop 21's bank {got} != prop_pal[21]"
                        f"[{pm.variant(21, d, whole)}] with "
                        f"prop_shadow[{pm.variant(21, d, whole)}][{y}] "
                        f"{want}")

    # and the snapshot's slot words as well (the previous frame's state)
    model_back, model_front = pm.layout(d)
    compared = bad = 0
    for pool, model in ((0, model_back), (1, model_front)):
        name = "back" if pool == 0 else "front"
        c, b = compare_pool(props.get(tag, {}).get(pool), model,
                            f"DARK (fc {fc}, prev da {d}, prev whole "
                            f"{whole}) {name}", tile_base,
                            failures, [0])
        compared += c
        bad += b
    print(f"DARK (fc {fc}, snapshot da {cur_d} -> prev da {d}): {compared} "
          f"shown prop slots compared vs the model: {bad} mismatches; prop "
          f"21's bank is variant {pm.variant(21, d, whole)} "
          f"(prop_pal[21][variant] + prop_shadow[variant][{y}])")

    # its uncovered pixels
    frame, drawn = props_picture(d, whole=whole, only=21)
    sprite_mask = upper_opacity_mask(upper.get(tag, []))
    fix_mask = fix_opacity_mask(fix.get(tag, {}))
    im = imgs[tag]
    cand = drawn & ~sprite_mask & ~fix_mask
    count = int(cand.sum())
    mismatches = 0
    first = None
    for yy, xx in np.argwhere(cand):
        want_px = tuple(int(v) for v in frame[yy, xx])
        got_px = _at(im, int(xx), int(yy))
        if got_px != want_px:
            mismatches += 1
            if first is None:
                first = (int(xx), int(yy), got_px, want_px)
    variant = pm.variant(21, d, whole)
    print(f"DARK: prop 21's uncovered pixels with prop_pal[21][{variant}] + "
          f"prop_shadow[{variant}][{y}]: {count} compared, {mismatches} "
          f"mismatches" + (f" (first {first})" if first else ""))
    if count < 50:
        failures.append(f"only {count} prop 21 pixels are uncovered in the "
                        "DARK snapshot (need at least 50)")
    if mismatches:
        failures.append(f"prop 21's DARK pixels: {mismatches} of {count} "
                        f"differ from prop_pal[21][{variant}] (first {first})")


def ship_proof(upper, im, fix_mask, failures):
    """Task 15 proof 3: the ship's own pixels in the FRONT frame are the
    ship's. Rebuild the ship from the ship slots' resolved boxes and SCB1
    tiles the probe dumped, through the generated ship palette, and compare
    every ship pixel not covered by the front props (10-26), the console,
    the front missiles, the explosions or the radar (and not by a fix
    tile)."""
    ship_pal = npal.ship_palette_rgb()
    frame = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
    mask = np.zeros((SCREEN_H, SCREEN_W), bool)
    higher = []
    for u in upper:
        if SHIP_FIRST <= u["slot"] <= SHIP_LAST:
            x, y, h = u["x"], u["y"], u["h"]
            for r, tile in enumerate(u["tiles"][:h]):
                idx = decode_tile(tile)
                sy, sx = y + r * 16, x
                if sy >= SCREEN_H or sy + 16 <= 0 or sx >= SCREEN_W or sx + 16 <= 0:
                    continue
                y0, y1 = max(0, sy), min(SCREEN_H, sy + 16)
                x0, x1 = max(0, sx), min(SCREEN_W, sx + 16)
                sub = idx[y0 - sy:y1 - sy, x0 - sx:x1 - sx]
                m = sub != 0
                region = frame[y0:y1, x0:x1]
                lut = np.array(ship_pal, np.uint8)[sub]
                region[m] = lut[m]
                mask[y0:y1, x0:x1] |= m
        elif u["slot"] > SHIP_LAST:
            higher.append(u)
    higher_mask = upper_opacity_mask(higher)
    cand = mask & ~higher_mask & ~fix_mask
    count = int(cand.sum())
    mismatches = 0
    first = None
    for y, x in np.argwhere(cand):
        want = tuple(int(v) for v in frame[y, x])
        got = _at(im, int(x), int(y))
        if got != want:
            mismatches += 1
            if first is None:
                first = (int(x), int(y), got, want)
    print(f"FRONT: ship's own pixels: {count} compared, {mismatches} "
          f"mismatches")
    if count < 20:
        failures.append(f"only {count} ship pixels in the FRONT frame: the "
                        "ship is not drawn at the peak")
    if mismatches:
        failures.append(f"the FRONT frame's ship pixels: {mismatches} of "
                        f"{count} differ from the ship palette (first "
                        f"{first})")


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    (snaps, da, banks, props, slots, upper, fix, census, worst, angles, pals,
     frame_da, frame_state) = parse(probe)
    pngs = snap_pngs(snap_png)
    failures = []

    for tag in ("TITLE", "PLAY", "DARK", "FRONT"):
        if tag not in snaps:
            failures.append(f"the probe never snapshotted the {tag} frame")
    if len(pngs) < len(snaps):
        failures.append(f"only {len(pngs)} snapshot(s) for {len(snaps)} "
                        "SNAP records")
    if failures:
        print("FAIL props:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    order = sorted(snaps.items(), key=lambda kv: kv[1][0])
    imgs = {tag: Image.open(pngs[i]).convert("RGB")
            for i, (tag, _) in enumerate(order) if i < len(pngs)}

    tile_base = crom_tile_base()
    print(f"props part base tile: {tile_base}")

    # ---- Task 13/14/15 proofs 1-2: every sampled frame over the turn ----
    check_angles(angles, frame_da, frame_state, tile_base, failures)

    # ---- Task 14 proof 3: prop 21 in the dome's shadow at DARK ----
    check_dark(snaps, da, banks, props, upper, fix, pals, imgs, tile_base,
               frame_da, frame_state, failures)

    # ---- Attract Task A2: the props are drawn under the title at the
    # fresh game's start-cell angle (the layout game_begin's props_show
    # draws before frame 1) ----
    title = props.get("TITLE", {})
    ntitle = sum(len(title.get(pool, {})) for pool, _, _ in POOL0)
    if ntitle != PROP_BACK_COUNT + PROP_FRONT_COUNT:
        failures.append(f"TITLE: {ntitle} prop slots read, want "
                        f"{PROP_BACK_COUNT + PROP_FRONT_COUNT}")
    else:
        model_back_t, model_front_t = pm.layout(START_DA)
        shown_t = 0
        bad_t = 0
        for pool, model in ((0, model_back_t), (1, model_front_t)):
            name = "back" if pool == 0 else "front"
            _c, b = compare_pool(title.get(pool, {}), model,
                                 f"TITLE (start angle {START_DA}) {name}",
                                 tile_base, failures, [0])
            shown_t += sum(1 for s in model if s[0])
            bad_t += b
        if shown_t < 6:
            failures.append(f"the title (start angle {START_DA}) shows only "
                            f"{shown_t} props; the fresh scene needs at "
                            "least 6")
        print(f"TITLE: {shown_t} shown prop slots vs the model at the start "
              f"angle {START_DA}: {bad_t} mismatches")

    # ---- proof 2: the PLAY frame's two pools against the model ----
    tag = "PLAY"
    play_fc = snaps[tag][1]
    cur_d = da.get(tag, -1)
    d = prev_da(play_fc, frame_da)
    whole = prev_whole(play_fc, frame_state)
    play = props.get(tag, {})
    model_back, model_front = pm.layout(d)
    bad = 0
    compared = 0
    for pool, model in ((0, model_back), (1, model_front)):
        name = "back" if pool == 0 else "front"
        got_pool = play.get(pool, {})
        c, b = compare_pool(got_pool, model,
                            f"PLAY (fc {play_fc}, prev da {d}, prev whole "
                            f"{whole}) {name}", tile_base, failures, [0])
        compared += c
        bad += b
    shown_model = sum(1 for s in model_back + model_front if s[0])
    if shown_model < 6:
        failures.append(f"the PLAY frame (prev da {d}) shows only "
                        f"{shown_model} props; the task needs at least 6")
    print(f"PLAY (fc {play_fc}, snapshot da {cur_d} -> prev da {d}): "
          f"{compared} shown prop slots compared (of "
          f"{PROP_BACK_COUNT + PROP_FRONT_COUNT} slots) vs the model: "
          f"{bad} mismatches")
    if bad:
        failures.append(f"the PLAY frame's prop slots: {bad} mismatches")

    # each shown prop's bank: the Task 14 variant at the previous frame's
    # state, i.e. prop_pal[i][d] with entries 1 and 13 from
    # prop_shadow[d][y]
    bank_bad = 0
    visible = pm.visible(d)
    vis_props = sorted(set(i for _, i in visible))
    if len(banks.get(tag, {})) != pm.NPROPS:
        failures.append(f"PLAY: {len(banks.get(tag, {}))} prop banks "
                        f"read, want {pm.NPROPS}")
    for i in vis_props:
        want = pm.bank(i, d, whole)
        got = banks.get(tag, {}).get(i)
        if got != want:
            y = max(0, min(SCREEN_H - 1, pm.Y[i][d]))
            variant = pm.variant(i, d, whole)
            failures.append(f"prop {i}'s bank {got} != prop_pal[{i}]"
                            f"[{variant}] with prop_shadow[{variant}]"
                            f"[{y}] ({want})")
            bank_bad += 1
    print(f"PLAY: {len(vis_props)} shown props' banks vs the model's "
          f"variant (prop_pal[i][d] + prop_shadow[d][y]) "
          f"({bank_bad} mismatches)")
    if bank_bad:
        failures.append(f"the shown props' banks: {bank_bad} mismatches")

    # the back pool's drawing order: it must end below the dome's first slot
    if BACK_END >= DOME_FIRST:
        failures.append(f"the back props' range ends at slot {BACK_END}, at "
                        f"or above the dome's first slot {DOME_FIRST}: they "
                        "must draw under the dome")
    # the drawing order: the ship right after the overlays, the front pool
    # right after the ship (Task 15; 10-26: a front prop covers the ship)
    if SHIP_FIRST != BROKEN_AFTER:
        failures.append(f"the ship starts at slot {SHIP_FIRST}, not at the "
                        f"overlays' end {BROKEN_AFTER}")
    if PROP_FRONT0 != SHIP_LAST + 1:
        failures.append(f"the front props start at slot {PROP_FRONT0}, not "
                        f"right after the ship ({SHIP_LAST + 1})")
    if min((u["slot"] for u in upper.get(tag, [])), default=BACK_END) <= BACK_END:
        failures.append("a slot in the back props' range was dumped as an "
                        "occluder; the props' range is out of order")

    # ---- PLAY proof 3: the clean back-pool prop pixels ----
    frame, drawn = props_picture(d, pool=0, whole=whole)
    sprite_mask = upper_opacity_mask(upper.get(tag, []))
    fix_mask = fix_opacity_mask(fix.get(tag, {}))
    im = imgs[tag]
    total = int(drawn.sum())
    covered = int((drawn & sprite_mask).sum())
    compared_px = 0
    mismatches = 0
    first = None
    for y, x in np.argwhere(drawn):
        if sprite_mask[y, x]:
            continue
        if fix_mask[y, x]:
            continue
        want = tuple(int(v) for v in frame[y, x])
        got = _at(im, int(x), int(y))
        compared_px += 1
        if got != want:
            mismatches += 1
            if first is None:
                first = (int(x), int(y), got, want)
    visible_px = total - covered
    print(f"PLAY: {compared_px} of {total} on-screen back-prop pixel "
          f"instances compared, {covered} covered by a higher sprite, "
          f"{visible_px} visible "
          f"({100.0 * compared_px / max(1, visible_px):.1f}% of the "
          f"visible), {mismatches} mismatches")
    if covered > 0.35 * total:
        failures.append(f"{covered} of {total} prop pixels are under "
                        "higher sprites (more than 35%): the cover mask "
                        "would hide the props")
    if compared_px < 0.90 * visible_px:
        failures.append(f"only {compared_px} of the {visible_px} prop "
                        "pixels not covered by a higher sprite compared "
                        "(need at least 90%)")
    if mismatches:
        failures.append(f"the props' pixels: {mismatches} of "
                        f"{compared_px} differ from the model (first "
                        f"{first})")

    # ---- Task 15 proof 3: prop 14's pixels over the dome at FRONT ----
    tag = "FRONT"
    front_fc = snaps[tag][1]
    cur_d = da.get(tag, -1)
    d = prev_da(front_fc, frame_da)
    whole = prev_whole(front_fc, frame_state)
    front = props.get(tag, {})
    model_back, model_front = pm.layout(d)
    if cur_d != FRONT_DA:
        failures.append(f"the FRONT snapshot is at da {cur_d}, not the "
                        f"probe's FRONT_DA {FRONT_DA}")
    front_props = sorted(set(s[1] for s in model_front if s[0]))
    if front_props != [14]:
        failures.append(f"at prev da {d} the front pool holds props "
                        f"{front_props}, want only prop 14")
    c, b = compare_pool(front.get(1, {}), model_front,
                        f"FRONT (fc {front_fc}, prev da {d}, prev whole "
                        f"{whole}) front", tile_base, failures, [0])
    print(f"FRONT (fc {front_fc}, snapshot da {cur_d} -> prev da {d}): {c} "
          f"shown front-pool slots compared vs the model: {b} mismatches")
    if b:
        failures.append(f"the FRONT frame's front slots: {b} mismatches")
    front_frame, front_drawn = props_picture(d, pool=1, whole=whole)
    dome_mask = rp.dome_mask()
    # the FRONT dump starts at the ship (for ship_proof); the ship and the
    # front pool itself are under or in the pool, so only slots after the
    # front pool cover its pixels
    sprite_mask = upper_opacity_mask([u for u in upper.get(tag, [])
                                      if u["slot"] > FRONT_END])
    fix_mask = fix_opacity_mask(fix.get(tag, {}))
    im = imgs[tag]
    on_dome = front_drawn & dome_mask
    cand = on_dome & ~sprite_mask & ~fix_mask
    count = int(cand.sum())
    mismatches = 0
    first = None
    for y, x in np.argwhere(cand):
        want = tuple(int(v) for v in front_frame[y, x])
        got = _at(im, int(x), int(y))
        if got != want:
            mismatches += 1
            if first is None:
                first = (int(x), int(y), got, want)
    print(f"FRONT: {count} prop 14 pixels on the dome uncovered by a higher "
          f"sprite or fix tile compared, {mismatches} mismatches "
          f"(prop 14 pixels on the dome before cover: {int(on_dome.sum())})")
    if count < 30:
        failures.append(f"only {count} prop 14 pixels over the dome are "
                        "visible (need at least 30)")
    if mismatches:
        failures.append(f"prop 14 over the dome: {mismatches} of {count} "
                        f"pixels differ from its palette (first {first})")
    ship_proof(upper.get(tag, []), im, fix_mask, failures)

    # ---- proof 4: the sprites-per-scanline census ----
    if not census:
        failures.append("the probe wrote no sprite census")
    if worst is None:
        failures.append("the probe never found a worst scanline")
    else:
        wc, wl = worst[1], worst[2]
        recount = 0
        prev_top, prev_h = 0, 0
        for s in range(381):
            w3 = worst[3].get(s, 0)
            h = w3 & 0x3f
            if w3 & 0x40:
                top, h = prev_top, prev_h
            else:
                top = 496 - (w3 >> 7)
            prev_top, prev_h = top, h
            if h > 0 and top <= wl < top + h * 16:
                recount += 1
        if recount != wc:
            failures.append(f"the recorded worst {wc} at line {wl} does not "
                            f"recount from its raw dump ({recount})")
        if wc != max(c[1] for c in census):
            failures.append(f"the recorded worst {wc} is not the census's max "
                            f"{max(c[1] for c in census)}")
        if wc > SCAN_MAX:
            failures.append(f"worst scanline {wl} has {wc} sprites, over the "
                            f"hardware's {SCAN_MAX}")
        print(f"sprites per scanline: worst {wc} at line {wl} (cart frame "
              f"{worst[0]}), over {len(census)} sampled frames, under the "
              f"hardware's {SCAN_MAX}")

    if failures:
        print("FAIL props:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS props: every sampled frame's slot words match the model at "
          f"the previous frame's angle/state ({len(angles)} frames, both "
          "ways), the previous-whole frames' shown props use variant 1 where "
          "prop_dark says so (including prop 21 at da 81..108), the "
          "previous-not-whole frames' shown props use variant 0, prop 21's "
          "DARK pixels match prop_pal[21][1], the PLAY frame's slots match, "
          "the back-prop pixels match their palette, prop 14 covers the "
          "dome's base in the FRONT frame, the ship's pixels are the ship's, "
          "the title's props match the start angle, the worst scanline is "
          "stated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
