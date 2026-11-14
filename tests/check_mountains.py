"""Assertions for the dome-scenery Task 16 mountains boot-test.

  check_mountains.py SNAP PROBE

scripts/mountains_probe.lua boots the normal cart, presses Start, walks the
ship up to the peak and spins the dome left through the panorama (and back
right), reading, at six dome angles, the driver's SCB3/SCB4 and all 21
chain columns' SCB1 tile words from MAME's own VRAM, and snapshotting the
title (fc 0) and a wrapping frame with a scroll phase (da 161). This
checker:

  1. builds the expected scroll from tests/mountains_model.py — the model,
     not a copy of the C — `s = 4 * da` (which equals the C formula for all
     240 angles, tests/test_mountains.py), its driver X and its per-column
     tile words;
  2. compares every sampled frame with the model: driver SCB3 (Y, height 3)
     and SCB4, and all 21 columns' SCB1 tile+attribute words and full-size
     SCB2 words (sticky followers do not inherit horizontal zoom); states
     the angles and the mismatches (expect 0);
  3. on the WINDOW snapshot (da 161: the panorama window wraps at 60 and
     the scroll phase is not 0), compares the band y 52..99, x 0..319 with
     the generated picture shifted by s, on every pixel no other sprite or
     fix tile covers. Dome-scenery Task 17 put the towns-and-forests band
     over y 68..99, so those rows are the band's picture now; the checker
     compares the mountains' still-visible rows (today y 52..67, 5120 px)
     and holds the visible slice to at least 30% of the old band, the
     comparison to every visible pixel (>= 90% of that set), and the
     mismatches to 0;
  4. the title: the driver's SCB3 has height 3 and its SCB4 is the model's
     scroll-0 X, and every visible mountain pixel (the band's own box hides
     y 68..99) matches the generated picture at s 0 — the mountains are
     drawn under the title (attract Task A2);
  5. the sprites-per-scanline census is taken from the probe's WINDOW
     snapshot slot dump, recounted from the raw SCB3 words; states the
     worst count and line in the mountain band.

The art is the orchestrator's: this checker re-runs the committed
generator's own picture (tools/render_mountains.py) rather than carrying a
copy of its numbers.
"""
import json
import os
import sys

import numpy as np
from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import neo_palette as npal     # noqa: E402  (MAME's 15-bit -> RGB pipeline)
import render_mountains as rm  # noqa: E402  (the committed art generator)
import mountains_model as mm   # noqa: E402  (the scroll model, not the C)

MTN_Y = rm.MTN_Y
MTN_H = rm.MTN_H
SCREEN_W, SCREEN_H = 320, 224
BAND = (MTN_Y, MTN_Y + MTN_H - 1, 0, SCREEN_W - 1)
TOL = 2                        # MAME snapshots may be scaled (they are 320x224)
CENSUS_MIN = 1
SCAN_MAX = 96

_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))


def _defines(path):
    """evaluate a generated header's #defines in order (a plain number, or an
    expression over the names defined before it: the radar's/ground's
    bases). The same reader the host tests use."""
    import re
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


