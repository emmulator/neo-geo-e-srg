"""Assertions for the attract mode's self-playing game boot-test (Attract
Task A3, scripts/demo_probe.lua).

  check_demo.py SNAP PROBE MODE
    SNAP   the MAME snapshot (unused)
    PROBE  the probe dump (see scripts/demo_probe.lua for the D/G/T/B/GO/
           C/M/SNAP/EXIT lines)
    MODE   demo (the cycle run) or demo-start (the Start/return run)

The checker replays build/demo_map.h through tests/hud_model.frame_model
with DEMO_SEED / DEMO_LEVEL and proves:

  demo (cycle):
   1. every frame of a whole 3245-frame cycle (epoch 2) equals the model's
      rules / ship / missiles / radar state; the model's events equal
      build/demo.json's kills/cracks/jumps/lock frames/rings/angles;
   2. the next cycle (epoch 3) is state-identical to it;
   3. the AES demo-sound toggle: power-on epoch 1 sends no command; the D
      press at epoch 2 turns it on and every command equals the model's;
      the setting holds across the epoch 3 restart; a D press on page 1
      turns it off (no command after it); a 60-frame D hold at epoch 4
      toggles it once (the model's commands resume); row 21 shows the
      confirmation for exactly 120 frames on pages 0 and 1, then the page's
      own prompt/cap returns;
   4a. after a B press mid-demo (epoch 4), the demo restarts (epoch 5, page
      0, title_t 0, level changed) and its next frames equal the script's
      first frames;
   5. flow_board's 126 bytes are identical before and after a whole cycle;
   7. the sprite census over the cycle is <= 96 a line; the framemark worst
      work span is <= 240 scanlines, measured without the modulo (a span
      that wraps is a failure); every demo frame is shown on exactly one
      MAME frame (n - fc constant); and no frame starts after the vblank
      return (a late start means the previous frame overran). The model also
      proves the demo never has more than one player bullet in flight.
   8. every sampled title frame's props_dbg_last_angle equals that frame's
      ship.dome_angle (proof P2: the props are prepared every frame).

  demo-start:
   3. START at the demo's first jump over a crack (the frame in
      build/demo.json's crack_jumps) starts a game whose state equals a game
      started from today's title at the same title_seed_t: seed
      mis_seed_from(title_seed_t), NORMAL, lives 3, score 0, no broken
      cells, no missiles, the ship at the start cell;
   4b. a GAME OVER returning to the title starts the demo at frame 0 (its
      first frames equal the script's first frames).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
import hud_model as hm          # noqa: E402
import mis_model as mm          # noqa: E402
import radar_model as radm      # noqa: E402
import rules_model as rm        # noqa: E402
import ship_model as sm         # noqa: E402
import sound_model              # noqa: E402  (the demo's sound commands)
from test_rules_play import frame_model as full_frame_model  # noqa: E402

FRAME_LINES = 264
# P1: the title frame must fit, measured from the vblank return to the end
# of the frame's work. The old modulo turned a frame that overran into a
# small "span"; the check below treats any end at or past the next vblank
# return (or a late start) as a wrap, so a frame that drops is a failure
# rather than a small number.
#
# Plan P2 amendment 2 (2026-10-28): the limit moves from P1's chosen 200
# headroom to 240, not because the hardware needs it — the demo is
# deterministic and its worst frame is measured exactly every cycle — but
# because the props commit is now paid on every frame (the demo prepares and
# commits them like the game). 240 keeps 24 lines to the 264-line frame; the
# checker still rejects any drop or late start. (The old per-changed-slot
# commit measured 55 lines and the shown-prefix runs 62 at the worst demo
# frame 2066, so the old write path is the cheaper one.)
WORST_LIMIT = 240
SPRITE_LIMIT = 96
VBLANK_RETURN = 243

# the state fields D/G carry after their tag-specific header, in order
FIELDS = [
    "rules_level", "rules_nbroken", "rules_lives", "rules_integ",
    "rules_dead_t", "rules_dome_dead", "rules_game_over",
    "ship_angle", "ship_lat", "ship_cell", "ship_move_left", "ship_lift",
    "ship_jumped", "broken_hex",
    "mis_rng", "mis_timer", "mis_level", "mis_kills", "mis_dome_hits",
    "mis_score10", "mis_fire_req", "mis_sfx",
    "radar_lock_t", "radar_locked",
]
INT_FIELDS = [f for f in FIELDS if f != "broken_hex"]
SLOT_FIELDS = ("state", "kind", "ring", "phi", "life", "r", "dr")


def parse_header():
    """(seed, level, frames, input bytes per frame) from build/demo_map.h."""
    text = open(os.path.join(ROOT, "build", "demo_map.h")).read()
    seed = int(re.search(r"#define DEMO_SEED\s+0x([0-9a-fA-F]+)", text).group(1), 16)
    level = int(re.search(r"#define DEMO_LEVEL\s+(\d+)", text).group(1))
    frames = int(re.search(r"#define DEMO_FRAMES\s+(\d+)", text).group(1))
    runs = [(int(b, 16), int(n))
            for b, n in re.findall(r"\{\s*0x([0-9a-fA-F]+)\s*,\s*(\d+)\s*\}", text)]
    inputs = []
    for b, n in runs:
        inputs.extend([b] * n)
    if len(inputs) != frames:
        sys.exit(f"check_demo: build/demo_map.h has {len(inputs)} frames, "
                 f"DEMO_FRAMES says {frames}")
    return seed, level, frames, inputs


def first_crack_jump():
    """the script frame of the demo's first jump over a crack, from
    build/demo.json (the START proof uses the run after it)."""
    ev = json.load(open(os.path.join(ROOT, "build", "demo.json")))
    return ev["crack_jumps"][0][0]


def _vpos(v):
    return v if v < 0x8000 else v - 0x10000


def _broken_hex(ship):
    bb = bytearray(10)
    for c in ship.broken:
        bb[c >> 3] |= 1 << (c & 7)
    return bb.hex()


HASH_BASE = 2166136261
HASH_PRIME = 33           # P1: the cart's shift-and-add x33 mix


def hash_mix(h, v):
    return ((h ^ (v & 0xFFFFFFFF)) * HASH_PRIME) & 0xFFFFFFFF


HASH_PRE = [
    "rules_level", "rules_nbroken", "rules_lives", "rules_integ",
    "rules_dead_t", "rules_dome_dead", "rules_game_over",
    "ship_angle", "ship_lat", "ship_cell", "ship_move_left", "ship_lift",
    "ship_jumped",
]
HASH_MIS = [
    "mis_rng", "mis_timer", "mis_level", "mis_kills", "mis_dome_hits",
    "mis_score10", "mis_fire_req",
]
# the D/G field block still carries mis_sfx (it is useful to report the
# frame's sound events), but the hash and the equality checks exclude it:
# the host model's frame_model does not clear it each frame, and the
# notifier can catch the next frame after mis_update cleared it.
PARSE_MIS = HASH_MIS + ["mis_sfx"]
COMPARE_FIELDS = [f for f in INT_FIELDS if f != "mis_sfx"]


def model_hashes(states):
    """the cart's demo_hash_frame() prefix after each frame (every field it
    mixes, in the same order: rules, ship, broken bytes, missiles, slots)."""
    h = HASH_BASE
    out = []
    for st in states:
        for k in HASH_PRE:
            h = hash_mix(h, st[k])
        for byte in bytes.fromhex(st["broken_hex"]):
            h = hash_mix(h, byte)
        for k in HASH_MIS:
            h = hash_mix(h, st[k])
        for slot in st["slots"]:
            for v in slot:
                h = hash_mix(h, v)
        out.append(h)
    return out


def model_hash(states):
    return model_hashes(states)[-1]


def model_states(inputs, seed, level):
    """one model state per frame, plus the events the generator's JSON has."""
    ship = sm.Ship()
    mis = mm.Missiles(level=level, seed=seed)
    rules = rm.Rules(level)
    radar = radm.Radar()
    prev = 0
    states = []
    ev = dict(kills=[], cracks=[], crack_jumps=[], lock=0,
              rings=set(), angles=set(), max_bullets=0)
    for f, cur in enumerate(inputs):
        pressed = cur & ~prev
        was_cell, was_broken = ship.cell, set(ship.broken)
        hm.frame_model((ship, mis, rules), cur, pressed)
        radar.frame(ship, mis)
        ev["max_bullets"] = max(
            ev["max_bullets"],
            sum(1 for o in mis.obj[mm.NMIS:] if o.state == 1))
        if ship.jumped:
            mid = [k for k in was_broken
                   if sm.toward(was_cell, sm.stick(cur & 15)) == k]
            if mid:
                ev["crack_jumps"].append((f, mid[0]))
        for _ in mis.hits:
            ev["kills"].append(f)
        for c in mis.lands:
            if c not in was_broken:
                ev["cracks"].append((f, c))
        ev["lock"] += 1 if radar.locked else 0
        ev["rings"].add(mm.CELL_RING[ship.cell])
        ev["angles"].add(ship.angle)
        states.append(dict(
            rules_level=rules.level,
            rules_nbroken=len(rules.broken),
            rules_lives=rules.lives,
            rules_integ=rules.integ,
            rules_dead_t=rules.dead_t,
            rules_dome_dead=rules.dome_dead,
            rules_game_over=rules.game_over,
            ship_angle=ship.angle,
            ship_lat=ship.lat,
            ship_cell=ship.cell,
            ship_move_left=ship.left,
            ship_lift=ship.lift,
            ship_jumped=ship.jumped,
            broken_hex=_broken_hex(ship),
            mis_rng=mis.rng,
            mis_timer=mis.timer,
            mis_level=mis.level,
            mis_kills=mis.kills,
            mis_dome_hits=mis.dome_hits,
            mis_score10=mis.score,
            mis_fire_req=mis.fire_req,
            mis_sfx=mis.sfx,
            radar_lock_t=radar.lock_t,
            radar_locked=radar.locked,
            slots=[(o.state, o.kind, o.ring, o.phi, o.life, o.r, o.dr)
                   for o in mis.obj[:mm.NMIS]],
        ))
        prev = cur
    return states, ev


