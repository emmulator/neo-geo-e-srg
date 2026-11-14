"""Assertions for the high-score boards Task B6 entry-screen boot-test
(scripts/entry_probe.lua).

  check_entry.py SNAP PROBE FRAMECNT_ADDR ENTRY_STATE_ADDR ENTRY_FC_ADDR
                 FLOW_STATE_ADDR CARDLOG_ADDR CASE

It proves, for the `entry-lives` (a lives-out GAME OVER over the dome) and
`entry-ruin` (a collapse GAME OVER over the ruin) runs:

  1. GAME OVER shows for exactly 118 frames, then the cart enters
     FLOW_ENTRY; B2's three-space insert/save at GAME OVER is gone (the
     board is still the defaults there).
  2. every entry frame's entry_state equals tests/entry_model.py replayed
     from the recorded inputs, and every entry frame's recorded REG_SOUND
     writes equal the commands its sfx bits call for (type/back/bell then
     tick), frame by frame; the counts of each command are printed. The
     typed sequence exercises a held left turn, an erase, the third-initial
     auto-jump and END. The final initials are AAB.
  3. every entry frame's ship.dome_angle equals entry_dome_angle(state,
     the GAME OVER angle).
  4. every entry frame's 38 ring slots equal build/ring_map.h's geometry
     at the staged phase (tiles, palette banks, SCB2/SCB3/SCB4, the
     back-to-front ring_order and the pointer blink), allowing the one
     staging lag (the first entry frame's ring is still hidden). K2: every
     entry frame's FLY_SPRITE words equal the flight tables at (fly_k, the
     flying letter's initial slot, fly_t) or SCB3 0 when it is hidden.
  5. the entry fix rows 2/4/6 and their caps 3/5/7 equal the design's
     text in the thick title font, with the next initial blinking every
     16 frames; K2: while a letter is flying its cell is blank and the
     blinking "_" is not drawn, so row 6 shows ninit - 1 letters.
  6. the sprites-per-scanline census on every entry frame is <= 96; the
     worst line/count and its dome angle are printed. The entry-ruin leg
     holds its first right turn through a full circle (the target passes
     every ring position), so the census covers every angle the leg
     reaches: the checker states the views, angles and front/back
     switches, and the ruin's SCB3/SCB4/SCB1 words are checked on every
     entry frame (Task V2). K2: the efc 6 mid-flight snapshot's flyer
     pixels equal tile fly_k through the kind-2 palette, where no higher
     slot covers them.
  7. END stores the typed initials and the GAME OVER score at the rank the
     GAME OVER board gave, saves the board to the fresh AES card
     (LOAD 2:81, SAVE 3:81, FORMAT 0:0, SAVE 3:0), and the returned title
     opens on the played level's board page with the new entry's row
     blanking every other 16 frames.
"""
import glob
import json
import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import board_model as bm          # noqa: E402
import entry_model as em          # noqa: E402
import hud_model as hm            # noqa: E402
import title_model as tm          # noqa: E402
import neo_palette as npal        # noqa: E402  (MAME's 15-bit -> RGB pipeline)
import render_collapse as rc      # noqa: E402  (the hardware zoom blit)
import check_flow as cf           # noqa: E402  (the title font's decoder)
import check_collapse as cc       # noqa: E402  (the ruin/plume art model)
import test_ring_render as rr     # noqa: E402  (ring_map.h and the C ROM base)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))
FLY_SPRITE = SLOTS["FLY_SPRITE"]
SCAN_MAX = 96
TITLE_ROWS = 28
GAME_OVER_TEXT_FRAMES = 118
SUB = em.SUB
END_PHASE = em.END_PHASE
ERASE_PHASE = em.ERASE_POS * SUB
# src/sound.h's picker command numbers (K1); the MAME compare pins them.
SND_TICK, SND_TYPE, SND_BELL, SND_BACK = 10, 11, 12, 13


def _pairs(s):
    try:
        return [tuple(int(x, 16) for x in q.split(":")) for q in s.split(",") if q]
    except ValueError:
        return []


