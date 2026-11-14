"""Assertions for the dome-scenery Task 19 grass-ripple boot-test.

  check_ripple.py SNAP PROBE

scripts/ripple_probe.lua boots the normal cart and plays the props leg's
spin (climb to the peak, turn the dome left through a whole turn, back right
to 0, then the centred game with A every 11 frames) until the first dome
death's collapse, so the whole/gone palette state is seen too. It records
every play frame's shown palette (bank 8 and the 11 ripple banks 44..54),
every palette write to those banks with its raster line, the ground's 160
SCB1 words, and three snapshots during the left turn.

This checker proves, against build/ground_map.h and the assembled C ROM:

  1. every play frame's 11 ripple banks equal
     ground_ripple_pal[k][gone][ground_ripple_rot[k][prev_da]], with gone
     read from bank 8 (the whole/gone marker) and prev_da the previous
     frame's dome_angle (the one-frame lag src/ground.c has, like the props);
  2. every palette write to bank 8 or 44..54 happens before the first grass
     line GROUND_Y + 16, and states the latest raster line seen;
  3. a frame whose dome_angle did not change writes no ripple word (except
     a whole/gone change, which writes the 148-word full set), and states
     the worst words in a frame;
  4. the 160 ground tiles' SCB1 attributes are RIPPLE_PAL_BANK +
     ground_bank[col][row] and their tile numbers are the header's unchanged
     col * GROUND_ROWS + row plus the part base;
  5. every ground pixel that no other sprite or fix tile covers, in each of
     the three snapshots, equals the C ROM tile's pixel through the tile's
     ripple bank at the snapshot's prev_da (expected thousands per snapshot;
     fewer than 1000 fails).

The generated header is the one the cartridge was built with; the checker
parses the built build/ground_map.h rather than carrying a copy.
"""
import json
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import neo_palette as npal     # noqa: E402

GROUND_MAP_H = os.path.join(ROOT, "build", "ground_map.h")
RADAR_MAP_H = os.path.join(ROOT, "build", "radar_map.h")
SCREEN_W, SCREEN_H = 320, 224
PAL_GROUND = 8                 # src/ground.h: the whole/gone marker
RIPPLE_PAL_BANK = 44           # src/ground.h RIPPLE_PAL_BANK
MIN_PIXELS = 1000


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


def _array_body(name):
    txt = open(GROUND_MAP_H).read()
    m = re.search(r"%s\[[^=]*= \{(.*?)\};" % name, txt, re.S)
    assert m, f"{name} missing from build/ground_map.h"
    return m.group(1)


def _u16_array(name, shape):
    body = _array_body(name)
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", body)]
    assert len(words) == int(np.prod(shape)), (name, len(words), shape)
    return np.array(words, np.uint16).reshape(shape)


def _u8_array(name, shape):
    body = _array_body(name)
    vals = [int(x) for x in re.findall(r"\d+", body)]
    assert len(vals) == int(np.prod(shape)), (name, len(vals), shape)
    return np.array(vals, np.uint8).reshape(shape)


def parse(fname):
    r, pw, g, snaps, xs, fix = {}, {}, {}, [], {}, {}
    pc_in_cart = 0
    for line in open(fname, encoding="latin-1"):
        p = line.split()
        if not p:
            continue
        if p[0] == "R":
            fc, da, prev = int(p[1]), int(p[2]), int(p[3])
            words = [int(x, 16) for x in p[4:]]
            assert len(words) == 12 * 16, (fc, len(words))
            b8 = words[:16]
            banks = [words[16 + 16 * k:16 + 16 * (k + 1)] for k in range(11)]
            r[fc] = {"da": da, "prev": prev, "b8": b8, "banks": banks}
        elif p[0] == "PW":
            fc = int(p[1])
            pw[fc] = (int(p[2]), int(p[3]), int(p[4]))
        elif p[0] == "G":
            g[(int(p[1]), int(p[2]))] = (int(p[3], 16), int(p[4], 16))
        elif p[0] == "SNAP":
            snaps.append({"tag": p[1], "n": int(p[2]), "fc": int(p[3]),
                          "da": int(p[4]), "prev": int(p[5])})
        elif p[0] == "X":
            xs.setdefault(p[1], {})[int(p[2])] = (
                int(p[3], 16), int(p[4], 16), int(p[5], 16))
        elif p[0] == "F":
            parts = line.rstrip("\n").split(" ", 3)
            fix.setdefault(parts[1], {})[int(parts[2])] = parts[3]
        elif p[0].startswith("pc_in_cart="):
            pc_in_cart = 1
    return r, pw, g, snaps, xs, fix, pc_in_cart


