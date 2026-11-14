"""The one sprite slot map (M5 Task 1).

  test_slots.py   (host, pytest)

src/slots.h is the ONLY place slot numbers are defined; build/slots.json
(and build/slots.lua, for the MAME probes) are generated from it by the
Makefile. This test proves the map it produces:

  1. src/slots.h parses: every #define evaluates, and the generated
     build/slots.json equals a direct parse of the header (seeded with the
     same NSTARS the build used, so it also holds for the -DNSTARS=16
     renumbering build);
  2. the ranges are contiguous, non-overlapping and in draw order (stars,
     missiles behind, dome, broken overlays, ship, front missiles,
     explosions, radar), every range starts where the previous one ended,
     and the last slot is <= 380;
  3. every count in the map equals the art it describes: NSTARS <= 16 (the
     renumbering proof's bound), MIS_BEHIND_COUNT = NOBJ x MIS_COLS_MAX,
     DOME_COUNT = DOME_COLS, SHIP_COUNT = SHIP_COLS, EXPL_COUNT = NEXPL x
     EXPL_COLS, RADAR_COUNT = 4 + 3 x (1 + 4) (the task's own number), and
     BROKEN_SLOT_COUNT equals tools/render_broken.py's computed overlay
     slot span (the "count from the generator, today 145").
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))

SLOTS_H = os.path.join(ROOT, "src", "slots.h")
SLOTS_JSON = os.path.join(ROOT, "build", "slots.json")
MISSILES_H = os.path.join(ROOT, "src", "missiles.h")
MIS_GFX_H = os.path.join(ROOT, "src", "mis_gfx.h")
DOME_MAP_H = os.path.join(ROOT, "build", "dome_map.h")
SHIP_MAP_H = os.path.join(ROOT, "build", "ship_map.h")
MISSILE_MAP_H = os.path.join(ROOT, "build", "missile_map.h")

# the draw order the plan states (M5 Task 1): each range's (name, count-name)
ORDER = [
    ("STAR_SPRITE", "NSTARS"),
    ("MIS_BEHIND_SPRITE", "MIS_BEHIND_COUNT"),
    ("DOME_SPRITE", "DOME_COUNT"),
    ("BROKEN_SLOT_BASE", "BROKEN_SLOT_COUNT"),
    ("SHIP_SPRITE", "SHIP_COUNT"),
    ("MIS_FRONT_SPRITE", "MIS_FRONT_COUNT"),
    ("EXPL_SPRITE", "EXPL_COUNT"),
    ("RADAR_SPRITE", "RADAR_COUNT"),
]

LAST_SLOT_MAX = 380           # the hardware's 381 sprites


def parse_slots_h(nstars=None):
    """evaluate the #defines in src/slots.h. Returns {name: value}. The
    header's own `#ifndef NSTARS` default is replaced by `nstars` when the
    caller passes the build's override (the -DNSTARS=16 proof)."""
    defines = {}
    overrides = {} if nstars is None else {"NSTARS": nstars}
    if nstars is not None:
        defines["NSTARS"] = nstars
    active = True
    for raw in open(SLOTS_H):
        line = raw.split("//")[0].split("/*")[0].strip()
        if not line:
            continue
        m = re.match(r"#ifndef\s+(\w+)", line)
        if m:
            active = m.group(1) not in overrides and m.group(1) not in defines
            continue
        if line.startswith("#endif"):
            active = True
            continue
        if not active:
            continue
        m = re.match(r"#define\s+(\w+)\s+(.+)", line)
        if not m:
            continue
        name, expr = m.group(1), m.group(2).strip()
        if name == "NSTARS" and nstars is not None:
            continue
        # evaluate: substitute already-known names (longest first)
        for k in sorted(defines, key=len, reverse=True):
            expr = expr.replace(k, str(defines[k]))
        expr = expr.replace("(", " ( ").replace(")", " ) ")
        defines[name] = int(eval(expr, {"__builtins__": {}}, {}))
    return defines


def load_json():
    with open(SLOTS_JSON) as fh:
        return {k: int(v) for k, v in json.load(fh).items()}


def ranges(values):
    """the consecutive (start, after) pairs in draw order; raises if a range
    does not start where the previous one ended."""
    out = []
    prev_after = None
    for name, count_name in ORDER:
        s = values[name]
        n = values[count_name]
        out.append((name, s, s + n))
        if prev_after is not None and s != prev_after:
            raise AssertionError(f"{name} starts at {s}, want the previous "
                                 f"range's end {prev_after}")
        prev_after = s + n
    return out


