#!/usr/bin/env python3
"""Assertions for the M5 Task 4 radar boot-test (proof 2).

  check_radar.py SNAP PROBE [MIS_ADDR [SHIP_ADDR [FRAMECNT_ADDR]]]

scripts/radar_probe.lua boots the -DRADAR_TEST cart (its first missile of
each game is forced to target the ship's start cell 27, so with no input
the ship rests on that cell and the lock-on happens by itself — see the
flag's comment in src/main.c), plays ~2400 MAME frames, and on every cart
frame reads from RAM and VRAM (see the probe's header for the layout):

  - the ship (cell, move_left, dome_angle) and every missile object;
  - the cart's own radar_t (the static `radar` in main.c): every blip's
    (shown, locked, sx, sy, h, hx, hy) and lock_t/locked/ellipse_bright —
    the exact struct the drawing (radar_gfx_show) read;
  - every radar sprite slot's VRAM (SCB2/SCB3/SCB4, SCB1 row-0 tile +
    attribute);
  - the ellipse palette entry (palette RAM, bank RADAR_PAL_BANK 20,
    entry 1 = 0x400282);
  - a full sprite census (all 381 slots) every 30th frame.

This checker:

  1. proves the cart's radar_t (RAM) equals radar_model.Radar's per-frame
     state on every sampled frame — the RAM readings are the ground truth
     the drawing used (locked, ellipse_bright, every blip's shown/locked);
  2. proves the VRAM matches the cart's blips:
       - each shown blip's stick: SCB4 (X = sx - 7 — the line is the art's
         column 7, see radar_gfx.c) and SCB3 (top = sy - 48, height 3)
         within 1 px, and the SCB1 row-0 tile is
         RADAR_STICK_TILE_BASE + (2h + locked) * 3 (tests/test_radar_render.py
         proves the picture at each number has exactly h lit pixels in
         column 7, or 7..8 when locked);
       - each shown blip's heading: SCB2's hz nibble = |dx| - 1, the
         vertical byte = radar_head_vz(|dy|), the SCB1 attr's h-flip bit
         equals the model's hf, and the box (SCB4 X, SCB3 Y) is placed per
         radar_gfx.c's formulas so the drawn staircase's start is the
         stick's top (and its end is within 1 px of (hx, hy) — the formula
         is mirrored here, so an exact match proves the placement);
       - a hidden blip (not shown): both its stick and heading slots' SCB3
         height is 0 (hidden in the same frame);
  3. proves the ellipse palette entry equals radar_pal_bright (0x4aef)
     exactly when the model says ellipse_bright, else radar_pal[1] (0x627a)
     — the blink is exactly that one palette entry;
  4. requires >= 50 sampled frames locked (the test cartridge's first
     missile is in range and aimed at the resting ship for ~580 frames);
  5. reports the most sprites on any one line of the radar rows (the
     picture's band, RADAR_CY-49 .. RADAR_CY+8 — 135..192 at CY 184) from
     the full sprite census (the hardware's per-line limit is 96) — the
     "busiest sampled frame".
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import radar_model as rm  # noqa: E402
import layout as lay  # noqa: E402

FRAME_SLOTS = 4
# radar_gfx_init: the frame's 4 slots sit at y RADAR_CY-16, height 2. The
# radar's centre comes from src/radar.h (RADAR_CY = DOME_Y + 112).
FRAME_SCB3 = ((496 - (lay.d.RADAR_CY - 16)) << 7) | 2
NMIS = rm.NMIS
TOL = 1                     # px: the task's bound
MIN_LOCKED = 50             # at least 50 sampled frames locked
RADAR0 = 219
PAL_DIM, PAL_BRIGHT = 0x627a, 0x4aef
STICK_BASE = 19146                   # build/radar_map.h: RADAR_STICK_TILE_BASE
HEAD_BASE = 19344                    # ... RADAR_HEAD_TILE_BASE (sticks occupy
                                     # 66 pictures x 3 tiles = 198 tile-slots)
# the task's radar rows: the picture's band (the frame spans RADAR_CY-16 ..
# RADAR_CY+15, the sticks +48, the spot up to ~+10 — today 151..208 at
# CY 200, so 135..192 at CY 184). The band follows the header's RADAR_CY
# (the dome's Y + 112), like FRAME_SCB3 above.
RADAR_Y0, RADAR_Y1 = lay.d.RADAR_CY - 49, lay.d.RADAR_CY + 8

# the C's radar_t / radar_blip_t layout (src/radar.h + m68k ABI, checked
# against the ELF's DWARF; the probe reads the same offsets)
BLIP = 12
BLIP_SHOWN, BLIP_LOCKED = 0, 1
BLIP_SX, BLIP_SY, BLIP_H = 2, 4, 6
BLIP_HX, BLIP_HY = 8, 10

# radar_head_vz (src/radar_gfx.c): the vertical byte that draws exactly dy
# box lines
HEAD_VZ = [1, 1, 17, 33, 49, 65, 81, 97, 113, 129, 145, 161, 177, 193,
           209, 225, 241]


def parse(fname):
    """(records, samples) — samples: {fc: {ship, objs, blips, radar, slots,
    pal, census}}."""
    records = []
    samples = {}
    cur = None
    census = None

    def new_sample(fc):
        nonlocal cur, census
        cur = {"ship": None, "objs": [None] * 5, "blips": [None] * 3,
               "radar": None, "slots": {}, "pal": None, "census": census}
        samples[fc] = cur
        census = None

    for raw in open(fname, "rb"):
        line = raw.decode("ascii", "replace").strip()
        if not line:
            continue
        p = line.split()
        if p[0] == "I":
            records.append(tuple(int(x) for x in p[1:5]))
        elif p[0] == "A":
            new_sample(int(p[1]))
            cur["ship"] = tuple(int(x) for x in p[2:5])
        elif p[0] == "O" and cur is not None:
            cur["objs"][int(p[2])] = tuple(int(x) for x in p[3:])
        elif p[0] == "B" and cur is not None:
            cur["blips"][int(p[2])] = tuple(int(x) for x in p[3:])
        elif p[0] == "R" and cur is not None:
            cur["radar"] = tuple(int(x) for x in p[2:5])
        elif p[0] == "T" and cur is not None:
            cur["slots"][int(p[2])] = (int(p[3], 16), int(p[4], 16),
                                       int(p[5], 16), int(p[6], 16),
                                       int(p[7], 16))
        elif p[0] == "P" and cur is not None:
            cur["pal"] = int(p[2], 16)
        elif p[0] == "W" and cur is not None:
            census = {}
        elif p[0] == "w" and census is not None:
            census[int(p[1])] = (int(p[2], 16), int(p[3], 16))
    return records, samples


def _heading_placement(sx, sy, h, hx, hy):
    """the heading box (bx, by) and the model's hf/hz/vz — radar_gfx.c's
    formulas, mirrored exactly."""
    tx, ty = sx, sy - h
    adx = abs(hx - tx)
    ady = abs(hy - ty)
    if adx == 0 and ady == 0:
        return None             # no line: the stick's top IS the centre
    hf = 1 if ((hx < tx) ^ (hy < ty)) else 0
    hz = adx - 1 if adx else 0
    bx = tx if hy >= ty else hx
    by = ty if hy >= ty else hy
    if hf and adx:
        bx -= adx - 1
    return bx, by, hf, hz, adx, ady


class _Ship:
    """the radar_model.Radar.frame shim: it reads only cell and left."""
    def __init__(self, cell, left):
        self.cell, self.left = cell, left


def _radar_region_count(census):
    """the most sprites whose box covers any line in the radar rows
    (RADAR_Y0..RADAR_Y1, the picture's band from src/radar.h's RADAR_CY),
    from every slot's SCB3 (top, height) / SCB4 (X). Sprites with height 0
    are not drawn. Clamped to the band's lines."""
    rows = [0] * (RADAR_Y1 - RADAR_Y0 + 1)
    for scb3, _scb4 in census.values():
        height = scb3 & 0x3f
        if not height:
            continue
        top = 496 - (scb3 >> 7)
        bot = top + height * 16 - 1
        if bot < RADAR_Y0 or top > RADAR_Y1:
            continue
        for y in range(max(RADAR_Y0, top), min(RADAR_Y1, bot) + 1):
            rows[y - RADAR_Y0] += 1
    return max(rows) if rows else 0


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    mis_addr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    ship_addr = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0
    fc_addr = int(sys.argv[5], 0) if len(sys.argv) > 5 else 0
    records, samples = parse(probe)
    failures = []

    if not records:
        failures.append("probe wrote no input records")
        return 1
    if mis_addr == 0 or ship_addr == 0:
        failures.append("no mis/ship RAM addresses (m68k-neogeo-elf-nm failed?)")
        return 1
    if not samples:
        failures.append("probe sampled no frames")
        return 1

    # ---- replay the game from the recorded inputs (as check_stars does), so
    # the radar_model (lock_t, ellipse_bright, blips) runs one step per real
    # cart frame, and validate each sampled frame against it. The RADAR_TEST
    # hook's two forced spawns are applied to the model exactly as the cart's
    # main.c does (the first missile of each game -> the start cell; the
    # second -> ring 4, azimuth 63), so the model's radar == the cart's.
    import mis_model as mmm  # noqa: E402
    import mis_seed  # noqa: E402  (Task 1: the cart's seed)
    import rules_model as rmm  # noqa: E402
    import ship_model as sm  # noqa: E402

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
    rmod = rm.Radar()
    n = len(records)
    i = first
    n_locked = 0
    stick_bad = head_bad = hidden_bad = pal_bad = radar_bad = blip_bad = frame_bad = 0
    busiest = (0, None)
    test_done = test_done2 = 0      # the RADAR_TEST hook's per-game flags

    def radar_test_spawn():
        """mirror src/main.c's radar_test_spawn: the first fresh missile of
        each game is retargeted to the start cell, the second to ring 4 phi
        63 (cell 25)."""
        nonlocal test_done, test_done2
        for k in range(NMIS):
            o = mis.obj[k]
            if o.state == 1 and o.kind == 0 and o.r == mmm.R_SPAWN[o.ring]:
                if not test_done:
                    o.ring, o.phi = mmm.CELL_RING[27], mmm.CELL_PHI[27]
                    o.r = mmm.R_SPAWN[o.ring]
                    test_done = 1
                    return
                if not test_done2:
                    o.ring, o.phi = mmm.CELL_RING[25], mmm.CELL_PHI[25]
                    o.r = mmm.R_SPAWN[o.ring]
                    test_done2 = 1
                    return

    while 0 <= i < n:
        rec, fc, cur, chg = records[i]
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
                    mis.hits.append((o.ring, o.phi, o.r))
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
        # the RADAR_TEST hook (after mis_update, before rules_end/radar_frame)
        if rules.game_over:
            test_done = test_done2 = 0
        radar_test_spawn()
        rules.end(ship, mis)
        mis.integ = rules.integ

        # the frame's radar (after the logic, as the cart's radar_frame) —
        # advanced EVERY frame so the lock_t/blink counting matches the cart
        sh = _Ship(ship.cell, ship.left)
        rmod.frame(sh, mis)
        if rmod.locked:
            n_locked += 1
        if fc not in samples:
            i += 1
            continue
        s = samples[fc]
        # 1. the cart's radar_t vs the model
        if s["radar"] is not None:
            if s["radar"][1] != rmod.locked:
                radar_bad += 1
                if radar_bad <= 5:
                    failures.append(f"frame {fc}: cart radar.locked "
                                    f"{s['radar'][1]}, model {rmod.locked}")
            if s["radar"][2] != rmod.bright:
                radar_bad += 1
                if radar_bad <= 5:
                    failures.append(f"frame {fc}: cart ellipse_bright "
                                    f"{s['radar'][2]}, model {rmod.bright}")
        # each blip's shown/locked vs the model
        for k in range(NMIS):
            o = mis.obj[k]
            want_shown = 1 if (o.state == 1 and o.r < rm.R_LIMIT) else 0
            want_locked = 1 if (want_shown and rmod.locked and
                                o.ring == rm.CELL_RING[ship.cell] and
                                o.phi == rm.CELL_PHI[ship.cell]) else 0
            b = s["blips"][k]
            if b is not None and (b[0] != want_shown or b[1] != want_locked):
                blip_bad += 1
                if blip_bad <= 5:
                    failures.append(f"frame {fc} blip {k}: cart "
                                    f"({b[0]},{b[1]}), model "
                                    f"({want_shown},{want_locked})")

        # 2. the VRAM vs the cart's blips
        for k in range(NMIS):
            b = s["blips"][k]
            if b is None:
                continue
            shown = b[0]
            stick_slot = RADAR0 + FRAME_SLOTS + k * 5
            head_slot = stick_slot + 1
            st = s["slots"].get(stick_slot)
            hd = s["slots"].get(head_slot)
            if not shown:
                if st is not None and (st[3] & 0x3f):
                    hidden_bad += 1
                    if hidden_bad <= 5:
                        failures.append(f"frame {fc} blip {k}: hidden stick "
                                        f"SCB3 {st[3]:#06x}")
                if hd is not None and (hd[3] & 0x3f):
                    hidden_bad += 1
                    if hidden_bad <= 5:
                        failures.append(f"frame {fc} blip {k}: hidden heading "
                                        f"SCB3 {hd[3]:#06x}")
                continue
            if st is None or hd is None:
                failures.append(f"frame {fc} blip {k}: shown but no slot read")
                continue
            _attr_s, _t0_s, _scb2_s, scb3_s, scb4_s = st
            attr_h, t0_h, scb2_h, scb3_h, scb4_h = hd
            sx, sy, h = b[2], b[3], b[4]
            hx, hy = b[5], b[6]
            locked = b[1]
            # stick: X = sx - 7, top at sy - 48, height 3,
            # tile base + (2h+locked)*3
            got_x = scb4_s >> 7
            got_top = 496 - (scb3_s >> 7)
            got_h = scb3_s & 0x3f
            want_tile = STICK_BASE + (2 * h + locked) * 3
            if abs(got_x - (sx - 7)) > TOL or abs(got_top - (sy - 48)) > TOL \
               or got_h != 3 or _t0_s != want_tile:
                stick_bad += 1
                if stick_bad <= 5:
                    failures.append(
                        f"frame {fc} blip {k} stick: VRAM (X {got_x}, top "
                        f"{got_top}, h {got_h}, tile {_t0_s}), want (sx-7 "
                        f"{sx - 7}, sy-48 {sy - 48}, h 3, tile {want_tile})")
            # heading
            hp = _heading_placement(sx, sy, h, hx, hy)
            if hp is None:
                # no line: the heading slot must be hidden
                if hd is not None and (hd[3] & 0x3f):
                    head_bad += 1
                    if head_bad <= 5:
                        failures.append(f"frame {fc} blip {k}: centre-top "
                                        f"has a visible heading "
                                        f"SCB3 {hd[3]:#06x}")
                continue
            bx, by, hf, hz, adx, ady = hp
            got_bx = scb4_h >> 7
            got_by = 496 - (scb3_h >> 7)
            got_bh = scb3_h & 0x3f
            got_hz = (scb2_h >> 8) & 0x0f
            got_vz = scb2_h & 0xff
            want_tile = HEAD_BASE + (ady * 17 + adx) * 2 + hf
            if abs(got_bx - bx) > TOL or abs(got_by - by) > TOL or got_bh != 1 \
               or got_hz != hz or got_vz != HEAD_VZ[ady] \
               or (attr_h & 1) != hf or t0_h != want_tile:
                head_bad += 1
                if head_bad <= 5:
                    failures.append(
                        f"frame {fc} blip {k} heading: VRAM (X {got_bx}, "
                        f"top {got_by}, h {got_bh}, hz {got_hz}, vz "
                        f"{got_vz}, flip {attr_h & 1}, tile {t0_h}), want "
                        f"(bx {bx}, by {by}, h 1, hz {hz}, vz "
                        f"{HEAD_VZ[ady]}, flip {hf}, tile {want_tile})")

        # 3. the ellipse palette entry
        if s["pal"] is not None:
            want = PAL_BRIGHT if rmod.bright else PAL_DIM
            if s["pal"] != want:
                pal_bad += 1
                if pal_bad <= 5:
                    failures.append(f"frame {fc}: ellipse palette "
                                    f"{s['pal']:#06x}, want {want:#06x} "
                                    f"(bright={rmod.bright})")
        # 6. the frame picture's 4 slots keep the SCB3 radar_gfx_init wrote
        # (y CY-16, height 2) on every game frame: nothing else rewrites
        # them, so a title hide that zeroed them left the radar without its
        # frame for the whole game (M6 Task 1)
        if s["census"]:
            for c in range(FRAME_SLOTS):
                scb3 = s["census"][RADAR0 + c][0]
                if scb3 != FRAME_SCB3:
                    frame_bad += 1
                    if frame_bad <= 5:
                        failures.append(f"frame {fc}: radar frame slot {c} "
                                        f"SCB3 {scb3:#06x}, want {FRAME_SCB3:#06x}")
        # 5. the busiest radar row (from this frame's census)
        if s["census"]:
            cnt = _radar_region_count(s["census"])
            if cnt > busiest[0]:
                busiest = (cnt, fc)
        i += 1

    if radar_bad:
        failures.append(f"{radar_bad} radar_t mismatches vs the model")
    if blip_bad:
        failures.append(f"{blip_bad} blip shown/locked mismatches vs the model")
    if stick_bad:
        failures.append(f"{stick_bad} stick slot mismatches")
    if head_bad:
        failures.append(f"{head_bad} heading slot mismatches")
    if hidden_bad:
        failures.append(f"{hidden_bad} hidden blip SCB3 mismatches")
    if pal_bad:
        failures.append(f"{pal_bad} ellipse palette mismatches")
    if frame_bad:
        failures.append(f"{frame_bad} radar frame slot SCB3 mismatches")
    if n_locked < MIN_LOCKED:
        failures.append(f"only {n_locked} sampled frames locked, want >= "
                        f"{MIN_LOCKED}")

    snap_fc = None
    for line in open(probe):
        p = line.split()
        if p and p[0] == "SNAP":
            snap_fc = int(p[1])
    if snap_fc is None:
        failures.append("the probe never snapshotted")
    elif snap_fc in samples:
        rr = samples[snap_fc]["radar"]
        if rr is not None and rr[1] != 1:
            failures.append(f"SNAP frame {snap_fc}: radar.locked {rr[1]}, want 1")

    if failures:
        print("FAIL radar:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS radar: {len(samples)} samples, {n_locked} locked, "
          f"ellipse palette == the model's bright state, stick/heading "
          f"slots within {TOL} px, hidden blips SCB3 0, busiest radar row "
          f"{busiest[0]} sprites (fc {busiest[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
