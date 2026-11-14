"""Assertions for the collapse boot-test (M4 Task 4, rewritten by Task C1,
extended by Task C2).

  check_collapse.py SNAP PROBE [FRAMECNT_ADDR]

scripts/collapse_probe.lua drives the normal cart through the deterministic
centred full game (the stick centred always so the ship rests on the start
cell, A every 11 cart frames — fire keeps kills below 6 and, under the
Vectrex 1.1.0 rule, the 6th dome hit that breaks a cell opens every ring,
so three clean dome deaths follow) and records, per MAME frame, the BIOS
joypad read-backs; on cart frames around the first dome death it records the
dome's SCB3 words, its box chain's SCB4 words and every column's SCB1 rows,
a fresh dump (cart frame 60), a rebuilt dump (cart frame 8513), a palette
dump for both, the decoded fix rows near GAME OVER, the fireball's 12 slots
(SCB2/SCB3/SCB4 and SCB1 rows 0..31) every frame from the ruin switch
through g 60, four snapshots (the ruin and the fire at g 2, 12 and 30) with
every slot's SCB3/SCB4, and every dome- and fire-slot write's raster line.
This checker:

  1. replays tests/rules_model.py from the recorded inputs (exactly as
     tests/check_hud.py does) to state, from the rules, the model's cart
     frame of the first dome death, the rebuild, and GAME OVER — the "frame
     budget derived from the rules" the task asks to state in the test;
  2. proves the columns move during the shake: some mid-collapse SCB3
     sample has columns at different Y/heights than the fixed chain (the
     collapse splits the chain), and the earliest split sample is no later
     than the model's death frame + COLLAPSE_SHAKE;
  3. proves the ruin stands from the collapse's burst (f >= COLLAPSE_SHAKE)
     to the rebuild: on every sampled frame in [death + COLLAPSE_SHAKE,
     rebuild) the dome's 8 SCB3 words are the ruin's chain (the driver one
     row shorter, RUIN_TOP px down the box; Task V2) and its SCB4 words are
     the box's, and every column's SCB1 rows equal COLLAPSE_TILE_BASE +
     ruin_tile in PAL_RUIN;
  4. proves the rebuilt dome's VRAM matches a fresh dome's (the SCB2/3/4
     words and the palette; the SCB1 tile lists legitimately differ because
     the dome turns behind the ship and the dumps are at different views);
  5. proves the ruin's pixels: among the snapshots in the ruin window, the
     one with the most uncovered ruin pixels (the g 2 fire snapshot, since
     the fireball covers the box by g 10) is compared: every pixel of the
     dome box where the ruin picture is opaque and no higher slot's box
     covers it equals ruin_pal through MAME's 15-bit colour, and states how
     many pixels were compared (under 2000 fails);
  6. proves the ruin's switch writes land before the dome box's first
     visible line: the probe's LSPC tap records every dome-slot write's
     vpos, and the latest on the switch frame must be < DOME_Y + 16;
  7. checks GAME OVER appears on the fix layer by the model's game-over
     frame + a small slack (probe-decoded rows vs the model replay);
  8. Task C2, words: on every sampled frame from the burst to g 44 + 1, the
     12 fire slots' SCB2/SCB3/SCB4 equal the tables at the previous frame's
     g (hidden columns SCB3 0) and their SCB1 rows 0..9 equal fire_tile of
     that g's picture in PAL_FIRE, rows 10..31 the blank tile; after g 45
     every fire slot is SCB3 0;
  9. Task C2, pixels: the g 2, 12 and 30 snapshots show every pixel where
     the generator's exact blit of that g's fireball is opaque and no
     higher slot covers it, against fire_pal through neo_rgb (fewer than
     500 at g 2, 3000 at g 12/30 fails);
 10. Task C2, no tearing: no write to a fire slot lands while the raster
     is inside that slot's old or new visible span, over the whole collapse
     (the probe's K records and T spans);
 11. Task C3, words: on every frame from the ruin switch to g FRAG_T + 1,
     each of the 49 fragment slots' SCB2/SCB3/SCB4 and SCB1 rows 0..1 equal
     frag_* at the previous frame's g (hidden = SCB3 0), including the flip
     rule (a V flip reverses a 2-tile fragment's rows); the first-frame
     blanking's rows 2..31 are COLLAPSE_TILE_BASE;
 12. Task C3, pixels: the g 2, 12, 30 and 40 snapshots show every pixel
     where the generator's exact fragment blit (slot order) is opaque and
     no higher slot covers it (the fireball by its exact blit) against
     PAL_DOME's words from the probe's fresh palette dump through neo_rgb;
     at least one V-flipped 2-tile fragment is among the compared pixels
     (fewer than 300 in any snapshot fails);
 13. Task C3, no tearing: no write to a fragment slot lands inside that
     slot's old or new visible span, over the whole collapse (the probe's
     Y records and N spans);
 14. Task C4, puffs: on every sampled frame of the shake, the 6 puff slots'
     SCB2/SCB3/SCB4 and (shown) SCB1 rows 0..1 equal the model at the
     previous frame's f (picture i = (f - puff_f0[n]) / PUFF_STEP, pair
     n % 3, full size, PAL_FIRE), and every slot is hidden from the burst
     on (displayed f >= COLLAPSE_SHAKE);
 15. Task C4, smoke: on every sampled frame from the burst to the rebuild,
     the 9 smoke slots' SCB2/SCB3/SCB4 and SCB1 rows 0..6 equal the
     header's tables at the previous frame's g (a plume that has not
     started is hidden), and the one-time blank rows 7..31 are the part's
     blank tile (the puffs' rows 2..31 too);
 16. Task C4, pixels: the f 35 snapshot's puff pixels and the g 40
     snapshot's smoke pixels, by the generator's exact blit (fewer than
     200 puff or 1000 smoke pixels fails);
 17. Task C4, no tearing: no write to a puff or smoke slot lands inside
     the slot's old or new visible span, over the whole collapse, and the
     worst collapse commit is stated in words and lines;
 18. Task C5, the sprite census: on every frame of the three collapses
     (3 x 118 frames) the worst scanline is <= 96; the worst frame's raw
     SCB3 dump recounts its count and lists the slots on that line by
     range; with the sticky bit ignored the worst is at least 19 lower;
     and the measured worst is stated against COLLAPSE_WORST_LINE.

Task 1 seeds the missiles from the title's time, so the timelines depend on
the Start frame and are stated by this replay, not fixed here: with the
default Start at MAME 600 (seed 0xaede) the first dome death is at cart
frame 8359, the rebuild at 8359 + 118 = 8477, GAME OVER at 27142 (Vectrex
1.1.0 rules; 8202/8320/24963 before Task 1).  The probe samples cart
frames 8290..8513, so they bracket the whole first collapse.
"""
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import layout  # noqa: E402
from PIL import Image  # noqa: E402
import neo_palette as npal  # noqa: E402  (MAME's 15-bit -> RGB pipeline)
import render_collapse as rc  # noqa: E402  (the ruin and fire pictures)
import hud_model as hm  # noqa: E402  (Task G1's GAME OVER rows)
import check_flow as cf  # noqa: E402  (the thick title font's row decoder)

HUD_GAMEOVER_ROW = hm.HUD_GAMEOVER_ROW
HUD_GAMEOVER_CAP_ROW = hm.HUD_GAMEOVER_CAP_ROW

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BUILD = os.path.join(ROOT, "build")

# the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.json
_SLOTS = json.load(open(os.path.join(BUILD, "slots.json")))
DOME_SPRITE = _SLOTS["DOME_SPRITE"]
DOME_COLS = _SLOTS["DOME_COUNT"]
DOME_ROWS = layout.d.DOME_ROWS    # the box height (geometry.py's knob)
DOME_X, DOME_Y = layout.d.DOME_X, layout.d.DOME_Y   # src/dome.h
PAL_RUIN = 55                     # src/dome.h
PAL_FIRE = 56                     # src/collapse.h
PAL_DOME = 1                      # src/dome.h: the fragments' bank
COLLAPSE_SHAKE_NEO = 41           # 35 x 59/50 (rules.h)
COLLAPSE_GONE_NEO = 100           # 85 x 59/50
DEAD_FRAMES_NEO = 118             # src/rules.h DEAD_FRAMES
SCAN_LIMIT = 96                   # the LSPC's sprites per scanline
GAME_OVER_SLACK = 40              # the sampled fix rows bracket the model's
                                  # GAME OVER frame by more than this
RUIN_LAG = 0                      # 0: the ruin's writes are made in
                                  # game_frame (the switch lands before the
                                  # box); 1 if a vblank commit is needed
FIRE_SPRITE = _SLOTS["COLLAPSE_FIRE_SPRITE"]
FIRE_COUNT = _SLOTS["COLLAPSE_FIRE_COUNT"]
FIRE_SCB1_ROWS = 32               # the hardware can sample rows 0..31
FRAG_SPRITE = _SLOTS["COLLAPSE_FRAG_SPRITE"]
FRAG_COUNT = _SLOTS["COLLAPSE_FRAG_COUNT"]
FRAG_SCB1_ROWS = 32               # the hardware can sample rows 0..31
# Task C4: the puffs (six slots, three pairs) and the smoke (nine slots,
# three plumes of three independent columns).
PUFF_SPRITE = _SLOTS["COLLAPSE_PUFF_SPRITE"]
PUFF_COUNT = _SLOTS["COLLAPSE_PUFF_COUNT"]
SMOKE_SPRITE = _SLOTS["COLLAPSE_SMOKE_SPRITE"]
SMOKE_COUNT = _SLOTS["COLLAPSE_SMOKE_COUNT"]
PUFF_SCB1_ROWS = 32               # the hardware can sample rows 0..31
SMOKE_SCB1_ROWS = 32
PAL_SMOKE = 57                    # src/collapse.h
VPOS_OFFSET = 16                  # vpos = screen line + 16 (flow.c)

import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import rules_model as rm  # noqa: E402
import ship_model as sm  # noqa: E402


# ---------------------------------------------------------------- headers
def _defines(path):
    """evaluate the header's #defines in order: a plain number, or an
    expression over the names defined before it."""
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
    """(views, cols, rows, top, ruin_tile, ruin_pal, collapse_tile_base) from
    the generated headers. The collapse part is LAST, after the band, so its
    base is radar head + ground + mountains + console + props + band. Task
    V2: `top` is RUIN_TOP, the ruin's first pixel row below the dome box's
    top (the box's empty top tile row is dropped from the picture)."""
    d = _defines(os.path.join(BUILD, "collapse_map.h"))
    txt = open(os.path.join(BUILD, "collapse_map.h")).read()
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
    assert len(pal) == 16, len(pal)
    radar = _defines(os.path.join(BUILD, "radar_map.h"))
    ground = _defines(os.path.join(BUILD, "ground_map.h"))
    mtn = _defines(os.path.join(BUILD, "mountain_map.h"))
    con = _defines(os.path.join(BUILD, "console_map.h"))
    props = _defines(os.path.join(BUILD, "props_map.h"))
    band = _defines(os.path.join(BUILD, "band_map.h"))
    base = (radar["RADAR_HEAD_TILE_BASE"] + radar["RADAR_HEAD_TILES"]
            + ground["GROUND_TILES"] + mtn["MTN_TILES"]
            + con["CON_TILES"] + props["PROP_TILES"] + band["BAND_TILES"])
    return views, cols, rows, top, tiles, pal, base


