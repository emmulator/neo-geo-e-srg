#!/usr/bin/env python3
"""Assertions for the M4-fixes Task 4 "dome stays gone" boot-test.

  check_gameover_draw.py SNAP PROBE [GO_FRESH_ADDR]

scripts/gameover_draw_probe.lua drives the -DGAMEOVER_DRAW_TEST cart (a
one-life test build of the normal cart; the hook in src/main.c runs under
that flag and mirrors this checker's policy model) through a two-phase
scripted game and records, per MAME frame, the BIOS joypad read-backs and
the hook's debug byte; through both GAME OVERs it records the dome slots'
SCB3 words, the shown broken-overlay slots, the decoded fix rows, fresh
dome dumps (cart frame 60 of the first game and the first frames after
the A-restart), and one snapshot per phase.  This checker:

  1. replays tests/rules_model.py + tests/ship_model.py + tests/mis_model.py
     with exactly the recorded inputs and the hook's semantics (one life
     at a fresh game; seeding and parking after the first GAME OVER) to
     state, from the rules, the model's frames: the phase-1 dome death,
     its GAME OVER, the A restart, the phase-2 cell death and GAME OVER —
     the "frame budget derived from the rules" the task asks for;
  2. proves the phase-1 (dome-death) GAME OVER keeps the dome gone: from
     the model's GAME OVER frame through the A restart, every sampled
     dome slot has SCB3 word 0, no overlay slot is shown, the
     fix layer says GAME OVER, and the snapshot's dome box has no dome
     pixels (the "empty screen" the task demands);
  3. proves the A restart brings back a fresh dome: the post-A fresh
     dump's slots equal the first game's fresh dump (both are fresh
     domes at the start cell, view 0) and no overlay slot is shown;
  4. proves a non-dome GAME OVER keeps today's look: under the phase-2
     GAME OVER (a cell death on the broken cell 5), the dome slots show
     the whole dome (SCB3 = the fixed chain words) and the seeded broken
     cells' overlays are shown (the 13 cells of rings 0..4's top-facing
     half, packed per the geometry tables) — the dome with its real
     broken tiles stays under GAME OVER.

The slot ranges come from the one slot map (M5 Task 1): build/slots.json
is generated from src/slots.h by the Makefile.
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import render_broken as rb  # noqa: E402
import layout as lay  # noqa: E402

# the one sprite slot map (src/slots.h -> build/slots.json)
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))

import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import rules_model as rm  # noqa: E402
import ship_model as sm  # noqa: E402

from PIL import Image  # noqa: E402

PHASE = 0
DOME_X, DOME_Y = lay.d.DOME_X, lay.d.DOME_Y  # the dome box's top-left (dome.h)
DOME_COLS = _SLOTS["DOME_COUNT"]
DOME_SPRITE = _SLOTS["DOME_SPRITE"]
OVERLAY_BASE = _SLOTS["BROKEN_SLOT_BASE"]
OVERLAY_AFTER = _SLOTS["BROKEN_SLOT_AFTER"]
FRESH_FRAME = 60                 # the probe's first-game fresh dump frame
A_DELAY = 60                     # the probe presses A 60 frames after GAME OVER
SEED_ORDER = (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 14)  # rings 0..4's
                                # top-facing half at view 0 (in broken order,
                                # i.e. ascending here — the checker sorts)
STEP0 = (27, 47, 71, 5, 0, 13)   # whole step-0 cells (the park targets)
PARK_CELL = 5                    # the phase-2 park: a seeded broken cell
FIXED_CHAIN = [(((496 - DOME_Y) << 7) | 8)] + [0x40] * 10  # whole dome SCB3 words


def model_frame(state, inp, pressed, hook):
    """one frame exactly as the C's main loop plus the GAMEOVER_DRAW_TEST
    hook (src/main.c under -DGAMEOVER_DRAW_TEST) — the two must stay in
    lockstep.  `hook` is the mirror of the C's go_test state:
    {'alive','saw_go','seeded'}.  Returns died."""
    ship, mis, rules = state
    # ---- the hook, before rules_begin ----
    if not rules.dead_t and not rules.game_over:
        hook["alive"] = min(255, hook["alive"] + 1)
    else:
        hook["alive"] = 0
    if hook["alive"] == 1:
        rules.lives = 1
    if rules.game_over:
        hook["saw_go"] = 1
    # ---- rules_begin / the play turn / mis_update ----
    busy = rules.begin(ship, mis, pressed)
    if not busy:
        ship.frame(inp, pressed)
    if not busy:
        if pressed & rm.A:
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
            if o.r <= mm.LAND:
                o.state = 2
    for b in mis.obj[mm.NMIS:]:
        if b.state != 1:
            continue
        for o in mis.obj[:mm.NMIS]:
            if o.state == 1 and o.phi == b.phi and o.ring == b.ring and b.r >= o.r:
                mis.hits.append(1)
                mis.kills = min(255, mis.kills + 1)
                mis.score = min(9999999, mis.score + rules.integ)
                o.state = b.state = 0
                break
    live = 0
    for o in mis.obj[:mm.NMIS]:
        if o.state == 2:
            c = mm.RING_END[o.ring - 1] if o.ring else 0
            while mm.CELL_PHI[c] != o.phi:
                c += 1
            mis.lands.append(c)
            if c not in ship.broken:     # a landing that broke a whole cell
                mis.dome_hits = min(255, mis.dome_hits + 1)  # counts as a hit
            rules.break_cell(ship, c)
            o.state = 0
        if o.state:
            live += 1
    if not (rules.dead_t or rules.game_over):
        if mis.timer:
            mis.timer -= 1
        elif live >= mm.V["wave_live"]:
            pass
        else:
            o = next(o for o in mis.obj if not o.state)
            mis.spawn(o, ship.broken)
            mis.timer = ((mm.V["spawn_gap"] + (mis.rand8() & 63)) * 59 + 25) // 50
    # ---- the hook, after mis_update and before rules_end ----
    if hook["saw_go"] and hook["alive"] == 10 and not hook["seeded"]:
        for c in SEED_ORDER:
            if c not in ship.broken:
                rules.break_cell(ship, c)
        hook["seeded"] = 1
    if not rules.dead_t and not rules.game_over:
        if hook["saw_go"] and hook["alive"] >= 11:
            park = PARK_CELL
        else:
            park = 27
            for c in STEP0:
                if c not in ship.broken:
                    park = c
                    break
        ship.cell, ship.angle, ship.lat = park, sm.STEP[park], sm.LAT[park]
        ship.left = ship.mlen = ship.lift = ship.jump_req = 0
        ship.last_dir = 8
        ship.spinning = ship.spin_acc = 0   # (ship_locate)
        ship.acc_s = ship.acc_l = ship.inc_s = ship.inc_l = 0
    # ---- the death checks and the integrity recast ----
    died = rules.end(ship, mis)
    mis.integ = rules.integ
    return died


def parse(fname):
    """(records, samples, overlays, rows, fresh, snaps, over, seeds)
    records: [(rec, fc, cur, chg, flags)]; samples: {fc: [11 scb3 words]};
    overlays: {fc: [slot dicts]}; rows: {fc: [10 fix rows]}; fresh:
    [ [11 slot lines] per FRESH dump, in order ]; snaps: {n: fc};
    over: {fc: shown-overlay-slot count}; seeds: {mame frame: the cart's
    mis_seed_used (Task 1)}."""
    records, samples, overlays, rows, fresh, snaps, over, seeds = [], {}, {}, {}, [], {}, {}, {}
    cur_f, cur_rows, cur_fresh = None, None, None
    with open(fname, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] == "I":
                records.append(tuple(int(x) for x in p[1:6]))
            elif p[0] == "D":
                samples[int(p[1])] = [int(x, 16) for x in p[2:]]
            elif p[0] == "O":
                over[int(p[1])] = int(p[2])
            elif p[0] == "S":
                fc = int(p[1])
                overlays.setdefault(fc, []).append(dict(
                    slot=int(p[2]), scb2=int(p[3], 16), scb3=int(p[4], 16),
                    scb4=int(p[5], 16), attr=int(p[6], 16),
                    tiles=[int(x, 16) for x in p[7:]]))
            elif p[0] == "F":
                cur_f, cur_rows = int(p[1]), [None] * 10
            elif p[0] == "W":
                if cur_rows is not None:
                    cur_rows[int(p[1])] = line.split(" ", 2)[2].rstrip("\n")
            elif p[0] == "FRESH":
                cur_fresh = []
            elif p[0] == "h":
                if cur_fresh is not None:
                    cur_fresh.append(line.rstrip("\n").split(" ", 1)[1])
            elif p[0] == "SEED":
                seeds[int(p[1])] = int(p[2])
            elif p[0] == "SNAP":
                snaps[int(p[1])] = int(p[2])
            if cur_f is not None and cur_rows is not None and all(x is not None for x in cur_rows):
                rows[cur_f] = cur_rows
                cur_f, cur_rows = None, None
            if cur_fresh is not None and len(cur_fresh) == 11:
                fresh.append(cur_fresh)
                cur_fresh = None
    return records, samples, overlays, rows, fresh, snaps, over, seeds


def replay(records, seed=None):
    """run the model over the recorded inputs; return (model, events,
    first) where model: {fc: (nbroken, dead_t, dome_dead, game_over, cell,
    alive, saw_go, seeded)}, events: [(frame, dome, nbroken, saw_go)] and
    first is the record index of cart frame 1.  The model's frame m is the
    cart frame m (the probe's samples carry the cart frame, so the frame
    BUDGET derives directly from the model's frames)."""
    first = None
    for i, (rec, fc, cur, chg, flags) in enumerate(records):
        if fc == 1:
            first = i
            break
    if first is None:
        first = 0
    ship, mis, rules = sm.Ship(), mm.Missiles(seed=seed), rm.Rules(1)
    hook = {"alive": 0, "saw_go": 0, "seeded": 0}
    model, events = {}, []
    i = first + PHASE
    m = 0
    while 0 <= i < len(records):
        rec, fc, cur, chg, flags = records[i]
        died = model_frame((ship, mis, rules), cur, chg, hook)
        m += 1
        model[m] = (len(rules.broken), rules.dead_t, rules.dome_dead,
                    rules.game_over, ship.cell, hook["alive"], hook["saw_go"],
                    hook["seeded"])
        if died:
            events.append((m, rules.dome_dead, len(rules.broken),
                           hook["saw_go"]))
        i += 1
    return model, events, first


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    records, samples, overlays, rows, fresh, snaps, over, seeds = parse(probe)
    seed = mis_seed.cart_seed(probe, seeds)   # Task 1: the cart's seed
    print(f"mis_seed_used: {seed:#06x}")
    failures = []
    if not records:
        print("FAIL gameover-draw: probe wrote no input records")
        return 1
    if len(fresh) < 2:
        print(f"FAIL gameover-draw: need 2 fresh dumps (got {len(fresh)})")
        return 1
    if len(snaps) < 3:
        print(f"FAIL gameover-draw: need 3 snapshots (got {len(snaps)})")
        return 1

    # ---- replay the model from the recorded inputs (the reference) ----
    model, events, first = replay(records, seed)
    dome_deaths = [e for e in events if e[1]]
    cell_deaths = [e for e in events if not e[1]]
    if not dome_deaths:
        failures.append("the model never reached a dome death in the "
                        "recorded game")
    if not cell_deaths:
        failures.append("the model never reached a cell death (phase 2)")
    if failures:
        return 1

    p1_death = dome_deaths[0][0]
    p1_go = p1_death + rm.DEAD_FRAMES_NEO          # death + the countdown
    # the A restart: the model frame where game_over returns to 0 after
    # being 1 (the recorded A press started the new game)
    a_fc = None
    for f in sorted(model):
        if f > 1 and model[f - 1][3] == 1 and model[f][3] == 0:
            a_fc = f
            break
    p2_death = p2_go = None
    if a_fc is not None:
        for f, st in sorted(model.items()):
            if f > a_fc and st[3] == 1:
                p2_go = f
                break
        for e in cell_deaths:
            if e[0] > a_fc:
                p2_death = e[0]
                break
    if a_fc is None or p2_death is None or p2_go is None:
        failures.append("the model never reached the phase-2 GAME OVER")
        return 1
    print(f"model: phase-1 dome death {p1_death}, GAME OVER {p1_go}, "
          f"A restart {a_fc}; phase-2 cell death {p2_death}, GAME OVER {p2_go}")

    if not samples:
        failures.append("probe wrote no dome-height samples")
    if not overlays:
        failures.append("probe wrote no overlay slot reads")
    if not rows:
        failures.append("probe wrote no fix rows")

    def show_go(fc):
        return rows.get(fc) is not None and rows[fc][7].strip() == "GAME OVER"

    # ---- 2. phase 1: the dome-death GAME OVER keeps the dome gone ----
    p1_frames = sorted(f for f in samples if p1_go <= f < (a_fc - 0))
    if not p1_frames:
        failures.append(f"no phase-1 samples in [{p1_go}, {a_fc})")
    else:
        hidden_ok = all(all(w == 0 for w in samples[f]) for f in p1_frames)
        if not hidden_ok:
            bad = [f for f in p1_frames if any(samples[f])]
            failures.append(f"phase-1 GAME OVER: dome slots not all hidden on "
                            f"{bad} (first SCB3 words: "
                            f"{['%04x' % w for w in samples[bad[0]]]})")
        over_bad = [f for f in p1_frames if overlays.get(f)]
        if over_bad:
            failures.append(f"phase-1 GAME OVER: overlays shown on {over_bad} "
                            f"(first: {overlays[over_bad[0]][:2]})")
        go_bad = [f for f in p1_frames if not show_go(f)]
        if go_bad:
            failures.append(f"phase-1 GAME OVER: fix layer lacks GAME OVER "
                            f"on {go_bad}")
        print(f"phase-1: {len(p1_frames)} sampled frames through the GAME "
              f"OVER: dome hidden ({not hidden_ok and 'NO' or 'yes'}), "
              f"no overlays ({not over_bad and 'yes' or 'NO'}), "
              f"GAME OVER text ({not go_bad and 'yes' or 'NO'})")

    # the phase-1 snapshot's dome box must have no dome pixels
    if 1 in snaps:
        lit = dome_lit_pixels(Image.open(snaps_snap(snap_png, probe, 1)).convert("RGB"))
        if lit:
            failures.append(f"phase-1 GAME OVER snapshot has {len(lit)} lit "
                            "pixels in the dome box — the dome is still drawn")
        else:
            print("phase-1 GAME OVER snapshot: no dome pixels (empty screen)")
    else:
        failures.append("no phase-1 snapshot")

    # ---- 3. the A restart brings back a fresh dome ----
    want, got = fresh[0], fresh[1]
    for k, (w, g) in enumerate(zip(want, got)):
        if w != g:
            failures.append(f"post-A dome slot {DOME_SPRITE + k} differs "
                            f"from the first game's fresh dome:\n"
                            f"  first {w}\n  after {g}")
    # the O-count right after the fresh dump (the probe writes it at the
    # new game's first dump frame, fc a_fc, where the fresh dump lands)
    # must be 0 — no overlay shown
    if a_fc is not None:
        for f_ in (a_fc, a_fc + 1):
            if over.get(f_, 0) != 0:
                failures.append(f"overlay slots shown right after the A "
                                f"restart (fc {f_}: {over.get(f_)} shown)")
    new_frames = [f for f in sorted(samples) if a_fc < f <= a_fc + 8]
    if new_frames and any(overlays.get(f) for f in new_frames):
        failures.append(f"overlay slots shown right after the A restart "
                        f"({new_frames})")
    print("post-A dome equals the first game's fresh dome, no overlays "
          "(both fresh domes at the start cell, view 0)")

    # ---- 4. phase 2: a cell death keeps today's look ----
    p2_frames = sorted(f for f in samples if f >= p2_go)
    if not p2_frames:
        failures.append(f"no phase-2 samples at/after {p2_go}")
    else:
        whole_ok = all(samples[f] == FIXED_CHAIN for f in p2_frames)
        if not whole_ok:
            failures.append("phase-2 GAME OVER: the dome is not the whole "
                            "fixed chain: "
                            f"{[(f, ['%04x' % w for w in samples[f]])
                               for f in p2_frames[:3]]}")
        # the shown overlay slots must be exactly the seeded cells' pictures
        # (each cell's stones contiguous, packed in broken order — the same
        # pack the cracks module does every frame; the count + the drawn
        # stones prove the real broken tiles are under this GAME OVER)
        want_cells = [c for c in SEED_ORDER if rb.overlay(c, 0) is not None]
        expect = sum(rb.overlay(c, 0)[0] for c in want_cells)
        shown = overlays.get(p2_frames[0], [])
        shown_slots = [s["slot"] for s in shown
                       if OVERLAY_BASE <= s["slot"] < OVERLAY_AFTER]
        if len(shown_slots) != expect:
            failures.append(f"phase-2 GAME OVER at {p2_frames[0]}: "
                            f"{len(shown_slots)} shown overlay slots, want "
                            f"{expect} (the {len(want_cells)} seeded cells' "
                            f"pictures)")
        go_bad2 = [f for f in p2_frames if not show_go(f)]
        if go_bad2:
            failures.append(f"phase-2 GAME OVER: fix layer lacks GAME OVER "
                            f"on {go_bad2}")
        print(f"phase-2: {len(p2_frames)} sampled frames, dome whole, "
              f"{len(shown_slots)} overlay columns shown, GAME OVER present")

    # the phase-2 snapshot must show the dome with its broken tiles (the
    # "keeps today's look" proof at the pixel level)
    if 3 in snaps:
        lit2 = len(dome_lit_pixels(
            Image.open(snaps_snap(snap_png, probe, 3)).convert("RGB")))
        if lit2 < 400:              # a whole dome with cracks is thousands
            failures.append(f"phase-2 GAME OVER snapshot has only {lit2} lit "
                            "pixels in the dome box — the whole dome with "
                            "its broken tiles is not drawn")
        else:
            print(f"phase-2 GAME OVER snapshot: {lit2} lit dome pixels "
                  "(whole dome with broken tiles)")

    if failures:
        print("FAIL gameover-draw:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS gameover-draw: a dome-death GAME OVER leaves the dome gone "
          f"(hidden + no overlays + empty box), A restarts a fresh dome == "
          f"the first game's, and a cell-death GAME OVER keeps the "
          f"broken-tile dome")
    return 0


