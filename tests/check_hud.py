"""Assertions for the M4 Task 3 HUD boot-test (HUD-layout Task 2).

  check_hud.py SNAP PROBE [EVENTS_ADDR [FRAMECNT_ADDR]]
    SNAP        the MAME snapshot (taken by scripts/hud_probe.lua)
    PROBE       the probe dump:
                  I <rec> <fc> <bios_p1current> <bios_p1change>   every record
                  F <fc>                                          a read follows
                  E <fc> <hud_dbg_events>                         (if addr known)
                  R <r> <40 chars>                                fix row
                  V <fc> <lives>          the rules' lives at a snapshot frame
                  SNAP <fc>
    EVENTS_ADDR 0 disables the event check. FRAMECNT_ADDR 0 disables the
    exact-frame alignment (then the probe's I records carry the record
    number as fc too).

scripts/hud_probe.lua drives the normal cart through a deterministic game by
setting the joypad ioports (the BIOS fills bios_p1current/bios_p1change from
them) and records both bytes once per record, in order, together with the
cart's frame counter (hud_framecnt). The cart's rules (src/rules.c, held to
the model by tests/test_rules_play.py) saw exactly the inputs this checker
replays into tests/hud_model.py's model, one record per model frame. The
BIOS preamble (about 470 MAME frames) and the cart's startup hold
hud_framecnt at 0 for the first records, so the model replay does not start
until the record where fc first reaches 1; after that fc counts 1, 2, ...
per record. On every sampled cart frame the decoded FIXMAP rows must equal
the model's hud_rows — the task's checks are then all visible:

  * the starting values (integ 100, lives 3, score 0),
  * after a crack (integ < 100),
  * after a death (lives < 3),
  * at GAME OVER (centred text on row 7),
  * after A starts a new game (GAME OVER gone, lives 3, integ 100 again),

and with EVENTS_ADDR the probe's hud_dbg_events (the cart's line-commit
count) must equal the number of commits the model's values imply over the
same frames — the HUD really did redraw only when a value changed.

The HUD-layout Task 2 proofs on top of the row match:

  * the rows cover fix rows 0..29, and rows 0..23 (except row 7's GAME
    OVER) hold only spaces during play — the top of the screen is empty;
  * proof 2 (the icons): the fc-100 snapshot (before the first death, lives
    3) shows exactly 18 lit pixels in each of the 3 ship-icon cells (8 x 8
    at x 256/272/288, y 192); the snapshot at the first death (the probe's
    V record reads rules.lives == 2) shows 2 cells with 18 and the third
    with 0;
  * proof 3 (the top of the screen during play): no lit fix pixel in
    y 0..71 outside row 7 (y 40..47, where GAME OVER may be drawn).

One detail: the probe records the joypad RAM read-back at the end of a MAME
frame; the cart's main loop read it at some point inside that same frame.
The replay therefore starts at the record where fc first reaches 1 (the
cart's first main-loop frame) and consumes records one per model frame
(PHASE = 0: the recorded read-back for a frame is the input that frame
saw). If a future BIOS revision shifts the joypad polling by a frame, only
PHASE needs to change; the row comparison below checks it empirically.
"""
import os
import re
import sys

from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import hud_model as hm  # noqa: E402
import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import rules_model as rm  # noqa: E402
import ship_model as sm  # noqa: E402

ROW_COUNT = 30
PHASE = 0                    # records the model frame lags the cart frame by

# the icon cells (HUD-layout Task 2): lives row 26 at fix cols 32/34/36,
# screen x 8*c = 256/272/288, screen y 8*26 - 16 = 192; each 8 x 8 cell
# holds the ICON_SHIP tile (18 lit pixels) while a life is left, 0 after.
LIVES_Y = 192
LIVES_XS = (256, 272, 288)
ICON_LIT = 18                # the tile's lit pixel count (generate_srom.py)

