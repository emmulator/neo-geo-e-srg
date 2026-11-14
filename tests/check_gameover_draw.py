#!/usr/bin/env python3
"""Assertions for the M4-fixes Task 4 "the dome stays a ruin" boot-test.

  check_gameover_draw.py SNAP PROBE [GO_FRESH_ADDR]

scripts/gameover_draw_probe.lua drives the -DGAMEOVER_DRAW_TEST cart (a
one-life test build of the normal cart; the hook in src/main.c runs under
that flag and mirrors this checker's policy model) through a two-phase
scripted game and records, per MAME frame, the BIOS joypad read-backs and
the hook's debug byte; through both GAME OVERs it records the dome slots'
SCB3/SCB4/SCB1 words (Task C1), the shown broken-overlay slots, the decoded
fix rows, fresh dome dumps (cart frame 60 of the first game and the first
frames after the A-restart), and one snapshot per phase.  This checker:

  1. replays tests/rules_model.py + tests/ship_model.py + tests/mis_model.py
     with exactly the recorded inputs and the hook's semantics (one life
     at a fresh game; seeding and parking after the first GAME OVER) to
     state, from the rules, the model's frames: the phase-1 dome death,
     its GAME OVER, the A restart, the phase-2 cell death and GAME OVER —
     the "frame budget derived from the rules" the task asks for;
  2. proves the phase-1 (dome-death) GAME OVER keeps the RUIN: from the
     model's GAME OVER frame through the A restart, every sampled dome
     slot holds the ruin's SCB3 chain (one row shorter, RUIN_TOP px down
     the box; Task V2) and the box's SCB4 words, and its SCB1 rows are the
     ruin's words in PAL_RUIN (not SCB3 0), every shown overlay slot is a SMOKE
     slot (Task C4: the ruin keeps smoking), the fix layer says GAME OVER,
     and the phase-1 snapshot's dome box shows the ruin's pixels (the same
     pixel proof as the collapse leg);
  2b. Task C4: on every frame from GAME OVER to after the A restart, the
     nine smoke slots' words equal the header's tables at the collapse's
     own g (wrapping from SMOKE_T with SMOKE_LOOP/SMOKE_PERIOD: the run
     watches >= 300 frames from the burst, more than the 144-frame loop);
     after A every smoke slot is hidden and the fresh-dome check stays
     unchanged;
  3. proves the A restart brings back a fresh dome: the post-A fresh
     dump's slots equal the first game's fresh dump (both are fresh
     domes at the start cell, view 0) and no overlay slot is shown;
  4. proves a non-dome GAME OVER keeps today's look: under the phase-2
     GAME OVER (a cell death on the broken cell 5), the dome slots show
     the whole dome (SCB3 = the whole fixed chain words) and the seeded broken
     cells' overlays are shown (the 13 cells of rings 0..4's top-facing
     half, packed per the geometry tables) — the dome with its real
     broken tiles stays under GAME OVER;
  5. Task C5, the sprite census: every frame from the phase-1 dome
     death's split through the GAME OVER to the A restart (>= 300 frames
     from the burst) has a worst scanline <= 96; the worst frame's raw
     SCB3 dump recounts and lists the slots by range; with the sticky bit
     ignored the worst is at least 19 lower; and the measured worst is
     stated against COLLAPSE_WORST_LINE.

The slot ranges come from the one slot map (M5 Task 1): build/slots.json
is generated from src/slots.h by the Makefile.
"""
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import render_broken as rb  # noqa: E402
import render_collapse as rc  # noqa: E402  (the ruin picture, Task C1)
import layout as lay  # noqa: E402

# the one sprite slot map (src/slots.h -> build/slots.json)
_SLOTS = json.load(open(os.path.join(ROOT, "build", "slots.json")))

import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import rules_model as rm  # noqa: E402
import ship_model as sm  # noqa: E402
import hud_model as hm  # noqa: E402  (Task G1's GAME OVER rows)
import check_flow as cf  # noqa: E402  (the thick title font's row decoder)

from PIL import Image  # noqa: E402
import neo_palette as npal  # noqa: E402  (the play backdrop: the sky)

PHASE = 0
DOME_X, DOME_Y = lay.d.DOME_X, lay.d.DOME_Y  # the dome box's top-left (dome.h)
DOME_W, DOME_H = lay.d.DOME_W, lay.d.DOME_H  # the box size (geometry.py's knob)
DOME_COLS = _SLOTS["DOME_COUNT"]
DOME_ROWS = lay.d.DOME_ROWS
DOME_SPRITE = _SLOTS["DOME_SPRITE"]
OVERLAY_BASE = _SLOTS["BROKEN_SLOT_BASE"]
OVERLAY_AFTER = _SLOTS["BROKEN_SLOT_AFTER"]
PAL_RUIN = 55                    # src/dome.h (Task C1)
FRESH_FRAME = 60                 # the probe's first-game fresh dump frame
A_DELAY = 280                    # Task C4: 280 GAME OVER frames before A
# (the collapse's 77 + 280 = 357 frames from the burst: more than the
# 144-frame smoke loop, and the A restart is inside GAME_OVER_WAIT 295)
PAL_SMOKE = 57                   # src/collapse.h
SMOKE_SPRITE = _SLOTS["COLLAPSE_SMOKE_SPRITE"]
SMOKE_COUNT = _SLOTS["COLLAPSE_SMOKE_COUNT"]
COLLAPSE_SHAKE_NEO = 41          # src/rules.h COLLAPSE_SHAKE (x 59/50)
DEAD_FRAMES_NEO = 118            # src/rules.h DEAD_FRAMES
SCAN_LIMIT = 96                  # the LSPC's sprites per scanline
SEED_ORDER = (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 14)  # rings 0..4's
                                # top-facing half at view 0 (in broken order,
                                # i.e. ascending here — the checker sorts)
