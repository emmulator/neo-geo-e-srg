"""Assertions for the dome-scenery Task 17 towns-and-forests band boot-test.

  check_band.py SNAP PROBE

scripts/band_probe.lua boots the normal cart, presses Start, walks the ship
up to the peak and spins the dome left through the panorama (and back right),
reading, at seven dome angles, the driver's SCB3/SCB4 and all 21 chain
columns' SCB1 tile words from MAME's own VRAM, and snapshotting the title
(fc 0) and a wrapping frame with a scroll phase and a back prop
reaching into the band (da 232). This checker:

  1. builds the expected scroll from tests/band_model.py — the model, not a
     copy of the C — `s = round(da * 768 / 240) = (16 * da + 2) / 5` (which
     equals the C formula for all 240 angles, tests/test_band.py), its driver
     X and its per-column tile words;
  2. compares every sampled frame with the model: driver SCB3 (Y, height 2)
     and SCB4, and all 21 columns' SCB1 tile+attribute words and full-size
     SCB2 words (sticky followers do not inherit horizontal zoom); states
     the angles and the mismatches (expect 0);
  3. on the WINDOW snapshot (da 232: the panorama window wraps at 48 and
     the scroll phase is not 0), compares the band y 68..99, x 0..319:
       - its OPAQUE pixels that no higher sprite box or fix tile covers show
         the generated picture shifted by s, through band_pal;
       - its TRANSPARENT pixels show the mountains' picture there (Task 16's
         model, shifted by the mountains' own scroll 4 * da), through
         mtn_pal (index 0 is the sky);
     states both counts and the mismatches (expect 0);
  4. the title: the driver's SCB3 has height 2 and its SCB4 is the model's
     scroll-0 X, and every visible band pixel matches the band picture at
     s 0 (its transparent pixels show the mountains at s 0) — the band is
     drawn under the title (attract Task A2);
  5. the sprites-per-scanline census: the worst count over the leg's run and
     its line, recounted from the probe's raw worst dump, and the worst on
     the band's lines 68..99 separately; both at or under 96.

The art is the orchestrator's: this checker re-runs the committed
generators' own pictures (tools/render_band.py and tools/render_mountains.py)
rather than carrying copies of their numbers.
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
import neo_palette as npal       # noqa: E402  (MAME's 15-bit -> RGB pipeline)
import render_band as rb        # noqa: E402  (the committed band art)
import render_mountains as rm   # noqa: E402  (the committed mountain art)
import band_model as bm         # noqa: E402  (the band scroll model, not the C)
import title_model as tm        # noqa: E402  (the title's rows)
import mountains_model as mm    # noqa: E402  (Task 16's mountain scroll model)

SCREEN_W, SCREEN_H = 320, 224
BAND_Y = rb.BAND_Y
BAND_H = rb.BAND_ROWS * 16
MTN_Y = rm.MTN_Y
MTN_H = rm.MTN_H
PAL_BAND = 12
PAL_MTN = 9
SCAN_MAX = 96

_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))
BAND0 = _SLOTS["BAND_SPRITE"]
BAND_COUNT = _SLOTS["BAND_COUNT"]
BAND_LAST = BAND0 + BAND_COUNT - 1


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


def _header_palette(path, name):
    txt = open(path).read()
    m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name, txt, re.S)
    assert m, f"{name} missing from {path}"
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]


def parse(fname):
    """(frames, snaps, pals_band, pals_mtn, slots, fix, census, worst,
    bworst) from the probe's dump.

    frames: {fc: {'da': int, 'scb3': int, 'scb4': int,
                  'cols': [[(tile, attr), (tile, attr)]], 'zooms': [scb2]}}
    worst/bworst: (fc, count, line, {slot: scb3})
    """
    frames, snaps, pals_b, pals_m, slots, fix = {}, {}, {}, {}, {}, {}
    census, worst, bworst = [], None, None
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
                     (int(p[5], 16), int(p[6], 16))])
            elif p[0] == "z":
                frames[int(p[1])]["zooms"].append(int(p[3], 16))
            elif p[0] == "SNAP":
                snaps[p[1]] = (int(p[2]), int(p[3]))
            elif p[0] == "PALB":
                pals_b[p[1]] = [int(x, 16) for x in p[2:18]]
            elif p[0] == "PALM":
                pals_m[p[1]] = [int(x, 16) for x in p[2:18]]
            elif p[0] == "X":
                slots.setdefault(p[1], {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
            elif p[0] == "F":
                parts = raw.split(" ", 3)
                fix.setdefault(parts[1], {})[int(parts[2])] = parts[3]
            elif p[0] == "CEN":
                census.append((int(p[1]), int(p[2]), int(p[3]),
                               int(p[4]), int(p[5])))
            elif p[0] == "W":
                worst = (int(p[1]), int(p[2]), int(p[3]), {})
            elif p[0] == "w" and worst is not None:
                worst[3][int(p[1])] = int(p[2], 16)
            elif p[0] == "B":
                bworst = (int(p[1]), int(p[2]), int(p[3]), {})
            elif p[0] == "b" and bworst is not None:
                bworst[3][int(p[1])] = int(p[2], 16)
    return frames, snaps, pals_b, pals_m, slots, fix, census, worst, bworst


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


def covered_by_higher(boxes, x, y):
    """is (x, y) inside a sprite slot above the band (a higher slot draws on
    top of it)?"""
    for s, (bx, by, bw, bh) in boxes.items():
        if s <= BAND_LAST:          # the band and everything below it
            continue
        # a sprite X is 9 bits and wraps at 512: a column at bx covers
        # screen x when (x - bx) mod 512 is inside its 16-px width
        if by <= y < by + bh and (x - bx) % 512 < bw:
            return True
    return False


def srom_tile(s1, tile):
    """the 8x8 palette-index array of S ROM tile `tile` (32 bytes, pixel
    rows in column-pair order (4,5),(6,7),(0,1),(2,3))."""
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


def fix_opacity_mask(fix_rows, solid_rows=()):
    """(224, 320) bool: does the fix layer draw a lit pixel at screen
    (x, y)? Fix row r is at y 8r-16..8r-9 and col c at x 8c..8c+7; the tile
    is decoded from the assembled S ROM (tile = character code). `fix_rows`
    is {row: 40 chars}. `solid_rows`: rows whose non-blank cells are the
    thick title font (and its caps), whose 2-px outline the S ROM's
    tile = character code does not describe: those cells count as fully
    drawn (the version's rows reach the band's top; the level and best
    rows lie above it)."""
    s1 = open(os.path.join(ROOT, "build", "rom", "esrg-s1.s1"), "rb").read()
    mask = np.zeros((SCREEN_H, SCREEN_W), bool)
    for r, srow in fix_rows.items():
        y0 = 8 * r - 16
        for c in range(min(40, len(srow))):
            idx = srom_tile(s1, ord(srow[c]))
            if r in solid_rows and srow[c] != " ":
                idx = np.ones((8, 8), int)
            if not idx.any():
                continue
            y1 = min(SCREEN_H, y0 + 8)
            x1 = min(SCREEN_W, c * 8 + 8)
            if y0 >= SCREEN_H or c * 8 >= SCREEN_W:
                continue
            mask[max(0, y0):y1, c * 8:x1] |= idx[max(0, y0) - y0:
                                                 y1 - y0, :x1 - c * 8] != 0
    return mask


def check_frame(frames, tile_base, failures):
    """proof 2: every sampled frame equals the model."""
    ok = 0
    bad = 0
    for fc in sorted(frames):
        fr = frames[fc]
        da = fr["da"]
        s = bm.band_scroll(da)
        want_scb3 = bm.scb3_driver()
        want_scb4 = bm.driver_scb4(s)
        if fr["scb3"] != want_scb3:
            failures.append(f"da {da}: driver SCB3 {fr['scb3']:#06x}, want "
                            f"{want_scb3:#06x} (y {BAND_Y}, height "
                            f"{rb.BAND_ROWS})")
            bad += 1
        if fr["scb4"] != want_scb4:
            failures.append(f"da {da}: driver SCB4 {fr['scb4']:#06x}, want "
                            f"{want_scb4:#06x} (x {bm.driver_x(s)})")
            bad += 1
        if len(fr["cols"]) != bm.BAND_SHOWN:
            failures.append(f"da {da}: {len(fr['cols'])} chain columns read, "
                            f"want {bm.BAND_SHOWN}")
            bad += 1
            continue
        if len(fr["zooms"]) != bm.BAND_SHOWN:
            failures.append(f"da {da}: {len(fr['zooms'])} chain column SCB2 "
                            f"words read, want {bm.BAND_SHOWN}")
            bad += 1
        # every column full size: the follower does NOT inherit the
        # driver's horizontal zoom, so a stale 0 would show a sliver
        for k, z in enumerate(fr["zooms"]):
            if z != 0x0fff:
                failures.append(f"da {da} column {k}: SCB2 {z:#06x}, want "
                                "0x0fff (full size; sticky does not inherit "
                                "horizontal zoom)")
                bad += 1
        for k, col in enumerate(fr["cols"]):
            want = bm.column_tiles(s, k, tile_base)
            got = [t for t, _ in col]
            if got != want:
                failures.append(f"da {da} column {k}: tiles {got}, want {want}")
                bad += 1
            for t, attr in col:
                if (attr >> 8) != PAL_BAND:
                    failures.append(f"da {da} column {k}: attribute "
                                    f"{attr:#06x}, want palette {PAL_BAND}")
                    bad += 1
        ok += 1
        print(f"  da {da}: s {s} (s>>4 {s >> 4}, phase {s & 15}), driver "
              f"SCB3 {fr['scb3']:#06x} SCB4 {fr['scb4']:#06x}, 21 columns "
              "SCB1/SCB2: OK")
    return ok, bad


def census_from_raw(raw, y0=0, y1=SCREEN_H - 1):
    """(worst count, line) over lines y0..y1 from a raw SCB3 dump,
    resolving the sticky chains as the hardware does."""
    rows = {}
    prev_top, prev_h = 0, 0
    for s in range(381):
        w3 = raw.get(s, 0)
        h = w3 & 0x3f
        if w3 & 0x40:
            top, h = prev_top, prev_h
        else:
            top = 496 - (w3 >> 7)
        prev_top, prev_h = top, h
        if h > 0:
            for y in range(max(y0, top), min(y1 + 1, top + h * 16)):
                rows[y] = rows.get(y, 0) + 1
    best, bestline = 0, -1
    for y in range(y0, y1 + 1):
        c = rows.get(y, 0)
        if c > best:
            best, bestline = c, y
    return best, bestline


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    frames, snaps, pals_b, pals_m, slots, fix, census, worst, bworst = parse(probe)
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
        print("FAIL band:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    order = sorted(snaps.items(), key=lambda kv: kv[1][0])
    imgs = {tag: Image.open(pngs[i]).convert("RGB")
            for i, (tag, _) in enumerate(order) if i < len(pngs)}

    # the band part's C ROM base: radar headings + ground + mountains +
    # console + props tiles before it (the Makefile's CROM1_PARTS order;
    # src/band.h's BAND_TILE_BASE)
    radar = _defines(os.path.join(ROOT, "build", "radar_map.h"))
    ground = _defines(os.path.join(ROOT, "build", "ground_map.h"))
    mtn = _defines(os.path.join(ROOT, "build", "mountain_map.h"))
    con = _defines(os.path.join(ROOT, "build", "console_map.h"))
    props = _defines(os.path.join(ROOT, "build", "props_map.h"))
    tile_base = radar["RADAR_HEAD_TILE_BASE"] + radar["RADAR_HEAD_TILES"] \
        + ground["GROUND_TILES"] + mtn["MTN_TILES"] + con["CON_TILES"] \
        + props["PROP_TILES"]
    print(f"band part base tile: {tile_base}")

    # ---- proof 2: the frames against the model ----
    print("sampled frames vs the model:")
    ok, bad = check_frame(frames, tile_base, failures)
    if ok < 6:
        failures.append(f"only {ok} sampled angle frames; the probe must hit "
                        "at least six")

    # ---- proof 3: the WINDOW snapshot's pixel band ----
    tag = "WINDOW"
    win_fc = snaps[tag][1]
    if win_fc not in frames:
        failures.append(f"the WINDOW snapshot's frame {win_fc} has no S record")
    else:
        fr = frames[win_fc]
        s = bm.band_scroll(fr["da"])
        if (s >> 4) + 20 < 48:
            failures.append(f"the WINDOW frame (da {fr['da']}) does not wrap "
                            f"the panorama window (s>>4 {s >> 4})")
        if s & 15 == 0:
            failures.append(f"the WINDOW frame (da {fr['da']}) has no scroll "
                            f"phase (s & 15 == 0)")

        band_words = _header_palette(os.path.join(ROOT, "build", "band_map.h"),
                                     "band_pal")
        mtn_words = _header_palette(
            os.path.join(ROOT, "build", "mountain_map.h"), "mtn_pal")
        if pals_b.get(tag) != band_words:
            failures.append("the runtime band bank is not the generated "
                            "band_pal")
        if pals_m.get(tag) != mtn_words:
            failures.append("the runtime mountain bank is not the generated "
                            "mtn_pal")

        band_rgb = [npal.neo_rgb(w) for w in band_words]
        mtn_rgb = [npal.neo_rgb(w) for w in mtn_words]
        mtn_rgb[0] = npal.SKY_RGB          # index 0: the sky shows through

        band_pic = rb.band_picture()
        mtn_pic = rm.mountain_picture()
        assert band_pic.shape == (BAND_H, rb.BAND_W)
        assert mtn_pic.shape == (MTN_H, rm.MTN_W)
        mtn_s = mm.mtn_scroll(fr["da"])

        boxes = sprite_boxes(slots[tag])
        fix_mask = fix_opacity_mask(fix.get(tag, {}))
        im = imgs[tag]
        compared_opaque = 0
        compared_transparent = 0
        sprite_skipped = 0
        fix_skipped = 0
        mismatches = 0
        first = None
        for y in range(BAND_Y, BAND_Y + BAND_H):
            for x in range(SCREEN_W):
                if fix_mask[y, x]:
                    fix_skipped += 1
                    continue
                if covered_by_higher(boxes, x, y):
                    sprite_skipped += 1
                    continue
                idx = int(band_pic[y - BAND_Y][bm.panorama_column(s, x)])
                if idx != 0:
                    want = tuple(band_rgb[idx])
                    compared_opaque += 1
                else:
                    midx = int(mtn_pic[y - MTN_Y][
                        mm.panorama_column(mtn_s, x)])
                    want = tuple(mtn_rgb[midx])
                    compared_transparent += 1
                got = _at(im, x, y)
                if got != want:
                    mismatches += 1
                    if first is None:
                        first = (x, y, idx, got, want)
        print(f"WINDOW (da {fr['da']}, s {s}, mountains s {mtn_s}): band y "
              f"{BAND_Y}..{BAND_Y + BAND_H - 1} x 0..{SCREEN_W - 1}: "
              f"{compared_opaque} opaque band pixels and "
              f"{compared_transparent} transparent pixels compared "
              f"({sprite_skipped} under higher sprites, {fix_skipped} under "
              f"fix tiles), {mismatches} mismatches")
        if compared_opaque == 0:
            failures.append("no band opaque pixel was compared")
        if compared_transparent == 0:
            failures.append("no band transparent pixel was compared")
        if mismatches:
            failures.append(f"the WINDOW band: {mismatches} of "
                            f"{compared_opaque + compared_transparent} pixels "
                            f"differ (first {first})")

    # ---- proof 4: the band is drawn under the title at s 0 ----
    drv3, drv4 = slots["TITLE"].get(BAND0, (0, 0))
    want3 = bm.scb3_driver()
    want4 = bm.driver_scb4(0)
    if drv3 != want3:
        failures.append(f"the title driver's SCB3 is {drv3:#06x}, want "
                        f"{want3:#06x} (y {BAND_Y}, height {rb.BAND_ROWS})")
    if drv4 != want4:
        failures.append(f"the title driver's SCB4 is {drv4:#06x}, want "
                        f"{want4:#06x} (the fresh game's scroll 0)")
    title_band = _header_palette(os.path.join(ROOT, "build", "band_map.h"),
                                 "band_pal")
    title_mtn = _header_palette(
        os.path.join(ROOT, "build", "mountain_map.h"), "mtn_pal")
    if pals_b.get("TITLE") != title_band:
        failures.append("the title's runtime band bank is not the generated "
                        "band_pal")
    if pals_m.get("TITLE") != title_mtn:
        failures.append("the title's runtime mountain bank is not the "
                        "generated mtn_pal")
    band_rgb = [npal.neo_rgb(w) for w in title_band]
    mtn_rgb = [npal.neo_rgb(w) for w in title_mtn]
    mtn_rgb[0] = npal.SKY_RGB
    band_pic = rb.band_picture()
    mtn_pic = rm.mountain_picture()
    boxes = sprite_boxes(slots["TITLE"])
    fix_mask = fix_opacity_mask(fix.get("TITLE", {}),
                                 (tm.VER_ROW, tm.VER_ROW + 1))
    im = imgs["TITLE"]
    compared_opaque = compared_transparent = 0
    sprite_skipped = fix_skipped = mismatches = 0
    first = None
    for y in range(BAND_Y, BAND_Y + BAND_H):
        for x in range(SCREEN_W):
            if fix_mask[y, x]:
                fix_skipped += 1
                continue
            if covered_by_higher(boxes, x, y):
                sprite_skipped += 1
                continue
            idx = int(band_pic[y - BAND_Y][bm.panorama_column(0, x)])
            if idx != 0:
                want = tuple(band_rgb[idx])
                compared_opaque += 1
            else:
                midx = int(mtn_pic[y - MTN_Y][mm.panorama_column(0, x)])
                want = tuple(mtn_rgb[midx])
                compared_transparent += 1
            got = _at(im, x, y)
            if got != want:
                mismatches += 1
                if first is None:
                    first = (x, y, idx, got, want)
    print(f"title (s 0): driver SCB3 {drv3:#06x}, SCB4 {drv4:#06x} "
          f"(x {bm.driver_x(0)}); band y {BAND_Y}..{BAND_Y + BAND_H - 1} x "
          f"0..{SCREEN_W - 1}: {compared_opaque} opaque band pixels and "
          f"{compared_transparent} transparent pixels compared "
          f"({sprite_skipped} under higher sprites, {fix_skipped} under fix "
          f"tiles), {mismatches} mismatches")
    if compared_opaque == 0:
        failures.append("no title band opaque pixel was compared")
    if compared_transparent == 0:
        failures.append("no title band transparent pixel was compared")
    if mismatches:
        failures.append(f"the title's band: {mismatches} of "
                        f"{compared_opaque + compared_transparent} pixels "
                        f"differ (first {first})")

    # ---- proof 5: the sprites-per-scanline census over the leg's run ----
    if not census:
        failures.append("the probe wrote no sprite census")
    if worst is None:
        failures.append("the probe never found a worst scanline")
    if bworst is None:
        failures.append("the probe never found a worst band scanline")
    if census and worst is not None and bworst is not None:
        c_max = max(c[1] for c in census)
        b_max = max(c[3] for c in census)
        wc, wl = worst[1], worst[2]
        bc, bl = bworst[1], bworst[2]
        recount, rline = census_from_raw(worst[3])
        brecount, brline = census_from_raw(bworst[3], BAND_Y,
                                           BAND_Y + BAND_H - 1)
        if (wc, wl) != (recount, rline):
            failures.append(f"the recorded worst {wc} at line {wl} does not "
                            f"recount ({recount} at line {rline})")
        if wc != c_max:
            failures.append(f"the recorded worst {wc} is not the census's max "
                            f"{c_max}")
        if (bc, bl) != (brecount, brline):
            failures.append(f"the recorded band worst {bc} at line {bl} does "
                            f"not recount ({brecount} at line {brline})")
        if bc != b_max:
            failures.append(f"the recorded band worst {bc} is not the "
                            f"census's band max {b_max}")
        if wc > SCAN_MAX:
            failures.append(f"worst scanline {wl} has {wc} sprites, over the "
                            f"hardware's {SCAN_MAX}")
        if bc > SCAN_MAX:
            failures.append(f"worst band scanline {bl} has {bc} sprites, over "
                            f"the hardware's {SCAN_MAX}")
        print(f"sprites per scanline: worst {wc} at line {wl} (cart frame "
              f"{worst[0]}), under the hardware's {SCAN_MAX}; worst on the "
              f"band's lines {BAND_Y}..{BAND_Y + BAND_H - 1}: {bc} at line "
              f"{bl} (cart frame {bworst[0]})")

    if failures:
        print("FAIL band:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS band: {ok} sampled frames match the model ({bad} "
          "mismatches), the WINDOW band matches the band and mountain "
          "pictures, the title's band matches s 0, the census is stated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