def test_header_matches_json():
    j = load_json()
    h = parse_slots_h(nstars=j["NSTARS"])     # the build's own override
    assert h == j, (h, j)


def test_default_header_is_twelve_stars():
    """src/slots.h's own default (what a plain `make` builds) is the plan's
    NSTARS 12; the generated json must be that build's (no override set)."""
    h = parse_slots_h(nstars=None)
    assert h["NSTARS"] == 12
    j = load_json()
    assert j["NSTARS"] == 12
    assert h == j


def test_ranges_ordered_contiguous_and_in_bounds():
    j = load_json()
    rng = ranges(j)
    last = rng[-1][2] - 1
    assert last <= LAST_SLOT_MAX, f"last slot {last} > {LAST_SLOT_MAX}"
    # starts ascend, nothing overlaps
    for (n1, s1, a1), (n2, s2, a2) in zip(rng, rng[1:]):
        assert a1 <= s2, f"{n1}..{a1 - 1} overlaps {n2} (starts {s2})"
        assert s1 < s2, "order"
    # the plan's table, checked against the map's own numbers
    assert j["STAR_SPRITE"] == 1
    assert j["DOME_COUNT"] == 11
    assert j["SHIP_COUNT"] == 2
    assert j["RADAR_COUNT"] == 19      # 4 frame + 3 x (1 stick + 4 heading)


def _define(path, name):
    txt = open(path).read()
    m = re.search(r"#define\s+" + name + r"\s+(\d+)", txt)
    assert m, f"{name} not found in {path}"
    return int(m.group(1))


def test_counts_match_the_art():
    """every count in the map equals the art constant it describes (the
    generated headers / missiles.h / mis_gfx.h)."""
    j = load_json()
    assert j["NSTARS"] == 12
    assert j["MIS_BEHIND_COUNT"] == j["MIS_FRONT_COUNT"] \
        == NOBJ() * MIS_COLS_MAX()
    assert j["DOME_COUNT"] == _define(DOME_MAP_H, "DOME_COLS")
    assert j["SHIP_COUNT"] == _define(SHIP_MAP_H, "SHIP_COLS")
    assert j["EXPL_COUNT"] == NEXPL() * _define(MISSILE_MAP_H, "EXPL_COLS")
    assert j["MIS_BEHIND_SPRITE"] + j["MIS_BEHIND_COUNT"] == j["DOME_SPRITE"]
    assert j["DOME_SPRITE"] + j["DOME_COUNT"] == j["BROKEN_SLOT_BASE"]
    assert j["BROKEN_SLOT_BASE"] + j["BROKEN_SLOT_COUNT"] \
        == j["BROKEN_SLOT_AFTER"]
    assert j["BROKEN_SLOT_AFTER"] == j["SHIP_SPRITE"]


def NOBJ():
    txt = open(MISSILES_H).read()
    nmis = _define_any(txt, "NMIS")
    nbul = _define_any(txt, "NBUL")
    return nmis + nbul


def MIS_COLS_MAX():
    return _define_any(open(MIS_GFX_H).read(), "MIS_COLS_MAX")


def NEXPL():
    return _define_any(open(MIS_GFX_H).read(), "NEXPL")


def _define_any(txt, name):
    m = re.search(r"#define\s+" + name + r"\s+(\d+)", txt)
    assert m, f"{name} not found"
    return int(m.group(1))


def test_overlay_count_equals_render_broken():
    """the map's BROKEN_SLOT_COUNT (145) is the generator's own slot span:
    render_broken starts its per-cell runs at BROKEN_SLOT_BASE (which it now
    takes from build/slots.json) and the art's pack ends at SLOT_AFTER."""
    import render_broken as rb  # noqa: E402

    j = load_json()
    base = j["BROKEN_SLOT_BASE"]
    assert rb._SLOT0 and rb._SLOT0[0] == base   # the pack starts at the map's base
    assert rb._SLOT0[-1] + rb._MSW[-1] - 1 <= j["BROKEN_SLOT_AFTER"] - 1
    # the generator's art-derived span equals the map's count
    assert rb.SLOT_AFTER - base == j["BROKEN_SLOT_COUNT"], (
        rb.SLOT_AFTER, base, j["BROKEN_SLOT_COUNT"])
    # and the ship really starts at the overlays' end (the runtime's
    # SHIP_SPRITE == BROKEN_SLOT_AFTER invariant)
    assert rb.SLOT_AFTER == j["SHIP_SPRITE"]