STEP0 = (27, 47, 71, 5, 0, 13)   # whole step-0 cells (the park targets)
PARK_CELL = 5                    # the phase-2 park: a seeded broken cell
WHOLE_CHAIN = [(((496 - DOME_Y) << 7) | lay.d.DOME_ROWS)] + [0x40] * (DOME_COLS - 1)  # whole dome SCB3 words


def _defines(path):
    """evaluate the header's #defines in order (the collapse base's parts)."""
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
            pass                    # a comment or an unparsed expression
    return out


def _header_ruin():
    """(views, cols, rows, top, ruin_tile, ruin_pal, base) from
    build/collapse_map.h and the parts' generated headers (the collapse part
    is LAST after the band). Task V2: `top` is RUIN_TOP, the ruin's first
    pixel row below the dome box's top (the box's empty top tile row is
    dropped from the picture)."""
    path = os.path.join(ROOT, "build", "collapse_map.h")
    d = _defines(path)
    txt = open(path).read()
    views, cols, rows = d["RUIN_VIEWS"], d["RUIN_COLS"], d["RUIN_ROWS"]
    top = d["RUIN_TOP"]
    m = re.search(r"static const u16 ruin_tile\[%d\]\[%d\]\[%d\] = \{(.*?)\};"
                  % (views, cols, rows), txt, re.S)
    assert m, "ruin_tile missing from build/collapse_map.h"
    vals = [int(x) for x in re.findall(r"\d+", m.group(1))]
    assert len(vals) == views * cols * rows, (len(vals), views * cols * rows)
    tiles = []
    for v in range(views):
        b = v * cols * rows
        tiles.append([vals[b + c * rows:b + (c + 1) * rows]
                      for c in range(cols)])
    m = re.search(r"static const u16 ruin_pal\[16\] = \{(.*?)\};", txt, re.S)
    assert m, "ruin_pal missing from build/collapse_map.h"
    pal = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    radar = _defines(os.path.join(ROOT, "build", "radar_map.h"))
    ground = _defines(os.path.join(ROOT, "build", "ground_map.h"))
    mtn = _defines(os.path.join(ROOT, "build", "mountain_map.h"))
    con = _defines(os.path.join(ROOT, "build", "console_map.h"))
    props = _defines(os.path.join(ROOT, "build", "props_map.h"))
    band = _defines(os.path.join(ROOT, "build", "band_map.h"))
    base = (radar["RADAR_HEAD_TILE_BASE"] + radar["RADAR_HEAD_TILES"]
            + ground["GROUND_TILES"] + mtn["MTN_TILES"]
            + con["CON_TILES"] + props["PROP_TILES"] + band["BAND_TILES"])
    return views, cols, rows, top, tiles, pal, base


def _reshape(shape, vals):
    if len(shape) == 1:
        return vals
    stride = 1
    for x in shape[1:]:
        stride *= x
    return [_reshape(shape[1:], vals[i * stride:(i + 1) * stride])
            for i in range(shape[0])]


def _header_smoke():
    """Task C4's smoke tables from build/collapse_map.h: smoke_tile,
    smoke_pic/x/y/v/h and the SMOKE_LOOP/SMOKE_PERIOD/SMOKE_T wrap."""
    path = os.path.join(ROOT, "build", "collapse_map.h")
    txt = open(path).read()
    d = _defines(path)

    def arr(name, typ, dims):
        pat = r"static const %s %s\[%s\] = \{(.*?)\};" % (
            typ, name, r"\]\[".join(str(x) for x in dims))
        m = re.search(pat, txt, re.S)
        assert m, f"{name} missing from build/collapse_map.h"
        vals = [int(x) for x in re.findall(r"-?\d+", m.group(1))]
        want = 1
        for x in dims:
            want *= x
        assert len(vals) == want, (name, len(vals), want)
        return _reshape(dims, vals)

    ns, nsm = d["NPLUMES"], d["SMOKE_FRAMES"]
    return dict(n=ns, frames=nsm, cols=d["SMOKE_COLS"], rows=d["SMOKE_ROWS"],
                loop=d["SMOKE_LOOP"], period=d["SMOKE_PERIOD"],
                t=d["SMOKE_T"],
                tile=arr("smoke_tile", "u16",
                         (ns, nsm, d["SMOKE_COLS"], d["SMOKE_ROWS"])),
                pic=arr("smoke_pic", "u8", (ns, d["SMOKE_T"])),
                dx=arr("smoke_dx", "s8", (ns, d["SMOKE_T"])),
                lines=arr("smoke_lines", "u8", (ns, d["SMOKE_T"])),
                v=arr("smoke_v", "u8", (ns, d["SMOKE_T"])),
                h=arr("smoke_h", "u8", (ns, d["SMOKE_T"])),
                foot_x=arr("smoke_foot_x", "s16", (d["SMOKE_T"], ns)),
                foot_y=arr("smoke_foot_y", "s16", (d["SMOKE_T"], ns)),
                front=arr("smoke_front", "u8", (d["SMOKE_T"],)))


RUIN_VIEWS, RUIN_COLS, RUIN_ROWS, RUIN_TOP, RUIN_TILES, RUIN_PAL, \
    COLLAPSE_TILE_BASE = _header_ruin()
assert RUIN_VIEWS == 48, RUIN_VIEWS
assert RUIN_COLS == DOME_COLS, (RUIN_COLS, DOME_COLS)
assert RUIN_TOP == 16 and RUIN_ROWS == DOME_ROWS - RUIN_TOP // 16, (
    RUIN_TOP, RUIN_ROWS, DOME_ROWS)
SMOKE = _header_smoke()
SMOKE_BACK_SPRITE = _SLOTS["SMOKE_BACK_SPRITE"]
SMOKE_BACK_COUNT = _SLOTS["SMOKE_BACK_COUNT"]
SMOKE_TOTAL = SMOKE_BACK_COUNT + SMOKE_COUNT
SMOKE_SLOTS = (list(range(SMOKE_BACK_SPRITE,
                          SMOKE_BACK_SPRITE + SMOKE_BACK_COUNT))
               + list(range(SMOKE_SPRITE, SMOKE_SPRITE + SMOKE_COUNT)))
