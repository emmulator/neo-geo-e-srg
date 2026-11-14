#!/usr/bin/env python3
"""Assertions for the dome-scenery Task 7 console boot-test.

  check_console.py SNAP PROBE

scripts/console_probe.lua boots the normal cart and plays the centred game,
snapshotting the title (fc 0) and an early whole-dome play frame (fc 30,
before the first missile). It reads, from MAME's own VRAM, every console
column's SCB1 tile + palette words, SCB2, SCB3 and SCB4 at both frames, every
slot's SCB3/SCB4 for the pixel proof, and the fix rows 15..28. This checker:

  1. builds the expected placement from build/console_map.h itself — per
     column its top y, its rows and its first tile in the part — and the
     console part's base tile (radar headings + ground tiles + mountain tiles
     before it in the C ROM; src/console.h's CON_TILE_BASE);
  2. at PLAY, compares all 20 columns: the SCB1 tile and palette words,
     SCB2 (0x0fff), SCB3 (Y, height, sticky bit clear) and SCB4 (X). State
     the mismatches (expect 0);
  3. at PLAY, compares every opaque pixel of the generator's own picture
     (tools/render_console.console_picture()) that no other sprite or fix
     tile covers with neo_rgb of its con_pal colour. State the count
     compared (at least 90% of the opaque pixels) and the mismatches
     (expect 0);
  4. the title: every console column's SCB3 has its header height, its
     SCB1/SCB2/SCB4 words match build/console_map.h, and the panel pixels
     that nothing above or the fix layer covers match con_pal — the panel is
     drawn under the title (attract Task A2);
  5. the sprites-per-scanline census: the worst count over the centred game
     and its line, recounted from the probe's raw worst dump; the console's
     own sprites on the lines it covers are recounted from that same dump
     and held to the header — one per column whose box covers the line: the
     wing columns (con_top 176, 13 of them, cols 0..5 and 13..19) on lines
     176..191 and all 20 on 192..223. The counts come from
     build/console_map.h, never from a copy.

The art is the orchestrator's: this checker re-runs the committed generator's
own picture rather than carrying a copy of its numbers.
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
import render_console as rc   # noqa: E402  (the committed art generator)

SCREEN_W, SCREEN_H = rc.SCREEN_W, rc.SCREEN_H
CON_COLS = rc.COLS
SCAN_MAX = 96
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))
CON0 = _SLOTS["CON_SPRITE"]


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


def _header_arrays():
    """(con_top, con_rows, con_first) from build/console_map.h."""
    txt = open(os.path.join(ROOT, "build", "console_map.h")).read()
    out = []
    for name in ("con_top", "con_rows", "con_first"):
        m = re.search(r"static const u8 %s\[CON_COLS\] = \{(.*?)\};" % name,
                      txt, re.S)
        out.append([int(x) for x in re.findall(r"\d+", m.group(1))])
    return out


def _header_palette():
    import re
    txt = open(os.path.join(ROOT, "build", "console_map.h")).read()
    m = re.search(r"static const u16 con_pal\[16\] = \{(.*?)\};", txt, re.S)
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]


def parse(fname):
    """(snaps, pals, cols, slots, fix, census, worst) from the probe dump.

    cols: {tag: [{c, scb2, scb3, scb4, words: [(tile, attr)]}]}
    upper: {tag: [{slot, scb3, scb4, tiles: [tile numbers]}]} — the slots
    above the console, for the pixel proof's true-opacity mask
    """
    snaps, pals, cols, slots, upper, fix, census = {}, {}, {}, {}, {}, {}, []
    worst = None
    with open(fname, encoding="latin-1") as fh:
        for line in fh:
            raw = line.rstrip("\n")
            p = raw.split()
            if not p:
                continue
            if p[0] == "SNAP":
                snaps[p[1]] = (int(p[2]), int(p[3]))
            elif p[0] == "PAL":
                pals[p[1]] = [int(x, 16) for x in p[2:18]]
            elif p[0] == "C":
                rows = (len(p) - 6) // 2
                words = [(int(p[6 + 2 * r], 16), int(p[7 + 2 * r], 16))
                         for r in range(rows)]
                cols.setdefault(p[1], []).append({
                    "c": int(p[2]), "scb2": int(p[3], 16),
                    "scb3": int(p[4], 16), "scb4": int(p[5], 16),
                    "words": words})
            elif p[0] == "X":
                slots.setdefault(p[1], {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
            elif p[0] == "U":
                upper.setdefault(p[1], []).append({
                    "slot": int(p[2]), "scb3": int(p[3], 16),
                    "scb4": int(p[4], 16),
                    "tiles": [int(x, 16) for x in p[5:]]})
            elif p[0] == "F":
                parts = raw.split(" ", 3)
                fix.setdefault(parts[1], {})[int(parts[2])] = parts[3]
            elif p[0] == "CEN":
                census.append((int(p[1]), int(p[2]), int(p[3])))
            elif p[0] == "W":
                worst = (int(p[1]), int(p[2]), int(p[3]), {})
            elif p[0] == "w" and worst is not None:
                worst[3][int(p[1])] = int(p[2], 16)
    return snaps, pals, cols, slots, upper, fix, census, worst


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


def sprite_opacity_mask(upper, h=SCREEN_H, w=SCREEN_W):
    """(h, w) bool: does a slot ABOVE the console draw a non-transparent
    pixel at screen (x, y)? Each U record's SCB1 tile rows are decoded from
    the assembled C ROM (tile N at byte N*64 of each plane file); the slot
    is pasted at its box (SCB4>>7, 496-(SCB3>>7)) row by row, so a panel
    pixel is excluded only where a missile, an explosion or the radar really
    draws — a box is not a picture. Off-screen parts are clipped."""
    c1, c2 = _rom_files()
    mask = np.zeros((h, w), bool)
    for u in upper:
        x = u["scb4"] >> 7
        y = 496 - (u["scb3"] >> 7)
        for r, tile in enumerate(u["tiles"]):
            idx = decode_tile(tile, c1, c2)
            sy, sx = y + r * 16, x
            if sy >= h or sy + 16 <= 0 or sx >= w or sx + 16 <= 0:
                continue
            y0, y1 = max(0, sy), min(h, sy + 16)
            x0, x1 = max(0, sx), min(w, sx + 16)
            mask[y0:y1, x0:x1] |= idx[y0 - sy:y1 - sy,
                                      x0 - sx:x1 - sx] != 0
    return mask


def _rom_files():
    """the assembled esrg-c1.c1/c2.c2 (cached)."""
    global _C1, _C2
    try:
        return _C1, _C2
    except NameError:
        pass
    rom = os.path.join(ROOT, "build", "rom")
    _C1 = open(os.path.join(rom, "esrg-c1.c1"), "rb").read()
    _C2 = open(os.path.join(rom, "esrg-c2.c2"), "rb").read()
    return _C1, _C2


def decode_tile(tile, c1, c2):
    """the 16x16 palette-index array of C ROM tile `tile` (the 4 8x8
    sub-tiles at flat offsets (8,136,0,128), each 8 rows of two plane
    bytes) — tests/neo_palette.decode_tile, without its module-level ROM
    cache (the checker must read the cart it is checking)."""
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


def fix_opacity_mask(fix_rows):
    """(224, 320) bool: does the fix layer draw a lit pixel at screen
    (x, y)? Fix row r is at y 8r-16..8r-9 and col c at x 8c..8c+7; the tile
    is decoded from the assembled S ROM (tile = character code). `fix_rows`
    is {row: 40 chars}."""
    s1 = open(os.path.join(ROOT, "build", "rom", "esrg-s1.s1"), "rb").read()
    mask = np.zeros((SCREEN_H, SCREEN_W), bool)
    for r, srow in fix_rows.items():
        y0 = 8 * r - 16
        for c in range(min(40, len(srow))):
            idx = srom_tile(s1, ord(srow[c]))
            if not idx.any():
                continue
            y1 = min(SCREEN_H, y0 + 8)
            x1 = min(SCREEN_W, c * 8 + 8)
            if y0 >= SCREEN_H or c * 8 >= SCREEN_W:
                continue
            mask[max(0, y0):y1, c * 8:x1] |= idx[max(0, y0) - y0:
                                                 y1 - y0, :x1 - c * 8] != 0
    return mask


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    snaps, pals, cols, slots, upper, fix, census, worst = parse(probe)
    pngs = snap_pngs(snap_png)
    failures = []

    for tag in ("TITLE", "PLAY"):
        if tag not in snaps:
            failures.append(f"the probe never snapshotted the {tag} frame")
    if len(pngs) < len(snaps):
        failures.append(f"only {len(pngs)} snapshot(s) for {len(snaps)} "
                        "SNAP records")
    if failures:
        print("FAIL console:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    order = sorted(snaps.items(), key=lambda kv: kv[1][0])
    imgs = {tag: Image.open(pngs[i]).convert("RGB")
            for i, (tag, _) in enumerate(order) if i < len(pngs)}

    # the console part's C ROM base: radar headings + ground tiles + mountains
    radar = _defines(os.path.join(ROOT, "build", "radar_map.h"))
    ground = _defines(os.path.join(ROOT, "build", "ground_map.h"))
    mtn = _defines(os.path.join(ROOT, "build", "mountain_map.h"))
    tile_base = radar["RADAR_HEAD_TILE_BASE"] + radar["RADAR_HEAD_TILES"] \
        + ground["GROUND_TILES"] + mtn["MTN_TILES"]
    print(f"console part base tile: {tile_base}")

    tops, rows, firsts = _header_arrays()

    # ---- proof 2: the PLAY frame's 20 columns against the header ----
    play = cols.get("PLAY", [])
    bad = 0
    if len(play) != CON_COLS:
        failures.append(f"PLAY: {len(play)} console columns read, want "
                        f"{CON_COLS}")
        bad += 1
    else:
        for col in play:
            c = col["c"]
            want_scb3 = ((496 - tops[c]) << 7) | rows[c]
            want_scb4 = c * 16 << 7
            if col["scb2"] != 0x0fff:
                failures.append(f"column {c}: SCB2 {col['scb2']:#06x}, want "
                                "0x0fff (full size)")
                bad += 1
            if col["scb3"] != want_scb3:
                failures.append(
                    f"column {c}: SCB3 {col['scb3']:#06x} (sticky "
                    f"{'set' if col['scb3'] & 0x40 else 'clear'}), want "
                    f"{want_scb3:#06x} (y {tops[c]}, height {rows[c]}, "
                    "own sprite: sticky bit clear)")
                bad += 1
            if col["scb4"] != want_scb4:
                failures.append(f"column {c}: SCB4 {col['scb4']:#06x}, want "
                                f"{want_scb4:#06x} (x {c * 16})")
                bad += 1
            want = [(tile_base + firsts[c] + r, 10 << 8)
                    for r in range(rows[c])]
            if col["words"] != want:
                failures.append(f"column {c}: SCB1 {col['words']}, want {want}")
                bad += 1
        print(f"PLAY: 20 console columns' SCB1/SCB2/SCB3/SCB4 vs the header: "
              f"{bad} mismatches")
    if bad:
        failures.append(f"the PLAY frame's console columns: {bad} mismatches")

    # ---- proof 3: the PLAY snapshot's clean panel pixels ----
    tag = "PLAY"
    play_fc = snaps[tag][1]
    pal_words = pals[tag]
    # proof 3's two halves: the runtime bank must BE the generated con_pal,
    # and the expected pixels come from the header's own words (not from the
    # bank the cart happened to write), so a cart that paints the panel with
    # another bank's palette cannot pass by comparing against itself.
    header_pal = _header_palette()
    if pal_words != header_pal:
        failures.append("the runtime console bank is not the generated "
                        "con_pal")
    pic = rc.console_picture()
    pal_rgb = [npal.neo_rgb(w) for w in header_pal]
    pal_rgb[0] = None                          # transparent: never sampled
    # the true-opacity mask of the slots ABOVE the console (front missiles,
    # explosions, radar) — those are the only ones that can draw over the
    # panel (higher slot = on top)
    sprite_mask = sprite_opacity_mask(upper.get(tag, []))
    # the fix layer's own opaque pixels (the HUD text), from the generated
    # S ROM: a fix tile draws over sprites wherever its pixels are lit
    fix_mask = fix_opacity_mask(fix.get(tag, {}))
    im = imgs[tag]
    compared = 0
    mismatches = 0
    first = None
    opaque = int((pic != 0).sum())
    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            if pic[y, x] == 0:
                continue
            if sprite_mask[y, x]:
                continue
            if fix_mask[y, x]:
                # the fix layer draws OVER sprites, so a lit fix pixel is
                # the HUD's (the hud leg proves the text); the panel is only
                # proved where nothing covers it
                continue
            want = tuple(pal_rgb[int(pic[y, x])])
            got = _at(im, x, y)
            compared += 1
            if got != want:
                mismatches += 1
                if first is None:
                    first = (x, y, int(pic[y, x]), got, want)
    print(f"PLAY (fc {play_fc}): {compared} of {opaque} opaque console "
          f"pixels compared ({100.0 * compared / opaque:.1f}%), "
          f"{mismatches} mismatches")
    # Dome-scenery Task 10 made the radar's frame a mostly OPAQUE scanner
    # disc (the Elite-style art: a fill, rings and a bezel), so the slots
    # above the panel now legitimately cover a large, exact set of its
    # pixels (1064 of the panel's 10740 today) instead of a few line
    # pixels. The anti-vacuity bound keeps its old meaning — compare at
    # least 90% of the panel pixels nothing above really draws over — by
    # leaving the sprite-covered pixels out of the denominator, not by
    # lowering the bound or skipping any pixel comparison.
    covered = int(((pic != 0) & sprite_mask).sum())
    visible = opaque - covered
    # ... and the cover itself stays bounded (1064 of 10740, 9.9%, today:
    # exactly the radar disc's opaque pixels; the fix layer's cells are
    # left out of `compared` separately), so a sprite mask that grew to
    # cover the panel can't make the comparison vacuous
    if covered > 0.20 * opaque:
        failures.append(f"{covered} of {opaque} console pixels are under "
                        "other sprites (more than 20%): the cover mask "
                        "would hide the panel")
    if compared < 0.90 * visible:
        failures.append(f"only {compared} of the {visible} console pixels "
                        "not covered by a sprite above compared "
                        "(need at least 90%)")
    if mismatches:
        failures.append(f"the console picture: {mismatches} of {compared} "
                        f"pixels differ from con_pal (first {first})")

    # ---- proof 4: the panel is drawn under the title ----
    title = cols.get("TITLE", [])
    if len(title) != CON_COLS:
        failures.append(f"TITLE: {len(title)} console columns read, want "
                        f"{CON_COLS}")
    else:
        shown = sum(1 for col in title if col["scb3"] & 0x3f)
        if shown != CON_COLS:
            failures.append(f"the title draws {shown} of {CON_COLS} console "
                            "columns (the panel is the fresh scene's)")
        bad_t = 0
        for col in title:
            c = col["c"]
            want_scb3 = ((496 - tops[c]) << 7) | rows[c]
            want_scb4 = c * 16 << 7
            if col["scb2"] != 0x0fff:
                failures.append(f"TITLE column {c}: SCB2 {col['scb2']:#06x}, "
                                "want 0x0fff")
                bad_t += 1
            if col["scb3"] != want_scb3:
                failures.append(f"TITLE column {c}: SCB3 {col['scb3']:#06x}, "
                                f"want {want_scb3:#06x}")
                bad_t += 1
            if col["scb4"] != want_scb4:
                failures.append(f"TITLE column {c}: SCB4 {col['scb4']:#06x}, "
                                f"want {want_scb4:#06x}")
                bad_t += 1
            want = [(tile_base + firsts[c] + r, 10 << 8)
                    for r in range(rows[c])]
            if col["words"] != want:
                failures.append(f"TITLE column {c}: SCB1 {col['words']}, "
                                f"want {want}")
                bad_t += 1
        print(f"TITLE: {shown} console columns drawn, SCB1/SCB2/SCB3/SCB4 vs "
              f"the header: {bad_t} mismatches")
        # the panel's clean pixels, exactly as the PLAY proof below: the
        # slots above the console and the fix layer (HUD/title) are the only
        # covers.
        title_pal = pals["TITLE"]
        if title_pal != header_pal:
            failures.append("the title's runtime console bank is not the "
                            "generated con_pal")
        title_sprite_mask = sprite_opacity_mask(upper.get("TITLE", []))
        title_fix_mask = fix_opacity_mask(fix.get("TITLE", {}))
        title_im = imgs["TITLE"]
        opaque_t = int((pic != 0).sum())
        compared_t = bad_px_t = 0
        first_t = None
        for y in range(SCREEN_H):
            for x in range(SCREEN_W):
                if pic[y, x] == 0:
                    continue
                if title_sprite_mask[y, x] or title_fix_mask[y, x]:
                    continue
                want = tuple(pal_rgb[int(pic[y, x])])
                got = _at(title_im, x, y)
                compared_t += 1
                if got != want:
                    bad_px_t += 1
                    if first_t is None:
                        first_t = (x, y, int(pic[y, x]), got, want)
        covered_t = int(((pic != 0) & title_sprite_mask).sum())
        visible_t = opaque_t - covered_t
        print(f"TITLE: {compared_t} of {visible_t} console pixels not "
              f"covered by a sprite above compared, {bad_px_t} mismatches")
        if covered_t > 0.20 * opaque_t:
            failures.append(f"{covered_t} of {opaque_t} title console pixels "
                            "are under other sprites (more than 20%)")
        if compared_t < 0.90 * visible_t:
            failures.append(f"only {compared_t} of the {visible_t} title "
                            "console pixels not covered above compared "
                            "(need at least 90%)")
        if bad_px_t:
            failures.append(f"the title's console picture: {bad_px_t} of "
                            f"{compared_t} pixels differ from con_pal (first "
                            f"{first_t})")

    # ---- proof 5: the sprites-per-scanline census ----
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
        # the console's band: the wings' first tile row (con_top of a wing
        # column, from build/console_map.h) to the screen's bottom. Since
        # dome-scenery Task 12 the props are one pool over the grass and the
        # mountains, and the census' worst line can legitimately sit in
        # their band (line 142, the props' densest line) rather than the
        # console's. The console's own per-line contribution is still proved
        # below, from the worst-frame dump; the band assertion only asks
        # that the worst line be in the scenery's band (the ground or the
        # props), never in the sky-only band above the ground.
        wing_cols = [c for c in range(CON_COLS) if c not in rc.STRIP_COLS]
        strip_cols = [c for c in range(CON_COLS) if c in rc.STRIP_COLS]
        wing_top = min(tops[c] for c in wing_cols)
        strip_top = min(tops[c] for c in strip_cols)
        ground_top = _defines(os.path.join(ROOT, "build",
                                           "ground_map.h"))["GROUND_Y"]
        if wl < ground_top:
            failures.append(f"the worst line {wl} is above the ground's band "
                            f"({ground_top}): the ground adds a sprite to "
                            "every line it covers, so the worst should be in "
                            "the ground's band or below")
        # the console's own sprite boxes on a line: one per column whose
        # first tile row (con_top) is at or above it, which is what the
        # probe's SCB3 places. Recount them from the worst-frame dump (the
        # console slots are CON0 .. CON0+CON_COLS-1) and hold them to the
        # header, so the printed counts are measured, not copied.
        top_of = {}
        prev_top, prev_h = 0, 0
        for s in range(381):
            w3 = worst[3].get(s, 0)
            h = w3 & 0x3f
            if w3 & 0x40:
                top, hh = prev_top, prev_h
            else:
                top, hh = 496 - (w3 >> 7), h
            prev_top, prev_h = top, hh
            top_of[s] = (top, hh)

        def console_on(y):
            return sum(1 for c in range(CON_COLS)
                       if top_of[CON0 + c][1] > 0
                       and top_of[CON0 + c][0] <= y
                       < top_of[CON0 + c][0] + top_of[CON0 + c][1] * 16)

        want_wing = sum(1 for c in wing_cols if tops[c] <= wing_top)
        want_strip = sum(1 for c in range(CON_COLS) if tops[c] <= strip_top)
        got_wing, got_strip = console_on(wing_top), console_on(strip_top)
        if got_wing != want_wing:
            failures.append(f"the console draws {got_wing} columns on line "
                            f"{wing_top}, the header's tops imply {want_wing}")
        if got_strip != want_strip:
            failures.append(f"the console draws {got_strip} columns on line "
                            f"{strip_top}, the header's tops imply {want_strip}")
        print(f"sprites per scanline: worst {wc} at line {wl} (cart frame "
              f"{worst[0]}), under the hardware's {SCAN_MAX}; the console adds "
              f"{got_wing} on lines {wing_top}..{strip_top - 1} and "
              f"{got_strip} on {strip_top}..223 (from the header's con_top "
              "and the worst-frame dump)")

    if failures:
        print("FAIL console:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS console: every column word matches the header ({bad} "
          "mismatches), the panel's pixels match con_pal, the title's panel "
          "is drawn, the worst scanline is stated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
