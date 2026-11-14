"""Assertions for the dome-scenery Task 5 grass boot-test.

  check_ground.py SNAP PROBE [FRAMECNT_ADDR]

scripts/ground_probe.lua boots the normal cart and plays the centred full
game (the same policy as the collapse leg: stick centred, A every 11 cart
frames) while taking three snapshots in order — TITLE (fc 0), WHOLE (an
early play frame, fc 30, before the first missile at fc 59) and GONE (the
first play frame whose dome slot 0 SCB1 attribute is PAL_RUIN << 8, after a
whole dome was seen: the collapse's ruin, Task C1). This checker proves:

  1. the generated ground art: the two palettes differ only in entries
     8..14, and there ground_pal_noshadow[k + 7] == ground_pal[k]
     (tests/test_ground.py holds the header to its own generator; this
     re-derives the picture the checker compares against);
  2. the WHOLE snapshot's clean band y 104..119, x 0..79 (no sprite or fix
     layer draws there) equals the generated picture's colour as MAME shows
     it (neo_rgb of the palette word the cart's ground bank holds);
  3. the shadow: 50 art pixels that are shadow (index 8..14) and not covered
     by any sprite (right of x 225) show the twin colour in the WHOLE
     snapshot and the plain shade in the GONE snapshot — the bank really
     switched to ground_pal_noshadow while the dome is not whole (from the
     collapse's first split on, and through the ruin);
  4. the TITLE snapshot (10, 150) is the generated grass colour through
     its ripple bank at the fresh game's angle 0: the grass is drawn under
     the title (attract Task A2);
  5. the sprites-per-scanline census: the worst count over the centred game
     and its line, from the probe's per-frame census; the worst must stay
     under the hardware's 96 and its line must be in the ground's band.

The art is the orchestrator's: this checker re-runs the committed
generator's own picture (tools/render_scenery.py) rather than carrying a
copy of its numbers.
"""
import os
import re
import sys

import numpy as np
from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import neo_palette as npal     # noqa: E402  (MAME's 15-bit -> RGB pipeline)
import layout as lay          # noqa: E402
import render_scenery as rs  # noqa: E402  (the committed art generator)
import render_ripple as rr   # noqa: E402  (Task 19: the ripple's picture)
import render_console as rc  # noqa: E402  (dome-scenery Task 7: the panel)

GROUND_Y = rs.GROUND_Y
GROUND_H = rs.GROUND_ROWS * 16
SCREEN_W, SCREEN_H = rs.SCREEN_W, rs.SCREEN_H
PAL_GROUND = 8                 # src/ground.h (the whole/gone marker)
RIPPLE_PAL_BANK = 44           # src/ground.h
BAND = (104, 119, 0, 79)       # y0, y1, x0, x1: nothing else draws there
SHADOW_X0 = 226                # right of x 225 (the proof's "right of x 225")
# dome-scenery Task 7: the console covers the bottom of the screen; Task 8
# lowered it (the wings' art starts at y 176, the strip's at y 192), so the
# shadow's pixels right of x 225 that used to be the proof (y 149..201) are
# mostly under the panel now. The scan keeps its "right of x 225" window; the
# console is excluded only where its generated picture is opaque, so the
# shadow pixels above the panel's own art are still
# found. 668 art shadow pixels right of x 225 are visible above that art (and
# 7013 left of it); the 50 picked below are the topmost of them.
TOL = 2                        # MAME snapshots may be scaled (they are 320x224)
CENSUS_MIN = 1                 # at least one sampled census
SCAN_MAX = 96                  # the hardware's sprites per scanline

# the one sprite slot map (src/slots.h -> build/slots.json)
import json  # noqa: E402
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))