def _header_fire():
    """the fireball's tables from build/collapse_map.h: fire_pic,
    fire_scb2 (hz << 8 | v), fire_h (SCB3 height), fire_x/fire_y (top-left),
    fire_mask (bit c = column c shown), fire_tile[pic][col][row] and
    fire_pal[16]."""
    d = _defines(os.path.join(BUILD, "collapse_map.h"))
    txt = open(os.path.join(BUILD, "collapse_map.h")).read()

    def u(name, n):
        m = re.search(r"static const u\d+ %s\[%d\] = \{(.*?)\};" % (name, n),
                      txt, re.S)
        assert m, f"{name} missing from build/collapse_map.h"
        vals = [int(x) for x in re.findall(r"\d+", m.group(1))]
        assert len(vals) == n, (name, len(vals), n)
        return vals

    def s(name, n):
        m = re.search(r"static const s16 %s\[%d\] = \{(.*?)\};" % (name, n),
                      txt, re.S)
        assert m, f"{name} missing from build/collapse_map.h"
        vals = [int(x) for x in re.findall(r"-?\d+", m.group(1))]
        assert len(vals) == n, (name, len(vals), n)
        return vals

    n = d["FIRE_T"]
    m = re.search(r"static const u16 fire_tile\[(\d+)\]\[(\d+)\]\[(\d+)\]"
                  r" = \{(.*?)\};", txt, re.S)
    assert m, "fire_tile missing from build/collapse_map.h"
    nf, cols, rows = int(m.group(1)), int(m.group(2)), int(m.group(3))
    vals = [int(x) for x in re.findall(r"\d+", m.group(4))]
    assert len(vals) == nf * cols * rows, (len(vals), nf * cols * rows)
    tile = [[[vals[(p * cols + c) * rows + r] for r in range(rows)]
             for c in range(cols)] for p in range(nf)]
    m = re.search(r"static const u16 fire_pal\[16\] = \{(.*?)\};", txt, re.S)
    assert m, "fire_pal missing from build/collapse_map.h"
    pal = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    assert len(pal) == 16, len(pal)
    return dict(t=n, cols=cols, rows=rows, pic=u("fire_pic", n),
                scb2=u("fire_scb2", n), h=u("fire_h", n),
                x=s("fire_x", n), y=s("fire_y", n),
                mask=u("fire_mask", n), tile=tile, pal=pal)


FIRE = _header_fire()
FIRE_T = FIRE["t"]
FIRE_COLS_H = FIRE["cols"]
FIRE_ROWS_H = FIRE["rows"]
assert FIRE_COLS_H == FIRE_COUNT



def _header_frag():
    """Task C3's fragment tables from build/collapse_map.h: frag_tile[n][r]
    (relative to the part; 0 = blank), frag_rows[n], frag_x/frag_y[n][g]
    (COLLAPSE_HIDE = not drawn) and frag_flip[n][g] (bit 0 H, bit 1 V)."""
    d = _defines(os.path.join(BUILD, "collapse_map.h"))
    txt = open(os.path.join(BUILD, "collapse_map.h")).read()

    def u(name, dims):
        pat = r"static const u\d+ %s\[%s\] = \{(.*?)\};" % (
            name, r"\]\[".join(str(x) for x in dims))
        m = re.search(pat, txt, re.S)
        assert m, f"{name} missing from build/collapse_map.h"
        vals = [int(x) for x in re.findall(r"\d+", m.group(1))]
        want = 1
        for x in dims:
            want *= x
        assert len(vals) == want, (name, len(vals), want)
        if len(dims) == 1:
            return vals
        out, stride = [], dims[-1]
        for i in range(dims[0]):
            out.append(vals[i * stride:(i + 1) * stride])
        return out

    def s(name, dims):
        pat = r"static const s16 %s\[%s\] = \{(.*?)\};" % (
            name, r"\]\[".join(str(x) for x in dims))
        m = re.search(pat, txt, re.S)
        assert m, f"{name} missing from build/collapse_map.h"
        vals = [int(x) for x in re.findall(r"-?\d+", m.group(1))]
        want = dims[0] * dims[1]
        assert len(vals) == want, (name, len(vals), want)
        return [vals[i * dims[1]:(i + 1) * dims[1]] for i in range(dims[0])]

    n, t, maxr = d["NFRAGS"], d["FRAG_T"], d["FRAG_MAX_ROWS"]
    return dict(n=n, t=t, maxr=maxr,
                tile=u("frag_tile", (n, maxr)),
                rows=u("frag_rows", (n,)),
                x=s("frag_x", (n, t)),
                y=s("frag_y", (n, t)),
                flip=u("frag_flip", (n, t)),
                hide=d["COLLAPSE_HIDE"])


FRAGS = _header_frag()
FRAG_T = FRAGS["t"]
FRAG_MAX_ROWS = FRAGS["maxr"]
assert FRAGS["n"] == FRAG_COUNT


def _reshape(shape, vals):
    """a flat C array -> nested lists of the declared shape."""
    if len(shape) == 1:
        return vals
    stride = 1
    for x in shape[1:]:
        stride *= x
    return [_reshape(shape[1:], vals[i * stride:(i + 1) * stride])
            for i in range(shape[0])]


def _header_smoke_puff():
    """Task C4's puffs and smoke from build/collapse_map.h: puff_tile,
    puff_f0/puff_x/puff_y; smoke_tile, smoke_pic/x/y/v/h and smoke_pal; and
    the SMOKE_LOOP/SMOKE_PERIOD/SMOKE_T wrap constants."""
    path = os.path.join(BUILD, "collapse_map.h")
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

    nf = d["PUFF_FRAMES"]
    npuff = d["NPUFFS"]
    ns = d["NPLUMES"]
    nsm = d["SMOKE_FRAMES"]
    return dict(
        puff_frames=nf, puff_step=d["PUFF_STEP"], npuffs=npuff,
        puff_cols=d["PUFF_COLS"], puff_rows=d["PUFF_ROWS"],
        puff_tile=arr("puff_tile", "u16", (nf, d["PUFF_COLS"], d["PUFF_ROWS"])),
        puff_f0=arr("puff_f0", "u8", (npuff,)),
        puff_x=arr("puff_x", "s16", (npuff,)),
        puff_y=arr("puff_y", "s16", (npuff,)),
        smoke_cols=d["SMOKE_COLS"], smoke_rows=d["SMOKE_ROWS"],
        smoke_frames=nsm, nplumes=ns,
        smoke_loop=d["SMOKE_LOOP"], smoke_period=d["SMOKE_PERIOD"],
        smoke_t=d["SMOKE_T"],
        smoke_tile=arr("smoke_tile", "u16",
                       (ns, nsm, d["SMOKE_COLS"], d["SMOKE_ROWS"])),
        smoke_pic=arr("smoke_pic", "u8", (ns, d["SMOKE_T"])),
        smoke_dx=arr("smoke_dx", "s8", (ns, d["SMOKE_T"])),
        smoke_lines=arr("smoke_lines", "u8", (ns, d["SMOKE_T"])),
        smoke_v=arr("smoke_v", "u8", (ns, d["SMOKE_T"])),
        smoke_h=arr("smoke_h", "u8", (ns, d["SMOKE_T"])),
        smoke_foot_x=arr("smoke_foot_x", "s16", (d["SMOKE_T"], ns)),
        smoke_foot_y=arr("smoke_foot_y", "s16", (d["SMOKE_T"], ns)),
        smoke_front=arr("smoke_front", "u8", (d["SMOKE_T"],)),
        smoke_pal=[int(x, 16) for x in re.findall(
            r"0x[0-9a-fA-F]{4}", re.search(
                r"static const u16 smoke_pal\[16\] = \{(.*?)\};", txt, re.S).group(1))],
    )


SMOKE = _header_smoke_puff()
NPUFFS = SMOKE["npuffs"]
PUFF_FRAMES = SMOKE["puff_frames"]
PUFF_STEP = SMOKE["puff_step"]
PUFF_COLS = SMOKE["puff_cols"]
PUFF_ROWS = SMOKE["puff_rows"]
NPLUMES = SMOKE["nplumes"]
SMOKE_COLS = SMOKE["smoke_cols"]
SMOKE_ROWS = SMOKE["smoke_rows"]
SMOKE_T = SMOKE["smoke_t"]
SMOKE_LOOP = SMOKE["smoke_loop"]
SMOKE_PERIOD = SMOKE["smoke_period"]
# the six slots are three pairs (puff n always takes pair n % 3), not one
# pair per puff.
assert 3 * PUFF_COLS == PUFF_COUNT
assert len(SMOKE["smoke_pal"]) == 16

# Task V1: the plumes' twelve columns are split over two slot ranges: the
# BACK six right below DOME_SPRITE and the FRONT six in the overlay range.
SMOKE_BACK_SPRITE = _SLOTS["SMOKE_BACK_SPRITE"]
SMOKE_BACK_COUNT = _SLOTS["SMOKE_BACK_COUNT"]
SMOKE_TOTAL = SMOKE_BACK_COUNT + SMOKE_COUNT
SMOKE_SLOTS = (list(range(SMOKE_BACK_SPRITE,
                          SMOKE_BACK_SPRITE + SMOKE_BACK_COUNT))
               + list(range(SMOKE_SPRITE, SMOKE_SPRITE + SMOKE_COUNT)))
assert NPLUMES * SMOKE_COLS == SMOKE_TOTAL
assert SMOKE_BACK_SPRITE + SMOKE_BACK_COUNT == DOME_SPRITE


RUIN_VIEWS, RUIN_COLS, RUIN_ROWS, RUIN_TOP, RUIN_TILES, RUIN_PAL, \
    COLLAPSE_TILE_BASE = _header_ruin()
assert RUIN_VIEWS == 48, RUIN_VIEWS
assert RUIN_COLS == DOME_COLS, (RUIN_COLS, DOME_COLS)
assert RUIN_TOP == 16 and RUIN_ROWS == DOME_ROWS - RUIN_TOP // 16, (
    RUIN_TOP, RUIN_ROWS, DOME_ROWS)

WHOLE_SCB3 = tuple([((496 - DOME_Y) << 7) | DOME_ROWS]
                   + [0x40] * (DOME_COLS - 1))
# Task V2: the ruin's chain driver starts RUIN_TOP px down the box and is
# one tile row shorter; its followers stay sticky.
RUIN_SCB3 = tuple([((496 - (DOME_Y + RUIN_TOP)) << 7) | RUIN_ROWS]
                  + [0x40] * (DOME_COLS - 1))
BOX_SCB4 = tuple((DOME_X + c * 16) << 7 for c in range(DOME_COLS))
RUIN_WORDS = [[[(COLLAPSE_TILE_BASE + RUIN_TILES[v][c][r], PAL_RUIN << 8)
                for r in range(RUIN_ROWS)] for c in range(RUIN_COLS)]
              for v in range(RUIN_VIEWS)]


def frame_model(state, inp, pressed):
    """one frame exactly as tests/hud_model.py's frame_model (the C's
    rules_begin / ship_frame / mis_update / rules_end)."""
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