def parse(fname):
    """(frames, snaps, pals, slots, fix) from the probe's dump.

    frames: {fc: {'da': int, 'scb3': int, 'scb4': int,
                  'cols': [[(tile, attr)]], 'zooms': [scb2 words]}}
    """
    frames, snaps, pals, slots, fix = {}, {}, {}, {}, {}
    with open(fname, encoding="latin-1") as fh:
        for line in fh:
            raw = line.rstrip("\n")
            p = raw.split()
            if not p:
                continue
            if p[0] == "S":
                fc, d = int(p[1]), int(p[2])
                frames.setdefault(fc, {"da": d})
                frames[fc]["scb3"] = int(p[3], 16)
                frames[fc]["scb4"] = int(p[4], 16)
                frames[fc]["cols"] = []
                frames[fc]["zooms"] = []
            elif p[0] == "c":
                fc, k = int(p[1]), int(p[2])
                frames[fc]["cols"].append(
                    [(int(p[3], 16), int(p[4], 16)),
                     (int(p[5], 16), int(p[6], 16)),
                     (int(p[7], 16), int(p[8], 16))])
            elif p[0] == "z":
                frames[int(p[1])]["zooms"].append(int(p[3], 16))
            elif p[0] == "SNAP":
                snaps[p[1]] = (int(p[2]), int(p[3]))
            elif p[0] == "PAL":
                pals[p[1]] = [int(x, 16) for x in p[2:18]]
            elif p[0] == "X":
                slots.setdefault(p[1], {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
            elif p[0] == "F":
                parts = raw.split(" ", 3)
                fix.setdefault(parts[1], {})[int(parts[2])] = parts[3]
    return frames, snaps, pals, slots, fix


def snap_pngs(snap_png):
    """the MAME-managed snapshot directory's PNGs in order."""
    snap_dir = os.path.join(os.path.dirname(os.path.abspath(snap_png)), "snap")
    if not os.path.isdir(snap_dir):
        return [snap_png]
    pngs = sorted(os.path.join(r, fn) for r, _, fs in os.walk(snap_dir)
                  for fn in fs if fn.endswith(".png"))
    return pngs or [snap_png]


def _at(im, x, y):
    """a snapshot pixel for a 320x224 screen coordinate (scaled PNGs)."""
    w, h = im.size
    return tuple(im.getpixel((int(x * w / SCREEN_W), int(y * h / SCREEN_H)))[:3])


def sprite_boxes(scb3):
    """slot -> its on-screen (x, y, w, h) box for every drawn slot,
    resolving the sticky chains as the hardware does."""
    boxes = {}
    prev = None
    for s in range(381):
        if s not in scb3:
            continue
        w3, w4 = scb3[s]
        h = w3 & 0x3f
        if w3 & 0x40 and prev is not None:      # sticky: inherit
            x, y, ph = prev
            x = (x + 16) & 0x1ff                # X is 9 bits: wrap at 512
            h = ph
        else:
            x, y = (w4 >> 7), 496 - (w3 >> 7)
        prev = (x, y, h)
        if h > 0:
            boxes[s] = (x, y, 16, h * 16)
    return boxes


def covered(boxes, x, y, skip_slots=()):
    """is screen pixel (x, y) inside a drawn sprite's box, other than the
    mountains' own slots (the mountains ARE the picture being checked)?"""
    for s, (bx, by, bw, bh) in boxes.items():
        if s in skip_slots:
            continue
        # a sprite X is 9 bits and wraps at 512: a column at bx covers
        # screen x when (x - bx) mod 512 is inside its 16-px width
        if by <= y < by + bh and (x - bx) % 512 < bw:
            return True
    return False


def fix_covers(fix_rows, x, y):
    """does a fix tile draw at screen (x, y)? Fix row r is at y 8r-16..8r-9
    and col c at x 8c..8c+7. `fix_rows` is {row: 40 chars}."""
    r = (y + 16) // 8
    c = x // 8
    row = fix_rows.get(r)
    return bool(row and c < len(row) and row[c] != " ")


def mountain_picture_rgb(pal_words):
    """the generated picture's screen RGB, the sky where the index is 0."""
    pic = rm.mountain_picture()
    lut = np.array([npal.neo_rgb(w) for w in pal_words], np.uint8)
    lut[0] = npal.SKY_RGB
    return lut[pic]


def check_frame(frames, tile_base, failures):
    """proof 2: every sampled frame equals the model."""
    ok = 0
    bad = 0
    for fc in sorted(frames):
        fr = frames[fc]
        da = fr["da"]
        s = mm.mtn_scroll(da)
        want_scb3 = mm.scb3_driver()
        want_scb4 = mm.driver_scb4(s)
        if fr["scb3"] != want_scb3:
            failures.append(f"da {da}: driver SCB3 {fr['scb3']:#06x}, want "
                            f"{want_scb3:#06x} (y {MTN_Y}, height {rm.MTN_ROWS})")
            bad += 1
        if fr["scb4"] != want_scb4:
            failures.append(f"da {da}: driver SCB4 {fr['scb4']:#06x}, want "
                            f"{want_scb4:#06x} (x {mm.driver_x(s)})")
            bad += 1
        if len(fr["cols"]) != mm.MTN_SHOWN:
            failures.append(f"da {da}: {len(fr['cols'])} chain columns read, "
                            f"want {mm.MTN_SHOWN}")
            bad += 1
            continue
        if len(fr["zooms"]) != mm.MTN_SHOWN:
            failures.append(f"da {da}: {len(fr['zooms'])} chain column SCB2 "
                            f"words read, want {mm.MTN_SHOWN}")
            bad += 1
        # every column full size: the follower does NOT inherit the
        # driver's horizontal zoom, so a stale 0 would show a sliver
        for k, z in enumerate(fr["zooms"]):
            if z != 0x0fff:
                failures.append(f"da {da} column {k}: SCB2 {z:#06x}, want "
                                f"0x0fff (full size; sticky does not inherit "
                                "horizontal zoom)")
                bad += 1
        for k, col in enumerate(fr["cols"]):
            want = mm.column_tiles(s, k, tile_base)
            got = [t for t, _ in col]
            if got != want:
                failures.append(f"da {da} column {k}: tiles {got}, want {want}")
                bad += 1
            for t, attr in col:
                if (attr >> 8) != 9:            # PAL_MTN
                    failures.append(f"da {da} column {k}: attribute "
                                    f"{attr:#06x}, want palette 9")
                    bad += 1
        ok += 1
        print(f"  da {da}: s {s} (s>>4 {s >> 4}, phase {s & 15}), driver "
              f"SCB3 {fr['scb3']:#06x} SCB4 {fr['scb4']:#06x}, 21 columns "
              "SCB1/SCB2: OK")
    return ok, bad


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    frames, snaps, pals, slots, fix = parse(probe)
    pngs = snap_pngs(snap_png)
    failures = []

    if not frames:
        failures.append("probe wrote no S frames")
    for tag in ("TITLE", "WINDOW"):
        if tag not in snaps:
            failures.append(f"the probe never snapshotted the {tag} frame")
    if len(pngs) < len(snaps):
        failures.append(f"only {len(pngs)} snapshot(s) for {len(snaps)} "
                        "SNAP records")
    if failures:
        print("FAIL mountains:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    order = sorted(snaps.items(), key=lambda kv: kv[1][0])
    imgs = {tag: Image.open(pngs[i]).convert("RGB")
            for i, (tag, _) in enumerate(order) if i < len(pngs)}

    # the mountain part's C ROM base: radar headings + ground tiles (the
    # Makefile's CROM1_PARTS order; src/mountains.h's MTN_TILE_BASE)
    radar = _defines(os.path.join(ROOT, "build", "radar_map.h"))
    ground = _defines(os.path.join(ROOT, "build", "ground_map.h"))
    tile_base = radar["RADAR_HEAD_TILE_BASE"] + radar["RADAR_HEAD_TILES"] \
        + ground["GROUND_TILES"]
    print(f"mountain part base tile: {tile_base}")

    # ---- proof 2: the frames against the model ----
    print("sampled frames vs the model:")
    ok, bad = check_frame(frames, tile_base, failures)
    if ok < 5:
        failures.append(f"only {ok} sampled angle frames; the probe must hit "
                        "at least five")

    # ---- proof 3: the WINDOW snapshot's pixel band ----
    tag = "WINDOW"
    win_fc = snaps[tag][1]
    if win_fc not in frames:
        failures.append(f"the WINDOW snapshot's frame {win_fc} has no S record")
    else:
        fr = frames[win_fc]
        s = mm.mtn_scroll(fr["da"])
        if (s >> 4) + 20 < 60:
            failures.append(f"the WINDOW frame (da {fr['da']}) does not wrap "
                            f"the panorama window (s>>4 {s >> 4})")
        if s & 15 == 0:
            failures.append(f"the WINDOW frame (da {fr['da']}) has no scroll "
                            f"phase (s & 15 == 0)")
        pal_words = pals[tag]
        # the runtime bank must be the generated palette
        mtn_pal = _header_palette()
        if pal_words != mtn_pal:
            failures.append("the runtime mountain bank is not the generated "
                            "mtn_pal")
        pic = rm.mountain_picture()
        pal_rgb = [npal.neo_rgb(w) for w in pal_words]
        pal_rgb[0] = npal.SKY_RGB
        boxes = sprite_boxes(slots[tag])
        mtn_slots = set(range(_SLOTS["MTN_SPRITE"],
                              _SLOTS["MTN_SPRITE"] + _SLOTS["MTN_COUNT"]))
        fix_rows = fix.get(tag, {})
        im = imgs[tag]
        y0, y1, x0, x1 = BAND
        compared = 0
        covered_other = 0
        covered_fix = 0
        mismatches = 0
        first = None
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if covered(boxes, x, y, mtn_slots):
                    covered_other += 1
                    continue
                if fix_covers(fix_rows, x, y):
                    covered_fix += 1
                    continue
                idx = int(pic[y - MTN_Y][mm.panorama_column(s, x)])
                want = tuple(pal_rgb[idx])
                got = _at(im, x, y)
                compared += 1
                if got != want:
                    mismatches += 1
                    if first is None:
                        first = (x, y, got, want, idx)
        total = (y1 - y0 + 1) * (x1 - x0 + 1)
        # dome-scenery Task 17 put the towns-and-forests band over the
        # mountain band's y 68..99, so those rows are no longer visible
        # mountains (the band's own boot leg proves they show ITS picture).
        # The proof still compares every pixel no sprite/fix tile covers
        # (today the mountains' own y 52..67); its denominator is that
        # visible set, and the set must stay a meaningful slice of the old
        # band rather than shrinking to nothing.
        visible = total - covered_other - covered_fix
        print(f"WINDOW (da {fr['da']}, s {s}): band y {y0}..{y1} x {x0}..{x1} "
              f"({total} px): {compared} compared of {visible} visible "
              f"({covered_other} under other sprites, {covered_fix} under "
              f"fix tiles), {mismatches} mismatches "
              f"({100.0 * compared / total:.1f}% of the old band)")
        if visible < 0.30 * total:
            failures.append(f"only {visible} of {total} band pixels are not "
                            "covered by a sprite/fix tile (need at least 30% "
                            "so the mountain picture is still proved)")
        if compared < 0.90 * visible:
            failures.append(f"only {compared} of the {visible} visible band "
                            "pixels compared (need at least 90%)")
        if mismatches:
            failures.append(f"the WINDOW band: {mismatches} of {compared} "
                            f"pixels differ from the shifted picture (first "
                            f"{first})")

    # ---- proof 4: the mountains are drawn under the title at s 0 ----
    drv3, drv4 = slots["TITLE"].get(_SLOTS["MTN_SPRITE"], (0, 0))
    want3 = mm.scb3_driver()
    want4 = mm.driver_scb4(0)
    if drv3 != want3:
        failures.append(f"the title driver's SCB3 is {drv3:#06x}, want "
                        f"{want3:#06x} (y {MTN_Y}, height {rm.MTN_ROWS})")
    if drv4 != want4:
        failures.append(f"the title driver's SCB4 is {drv4:#06x}, want "
                        f"{want4:#06x} (the fresh game's scroll 0)")
    title_pal = pals["TITLE"]
    mtn_pal = _header_palette()
    if title_pal != mtn_pal:
        failures.append("the title's runtime mountain bank is not the "
                        "generated mtn_pal")
    pal_rgb = [npal.neo_rgb(w) for w in mtn_pal]
    pal_rgb[0] = npal.SKY_RGB
    pic = rm.mountain_picture()
    boxes = sprite_boxes(slots["TITLE"])
    mtn_slots = set(range(_SLOTS["MTN_SPRITE"],
                          _SLOTS["MTN_SPRITE"] + _SLOTS["MTN_COUNT"]))
    fix_rows = fix.get("TITLE", {})
    im = imgs["TITLE"]
    y0, y1, x0, x1 = BAND
    compared = covered_other = covered_fix = mismatches = 0
    first = None
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if covered(boxes, x, y, mtn_slots):
                covered_other += 1
                continue
            if fix_covers(fix_rows, x, y):
                covered_fix += 1
                continue
            idx = int(pic[y - MTN_Y][mm.panorama_column(0, x)])
            want = tuple(pal_rgb[idx])
            got = _at(im, x, y)
            compared += 1
            if got != want:
                mismatches += 1
                if first is None:
                    first = (x, y, got, want, idx)
    total = (y1 - y0 + 1) * (x1 - x0 + 1)
    visible = total - covered_other - covered_fix
    print(f"title (s 0): driver SCB3 {drv3:#06x}, SCB4 {drv4:#06x} "
          f"(x {mm.driver_x(0)}); band y {y0}..{y1} x {x0}..{x1}: "
          f"{compared} compared of {visible} visible ({covered_other} under "
          f"other sprites, {covered_fix} under fix tiles), {mismatches} "
          f"mismatches")
    if compared < 0.90 * visible:
        failures.append(f"only {compared} of the {visible} visible title "
                        "mountain pixels compared (need at least 90%)")
    if mismatches:
        failures.append(f"the title's mountains: {mismatches} of {compared} "
                        f"pixels differ from the s-0 picture (first {first})")

    # ---- proof 5: the sprites-per-scanline census from the slot dump ----
    raw = slots["WINDOW"]
    rows = {}
    prev_top, prev_h = 0, 0
    for s in range(381):
        w3, _w4 = raw.get(s, (0, 0))
        h = w3 & 0x3f
        if w3 & 0x40:
            top, h = prev_top, prev_h
        else:
            top = 496 - (w3 >> 7)
        prev_top, prev_h = top, h
        if h > 0:
            for y in range(max(0, top), min(SCREEN_H, top + h * 16)):
                rows[y] = rows.get(y, 0) + 1
    worst, worst_line = 0, -1
    for y in range(SCREEN_H):
        c = rows.get(y, 0)
        if c > worst:
            worst, worst_line = c, y
    if worst > SCAN_MAX:
        failures.append(f"worst scanline {worst_line} has {worst} sprites, "
                        f"over the hardware's {SCAN_MAX}")
    print(f"sprites per scanline at the WINDOW frame: worst {worst} at line "
          f"{worst_line}, under the hardware's {SCAN_MAX}; the mountains add "
          f"{mm.MTN_SHOWN} on lines {MTN_Y}..{MTN_Y + MTN_H - 1}")

    if failures:
        print("FAIL mountains:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS mountains: {ok} sampled frames match the model ({bad} "
          "mismatches), the WINDOW band matches the shifted picture, the "
          "title's mountains match s 0, worst scanline stated")
    return 0


def _header_palette():
    import re
    txt = open(os.path.join(ROOT, "build", "mountain_map.h")).read()
    m = re.search(r"static const u16 mtn_pal\[16\] = \{(.*?)\};", txt, re.S)
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]


if __name__ == "__main__":
    sys.exit(main())