def snap_pngs(snap_png):
    snap_dir = os.path.join(os.path.dirname(os.path.abspath(snap_png)), "snap")
    if not os.path.isdir(snap_dir):
        return [snap_png]
    pngs = sorted(os.path.join(r, fn) for r, _, fs in os.walk(snap_dir)
                  for fn in fs if fn.endswith(".png"))
    return pngs or [snap_png]


def _at(im, x, y):
    w, h = im.size
    return tuple(im.getpixel((int(x * w / SCREEN_W),
                              int(y * h / SCREEN_H)))[:3])


def sprite_boxes(raw):
    """slot -> (x, y, w, h) for every drawn slot, with the sticky chains and
    both shrink coefficients resolved the way the hardware does: a sticky
    slot inherits the previous slot's Y/height/vzoom, sits 16 px right, and
    keeps its own hzoom.  SCB2 0 hides a slot."""
    boxes = {}
    prev = None                      # (x, top, h, vzoom)
    for s in range(381):
        scb2, scb3, scb4 = raw[s]
        h = scb3 & 0x3f
        vz = scb2 & 0xff
        hz = (scb2 >> 8) & 0xf
        if scb3 & 0x40 and prev is not None:
            x, top, h, vz = prev[0] + 16, prev[1], prev[2], prev[3]
        else:
            x = (scb4 >> 7) & 0x1ff
            top = 496 - (scb3 >> 7)
        prev = (x, top, h, vz)
        if h == 0 or scb2 == 0:
            continue
        lines = (h * 16 * (vz + 1) + 255) // 256
        boxes[s] = (x, top, hz + 1, lines)
    return boxes


def covered(boxes, x, y, skip_slots):
    for s, (bx, by, bw, bh) in boxes.items():
        if s in skip_slots:
            continue
        if bx <= x < bx + bw and by <= y < by + bh:
            return True
    return False


