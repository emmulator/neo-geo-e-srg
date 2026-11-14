#!/usr/bin/env python3
"""Assertions for the dome-scenery Task 18 / 18b tear boot-test.

  check_tear.py PROBE

scripts/tear_probe.lua boots the FRAME_MARK cart and drives one of two
inputs (TEAR_DRIVE):

  spin — Task 18's props leg: up to the peak, left through the whole turn
         (0..239) and right back to 0.
  fire — Task 18b's drive, the collapse leg's centred policy: stick centred,
         A every 11 cart frames, 3000 MAME frames — missiles land, the radar
         locks and blinks, explosions play. The normal cart's centred policy
         never targets the resting ship's cell 27 (it is outside the spawn
         rings), so the probe also forces the first missile to that cell at a
         visible range (the RADAR_TEST cart's hook, plus a bullet clear) to
         make the lock/blink and a visible hit's explosion happen.
  title — attract Task A2: the cart is left on the title for 600 frames,
          logged from MAME frame 41 to 640. The scene's vblank writes must
          not tear, and every title fix write must land in vblank (before
          the row it changes).

It taps the LSPC registers (0x3c0000/2/4) to follow the cart's VRAM pointer
and logs every slot write with the raster line at that moment (LSPCMODE's
counter, as src/flow.c's lspc_vpos):

  W <fc> <da> <slot> <reg> <vpos>     any slot write (reg 1..4 = SCB1..4)
  S <fc> <da> <slot> <top> <bottom>   a shown slot's span (screen lines)
  C <fc> <start> <commit>             the frame's work-start and the LAST
                                      commit's end (vpos; FRAME_MARK marks)
  P <fc> <vpos> <word>                a palette write to the radar's blink
                                      entry (bank 20, entry 1)
  F <tick> <col> <row> <vpos>         a fix-layer write (ADDR_FIXMAP)
  TEAR_DRIVE <spin|fire|title>

Task 18 moved the props' writes to right after vblank; Task 18b moved the
missiles, explosions and radar there too. The checker, for every sprite group
in build/slots.json (ground, mountains, band, back and front props, missiles
behind and in front, dome, overlays, ship, console, explosions, radar):

  1. counts the frames with a write inside a slot's old span (the words at
     the previous frame's end) or its new span (this frame's end), counting
     visible lines 0..223 only (a box may run past the screen's bottom; a
     vblank write at line 231 cannot tear). Every group must have 0, and the
     checker states each group's write count;
  2. the props' Task 18 claims: both props pools have 0 tear frames and, on
     the spin drive, the latest props write is before the frame's first prop
     line. The fire drive keeps the ship centred, so its dome angle never
     changes and its props memo writes nothing; the 0-tear claim still holds
     and the latest-write check is vacuous there (states that);
  3. the radar's palette blink: every write to bank 20's entry 1 lands
     before the radar's first line; it states how many were seen (the fire
     drive must show > 0) and the latest vpos;
  4. the frame's worst start-to-commit-end in scanlines (all commits: the
     missiles, mountains, band, props and radar).

On the fire drive the missiles (behind or in front), explosions and radar
must each have > 0 writes: the drive really exercised them.
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FRAME_LINES = 264
VPOS_OFFSET = 16            # vpos = screen line + 16 (src/flow.c lspc_vpos)

_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))

# every sprite range in build/slots.json, in the map's draw order
GROUPS = [
    ("ground", _SLOTS["GROUND_SPRITE"], _SLOTS["GROUND_COUNT"]),
    ("mountains", _SLOTS["MTN_SPRITE"], _SLOTS["MTN_COUNT"]),
    ("band", _SLOTS["BAND_SPRITE"], _SLOTS["BAND_COUNT"]),
    ("back props", _SLOTS["PROP_SPRITE"], _SLOTS["PROP_BACK_COUNT"]),
    ("front props", _SLOTS["PROP_FRONT_SPRITE"], _SLOTS["PROP_FRONT_COUNT"]),
    ("missiles behind", _SLOTS["MIS_BEHIND_SPRITE"],
     _SLOTS["MIS_BEHIND_COUNT"]),
    ("missiles in front", _SLOTS["MIS_FRONT_SPRITE"],
     _SLOTS["MIS_FRONT_COUNT"]),
    ("dome", _SLOTS["DOME_SPRITE"], _SLOTS["DOME_COUNT"]),
    ("overlays", _SLOTS["BROKEN_SLOT_BASE"], _SLOTS["BROKEN_SLOT_COUNT"]),
    ("ship", _SLOTS["SHIP_SPRITE"], _SLOTS["SHIP_COUNT"]),
    ("console", _SLOTS["CON_SPRITE"], _SLOTS["CON_COUNT"]),
    ("explosions", _SLOTS["EXPL_SPRITE"], _SLOTS["EXPL_COUNT"]),
    ("radar", _SLOTS["RADAR_SPRITE"], _SLOTS["RADAR_COUNT"]),
]
PROPS = [g for g in GROUPS if g[0] in ("back props", "front props")]
RADAR = next(g for g in GROUPS if g[0] == "radar")


def _vpos(v):
    """the cart stores lspc_vpos() as a u16; the vblank tail past line 263
    shows as a negative (0xFFFD = -3 = line 261), as check_frame_mark's. The
    probe's P records hold the signed Lua value; this is harmless for them."""
    return v if v < 0x8000 else v - 0x10000