def parse(fname):
    """(records, samples, ruin, gone, fresh, rebuilt, snaps, rows, seeds,
    slots, writes, ruin_fc, fire, fire_writes, spans, frag, frag_blank,
    frag_writes, frag_spans) from the dump.

    records: [(rec, fc, cur, chg)]; samples: {fc: [scb3 words]};
    ruin: {fc: (scb4 words, [[(tile, attr)] per column])}; gone: {fc: 0/1};
    fresh: {'slots': [slot lines], 'pal': [15 words]}; rebuilt: (fc, {...});
    snaps: [fc] in probe order; rows: {fc: [10 fix rows]};
    seeds: {mame: cart seed}; slots: {fc: {slot: (scb3, scb4)}};
    writes: {fc: [(slot, reg, vpos)]} (the dome slots, Task C1);
    ruin_fc: the fc the dome slot 0 attribute turned PAL_RUIN << 8;
    fire: {fc: {col: (scb2, scb3, scb4, [(tile, attr)] x 32)}};
    fire_writes: {fc: [(slot, reg, vpos)]} (the fire slots, Task C2; the
    probe's KW records);
    spans: {fc: {slot: (scb3, scb4, scb2)}} for the fire slots;
    frag: {fc: {n: (scb2, scb3, scb4, [(tile, attr)] x FRAG_MAX_ROWS)}};
    frag_blank: {n: [(tile, attr)] x (32 - FRAG_MAX_ROWS)};
    frag_writes: {fc: [(slot, reg, vpos)]} (the fragment slots, Task C3);
    frag_spans: {fc: {slot: (scb3, scb4, scb2)}} for the fragment slots;
    puff: {fc: {slot: (scb2, scb3, scb4, [(tile, attr)] x PUFF_ROWS)}};
    puff_blank: {slot: [(tile, attr)] x (32 - PUFF_ROWS)};
    puff_writes: {fc: [(slot, reg, vpos)]};
    puff_spans: {fc: {slot: (scb3, scb4, scb2)}};
    smoke: {fc: {slot: (scb2, scb3, scb4, [(tile, attr)] x SMOKE_ROWS)}};
    smoke_blank: {slot: [(tile, attr)] x (32 - SMOKE_ROWS)};
    smoke_writes: {fc: [(slot, reg, vpos)]};
    smoke_spans: {fc: {slot: (scb3, scb4, scb2)}};
    census: {fc: (g, worst count, worst line)} (Task C5's K records);
    worst: (fc, count, line, {slot: scb3}) (Task C5's W/w raw dump)."""
    records, samples, ruin, gone, fresh, rebuilt = [], {}, {}, {}, None, None
    snaps, rows, seeds, slots, writes = [], {}, {}, {}, {}
    ruin_fc, fire, fire_writes, spans = None, {}, {}, {}
    frag, frag_blank, frag_writes, frag_spans = {}, {}, {}, {}
    puff, puff_blank, puff_writes, puff_spans = {}, {}, {}, {}
    smoke, smoke_blank, smoke_writes, smoke_spans = {}, {}, {}, {}
    census, worst = {}, None
    cur_f, cur_rows = None, None
    with open(fname, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] == "I":
                rec, fc, cur, chg = (int(x) for x in p[1:5])
                records.append((rec, fc, cur, chg))
            elif p[0] == "S":
                samples[int(p[1])] = p[2:]
            elif p[0] == "U":
                fc = int(p[1])
                rest = p[2:]
                scb4, scb1, i = [], [], 0
                for _c in range(DOME_COLS):
                    scb4.append(rest[i])
                    i += 1
                    rows_c = []
                    for _r in range(RUIN_ROWS):
                        rows_c.append((rest[i], rest[i + 1]))
                        i += 2
                    scb1.append(rows_c)
                ruin[fc] = (scb4, scb1)
            elif p[0] == "G":
                gone[int(p[1])] = int(p[2])
            elif p[0] == "H":
                fresh = {"slots": [], "pal": []}
            elif p[0] == "h":
                if fresh is not None:
                    fresh["slots"].append(line.rstrip("\n"))
            elif p[0] == "P":
                if fresh is not None:
                    fresh["pal"] = [int(x, 16) for x in p[1:]]
            elif p[0] == "REBUILD":
                rebuilt = (int(p[1]), {"slots": [], "pal": []})
            elif p[0] == "R":
                if rebuilt is not None:
                    rebuilt[1]["slots"].append(line.rstrip("\n"))
            elif p[0] == "Q":
                if rebuilt is not None:
                    rebuilt[1]["pal"] = [int(x, 16) for x in p[1:]]
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
            elif p[0] == "SEED":
                seeds[int(p[1])] = int(p[2])
            elif p[0] == "SNAP":
                snaps.append(int(p[1]))
            elif p[0] == "X":
                slots.setdefault(int(p[1]), {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16))
            elif p[0] == "L":
                writes.setdefault(int(p[1]), []).append(
                    (int(p[2]), int(p[3]), int(p[4])))
            elif p[0] == "RUIN":
                ruin_fc = int(p[1])
            elif p[0] == "V":
                fc, col = int(p[1]), int(p[2])
                scb2, scb3, scb4 = (int(x, 16) for x in p[3:6])
                rest = p[6:]
                assert len(rest) == 2 * FIRE_SCB1_ROWS, len(rest)
                rows_c = [(int(rest[i * 2], 16), int(rest[i * 2 + 1], 16))
                          for i in range(FIRE_SCB1_ROWS)]
                fire.setdefault(fc, {})[col] = (scb2, scb3, scb4, rows_c)
            elif p[0] == "K":
                census[int(p[1])] = (int(p[2]), int(p[3]), int(p[4]))
            elif p[0] == "KW":
                fire_writes.setdefault(int(p[1]), []).append(
                    (int(p[2]), int(p[3]), int(p[4])))
            elif p[0] == "T":
                spans.setdefault(int(p[1]), {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16), int(p[5], 16))
            elif p[0] == "Z":
                fc, n = int(p[1]), int(p[2])
                scb2, scb3, scb4 = (int(x, 16) for x in p[3:6])
                rest = p[6:]
                assert len(rest) == 2 * FRAG_MAX_ROWS, len(rest)
                rows_c = [(int(rest[i * 2], 16), int(rest[i * 2 + 1], 16))
                          for i in range(FRAG_MAX_ROWS)]
                frag.setdefault(fc, {})[n] = (scb2, scb3, scb4, rows_c)
            elif p[0] == "B":
                n = int(p[2])
                rest = p[3:]
                assert len(rest) == 2 * (FRAG_SCB1_ROWS - FRAG_MAX_ROWS), len(rest)
                frag_blank[n] = [(int(rest[i * 2], 16), int(rest[i * 2 + 1], 16))
                                 for i in range(FRAG_SCB1_ROWS - FRAG_MAX_ROWS)]
            elif p[0] == "N":
                frag_spans.setdefault(int(p[1]), {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16), int(p[5], 16))
            elif p[0] == "Y":
                frag_writes.setdefault(int(p[1]), []).append(
                    (int(p[2]), int(p[3]), int(p[4])))
            elif p[0] == "PU":
                fc, slot = int(p[1]), int(p[2])
                scb2, scb3, scb4 = (int(x, 16) for x in p[3:6])
                rest = p[6:]
                assert len(rest) == 2 * PUFF_ROWS, len(rest)
                rows_c = [(int(rest[i * 2], 16), int(rest[i * 2 + 1], 16))
                          for i in range(PUFF_ROWS)]
                puff.setdefault(fc, {})[slot] = (scb2, scb3, scb4, rows_c)
            elif p[0] == "PB":
                slot = int(p[2])
                rest = p[3:]
                assert len(rest) == 2 * (PUFF_SCB1_ROWS - PUFF_ROWS), len(rest)
                puff_blank[slot] = [(int(rest[i * 2], 16),
                                     int(rest[i * 2 + 1], 16))
                                    for i in range(PUFF_SCB1_ROWS - PUFF_ROWS)]
            elif p[0] == "PWR":
                puff_writes.setdefault(int(p[1]), []).append(
                    (int(p[2]), int(p[3]), int(p[5]), int(p[4])))
            elif p[0] == "PS":
                puff_spans.setdefault(int(p[1]), {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16), int(p[5], 16))
            elif p[0] == "SM":
                fc, slot = int(p[1]), int(p[2])
                scb2, scb3, scb4 = (int(x, 16) for x in p[3:6])
                rest = p[6:]
                assert len(rest) == 2 * SMOKE_ROWS, len(rest)
                rows_c = [(int(rest[i * 2], 16), int(rest[i * 2 + 1], 16))
                          for i in range(SMOKE_ROWS)]
                smoke.setdefault(fc, {})[slot] = (scb2, scb3, scb4, rows_c)
            elif p[0] == "SB":
                slot = int(p[2])
                rest = p[3:]
                assert len(rest) == 2 * (SMOKE_SCB1_ROWS - SMOKE_ROWS), len(rest)
                smoke_blank[slot] = [(int(rest[i * 2], 16),
                                      int(rest[i * 2 + 1], 16))
                                     for i in range(SMOKE_SCB1_ROWS - SMOKE_ROWS)]
            elif p[0] == "SWR":
                smoke_writes.setdefault(int(p[1]), []).append(
                    (int(p[2]), int(p[3]), int(p[5]), int(p[4])))
            elif p[0] == "SS":
                smoke_spans.setdefault(int(p[1]), {})[int(p[2])] = (
                    int(p[3], 16), int(p[4], 16), int(p[5], 16))
            if cur_f is not None and cur_rows is not None and all(r is not None for r in cur_rows):
                rows[cur_f] = cur_rows
                cur_f, cur_rows = None, None
    return (records, samples, ruin, gone, fresh, rebuilt, snaps, rows, seeds,
            slots, writes, ruin_fc, fire, fire_writes, spans, frag, frag_blank,
            frag_writes, frag_spans, puff, puff_blank, puff_writes, puff_spans,
            smoke, smoke_blank, smoke_writes, smoke_spans, census, worst)


def _at(im, x, y):
    """a snapshot pixel for a 320x224 screen coordinate (scaled PNGs)."""
    w, h = im.size
    return tuple(im.getpixel((int(x * w / 320), int(y * h / 224)))[:3])


def sprite_boxes(scb3):
    """slot -> its on-screen (x, y, w, h) box for every drawn slot,
    resolving the sticky chains exactly as the hardware does: a sticky slot
    inherits the PREVIOUS slot's Y and height and sits 16 px right of it; a
    non-sticky slot uses its own SCB3 Y/height."""
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


def ruin_pixels(im, slot_dump, view):
    """(compared, mismatches, first) for the ruin's opaque box pixels at
    `view` that no slot above the dome covers, against ruin_pal through
    neo_rgb. Task V2: only the picture's drawn rows (RUIN_TOP .. the box's
    bottom) are compared; the dropped top row is not drawn."""
    boxes = sprite_boxes(slot_dump)
    high = {s: b for s, b in boxes.items() if s >= DOME_SPRITE + DOME_COLS}
    pic = _FRAG_OUT["ruins"][view]
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
            compared += 1
            got = _at(im, xx, yy)
            want = rgb[idx]
            if got != tuple(want):
                mismatches += 1
                if first is None:
                    first = (xx, yy, got, tuple(want))
    return compared, mismatches, first


# Task C2: the fireball's pictures are the generator's own frames (the
# exact pictures the header's fire_tile tiles were cut from). Precompute
# them once; fire_picture is deterministic (fixed seeds).
_FIRE_PICS = [rc.fire_picture(t)
              for t in np.linspace(0, 1, rc.FIRE_FRAMES)]


def fire_blit(g):
    """the generator's exact screen for fireball frame g: its picture (with
    the hidden columns zeroed, as render_collapse's preview does) drawn with
    the hardware's own zoom tables, at the header's top-left and shrink."""
    scb2 = FIRE["scb2"][g]
    hz, v = scb2 >> 8, scb2 & 0xff
    pic = _FIRE_PICS[FIRE["pic"][g]].copy()
    for c in range(FIRE_COUNT):
        if not (FIRE["mask"][g] >> c) & 1:
            pic[:, c * 16:(c + 1) * 16] = 0
    frame = np.zeros((224, 320), int)
    rc.blit(frame, pic, np.arange(16), FIRE["x"][g], FIRE["y"][g],
            hz=hz, v=v, height=FIRE["h"][g])
    return frame