def demo_commands(inputs, seed, level, nframes):
    """the demo's sound commands, frame by frame: the same model
    tests/check_sound.py's demo mode uses (tests/sound_model.py's Sound.cmds
    around test_rules_play.frame_model). The model's Sound starts fresh for
    each demo epoch, exactly as src/flow.c's game_sound_state is reset by
    demo_restart, so one replay from frame 1 gives any epoch's commands."""
    ship = sm.Ship()
    mis = mm.Missiles(level=level, seed=seed)
    rules = rm.Rules(level)
    radar = radm.Radar()
    state = (ship, mis, rules, radar)
    sound = sound_model.Sound()
    pred = []
    prev = 0
    for f, cur in enumerate(inputs[:nframes], 1):
        pressed = cur & ~prev
        full_frame_model(state, cur, pressed)
        for c in sound.cmds(ship, mis, rules, radar, rules._died):
            pred.append((f, c))
        prev = cur
    return pred


def _state_from(tokens, base):
    d = {}
    i = base
    for name in HASH_PRE:
        d[name] = int(tokens[i])
        i += 1
    d["broken_hex"] = tokens[i]
    i += 1
    for name in PARSE_MIS:
        d[name] = int(tokens[i])
        i += 1
    d["radar_lock_t"] = int(tokens[i])
    i += 1
    d["radar_locked"] = int(tokens[i])
    i += 1
    sb = base + len(FIELDS)
    d["slots"] = []
    for s in range(mm.NMIS):
        off = sb + s * len(SLOT_FIELDS)
        d["slots"].append(tuple(int(tokens[off + i])
                                for i in range(len(SLOT_FIELDS))))
    return d