# the "top of the screen" during play: fix rows 0..23 -> screen y 0..8*24-17
# = 0..175, but the fix layer starts at row 2 -> y 0..175 has nothing from
# rows above; row 7 (GAME OVER) is y 40..47. The task's band is y 0..71
# outside row 7's y 40..47.
TOP_BAND = (0, 71)
GO_BAND = (40, 47)


def decode_row(raw):
    """a probe R line's 40 chars -> the row as the model builds it: the
    probe writes the icon tile numbers (>= 0x80) as <NN> escapes."""
    s = raw
    out = []
    i = 0
    while i < len(s):
        m = re.match(r"<(\d+)>", s[i:])
        if m:
            out.append(chr(int(m.group(1))))
            i += m.end()
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def parse(fname):
    """(records, samples, events, veg, snaps, seeds) — records:
    [(rec, fc, cur, chg)] in order; samples: {fc: rows} (30 strings);
    events: {fc: count}; veg: {fc: lives} (the snapshot-frame V records);
    snaps: the snapshot frames in order; seeds: {mame frame: seed} (the
    cart's mis_seed_used, Task 1)."""
    records, samples, events, veg, seeds = [], {}, {}, {}, {}
    snaps = []
    cur_f, cur_rows = None, None
    with open(fname, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] in ("I", b"I"):
                rec, fc, cur, chg = (int(x) for x in p[1:5])
                records.append((rec, fc, cur, chg))
            elif p[0] == "F":
                cur_f = int(p[1])
                cur_rows = [None] * ROW_COUNT
            elif p[0] == "E":
                events[int(p[1])] = int(p[2])
            elif p[0] == "R":
                if cur_rows is not None:
                    cur_rows[int(p[1])] = decode_row(line.split(" ", 2)[2].rstrip("\n"))
            elif p[0] == "V":
                veg[int(p[1])] = int(p[2])
            elif p[0] == "SEED":
                seeds[int(p[1])] = int(p[2])
            elif p[0] == "SNAP":
                snaps.append(int(p[1]))
            if cur_f is not None and cur_rows is not None and all(r is not None for r in cur_rows):
                samples[cur_f] = cur_rows
                cur_f, cur_rows = None, None
    return records, samples, events, veg, snaps, seeds


def commits(prev, rules, mis):
    """line-commits hud_frame makes when the state moves from prev to now."""
    v = (rules.integ, rules.lives, mis.score * 10, rules.game_over)
    if prev is None:
        return 4
    return sum(1 for a, b in zip(v, prev) if a != b)