def fire_pixels(im, slot_dump, g):
    """(compared, mismatches, first) for the fireball's opaque pixels at
    frame g that no higher slot covers, against fire_pal through neo_rgb.
    A pixel belongs to fire column c = (x - left) / (hz + 1); a slot above
    that column's slot (a puff, a front prop, the ship, the console, a
    missile, an explosion, the radar) hides it."""
    frame = fire_blit(g)
    boxes = sprite_boxes(slot_dump)
    rgb = [npal.neo_rgb(w) for w in FIRE["pal"]]
    stride = (FIRE["scb2"][g] >> 8) + 1
    compared = mismatches = 0
    first = None
    for yy in range(224):
        for xx in range(320):
            idx = int(frame[yy, xx])
            if idx == 0:
                continue
            c = (xx - FIRE["x"][g]) // stride
            if not (0 <= c < FIRE_COUNT):
                continue
            slot = FIRE_SPRITE + c
            if any(s > slot and _covers(b, xx, yy)
                   for s, b in boxes.items()):
                continue
            compared += 1
            got = _at(im, xx, yy)
            want = tuple(rgb[idx])
            if got != want:
                mismatches += 1
                if first is None:
                    first = (xx, yy, c, got, want)
    return compared, mismatches, first


# Task C3: the fragments are the generator's own pieces and their tracks
# (the header's frag_tile/frag_rows/frag_x/frag_y/frag_flip are cut from
# these). Build them once; render_collapse.build() is deterministic and
# takes well under a second.
_FRAG_OUT = rc.build()


def fragment_frame(g):
    """(owner, idx) for the generator's exact blit of frame g's fragments:
    each fragment drawn in slot order (n 0..45, a later one on top), with
    the whole-piece H/V flip, at its top-left, full size. owner is the
    fragment index that owns the pixel (-1 where nothing is drawn); idx is
    its dome-palette index."""
    owner = np.full((224, 320), -1, int)
    idx = np.zeros((224, 320), int)
    for n, (pic, tr) in enumerate(_FRAG_OUT["frags"]):
        st = tr[g] if 0 <= g < rc.FRAG_T else None
        if st is None:
            continue
        x, y, flip = st
        f = np.zeros((224, 320), int)
        rc.blit(f, pic, np.arange(16), x, y,
                hflip=flip & 1, vflip=flip & 2)
        m = f != 0
        owner[m] = n
        idx[m] = f[m]
    return owner, idx


def frag_pixels(im, slot_dump, g, dome_pal):
    """(compared, mismatches, first, vflip2, bad_by_frag) for the
    fragments' opaque pixels at frame g that no higher slot covers, against
    PAL_DOME's words (the probe's fresh palette dump) through neo_rgb. The
    fragments are drawn in slot order; the fireball (all its slots are
    higher) is drawn over them exactly (its blit, not its box), and the
    other higher slots (puffs, front props, the ship, the console, the
    front missiles, the explosions, the radar) cover by their boxes as the
    other checkers do."""
    owner, idx = fragment_frame(g)
    fire = fire_blit(g) if g < FIRE_T else np.zeros((224, 320), int)
    boxes = sprite_boxes(slot_dump)
    rgb = [None] + [npal.neo_rgb(w) for w in dome_pal]
    compared = mismatches = 0
    first = None
    vflip2 = set()
    bad_by_frag = {}
    for yy in range(224):
        for xx in range(320):
            n = int(owner[yy, xx])
            if n < 0:
                continue
            slot = FRAG_SPRITE + n
            if fire[yy, xx] != 0:
                continue                # the fireball is drawn over it
            if any(s > slot
                   and not (FIRE_SPRITE <= s < FIRE_SPRITE + FIRE_COUNT)
                   and _covers(b, xx, yy)
                   for s, b in boxes.items()):
                continue
            if FRAGS["rows"][n] == 2 and (FRAGS["flip"][n][g] & 2):
                vflip2.add(n)
            compared += 1
            got = _at(im, xx, yy)
            want = tuple(rgb[int(idx[yy, xx])])
            if got != want:
                mismatches += 1
                bad_by_frag[n] = bad_by_frag.get(n, 0) + 1
                if first is None:
                    first = (xx, yy, n, got, want)
    return compared, mismatches, first, vflip2, bad_by_frag


# Task C4: the puffs (f 0..40) and the smoke (g >= the plume's start),
# exactly as the runtime's model. The header's tables are cut from
# _FRAG_OUT's pictures, so the pixel proofs use the generator's own art.
def puffs_at(f):
    """{puff n: picture i} for a displayed frame f; empty at/after the
    burst (f >= COLLAPSE_SHAKE)."""
    shown = {}
    if f < 0 or f >= COLLAPSE_SHAKE_NEO:
        return shown
    for n in range(NPUFFS):
        i = (f - SMOKE["puff_f0"][n]) // PUFF_STEP
        if 0 <= i < PUFF_FRAMES:
            shown[n] = int(i)
    return shown


def puff_slot_words(f):
    """slot -> (scb2, scb3, scb4, [(tile, attr)] x PUFF_ROWS or None) for
    every one of the 6 puff slots at displayed f. A shown puff n takes the
    slot pair n % 3; every other pair is hidden (SCB3 0)."""
    want = {}
    shown = puffs_at(f)
    for n, i in shown.items():
        pair = n % 3
        x, y = SMOKE["puff_x"][n], SMOKE["puff_y"][n]
        for col in range(PUFF_COLS):
            slot = PUFF_SPRITE + pair * PUFF_COLS + col
            want[slot] = (
                0x0fff,
                ((496 - y) << 7) | PUFF_ROWS,
                ((x + col * 16) & 0x1ff) << 7,
                [(COLLAPSE_TILE_BASE + SMOKE["puff_tile"][i][col][r],
                  PAL_FIRE << 8) for r in range(PUFF_ROWS)])
    for pair in range(3):
        for col in range(PUFF_COLS):
            slot = PUFF_SPRITE + pair * PUFF_COLS + col
            if slot not in want:
                want[slot] = (0x0fff, 0, 0, None)
    return want


def smoke_at(p, g, angle):
    """(picture, left, top, v, height) for plume p at g and the scene's
    angle, or None when it has not started. From SMOKE_T on the per-g
    tables repeat every SMOKE_PERIOD from SMOKE_LOOP."""
    if g < 0:
        return None
    gg = g
    if g >= SMOKE_T:
        gg = SMOKE_LOOP + (g - SMOKE_LOOP) % SMOKE_PERIOD
    pic = SMOKE["smoke_pic"][p][gg]
    if pic == 0xff:
        return None
    left = (SMOKE["smoke_foot_x"][angle][p] + SMOKE["smoke_dx"][p][gg]
            - SMOKE_COLS * 8)
    top = SMOKE["smoke_foot_y"][angle][p] - SMOKE["smoke_lines"][p][gg]
    return (int(pic), left, top, SMOKE["smoke_v"][p][gg],
            SMOKE["smoke_h"][p][gg])


def smoke_bases(angle):
    """plume p -> the first of its two column slots at this angle: the next
    free FRONT pair when bit p of smoke_front is set, else the next free
    BACK pair."""
    front = SMOKE["smoke_front"][angle]
    fp = bp = 0
    bases = {}
    for p in range(NPLUMES):
        if front & (1 << p):
            bases[p] = SMOKE_SPRITE + fp * SMOKE_COLS
            fp += 1
        else:
            bases[p] = SMOKE_BACK_SPRITE + bp * SMOKE_COLS
            bp += 1
    return bases


def smoke_slot_words(g, angle):
    """slot -> (scb2, scb3, scb4, [(tile, attr)] x SMOKE_ROWS or None) for
    every one of the twelve plume columns at g and the scene's angle. A
    plume that has not started leaves its pair hidden (SCB3 0)."""
    want = {slot: (0x0f00, 0, 0, None) for slot in SMOKE_SLOTS}
    bases = smoke_bases(angle)
    for p in range(NPLUMES):
        s = smoke_at(p, g, angle)
        if s is None:
            continue
        pic, left, top, v, h = s
        for c in range(SMOKE_COLS):
            slot = bases[p] + c
            want[slot] = (
                0x0f00 | v,
                ((496 - top) << 7) | h,
                ((left + c * 16) & 0x1ff) << 7,
                [(COLLAPSE_TILE_BASE + SMOKE["smoke_tile"][p][pic][c][r],
                  PAL_SMOKE << 8) for r in range(SMOKE_ROWS)])
    return want


def puff_frame(f):
    """(owner, idx) for the generator's exact full-size blit of displayed
    frame f's puffs, drawn in slot order (pair 0, 1, 2; a later pair on
    top). owner is the slot that owns the pixel (-1 where nothing is)."""
    owner = np.full((224, 320), -1, int)
    idx = np.zeros((224, 320), int)
    shown = puffs_at(f)
    for pair in range(3):
        for n, i in shown.items():
            if n % 3 != pair:
                continue
            x, y = SMOKE["puff_x"][n], SMOKE["puff_y"][n]
            fr = np.zeros((224, 320), int)
            # the two slots of the pair show the picture's two columns, one
            # 16-px column each; the generator's blit draws the whole 2 x 2
            # picture at (x, y), which is exactly the pair.
            rc.blit(fr, _FRAG_OUT["puffs"][i], np.arange(16), x, y)
            ys, xs = np.nonzero(fr)
            col = (xs - x) // 16
            good = (col >= 0) & (col < PUFF_COLS)
            ys, xs, col = ys[good], xs[good], col[good]
            owner[ys, xs] = PUFF_SPRITE + pair * PUFF_COLS + col
            idx[ys, xs] = fr[ys, xs]
    return owner, idx


def puff_pixels(im, slot_dump, f):
    """(compared, mismatches, first) for the puffs' opaque pixels at
    displayed frame f that no higher slot covers, against fire_pal through
    neo_rgb (fewer than 200 fails)."""
    owner, idx = puff_frame(f)
    boxes = sprite_boxes(slot_dump)
    rgb = [npal.neo_rgb(w) for w in FIRE["pal"]]
    compared = mismatches = 0
    first = None
    for yy in range(224):
        for xx in range(320):
            slot = int(owner[yy, xx])
            if slot < 0:
                continue
            if any(s > slot and _covers(b, xx, yy)
                   for s, b in boxes.items() if s >= PUFF_SPRITE + PUFF_COUNT):
                continue
            compared += 1
            got = _at(im, xx, yy)
            want = tuple(rgb[int(idx[yy, xx])])
            if got != want:
                mismatches += 1
                if first is None:
                    first = (xx, yy, slot, got, want)
    return compared, mismatches, first


def smoke_frame(g, angle):
    """(owner, idx) for the generator's exact blit of the plumes at g and
    the scene's angle, drawn in ascending slot order (a higher slot on top).
    Each 16-px column belongs to its own slot, so the owner is the plume's
    column sprite."""
    owner = np.full((224, 320), -1, int)
    idx = np.zeros((224, 320), int)
    bases = smoke_bases(angle)
    pieces = []
    for p in range(NPLUMES):
        s = smoke_at(p, g, angle)
        if s is None:
            continue
        pc, left, top, v, h = s
        for c in range(SMOKE_COLS):
            pieces.append((bases[p] + c, p, pc, left, top, v, h, c))
    for slot, p, pc, left, top, v, h, c in sorted(pieces):
        fr = np.zeros((224, 320), int)
        rc.blit(fr, _FRAG_OUT["smoke"][p][pc], np.arange(16), left, top,
                v=v, height=h)
        m = fr != 0
        yy, xx = np.nonzero(m)
        col = (xx - left) // 16
        good = (col >= 0) & (col < SMOKE_COLS)
        yy, xx, col = yy[good], xx[good], col[good]
        owner[yy, xx] = slot
        idx[yy, xx] = fr[yy, xx]
    return owner, idx