def parse(fname):
    """(records, snaps, pals, slots, fix, census, worst) from the dump."""
    records, snaps, pals, slots, fix, census = [], {}, {}, {}, {}, []
    worst = None
    with open(fname, encoding="latin-1") as fh:
        for line in fh:
            raw = line.rstrip("\n")
            p = raw.split()
            if not p:
                continue
            if p[0] == "I":
                records.append((int(p[1]), int(p[2]), int(p[3]), int(p[4])))
            elif p[0] == "SNAP":
                snaps[p[1]] = (int(p[2]), int(p[3]))
            elif p[0] == "PAL":
                pals[p[1]] = [int(x, 16) for x in p[2:18]]
            elif p[0] == "X":
                slots.setdefault(p[1], {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
            elif p[0] == "F":
                # F <TAG> <row> <40 chars>: the row may be all spaces, so
                # split off the first three fields and keep the rest.
                parts = raw.split(" ", 3)
                fix.setdefault(parts[1], {})[int(parts[2])] = parts[3]
            elif p[0] == "C":
                census.append((int(p[1]), int(p[2]), int(p[3])))
            elif p[0] == "W":
                worst = (int(p[1]), int(p[2]), int(p[3]), {})
            elif p[0] == "w" and worst is not None:
                worst[3][int(p[1])] = int(p[2], 16)
    return records, snaps, pals, slots, fix, census, worst


def snap_pngs(snap_png):
    """the MAME-managed snapshot directory's PNGs in order (never the copy
    boot_test.sh makes next to it)."""
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
    resolving the sticky chains exactly as the hardware does: a sticky slot
    inherits the PREVIOUS slot's Y and height and sits 16 px right of it; a
    non-sticky slot uses its own SCB3 Y/height. `scb3` maps slot ->
    (scb3, scb4)."""
    boxes = {}
    prev = None
    for s in range(381):
        if s not in scb3:
            continue
        w3, w4 = scb3[s]
        h = w3 & 0x3f
        if w3 & 0x40 and prev is not None:      # sticky: inherit
            x, y, ph = prev
            x += 16
            h = ph
        else:
            x, y = (w4 >> 7), 496 - (w3 >> 7)
        prev = (x, y, h)
        if h > 0:
            boxes[s] = (x, y, 16, h * 16)
    return boxes


def covered(boxes, x, y, skip_slots=()):
    """is screen pixel (x, y) inside a drawn sprite's box, other than the
    ground's own slots (the grass IS the shadow's picture, so it must not
    count as an occluder)? `boxes` maps slot -> (x, y, w, h)."""
    for s, (bx, by, bw, bh) in boxes.items():
        if s in skip_slots:
            continue
        if bx <= x < bx + bw and by <= y < by + bh:
            return True
    return False


def fix_covers(fix_rows, x, y):
    """does a fix tile draw at screen (x, y)? Fix row r is at y 8r-16..8r-9
    and col c at x 8c..8c+7 (src/hud.h). `fix_rows` is {row: 40 chars}."""
    r = (y + 16) // 8
    c = x // 8
    row = fix_rows.get(r)
    return bool(row and c < len(row) and row[c] != " ")


def _header_palettes():
    """the generated build/ground_map.h's two palettes as word lists."""
    txt = open(os.path.join(ROOT, "build", "ground_map.h")).read()
    out = {}
    for name in ("ground_pal", "ground_pal_noshadow"):
        m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name, txt, re.S)
        out[name] = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    return out