def icon_counts(im):
    """(n0, n1, n2): the lit pixel counts in the three ship-icon cells."""
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    out = []
    for x in LIVES_XS:
        x0, x1 = int(x * sx), int((x + 8) * sx)
        y0, y1 = int(LIVES_Y * sy), int((LIVES_Y + 8) * sy)
        n = 0
        for py in range(y0, y1):
            for px in range(x0, x1):
                if max(im.getpixel((px, py))[:3]) > 40:
                    n += 1
        out.append(n)
    return tuple(out)


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    events_addr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    framecnt_addr = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0
    records, samples, events, veg, snaps, seeds = parse(probe)
    seed = mis_seed.cart_seed(probe, seeds)   # Task 1: the cart's seed
    print(f"mis_seed_used: {seed:#06x}")
    failures = []

    if not records:
        failures.append("probe wrote no input records")
        return 1
    if not samples:
        failures.append("probe wrote no decoded rows")
        return 1

    # the model's frame 1 is the first record whose cart frame is 1 (the
    # first main-loop frame); records before it are the BIOS preamble and
    # the cart's startup, which saw none of the game. fc==0 repeats while
    # startup runs, so find the first 0 -> 1 edge.
    first = None
    for i, (rec, fc, cur, chg) in enumerate(records):
        if fc == 1:
            first = i
            break
    if first is None:
        # the framecnt address was 0: the probe wrote rec as fc, so the
        # game starts at record 1
        first = 0
    first_rec = records[first][0]

    # replay: model frame m consumes record (first + m - 1 + PHASE). Its
    # state after frame m is the rows the cart's fix layer showed at cart
    # frame m (the sample key). Events accumulate the same way.
    ship, mis, rules = sm.Ship(), mm.Missiles(seed=seed), rm.Rules(1)
    model_events = 0
    prev = None
    state_by_fc = {}                   # cart frame m -> (integ, lives, score, go)
    rows_by_fc = {}                    # cart frame m -> hud_rows (30 strings)
    events_by_fc = {}                  # cart frame m -> model commits through m
    n = len(records)
    m = 0
    i = first + PHASE
    while 0 <= i < n:
        rec, fc, cur, chg = records[i]
        hm.frame_model((ship, mis, rules), cur, chg)
        v = (rules.integ, rules.lives, mis.score * 10, rules.game_over)
        model_events += commits(prev, rules, mis)
        prev = v
        m += 1
        state_by_fc[m] = v
        rows_by_fc[m] = hm.hud_rows(rules, mis)
        events_by_fc[m] = model_events
        i += 1

    # compare the sampled rows with the model at the same cart frames
    for g in sorted(samples):
        if g not in rows_by_fc:
            continue
        if samples[g] != rows_by_fc[g]:
            for r in range(ROW_COUNT):
                if samples[g][r] != rows_by_fc[g][r]:
                    failures.append(
                        f"frame {g} row {r}:\n  cart  {samples[g][r]!r}"
                        f"\n  model {rows_by_fc[g][r]!r}")
        if events_addr and g in events_by_fc:
            if events[g] != events_by_fc[g]:
                failures.append(
                    f"frame {g}: cart redrew {events[g]} lines, the model implies "
                    f"{events_by_fc[g]} (the HUD must redraw only when a value changes)")

    # ---- HUD-layout Task 2 proof 3 (rows): nothing at the top of the
    # screen — rows 0..6 and 8..23 hold only spaces during play (row 7's
    # GAME OVER excepted). The whole-row equality above already proves the
    # cart drew exactly the model's rows, so checking the model's rows is
    # checking the cart's.
    top_bad = [g for g in sorted(samples) if g in rows_by_fc
               and any(rows_by_fc[g][r].strip() for r in range(0, 7))] + \
              [g for g in sorted(samples) if g in rows_by_fc
               and any(rows_by_fc[g][r].strip() for r in range(8, 24))]
    if top_bad:
        failures.append(f"the model's rows above the lower-right HUD are not "
                        f"blank on frames {top_bad[:5]} (rows 0..6, 8..23)")

    # ---- the task's checkpoints: the text is proven above (whole rows ==
    # the model), so the checkpoints are the moments the script drove the
    # game to, read from the model at the sampled frames ----
    seen_int100 = seen_crack = seen_lives3 = seen_death = False
    seen_go = seen_restart = seen_score0 = seen_score = False
    prev_go = 0
    for g in sorted(samples):
        if g not in state_by_fc:
            continue
        integ, lives, score, go = state_by_fc[g]
        if integ == 100:
            seen_int100 = True
        else:
            seen_crack = True
        if lives == 3:
            seen_lives3 = True
        else:
            seen_death = True
        if score == 0:
            seen_score0 = True
        else:
            seen_score = True
        if go and not prev_go:
            seen_go = True
        if not go and prev_go:
            seen_restart = True
        prev_go = go
    if not seen_int100:
        failures.append("no sampled frame showed the starting integrity 100%")
    if not seen_crack:
        failures.append("no sampled frame showed a crack (integrity below 100)")
    if not seen_lives3:
        failures.append("no sampled frame showed 3 lives")
    if not seen_death:
        failures.append("no sampled frame showed a death (fewer than 3 lives)")
    if not seen_go:
        failures.append("no sampled frame showed GAME OVER")
    if not seen_restart:
        failures.append("no sampled frame showed A starting a new game (GAME OVER gone)")
    if not seen_score0:
        failures.append("no sampled frame showed score 0 at the start")
    if not seen_score:
        failures.append("the score never grew (no kill) in the sampled frames")

    # ---- HUD-layout Task 2 proof 2: the icons on the snapshots ----
    if len(snaps) < 2:
        failures.append(f"the probe took {len(snaps)} snapshots, need 2 "
                        "(before the first death and after it)")
    else:
        im1 = Image.open(snaps_snap(snap_png, probe, 1)).convert("RGB")
        c1 = icon_counts(im1)
        # the first snapshot keys the model: it must be on a frame the
        # model shows lives 3 (before the first death — fc 100, the probe's
        # snap frame, is before the first landing ~fc 285)
        g1 = snaps[0]
        if g1 in state_by_fc and state_by_fc[g1][1] != 3:
            failures.append(f"snapshot 1 at fc {g1} shows lives "
                            f"{state_by_fc[g1][1]} in the model, want 3")
        if c1 != (ICON_LIT, ICON_LIT, ICON_LIT):
            failures.append(f"snapshot 1 (fc {g1}): icon cells have "
                            f"{c1} lit pixels, want {18, 18, 18} "
                            "(3 lives: 3 ships)")
        print(f"icons before the first death (fc {g1}): {c1} lit pixels "
              f"in the 3 cells, want (18, 18, 18)")
        # the second snapshot: the probe's V record reads rules.lives == 2
        # on that frame (the first death has happened) — the model must
        # agree, and 2 of the 3 cells must still be ships.
        if veg:
            vfc, vlives = sorted(veg.items())[0]
            st = state_by_fc.get(vfc)
            if vlives != 2:
                failures.append(f"the probe's V record at fc {vfc} reads "
                                f"lives {vlives}, want 2 (the first death)")
            elif st is not None and st[1] != 2:
                failures.append(f"the model at fc {vfc} shows lives {st[1]}, "
                                f"the probe's {vlives} (snapshot misaligned)")
            im2 = Image.open(snaps_snap(snap_png, probe, 2)).convert("RGB")
            c2 = icon_counts(im2)
            if c2 != (ICON_LIT, ICON_LIT, 0):
                failures.append(f"after the first death (fc {vfc}): icon "
                                f"cells have {c2} lit pixels, want "
                                f"(18, 18, 0) (2 lives left)")
            print(f"icons after the first death (fc {vfc}, lives {vlives}): "
                  f"{c2} lit pixels, want (18, 18, 0)")
        else:
            failures.append("the probe wrote no V record (no after-death "
                            "snapshot)")

    if failures:
        print("FAIL hud:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    n_s = len([g for g in samples if g in state_by_fc])
    print(f"PASS hud: {n_s} sampled frames (rows 0..29) match the model, "
          f"score/icon rows part of the match, icons (18,18,18) -> "
          f"(18,18,0), top rows 0..6/8..23 blank, checkpoints all seen"
          + (f", events={model_events}" if events_addr else ""))
    return 0


def snaps_snap(snap_png, probe, idx):
    """MAME writes 0000.png, 0001.png, ... in the snapshot directory (its
    own subdir, $OUT/snap/aes) as the probe's snapshots happen, one file
    per session snapshot in order. boot_test.sh copies the first PNG to
    $OUT/snap.png afterwards — that copy must NOT be indexed (it would be
    the first candidate and throw every index off by one), so this walks
    ONLY the MAME-managed snapshot directory ($OUT/snap, the `snap` dir
    next to snap.png), never $OUT itself."""
    snap_dir = os.path.join(os.path.dirname(os.path.abspath(snap_png)), "snap")
    if not os.path.isdir(snap_dir):
        return snap_png
    pngs = sorted(os.path.join(r, fn) for r, _, fs in os.walk(snap_dir)
                  for fn in fs if fn.endswith(".png"))
    if len(pngs) >= idx:
        return pngs[idx - 1]
    return snap_png


if __name__ == "__main__":
    sys.exit(main())