def smoke_pixels(im, slot_dump, g, angle, frag_owner, fire):
    """(compared, mismatches, first) for the smoke's opaque pixels at g and
    the scene's angle that no higher slot covers: the fragments and the
    fireball by their exact blits, the other higher slots (the dome/ruin,
    puffs, props, ship, console, missiles, explosions, radar) by their
    boxes. Against smoke_pal through neo_rgb."""
    owner, idx = smoke_frame(g, angle)
    boxes = sprite_boxes(slot_dump)
    rgb = [npal.neo_rgb(w) for w in SMOKE["smoke_pal"]]
    compared = mismatches = 0
    first = None
    for yy in range(224):
        for xx in range(320):
            slot = int(owner[yy, xx])
            if slot < 0:
                continue
            if frag_owner[yy, xx] >= 0 or fire[yy, xx] != 0:
                continue
            if any(s > slot
                   and s not in SMOKE_SLOTS
                   and not (FRAG_SPRITE <= s < FRAG_SPRITE + FRAG_COUNT)
                   and not (FIRE_SPRITE <= s < FIRE_SPRITE + FIRE_COUNT)
                   and _covers(b, xx, yy)
                   for s, b in boxes.items()):
                continue
            compared += 1
            got = _at(im, xx, yy)
            want = tuple(rgb[int(idx[yy, xx])])
            if got != want:
                mismatches += 1
                if first is None:
                    first = (xx, yy, slot, got, want)
    return compared, mismatches, first


def span_of(words):
    """(top, bottom) screen lines of a fire or fragment slot's
    (scb3, scb4, scb2), or None when hidden. The columns are independent
    (never sticky), and vertical shrink shortens the picture's visible
    lines exactly as the hardware draws them."""
    if words is None:
        return None
    scb3, _scb4, scb2 = words
    h = scb3 & 0x3f
    if h == 0:
        return None
    top = 496 - (scb3 >> 7)
    if top >= 256:
        top -= 512
    lines = (h * 16 * ((scb2 & 0xff) + 1)) // 256
    return (top, top + lines - 1)


def _unsafe(vpos, old, new):
    """the write's vpos is inside the slot's old or new VISIBLE screen span
    (screen line 0 = vpos 16; a box past line 223 cannot tear)."""
    for span in (old, new):
        if span is None:
            continue
        top = max(16, span[0] + VPOS_OFFSET)
        bottom = min(239, span[1] + VPOS_OFFSET)
        if top <= vpos <= bottom:
            return True
    return False


# Task C5: the census's slot ranges, in draw order. The collapse's sub-map
# sits inside the broken overlays' range, so those four ranges are listed
# first and the rest of the overlay range is the (hidden) broken overlays.
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
    """slot -> (top, h), resolving the sticky chains exactly as the probe:
    a sticky slot inherits the previous slot's top and height."""
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
    """the same line's count with every sticky follower treated as height 0
    (only the chain leaders count)."""
    count = 0
    for s in range(381):
        w3 = raw.get(s, 0)
        if w3 & 0x40:
            continue                    # a follower: ignored
        h = w3 & 0x3f
        if h == 0:
            continue
        top = 496 - (w3 >> 7)
        if top <= line < top + h * 16:
            count += 1
    return count