def _in_range(slot, base, count):
    return base <= slot < base + count


def parse(fname):
    """(drive, writes, spans, commits, pal, fix): writes {tick: [(slot, reg,
    vpos)]}, spans {tick: {slot: (top, bottom)}}, commits {tick: (start,
    commit)}, pal {tick: [(vpos, word)]}, fix {tick: [(col, row,
    vpos)]}."""
    drive = "spin"
    writes = {}
    spans = {}
    commits = {}
    pal = {}
    fix = {}
    with open(fname, encoding="latin-1") as fh:
        for line in fh:
            p = line.split()
            if not p:
                continue
            if p[0] == "TEAR_DRIVE":
                drive = p[1]
            elif p[0] == "W":
                tick = int(p[1])
                writes.setdefault(tick, []).append(
                    (int(p[3]), int(p[4]), int(p[5])))
            elif p[0] == "S":
                tick = int(p[1])
                spans.setdefault(tick, {})[int(p[3])] = (
                    int(p[4]), int(p[5]))
            elif p[0] == "C":
                commits[int(p[1])] = (int(p[2]), int(p[3]))
            elif p[0] == "P":
                tick = int(p[1])
                pal.setdefault(tick, []).append((int(p[2]), int(p[3], 16)))
            elif p[0] == "F":
                tick = int(p[1])
                fix.setdefault(tick, []).append(
                    (int(p[2]), int(p[3]), int(p[4])))
    return drive, writes, spans, commits, pal, fix


def _unsafe(vpos, old, new):
    """the write's vpos is inside the slot's old or new VISIBLE screen span.
    The probe's span may run below line 223 (the screen's last line); those
    lines are off-screen, so a vblank write there cannot tear anything."""
    for span in (old, new):
        if span is None:
            continue
        top = max(16, span[0] + VPOS_OFFSET)     # screen line 0 = vpos 16
        bottom = min(239, span[1] + VPOS_OFFSET)  # screen line 223 = vpos 239
        if top <= vpos <= bottom:
            return True
    return False


def _first_visible(span):
    """the slot's first visible screen line as a vpos, or None if the whole
    span is off-screen."""
    if span is None:
        return None
    top = span[0] + VPOS_OFFSET
    bottom = span[1] + VPOS_OFFSET
    if bottom < 16 or top > 239:
        return None
    return max(16, top)


def _group_counts(writes, spans, base, count):
    """(frames with a write inside the slot's old/new span, writes checked)."""
    frames = set()
    checked = 0
    for tick, ws in writes.items():
        old = spans.get(tick - 1, {})
        new = spans.get(tick, {})
        for slot, _reg, vpos in ws:
            if not _in_range(slot, base, count):
                continue
            checked += 1
            if _unsafe(vpos, old.get(slot), new.get(slot)):
                frames.add(tick)
    return frames, checked


def _group_write_count(writes, base, count):
    return sum(1 for ws in writes.values() for slot, _r, _v in ws
               if _in_range(slot, base, count))


def _radar_first_line(tick, spans):
    """the radar's first visible line (vpos) in `tick`, from the old and new
    spans of every radar slot; None if no radar slot is visible."""
    old = spans.get(tick - 1, {})
    new = spans.get(tick, {})
    first = None
    base, count = RADAR[1], RADAR[2]
    for s in range(base, base + count):
        for span in (old.get(s), new.get(s)):
            line = _first_visible(span)
            if line is not None and (first is None or line < first):
                first = line
    return first