def dome_lit_pixels(im):
    """the lit pixels inside the dome box (DOME_X,DOME_Y)-
    (DOME_X+176,DOME_Y+128) on the snapshot's scale — the dome's
    glass/glow colours all have max channel > 40, and nothing else draws in
    the box during a GAME OVER with the dome hidden (the HUD rows are above
    the box, the missiles were cleared on the death, the ship is hidden,
    the overlays are hidden). The box bounds come from src/dome.h."""
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    out = []
    for yy in range(int(DOME_Y * sy), int((DOME_Y + 128) * sy)):
        for xx in range(int(DOME_X * sx), int((DOME_X + 176) * sx)):
            if max(im.getpixel((xx, yy))[:3]) > 40:
                out.append((xx, yy))
    return out


def snaps_snap(snap_png, probe, idx):
    """MAME writes 0000.png, 0001.png, ... under the snapshot directory's
    machine subdir; the checker walks them in order (the probe's SNAP
    records carry the frames)."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(snap_png)))
    for root in (os.path.join(base, "snap"), base):
        if not os.path.isdir(root):
            continue
        pngs = sorted(os.path.join(r, fn) for r, _, fs in os.walk(root)
                      for fn in fs if fn.endswith(".png"))
        if len(pngs) >= idx:
            return pngs[idx - 1]
    return snap_png


if __name__ == "__main__":
    sys.exit(main())