def fix_covers(fix_rows, x, y):
    r = (y + 16) // 8
    c = x // 8
    row = fix_rows.get(r)
    return bool(row and c < len(row) and row[c] != " ")


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    d = _defines(GROUND_MAP_H)
    ground_y = d["GROUND_Y"]
    ground_rows = d["GROUND_ROWS"]
    ground_cols = d["GROUND_COLS"]
    nbanks = d["RIPPLE_BANKS"]
    nrot = d["RIPPLE_NROT"]
    assert nbanks == 11 and nrot == 3
    ground_bank = _u8_array("ground_bank", (ground_cols, ground_rows))
    ripple_pal = _u16_array("ground_ripple_pal", (nbanks, 2, nrot, 16))
    ripple_rot = _u8_array("ground_ripple_rot", (nbanks, 240))
    ground_pal = _u16_array("ground_pal", (16,))
    ground_noshadow = _u16_array("ground_pal_noshadow", (16,))

    radar = _defines(RADAR_MAP_H)
    tile_base = radar["RADAR_HEAD_TILE_BASE"] + radar["RADAR_HEAD_TILES"]

    slots = json.load(open(os.path.join(ROOT, "build", "slots.json")))
    ground_first = slots["GROUND_SPRITE"]
    ground_count = slots["GROUND_COUNT"]
    ground_slots = set(range(ground_first, ground_first + ground_count))

    r, pw, g, snaps, xs, fix, pc_in_cart = parse(probe)
    failures = []

    if not pc_in_cart:
        failures.append("the 68k never reached cart space")
    if not r:
        failures.append("the probe wrote no per-frame palette records (R)")
    if failures:
        print("FAIL ripple:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    # ---- 1. every play frame's shown ripple banks ----
    gone_of = {}
    frames_compared = 0
    bank_mismatches = []           # the first 8, as examples
    n_bank_mismatches = 0          # all of them
    for fc in sorted(r):
        rec = r[fc]
        b8 = rec["b8"]
        if b8 == ground_pal.tolist():
            gone = 0
        elif b8 == ground_noshadow.tolist():
            gone = 1
        else:
            failures.append(f"fc {fc}: bank 8 is neither ground_pal nor "
                            "ground_pal_noshadow")
            gone = None
        gone_of[fc] = gone
        if gone is None:
            continue
        prev = rec["prev"]
        if not (0 <= prev < 240):
            failures.append(f"fc {fc}: prev_da {prev} is outside 0..239")
            continue
        for k in range(nbanks):
            rot = int(ripple_rot[k][prev])
            want = ripple_pal[k][gone][rot]
            got = rec["banks"][k]
            frames_compared += 1
            if got != want.tolist():
                bad = [(e, got[e], int(want[e]))
                       for e in range(16) if got[e] != want[e]]
                n_bank_mismatches += 1
                if len(bank_mismatches) < 8:
                    bank_mismatches.append((fc, k, prev, rot, bad))
        # also prove the bank-8 marker is one of the two generated words
        if b8 != ground_pal.tolist() and b8 != ground_noshadow.tolist():
            pass

    if bank_mismatches:
        failures.append(f"{n_bank_mismatches} ripple-bank frame mismatches "
                        f"of {frames_compared} banks compared "
                        f"(examples {bank_mismatches[:4]})")
    print(f"ripple banks: {len(r)} play frames compared, "
          f"{frames_compared} bank-words compared (11 banks x {len(r)} frames)")

    # state the frames compared: the whole turn left (da rises), back right
    # (da falls), and the gone frames.
    fcs = sorted(r)
    rising = [fc for fc in fcs if r[fc]["da"] > r[fc]["prev"]]
    falling = [fc for fc in fcs if r[fc]["da"] < r[fc]["prev"]]
    steady = [fc for fc in fcs if r[fc]["da"] == r[fc]["prev"]]
    gone_frames = [fc for fc in fcs if gone_of[fc] == 1]
    print(f"  turn left: {len(rising)} rising frames "
          f"(fc {rising[0]}..{rising[-1]})" if rising else "  turn left: 0")
    print(f"  turn right: {len(falling)} falling frames "
          f"(fc {falling[0]}..{falling[-1]})" if falling else "  turn right: 0")
    print(f"  steady-angle frames: {len(steady)}; gone frames: "
          f"{len(gone_frames)}"
          + (f" (fc {gone_frames[0]}..{gone_frames[-1]})" if gone_frames else ""))
    if max(r[fc]["da"] for fc in fcs) != 239:
        failures.append("the left turn never reached dome_angle 239")
    if not falling:
        failures.append("the dome never turned back right to 0")
    if not gone_frames:
        failures.append("the probe never saw the dome gone: no gone frames")

    # ---- 2. every play-frame palette write before the first grass line ----
    # ground_show (PW key 0) is the one-time show outside play frames: it
    # writes all 11 banks and bank 8 directly when the fresh scene (now the
    # title's too, attract A2) is shown, so it is reported separately, not
    # held to the commit rule.
    if not pw:
        failures.append("the probe recorded no palette writes (PW)")
        latest = None
    else:
        play_pw = {fc: v for fc, v in pw.items() if fc in r}
        if not play_pw:
            failures.append("the probe recorded no play-frame palette writes")
        latest = max((v for _r, _b, v in play_pw.values()), default=None)
        # held to the first grass line: the ripple banks' words only. Bank 8
        # is the whole/gone marker the probes read; no tile or fix row
        # draws with it since Task 19 (proof: the ground SCB1 check below),
        # so a late bank-8 write cannot tear anything. It stays a direct
        # write (Task 19's deviation) and its latest vpos is stated.
        late = [(fc, r_, b_, v) for fc, (r_, b_, v) in play_pw.items()
                if r_ and v >= ground_y + 16]
        if late:
            failures.append(f"{len(late)} play frames wrote a ripple-bank "
                            f"word at vpos >= GROUND_Y+16 ({ground_y + 16}): "
                            f"{late[:4]}")
        b8_late = [(fc, v) for fc, (r_, b_, v) in play_pw.items()
                   if b_ and not r_ and v >= ground_y + 16]
        if b8_late:
            print(f"  bank-8-only frames at vpos >= {ground_y + 16} (not "
                  f"drawn, so not held): {b8_late[:4]}")
        total = sum(r_ + b_ for r_, b_, _v in play_pw.values())
        show = pw.get(0)
        print(f"palette writes: {len(play_pw)} play frames, {total} words "
              f"(ripple + bank 8), latest vpos {latest} "
              f"(before GROUND_Y+16 = {ground_y + 16})")
        if show is not None:
            print(f"  ground_show (outside play frames): {show[0] + show[1]} "
                  f"words at vpos {show[2]} (the fresh scene's grass)")

    # ---- 3. unchanged-angle frames write nothing; the worst frame ----
    worst_ripple, worst_b8, worst_fc, worst_gone = 0, 0, None, False
    bad_steady = []
    missing_change = []
    for fc in sorted(r):
        rc, bc, _v = pw.get(fc, (0, 0, -1))
        da_changed = r[fc]["da"] != r[fc]["prev"]
        gone_changed = (fc + 1 in gone_of and gone_of[fc] is not None
                        and gone_of[fc + 1] is not None
                        and gone_of[fc + 1] != gone_of[fc])
        if da_changed or gone_changed:
            if rc == 0:
                missing_change.append(fc)
        else:
            if rc:
                bad_steady.append((fc, rc))
        if rc > worst_ripple:
            worst_ripple, worst_fc, worst_gone = rc, fc, gone_changed
        if bc > worst_b8:
            worst_b8 = bc
        if rc > 11 * 12:
            failures.append(f"fc {fc}: {rc} ripple words staged in one "
                            "commit (11 banks x 12 is the whole/gone change)")
        if bc > 16:
            failures.append(f"fc {fc}: {bc} bank-8 words in one frame (the "
                            "whole/gone switch is 16)")
    if bad_steady:
        failures.append(f"{len(bad_steady)} frames whose dome_angle did not "
                        f"change wrote ripple words: {bad_steady[:4]}")
    if missing_change:
        failures.append(f"{len(missing_change)} frames whose dome_angle or "
                        f"whole/gone state changed wrote no ripple word: "
                        f"{missing_change[:4]}")
    print(f"unchanged-angle frames: {len(steady) - len(bad_steady)} wrote no "
          f"ripple word; worst commit fc {worst_fc}: {worst_ripple} words"
          + (" (the whole/gone change)" if worst_gone else "")
          + f"; bank 8's separate switch: at most {worst_b8} words a frame")

    # ---- 4. the 160 ground tiles' SCB1 words ----
    if len(g) != ground_cols * ground_rows:
        failures.append(f"the probe dumped {len(g)} ground SCB1 rows, want "
                        f"{ground_cols * ground_rows}")
    bad_tiles = []
    checked_tiles = 0
    for c in range(ground_cols):
        slot = ground_first + c
        for row in range(ground_rows):
            got = g.get((slot, row))
            if got is None:
                bad_tiles.append((slot, row, "missing", None))
                continue
            want_tile = tile_base + c * ground_rows + row
            want_attr = (RIPPLE_PAL_BANK + int(ground_bank[c][row])) << 8
            checked_tiles += 1
            if got[0] != want_tile or got[1] != want_attr:
                bad_tiles.append((slot, row, got, (want_tile, want_attr)))
    if bad_tiles:
        failures.append(f"{len(bad_tiles)} ground SCB1 words differ from the "
                        f"header's banks/tile numbers: {bad_tiles[:4]}")
    print(f"ground SCB1: {checked_tiles} tile rows checked; every attribute "
          f"is RIPPLE_PAL_BANK + ground_bank, every tile number is the "
          f"unchanged col * GROUND_ROWS + row + {tile_base}")

    # ---- 5. the three snapshots' uncovered ground pixels ----
    pngs = snap_pngs(snap_png)
    if len(snaps) != 3:
        failures.append(f"the probe took {len(snaps)} snapshots, want 3")
    if len(pngs) < len(snaps):
        failures.append(f"only {len(pngs)} snapshot PNG(s) for {len(snaps)} "
                        "SNAP records")
    if failures:
        print("FAIL ripple:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    by_n = {s["n"]: s for s in snaps}
    for n in sorted(by_n):
        s = by_n[n]
        im = Image.open(pngs[n]).convert("RGB")
        raw = xs.get(s["tag"])
        if raw is None:
            failures.append(f"snapshot {s['tag']}: no slot dump (X)")
            continue
        boxes = sprite_boxes(raw)
        fix_rows = fix.get(s["tag"], {})
        gone = gone_of.get(s["fc"])
        if gone is None:
            failures.append(f"snapshot {s['tag']}: fc {s['fc']} has no R record")
            continue
        prev = s["prev"]
        compared = 0
        mismatches = 0
        first = None
        for y in range(ground_y, min(SCREEN_H, ground_y + ground_rows * 16)):
            for x in range(SCREEN_W):
                if covered(boxes, x, y, ground_slots):
                    continue
                if fix_covers(fix_rows, x, y):
                    continue
                c = x // 16
                r_ = (y - ground_y) // 16
                tx, ty = x % 16, (y - ground_y) % 16
                tile = g.get((ground_first + c, r_))
                if tile is None:
                    continue
                idx = int(npal.decode_tile(tile[0])[ty][tx])
                if idx == 0:              # transparent: the backdrop shows
                    continue
                bank = int(ground_bank[c][r_])
                rot = int(ripple_rot[bank][prev])
                want = npal.neo_rgb(int(ripple_pal[bank][gone][rot][idx]))
                got = _at(im, x, y)
                compared += 1
                if got != want:
                    mismatches += 1
                    if first is None:
                        first = (x, y, got, want, bank, idx)
        if compared < MIN_PIXELS:
            failures.append(f"snapshot {s['tag']} (fc {s['fc']}, prev_da "
                            f"{prev}): only {compared} uncovered ground "
                            f"pixels compared, want at least {MIN_PIXELS}")
        if mismatches:
            failures.append(f"snapshot {s['tag']} (fc {s['fc']}, prev_da "
                            f"{prev}): {mismatches} of {compared} uncovered "
                            f"ground pixels differ from the C ROM through "
                            f"the tile's ripple bank (first {first})")
        print(f"snapshot {s['tag']}: fc {s['fc']}, prev_da {prev}, gone {gone}: "
              f"{compared} uncovered ground pixels compared, "
              f"{mismatches} mismatches")

    if failures:
        print("FAIL ripple:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS ripple: every play frame's 11 banks match the header at the "
          "previous frame's angle, every write lands before the grass's first "
          "line, unchanged angles write nothing, the ground SCB1 words are "
          "the ripple banks, and the uncovered ground pixels match the C ROM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