def no_sticky_worst(raw):
    """(worst count, line) over all screen lines with followers ignored."""
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
    """COLLAPSE_WORST_LINE from the generated header."""
    return _defines(os.path.join(BUILD, "collapse_map.h"))["COLLAPSE_WORST_LINE"]


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    framecnt_addr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    (records, samples, ruin, gone, fresh, rebuilt, snaps, rows, seeds, slots,
     writes, ruin_fc, fire, fire_writes, spans, frag, frag_blank,
     frag_writes, frag_spans, puff, puff_blank, puff_writes, puff_spans,
     smoke, smoke_blank, smoke_writes, smoke_spans, census, worst) = parse(probe)
    # Task C2/C3: the probe takes the ruin switch snapshot, the C1 g~10
    # sample and the fire/fragment snapshots at g 2, 12, 30 and 40; MAME
    # names them in call order, and the SNAP records are in that same
    # order. Pair them from the snapshot dir (the boot leg copies the first
    # PNG to SNAP, but the dir keeps every one).
    snap_dir = os.path.join(os.path.dirname(os.path.abspath(probe)), "snap")
    pngs = sorted(glob.glob(os.path.join(snap_dir, "**", "*.png"),
                            recursive=True))
    if snaps and len(pngs) == len(snaps):
        snap_imgs = {fc: Image.open(png).convert("RGB")
                     for fc, png in zip(snaps, pngs)}
    elif snaps:
        snap_imgs = {snaps[0]: Image.open(snap_png).convert("RGB")}
    else:
        snap_imgs = {}
    seed = mis_seed.cart_seed(probe, seeds)   # Task 1: the cart's seed
    print(f"mis_seed_used: {seed:#06x}")
    failures = []

    if not records:
        failures.append("probe wrote no input records")
        return 1
    if not samples:
        failures.append("probe wrote no SCB3 samples")
        return 1
    if fresh is None:
        failures.append("probe wrote no fresh dome dump")
        return 1
    if len(fresh["slots"]) != DOME_COLS:
        failures.append(f"fresh dump has {len(fresh['slots'])} slots, want {DOME_COLS}")
        return 1

    # ---- replay the model from the recorded inputs, one per model frame
    first = None
    for i, (rec, fc, cur, chg) in enumerate(records):
        if fc == 1:
            first = i
            break
    if first is None:
        first = 0
    ship, mis, rules = sm.Ship(), mm.Missiles(seed=seed), rm.Rules(1)
    first_death = rebuild = game_over = None
    dome_deaths = []
    angles = {}
    hud = {}                            # Task G1: model rows per cart frame
    last_sample = max(rows) if rows else 0
    i = first
    m = 0
    while 0 <= i < len(records):
        rec, fc, cur, chg = records[i]
        died = frame_model((ship, mis, rules), cur, chg)
        m += 1
        angles[m] = ship.angle
        hud[m] = hm.hud_rows(rules, mis)
        if died and rules.dome_dead:
            dome_deaths.append(m)
            if first_death is None:
                first_death = m
        if first_death is not None and rebuild is None and m > first_death \
           and rules.dead_t == 0 and rules.dome_dead:
            rebuild = m
        if rules.game_over and game_over is None:
            game_over = m
        if m >= last_sample:
            break                       # every sampled frame has a model row
        i += 1

    if first_death is None:
        failures.append("the model never hit a dome death in the recorded game")
        return 1
    if rebuild is None:
        failures.append("the model never rebuilt the dome after the first death")
        return 1
    if game_over is None:
        failures.append("the model never reached GAME OVER in the recorded game")
        return 1
    if game_over > m:
        failures.append(f"the probe did not run long enough (model game over is "
                        f"at frame {game_over}, only {m} frames recorded)")
        return 1

    print(f"model: first dome death at cart frame {first_death}, rebuild at "
          f"{rebuild}, GAME OVER at {game_over}")

    # ---- C5 proof 1: every collapse frame's worst scanline is <= 96 ----
    worst_c = worst_fc = worst_line = worst_g = worst_death = None
    counted = 0
    if len(dome_deaths) != 3:
        failures.append(f"the model found {len(dome_deaths)} dome deaths, want "
                        f"3 (the centred policy's three collapses)")
    else:
        windows = [(i + 1, d, d + DEAD_FRAMES_NEO)
                   for i, d in enumerate(dome_deaths)]
        missing, over = [], []
        for death_no, start, end in windows:
            for fc in range(start, end):
                if fc not in census:
                    missing.append(fc)
                    continue
                g, c, line = census[fc]
                counted += 1
                if c > SCAN_LIMIT:
                    over.append((fc, c, line))
                if worst_c is None or c > worst_c:
                    worst_c, worst_fc, worst_line = c, fc, line
                    worst_g, worst_death = g, death_no
        if missing:
            failures.append(f"the probe did not scan {len(missing)} collapse "
                            f"frame(s): {missing[:8]}")
        if over:
            failures.append(f"the census found {len(over)} frame(s) over the "
                            f"hardware's {SCAN_LIMIT} sprites per line "
                            f"(first: fc {over[0][0]}, line {over[0][2]}, "
                            f"{over[0][1]} sprites)")
        # the probe's own raw worst must be the census's worst
        if worst_c is not None and worst is not None:
            if (worst[0], worst[1], worst[2]) != (worst_fc, worst_c, worst_line):
                failures.append(
                    f"the raw worst dump is fc {worst[0]}, {worst[1]} at line "
                    f"{worst[2]}, but the census's is fc {worst_fc}, "
                    f"{worst_c} at line {worst_line}")
        print(f"collapse census: {counted} frames scanned "
              f"({len(dome_deaths)} x {DEAD_FRAMES_NEO}); worst {worst_c} at "
              f"line {worst_line}, fc {worst_fc}, g {worst_g}, death "
              f"{worst_death} "
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

    # ---- 1. the columns move during the shake ----
    fixed_scb3 = tuple("%04x" % w for w in WHOLE_SCB3)
    moved = None
    for fc in sorted(samples):
        if fc < first_death:
            continue
        if fc > first_death + COLLAPSE_SHAKE_NEO + 10:
            break
        if tuple(samples[fc]) != fixed_scb3:
            moved = fc
            break
    if moved is None:
        failures.append("the collapse never split the dome columns "
                        "(no moved SCB3 sample)")
    elif moved > first_death + COLLAPSE_SHAKE_NEO + 10:
        failures.append(f"columns first moved at cart frame {moved}, later than "
                        f"the shake window (death {first_death} + "
                        f"{COLLAPSE_SHAKE_NEO})")

    # ---- 3. the ruin stands from the burst to the rebuild ----
    ruin_start = first_death + COLLAPSE_SHAKE_NEO + RUIN_LAG
    ruin_frames = sorted(fc for fc in samples if ruin_start <= fc < rebuild)
    if not ruin_frames:
        failures.append(f"no sampled frames in the ruin window "
                        f"[{ruin_start}, {rebuild})")
    else:
        bad_chain, bad_words = [], []
        want_scb3 = tuple("%04x" % w for w in RUIN_SCB3)
        want_scb4 = tuple("%04x" % w for w in BOX_SCB4)
        for fc in ruin_frames:
            if tuple(samples[fc]) != want_scb3:
                bad_chain.append((fc, samples[fc]))
                continue
            if fc not in ruin:
                bad_words.append((fc, "no U dump"))
                continue
            got_scb4, got_scb1 = ruin[fc]
            if tuple(got_scb4) != want_scb4:
                bad_words.append((fc, "scb4", got_scb4))
                continue
            view = angles.get(fc, 0) % RUIN_VIEWS
            for c in range(RUIN_COLS):
                for r in range(RUIN_ROWS):
                    want = ("%04x" % RUIN_WORDS[view][c][r][0],
                            "%04x" % RUIN_WORDS[view][c][r][1])
                    if got_scb1[c][r] != want:
                        bad_words.append((fc, c, r, got_scb1[c][r], want,
                                          view))
                        break
                else:
                    continue
                break
        if bad_chain:
            failures.append(
                f"the dome's SCB3 chain is not the box's on "
                f"{[f for f, _ in bad_chain]} (first: "
                f"{bad_chain[0][1]})")
        if bad_words:
            failures.append(
                f"the dome's SCB4/SCB1 words are not the ruin's on "
                f"{[b[0] for b in bad_words]} (first: {bad_words[0]})")
        views = sorted({angles.get(fc, 0) % RUIN_VIEWS for fc in ruin_frames})
        print(f"ruin frames compared: {ruin_frames[0]}..{ruin_frames[-1]} "
              f"({len(ruin_frames)} sampled frames, views {views}), SCB3/SCB4 "
              f"box chain + {RUIN_COLS * RUIN_ROWS} SCB1 rows "
              f"{'== the ruin words' if not (bad_chain or bad_words) else 'MISMATCH'}")

    # ---- 4. the rebuilt dome's VRAM matches a fresh dome's ----
    if rebuilt is None or len(rebuilt[1]["slots"]) != DOME_COLS:
        failures.append("no rebuilt dump was recorded")
    else:
        want_s = [l.partition(" ")[2].split() for l in fresh["slots"]]
        got_s = [l.partition(" ")[2].split() for l in rebuilt[1]["slots"]]
        # each slot line: <scb2> <scb3> <scb4> <attr> <tile0..tile7>
        for i_, (w, g) in enumerate(zip(want_s, got_s)):
            if w[:4] != g[:4]:
                failures.append(
                    f"rebuilt slot {DOME_SPRITE + i_} SCB2/3/4+attr differs from fresh:\n"
                    f"  want {w[:4]}\n  got  {g[:4]}")
        if not fresh["pal"] or not rebuilt[1]["pal"]:
            failures.append("no palette dump recorded (fresh or rebuilt)")
        else:
            if len(fresh["pal"]) != 15 or len(rebuilt[1]["pal"]) != 15:
                failures.append("palette dumps have wrong lengths "
                                f"({len(fresh['pal'])} fresh, "
                                f"{len(rebuilt[1]['pal'])} rebuilt; want 15)")
            elif fresh["pal"] != rebuilt[1]["pal"]:
                failures.append(
                    f"rebuilt dome palette differs from fresh:\n"
                    f"  want {' '.join('%04x' % x for x in fresh['pal'])}\n"
                    f"  got  {' '.join('%04x' % x for x in rebuilt[1]['pal'])}")
            else:
                print(f"rebuilt dome palette equals a fresh dome's "
                      f"({len(rebuilt[1]['pal'])} entries)")

    # ---- 5. the snapshot shows the ruin's pixels ----
    if not snap_imgs:
        failures.append("the probe took no snapshot")
    else:
        # Task C2's fireball grows over the ruin: by g 10 (fc 8410 under the
        # default seed) it covers the box's pixels that are not under a
        # higher slot, so no ruin pixel is left to compare there. Use the
        # snapshot in the ruin window with the MOST uncovered ruin pixels
        # (the g 2 fire snapshot, still small); the claim and the 2000-pixel
        # threshold are unchanged.
        ruin_candidates = [fc for fc in snap_imgs
                           if ruin_start <= fc < rebuild and fc in slots]
        best = None
        for fc in sorted(ruin_candidates):
            view = angles.get(fc, 0) % RUIN_VIEWS
            r = ruin_pixels(snap_imgs[fc], slots[fc], view)
            if best is None or r[0] > best[0]:
                best = (r[0], fc, view, r)
        if best is None:
            failures.append(f"no snapshot with a slot dump in the ruin "
                            f"window [{ruin_start}, {rebuild})")
        else:
            compared, ruin_snap_fc, ruin_view, (_c, mismatches, first_px) = best
            g = ruin_snap_fc - first_death - COLLAPSE_SHAKE_NEO
            if compared < 2000:
                failures.append(f"only {compared} ruin pixels compared at the "
                                f"snapshot fc {ruin_snap_fc} (need at least "
                                f"2000)")
            if mismatches:
                failures.append(f"{mismatches} of {compared} ruin pixels "
                                f"differ from ruin_pal through neo_rgb (first "
                                f"{first_px})")
            print(f"snapshot fc {ruin_snap_fc} (g {g}, view {ruin_view}): "
                  f"{compared} opaque ruin pixels not covered by a higher "
                  f"slot compared, {mismatches} mismatches")

    # ---- 6. the ruin's switch writes land before the box's first line ----
    switch_fc, latest = None, None
    for fc in sorted(writes):
        if ruin_start <= fc < rebuild:
            switch_fc = fc
            break
    if switch_fc is None:
        failures.append(f"the probe tapped no dome-slot write in "
                        f"[{ruin_start}, {rebuild})")
    else:
        latest = max(w[2] for w in writes[switch_fc])
        if latest >= DOME_Y + 16:
            failures.append(
                f"the ruin's switch writes land at vpos {latest} on fc "
                f"{switch_fc}, not before the box's first line "
                f"(DOME_Y + 16 = {DOME_Y + 16})")
        print(f"ruin switch frame fc {switch_fc}: "
              f"{len(writes[switch_fc])} dome-slot writes, latest vpos "
              f"{latest} (box's first line vpos {DOME_Y + 16})")

    # ---- C2 proof 1: the fireball's words, previous frame's g ----
    if ruin_fc is None:
        failures.append("the probe saw no ruin switch (dome slot 0 attribute "
                        "PAL_RUIN << 8): no fire window to compare")
    else:
        if ruin_fc != ruin_start:
            failures.append(
                f"the ruin switch is at cart frame {ruin_fc}, but the model's "
                f"burst is at {ruin_start} (death {first_death} + "
                f"{COLLAPSE_SHAKE_NEO})")
        fire_bad = []
        shown, hidden = [], []
        slot_frames = 0
        for fc in sorted(fire):
            g = fc - ruin_fc - 1
            for c in range(FIRE_COUNT):
                if c not in fire[fc]:
                    fire_bad.append((fc, c, "no V record"))
                    continue
                scb2, scb3, scb4, rows_c = fire[fc][c]
                if g < 0 or g >= FIRE_T:
                    if scb3 != 0:
                        fire_bad.append((fc, c, "hidden but SCB3 != 0",
                                         f"0x{scb3:04x}"))
                    continue
                s2 = FIRE["scb2"][g]
                hz = s2 >> 8
                if FIRE["mask"][g] & (1 << c):
                    want3 = ((496 - FIRE["y"][g]) << 7) | FIRE["h"][g]
                    want4 = ((FIRE["x"][g] + c * (hz + 1)) & 0x1ff) << 7
                    if (scb2, scb3, scb4) != (s2, want3, want4):
                        fire_bad.append(
                            (fc, c, "SCB2/3/4",
                             f"got {scb2:04x},{scb3:04x},{scb4:04x} "
                             f"want {s2:04x},{want3:04x},{want4:04x}"))
                elif scb3 != 0:
                    fire_bad.append((fc, c, "masked column but SCB3 != 0",
                                     f"0x{scb3:04x}"))
                pic = FIRE["pic"][g]
                for r in range(FIRE_ROWS_H):
                    want = (COLLAPSE_TILE_BASE + FIRE["tile"][pic][c][r],
                            PAL_FIRE << 8)
                    if rows_c[r] != want:
                        fire_bad.append(
                            (fc, c, f"row {r}", f"{rows_c[r]} want {want}"))
                        break
                for r in range(FIRE_ROWS_H, FIRE_SCB1_ROWS):
                    if rows_c[r][0] != COLLAPSE_TILE_BASE:
                        fire_bad.append(
                            (fc, c, f"blank row {r}",
                             f"0x{rows_c[r][0]:04x}"))
                        break
                slot_frames += 1
            if 0 <= g < FIRE_T:
                shown.append(fc)
            else:
                hidden.append(fc)
        # the burst to g 44 + 1 must all have been dumped
        want_frames = list(range(ruin_fc + 1, ruin_fc + 1 + FIRE_T + 1))
        missing = [fc for fc in want_frames if fc not in fire]
        if missing:
            failures.append(f"the probe dumped no fire words on {missing[:8]}"
                            f" (want the burst through g {FIRE_T})")
        if fire_bad:
            failures.append(
                f"{len(fire_bad)} fire word mismatches (first: "
                f"{fire_bad[0]})")
        print(f"fire words compared: fc {ruin_fc}..{ruin_fc + 60} "
              f"({len(fire)} frames, {slot_frames} shown slot-frames), "
              f"shown g 0..{FIRE_T - 1} at fc {shown[0]}..{shown[-1]} "
              f"(previous-frame g), hidden g {FIRE_T}.. at fc "
              f"{hidden[0]}..{hidden[-1]}; "
              f"{'all match the tables' if not fire_bad else 'MISMATCH'}")

    # ---- C2 proof 2: the fireball's pixels at g 2, 12 and 30 ----
    for g in (2, 12, 30):
        fc = ruin_fc + 1 + g if ruin_fc is not None else None
        if fc is None or fc not in snap_imgs:
            failures.append(f"no fire snapshot at g {g} (fc {fc})")
            continue
        if fc not in slots:
            failures.append(f"no slot dump at the fire snapshot fc {fc} "
                            f"(g {g})")
            continue
        compared, mismatches, first_px = fire_pixels(snap_imgs[fc], slots[fc], g)
        need = 500 if g == 2 else 3000
        if compared < need:
            failures.append(f"only {compared} fireball pixels compared at "
                            f"g {g} (need at least {need})")
        if mismatches:
            failures.append(
                f"{mismatches} of {compared} fireball pixels differ from "
                f"fire_pal through neo_rgb at g {g} (first {first_px})")
        print(f"snapshot fc {fc} (g {g}): {compared} opaque fireball pixels "
              f"not covered by a higher slot compared, {mismatches} "
              f"mismatches")

    # ---- C2 proof 3: no fire write lands inside a fire slot's span ----
    if not fire_writes:
        failures.append("the probe recorded no write to a fire slot")
    elif ruin_fc is None:
        failures.append("no ruin switch: cannot bound the collapse's frames")
    else:
        collapse_start = ruin_fc - COLLAPSE_SHAKE_NEO
        tear_frames = set()
        checked = 0
        latest = None
        for fc, ws in fire_writes.items():
            if fc < collapse_start or fc >= rebuild:
                continue                # only the collapse's own frames
            old = spans.get(fc - 1, {})
            new = spans.get(fc, {})
            for slot, _reg, vpos in ws:
                if not (FIRE_SPRITE <= slot < FIRE_SPRITE + FIRE_COUNT):
                    continue
                checked += 1
                if latest is None or vpos > latest:
                    latest = vpos
                if _unsafe(vpos, span_of(old.get(slot)),
                           span_of(new.get(slot))):
                    tear_frames.add(fc)
        if tear_frames:
            failures.append(
                f"the fire slots have {len(tear_frames)} frames with a write "
                f"inside the slot's old or new span (want 0): "
                f"{sorted(tear_frames)[:8]}")
        print(f"fire slot writes: {checked} checked over the collapse "
              f"(fc {collapse_start}..{rebuild - 1}), latest vpos {latest}, "
              f"{len(tear_frames)} frames with a write inside the slot's old "
              f"or new span")

        # the two heaviest commits: the first-frame blanking (rows 10..31 of
        # all 12 columns) and a picture-change frame (rows 0..9 + placement)
        for label, fc in (("first-frame blanking", collapse_start + 1),
                          ("picture change",
                           next((f for f in sorted(fire)
                                 if f - ruin_fc - 1 >= 1 and
                                 FIRE["pic"][f - ruin_fc - 1] !=
                                 FIRE["pic"][f - ruin_fc - 2]),
                                None))):
            if fc is None or fc not in fire_writes:
                continue
            ws = fire_writes[fc]
            vps = [w[2] for w in ws]
            scb1 = sum(1 for w in ws if w[1] == 1)
            place = sum(1 for w in ws if w[1] in (2, 3, 4))
            print(f"  {label} commit fc {fc}: {len(ws)} words "
                  f"({scb1} SCB1, {place} placement), vpos {min(vps)}.."
                  f"{max(vps)} = {max(vps) - min(vps) + 1} lines")

    # ---- C3 proof 1: the fragments' words, previous frame's g ----
    if ruin_fc is None:
        failures.append("the probe saw no ruin switch: no fragment window")
    elif not frag:
        failures.append("the probe dumped no fragment words")
    else:
        if ruin_fc != ruin_start:
            failures.append(
                f"the ruin switch is at cart frame {ruin_fc}, but the model's "
                f"burst is at {ruin_start} (death {first_death} + "
                f"{COLLAPSE_SHAKE_NEO})")
        want_frames = list(range(ruin_fc, ruin_fc + FRAG_T + 3))
        missing = [fc for fc in want_frames if fc not in frag]
        if missing:
            failures.append(f"the probe dumped no fragment words on "
                            f"{missing[:8]} (want the ruin switch through "
                            f"g {FRAG_T + 1})")
        frag_bad = []
        slot_frames = 0
        shown_frames, hidden_frames = [], []
        for fc in sorted(fc for fc in frag
                         if ruin_fc <= fc <= ruin_fc + FRAG_T + 2):
            g = fc - ruin_fc - 1
            for n in range(FRAG_COUNT):
                rec = frag[fc].get(n)
                if rec is None:
                    frag_bad.append((fc, n, "no Z record"))
                    continue
                scb2, scb3, scb4, rows_c = rec
                if scb2 != 0x0fff:
                    frag_bad.append((fc, n, "SCB2", f"0x{scb2:04x}"))
                inside = 0 <= g < FRAG_T
                hidden = (not inside
                          or FRAGS["x"][n][g] == FRAGS["hide"]
                          or FRAGS["y"][n][g] == FRAGS["hide"])
                if hidden:
                    if scb3 != 0:
                        frag_bad.append((fc, n, "hidden but SCB3 != 0",
                                         f"0x{scb3:04x}"))
                    if scb4 != 0:
                        frag_bad.append((fc, n, "hidden but SCB4 != 0",
                                         f"0x{scb4:04x}"))
                else:
                    x, y = FRAGS["x"][n][g], FRAGS["y"][n][g]
                    want3 = ((496 - y) << 7) | FRAGS["rows"][n]
                    want4 = (x & 0x1ff) << 7
                    if scb3 != want3:
                        frag_bad.append((fc, n, "SCB3",
                                         f"0x{scb3:04x}",
                                         f"0x{want3:04x}"))
                    if scb4 != want4:
                        frag_bad.append((fc, n, "SCB4",
                                         f"0x{scb4:04x}",
                                         f"0x{want4:04x}"))
                    flip = FRAGS["flip"][n][g]
                    nrows = FRAGS["rows"][n]
                    for r in range(FRAG_MAX_ROWS):
                        if r < nrows:
                            t = FRAGS["tile"][n][
                                (nrows - 1 - r) if (flip & 2) else r]
                        else:
                            t = 0
                        want = (COLLAPSE_TILE_BASE + t,
                                (PAL_DOME << 8) | flip)
                        if rows_c[r] != want:
                            frag_bad.append((fc, n, f"row {r}",
                                             rows_c[r], want))
                            break
                slot_frames += 1
            if 0 <= g < FRAG_T:
                shown_frames.append(fc)
            else:
                hidden_frames.append(fc)
        if frag_bad:
            failures.append(
                f"{len(frag_bad)} fragment word mismatches (first: "
                f"{frag_bad[0]})")
        print(f"fragment words compared: fc {ruin_fc}..{ruin_fc + FRAG_T + 2} "
              f"({len(shown_frames) + len(hidden_frames)} frames, "
              f"{slot_frames} slot-frames), shown g 0..{FRAG_T - 1} at fc "
              f"{shown_frames[0] if shown_frames else None}.."
              f"{shown_frames[-1] if shown_frames else None}, hidden g "
              f"{FRAG_T}..{FRAG_T + 1} at fc "
              f"{hidden_frames[0] if hidden_frames else None}.."
              f"{hidden_frames[-1] if hidden_frames else None}; "
              f"{'all match the tables' if not frag_bad else 'MISMATCH'}")
        if not frag_blank:
            failures.append("the probe dumped no fragment blank rows")
        else:
            blank_bad = [(n, r, got)
                         for n, rows_b in frag_blank.items()
                         for r, (got, _attr) in enumerate(rows_b)
                         if got != COLLAPSE_TILE_BASE]
            if blank_bad:
                failures.append(
                    f"{len(blank_bad)} fragment blank rows are not "
                    f"COLLAPSE_TILE_BASE (first: {blank_bad[0]})")
            print(f"fragment blank rows: {FRAG_COUNT * (FRAG_SCB1_ROWS - FRAG_MAX_ROWS)} "
                  f"checked (rows {FRAG_MAX_ROWS}..{FRAG_SCB1_ROWS - 1} of all "
                  f"{FRAG_COUNT} slots), {'all blank' if not blank_bad else 'MISMATCH'}")

    # ---- C3 proof 2: the fragments' pixels at g 2, 12, 30 and 40 ----
    if not snap_imgs:
        failures.append("the probe took no snapshot")
    elif not fresh["pal"]:
        failures.append("no fresh palette dump for the fragments' bank")
    else:
        all_vflip2 = set()
        named = None
        for g in (2, 12, 30, 40):
            fc = ruin_fc + 1 + g if ruin_fc is not None else None
            if fc is None or fc not in snap_imgs:
                failures.append(f"no fragment snapshot at g {g} (fc {fc})")
                continue
            if fc not in slots:
                failures.append(f"no slot dump at the fragment snapshot fc "
                                f"{fc} (g {g})")
                continue
            compared, mismatches, first_px, vflip2, bad_by_frag = frag_pixels(
                snap_imgs[fc], slots[fc], g, fresh["pal"])
            if compared < 300:
                failures.append(f"only {compared} fragment pixels compared at "
                                f"g {g} (need at least 300)")
            if mismatches:
                failures.append(
                    f"{mismatches} of {compared} fragment pixels differ from "
                    f"PAL_DOME through neo_rgb at g {g} (first {first_px}; "
                    f"mismatches by fragment {sorted(bad_by_frag.items())})")
            all_vflip2 |= vflip2
            if vflip2 and named is None:
                named = (g, sorted(vflip2)[0])
            print(f"snapshot fc {fc} (g {g}): {compared} opaque fragment "
                  f"pixels not covered by a higher slot compared, "
                  f"{mismatches} mismatches; V-flipped 2-tile fragments among "
                  f"them: {sorted(vflip2)}")
        if not all_vflip2:
            failures.append("no V-flipped 2-tile fragment among the compared "
                            "pixels")
        else:
            print(f"V-flipped 2-tile fragments compared: "
                  f"{sorted(all_vflip2)} (first at g {named[0]}: "
                  f"fragment {named[1]})")

    # ---- C3 proof 3: no fragment write lands inside a fragment slot's span ----
    if not frag_writes:
        failures.append("the probe recorded no write to a fragment slot")
    elif ruin_fc is None:
        failures.append("no ruin switch: cannot bound the fragments' "
                        "collapse frames")
    else:
        collapse_start = ruin_fc - COLLAPSE_SHAKE_NEO
        tear_frames = set()
        checked = 0
        latest = None
        worst_fc, worst_words = None, 0
        place_fc, place_words = None, 0
        for fc, ws in frag_writes.items():
            if fc < collapse_start or fc >= rebuild:
                continue                # only the collapse's own frames
            old = frag_spans.get(fc - 1, {})
            new = frag_spans.get(fc, {})
            for slot, _reg, vpos in ws:
                if not (FRAG_SPRITE <= slot < FRAG_SPRITE + FRAG_COUNT):
                    continue
                checked += 1
                if latest is None or vpos > latest:
                    latest = vpos
                if _unsafe(vpos, span_of(old.get(slot)),
                           span_of(new.get(slot))):
                    tear_frames.add(fc)
            if len(ws) > worst_words:
                worst_words, worst_fc = len(ws), fc
            pw = sum(1 for w in ws if w[1] in (3, 4))
            if pw > place_words:
                place_words, place_fc = pw, fc
        if tear_frames:
            failures.append(
                f"the fragment slots have {len(tear_frames)} frames with a "
                f"write inside the slot's old or new span (want 0): "
                f"{sorted(tear_frames)[:8]}")
        print(f"fragment slot writes: {checked} checked over the collapse "
              f"(fc {collapse_start}..{rebuild - 1}), latest vpos {latest}, "
              f"{len(tear_frames)} frames with a write inside the slot's old "
              f"or new span")
        if worst_fc is not None:
            ws = frag_writes[worst_fc]
            vps = [w[2] for w in ws]
            print(f"  worst fragment commit fc {worst_fc}: {worst_words} words, "
                  f"vpos {min(vps)}..{max(vps)} = "
                  f"{max(vps) - min(vps) + 1} lines")
        if place_fc is not None:
            print(f"  worst fragment placement: {place_words} words "
                  f"(SCB3/SCB4) at fc {place_fc}")

    # ---- C4 proof 1a: the puffs' words, previous frame's f ----
    if ruin_fc is None:
        failures.append("no ruin switch: cannot bound the puffs' shake window")
    elif not puff:
        failures.append("the probe dumped no puff words")
    else:
        collapse_start = ruin_fc - COLLAPSE_SHAKE_NEO
        want_frames = list(range(collapse_start + 1, ruin_fc + 31))
        missing = [fc for fc in want_frames if fc not in puff]
        if missing:
            failures.append(f"the probe dumped no puff words on {missing[:8]} "
                            f"(want the collapse's f 0 through the burst + 30)")
        puff_bad = []
        shown_frames, hidden_frames = [], []
        slot_frames = 0
        for fc in sorted(fc for fc in puff
                         if collapse_start + 1 <= fc <= ruin_fc + 30):
            f = fc - collapse_start - 1
            want = puff_slot_words(f)
            for slot in range(PUFF_SPRITE, PUFF_SPRITE + PUFF_COUNT):
                rec = puff[fc].get(slot)
                if rec is None:
                    puff_bad.append((fc, slot, "no PU record"))
                    continue
                scb2, scb3, scb4, rows_c = rec
                w = want[slot]
                if (scb2, scb3, scb4) != w[:3]:
                    puff_bad.append(
                        (fc, slot, "SCB2/3/4",
                         f"got {scb2:04x},{scb3:04x},{scb4:04x} "
                         f"want {w[0]:04x},{w[1]:04x},{w[2]:04x}"))
                if w[3] is not None:
                    for r in range(PUFF_ROWS):
                        if rows_c[r] != w[3][r]:
                            puff_bad.append((fc, slot, f"row {r}",
                                             rows_c[r], w[3][r]))
                            break
                slot_frames += 1
            if 0 <= f < COLLAPSE_SHAKE_NEO:
                shown_frames.append(fc)
            else:
                hidden_frames.append(fc)
        if puff_bad:
            failures.append(f"{len(puff_bad)} puff word mismatches (first: "
                            f"{puff_bad[0]})")
        print(f"puff words compared: fc {collapse_start + 1}.."
              f"{ruin_fc + 30} ({len(shown_frames) + len(hidden_frames)} "
              f"frames, {slot_frames} slot-frames), shown f 0.."
              f"{COLLAPSE_SHAKE_NEO - 1} at fc {shown_frames[0] if shown_frames else None}.."
              f"{shown_frames[-1] if shown_frames else None}, hidden f "
              f"{COLLAPSE_SHAKE_NEO}.. at fc "
              f"{hidden_frames[0] if hidden_frames else None}.."
              f"{hidden_frames[-1] if hidden_frames else None}; "
              f"{'all match the model' if not puff_bad else 'MISMATCH'}")
        if not puff_blank:
            failures.append("the probe dumped no puff blank rows")
        else:
            blank_bad = [(slot, r, got)
                         for slot, rows_b in puff_blank.items()
                         for r, (got, _attr) in enumerate(rows_b)
                         if got != COLLAPSE_TILE_BASE]
            if blank_bad:
                failures.append(
                    f"{len(blank_bad)} puff blank rows are not "
                    f"COLLAPSE_TILE_BASE (first: {blank_bad[0]})")
            print(f"puff blank rows: {PUFF_COUNT * (PUFF_SCB1_ROWS - PUFF_ROWS)} "
                  f"checked (rows {PUFF_ROWS}..{PUFF_SCB1_ROWS - 1} of all "
                  f"{PUFF_COUNT} slots), "
                  f"{'all blank' if not blank_bad else 'MISMATCH'}")

    # ---- C4/V1 proof 1b: the smoke's words, previous frame's g ----
    if ruin_fc is None:
        failures.append("no ruin switch: no smoke window")
    elif not smoke:
        failures.append("the probe dumped no smoke words")
    else:
        # The rebuild frame hands the overlay range back to src/cracks.c,
        # which hides the FRONT slots (SCB3 0) directly; collapse_prepare
        # now hides the BACK slots on that same frame (the last death frame
        # before a rebuild), so the last shown frame is rebuild - 1 and
        # from the rebuild on only the hide matters.
        want_frames = list(range(ruin_fc, rebuild))
        missing = [fc for fc in want_frames if fc not in smoke]
        if missing:
            failures.append(f"the probe dumped no smoke words on "
                            f"{missing[:8]} (want the burst to the frame "
                            f"before the rebuild)")
        smoke_bad = []
        slot_frames = 0
        switches = 0
        prev_front = None
        views = set()
        for fc in sorted(fc for fc in smoke
                         if ruin_fc <= fc <= ruin_fc + 80):
            if fc >= rebuild:
                for slot in SMOKE_SLOTS:
                    rec = smoke[fc].get(slot)
                    if rec is None:
                        smoke_bad.append((fc, slot, "no SM record"))
                    elif rec[1] != 0:
                        smoke_bad.append((fc, slot, "not hidden at/after "
                                          "the rebuild", f"0x{rec[1]:04x}"))
                    slot_frames += 1
                continue
            g = fc - ruin_fc - 1
            angle = angles.get(fc - 1, 0) % 240
            views.add(angle)
            front = SMOKE["smoke_front"][angle]
            if prev_front is not None:
                switches += bin(front ^ prev_front).count("1")
            prev_front = front
            want = smoke_slot_words(g, angle)
            for slot in SMOKE_SLOTS:
                rec = smoke[fc].get(slot)
                if rec is None:
                    smoke_bad.append((fc, slot, "no SM record"))
                    continue
                scb2, scb3, scb4, rows_c = rec
                w = want[slot]
                if (scb2, scb3, scb4) != w[:3]:
                    smoke_bad.append(
                        (fc, slot, "SCB2/3/4",
                         f"got {scb2:04x},{scb3:04x},{scb4:04x} "
                         f"want {w[0]:04x},{w[1]:04x},{w[2]:04x}"))
                if w[3] is not None:
                    for r in range(SMOKE_ROWS):
                        if rows_c[r] != w[3][r]:
                            smoke_bad.append((fc, slot, f"row {r}",
                                              rows_c[r], w[3][r]))
                            break
                slot_frames += 1
        if smoke_bad:
            failures.append(f"{len(smoke_bad)} smoke word mismatches (first: "
                            f"{smoke_bad[0]})")
        print(f"smoke words compared: fc {ruin_fc}.."
              f"{ruin_fc + 80} ({len(want_frames)} frames of the burst.."
              f"rebuild, {slot_frames} slot-frames, "
              f"{switches} front/back bit switches checked, angles "
              f"{sorted(views)}), "
              f"{'all match the tables' if not smoke_bad else 'MISMATCH'}")
        if not smoke_blank:
            failures.append("the probe dumped no smoke blank rows")
        else:
            blank_bad = [(slot, r, got)
                         for slot, rows_b in smoke_blank.items()
                         for r, (got, _attr) in enumerate(rows_b)
                         if got != COLLAPSE_TILE_BASE]
            if blank_bad:
                failures.append(
                    f"{len(blank_bad)} smoke blank rows are not "
                    f"COLLAPSE_TILE_BASE (first: {blank_bad[0]})")
            print(f"smoke blank rows: "
                  f"{SMOKE_TOTAL * (SMOKE_SCB1_ROWS - SMOKE_ROWS)} "
                  f"checked (rows {SMOKE_ROWS}..{SMOKE_SCB1_ROWS - 1} of all "
                  f"{SMOKE_TOTAL} slots), "
                  f"{'all blank' if not blank_bad else 'MISMATCH'}")

    # ---- C4 proof 2: the puff (f 35) and smoke (g 40) pixels ----
    if not snap_imgs:
        failures.append("the probe took no snapshot")
    elif ruin_fc is not None:
        collapse_start = ruin_fc - COLLAPSE_SHAKE_NEO
        pf = 35
        pfc = collapse_start + 1 + pf
        if pfc not in snap_imgs:
            failures.append(f"no puff snapshot at f {pf} (fc {pfc})")
        elif pfc not in slots:
            failures.append(f"no slot dump at the puff snapshot fc {pfc}")
        else:
            compared, mismatches, first_px = puff_pixels(
                snap_imgs[pfc], slots[pfc], pf)
            if compared < 200:
                failures.append(f"only {compared} puff pixels compared at "
                                f"f {pf} (need at least 200)")
            if mismatches:
                failures.append(
                    f"{mismatches} of {compared} puff pixels differ from "
                    f"fire_pal through neo_rgb at f {pf} (first {first_px})")
            print(f"snapshot fc {pfc} (f {pf}): {compared} opaque puff pixels "
                  f"not covered by a higher slot compared, {mismatches} "
                  f"mismatches")
        # The plan named the g 40 snapshot, but at g 40 the C2 fireball and
        # C3's fragments cover most of the smoke (460 pixels), so the
        # >1000-pixel proof uses the g 50 snapshot the probe now also takes
        # (the fireball is gone by then). The g 40 snapshot is still
        # checked for its own pixels (and mismatches).
        for g, need in ((40, 200), (50, 1000)):
            sfc = ruin_fc + 1 + g
            if sfc not in snap_imgs:
                failures.append(f"no smoke snapshot at g {g} (fc {sfc})")
            elif sfc not in slots:
                failures.append(f"no slot dump at the smoke snapshot fc "
                                f"{sfc}")
            else:
                frag_owner, _frag_idx = fragment_frame(g)
                fire = fire_blit(g) if g < FIRE_T else np.zeros((224, 320), int)
                angle = angles.get(sfc - 1, 0) % 240
                compared, mismatches, first_px = smoke_pixels(
                    snap_imgs[sfc], slots[sfc], g, angle, frag_owner, fire)
                if compared < need:
                    failures.append(f"only {compared} smoke pixels compared "
                                    f"at g {g} (need at least {need})")
                if mismatches:
                    failures.append(
                        f"{mismatches} of {compared} smoke pixels differ "
                        f"from smoke_pal through neo_rgb at g {g} (first "
                        f"{first_px})")
                print(f"snapshot fc {sfc} (g {g}, angle {angle}): "
                      f"{compared} opaque smoke pixels not covered by a "
                      f"higher slot compared, {mismatches} mismatches")

    # ---- C4 proof 3: no puff/smoke write inside their span; worst commit ----
    if ruin_fc is None:
        failures.append("no ruin switch: cannot bound the puffs/smoke")
    else:
        collapse_start = ruin_fc - COLLAPSE_SHAKE_NEO
        for label, wrs, spans_, slot_set in (
                ("puff", puff_writes, puff_spans,
                 set(range(PUFF_SPRITE, PUFF_SPRITE + PUFF_COUNT))),
                ("smoke", smoke_writes, smoke_spans, set(SMOKE_SLOTS))):
            if not wrs:
                failures.append(f"the probe recorded no write to a {label} slot")
                continue
            tear_frames = set()
            checked = 0
            latest = None
            for fc, ws in wrs.items():
                if fc < collapse_start or fc >= rebuild:
                    continue
                old = spans_.get(fc - 1, {})
                new = spans_.get(fc, {})
                for slot, reg, vpos, data in ws:
                    if slot not in slot_set:
                        continue
                    # a SCB3 0 write disables the slot: it hides, it cannot
                    # tear a sprite (src/cracks.c's one-time hide at the
                    # collapse's first frame writes exactly this).
                    if reg == 3 and data == 0:
                        continue
                    checked += 1
                    if latest is None or vpos > latest:
                        latest = vpos
                    if _unsafe(vpos, span_of(old.get(slot)),
                               span_of(new.get(slot))):
                        tear_frames.add(fc)
            if tear_frames:
                failures.append(
                    f"the {label} slots have {len(tear_frames)} frames with a "
                    f"write inside the slot's old or new span (want 0): "
                    f"{sorted(tear_frames)[:8]}")
            print(f"{label} slot writes: {checked} checked over the collapse "
                  f"(fc {collapse_start}..{rebuild - 1}), latest vpos "
                  f"{latest}, {len(tear_frames)} frames with a write inside "
                  f"the slot's old or new span")

        all_writes = {}
        for src in (fire_writes, frag_writes, puff_writes, smoke_writes):
            for fc, ws in src.items():
                if collapse_start <= fc < rebuild:
                    all_writes.setdefault(fc, []).extend(ws)
        worst_fc, worst_words, worst_lines = None, 0, 0
        worst_vps = None
        for fc in range(collapse_start, rebuild):
            ws = all_writes.get(fc, [])
            if len(ws) > worst_words:
                worst_fc, worst_words = fc, len(ws)
                vps = [w[2] for w in ws]
                worst_vps = (min(vps), max(vps))
                worst_lines = max(vps) - min(vps) + 1
        if worst_fc is not None:
            print(f"worst collapse commit fc {worst_fc}: {worst_words} words "
                  f"(fire/frag/smoke/puff), vpos {worst_vps[0]}.."
                  f"{worst_vps[1]} = {worst_lines} lines")

    # ---- 7. GAME OVER by the model's frame, within the derived budget ----
    if not rows:
        failures.append("the probe decoded no fix rows (no GAME OVER check)")
    else:
        def go_at(fc):
            return rows.get(fc) and rows[fc][HUD_GAMEOVER_ROW].strip() == "GAME OVER"

        # Task G1: rows 7 and 8 must equal the model's on every sampled
        # frame (blank before GAME OVER, "GAME OVER" and its cap after it).
        bad_rows = []
        for fc in sorted(rows):
            if fc not in hud:
                continue
            if rows[fc][HUD_GAMEOVER_ROW] != hud[fc][HUD_GAMEOVER_ROW] \
               or rows[fc][HUD_GAMEOVER_CAP_ROW] != hud[fc][HUD_GAMEOVER_CAP_ROW]:
                bad_rows.append((fc, rows[fc][HUD_GAMEOVER_ROW],
                                 hud[fc][HUD_GAMEOVER_ROW]))
                break
        if bad_rows:
            failures.append(f"GAME OVER rows 7/8 do not match the model on "
                            f"sampled frame {bad_rows[0][0]} (drawn "
                            f"{bad_rows[0][1]!r}, model {bad_rows[0][2]!r})")
        else:
            print(f"GAME OVER rows 7/8: {len([fc for fc in rows if fc in hud])} "
                  f"sampled frames match the model")
        before = [fc for fc in sorted(rows) if fc < game_over - GAME_OVER_SLACK]
        after = [fc for fc in sorted(rows) if fc >= game_over - GAME_OVER_SLACK]
        if before and any(go_at(fc) for fc in before):
            failures.append(
                f"GAME OVER shown early at cart frame {[fc for fc in before
                 if go_at(fc)][0]} (model's frame {game_over})")
        seen_go_row = next((fc for fc in after if go_at(fc)), None)
        if seen_go_row is None:
            failures.append(
                f"the fix layer never showed GAME OVER by the model's "
                f"frame {game_over} + {GAME_OVER_SLACK} slack; sampled "
                f"rows at frames {sorted(rows)}")
        else:
            print(f"GAME OVER shown on the fix layer at cart frame "
                  f"{seen_go_row} (model: {game_over})")

    if failures:
        print("FAIL collapse:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS collapse: columns moved during the shake (first split at "
          f"cart frame {moved}), the ruin stands for fc "
          f"{ruin_frames[0]}..{ruin_frames[-1]} in the box chain and its "
          f"words, rebuilt dome VRAM == fresh dome, snapshot pixels == the "
          f"ruin, switch writes before vpos {DOME_Y + 16}, GAME OVER by the "
          f"model's frame {game_over}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