assert SMOKE["n"] * SMOKE["cols"] == SMOKE_TOTAL
assert SMOKE_BACK_SPRITE + SMOKE_BACK_COUNT == DOME_SPRITE
# the GAME OVER branch's expected SCB1 words per view/column/row (Task C1/V1)
RUIN_WORDS = [[[(COLLAPSE_TILE_BASE + RUIN_TILES[v][c][r], PAL_RUIN << 8)
                for r in range(RUIN_ROWS)] for c in range(RUIN_COLS)]
              for v in range(RUIN_VIEWS)]
# the box chain's SCB4 words (dome_rechain writes every column's box X)
BOX_SCB4 = [(DOME_X + c * 16) << 7 for c in range(DOME_COLS)]
# Task V2: the ruin's chain driver starts RUIN_TOP px down the box and is
# one tile row shorter; its followers stay sticky.
RUIN_CHAIN = [(((496 - (DOME_Y + RUIN_TOP)) << 7) | RUIN_ROWS)] \
    + [0x40] * (DOME_COLS - 1)


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
    """(records, samples, dome_slots, all_slots, overlays, rows, fresh, snaps,
    over, seeds, smoke) from the dump.
    records: [(rec, fc, cur, chg, flags)]; samples: {fc: [11 scb3 words]};
    dome_slots: {fc: {slot: dict(scb2, scb3, scb4, attr, tiles)}} (Task C1);
    all_slots: {fc: {slot: (scb3, scb4)}} at the phase-1 snapshot;
    overlays: {fc: [slot dicts]}; rows: {fc: [10 fix rows]}; fresh:
    [ [11 slot lines] per FRESH dump, in order ]; snaps: {n: fc};
    over: {fc: shown-overlay-slot count}; seeds: {mame frame: the cart's
    mis_seed_used (Task 1)}; smoke: {fc: {slot: dict(scb2, scb3, scb4,
    attr, tiles)}} (Task C4); census: {fc: (g, worst count, worst line)}
    (Task C5's K records); worst: (fc, count, line, {slot: scb3}) (Task
    C5's W/w raw dump)."""
    (records, samples, dome_slots, all_slots, overlays, rows, fresh, snaps,
     over, seeds, smoke) = [], {}, {}, {}, {}, {}, [], {}, {}, {}, {}
    census, worst = {}, None
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
            elif p[0] == "U":
                fc = int(p[1])
                dome_slots.setdefault(fc, {})[int(p[2])] = dict(
                    scb2=int(p[3], 16), scb3=int(p[4], 16),
                    scb4=int(p[5], 16), attr=int(p[6], 16),
                    tiles=[int(x, 16) for x in p[7:]])
            elif p[0] == "X":
                all_slots.setdefault(int(p[1]), {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
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
            elif p[0] == "FR":
                if cur_rows is not None:
                    cur_rows[int(p[1])] = cf._decode_row(
                        line.split(" ", 2)[2].rstrip("\n"))
            elif p[0] == "W":
                worst = (int(p[1]), int(p[2]), int(p[3]), {})
            elif p[0] == "w" and worst is not None:
                worst[3][int(p[1])] = int(p[2], 16)
            elif p[0] == "K":
                census[int(p[1])] = (int(p[2]), int(p[3]), int(p[4]))
            elif p[0] == "FRESH":
                cur_fresh = []
            elif p[0] == "h":
                if cur_fresh is not None:
                    cur_fresh.append(line.rstrip("\n").split(" ", 1)[1])
            elif p[0] == "SEED":
                seeds[int(p[1])] = int(p[2])
            elif p[0] == "SNAP":
                snaps[int(p[1])] = int(p[2])
            elif p[0] == "SM":
                fc = int(p[1])
                smoke.setdefault(fc, {})[int(p[2])] = dict(
                    scb2=int(p[3], 16), scb3=int(p[4], 16),
                    scb4=int(p[5], 16),
                    tiles=[(int(p[6 + i * 2], 16),
                            int(p[7 + i * 2], 16))
                           for i in range(SMOKE["rows"])])
            if cur_f is not None and cur_rows is not None and all(x is not None for x in cur_rows):
                rows[cur_f] = cur_rows
                cur_f, cur_rows = None, None
            if cur_fresh is not None and len(cur_fresh) == DOME_COLS:
                fresh.append(cur_fresh)
                cur_fresh = None
    return (records, samples, dome_slots, all_slots, overlays, rows, fresh,
            snaps, over, seeds, smoke, census, worst)


def replay(records, seed=None):
    """run the model over the recorded inputs; return (model, events,
    first) where model: {fc: (nbroken, dead_t, dome_dead, game_over, cell,
    alive, saw_go, seeded, dome_angle)}, events: [(frame, dome, nbroken,
    saw_go)] and
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
    model, events, hud = {}, [], {}
    i = first + PHASE
    m = 0
    while 0 <= i < len(records):
        rec, fc, cur, chg, flags = records[i]
        died = model_frame((ship, mis, rules), cur, chg, hook)
        m += 1
        model[m] = (len(rules.broken), rules.dead_t, rules.dome_dead,
                    rules.game_over, ship.cell, hook["alive"], hook["saw_go"],
                    hook["seeded"], ship.angle)
        hud[m] = hm.hud_rows(rules, mis)   # Task G1: rows 7/8
        if died:
            events.append((m, rules.dome_dead, len(rules.broken),
                           hook["saw_go"]))
        i += 1
    return model, events, first, hud


def _at(im, x, y):
    """a snapshot pixel for a 320x224 screen coordinate (scaled PNGs)."""
    w, h = im.size
    return tuple(im.getpixel((int(x * w / 320), int(y * h / 224)))[:3])


def sprite_boxes(scb3):
    """slot -> its on-screen (x, y, w, h) box for every drawn slot,
    resolving the sticky chains exactly as the hardware does."""
    boxes = {}
    prev = None
    for s in range(381):
        if s not in scb3:
            continue
        w3, w4 = scb3[s]
        h = w3 & 0x3f
        if w3 & 0x40 and prev is not None:      # sticky: inherit
            x, y, ph = prev
            x = (x + 16) & 0x1ff
            h = ph
        else:
            x, y = (w4 >> 7) & 0x1ff, 496 - (w3 >> 7)
        prev = (x, y, h)
        if h > 0:
            boxes[s] = (x, y, 16, h * 16)
    return boxes


def _covers(box, x, y):
    """the slot's box covers (x, y): SCB4's X is 9 bits and wraps at 512."""
    bx, by, bw, bh = box
    if not by <= y < by + bh:
        return False
    return ((x - bx) % 512) < bw


# Task C5: the census's slot ranges, in draw order (the collapse's sub-map
# sits inside the broken overlays' range, so its four ranges come first).
SCAN_RANGES = [
    ("ground", _SLOTS["GROUND_SPRITE"], _SLOTS["GROUND_COUNT"]),
    ("mountains", _SLOTS["MTN_SPRITE"], _SLOTS["MTN_COUNT"]),
    ("band", _SLOTS["BAND_SPRITE"], _SLOTS["BAND_COUNT"]),
    ("back props", _SLOTS["PROP_SPRITE"], _SLOTS["PROP_BACK_COUNT"]),
    ("missiles behind", _SLOTS["MIS_BEHIND_SPRITE"],
     _SLOTS["MIS_BEHIND_COUNT"]),
    ("dome", _SLOTS["DOME_SPRITE"], _SLOTS["DOME_COUNT"]),
    ("collapse smoke", _SLOTS["COLLAPSE_SMOKE_SPRITE"],
     _SLOTS["COLLAPSE_SMOKE_COUNT"]),
    ("collapse fragments", _SLOTS["COLLAPSE_FRAG_SPRITE"],
     _SLOTS["COLLAPSE_FRAG_COUNT"]),
    ("collapse fireball", _SLOTS["COLLAPSE_FIRE_SPRITE"],
     _SLOTS["COLLAPSE_FIRE_COUNT"]),
    ("collapse puffs", _SLOTS["COLLAPSE_PUFF_SPRITE"],
     _SLOTS["COLLAPSE_PUFF_COUNT"]),
    ("broken overlays", _SLOTS["BROKEN_SLOT_BASE"],
     _SLOTS["BROKEN_SLOT_COUNT"]),
    ("front props", _SLOTS["PROP_FRONT_SPRITE"],
     _SLOTS["PROP_FRONT_COUNT"]),
    ("ship", _SLOTS["SHIP_SPRITE"], _SLOTS["SHIP_COUNT"]),
    ("console", _SLOTS["CON_SPRITE"], _SLOTS["CON_COUNT"]),
    ("front missiles", _SLOTS["MIS_FRONT_SPRITE"],
     _SLOTS["MIS_FRONT_COUNT"]),
    ("explosions", _SLOTS["EXPL_SPRITE"], _SLOTS["EXPL_COUNT"]),
    ("radar", _SLOTS["RADAR_SPRITE"], _SLOTS["RADAR_COUNT"]),
]


def _effective_slots(raw):
    """slot -> (top, h), resolving the sticky chains exactly as the probe."""
    out = {}
    prev_top, prev_h = 0, 0
    for s in range(381):
        w3 = raw.get(s, 0)
        h = w3 & 0x3f
        if w3 & 0x40:
            top, h = prev_top, prev_h
        else:
            top = 496 - (w3 >> 7)
        prev_top, prev_h = top, h
        out[s] = (top, h)
    return out


def line_slots(raw, line):
    """the slots whose effective box covers `line`, in slot order."""
    eff = _effective_slots(raw)
    return [s for s in range(381)
            if eff[s][1] > 0 and eff[s][0] <= line < eff[s][0] + eff[s][1] * 16]


def no_sticky_line(raw, line):
    """the line's count with every sticky follower treated as height 0."""
    count = 0
    for s in range(381):
        w3 = raw.get(s, 0)
        if w3 & 0x40:
            continue
        h = w3 & 0x3f
        if h == 0:
            continue
        top = 496 - (w3 >> 7)
        if top <= line < top + h * 16:
            count += 1
    return count


def no_sticky_worst(raw):
    """(worst count, line) over all lines with followers ignored."""
    rows = [0] * 224
    for s in range(381):
        w3 = raw.get(s, 0)
        if w3 & 0x40:
            continue
        h = w3 & 0x3f
        if h == 0:
            continue
        top = 496 - (w3 >> 7)
        for y in range(max(0, top), min(223, top + h * 16 - 1) + 1):
            rows[y] += 1
    best = max(rows)
    return best, rows.index(best)


def _runs(slots):
    """contiguous slot numbers -> 'a-b' runs (a lone slot is 'a')."""
    out = []
    if not slots:
        return out
    start = prev = slots[0]
    for s in slots[1:]:
        if s == prev + 1:
            prev = s
            continue
        out.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = s
    out.append(f"{start}-{prev}" if start != prev else f"{start}")
    return out


def slot_list_by_range(slots):
    """[(range name, slots in it)] for the slots on the line, first range
    wins (the collapse's sub-map before the rest of the overlays)."""
    by = {}
    other = []
    for s in slots:
        for name, start, count in SCAN_RANGES:
            if start <= s < start + count:
                by.setdefault(name, []).append(s)
                break
        else:
            other.append(s)
    out = [(name, by[name]) for name, _start, _count in SCAN_RANGES
           if name in by]
    if other:
        out.append(("other", other))
    return out


def generator_worst_line():
    """COLLAPSE_WORST_LINE from the generated collapse header."""
    return _defines(os.path.join(ROOT, "build", "collapse_map.h"))[
        "COLLAPSE_WORST_LINE"]


def ruin_pixels(im, slot_dump, view, smoke_owner=None):
    """(compared, mismatches, first) for the ruin's opaque box pixels at
    `view` that no higher slot covers, against ruin_pal through neo_rgb
    (Task C1). Task C4/V1: the front smoke slots are excluded by their exact
    art (smoke_owner) instead of their boxes, so the ruin pixels visible
    through the smoke's transparent gaps are still compared (the smoke boxes
    would cover most of the ruin)."""
    global _BUILT
    if _BUILT is None:
        _BUILT = rc.build()
    boxes = sprite_boxes(slot_dump)
    high = {s: b for s, b in boxes.items()
            if s >= DOME_SPRITE + DOME_COLS and s not in SMOKE_SLOTS}
    pic = _BUILT["ruins"][view]
    rgb = [npal.neo_rgb(w) for w in RUIN_PAL]
    compared = mismatches = 0
    first = None
    for yy in range(DOME_Y + RUIN_TOP, DOME_Y + DOME_ROWS * 16):
        for xx in range(DOME_X, DOME_X + RUIN_COLS * 16):
            idx = int(pic[yy - DOME_Y][xx - DOME_X])
            if idx == 0:
                continue
            if any(_covers(b, xx, yy) for b in high.values()):
                continue
            if smoke_owner is not None and int(smoke_owner[yy, xx]) >= 0:
                continue
            compared += 1
            got = _at(im, xx, yy)
            want = rgb[idx]
            if got != tuple(want):
                mismatches += 1
                if first is None:
                    first = (xx, yy, got, tuple(want))
    return compared, mismatches, first


def smoke_at(p, g, angle):
    """(picture, left, top, v, height) for plume p at g and the scene's
    angle, or None when it has not started; from SMOKE_T on the tables
    repeat every SMOKE_PERIOD."""
    if g < 0:
        return None
    gg = g
    if g >= SMOKE["t"]:
        gg = SMOKE["loop"] + (g - SMOKE["loop"]) % SMOKE["period"]
    pic = SMOKE["pic"][p][gg]
    if pic == 0xff:
        return None
    left = SMOKE["foot_x"][angle][p] + SMOKE["dx"][p][gg] \
        - SMOKE["cols"] * 8
    top = SMOKE["foot_y"][angle][p] - SMOKE["lines"][p][gg]
    return (int(pic), left, top, SMOKE["v"][p][gg], SMOKE["h"][p][gg])


def smoke_bases(angle):
    """plume p -> the first of its two column slots at this angle: the next
    free FRONT pair when bit p of smoke_front is set, else the next free
    BACK pair."""
    front = SMOKE["front"][angle]
    fp = bp = 0
    bases = {}
    for p in range(SMOKE["n"]):
        if front & (1 << p):
            bases[p] = SMOKE_SPRITE + fp * SMOKE["cols"]
            fp += 1
        else:
            bases[p] = SMOKE_BACK_SPRITE + bp * SMOKE["cols"]
            bp += 1
    return bases


def smoke_slot_words(g, angle):
    """slot -> (scb2, scb3, scb4, [(tile, attr)] x SMOKE_ROWS or None) for
    all twelve plume columns at g and the scene's angle."""
    want = {slot: (0x0f00, 0, 0, None) for slot in SMOKE_SLOTS}
    bases = smoke_bases(angle)
    for p in range(SMOKE["n"]):
        s = smoke_at(p, g, angle)
        if s is None:
            continue
        pic, left, top, v, h = s
        for c in range(SMOKE["cols"]):
            slot = bases[p] + c
            want[slot] = (
                0x0f00 | v,
                ((496 - top) << 7) | h,
                ((left + c * 16) & 0x1ff) << 7,
                [(COLLAPSE_TILE_BASE + SMOKE["tile"][p][pic][c][r],
                  PAL_SMOKE << 8) for r in range(SMOKE["rows"])])
    return want


_BUILT = None


def smoke_frame(g, angle):
    """(owner, idx) for the generator's exact smoke blit at g and the scene's
    angle, in ascending slot order (a higher slot is on top). Used only to
    exclude the smoke's opaque pixels from the ruin pixel proof."""
    global _BUILT
    if _BUILT is None:
        _BUILT = rc.build()
    pics = _BUILT["smoke"]
    owner = np.full((224, 320), -1, int)
    idx = np.zeros((224, 320), int)
    bases = smoke_bases(angle)
    pieces = []
    for p in range(SMOKE["n"]):
        s = smoke_at(p, g, angle)
        if s is None:
            continue
        pic, left, top, v, h = s
        for c in range(SMOKE["cols"]):
            pieces.append((bases[p] + c, p, pic, left, top, v, h))
    for slot, p, pic, left, top, v, h in sorted(pieces):
        fr = np.zeros((224, 320), int)
        rc.blit(fr, pics[p][pic], np.arange(16), left, top, v=v, height=h)
        ys, xs = np.nonzero(fr)
        col = (xs - left) // 16
        good = (col >= 0) & (col < SMOKE["cols"])
        ys, xs = ys[good], xs[good]
        owner[ys, xs] = slot
        idx[ys, xs] = fr[ys, xs]
    return owner, idx


def expected_angle(model, fc):
    """the collapse's scene angle at the PREVIOUS frame (the committed
    smoke's angle); None when the model has no such frame."""
    st = model.get(fc - 1)
    return None if st is None else st[8]


def expected_g(model, p1_go, fc):
    """the collapse's own g at the PREVIOUS frame (collapse_prepare's g):
    collapse_frac - COLLAPSE_SHAKE while the collapse runs, then one more
    every frame under the dome death's GAME OVER. None = hidden (A ended
    it)."""
    st = model.get(fc - 1)
    if st is None:
        return None
    nbroken, dead_t, dome_dead, game_over, cell, alive, saw_go, seeded, angle = st
    if dead_t and dome_dead:
        f = rm.DEAD_FRAMES_NEO - dead_t
        if f >= COLLAPSE_SHAKE_NEO:
            return f - COLLAPSE_SHAKE_NEO
        return 0
    if game_over and dome_dead:
        return (rm.DEAD_FRAMES_NEO - COLLAPSE_SHAKE_NEO) + (fc - 1 - p1_go)
    return None


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    (records, samples, dome_slots, all_slots, overlays, rows, fresh, snaps,
     over, seeds, smoke, census, worst) = parse(probe)
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
    model, events, first, hud = replay(records, seed)
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

    # ---- C5 proof 1: the dome death's collapse/GAME OVER census ----
    burst = p1_death + COLLAPSE_SHAKE_NEO
    scan_start, scan_end = p1_death, a_fc
    missing = [fc for fc in range(scan_start, scan_end) if fc not in census]
    counted = scan_end - scan_start - len(missing)
    from_burst = a_fc - burst
    gameover_frames = a_fc - p1_go
    worst_c = worst_fc = worst_line = worst_g = None
    over_frames = []
    for fc in range(scan_start, scan_end):
        if fc not in census:
            continue
        g, c, line = census[fc]
        if c > SCAN_LIMIT:
            over_frames.append((fc, c, line))
        if worst_c is None or c > worst_c:
            worst_c, worst_fc, worst_line, worst_g = c, fc, line, g
    if missing:
        failures.append(f"the probe did not scan {len(missing)} dome-death "
                        f"frame(s): {missing[:8]}")
    if from_burst < 300:
        failures.append(f"only {from_burst} frames scanned from the burst to "
                        f"the A restart (need >= 300)")
    if over_frames:
        failures.append(f"the GAME OVER census found {len(over_frames)} frame(s) "
                        f"over the hardware's {SCAN_LIMIT} sprites per line "
                        f"(first: fc {over_frames[0][0]}, line {over_frames[0][2]}, "
                        f"{over_frames[0][1]} sprites)")
    if worst_c is not None and worst is not None:
        if (worst[0], worst[1], worst[2]) != (worst_fc, worst_c, worst_line):
            failures.append(
                f"the raw worst dump is fc {worst[0]}, {worst[1]} at line "
                f"{worst[2]}, but the census's is fc {worst_fc}, "
                f"{worst_c} at line {worst_line}")
    print(f"GAME OVER census: {counted} frames from fc {scan_start} (split) "
          f"to {scan_end - 1} (A restart - 1), {from_burst} from the burst "
          f"(>= 300) and {gameover_frames} of them GAME OVER; worst "
          f"{worst_c} at line {worst_line}, fc {worst_fc}, g {worst_g} "
          f"({'PASS' if worst_c is not None and worst_c <= SCAN_LIMIT else 'FAIL'}"
          f" against the hardware's {SCAN_LIMIT})")

    # ---- C5 proof 2: the raw dump recounts, and the line's slots ----
    if worst is None:
        failures.append("the probe wrote no raw worst dump")
    elif worst_c is not None:
        wfc, wcnt, wline, wraw = worst
        recount = len(line_slots(wraw, wline))
        if recount != wcnt:
            failures.append(f"the raw worst dump fc {wfc} recounts {recount} "
                            f"sprites on line {wline}, not its recorded "
                            f"{wcnt}")
        line_slot_list = line_slots(wraw, wline)
        print(f"raw dump fc {wfc}: {wcnt} sprites on line {wline} "
              f"(recount {recount})")
        for name, ss in slot_list_by_range(line_slot_list):
            print(f"  {name}: {len(ss)} slots ({', '.join(_runs(ss))})")
        # ---- C5 proof 4: the counter follows the sticky chains ----
        ign_worst, ign_line = no_sticky_worst(wraw)
        ign_same = no_sticky_line(wraw, wline)
        print(f"sticky ignored on the same frame: worst {ign_worst} at line "
              f"{ign_line}, {ign_same} on line {wline} "
              f"(sticky-resolved worst {wcnt}, {wcnt - ign_worst:+d})")
        if wcnt - ign_worst < 19:
            failures.append(f"the sticky chains are not seen: ignoring the "
                            f"sticky bit gives a worst {ign_worst}, only "
                            f"{wcnt - ign_worst} below {wcnt} (need >= 19)")
        # ---- C5 proof 3: the generator's model vs the measured worst ----
        gen = generator_worst_line()
        print(f"COLLAPSE_WORST_LINE {gen}: measured {wcnt}, "
              f"measured - model {wcnt - gen:+d}, model - measured "
              f"{gen - wcnt:+d} "
              f"({'model under-estimates' if wcnt > gen else 'model over-estimates' if wcnt < gen else 'model exact'})")

    if not samples:
        failures.append("probe wrote no dome-height samples")
    if not overlays:
        failures.append("probe wrote no overlay slot reads")
    if not rows:
        failures.append("probe wrote no fix rows")

    # Task G1: on every sampled frame, rows 7/8 equal the model's (blank
    # before GAME OVER, the thick text and its cap after it).
    bad_rows = []
    for fc in sorted(rows):
        if fc not in hud:
            continue
        if rows[fc][hm.HUD_GAMEOVER_ROW] != hud[fc][hm.HUD_GAMEOVER_ROW] \
           or rows[fc][hm.HUD_GAMEOVER_CAP_ROW] \
              != hud[fc][hm.HUD_GAMEOVER_CAP_ROW]:
            bad_rows.append((fc, rows[fc][hm.HUD_GAMEOVER_ROW],
                             hud[fc][hm.HUD_GAMEOVER_ROW]))
            break
    if bad_rows:
        failures.append(f"GAME OVER rows 7/8 do not match the model on "
                        f"sampled frame {bad_rows[0][0]} (drawn "
                        f"{bad_rows[0][1]!r}, model {bad_rows[0][2]!r})")

    def show_go(fc):
        return rows.get(fc) is not None and rows[fc][7].strip() == "GAME OVER"

    # ---- 2. phase 1: the dome-death GAME OVER keeps the ruin ----
    p1_frames = sorted(f for f in samples if p1_go <= f < (a_fc - 0))
    if not p1_frames:
        failures.append(f"no phase-1 samples in [{p1_go}, {a_fc})")
    else:
        bad_chain, bad_words = [], []
        for fc in p1_frames:
            ds = dome_slots.get(fc, {})
            if len(ds) != DOME_COLS:
                bad_words.append((fc, f"{len(ds)} dome slot lines, want "
                                     f"{DOME_COLS}"))
                continue
            for c in range(DOME_COLS):
                got = ds.get(DOME_SPRITE + c)
                if got is None:
                    bad_words.append((fc, DOME_SPRITE + c, "missing"))
                    break
                if got["scb3"] != RUIN_CHAIN[c]:
                    bad_chain.append((fc, c, got["scb3"], RUIN_CHAIN[c]))
                    break
                if got["scb4"] != BOX_SCB4[c]:
                    bad_words.append((fc, c, "scb4", got["scb4"],
                                      BOX_SCB4[c]))
                    break
                want_attr = PAL_RUIN << 8
                if got["attr"] != want_attr:
                    bad_words.append((fc, c, "attr", got["attr"], want_attr))
                    break
                view = (model.get(fc)[8] % RUIN_VIEWS
                        if model.get(fc) is not None else 0)
                want_tiles = [COLLAPSE_TILE_BASE + RUIN_TILES[view][c][r]
                              for r in range(RUIN_ROWS)]
                if got["tiles"][:RUIN_ROWS] != want_tiles:
                    bad_words.append((fc, c, "tiles",
                                      got["tiles"][:RUIN_ROWS], want_tiles))
                    break
            if bad_chain or bad_words:
                break
        if bad_chain:
            failures.append(
                f"phase-1 GAME OVER: the dome's ruin chain is not the box's "
                f"on {[b[0] for b in bad_chain]} (first: {bad_chain[0]})")
        if bad_words:
            failures.append(
                f"phase-1 GAME OVER: the dome's SCB1 words are not the "
                f"ruin's on {[b[0] for b in bad_words]} "
                f"(first: {bad_words[0]})")
        over_bad = [f for f in p1_frames
                    if any(OVERLAY_BASE <= s["slot"] < OVERLAY_AFTER
                           and not (SMOKE_SPRITE <= s["slot"]
                                    < SMOKE_SPRITE + SMOKE_COUNT)
                           for s in overlays.get(f, []))]
        if over_bad:
            failures.append(f"phase-1 GAME OVER: a non-smoke overlay is "
                            f"shown on {over_bad} "
                            f"(first: {overlays[over_bad[0]][:2]})")
        smoke_shown = [f for f in p1_frames
                       if any(SMOKE_SPRITE <= s["slot"]
                              < SMOKE_SPRITE + SMOKE_COUNT
                              for s in overlays.get(f, []))]
        go_bad = [f for f in p1_frames if not show_go(f)]
        if go_bad:
            failures.append(f"phase-1 GAME OVER: fix layer lacks GAME OVER "
                            f"on {go_bad}")
        print(f"phase-1: {len(p1_frames)} sampled frames through the GAME "
              f"OVER: dome holds the ruin chain "
              f"({not (bad_chain or bad_words) and 'yes' or 'NO'}), "
              f"no non-smoke overlay ({not over_bad and 'yes' or 'NO'}), "
              f"smoke shown on {len(smoke_shown)} of them, "
              f"GAME OVER text ({not go_bad and 'yes' or 'NO'})")

    # ---- 2b. Task C4: the smoke follows the collapse's own g, with wrap ----
    smoke_frames = sorted(fc for fc in smoke if fc >= p1_go - 1)
    burst_fc = p1_death + COLLAPSE_SHAKE_NEO
    if not smoke_frames:
        failures.append("the probe dumped no smoke words through the GAME OVER")
    else:
        first_smoke = smoke_frames[0]
        if a_fc - burst_fc < 300:
            failures.append(f"only {a_fc - burst_fc} frames from the burst "
                            f"to the A restart (need at least 300)")
        if a_fc - first_smoke < 280:
            failures.append(f"only {a_fc - first_smoke} smoke frames "
                            f"sampled through the GAME OVER (need at least "
                            f"280)")
        smoke_bad = []
        slot_frames = 0
        frames = 0
        max_g = None
        switches = 0
        prev_front = None
        for fc in sorted(fc for fc in smoke
                         if first_smoke <= fc <= a_fc + 8):
            # the A restart frame hands the overlay range back to
            # src/cracks.c, which hides the smoke slots at once (the
            # collapse's own hide is committed on the next frame).
            g = None if fc >= a_fc else expected_g(model, p1_go, fc)
            angle = None if g is None else expected_angle(model, fc)
            frames += 1
            if g is not None:
                front = SMOKE["front"][angle]
                if prev_front is not None:
                    switches += bin(front ^ prev_front).count("1")
                prev_front = front
                want = smoke_slot_words(g, angle)
            for slot in SMOKE_SLOTS:
                rec = smoke[fc].get(slot)
                if rec is None:
                    smoke_bad.append((fc, slot, "no SM record"))
                    continue
                slot_frames += 1
                if g is None:
                    if rec["scb3"] != 0:
                        smoke_bad.append((fc, slot, "not hidden after A",
                                          f"0x{rec['scb3']:04x}"))
                    continue
                if angle is None:
                    smoke_bad.append((fc, slot, "no angle"))
                    continue
                max_g = g if max_g is None else max(max_g, g)
                w = want[slot]
                got = (rec["scb2"], rec["scb3"], rec["scb4"])
                if got != w[:3]:
                    smoke_bad.append(
                        (fc, slot, "SCB2/3/4",
                         f"got {got[0]:04x},{got[1]:04x},{got[2]:04x} "
                         f"want {w[0]:04x},{w[1]:04x},{w[2]:04x}"))
                if w[3] is not None:
                    for r in range(SMOKE["rows"]):
                        if rec["tiles"][r] != w[3][r]:
                            smoke_bad.append((fc, slot, f"row {r}",
                                              rec["tiles"][r], w[3][r]))
                            break
        if smoke_bad:
            failures.append(f"{len(smoke_bad)} smoke word mismatches through "
                            f"the GAME OVER (first: {smoke_bad[0]})")
        if max_g is None or max_g < SMOKE["t"]:
            failures.append(f"the smoke never reached the wrap (max g "
                            f"{max_g}, SMOKE_T {SMOKE['t']})")
        print(f"GAME OVER smoke: {frames} frames, {slot_frames} slot-frames "
              f"from fc {first_smoke} (burst {burst_fc}, A restart {a_fc} = "
              f"{a_fc - burst_fc} frames from the burst, max g {max_g}, "
              f"{switches} front/back switches checked; "
              f"{'all match the tables with the wrap' if not smoke_bad else 'MISMATCH'})")

    # the phase-1 snapshot's dome box must show the ruin's pixels
    if 1 in snaps:
        snap_fc = snaps[1]
        if snap_fc not in all_slots:
            failures.append(f"the probe dumped no slots at phase-1 snapshot "
                            f"fc {snap_fc}")
        else:
            im = Image.open(snaps_snap(snap_png, probe, 1)).convert("RGB")
            snap_g = expected_g(model, p1_go, snap_fc)
            snap_angle = expected_angle(model, snap_fc)
            snap_view = (model.get(snap_fc)[8] % RUIN_VIEWS
                         if model.get(snap_fc) is not None else 0)
            smoke_owner = (smoke_frame(snap_g, snap_angle)[0]
                           if snap_g is not None and snap_angle is not None
                           else None)
            compared, mismatches, first_px = ruin_pixels(
                im, all_slots[snap_fc], snap_view, smoke_owner)
            if compared < 2000:
                failures.append(f"phase-1 GAME OVER snapshot: only {compared} "
                                f"ruin pixels compared (need at least 2000)")
            if mismatches:
                failures.append(f"phase-1 GAME OVER snapshot: {mismatches} of "
                                f"{compared} ruin pixels differ from ruin_pal "
                                f"through neo_rgb (first {first_px})")
            print(f"phase-1 GAME OVER snapshot fc {snap_fc} (view {snap_view}, "
                  f"g {snap_g}): {compared} opaque ruin pixels not covered "
                  f"by a higher slot compared, {mismatches} mismatches")
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
        # the smoke's hide is committed on the frame after the A restart
        # (the restart itself still displays the previous frame's smoke).
        for f_ in (a_fc + 1, a_fc + 2):
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
        whole_ok = all(samples[f] == WHOLE_CHAIN for f in p2_frames)
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
    print(f"PASS gameover-draw: a dome-death GAME OVER holds the ruin "
          f"(the box chain + SCB1 words + the snapshot's pixels; no "
          f"overlays), A restarts a fresh dome == the first game's, and a "
          f"cell-death GAME OVER keeps the broken-tile dome")
    return 0


def dome_lit_pixels(im):
    """the lit pixels inside the dome box (DOME_X,DOME_Y)-
    (DOME_X+DOME_W,DOME_Y+DOME_H) on the snapshot's scale — the dome's
    glass/glow colours are all drawn pixels, and nothing else draws in the
    box during a GAME OVER with the dome hidden (the HUD rows are above the
    box, the missiles were cleared on the death, the ship is hidden, the
    overlays are hidden). Dome-scenery Task 4's play backdrop is the sky, so
    the backdrop pixel is not counted (npal.is_lit). The box bounds come
    from src/dome.h. Dome-scenery Tasks 5 and 8: the grass fills the box's
    lower rows and the lowered console's art reaches y 195..199 at the box's
    left and right edges (30 pixels), so both static pictures' colours are
    subtracted too — a GAME OVER with the dome hidden has no dome pixel, and
    the console's own colours are provably not the dome's (the two banks do
    not share a word). Dome-scenery Task 12: the props stand on the grass
    and reach into the box, so their own colours are left out too."""
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    out = []
    for yy in range(int(DOME_Y * sy), int((DOME_Y + DOME_H) * sy)):
        for xx in range(int(DOME_X * sx), int((DOME_X + DOME_W) * sx)):
            px = im.getpixel((xx, yy))
            # dome-scenery Task 5: the ground fills the dome box's lower
            # rows, so the static grass must not count as a dome pixel;
            # Task 8: the lowered console's wing trim is in the box's
            # bottom corners, so its colours are subtracted too; Task 12:
            # the props stand on the grass and their tall columns reach
            # into the box, so a prop's own colours are not dome pixels
            # either (the dome is hidden at GAME OVER, the props are not)
            if npal.is_lit(px, npal.SKY_RGB) and not npal.is_grass(px) \
               and not npal.is_console_only(px) and not npal.is_prop(px):
                out.append((xx, yy))
    return out


def snaps_snap(snap_png, probe, idx):
    """MAME writes 0000.png, 0001.png, ... under the snapshot directory's
    machine subdir; the checker walks them in order (the probe's SNAP
    records carry the frames)."""
    # the leg's own output directory ($OUT: snap.png's directory). Its
    # snap/ holds this run's PNGs only; two levels up was the whole
    # build/ (it worked while every leg shared build/boot, and walked
    # other legs' snapshots once each leg got its own directory).
    base = os.path.dirname(os.path.abspath(snap_png))
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