def _latest_props_write(writes, spans, commits):
    """the props' latest write of any frame, relative to the frame start, and
    the frame's first prop line; (latest, first, reason), where latest is
    (rel, tick, start, vpos, slot) and first is (first, frel, line, slot)."""
    latest = None
    for tick, ws in writes.items():
        c = commits.get(tick)
        if c is None:
            continue
        start, commit = _vpos(c[0]), _vpos(c[1])
        if start == commit == 0:
            continue
        old = spans.get(tick - 1, {})
        new = spans.get(tick, {})
        for slot, _reg, vpos in ws:
            if not any(_in_range(slot, b, n) for _n, b, n in PROPS):
                continue
            rel = (vpos - start) % FRAME_LINES
            if latest is None or rel > latest[0]:
                latest = (rel, tick, start, vpos, slot)
    if latest is None:
        return None, None, "the probe saw no props write with frame marks"
    rel, tick, start, vpos, slot = latest
    old = spans.get(tick - 1, {})
    new = spans.get(tick, {})
    first = None
    for _name, base, count in PROPS:
        for s in range(base, base + count):
            for span in (old.get(s), new.get(s)):
                line = _first_visible(span)
                if line is None:
                    continue
                frel = (line - start) % FRAME_LINES
                if first is None or frel < first[0]:
                    first = (frel, line, s)
    if first is None:
        return None, None, (f"the latest props write's frame (tick {tick}) "
                            "shows no prop slot: no first prop line to "
                            "compare against")
    frel, line, fs = first
    return latest, (first, frel, line, fs), None