def parse(path):
    d, g, t, b, go, c, m, snaps, hs = [], [], [], {}, {}, [], [], [], {}
    p, f, s = [], [], []
    with open(path, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            parts = line.split()
            if not parts:
                continue
            tag = parts[0]
            if tag == "D":
                rec = dict(n=int(parts[1]), epoch=int(parts[2]),
                           fc=int(parts[3]), page=int(parts[4]),
                           t=int(parts[5]), lvvalid=int(parts[6]),
                           lv=int(parts[7]), hash=int(parts[-2]),
                           props_angle=int(parts[-1]))
                rec.update(_state_from(parts, 8))
                d.append(rec)
            elif tag == "G":
                rec = dict(n=int(parts[1]), fc=int(parts[2]),
                           title_seed=int(parts[3]), mis_seed=int(parts[4]))
                rec.update(_state_from(parts, 5))
                g.append(rec)
            elif tag == "T":
                t.append(dict(n=int(parts[1]), epoch=int(parts[2]),
                              fc=int(parts[3]), title_seed=int(parts[4])))
            elif tag == "B":
                b[int(parts[2])] = parts[4]
            elif tag == "GO":
                go[int(parts[1])] = int(parts[2])
            elif tag == "C":
                c.append(dict(n=int(parts[1]), epoch=int(parts[2]),
                              fc=int(parts[3]), worst=int(parts[4]),
                              line=int(parts[5])))
            elif tag == "M":
                m.append(dict(n=int(parts[1]), epoch=int(parts[2]),
                              fc=int(parts[3]), end=int(parts[4]),
                              max=int(parts[5]), min=int(parts[6]),
                              start=int(parts[7])))
            elif tag == "SNAP":
                snaps.append(int(parts[1]))
            elif tag == "H":
                hs[int(parts[2])] = int(parts[3])
            elif tag == "P":
                p.append(dict(n=int(parts[1]), epoch=int(parts[2]),
                              fc=int(parts[3]), page=int(parts[4]),
                              t=int(parts[5]), aes=int(parts[6]),
                              toggles=int(parts[7])))
            elif tag == "F":
                f.append(dict(n=int(parts[1]), epoch=int(parts[2]),
                              fc=int(parts[3]), page=int(parts[4]),
                              t=int(parts[5]),
                              text=bytes.fromhex(parts[6])
                              .decode("ascii", "replace")))
            elif tag == "S":
                s.append(dict(n=int(parts[1]), epoch=int(parts[2]),
                              fc=int(parts[3]), cmd=int(parts[4])))
    return d, g, t, b, go, c, m, snaps, hs, p, f, s


def eff_level(rec):
    return rec["lv"] if rec["lvvalid"] == 0x53 and rec["lv"] <= 2 else 1


def compare(a, b):
    """the differing state field names between two state dicts."""
    bad = [k for k in COMPARE_FIELDS if a[k] != b[k]]
    if a["broken_hex"] != b["broken_hex"]:
        bad.append("broken_hex")
    if a["slots"] != b["slots"]:
        bad.append("slots")
    return bad


def compare_frame(rec, model, frame):
    bad = compare(rec, model)
    if bad:
        detail = []
        for k in bad[:6]:
            detail.append(f"{k}: cart {rec[k]!r} model {model[k]!r}")
        return f"demo frame {frame}: " + "; ".join(detail)
    return None


def title_prompt_b(t):
    """src/title.h's title_prompt_b: the prompt alternation."""
    return (t >= 76 and t < 152) or t >= 227


def _epoch_p(p, epoch):
    recs = [r for r in p if r["epoch"] == epoch]
    return min(recs, key=lambda r: r["n"]) if recs else None


def _confirmation(f, epoch, page, msg):
    """the first F record whose row 21 is msg on (epoch, page), and the
    next F record (the row changed away from it)."""
    recs = [r for r in f if r["epoch"] == epoch and r["page"] == page]
    for j, r in enumerate(recs):
        if r["text"].strip() == msg:
            for r2 in recs[j + 1:]:
                if r2["text"].strip() != msg:
                    return r, r2
            return r, None
    return None, None


def _check_confirmation(failures, f, epoch, page, msg, prompt):
    first, nxt = _confirmation(f, epoch, page, msg)
    if first is None:
        failures.append(f"AES epoch {epoch}: no {msg!r} confirmation on "
                        f"page {page}")
        return
    if nxt is None:
        failures.append(f"AES epoch {epoch}: the {msg!r} confirmation on "
                        f"page {page} never ended")
        return
    dur = nxt["n"] - first["n"]
    if dur != 120:
        failures.append(f"AES epoch {epoch}: the {msg!r} confirmation on "
                        f"page {page} lasted {dur} frames, want 120")
    else:
        print(f"AES epoch {epoch}: page {page} row 21 read {msg!r} for 120 "
              f"frames, then {nxt['text'].strip()!r}")
    if prompt:
        want = "B TO CHANGE LEVEL" if title_prompt_b(nxt["t"]) else "PRESS START"
        if nxt["text"].strip() != want:
            failures.append(f"AES epoch {epoch}: after the confirmation row "
                            f"21 reads {nxt['text'].strip()!r}, want {want!r} "
                            f"(title_t {nxt['t']})")
    elif nxt["text"].strip():
        failures.append(f"AES epoch {epoch}: after the page-{page} "
                        f"confirmation row 21 reads {nxt['text'].strip()!r}, "
                        f"want blank (the page's cap row)")


def demo_aes_sound(p, f, s, inputs, seed, level):
    """Attract D1 proof 3: the AES demo-sound toggle, from the demo probe's
    P (toggle state), F (fix row 21) and S (REG_SOUND tap) records."""
    failures = []
    pred = demo_commands(inputs, seed, level, len(inputs))

    # power-on: OFF, no command in the entry epoch
    e1 = _epoch_p(p, 1)
    if e1 is None:
        failures.append("AES power-on: no P record for epoch 1")
    elif e1["aes"] != 0 or e1["toggles"] != 0:
        failures.append(f"AES power-on: toggle {e1['aes']}, toggles "
                        f"{e1['toggles']}, want OFF / 0")
    s1 = [(r["fc"], r["cmd"]) for r in s if r["epoch"] == 1]
    if s1:
        failures.append(f"AES power-on: {len(s1)} demo sound command(s) in "
                        f"epoch 1: {s1[:8]}")
    else:
        print("AES power-on: epoch 1 sent no sound command")

    # epoch 2: a D press turns it ON; a full cycle equals the model
    e2 = next((r for r in sorted((r for r in p if r["epoch"] == 2),
                                 key=lambda r: r["n"])
               if r["aes"] == 1), None)
    if e2 is None or e2["toggles"] != 1:
        failures.append("AES epoch 2: the D press did not turn the demo "
                        "sound ON (want toggle 1)")
    s2 = [(r["fc"], r["cmd"]) for r in s if r["epoch"] == 2]
    if s2 == pred:
        print(f"AES after D: epoch 2 sent {len(s2)} commands equal the "
              f"model's {len(pred)}")
    else:
        if len(s2) != len(pred):
            failures.append(f"AES after D: epoch 2 sent {len(s2)} commands, "
                            f"the model predicts {len(pred)}")
        for i, (a, b) in enumerate(zip(s2, pred)):
            if a != b:
                failures.append(f"AES after D: command {i} is cart {a}, "
                                f"model {b}")
                break
    _check_confirmation(failures, f, 2, 0, "DEMO SOUND ON", prompt=True)

    # epoch 3: the setting held across the restart; a page-1 D press turns
    # it OFF, and no command follows it
    e3 = _epoch_p(p, 3)
    if e3 is None or e3["aes"] != 1:
        failures.append("AES epoch 3: the setting did not stay ON across "
                        "the demo restart")
    off = None
    if e3 is not None:
        for r in sorted((r for r in p if r["epoch"] == 3),
                        key=lambda r: r["n"]):
            if r["aes"] == 0:
                off = r
                break
    if off is None:
        failures.append("AES epoch 3: the page-1 D press did not turn the "
                        "sound OFF")
    else:
        if off["page"] != 1:
            failures.append(f"AES epoch 3: the OFF toggle happened on page "
                            f"{off['page']}, want 1")
        want_on = [(fc, cmd) for fc, cmd in pred if fc < off["fc"]]
        got_on = [(r["fc"], r["cmd"]) for r in s
                  if r["epoch"] == 3 and r["fc"] < off["fc"]]
        if got_on == want_on:
            print(f"AES page-1 D press: epoch 3 kept the model's "
                  f"{len(got_on)} ON commands before frame {off['fc']}")
        else:
            if len(got_on) != len(want_on):
                failures.append(f"AES epoch 3: {len(got_on)} ON commands "
                                f"before frame {off['fc']}, the model "
                                f"predicts {len(want_on)}")
            for i, (a, b) in enumerate(zip(got_on, want_on)):
                if a != b:
                    failures.append(f"AES epoch 3: ON command {i} is cart "
                                    f"{a}, model {b}")
                    break
        got_off = [(r["fc"], r["cmd"]) for r in s
                   if r["epoch"] == 3 and r["fc"] >= off["fc"]]
        if got_off:
            failures.append(f"AES epoch 3: {len(got_off)} command(s) after "
                            f"the OFF press: {got_off[:8]}")
        else:
            print(f"AES page-1 D press: epoch 3 sent no command after the "
                  f"OFF toggle at frame {off['fc']}")
    _check_confirmation(failures, f, 3, 1, "DEMO SOUND OFF", prompt=False)

    # epoch 4: a 60-frame D hold toggles once; the model's commands resume
    e4p = [r for r in p if r["epoch"] == 4]
    if not e4p:
        failures.append("AES epoch 4: no P records")
    else:
        first4 = min(e4p, key=lambda r: r["n"])
        if first4["aes"] != 0 or first4["toggles"] != 2:
            failures.append(f"AES epoch 4: it began with toggle "
                            f"{first4['aes']}, toggles {first4['toggles']}, "
                            f"want OFF / 2")
        on = next((r for r in sorted(e4p, key=lambda r: r["n"])
                   if r["aes"] == 1), None)
        if on is None:
            failures.append("AES epoch 4: the 60-frame D hold did not turn "
                            "the sound ON")
        else:
            top = max(r["toggles"] for r in e4p)
            if on["toggles"] - first4["toggles"] != 1 or top != 3:
                failures.append(f"AES epoch 4: the 60-frame D hold changed "
                                f"toggles {first4['toggles']} -> {top}, "
                                f"want +1 (one toggle)")
            else:
                print(f"AES 60-frame D hold: toggles {first4['toggles']} -> "
                      f"{top} (one toggle), sound ON at frame {on['fc']}")
            want = [(fc, cmd) for fc, cmd in pred if fc <= 500]
            got = [(r["fc"], r["cmd"]) for r in s
                   if r["epoch"] == 4 and r["fc"] <= 500]
            if got == want:
                print(f"AES 60-frame D hold: epoch 4 sent the model's "
                      f"{len(got)} commands through frame 500")
            else:
                if len(got) != len(want):
                    failures.append(f"AES epoch 4: {len(got)} commands "
                                    f"through frame 500, the model predicts "
                                    f"{len(want)}")
                for i, (a, b) in enumerate(zip(got, want)):
                    if a != b:
                        failures.append(f"AES epoch 4: command {i} is cart "
                                        f"{a}, model {b}")
                        break
        _check_confirmation(failures, f, 4, 0, "DEMO SOUND ON", prompt=True)
    return failures


def demo_props_angle(d):
    """proof P2: every sampled title frame's props_dbg_last_angle equals the
    frame's ship.dome_angle. A skipped props_prepare leaves last_angle at an
    older angle and shows here; with the table and the budget removed the
    demo prepares every frame, so every sampled frame must agree."""
    bad = [(r["epoch"], r["fc"], r["props_angle"], r["ship_angle"])
           for r in d if r["props_angle"] != r["ship_angle"]]
    if bad:
        return [f"props angle: {len(bad)} of {len(d)} sampled demo frames "
                f"have a stale props_dbg_last_angle (epoch, fc, props, ship): "
                f"{bad[:5]}"]
    print(f"props angle: all {len(d)} sampled demo frames have "
          f"props_dbg_last_angle == ship.dome_angle (0 mismatches)")
    return []


def demo_cycle(d, g, t, b, go, c, m, snaps, hs, p, f, s, states, ev,
               inputs, seed, level):
    failures = demo_props_angle(d)
    by_epoch = {}
    for rec in d:
        by_epoch.setdefault(rec["epoch"], []).append(rec)
    e2 = {r["fc"]: r for r in by_epoch.get(2, [])}
    e3 = {r["fc"]: r for r in by_epoch.get(3, [])}
    # the notifier may miss the first two cart frames of an epoch (it can
    # catch demo_input's fc bump before game_frame/hash), but the epoch
    # hash covers all 3245 frames; the sampled subset only has to reach the
    # first few and the last frame.
    if not e2 or max(e2) != len(states) or min(e2) > 3:
        failures.append(f"cycle epoch 2 has frames {sorted(e2)[:5]}..{sorted(e2)[-5:]} "
                        f"({len(e2)}), want a subset of 1..{len(states)}")
        return failures
    if not e3 or max(e3) != len(states) or min(e3) > 3:
        failures.append(f"cycle epoch 3 has {len(e3)} frames, want a subset "
                        f"of 1..{len(states)}")
    # the notifier can miss a cart frame or catch one mid-update, so the
    # sampled D lines carry the cart's per-frame hash; a record is aligned
    # by that hash to the model prefix it equals, then its fields compared.
    # The cart's epoch hash (demo_hash_frame) covers all 3245 frames exactly.
    prefix = model_hashes(states)
    want_hash = prefix[-1]
    hindex = {}
    for i, h in enumerate(prefix, 1):
        hindex.setdefault(h, i)
    bad = 0
    unmapped = 0
    for rec in e2.values():
        idx = hindex.get(rec["hash"])
        if idx is None:
            unmapped += 1
            if unmapped <= 5:
                failures.append(f"demo frame {rec['fc']}: cart hash "
                                f"{rec['hash']:#010x} is not a model prefix")
            continue
        msg = compare_frame(rec, states[idx - 1], idx)
        if msg:
            bad += 1
            if bad <= 5:
                failures.append(msg)
    if unmapped:
        failures.append(f"{unmapped} sampled cart hashes are not model "
                        f"prefixes")
    if bad:
        failures.append(f"{bad} of {len(e2)} sampled demo frames differ from "
                        f"the model")
    else:
        print(f"demo cycle: {len(e2)} sampled frames aligned by their cart "
              f"hash and compared to the model (epoch 2), 0 mismatches")
    if hs.get(2) != want_hash:
        failures.append(f"cycle epoch 2 hash {hs.get(2)!r} != model hash "
                        f"{want_hash:#010x} (the hash covers all "
                        f"{len(states)} frames)")
    else:
        print(f"demo cycle: every one of {len(states)} frames covered by the "
              f"cart's hash {want_hash:#010x} = the model's")
    # events against build/demo.json
    want = json.load(open(os.path.join(ROOT, "build", "demo.json")))
    for name in ("kills", "cracks", "crack_jumps"):
        got = [list(x) if isinstance(x, tuple) else x for x in ev[name]]
        if got != want[name]:
            failures.append(f"model {name} {got} != build/demo.json {want[name]}")
    if ev["lock"] != want["lock_frames"]:
        failures.append(f"model lock frames {ev['lock']} != "
                        f"build/demo.json {want['lock_frames']}")
    if sorted(ev["rings"]) != want["rings"]:
        failures.append(f"model rings {sorted(ev['rings'])} != {want['rings']}")
    if len(ev["angles"]) != want["angles"]:
        failures.append(f"model dome angles {len(ev['angles'])} != "
                        f"{want['angles']}")
    print(f"demo events: {len(ev['kills'])} kills (first {ev['kills'][0]}), "
          f"cracks {ev['cracks']}, jumps over cracks {ev['crack_jumps']}, "
          f"lock frames {ev['lock']}, rings {sorted(ev['rings'])}, "
          f"{len(ev['angles'])} dome angles")
    if ev["max_bullets"] > 1:
        failures.append(f"the demo has {ev['max_bullets']} player bullets in "
                        f"flight (want <= 1)")
    else:
        print(f"player bullets: at most {ev['max_bullets']} in flight over "
              f"the {len(states)}-frame cycle")

    # proof 3: the AES demo-sound toggle and its row-21 confirmation
    failures.extend(demo_aes_sound(p, f, s, inputs, seed, level))

    # proof 2: two cycles identical. The hashes prove every frame; the
    # sampled lines prove page/title_t and let a mismatch be localised.
    if e3:
        bad3 = 0
        for rec in e3.values():
            idx = hindex.get(rec["hash"])
            if idx is None:
                bad3 += 1
                continue
            msg = compare_frame(rec, states[idx - 1], idx)
            if msg:
                bad3 += 1
                if bad3 <= 5:
                    failures.append("epoch 3 " + msg)
        if bad3:
            failures.append(f"{bad3} epoch 3 sampled frames differ from the "
                            f"model")
        if hs.get(2) == hs.get(3) == want_hash:
            print(f"two cycles: epoch 2 and epoch 3 have the same hash "
                  f"{want_hash:#010x} (all {len(states)} frames identical); "
                  f"{len(e2)} and {len(e3)} sampled frames also match")
        else:
            failures.append(f"cycle hashes differ: epoch 2 {hs.get(2)!r}, "
                            f"epoch 3 {hs.get(3)!r}, model {want_hash:#010x}")

    # proof 4a: the B press restarts the demo
    b_epoch = None
    for ep in sorted(by_epoch):
        if ep >= 5 and by_epoch[ep]:
            first = min(by_epoch[ep], key=lambda r: r["fc"])
            if first["fc"] == 1 and first["page"] == 0 and first["t"] == 0:
                b_epoch = ep
                break
    if b_epoch is None:
        failures.append("no post-B demo restart on page 0 with title_t 0")
    else:
        first = min(by_epoch[b_epoch], key=lambda r: r["fc"])
        prev = [r for ep in sorted(by_epoch) if ep < b_epoch
                for r in by_epoch[ep]]
        prev_level = eff_level(max(prev, key=lambda r: r["n"])) if prev else 1
        if eff_level(first) == prev_level:
            failures.append(f"the B press did not change the level "
                            f"({prev_level} -> {eff_level(first)})")
        sampled = [r for r in by_epoch[b_epoch] if r["fc"] <= 100]
        bad_b = []
        for rec in sampled:
            if rec["hash"] == HASH_BASE:
                # the notifier caught the frame after demo_input advanced
                # demo_fc but before demo_hash_frame; its fields are the
                # completed frame but its hash is the initial accumulator.
                continue
            idx = hindex.get(rec["hash"])
            if idx is None:
                bad_b.append((rec, None))
                continue
            msg = compare_frame(rec, states[idx - 1], idx)
            if msg:
                bad_b.append((rec, msg))
        if len(sampled) < 90:
            failures.append(f"post-B demo only sampled {len(sampled)} of the "
                            f"first 100 frames")
        if bad_b:
            rec, msg = bad_b[0]
            failures.append("post-B restart: " +
                            (msg or f"frame {rec['fc']} hash not a model prefix"))
        if not bad_b and len(sampled) >= 90:
            print(f"B restart: epoch {b_epoch} page 0/title_t 0, level "
                  f"{prev_level} -> {eff_level(first)}, {len(sampled)} "
                  f"sampled frames of the first 100 equal the script's")

    # proof 4b (10-30): the probe taps C 11 times from the post-B epoch's
    # frame 120, turning the title through every page back to page 0. That
    # wrap restarts the demo: the next epoch's first frame is script frame 1
    # on page 0, title_t 0, before the post-B epoch reached frame 200 (a
    # wrap that skipped the restart would leave the script running out
    # mid-cycle, the ship frozen).
    if b_epoch is not None:
        c_epoch = b_epoch + 1
        last_b = max((r["fc"] for r in by_epoch[b_epoch]), default=0)
        recs = by_epoch.get(c_epoch) or []
        if not recs:
            failures.append(f"the C page-through did not restart the demo "
                            f"(no epoch {c_epoch}; epoch {b_epoch} reached "
                            f"frame {last_b})")
        else:
            first = min(recs, key=lambda r: r["fc"])
            if not (first["fc"] == 1 and first["page"] == 0 and first["t"] == 0):
                failures.append(f"epoch {c_epoch} began at frame {first['fc']}, "
                                f"page {first['page']}, title_t {first['t']}")
            elif last_b >= 200:
                failures.append(f"epoch {b_epoch} ran to frame {last_b}: the "
                                f"restart was not the C wrap")
            else:
                print(f"C wrap restart: epoch {b_epoch} ended at frame "
                      f"{last_b}, epoch {c_epoch} began at frame 1, page 0, "
                      f"title_t 0")

    # proof 5: the board is byte-identical over a whole cycle
    if 2 in b and 3 in b:
        if b[2] == b[3]:
            print(f"board: epoch 2 and epoch 3 both {b[2]} (126 bytes, "
                  f"identical before/after a whole cycle)")
        else:
            failures.append(f"board changed over a cycle: {b[2]} -> {b[3]}")
    else:
        failures.append("no B records at epoch 2 and 3 (need the board)")

    # proof 7: the sprite census and the frame budget over the cycle
    census = [r for r in c if r["epoch"] == 2]
    if not census:
        failures.append("no sprite census over the demo cycle")
    else:
        worst = max(census, key=lambda r: r["worst"])
        print(f"census: {len(census)} samples over the cycle, worst "
              f"{worst['worst']} sprites on line {worst['line']} "
              f"(limit {SPRITE_LIMIT})")
        if worst["worst"] > SPRITE_LIMIT:
            failures.append(f"the demo cycle has {worst['worst']} sprites on "
                            f"line {worst['line']} (limit {SPRITE_LIMIT})")
    marks = [r for r in m if r["epoch"] == 2]
    if not marks:
        failures.append("no framemark records over the demo cycle")
        return failures

    def _norm(v):
        return v + FRAME_LINES if v < 0 else v

    def _span(r):
        """the frame's work in lines, without the modulo: a frame whose work
        reached the next vblank return wraps to >= FRAME_LINES, and a start
        below the vblank means the previous frame overran."""
        s, e = _norm(_vpos(r["start"])), _norm(_vpos(r["end"]))
        if s >= 240:
            if e >= s:
                return FRAME_LINES + (e - s)
            return FRAME_LINES - s + e
        if e >= s:
            return e - s
        return FRAME_LINES - s + e

    worst_span, worst_start, worst_end, worst_fc = -1, 0, 0, 0
    late_starts = 0
    for r in marks:
        if r["start"] == 0 and r["end"] == 0:
            continue
        s = _norm(_vpos(r["start"]))
        span = _span(r)
        if s < 240:
            late_starts += 1
            if late_starts <= 3:
                failures.append(
                    f"demo frame {r['fc']}: the frame started at vpos {s}, "
                    f"not the vblank return ({VBLANK_RETURN}): the previous "
                    f"frame overran")
        if span > worst_span:
            worst_span = span
            worst_start = s
            worst_end = _norm(_vpos(r["end"]))
            worst_fc = r["fc"]
    if worst_span < 0:
        failures.append("no framemark records over the demo cycle")
        return failures
    print(f"framemark: worst work span {worst_span} scanlines "
          f"(vpos {worst_start} -> {worst_end}, demo frame {worst_fc}); "
          f"limit {WORST_LIMIT}")
    if worst_span > WORST_LIMIT:
        failures.append(f"the demo cycle's worst work span is {worst_span} "
                        f"scanlines (> {WORST_LIMIT}), at demo frame "
                        f"{worst_fc} (vpos {worst_start} -> {worst_end})")
    if late_starts:
        failures.append(f"{late_starts} demo frames started after the vblank "
                        f"return (a previous frame overran)")

    # P1 proof 1: every demo frame shown on exactly one video frame. The
    # notifier may miss samples (n and fc both jump), but a dropped frame
    # moves n - fc; it must stay constant across the cycle.
    base_d = marks[0]["n"] - marks[0]["fc"]
    drops = []
    for r in marks:
        d = r["n"] - r["fc"]
        if d != base_d:
            drops.append((r["fc"], r["n"], d))
            if len(drops) <= 5:
                failures.append(
                    f"demo frame {r['fc']} (MAME frame {r['n']}): n - fc is "
                    f"{d}, want {base_d}: a frame dropped")
    if drops:
        failures.append(f"{len(drops)} demo frames break n - fc == {base_d}")
    else:
        print(f"frame pace: n - fc == {base_d} on all {len(marks)} sampled "
              f"demo frames (0 dropped frames)")
    return failures


def demo_start(d, g, t, b, go, c, m, snaps, hs, states, ev, seed, level):
    failures = demo_props_angle(d)
    prefix = model_hashes(states)
    hindex = {}
    for i, h in enumerate(prefix, 1):
        hindex.setdefault(h, i)
    if not g:
        failures.append("no G record (the START never began a game)")
        return failures
    first = min(g, key=lambda r: r["fc"])
    ts = first["title_seed"]
    want_seed = mm.mis_seed_from(ts)
    if first["mis_seed"] != want_seed:
        failures.append(f"the new game's seed is {first['mis_seed']:#06x}, "
                        f"want mis_seed_from(title_seed_t {ts}) = "
                        f"{want_seed:#06x}")
    ship = sm.Ship()
    mis = mm.Missiles(level=level, seed=want_seed)
    rules = rm.Rules(level)
    radar = radm.Radar()
    hm.frame_model((ship, mis, rules), 0, 0)
    radar.frame(ship, mis)
    model = dict(
        rules_level=rules.level,
        rules_nbroken=len(rules.broken),
        rules_lives=rules.lives,
        rules_integ=rules.integ,
        rules_dead_t=rules.dead_t,
        rules_dome_dead=rules.dome_dead,
        rules_game_over=rules.game_over,
        ship_angle=ship.angle,
        ship_lat=ship.lat,
        ship_cell=ship.cell,
        ship_move_left=ship.left,
        ship_lift=ship.lift,
        ship_jumped=ship.jumped,
        broken_hex=_broken_hex(ship),
        mis_rng=mis.rng,
        mis_timer=mis.timer,
        mis_level=mis.level,
        mis_kills=mis.kills,
        mis_dome_hits=mis.dome_hits,
        mis_score10=mis.score,
        mis_fire_req=mis.fire_req,
        mis_sfx=mis.sfx,
        radar_lock_t=radar.lock_t,
        radar_locked=radar.locked,
        slots=[(o.state, o.kind, o.ring, o.phi, o.life, o.r, o.dr)
               for o in mis.obj[:mm.NMIS]],
    )
    msg = compare_frame(first, model, "game frame 1")
    if msg:
        failures.append("fresh game: " + msg)
    else:
        print(f"START at the first jump: title_seed_t {ts}, seed "
              f"{want_seed:#06x}, the first game frame is a fresh NORMAL "
              f"game (0 broken, no missiles, the ship at the start cell)")
    # the last demo frame before Start must be mid-jump with missiles in
    # flight (the review focus: START while the demo ship is mid-jump)
    before = [r for r in d if r["n"] < first["n"]]
    last = max(before, key=lambda r: r["n"]) if before else None
    if last is None:
        failures.append("no demo frames before the START")
    else:
        flying = sum(1 for s in last["slots"] if s[0] == 1)
        if last["ship_move_left"] == 0:
            failures.append(f"the demo ship was not jumping at the last "
                            f"title frame (move_left 0, demo frame "
                            f"{last['fc']})")
        if flying == 0:
            failures.append(f"no missiles were in flight at the last title "
                            f"frame (demo frame {last['fc']})")
        print(f"START frame: the demo was at frame {last['fc']} with "
              f"{last['ship_move_left']} jump frames left and {flying} "
              f"missile(s) in flight")
    # the press itself is after the first crack-jump frame (dfc = frame + 1)
    jump_fc = first_crack_jump()
    if t:
        tr = max(t, key=lambda r: r["n"])
        if tr["fc"] != jump_fc + 1:
            failures.append(f"START was pressed after demo frame {tr['fc']}, "
                            f"want {jump_fc + 1} (the first jump over a crack "
                            f"is frame {jump_fc}, build/demo.json)")
    # proof 4b: GAME OVER return starts the demo at frame 0
    if not go:
        failures.append("the game never reached GAME OVER")
    go_n = min(go) if go else None
    ret_n = None
    if go_n is not None:
        # after GAME OVER the BIOS re-enters the cart: .bss is zeroed and
        # demo_restart() starts the demo at frame 1 (epoch 1 again), on the
        # played level's board page. Find that first post-GO frame 1.
        # the notifier can miss the first two frames of the re-entry; the
        # last title dfc is 1487, so fc <= 3 is unambiguous.
        for rec in d:
            if rec["n"] > go_n and rec["fc"] <= 3:
                ret_n = rec["n"]
                break
    if ret_n is None:
        failures.append("the returned title never restarted the demo")
    else:
        sampled = [r for r in d if r["n"] >= ret_n and r["fc"] <= 100]
        bad_ret = []
        for rec in sampled:
            if rec["hash"] == HASH_BASE:
                # as above: the frame's fields are complete but the hash is
                # the pre-frame accumulator (the notifier caught the gap).
                continue
            idx = hindex.get(rec["hash"])
            if idx is None:
                bad_ret.append((rec, None))
                continue
            msg = compare_frame(rec, states[idx - 1], idx)
            if msg:
                bad_ret.append((rec, msg))
        if len(sampled) < 90:
            failures.append(f"the returned demo only sampled {len(sampled)} "
                            f"of the first 100 frames")
        if bad_ret:
            rec, msg = bad_ret[0]
            failures.append("post-GAME-OVER restart: " +
                            (msg or f"frame {rec['fc']} hash not a model prefix"))
        if not bad_ret and len(sampled) >= 90:
            print(f"GAME OVER return: the demo restarted at frame 0 "
                  f"({len(sampled)} sampled frames of the first 100 equal "
                  f"the script's)")
    return failures


def main():
    snap, probe, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    seed, level, frames, inputs = parse_header()
    states, ev = model_states(inputs, seed, level)
    d, g, t, b, go, c, m, snaps, hs, p, f, s = parse(probe)
    if mode == "demo":
        failures = demo_cycle(d, g, t, b, go, c, m, snaps, hs, p, f, s,
                              states, ev, inputs, seed, level)
    elif mode == "demo-start":
        failures = demo_start(d, g, t, b, go, c, m, snaps, hs, states, ev,
                              seed, level)
    else:
        sys.exit(f"check_demo: unknown mode {mode}")
    if failures:
        print(f"FAIL {mode}:")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"PASS {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