def parse(probe):
    records, entry, ang, ring, cens, efix = [], [], {}, {}, [], {}
    samples, title, bests, cards, worst = {}, {}, {}, {}, None
    ruin, smoke, esnap, eslots = {}, {}, None, {}
    snd, fly = {}, {}
    go = exit_ = ruin_pal = rule = None
    cur_f = cur_rows = None
    cur_ef = cur_ef_rows = None
    cur_ring = None
    cur_worst = False
    raw = {}
    with open(probe, "rb") as fh:
        for raw_line in fh:
            text = raw_line.decode("ascii", "replace")
            p = text.split()
            if not p:
                continue
            tag = p[0]
            if tag == "I":
                records.append((int(p[1]), int(p[2]), int(p[3]), int(p[4])))
            elif tag == "GO":
                go = (int(p[1]), int(p[2]), int(p[3]), int(p[4]), int(p[5]))
            elif tag == "RUIN":
                ruin_pal = int(p[3])
            elif tag == "RULE":
                rule = (int(p[3]), int(p[4]), int(p[5]))
            elif tag == "E":
                entry.append({
                    "n": int(p[1]), "efc": int(p[2]),
                    "phase": int(p[3]), "target": int(p[4]),
                    "ninit": int(p[5]), "init": (int(p[6]), int(p[7]), int(p[8])),
                    "hold": int(p[9]), "dir": int(p[10]), "done": int(p[11]),
                    "sfx": int(p[12]), "fly_t": int(p[13]),
                    "fly_k": int(p[14]), "cur": int(p[15]), "chg": int(p[16]),
                })
            elif tag == "SND":
                snd[int(p[1])] = (int(p[2]),
                                  [int(x) for x in p[3:]])
            elif tag == "ANG":
                ang[int(p[2])] = int(p[3])
            elif tag == "R":
                n, j = int(p[1]), int(p[2])
                if n not in ring:
                    ring[n] = [None] * 38
                ring[n][j] = (int(p[3], 16), int(p[4], 16),
                              int(p[5], 16), int(p[6], 16), int(p[7], 16))
            elif tag == "FLY":
                fly[int(p[1])] = (int(p[2]), int(p[3], 16), int(p[4], 16),
                                  int(p[5], 16), int(p[6], 16), int(p[7], 16))
            elif tag == "U":
                efc = int(p[1])
                rest = p[2:]
                scb4, scb3, scb1, i = [], [], [], 0
                for _c in range(cc.DOME_COLS):
                    scb4.append(rest[i])
                    i += 1
                    scb3.append(rest[i])
                    i += 1
                    rows_c = []
                    for _r in range(cc.RUIN_ROWS):
                        rows_c.append((rest[i], rest[i + 1]))
                        i += 2
                    scb1.append(rows_c)
                ruin[efc] = (scb4, scb3, scb1)
            elif tag == "SM":
                efc, slot = int(p[1]), int(p[2])
                scb2, scb3, scb4 = (int(x, 16) for x in p[3:6])
                rest = p[6:]
                assert len(rest) == 2 * cc.SMOKE_ROWS, len(rest)
                rows_c = [(int(rest[i * 2], 16), int(rest[i * 2 + 1], 16))
                          for i in range(cc.SMOKE_ROWS)]
                smoke.setdefault(efc, {})[slot] = (scb2, scb3, scb4, rows_c)
            elif tag == "ESNAP":
                esnap = (int(p[1]), int(p[2]))
            elif tag == "X":
                eslots.setdefault(int(p[1]), {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
            elif tag == "CEN":
                cens.append((int(p[1]), int(p[2]), int(p[3])))
            elif tag == "EF":
                cur_ef = int(p[1])
                cur_ef_rows = {}
            elif tag == "EW":
                if cur_ef_rows is not None:
                    cur_ef_rows[int(p[1])] = cf._decode_row(
                        text.split(" ", 2)[2].rstrip("\n"))
                    if len(cur_ef_rows) == 7:
                        # rows 2..7 (the entry text/caps) + row 8, which
                        # must be blank from the entry's first frame (Task
                        # G1: it was GAME OVER's thick-font cap row)
                        efix[cur_ef] = [cur_ef_rows[r] for r in range(2, 9)]
                        cur_ef_rows = None
            elif tag == "F":
                cur_f = int(p[1])
                cur_rows = [None] * 30
            elif tag == "W":
                if cur_rows is not None:
                    cur_rows[int(p[1])] = cf._decode_row(
                        text.split(" ", 2)[2].rstrip("\n"))
                    if all(r is not None for r in cur_rows):
                        samples[cur_f] = cur_rows
                        cur_f = cur_rows = None
                elif not cur_worst:
                    worst = (int(p[1]), int(p[2]), int(p[3]))
                    cur_worst = True
            elif tag == "w":
                raw[int(p[1])] = int(p[2], 16)
            elif tag == "B":
                bests[int(p[1])] = (int(p[2]), int(p[3]), int(p[4]),
                                    int(p[5]), p[6])
            elif tag == "CARD":
                cards[int(p[1])] = (int(p[2]), _pairs(p[3] if len(p) > 3 else ""))
            elif tag == "T":
                title[int(p[1])] = (int(p[3]), int(p[4]))
            elif tag == "SNAP":
                pass
            elif tag == "EXIT":
                exit_ = (int(p[1]), int(p[2]), int(p[3]))
    entry.sort(key=lambda e: e["n"])
    return (records, entry, ang, ring, cens, efix, samples, title, bests,
            cards, go, worst, raw, exit_, ruin_pal, rule, ruin, smoke,
            esnap, eslots, snd, fly)


def _ring_tables():
    n = rr.define("RING_N")
    phases = rr.define("RING_PHASES")
    x = rr.table("ring_x")
    y = rr.table("ring_y")
    scb2 = rr.table("ring_scb2")
    kind = rr.table("ring_kind")
    order = rr.table("ring_order")
    text = open(os.path.join(ROOT, "src", "ring_gfx.h")).read()
    pal_base = int(re.search(r"#define PAL_RING_BASE (\d+)", text).group(1))
    return (n, phases, x, y, scb2, kind, order, rr.ring_tile_base(),
            pal_base, rr.define("RING_POINTER"),
            rr.define("RING_POINTER_X"), rr.define("RING_POINTER_Y"))


def _fly_tables():
    """K2: the generated flight tables (build/ring_map.h), flattened."""
    return (rr.define("FLY_FRAMES"), rr.table("fly_x"), rr.table("fly_y"),
            rr.table("fly_scb2"))


def fly_pixels(im, slot_dump, prev):
    """(compared, mismatches, first) for the flying letter's opaque pixels
    that no higher slot covers, against tile fly_k through the ring's kind-2
    palette via neo_rgb. The snapshot's words are one staging frame behind
    the entry state, so the caller passes the PREVIOUS entry frame's flight
    fields (the same lag the ring-slot check uses)."""
    fly_n, fly_x, fly_y, fly_scb2 = _fly_tables()
    f = prev["fly_t"] - 1
    slot = prev["ninit"] - 1
    scb2 = fly_scb2[f]
    x = fly_x[slot * fly_n + f]
    y = fly_y[slot * fly_n + f]
    hz, v = (scb2 >> 8) & 0xf, scb2 & 0xff
    pic = rr.tiles()[prev["fly_k"]]
    frame = np.zeros((224, 320), int)
    rc.blit(frame, pic, np.arange(16), x, y, hz=hz, v=v, height=1)
    ring_pal = rr.table("ring_pal")
    rgb = [npal.neo_rgb(w) for w in ring_pal[32:48]]
    boxes = cc.sprite_boxes(slot_dump)
    high = {s: b for s, b in boxes.items() if s > FLY_SPRITE}
    compared = mismatches = 0
    first = None
    for yy in range(224):
        for xx in range(320):
            idx = int(frame[yy, xx])
            if idx == 0:
                continue
            if any(cc._covers(b, xx, yy) for b in high.values()):
                continue
            compared += 1
            got = cc._at(im, xx, yy)
            want = rgb[idx]
            if got != tuple(want):
                mismatches += 1
                if first is None:
                    first = (xx, yy, got, tuple(want))
    return compared, mismatches, first


def _entry_rows(level, rank, score10, ninit, init, blink, flying):
    def centre(s):
        col = (40 - len(s)) // 2
        return " " * col + s + " " * (40 - len(s) - col)

    rows = [None] * 9
    rows[2] = centre("NEW HIGH SCORE")
    rows[3] = rows[2]
    rows[4] = centre("%s  %s  %d" % (tm.LEVEL_NAMES[level],
                                     tm.RANKS[rank], score10 * 10))
    rows[5] = rows[4]
    shown = ninit - (1 if flying else 0)
    s = ""
    for i in range(3):
        if i < shown:
            s += chr(init[i])
        elif not flying and i == ninit:
            s += "_" if blink else " "
        else:
            s += " "
        if i < 2:
            s += " "
    rows[6] = centre(s)
    rows[7] = rows[6]
    rows[8] = " " * 40          # Task G1: GAME OVER's cap row is blank
    return rows


def _recount(raw, line):
    prev_top, prev_h = 0, 0
    count = 0
    for s in range(381):
        w3 = raw.get(s, 0)
        h = w3 & 0x3f
        if w3 & 0x40:
            top, h = prev_top, prev_h
        else:
            top = 496 - (w3 >> 7)
        prev_top, prev_h = top, h
        if h > 0 and top <= line < top + h * 16:
            count += 1
    return count


def main():
    snap, probe, framecnt_addr = sys.argv[1], sys.argv[2], sys.argv[3]
    entry_addr = int(sys.argv[4], 0)
    entry_fc_addr = int(sys.argv[5], 0)
    flow_state_addr = int(sys.argv[6], 0)
    cardlog_addr = int(sys.argv[7], 0)
    case = sys.argv[8]
    failures = []
    (records, entry, ang, ring, cens, efix, samples, title, bests, cards,
     go, worst, raw, exit_, ruin_pal, rule, ruin, smoke, esnap,
     eslots, snd, fly) = parse(probe)
    if not records:
        failures.append("no input records (the probe never reached the cart)")
    if go is None:
        failures.append("no GO record (the game never reached GAME OVER)")
    if not entry:
        failures.append("no E records (the cart never entered FLOW_ENTRY)")
    if not cens:
        failures.append("no census records (no entry frames)")
    if failures:
        print("FAIL entry-%s:" % case)
        for f_ in failures:
            print("  - " + f_)
        return 1

    _n, go_fc, level, base_angle, score10 = go
    if ruin_pal is None:
        failures.append("no RUIN record (the GAME OVER backdrop was not read)")
    elif case == "ruin" and ruin_pal != 55:
        failures.append(
            f"the collapse GAME OVER backdrop palette is {ruin_pal}, not "
            "the ruin's 55")
    elif case == "lives" and ruin_pal == 55:
        failures.append("the lives-out GAME OVER is over the ruin, not the dome")
    if rule is None:
        failures.append("no RULE record (the GAME OVER rules bytes were not read)")
    else:
        lives, dome_dead, game_over = rule
        if game_over != 1:
            failures.append(f"the GAME OVER rules byte is {game_over}, not 1")
        if lives != 0:
            failures.append(f"the GAME OVER lives byte is {lives}, not 0")
        if case == "lives" and dome_dead != 0:
            failures.append("the lives-out death's dome_dead byte is 1 "
                            "(it was a collapse, not a ship death)")
        if case == "ruin" and dome_dead == 0:
            failures.append("the ruin GAME OVER's dome_dead byte is 0 "
                            "(it was not the dome collapse)")
    if not (0 <= level < bm.NLEVELS):
        failures.append(f"GAME OVER level {level} is not 0..2")
        level = 1
    # ---- 1. GAME OVER's timing and B2's insert removal ----
    if len(entry) < 1:
        failures.append("no entry frames")
    first_entry = entry[0]["n"]
    if not (first_entry - go[0] >= GAME_OVER_TEXT_FRAMES):
        failures.append(
            f"the entry started {first_entry - go[0]} MAME frames after "
            f"GAME OVER; expected at least {GAME_OVER_TEXT_FRAMES}")
    # the entry's first frame's fc is the last game frame (hud_framecnt is
    # not advanced by the entry); the GAME OVER frame's fc is go_fc.
    go_board = cf.board_from_hex(bests[go[0]][4]) if go[0] in bests else None
    if go_board is None or not go_board.valid():
        failures.append("the GAME OVER frame has no valid flow_board record")
        rank = bm.NENTRIES
    else:
        if go_board.bytes126() != bm.Board().bytes126():
            failures.append(
                "the board changed on the GAME OVER frame (B2's "
                "three-space insert/save is still there)")
        rank = go_board.rank(level, score10)
    if rank >= bm.NENTRIES:
        failures.append(
            f"score10 {score10} does not qualify on level {level} "
            f"(rank {rank}); the run never entered the entry")

    # ---- 2. the entry machine vs tests/entry_model.py ----
    model = em.Entry()
    model.begin()
    previous = None
    saw_left_hold = saw_right_hold = saw_erase = saw_auto = False
    snd_count = {SND_TICK: 0, SND_TYPE: 0, SND_BELL: 0, SND_BACK: 0}
    snd_frames = 0
    flight_frames = 0
    for e in entry:
        model.frame(e["cur"], e["chg"])
        got = (e["phase"], e["target"], e["ninit"], e["init"][0],
               e["init"][1], e["init"][2], e["hold"], e["dir"], e["done"],
               e["sfx"], e["fly_t"], e["fly_k"])
        if got != model.state():
            failures.append(
                f"entry frame {e['efc']} (MAME {e['n']}): state {got} != "
                f"the model {model.state()} (input cur {e['cur']:#x} "
                f"chg {e['chg']:#x})")
            break
        # K1: the recorded sends are exactly the sfx bits' commands, in the
        # flow's order: type, backspace, bell, then the tick.
        want_snd = []
        if e["sfx"] & em.SFX_TYPE:
            want_snd.append(SND_TYPE)
        if e["sfx"] & em.SFX_BACK:
            want_snd.append(SND_BACK)
        if e["sfx"] & em.SFX_BELL:
            want_snd.append(SND_BELL)
        if e["sfx"] & em.SFX_TICK:
            want_snd.append(SND_TICK)
        rec = snd.get(e["n"])
        if rec is None:
            failures.append(
                f"entry frame {e['efc']} (MAME {e['n']}): no SND record")
            break
        got_efc, got_snd = rec
        if got_efc != e["efc"]:
            failures.append(
                f"entry frame {e['efc']}: the SND record's frame is "
                f"{got_efc}")
            break
        if got_snd != want_snd:
            failures.append(
                f"entry frame {e['efc']} (MAME {e['n']}): REG_SOUND "
                f"{got_snd} != the sfx {e['sfx']:#x} commands {want_snd}")
            break
        for cmd in got_snd:
            snd_count[cmd] = snd_count.get(cmd, 0) + 1
        snd_frames += 1
        if e["fly_t"] > 0:
            flight_frames += 1
        if e["dir"] == 2 and e["hold"] > 0:
            saw_left_hold = True
        if e["dir"] == 1 and e["hold"] > 0:
            saw_right_hold = True
        if previous is not None and previous["ninit"] == 2 \
                and e["ninit"] == 1 and e["phase"] == ERASE_PHASE:
            saw_erase = True
        if previous is not None and previous["ninit"] == 2 \
                and e["ninit"] == 3 and e["target"] == END_PHASE:
            saw_auto = True
        previous = e
    if not model.done:
        failures.append("the entry never reached done (END was not pressed)")
    if model.init != [ord("A"), ord("A"), ord("B")]:
        failures.append(
            f"the typed initials are {bytes(model.init)!r}, expected b'AAB' "
            "(A, B, erase B, A, B)")
    if not saw_left_hold:
        failures.append("no held left turn reached a repeat frame")
    if not saw_right_hold:
        failures.append("no held right turn reached a repeat frame")
    if not saw_erase:
        failures.append("no erase (ninit 2 -> 1 at ERASE) happened")
    if not saw_auto:
        failures.append("the third initial did not auto-jump to END")
    if entry[-1]["efc"] != len(entry):
        failures.append("the entry frame counter is not contiguous 1..n")

    # ---- 3. the dome angle ----
    for e in entry:
        want = (base_angle - (e["phase"] * 240 + em.PHASES // 2)
                // em.PHASES) % 240
        got = ang.get(e["efc"])
        if got != want:
            failures.append(
                f"entry frame {e['efc']}: dome angle {got}, expected "
                f"entry_dome_angle({e['phase']}, {base_angle}) = {want}")
            break

    if case == "ruin":
        # ---- 3b. the ruin and its plumes follow the angle every entry
        # frame; the first right turn is held through a full circle, so the
        # target passes every ring position and the census sees every angle
        # the leg reaches. ----
        views = set()
        angles_seen = set()
        positions_seen = set()
        ruin_frames = 0
        ruin_bad = []
        want_scb3 = tuple("%04x" % w for w in cc.RUIN_SCB3)
        want_scb4 = tuple("%04x" % w for w in cc.BOX_SCB4)
        for e in entry:
            efc = e["efc"]
            angle = ang.get(efc)
            if angle is None:
                ruin_bad.append((efc, "no ANG record"))
                break
            angles_seen.add(angle)
            positions_seen.add(e["target"] // em.SUB)
            view = angle % cc.RUIN_VIEWS
            views.add(view)
            if efc not in ruin:
                ruin_bad.append((efc, "no U record"))
                break
            got_scb4, got_scb3, got_scb1 = ruin[efc]
            if tuple(got_scb4) != want_scb4:
                ruin_bad.append((efc, "scb4", got_scb4))
                break
            if tuple(got_scb3) != want_scb3:
                ruin_bad.append((efc, "scb3", got_scb3, want_scb3))
                break
            for c in range(cc.RUIN_COLS):
                for r in range(cc.RUIN_ROWS):
                    want = ("%04x" % cc.RUIN_WORDS[view][c][r][0],
                            "%04x" % cc.RUIN_WORDS[view][c][r][1])
                    if got_scb1[c][r] != want:
                        ruin_bad.append((efc, c, r, got_scb1[c][r], want, view))
                        break
                else:
                    continue
                break
            if ruin_bad:
                break
            ruin_frames += 1
        if ruin_bad:
            failures.append(f"the entry ruin's SCB3/SCB4/SCB1 does not follow "
                            f"the angle (first: {ruin_bad[0]})")
        if len(views) != cc.RUIN_VIEWS:
            failures.append(f"only {len(views)} distinct ruin view(s) seen on "
                            f"the entry frames, want all {cc.RUIN_VIEWS}: "
                            f"{sorted(views)}")
        if len(angles_seen) < em.PHASES:
            failures.append(f"only {len(angles_seen)} distinct dome angle(s) "
                            f"seen, fewer than the full turn's {em.PHASES}")
        if positions_seen != set(range(em.N)):
            failures.append(f"the full turn passed {len(positions_seen)} ring "
                            f"positions, not all {em.N}: "
                            f"{sorted(positions_seen)}")

        # the plumes: the committed words are one frame behind (the staged
        # collapse_prepare), so entry frame e shows the previous frame's angle
        # and g; frame 1 shows the last GAME OVER frame's prepare.
        smoke_bad = []
        smoke_frames = 0
        slot_frames = 0
        switches = 0
        prev_front = None
        for i, e in enumerate(entry):
            efc = e["efc"]
            prev_angle = base_angle if i == 0 else ang.get(entry[i - 1]["efc"])
            if prev_angle is None:
                smoke_bad.append((efc, "no previous ANG"))
                break
            g = 194 + efc
            front = cc.SMOKE["smoke_front"][prev_angle]
            if prev_front is not None:
                switches += bin(front ^ prev_front).count("1")
            prev_front = front
            bases = cc.smoke_bases(prev_angle)
            for p in range(cc.NPLUMES):
                if front & (1 << p):
                    if bases[p] < cc.SMOKE_SPRITE:
                        smoke_bad.append((efc, p, "front bit but back slot",
                                          bases[p]))
                elif bases[p] >= cc.DOME_SPRITE:
                    smoke_bad.append((efc, p, "back bit but not below DOME",
                                      bases[p]))
            want = cc.smoke_slot_words(g, prev_angle)
            recs = smoke.get(efc, {})
            for slot in cc.SMOKE_SLOTS:
                rec = recs.get(slot)
                if rec is None:
                    smoke_bad.append((efc, slot, "no SM record"))
                    continue
                scb2, scb3, scb4, rows_c = rec
                w = want[slot]
                if (scb2, scb3, scb4) != w[:3]:
                    smoke_bad.append(
                        (efc, slot, "SCB2/3/4",
                         f"got {scb2:04x},{scb3:04x},{scb4:04x} "
                         f"want {w[0]:04x},{w[1]:04x},{w[2]:04x}"))
                if w[3] is not None:
                    for r in range(cc.SMOKE_ROWS):
                        if rows_c[r] != w[3][r]:
                            smoke_bad.append((efc, slot, f"row {r}",
                                              rows_c[r], w[3][r]))
                            break
                slot_frames += 1
            if smoke_bad:
                break
            smoke_frames += 1
        if smoke_bad:
            failures.append(f"{len(smoke_bad)} entry plume word mismatches "
                            f"(first: {smoke_bad[0]})")

        # ---- 3c. one entry-ruin snapshot: the ruin's pixels at its view ----
        if esnap is None:
            failures.append("no ESNAP record (the entry-ruin frame was not "
                            "snapped)")
        elif esnap[0] not in eslots:
            failures.append(f"no X slot dump at the entry snapshot MAME frame "
                            f"{esnap[0]}")
        else:
            snap_dir = os.path.join(os.path.dirname(os.path.abspath(probe)),
                                    "snap")
            pngs = sorted(glob.glob(os.path.join(snap_dir, "**", "*.png"),
                                    recursive=True))
            if len(pngs) < 2:
                failures.append(f"only {len(pngs)} snapshot(s) found; the "
                                f"entry-ruin snapshot is the last one")
            else:
                im = Image.open(pngs[-1]).convert("RGB")
                snap_efc = esnap[1]
                view = ang.get(snap_efc, 0) % cc.RUIN_VIEWS
                compared, mismatches, first_px = cc.ruin_pixels(
                    im, eslots[esnap[0]], view)
                if compared < 2000:
                    failures.append(f"only {compared} ruin pixels compared at the "
                                    f"entry snapshot efc {snap_efc} (need at "
                                    f"least 2000)")
                if mismatches:
                    failures.append(
                        f"{mismatches} of {compared} ruin pixels differ from "
                        f"ruin_pal through neo_rgb at the entry snapshot efc "
                        f"{snap_efc} (first {first_px})")
                print(f"entry snapshot efc {snap_efc} (view {view}): {compared} "
                      f"opaque ruin pixels not covered by a higher slot "
                      f"compared, {mismatches} mismatches")

                # K2: the same snapshot's flying letter: its words are one
                # staging frame behind the entry state (the ring-slot lag),
                # so use the previous entry frame's flight fields.
                idx = next((i for i, e in enumerate(entry)
                            if e["efc"] == snap_efc), None)
                if idx is None or idx == 0:
                    failures.append(
                        f"no entry frame record before the snapshot efc "
                        f"{snap_efc}")
                else:
                    prev = entry[idx - 1]
                    if prev["fly_t"] == 0:
                        failures.append(
                            f"the entry snapshot efc {snap_efc} is not "
                            "mid-flight (the previous frame has fly_t 0)")
                    else:
                        fcmp, fmis, ffirst = fly_pixels(
                            im, eslots[esnap[0]], prev)
                        # the 16x16 ring tile has ~150 opaque pixels; the
                        # flyer is the highest slot, so all should compare.
                        if fcmp < 100:
                            failures.append(
                                f"only {fcmp} flyer pixels compared at the "
                                f"entry snapshot efc {snap_efc} (need at "
                                "least 100)")
                        if fmis:
                            failures.append(
                                f"{fmis} of {fcmp} flyer pixels differ from "
                                f"tile {prev['fly_k']} through the kind-2 "
                                f"palette at the entry snapshot efc "
                                f"{snap_efc} (first {ffirst})")
                        print(f"entry snapshot efc {snap_efc} flyer "
                              f"(fly_k {prev['fly_k']}, slot "
                              f"{prev['ninit'] - 1}, fly_t {prev['fly_t']}): "
                              f"{fcmp} opaque flyer pixels not covered by a "
                              f"higher slot compared, {fmis} mismatches")

        print(f"entry ruin: {ruin_frames} frames, all {len(views)} views, "
              f"{len(angles_seen)} distinct angles, {len(positions_seen)}/{em.N} "
              f"ring positions; plumes: {smoke_frames} frames, "
              f"{slot_frames} slot-frames, {switches} front/back switches")

    # ---- 4. the ring slots ----
    (ring_n, phases, rx, ry, rscb2, rkind, rorder, tile_base, pal_base,
     pointer_tile, p_x, p_y) = _ring_tables()
    slots_checked = 0
    for i, e in enumerate(entry):
        slots = ring.get(e["n"])
        if slots is None:
            failures.append(f"entry frame {e['efc']}: no R records")
            break
        if i == 0:
            for j, got in enumerate(slots):
                if got is None or got[3] != 0:
                    failures.append(
                        f"entry frame 1 slot {j}: the ring is not hidden "
                        "before its first commit")
                    break
            continue
        prev = entry[i - 1]
        p = prev["phase"]
        for j in range(38):
            got = slots[j]
            if got is None:
                failures.append(f"entry frame {e['efc']}: slot {j} missing")
                break
            if j < ring_n:
                pos = rorder[p * ring_n + j]
                tile = tile_base + pos
                attr = (pal_base + rkind[p * ring_n + pos]) << 8
                scb2 = rscb2[p * ring_n + pos]
                scb3 = ((496 - ry[p * ring_n + pos]) << 7) | 1
                scb4 = rx[p * ring_n + pos] << 7
            else:
                tile = tile_base + pointer_tile
                attr = (pal_base + 2) << 8
                scb2 = 0x0fff
                scb3 = (((496 - p_y) << 7) | 1) \
                    if ((prev["efc"] >> 3) & 1) else 0
                scb4 = p_x << 7
            want = (tile, attr, scb2, scb3, scb4)
            if got != want:
                failures.append(
                    f"entry frame {e['efc']} slot {j}: {got} != the "
                    f"phase {p} tables {want}")
                break
            slots_checked += 1
        if failures:
            break

    # ---- 4b. K2: the flying letter's words ----
    fly_n, fly_x, fly_y, fly_scb2 = _fly_tables()
    assert fly_n == em.FLY_FRAMES == 20, fly_n
    fly_words = 0
    for i, e in enumerate(entry):
        rec = fly.get(e["n"])
        if rec is None:
            failures.append(f"entry frame {e['efc']}: no FLY record")
            break
        got_efc, tile, attr, scb2, scb3, scb4 = rec
        if got_efc != e["efc"]:
            failures.append(
                f"entry frame {e['efc']}: the FLY record's frame is "
                f"{got_efc}")
            break
        if i == 0:
            if scb3 != 0:
                failures.append(
                    f"entry frame 1 flyer slot {FLY_SPRITE}: the flyer is "
                    "not hidden before its first commit")
                break
            continue
        prev = entry[i - 1]
        if prev["fly_t"] > 0:
            slot = prev["ninit"] - 1
            f = prev["fly_t"] - 1
            want = (tile_base + prev["fly_k"], (pal_base + 2) << 8,
                    fly_scb2[f],
                    ((496 - fly_y[slot * fly_n + f]) << 7) | 1,
                    fly_x[slot * fly_n + f] << 7)
            if (tile, attr, scb2, scb3, scb4) != want:
                failures.append(
                    f"entry frame {e['efc']} flyer slot {FLY_SPRITE}: "
                    f"{(tile, attr, scb2, scb3, scb4)} != the flight tables "
                    f"at (fly_k {prev['fly_k']}, slot {slot}, "
                    f"fly_t {prev['fly_t']}) {want}")
                break
        else:
            if scb3 != 0:
                failures.append(
                    f"entry frame {e['efc']} flyer slot {FLY_SPRITE}: shown "
                    f"while fly_t is 0")
                break
        fly_words += 1
    for c in cens:
        if c[1] > SCAN_MAX:
            failures.append(
                f"census on entry frame {c[0]}: line {c[2]} has {c[1]} "
                f"sprites, over {SCAN_MAX} (stop; do not cut the ring)")
    if worst is None:
        failures.append("the probe wrote no worst census raw dump")
    else:
        wc, wl = worst[1], worst[2]
        if _recount(raw, wl) != wc:
            failures.append(
                f"the recorded worst {wc} at line {wl} does not recount "
                f"({_recount(raw, wl)})")
        if wc > SCAN_MAX:
            failures.append(f"the worst census {wc} at line {wl} is over "
                            f"{SCAN_MAX}")

    # ---- 5. the entry fix text ----
    text_frames = 0
    for i, e in enumerate(entry):
        if i == 0:
            continue
        rows = efix.get(e["n"])
        if rows is None:
            failures.append(f"entry frame {e['efc']}: no EF rows")
            break
        prev = entry[i - 1]
        blink = (prev["efc"] >> 4) & 1
        want = _entry_rows(level, rank, score10, prev["ninit"],
                           list(prev["init"]), blink, prev["fly_t"] > 0)
        for r in range(2, 9):
            got = rows[r - 2]
            if got != want[r]:
                failures.append(
                    f"entry frame {e['efc']} row {r}: {got!r} != {want[r]!r} "
                    f"(initials {list(prev['init'])}, blink {blink})")
                break
        if failures:
            break
        text_frames += 1

    # Task G1: row 8 (GAME OVER's thick-font cap row) is blank on EVERY
    # entry frame, including the first one that still shows GAME OVER's text
    # on row 7 before the entry rows commit.
    if not failures:
        for e in entry:
            rows = efix.get(e["n"])
            if rows is not None and rows[6].strip():
                failures.append(f"entry frame {e['efc']}: row 8 is "
                                f"{rows[6]!r}, want blank (GAME OVER's cap "
                                f"row must be gone)")
                break

    # ---- 6. the board, the card save and the returned title ----
    back_samples = []
    for n in sorted(samples):
        if n not in title or n not in bests:
            continue
        page, t = title[n]
        rows = samples[n]
        if page != level + 1 or t < 2:
            continue
        if rows[6].strip() != "HIGH SCORES":
            continue
        board = cf.board_from_hex(bests[n][4])
        if board is None or not board.valid():
            failures.append(f"returned title frame {n}: invalid flow_board")
            continue
        back_samples.append((n, rows, board, page, t))
    if not back_samples:
        failures.append("no drawn returned-title samples on the played "
                        "level's board page")
    else:
        want_board = bm.Board()
        want_board.insert(level, rank, bytes(model.init), score10)
        n0, rows0, board0, page0, t0 = back_samples[0]
        if board0.bytes126() != want_board.bytes126():
            failures.append(
                "the returned title's flow_board is not the expected "
                f"insert (rank {rank}, initials {bytes(model.init)!r}, "
                f"score10 {score10})")
        # the new entry's row and its cap must blink every other 16 frames
        row = tm.BOARD_FIRST_ROW + rank * tm.BOARD_STEP
        hidden_seen = shown_seen = 0
        for n, rows, board, page, t in back_samples:
            model_rows = tm.title_rows(page, level, t, board, 0)
            hidden = ((t - 2) >> 4) & 1
            for r in range(TITLE_ROWS):
                if r == hm.HUD_INTEG_ROW or r == 28:
                    continue
                expected = model_rows[r]
                if hidden and r in (row, row + 1):
                    expected = " " * 40
                if rows[r] != expected:
                    failures.append(
                        f"returned title frame {n} (page {page}, t {t}): "
                        f"row {r} {rows[r]!r} != {expected!r} (blink "
                        f"{hidden})")
                    break
            if hidden:
                hidden_seen += 1
                if rows[row].strip() or rows[row + 1].strip():
                    failures.append(
                        f"returned title frame {n}: the hidden blink phase "
                        f"still shows rank {rank}'s row")
            else:
                shown_seen += 1
                if rows[row].strip() != model_rows[row].strip():
                    failures.append(
                        f"returned title frame {n}: the shown blink phase "
                        f"does not show rank {rank}'s row")
        if hidden_seen == 0 or shown_seen == 0:
            failures.append(
                f"the blink was not seen in both phases (hidden "
                f"{hidden_seen}, shown {shown_seen})")

    # the card log: the last LOAD-bearing record before the return must
    # carry the full fresh-card sequence. The post-END samples are the ones
    # after the last entry frame and before the first title sample.
    end_n = entry[-1]["n"]
    first_title_n = min(title) if title else 10 ** 9
    log_pairs = None
    for n in sorted(cards):
        if n <= end_n or n >= first_title_n:
            continue
        if any(c == 2 for (c, _a) in cards[n][1]):
            log_pairs = cards[n][1]
    if log_pairs is None:
        failures.append("no post-END card-log record (the save was not read)")
    elif log_pairs != [(2, 0x81), (3, 0x81), (0, 0), (3, 0)]:
        failures.append(
            f"the post-END card log is {[(hex(c), hex(a)) for c, a in log_pairs]}, "
            "expected LOAD 2:81, SAVE 3:81, FORMAT 0:0, SAVE 3:0")

    if failures:
        print("FAIL entry-%s:" % case)
        for f_ in failures:
            print("  - " + f_)
        return 1
    wc, wl = worst[1], worst[2]
    wang = ang.get(worst[0])
    print(f"PASS entry-{case}: GAME OVER at fc {go_fc} for score10 "
          f"{score10} (rank {rank}); {len(entry)} entry frames and "
          f"{len(cens)} censuses with worst {wc} sprites on line {wl} "
          f"at dome angle {wang} (<= {SCAN_MAX}); {slots_checked} ring-slot "
          f"words matched the phase tables; {fly_words} flyer-slot frames "
          f"matched the flight tables ({flight_frames} entry frames flying); "
          f"{text_frames} fix-text frames "
          f"matched; the typed initials {bytes(model.init)!r} landed at rank "
          f"{rank} and the fresh card saved with LOAD 2:81, SAVE 3:81, "
          f"FORMAT 0:0, SAVE 3:0; the returned page {level + 1} blinked rank "
          f"{rank}'s row in both phases ({hidden_seen} hidden, "
          f"{shown_seen} shown); {snd_frames} entry SND records matched the "
          f"sfx bits with tick {snd_count[SND_TICK]}, type "
          f"{snd_count[SND_TYPE]}, bell {snd_count[SND_BELL]}, backspace "
          f"{snd_count[SND_BACK]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
