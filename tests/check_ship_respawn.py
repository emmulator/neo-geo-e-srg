#!/usr/bin/env python3
"""Assertions for the M4-fixes Task 1 ship-respawn boot-test.

  check_ship_respawn.py SNAP PROBE [FRAMECNT_ADDR [RC_ADDR]]

scripts/ship_respawn_probe.lua drives the normal cart through the
deterministic hold-Up game — centred 60 frames, Up held from then on, never
A — and records, per MAME frame, the BIOS joypad read-backs and the rules'
respawn-complete debug bit (rules_dbg_alive). It takes two dumps of the
ship slots (SCB2/3/4, SCB1 attribute row, and the 4 SCB1 tile rows of the
2x2 picture):

  C  start of game: cart frame 45
  X  the respawn: the frame the alive flag re-rises to 1 after the death
     (the model's death + DEAD_FRAMES_NEO = 604)

and a snapshot at each. This checker:

  1. replays tests/rules_model.py from the recorded inputs (exactly as
     tests/check_hud.py and tests/check_collapse.py do) and states, from
     the model, the first death's cart frame (486) and the respawn frame
     486 + 118 = 604;
  2. proves the probe's dump X really is the respawn frame: its cart frame
     equals the model's death + DEAD_FRAMES_NEO, the model's ship
     state at that frame is at rest on the start cell [27, 27] with no
     lift, and the probe recorded the rules' respawn-complete bit back to
     1 at both the dump and the model's respawn frame;
  3. proves the respawned ship's VRAM equals the start-of-game ship's:
     the two dumps' SCB2/3/4 and SCB1 words are identical for both slots;
  4. proves the respawned ship has the same pixels on screen as the start
     of the game: the amber ship pixels around cell 27's projected centre
     match in both snapshots (the bug's right column — a non-sticky
     sprite with height 0 — draws nothing, so the count collapses).

The death is a "resting on a broken cell" death: the ship never leaves the
start cell, cell 27 breaks at the model's frame 486, and the countdown
ends with the ship back on [27, 27] at frame 604 (the respawn's
ship_locate puts it at cell 27's exact place again; cell 0's crack is far
from the ship on screen, so the amber counts match).

The model's first death at cart frame 486 is deterministic: the hold-Up
policy with its 60-frame delay (verified by this replay — see the summary
line the checker prints). With SHIP_NODEATH=1 (boot-test
ship-respawn-nodeath) the same checker runs the *no-death* leg instead:
a centred ship that never breaks, whose two dumps must still be
word-identical — a direct proof that a fresh boot cannot mask a broken
right column that a death would otherwise expose.
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
# the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.json
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import rules_model as rm  # noqa: E402
import ship_model as sm  # noqa: E402
import layout as lay  # noqa: E402
from PIL import Image  # noqa: E402

PHASE = 0
DEAD_FRAMES_NEO = 118           # rules.h: 100 Vectrex frames x 59/50
START_FRAME = 45                # the probe's start-of-game dump frame
SLOT0, SLOT1 = _SLOTS["SHIP_SPRITE"], _SLOTS["SHIP_SPRITE"] + 1
# cell 27's projected centre on the 224-line screen (the dome box's X + 88,
# its Y + 56): the search window the amber-pixel count looks in. It follows
# the header's DOME position (the ship lifts with the dome), so the window
# stays on the ship under the HUD-layout mutation rule too.
CELL27_CENTRE = (lay.d.DOME_X + 88, lay.d.DOME_Y + 56)


def parse(fname):
    """(records, dumps, death, snaps, seeds) — records: [(rec, fc, cur, chg,
    rc)]; dumps: {'C': (fc, death, rc, [slot lines]), 'X': ...}; death: fc
    or None; snaps: {'S1': fc, 'S2': fc or None}; seeds: {mame frame: the
    cart's mis_seed_used, Task 1}."""
    records, dumps, snaps, death, seeds = [], {}, {}, None, {}
    cur_tag = None
    cur_death = None
    cur_rc = None
    with open(fname, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] == "I":
                records.append(tuple(int(x) for x in p[1:6]))
            elif p[0] == "D":
                death = int(p[2])
            elif p[0] in ("C", "X"):
                cur_tag, cur_death, cur_rc = p[0], int(p[2]) if p[2] != "-" else None, int(p[3])
                dumps[cur_tag] = {"fc": int(p[1]), "death": cur_death, "rc": cur_rc, "slots": []}
            elif p[0] in ("W",):
                if cur_tag is not None:
                    dumps[cur_tag]["slots"].append(line.rstrip("\n"))
            elif p[0] == "SEED":
                seeds[int(p[1])] = int(p[2])
            elif p[0] in ("S1", "S2"):
                snaps[p[0]] = int(p[1])
    return records, dumps, death, snaps, seeds


def frame_model(state, inp, pressed):
    """one frame exactly as tests/check_hud.py's frame_model (the C's
    rules_begin / ship_frame / mis_update / rules_end)."""
    import hud_model as hm  # noqa
    ship, mis, rules = state
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
    died = rules.end(ship, mis)
    mis.integ = rules.integ
    return died


def ship_amber_pts(im, centre):
    """the ship's amber pixels near `centre` (the cell's projected centre on
    the 320x224 screen). Missiles are red, bullets green, the dome's glows
    keep r >= 90 (never amber), so amber is the ship's hull+glow."""
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    cx, cy = centre
    pts = []
    for py in range(h):
        for px in range(w):
            xx, yy = px / sx, py / sy
            if abs(xx - cx) > 30 or abs(yy - cy) > 20:
                continue
            r, g, b = im.getpixel((px, py))[:3]
            if r > 150 and g > b + 50:
                pts.append((xx, yy))
    return pts


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    framecnt_addr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    rc_addr = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0
    nodeath = snap_png.endswith("nodeath.png") or os.environ.get("SHIP_NODEATH") == "1"
    records, dumps, probe_death, snaps, seeds = parse(probe)
    seed = mis_seed.cart_seed(probe, seeds)   # Task 1: the cart's seed
    print(f"mis_seed_used: {seed:#06x}")
    failures = []
    if nodeath:
        return _nodeath(records, dumps, probe_death, snaps, failures, snap_png, probe)

    if not records:
        failures.append("probe wrote no input records")
        print("FAIL ship-respawn: " + failures[0])
        return 1
    if "C" not in dumps or "X" not in dumps:
        failures.append(f"probe dumps: C={'C' in dumps} X={'X' in dumps} "
                        f"(need both; NODEATH={probe_death})")
        print("FAIL ship-respawn: " + failures[0])
        return 1
    if len(dumps["C"]["slots"]) != 2 or len(dumps["X"]["slots"]) != 2:
        failures.append(f"dumps have {len(dumps['C']['slots'])}/{len(dumps['X']['slots'])} "
                        "slots, want 2 each")
        print("FAIL ship-respawn: " + failures[0])
        return 1
    if snaps.get("S1") is None or snaps.get("S2") is None:
        failures.append("the probe did not snapshot both moments")
        print("FAIL ship-respawn: " + failures[0])
        return 1

    # ---- replay the model from the recorded inputs (the reference) ----
    first = None
    for i, (rec, fc, cur, chg, rc) in enumerate(records):
        if fc == 1:
            first = i
            break
    if first is None:
        first = 0
    ship, mis, rules = sm.Ship(), mm.Missiles(seed=seed), rm.Rules(1)
    first_death = None
    rc_by_fc = {}                       # model cart frame -> alive flag
    state_by_fc = {}
    i = first + PHASE
    m = 0
    while 0 <= i < len(records):
        rec, fc, cur, chg, rcnow = records[i]
        died = frame_model((ship, mis, rules), cur, chg)
        m += 1
        state_by_fc[m] = (ship.cell, ship.left, ship.lift)
        rc_by_fc[m] = 1 if not (rules.dead_t or rules.game_over) else 0
        if died and first_death is None:
            first_death = m
        i += 1

    if first_death is None:
        failures.append("the model never found a death in the recorded game")
        print("FAIL ship-respawn: " + failures[0])
        return 1
    print(f"model: first death at cart frame {first_death}, respawn at "
          f"{first_death + DEAD_FRAMES_NEO}")

    # ---- the probe's dump X is the respawn frame, at the ship's rest state
    # The probe's death is the 1->0 edge of the alive flag: rules_begin
    # latches the flag while the death lands in rules_end, so the recorded
    # death frame is the model's death frame + 1; the dump X is the frame
    # the flag re-rises to 1 (the respawn frame itself, death + 118).
    x = dumps["X"]
    model_respawn = first_death + DEAD_FRAMES_NEO
    if x["fc"] != model_respawn:
        failures.append(f"dump X at cart frame {x['fc']}, want the model's "
                        f"respawn frame {model_respawn} (death {first_death} "
                        f"+ {DEAD_FRAMES_NEO})")
    st = state_by_fc.get(x["fc"])
    if st is None:
        failures.append(f"the model never reached cart frame {x['fc']}")
    else:
        cell, left, lift = st
        if cell != sm.Ship().cell or left != 0 or lift != 0:
            failures.append(f"model ship at {x['fc']}: cell {cell} left {left} "
                            f"lift {lift}, want at rest on the start cell "
                            f"({sm.Ship().cell}, 0, 0)")
        if x["rc"] != 1:
            failures.append(f"respawn-complete flag at dump X is {x['rc']}, "
                            "want 1 (the ship must really be back)")
    if rc_addr and x["rc"]:
        want_rc = rc_by_fc.get(x["fc"])
        if want_rc is not None and want_rc != 1:
            failures.append(f"probe says the ship is alive at {x['fc']} but "
                            f"the model's countdown was still running")
    # the respawn frame itself (the model's): the probe's I record must carry
    # the flag back to 1 there too
    if rc_addr:
        got_rc = None
        for rec, fc, cur, chg, rcnow in records:
            if fc == first_death + DEAD_FRAMES_NEO:
                got_rc = rcnow
                break
        if got_rc is None:
            failures.append(f"no record at the model's respawn frame "
                            f"{first_death + DEAD_FRAMES_NEO}")
        elif got_rc != 1:
            failures.append(f"respawning at {first_death + DEAD_FRAMES_NEO}: "
                            f"probe rc flag {got_rc}, want 1")
    # the start dump must be at the model's frame 45 (the first launch is
    # still ~14 frames away; nothing has moved the ship)
    c = dumps["C"]
    if c["fc"] != START_FRAME:
        failures.append(f"dump C at cart frame {c['fc']}, want {START_FRAME}")

    # ---- the respawned ship's VRAM equals the start-of-game ship's ----
    # each slot line: <scb2> <scb3> <scb4> <attr> <tile0..tile3>
    def slot_words(lines):
        return [tuple(l.partition(" ")[2].split()) for l in lines]

    want_w = slot_words(dumps["C"]["slots"])
    got_w = slot_words(dumps["X"]["slots"])
    for i_, (w, g) in enumerate(zip(want_w, got_w)):
        if w != g:
            failures.append(f"slot {SLOT0 + i_} after the respawn differs "
                            f"from the start of the game:\n"
                            f"  start {w}\n  after {g}")

    # ---- the respawned ship has the same pixels on screen ----
    im1 = Image.open(snaps_snap(snap_png, probe, 1)).convert("RGB")
    im2 = Image.open(snaps_snap(snap_png, probe, 2)).convert("RGB")
    centre = CELL27_CENTRE           # cell 27.s projected centre (224-line screen)
    p1 = ship_amber_pts(im1, centre)
    p2 = ship_amber_pts(im2, centre)
    if not p1:
        failures.append(f"no ship pixels found at the start (snapshot {snaps['S1']})")
    if not p2:
        failures.append(f"no ship pixels found after the respawn "
                        f"(snapshot {snaps['S2']})")
    if p1 and p2:
        n1, n2 = len(p1), len(p2)
        if abs(n1 - n2) > max(4, n1 // 4):
            failures.append(f"ship pixel count after the respawn ({n2}) "
                            f"differs from the start ({n1})")
        print(f"ship pixels: start {n1}, after respawn {n2} (centre "
              f"{centre[0]},{centre[1]})")

    if failures:
        print("FAIL ship-respawn:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS ship-respawn: respawned ship slots equal the start of the "
          f"game's, pixels match (start {len(p1) if p1 else 0}, after "
          f"{len(p2) if p2 else 0})")
    return 0


def _nodeath(records, dumps, probe_death, snaps, failures, snap_png, probe):
    """the robustness leg: a centred ship that never breaks. The ship never
    dies and never hides, so the C and X dumps (both taken while the ship
    is alive at (27, 27, 0)) must be word-identical and the two snapshots'
    ship pixels must match. With the pre-fix hide this is exactly the FIRST
    hide/show pair the respawn boot-test hits (the first death was at
    fc 486): on the buggy code the X dump's slot 33 SCB3 would be 0 and
    the ship a left half — this leg proves no fresh boot can mask that."""
    if not records:
        failures.append("probe wrote no input records")
        return 1
    if "C" not in dumps or "X" not in dumps:
        failures.append(f"probe dumps: C={'C' in dumps} X={'X' in dumps} (NODEATH)")
        return 1
    if len(dumps["C"]["slots"]) != 2 or len(dumps["X"]["slots"]) != 2:
        failures.append(f"dumps have {len(dumps['C']['slots'])}/{len(dumps['X']['slots'])} "
                        "slots, want 2 each")
        return 1
    if snaps.get("S1") is None or snaps.get("S2") is None:
        failures.append("the probe did not snapshot both moments")
        return 1
    # the ship stayed alive the whole run: the alive flag at both dumps
    for tag in ("C", "X"):
        if dumps[tag]["rc"] != 1:
            failures.append(f"{tag} dump read while the alive flag was {dumps[tag]['rc']}")
    if probe_death is not None:
        failures.append("the probe saw a death in the no-death run")
        return 1
    # word-identical slots
    def slot_words(lines):
        return [tuple(l.partition(" ")[2].split()) for l in lines]
    want_w = slot_words(dumps["C"]["slots"])
    got_w = slot_words(dumps["X"]["slots"])
    for i_, (w, g) in enumerate(zip(want_w, got_w)):
        if w != g:
            failures.append(f"slot {SLOT0 + i_} at frame {dumps['X']['fc']} differs "
                            f"from frame {dumps['C']['fc']} (no death ran):\n"
                            f"  first {w}\n  later {g}")
    # pixel match
    im1 = Image.open(snaps_snap(snap_png, probe, 1)).convert("RGB")
    im2 = Image.open(snaps_snap(snap_png, probe, 2)).convert("RGB")
    centre = CELL27_CENTRE
    p1 = ship_amber_pts(im1, centre)
    p2 = ship_amber_pts(im2, centre)
    if not p1 or not p2:
        failures.append(f"ship pixels missing: start {len(p1)} after {len(p2)}")
    elif abs(len(p1) - len(p2)) > max(4, len(p1) // 4):
        failures.append(f"ship pixel count changed without a death: {len(p1)} -> {len(p2)}")
    if failures:
        print("FAIL ship-respawn-nodeath:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS ship-respawn-nodeath: ship slots identical at {dumps['C']['fc']} "
          f"and {dumps['X']['fc']}, pixels {len(p1)} == {len(p2)}")
    return 0


def snaps_snap(snap_png, probe, idx):
    """MAME writes 0000.png, 0001.png, ... in the snapshot directory (its
    own subdir, build/boot/snap/aes) while the probe's records carry the
    S1/S2 frames. boot_test.sh copies the first PNG to $OUT/snap.png; the
    ordered snapshots are the PNGs in the directory the MAME run wrote
    them into (the `snap` directory next to the probe output)."""
    # the probe's dir: $OUT/snap (boot_test) — the snapshots live in its
    # MAME-managed subdirectory (aes/), or directly in it
    base = os.path.dirname(os.path.dirname(os.path.abspath(snap_png)))
    for root in (os.path.join(base, "snap"), base):
        if not os.path.isdir(root):
            continue
        pngs = sorted(os.path.join(r, fn) for r, _, fs in os.walk(root)
                      for fn in fs if fn.endswith(".png"))
        if len(pngs) >= idx and probe_frames(probe):
            return pngs[idx - 1]
    return snap_png


def probe_frames(probe):
    """the probe took snapshots only if its S1/S2 records exist."""
    with open(probe, "rb") as fh:
        return b"S1" in fh.read()


if __name__ == "__main__":
    sys.exit(main())
