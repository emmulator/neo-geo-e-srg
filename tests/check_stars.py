#!/usr/bin/env python3
"""Assertions for the M5 Task 2 stars boot-test.

  check_stars.py SNAP PROBE [ANGLE_ADDR [FRAMECNT_ADDR]]

scripts/stars_probe.lua boots the normal cart, holds the stick right (so the
ship spins the dome, moving the stars) and samples 100 cart frames. For
each sample it records the ship's dome_angle read from RAM (ANGLE_ADDR, the
address of the static `ship` in build/rom.elf) and reads every star slot's
SCB4 X, SCB3 Y and height straight out of VRAM. This checker:

  1. replays tests/ship_model.py from the probe's recorded inputs to state
     the ship's dome_angle on every sampled cart frame, and proves the
     probe's RAM reading equals it (the RAM address is found from the real
     ELF via m68k-neogeo-elf-nm in boot_test.sh — neither side is fixed);
  2. reads the star table (tests/stars_model.py, the reference) and, for
     every sample and every star, computes (x, y) = stars_pos(i, angle) and
     proves the VRAM's SCB4 >> 7 and 496 - (SCB3 >> 7) equal them exactly,
     and the height field is 1 (a 1-tile sprite);
  3. proves no star is inside the dome box (x 72..247, y 72..199): the box
     is the one thing the stars must never overlap (their y is at most 68
     by construction — the band's bottom is DOME_Y - 4 — so a star drawn
     low would fail here even if its X matched the table);
  4. proves the samples' dome_angle values are not all equal: the star
     motion exists to be tested, and if the stick-right policy failed to
     spin the dome the sample would be a single angle.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import layout as lay  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
# the one sprite slot map (src/slots.h -> build/slots.json)
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))
STAR_SPRITE = _SLOTS["STAR_SPRITE"]
NSTARS = _SLOTS["NSTARS"]

import ship_model as sm  # noqa: E402
import stars_model as stm  # noqa: E402

DOME_BOX = lay.d.DOME_BOX        # src/dome.h: the 176x128 box on screen
DOME_Y = lay.d.DOME_Y
NSAMPLES = 100


def parse(fname):
    """(records, samples) — records: [(rec, fc, cur, chg)]; samples:
    {fc: {'angle': int, 'slots': {slot: (x, y, h)}}}."""
    records, samples = [], {}
    cur = None
    with open(fname, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] == "I":
                records.append(tuple(int(x) for x in p[1:5]))
            elif p[0] == "A":
                cur = {"angle": int(p[2]), "slots": {}}
                samples[int(p[1])] = cur
            elif p[0] == "S":
                if cur is not None:
                    cur["slots"][int(p[1])] = (int(p[2]), int(p[3]), int(p[4]))
    return records, samples


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    angle_addr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    fc_addr = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0
    records, samples = parse(probe)
    failures = []

    if not records:
        failures.append("probe wrote no input records")
        return 1
    if len(samples) != NSAMPLES:
        failures.append(f"probe sampled {len(samples)} frames, want {NSAMPLES}")
        return 1
    if angle_addr == 0:
        failures.append("no ship RAM angle address (m68k-neogeo-elf-nm failed?)")
        return 1

    # The recorded input read-backs are the reference (as the hud/collapse
    # checkers replay the same records through the model). The probe's RAM
    # angle is what the cart actually ran; the model must agree on every
    # sampled frame. The replay runs the ship model with the rules model
    # (mis_update's launches consume RNG that the ship's rest/spin does not
    # depend on, but the model framework is the same as the other checkers).
    #
    # the model's frame 1 is the first record whose cart frame is 1 (the
    # first main-loop frame); records before it are the BIOS preamble (the
    # hud_framecnt at 0 for the first records, exactly as check_hud.py).
    import mis_model as mmm  # noqa: E402
    import mis_seed  # noqa: E402  (Task 1: the cart's seed)
    import rules_model as rmm  # noqa: E402
    PHASE = 0
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
    mangle = {}
    n = len(records)
    m = 0
    i = first + PHASE
    while 0 <= i < n:
        rec, fc, cur, chg = records[i]
        m += 1
        # one frame exactly as tests/check_hud.py's frame_model (the full
        # rules; the ship's angle is what the stars turn with). The cart's
        # sample reads fc and the angle at the same instant, after that
        # frame's logic ran (hud_frame, which owns hud_framecnt, runs after
        # ship_frame), so the model's angle is recorded AFTER the frame,
        # like the state the other checkers record.
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
                    mis.hits.append(1)
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
        rules.end(ship, mis)
        mis.integ = rules.integ
        mangle[m] = ship.angle       # after the frame: the angle the stars
                                     # showed on frame m (the cart's sample)
        i += 1

    for fc, s in sorted(samples.items()):
        want_a = mangle.get(fc)      # keyed by the model's frame == cart fc
        if want_a is None:
            failures.append(f"the model never reached cart frame {fc}")
            continue
        if s["angle"] != want_a:
            failures.append(f"frame {fc}: RAM dome_angle {s['angle']}, "
                            f"the model's is {want_a}")

    # ---- 2 + 3. every star slot holds stars_pos exactly; none in the dome box
    bx0, by0, bx1, by1 = DOME_BOX
    all_angles = set()
    box_target = 4                  # stars are behind the dome: ≥4 frames with
                                    # a star over the dome-box x-range is expected
    for fc, s in sorted(samples.items()):
        all_angles.add(s["angle"])
        for i in range(NSTARS):
            slot = STAR_SPRITE + i
            if slot not in s["slots"]:
                failures.append(f"frame {fc}: star slot {slot} not read")
                continue
            x, y, h = s["slots"][slot]
            wx, wy = stm.pos(i, s["angle"])
            if x != wx or y != wy:
                failures.append(f"frame {fc} star {i} (slot {slot}): VRAM "
                                f"({x},{y}), stars_pos({wx},{wy})")
            if h != 1:
                failures.append(f"frame {fc} star {i}: height {h}, want 1")
            if bx0 <= x <= bx1 and by0 <= y <= by1:
                failures.append(f"frame {fc} star {i}: inside the dome box "
                                f"({x},{y})")

    # ---- 4. the dome really turned ----
    if len(all_angles) < 2:
        failures.append(f"samples covered only {len(all_angles)} dome_angle"
                        " value(s) — the star motion was not exercised")

    # ---- the star y-range: above the dome box, by construction ----
    # the band spans DOME_Y-4-60 .. DOME_Y-4-3 by the table's own y_v span
    # (the topmost star's 60, the lowest's 3): 8..65 at DOME_Y 72. The
    # band's bottom is the header's DOME_Y - 4, so the checks follow the
    # dome's position (a star drawn low would still fail the box check).
    ys = [stm.y(i) for i in range(NSTARS)]
    top, bottom = stm.BAND_BOTTOM - 60, stm.BAND_BOTTOM - 3
    if min(ys) < top or max(ys) > bottom:
        failures.append(f"star y range {min(ys)}..{max(ys)} outside the "
                        f"constructed band {top}..{bottom} "
                        "(the table's own span, DOME_Y - 4 minus 60..3)")
    if failures:
        print("FAIL stars:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS stars: {len(samples)} samples, {len(all_angles)} distinct "
          f"dome_angles, every star slot == stars_pos (SCB4 X, SCB3 Y, "
          f"height 1), none in the dome box, RAM angle == the model's")
    return 0


if __name__ == "__main__":
    sys.exit(main())