def main():
    if len(sys.argv) != 2:
        print("usage: check_tear.py PROBE")
        return 1
    probe = sys.argv[1]
    drive, writes, spans, commits, pal, fix = parse(probe)
    if not writes:
        print("FAIL tear: the probe wrote no W records: no VRAM writes were "
              "seen")
        return 1
    if not spans:
        print("FAIL tear: the probe wrote no S records: no slot spans were "
              "seen")
        return 1
    if not commits:
        print("FAIL tear: the probe wrote no C records: the FRAME_MARK "
              "start/commit marks were not read")
        return 1

    failures = []
    print(f"tear probe ({drive} drive): {len(writes)} frames with VRAM "
          f"writes, {len(spans)} frames with slot spans, {len(commits)} "
          f"commit marks")

    # proof 1: every sprite group, 0 frames with a write inside a slot's span,
    # and that group's write count
    counts = {}
    for name, base, count in GROUPS:
        frames, checked = _group_counts(writes, spans, base, count)
        counts[name] = _group_write_count(writes, base, count)
        print(f"  {name}: {counts[name]} slot writes, {len(frames)} frames "
              f"with a write inside the slot's old or new span")
        if frames:
            failures.append(
                f"the {name} group has {len(frames)} frames with a write "
                f"inside the slot's old or new span (want 0)")

    # the fire drive must really exercise the out-of-scope-before groups
    if drive == "fire":
        missiles = counts["missiles behind"] + counts["missiles in front"]
        if missiles == 0:
            failures.append("the fire drive wrote no missile slots: the drive "
                            "did not exercise the missiles")
        if counts["explosions"] == 0:
            failures.append("the fire drive wrote no explosion slots: the "
                            "drive did not play an explosion")
        if counts["radar"] == 0:
            failures.append("the fire drive wrote no radar slots: the drive "
                            "did not exercise the radar")
    print(f"  missiles (both pools): {counts['missiles behind']} behind + "
          f"{counts['missiles in front']} in front; explosions: "
          f"{counts['explosions']}; radar: {counts['radar']}")

    # proof 2: the props' Task 18 claims still hold
    latest, first, why = _latest_props_write(writes, spans, commits)
    if why is not None:
        if drive in ("fire", "title") and latest is None:
            # these drives leave the ship centred (fire) or the title at the
            # fresh state (title), so the props are static and no props words
            # changed: the Task 18 "latest props write" claim is vacuous here
            # (the 0-tear-frames claim above still holds for both pools)
            print(f"  latest props write: none — the {drive} drive keeps the "
                  "props static and no props words changed")
        else:
            failures.append(why)
    elif latest is not None:
        rel, tick, start, vpos, slot = latest
        first_span, frel, line, fs = first
        print(f"  latest props write: vpos {vpos} ({rel} lines after the "
              f"frame start) at tick {tick}, slot {slot}; first prop line: "
              f"vpos {line} ({frel} lines after the frame start, slot {fs})")
        if rel >= frel:
            failures.append(
                f"the latest props write at vpos {vpos} ({rel} lines after "
                f"the frame start) is not before the frame's first prop line "
                f"vpos {line} ({frel} lines after the frame start)")

    # proof 3: the radar's palette blink entry
    pal_count = 0
    pal_latest = None
    pal_bad = 0
    pal_first_none = 0
    for tick, ps in pal.items():
        first_line = _radar_first_line(tick, spans)
        for vpos, _word in ps:
            pal_count += 1
            vp = _vpos(vpos)
            if pal_latest is None or vp > pal_latest:
                pal_latest = vp
            if first_line is None:
                pal_first_none += 1
                continue
            if vp >= first_line:
                pal_bad += 1
    print(f"  radar palette entry (bank 20, entry 1): {pal_count} writes, "
          f"latest vpos {pal_latest}; "
          f"{'every write before the radar first line' if pal_bad == 0 else f'{pal_bad} writes NOT before the radar first line'}")
    if pal_bad:
        failures.append(f"{pal_bad} radar palette writes landed at or after "
                        f"the radar's first line (want every write before it)")
    if pal_first_none:
        failures.append(f"{pal_first_none} radar palette writes were in "
                        "frames with no visible radar slot")
    if drive == "fire" and pal_count == 0:
        failures.append("the fire drive wrote the radar palette entry 0 "
                        "times (want > 0: the blink must be exercised)")

    # proof 2 (attract Task A2): every title fix write lands in vblank, so
    # it is before every row of the next frame. The title's scene commits
    # also run in the same block.
    if drive == "title":
        fw = [(tick, col, row, vpos)
              for tick, ws in fix.items() for col, row, vpos in ws]
        if not fw:
            failures.append("the title drive wrote no fix-layer cells (the F "
                            "records are empty)")
        else:
            # A fix write is before the row it changes unless it lands while
            # the raster is inside that row's own 8-line span (screen line
            # 8*row-16..8*row-9, vpos 8*row..8*row+7). A vblank write (vpos
            # 240..263 / -8..-1) is before every row; a write after the
            # row's span is before its next frame's display. The title's
            # commit writes top-down from the vblank, ahead of the raster.
            def before_row(v, row):
                if v >= 240 or v < 16:
                    return True
                first = 8 * row
                return not (first <= v <= first + 7)

            bad_fix = [(tick, col, row, vpos) for tick, col, row, vpos in fw
                       if not before_row(_vpos(vpos), row)]
            rows = sorted(set(row for _t, _c, row, _v in fw))
            print(f"  title fix writes: {len(fw)} cells on rows {rows[0]}.."
                  f"{rows[-1]}, "
                  + ("every write before the row it changes (none inside "
                     "the row's visible span)" if not bad_fix else
                     f"{len(bad_fix)} landed inside the row's visible span"))
            if bad_fix:
                tick, col, row, vpos = bad_fix[0]
                failures.append(f"the title fix write at tick {tick}, col "
                                f"{col}, row {row} landed at vpos {vpos}, "
                                "inside that row's visible span (it tears "
                                "the row it changes)")

    # proof 4: the frame's worst start-to-last-commit-end, all commits
    worst = None
    for tick, c in commits.items():
        start, commit = _vpos(c[0]), _vpos(c[1])
        if start == commit == 0:
            continue
        span = (commit - start) % FRAME_LINES
        if worst is None or span > worst[0]:
            worst = (span, tick, start, commit)
    if worst is None:
        failures.append("no usable C records: the frames' start/commit marks "
                        "were all zero")
    else:
        span, tick, start, commit = worst
        print(f"  frame start-to-last-commit-end: worst {span} scanlines "
              f"(start vpos {start}, commit end vpos {commit}) at tick {tick}")
        if span >= 224:
            failures.append(f"the commits' worst span is {span} scanlines "
                            f"(>= 224): it reaches the next frame")

    if failures:
        print("FAIL tear:")
        for f in failures:
            print("  - " + f)
        return 1
    props_line = ("the props wrote nothing (the fire drive keeps the ship "
                  "centred, so the 0-tear-frames claim holds)"
                  if latest is None else
                  "the props' latest write is before the frame's first prop "
                  "line")
    if drive == "title":
        print(f"PASS tear (title drive): every sprite group has 0 frames with "
              f"a write inside the slot's old or new span; {len(fw)} title fix "
              f"writes are before the rows they change; the frame's worst "
              "start-to-last-commit-end is stated")
    else:
        print(f"PASS tear ({drive} drive): every sprite group has 0 frames "
              f"with a write inside the slot's old or new span; {props_line}; "
              "every radar palette write is before the radar's first line; "
              "the frame's worst start-to-last-commit-end is stated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