def _header_ripple():
    """(ground_bank, ground_ripple_pal, ground_ripple_rot) from the built
    header: the ripple's bank per tile and its palettes/rotations."""
    txt = open(os.path.join(ROOT, "build", "ground_map.h")).read()

    def body(name):
        m = re.search(r"%s\[[^=]*= \{(.*?)\};" % name, txt, re.S)
        return m.group(1)

    bank_body = body("ground_bank")
    bank = [[int(x) for x in re.findall(r"\d+", row)]
            for row in re.findall(r"\{([^{}]*)\}", bank_body)]
    pal_body = body("ground_ripple_pal")
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", pal_body)]
    nbanks = len(bank)
    nrot = 3
    pal = []
    i = 0
    for _k in range(nbanks):
        per = []
        for _g in (0, 1):
            rots = []
            for _r in range(nrot):
                rots.append(words[i:i + 16])
                i += 16
            per.append(rots)
        pal.append(per)
    rot_body = body("ground_ripple_rot")
    rot = [[int(x) for x in re.findall(r"\d+", row)]
           for row in re.findall(r"\{([^{}]*)\}", rot_body)]
    return bank, pal, rot


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    records, snaps, pals, slots, fix, census, worst = parse(probe)
    pngs = snap_pngs(snap_png)
    failures = []

    if not records:
        failures.append("probe wrote no input records")
        return 1
    for tag in ("TITLE", "WHOLE", "GONE"):
        if tag not in snaps:
            failures.append(f"the probe never snapshotted the {tag} frame")
    if len(pngs) < len(snaps):
        failures.append(f"only {len(pngs)} snapshot(s) for {len(snaps)} "
                        "SNAP records")
    if failures:
        print("FAIL ground:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    # the snapshot PNGs in the probe's SNAP order
    order = sorted(snaps.items(), key=lambda kv: kv[1][0])
    imgs = {tag: Image.open(pngs[i]).convert("RGB")
            for i, (tag, _) in enumerate(order) if i < len(pngs)}

    # ---- the generated art: palettes + picture ----
    # Task 19: the tiles use the 11 ripple banks; bank 8 keeps the whole/gone
    # marker (the PAL records above), so the clean band/shadow colours come
    # from the tile's ripple bank. The centred game never turns the dome (the
    # ship rests on cell 27, whose dome_angle is 0), so the displayed angle
    # and the previous frame's angle are both 0: rotation 0.
    pic = rs.ground_picture()          # palette indices, row 0 at GROUND_Y
    ripple_pic, _maj, _bank_of = rr.ripple_picture()
    ground_bank, ripple_pal, ripple_rot = _header_ripple()
    pal_rgb = [npal.neo_rgb(w) for w in pals["WHOLE"]]
    pal_rgb[0] = (0, 0, 0)             # index 0 is transparent (backdrop)
    ns_rgb = [npal.neo_rgb(w) for w in pals["GONE"]]
    ns_rgb[0] = (0, 0, 0)

    # 0. the dome's state at the snapshots: WHOLE must draw all its columns
    # (the sticky chain resolved: the driver's height, followers inherit),
    # and GONE must draw all its columns too — Task C1's ruin stands in the
    # dome's own 8 columns; the probe picks GONE on the ruin's SCB1 attribute
    # (PAL_RUIN << 8), and the ground bank is the plain shade because
    # dome_is_whole is 0 from the collapse's first split on.
    def dome_drawn(tag):
        raw = slots[tag]
        drawn = 0
        prev_h = 0
        for c in range(_SLOTS["DOME_COUNT"]):
            w3, _w4 = raw[_SLOTS["DOME_SPRITE"] + c]
            if w3 & 0x40:                       # sticky: inherits the height
                h = prev_h
            else:
                h = w3 & 0x3f
            prev_h = h
            drawn += 1 if h else 0
        return drawn
    wh = dome_drawn("WHOLE")
    gh = dome_drawn("GONE")
    if wh != _SLOTS["DOME_COUNT"]:
        failures.append(f"the WHOLE snapshot draws {wh} of the dome's "
                        f"{_SLOTS['DOME_COUNT']} columns (it must be whole)")
    if gh != _SLOTS["DOME_COUNT"]:
        failures.append(f"the GONE snapshot draws {gh} dome columns "
                        "(the ruin must be in all of the dome's columns)")
    print(f"dome columns drawn: WHOLE {wh}/{_SLOTS['DOME_COUNT']}, "
          f"GONE (ruin) {gh}/{_SLOTS['DOME_COUNT']}")

    # 1. the two palettes differ only in 8..14 (re-derived from the art).
    # The runtime's PAL records are the generated words the cartridge
    # wrote, so this also proves the header reached the hardware.
    pal = pals["WHOLE"]
    nosh = pals["GONE"]
    for i in range(16):
        if 7 < i <= 14:
            if pal[i] == nosh[i]:
                failures.append(f"palette entry {i} is the same in both; "
                                "the shadow needs its twin")
        elif pal[i] != nosh[i]:
            failures.append(f"palette entry {i} changed outside 8..14")
    for k in range(1, 8):
        if nosh[k + 7] != pal[k]:
            failures.append(f"ground_pal_noshadow[{k + 7}] {nosh[k + 7]:#06x} "
                            f"!= ground_pal[{k}] {pal[k]:#06x}")
    # the generated header's own words (the host test proves the header is
    # well-formed; here they must equal what the cart wrote)
    gen = _header_palettes()
    if pal != gen["ground_pal"]:
        failures.append("the WHOLE snapshot's ground bank is not the "
                        "generated ground_pal")
    if nosh != gen["ground_pal_noshadow"]:
        failures.append("the GONE snapshot's ground bank is not the "
                        "generated ground_pal_noshadow")
    print(f"runtime ground bank: WHOLE == ground_pal, "
          f"GONE == ground_pal_noshadow (16 words compared)")

    # 2. the clean band: every pixel equals the generated ripple picture's
    # colour through the tile's ripple bank (the displayed angle is 0, whole)
    y0, y1, x0, x1 = BAND
    im = imgs["WHOLE"]
    compared = 0
    mismatches = 0
    first = None
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            idx = int(ripple_pic[y - GROUND_Y][x])
            if idx == 0:
                want = npal.SKY_RGB
            else:
                bank = ground_bank[x // 16][(y - GROUND_Y) // 16]
                rot = ripple_rot[bank][0]
                want = npal.neo_rgb(ripple_pal[bank][0][rot][idx])
            got = _at(im, x, y)
            compared += 1
            if got != tuple(want):
                mismatches += 1
                if first is None:
                    first = (x, y, got, tuple(want))
    if mismatches:
        failures.append(f"the clean band y {y0}..{y1}, x {x0}..{x1}: "
                        f"{mismatches} of {compared} pixels differ from the "
                        f"ripple bank's colour (first {first})")
    print(f"clean band y {y0}..{y1}, x {x0}..{x1}: {compared} pixels compared "
          f"through the tile's ripple bank, {mismatches} mismatches "
          f"(the dome is whole, angle 0)")

    # 3. the shadow: 50 art shadow pixels, right of the dome, not covered
    # by any sprite (the ground's own slots excepted: the grass IS the
    # picture that carries the shadow) or by a fix tile (the WHOLE
    # snapshot's fix rows, dumped by the probe). Dome-scenery Task 7 adds
    # the console (slots 177..196): its 20 column boxes span y 176..223
    # across the whole width, but only the columns' own art is drawn there,
    # so a shadow pixel under a console BOX is still visible wherever the
    # column's picture is transparent — the console is excluded where its
    # generated picture is opaque (console_picture() != 0), and a pixel its
    # picture does not paint is still the grass. 850 art shadow pixels are
    # then uncovered on screen (668 of them right of x 225); the 50 picked
    # are the topmost of them.
    boxes = sprite_boxes(slots["WHOLE"])
    ground_slots = set(range(_SLOTS["GROUND_SPRITE"],
                             _SLOTS["GROUND_SPRITE"] + _SLOTS["GROUND_COUNT"]))
    fix_rows = fix.get("WHOLE", {})
    con_pic = rc.console_picture()
    con_slots = set(range(_SLOTS["CON_SPRITE"],
                          _SLOTS["CON_SPRITE"] + _SLOTS["CON_COUNT"]))
    shadow_px = []
    for y in range(GROUND_Y, GROUND_Y + GROUND_H):
        if y >= SCREEN_H:
            break
        for x in range(SHADOW_X0, SCREEN_W):
            idx = int(pic[y - GROUND_Y][x])
            if 8 <= idx <= 14 \
               and not covered(boxes, x, y, ground_slots | con_slots) \
               and not (con_pic[y, x] != 0) \
               and not fix_covers(fix_rows, x, y):
                shadow_px.append((x, y, idx))
                if len(shadow_px) == 50:
                    break
        if len(shadow_px) == 50:
            break
    if len(shadow_px) != 50:
        failures.append(f"only {len(shadow_px)} uncovered art shadow pixels "
                        "right of x 225; need 50")
    else:
        twin_ok, plain_ok = 0, 0
        bad = []
        for x, y, idx in shadow_px:
            ri = int(ripple_pic[y - GROUND_Y][x])
            bank = ground_bank[x // 16][(y - GROUND_Y) // 16]
            rot = ripple_rot[bank][0]
            twin = npal.neo_rgb(ripple_pal[bank][0][rot][ri])
            plain = npal.neo_rgb(ripple_pal[bank][1][rot][ri])
            got_whole = _at(imgs["WHOLE"], x, y)
            got_gone = _at(imgs["GONE"], x, y)
            if got_whole == tuple(twin):
                twin_ok += 1
            elif len(bad) < 5:
                bad.append((x, y, "WHOLE", got_whole, tuple(twin)))
            if got_gone == tuple(plain):
                plain_ok += 1
            elif len(bad) < 5:
                bad.append((x, y, "GONE", got_gone, tuple(plain)))
        if twin_ok != 50:
            failures.append(f"the dome whole: {twin_ok} of 50 shadow pixels "
                            f"show the twin colour (want 50) {bad}")
        if plain_ok != 50:
            failures.append(f"the dome gone: {plain_ok} of 50 shadow pixels "
                            f"show the plain shade (want 50) {bad}")
        print(f"shadow pixels: 50 picked right of x {SHADOW_X0 - 1} "
              f"(visible above the console's own art), through the tile's "
              f"ripple bank: {twin_ok} show the twin with the dome whole, "
              f"{plain_ok} show the plain shade with it gone")
        if bad:
            print(f"  samples: {bad}")

    # 4. the title: the grass is drawn under the title at the fresh game's
    # state (angle 0, dome whole), so (10, 150) is the generated picture's
    # colour through the tile's ripple bank.
    title = _at(imgs["TITLE"], 10, 150)
    idx = int(ripple_pic[150 - GROUND_Y][10])
    bank = ground_bank[10 // 16][(150 - GROUND_Y) // 16]
    rot = ripple_rot[bank][0]
    want_title = npal.neo_rgb(ripple_pal[bank][0][rot][idx])
    if title != tuple(want_title):
        failures.append(f"title pixel (10,150) is {title}, not the grass's "
                        f"{tuple(want_title)} (the ground is drawn under the "
                        "title at angle 0)")
    print(f"title pixel (10, 150): {title} == the grass's "
          f"{tuple(want_title)} (bank {bank}, rot {rot}, index {idx})")

    # 5. sprites per scanline: the census's raw worst dump must agree with
    # the per-frame count, and the line must be inside the ground's band
    # (the ground adds a sprite to every line y GROUND_Y..223).
    if len(census) < CENSUS_MIN:
        failures.append("the probe wrote no sprite census")
    if worst is None:
        failures.append("the probe never found a worst scanline")
    else:
        wc = worst[1]
        wl = worst[2]
        # the raw dump carries only SCB3 words (X does not matter for a
        # scanline count): resolve the sticky chains exactly as the probe
        # did and recount the line.
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
        if wl < GROUND_Y:
            failures.append(f"the worst line {wl} is above the ground's band "
                            f"({GROUND_Y}): the ground adds a sprite to every "
                            "line it covers, so the worst should be in it")
        print(f"sprites per scanline: worst {wc} at line {wl} (cart frame "
              f"{worst[0]}), under the hardware's {SCAN_MAX}; the ground "
              f"adds {rs.GROUND_COLS} on lines {GROUND_Y}..{SCREEN_H - 1}")

    if failures:
        print("FAIL ground:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS ground: clean band matches the art, shadow twin/plain "
          "counts 50/50, title grass drawn, worst scanline stated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
