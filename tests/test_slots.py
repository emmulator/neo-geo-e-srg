"""The one sprite slot map (M5 Task 1; stars retired by dome-scenery Task 4).

  test_slots.py   (host, pytest)

src/slots.h is the ONLY place slot numbers are defined; build/slots.json
(and build/slots.lua, for the MAME probes) are generated from it by the
Makefile. This test proves the map it produces:

  1. src/slots.h parses: every #define evaluates, and the generated
     build/slots.json equals a direct parse of the header;
  2. the ranges are contiguous, non-overlapping and in draw order (the
     ground lowest, the mountains next, the towns-and-forests band, the
     back props, then missiles behind, dome, broken overlays, the front
     props, ship, front missiles, explosions, radar, the initials ring and
     K2's one flying letter above it), every range starts where the
     previous one ended, and the last slot is <= 380;
  3. the map starts at slot 1 (GROUND_SPRITE), now that the stars'
     1..12 range is gone (dome-scenery Task 4 retired the star field) and
     the ground took the bottom (dome-scenery Task 5);
  4. every count in the map equals the art it describes:
     GROUND_COUNT = GROUND_COLS,
     MTN_COUNT = MTN_SHOWN (the mountain chain, 21 x 16 >= 320),
     BAND_COUNT = BAND_SHOWN (the band's chain, 21 x 16 >= 320),
     PROP_BACK_COUNT = PROP_BACK_SLOTS and PROP_FRONT_COUNT =
     PROP_FRONT_SLOTS (the two prop pools), MIS_BEHIND_COUNT = NOBJ x
     MIS_COLS_MAX, DOME_COUNT = DOME_COLS,
     SHIP_COUNT = SHIP_COLS, EXPL_COUNT = NEXPL x EXPL_COLS,
     RADAR_COUNT = 4 + 3 x (1 + 4) (the task's own number), and
     BROKEN_SLOT_COUNT equals tools/render_broken.py's computed overlay
     slot span (the "count from the generator").
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
GROUND_MAP_H = os.path.join(ROOT, "build", "ground_map.h")
BAND_MAP_H = os.path.join(ROOT, "build", "band_map.h")
CON_MAP_H = os.path.join(ROOT, "build", "console_map.h")
PROP_MAP_H = os.path.join(ROOT, "build", "props_map.h")
COLLAPSE_MAP_H = os.path.join(ROOT, "build", "collapse_map.h")

# the draw order (M5 Task 1, without the stars since dome-scenery Task 4,
# with the ground lowest since dome-scenery Task 5, the mountains right
# after the ground since dome-scenery Task 6, the towns-and-forests band
# right after the mountains since dome-scenery Task 17, the props right
# after the band since dome-scenery Task 12, and the console right after
# the ship since dome-scenery Task 7): each range's (name, count-name)
ORDER = [
    ("GROUND_SPRITE", "GROUND_COUNT"),
    ("MTN_SPRITE", "MTN_COUNT"),
    ("BAND_SPRITE", "BAND_COUNT"),
    ("PROP_SPRITE", "PROP_BACK_COUNT"),
    ("MIS_BEHIND_SPRITE", "MIS_BEHIND_COUNT"),
    ("SMOKE_BACK_SPRITE", "SMOKE_BACK_COUNT"),
    ("DOME_SPRITE", "DOME_COUNT"),
    ("BROKEN_SLOT_BASE", "BROKEN_SLOT_COUNT"),
    ("SHIP_SPRITE", "SHIP_COUNT"),
    ("PROP_FRONT_SPRITE", "PROP_FRONT_COUNT"),
    ("CON_SPRITE", "CON_COUNT"),
    ("MIS_FRONT_SPRITE", "MIS_FRONT_COUNT"),
    ("EXPL_SPRITE", "EXPL_COUNT"),
    ("RADAR_SPRITE", "RADAR_COUNT"),
    ("RING_SPRITE", "RING_COUNT"),
    ("FLY_SPRITE", "FLY_COUNT"),
]

LAST_SLOT_MAX = 380           # the hardware's 381 sprites

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout as lay  # noqa: E402  (dome size knob: DOME_COLS/ROWS)


def parse_slots_h():
    """evaluate the #defines in src/slots.h. Returns {name: value}."""
    defines = {"DOME_COLS": lay.d.DOME_COLS}   # slots.h includes dome_map.h
    for raw in open(SLOTS_H):
        line = raw.split("//")[0].split("/*")[0].strip()
        if not line:
            continue
        if line.startswith("#include"):
            continue                    # dome_map.h: DOME_COLS seeded above
        m = re.match(r"#ifndef\s+(\w+)", line)
        if m:
            continue                    # no override: the header's default
        if line.startswith("#endif"):
            continue
        m = re.match(r"#define\s+(\w+)\s+(.+)", line)
        if not m:
            continue
        name, expr = m.group(1), m.group(2).strip()
        # evaluate: substitute already-known names (longest first)
        for k in sorted(defines, key=len, reverse=True):
            expr = expr.replace(k, str(defines[k]))
        expr = expr.replace("(", " ( ").replace(")", " ) ")
        defines[name] = int(eval(expr, {"__builtins__": {}}, {}))
    defines.pop("DOME_COLS", None)          # the knob, not a slot
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
    h = parse_slots_h()                # the build's own header
    assert h == j, (h, j)


def test_the_stars_are_gone():
    """dome-scenery Task 4 retired the star field: no star slot, range or
    count may survive in the header or the generated map."""
    h = load_json()
    for name in ("STAR_SPRITE", "NSTARS", "STAR_TILE_BASE", "STARS_COUNT"):
        assert name not in h, f"{name} is still in the slot map: {h}"
    # ... and the map (both the header and the generated json) starts at
    # slot 1: the ground is the lowest sprite now (dome-scenery Task 5).
    assert h["GROUND_SPRITE"] == 1
    assert parse_slots_h()["GROUND_SPRITE"] == 1


def test_ground_is_below_every_other_sprite():
    """dome-scenery Task 5: the grass must be under everything, so its
    range is the FIRST in draw order and the missiles behind the dome
    start after it (a higher slot draws on top). Dome-scenery Task 6 put
    the mountains directly after the ground, so the grass is still first
    and the mountains are the second range."""
    j = load_json()
    assert j["GROUND_SPRITE"] == 1
    assert j["GROUND_COUNT"] == 20
    # every other range starts at or after the ground's end
    for name, count_name in ORDER[1:]:
        assert j[name] >= j["GROUND_SPRITE"] + j["GROUND_COUNT"], (
            f"{name} {j[name]} is inside the ground's range")
    assert j["MTN_SPRITE"] == j["GROUND_SPRITE"] + j["GROUND_COUNT"]
    assert j["BAND_SPRITE"] == j["MTN_SPRITE"] + j["MTN_COUNT"]
    assert j["PROP_SPRITE"] == j["BAND_SPRITE"] + j["BAND_COUNT"]


def test_the_mountains_are_right_after_the_ground_and_below_the_band():
    """dome-scenery Task 6: the mountain band draws over nothing but the
    grass and under everything else — the towns-and-forests band and the
    missiles behind the dome included. So its range is the second in draw
    order, starts at the ground's end, and ends exactly where the band
    begins."""
    j = load_json()
    assert j["MTN_COUNT"] == 21          # MTN_SHOWN: 21 x 16 >= 320
    assert j["MTN_SPRITE"] == j["GROUND_SPRITE"] + j["GROUND_COUNT"]
    assert j["MTN_SPRITE"] + j["MTN_COUNT"] == j["BAND_SPRITE"]
    # the mountains are the 2nd range, the ground the 1st
    names = [n for n, _ in ORDER]
    assert names.index("MTN_SPRITE") == 1
    # no other range starts inside the mountains' range
    for name, count_name in ORDER[2:]:
        assert j[name] >= j["MTN_SPRITE"] + j["MTN_COUNT"], (
            f"{name} {j[name]} is inside the mountains' range")


def test_the_band_is_right_after_the_mountains_and_below_the_props():
    """dome-scenery Task 17: the towns-and-forests band draws over the
    mountains and under every prop, so its range is the third in draw
    order, starts at the mountains' end, and ends exactly where the back
    props begin; BAND_COUNT equals BAND_SHOWN (the 21-column chain)."""
    j = load_json()
    assert j["BAND_COUNT"] == 21          # BAND_SHOWN: 21 x 16 >= 320
    assert j["BAND_SPRITE"] == j["MTN_SPRITE"] + j["MTN_COUNT"]
    assert j["BAND_SPRITE"] + j["BAND_COUNT"] == j["PROP_SPRITE"]
    names = [n for n, _ in ORDER]
    assert names.index("BAND_SPRITE") == names.index("MTN_SPRITE") + 1
    assert names.index("PROP_SPRITE") == names.index("BAND_SPRITE") + 1
    # nothing else starts inside the band's range
    for name, count_name in ORDER[names.index("BAND_SPRITE") + 1:]:
        assert j[name] >= j["BAND_SPRITE"] + j["BAND_COUNT"], (
            f"{name} {j[name]} is inside the band's range")


def test_the_back_props_are_right_after_the_band_and_below_the_missiles():
    """dome-scenery Tasks 12 and 15: the BACK props (every prop except the
    near one that passes in front of the dome) are drawn under everything
    but the ground, the mountains and the band. So their range is the
    fourth in draw order, starts at the band's end, and ends exactly where
    the behind-the-dome missiles begin; PROP_BACK_COUNT equals the
    generated build/props_map.h's PROP_BACK_SLOTS."""
    j = load_json()
    assert j["PROP_BACK_COUNT"] == _define(PROP_MAP_H, "PROP_BACK_SLOTS") == 56
    assert j["PROP_SPRITE"] == j["BAND_SPRITE"] + j["BAND_COUNT"]
    assert j["PROP_SPRITE"] + j["PROP_BACK_COUNT"] == j["MIS_BEHIND_SPRITE"]
    names = [n for n, _ in ORDER]
    assert names.index("PROP_SPRITE") == names.index("BAND_SPRITE") + 1
    assert names.index("MIS_BEHIND_SPRITE") == names.index("PROP_SPRITE") + 1
    # nothing else starts inside the back props' range
    for name, count_name in ORDER[names.index("PROP_SPRITE") + 1:]:
        assert j[name] >= j["PROP_SPRITE"] + j["PROP_BACK_COUNT"], (
            f"{name} {j[name]} is inside the back props' range")


def test_the_front_props_are_right_after_the_ship_and_below_the_console():
    """dome-scenery Task 15: the FRONT pool (the near prop that covers the
    dome on screen) draws over the dome and its broken overlays; since 10-26
    also over the ship (wherever the two overlap the prop is nearer the
    camera), and under the console, the front missiles, the explosions and
    the radar. So the ship is right after the overlays and the front pool
    right after the ship; PROP_FRONT_COUNT equals build/props_map.h's
    PROP_FRONT_SLOTS."""
    j = load_json()
    assert j["PROP_FRONT_COUNT"] == _define(PROP_MAP_H, "PROP_FRONT_SLOTS") == 6
    assert j["SHIP_SPRITE"] == j["BROKEN_SLOT_AFTER"]
    assert j["SHIP_SPRITE"] + j["SHIP_COUNT"] == j["PROP_FRONT_SPRITE"]
    names = [n for n, _ in ORDER]
    assert names.index("SHIP_SPRITE") == names.index("BROKEN_SLOT_BASE") + 1
    assert names.index("PROP_FRONT_SPRITE") == names.index("SHIP_SPRITE") + 1
    # nothing else starts inside the front props' range
    for name, count_name in ORDER[names.index("PROP_FRONT_SPRITE") + 1:]:
        assert j[name] >= j["PROP_FRONT_SPRITE"] + j["PROP_FRONT_COUNT"], (
            f"{name} {j[name]} is inside the front props' range")


def test_the_console_is_right_after_the_front_props_and_below_the_front_missiles():
    """dome-scenery Task 7: the console goes right after the ship (since 10-26
    right after the front props, which follow the ship) and before
    the front missiles, so it draws over the grass, the mountains, the dome,
    its overlays and the ship, and UNDER the front missiles, the explosions
    and the radar (missiles fly in from in front of the camera, across the
    bottom of the screen; the console must never hide one)."""
    j = load_json()
    assert j["CON_COUNT"] == 20          # CON_COLS: the panel's columns
    assert j["CON_SPRITE"] == j["PROP_FRONT_SPRITE"] + j["PROP_FRONT_COUNT"]
    assert j["CON_SPRITE"] + j["CON_COUNT"] == j["MIS_FRONT_SPRITE"]
    # the console is the range right after the ship's in draw order
    names = [n for n, _ in ORDER]
    assert names.index("CON_SPRITE") == names.index("PROP_FRONT_SPRITE") + 1
    assert names.index("MIS_FRONT_SPRITE") == names.index("CON_SPRITE") + 1
    # nothing else starts inside the console's range
    for name, count_name in ORDER[names.index("CON_SPRITE") + 1:]:
        assert j[name] >= j["CON_SPRITE"] + j["CON_COUNT"], (
            f"{name} {j[name]} is inside the console's range")


def test_ranges_ordered_contiguous_and_in_bounds():
    j = load_json()
    rng = ranges(j)
    first = rng[0][1]
    last = rng[-1][2] - 1
    assert first == 1, f"the map starts at slot {first}, want 1"
    assert last <= LAST_SLOT_MAX, f"last slot {last} > {LAST_SLOT_MAX}"
    # starts ascend, nothing overlaps
    for (n1, s1, a1), (n2, s2, a2) in zip(rng, rng[1:]):
        assert a1 <= s2, f"{n1}..{a1 - 1} overlaps {n2} (starts {s2})"
        assert s1 < s2, "order"
    # the plan's table, checked against the map's own numbers
    assert j["DOME_COUNT"] == lay.d.DOME_COLS
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
    assert j["GROUND_COUNT"] == _define(GROUND_MAP_H, "GROUND_COLS")
    assert j["MIS_BEHIND_COUNT"] == j["MIS_FRONT_COUNT"] \
        == NOBJ() * MIS_COLS_MAX()
    assert j["DOME_COUNT"] == _define(DOME_MAP_H, "DOME_COLS")
    assert j["SHIP_COUNT"] == _define(SHIP_MAP_H, "SHIP_COLS")
    assert j["CON_COUNT"] == _define(CON_MAP_H, "CON_COLS")
    assert j["EXPL_COUNT"] == NEXPL() * _define(MISSILE_MAP_H, "EXPL_COLS")
    import mountains_model as mm  # noqa: E402 (MTN_SHOWN: 21)
    import band_model as bm  # noqa: E402 (BAND_SHOWN: 21)
    assert j["MTN_COUNT"] == mm.MTN_SHOWN == 21
    assert mm.MTN_SHOWN * 16 >= mm.SCREEN_W, (
        "the mountain chain must cover the screen at any 16-px scroll phase")
    assert j["BAND_COUNT"] == bm.BAND_SHOWN == 21
    assert bm.BAND_SHOWN * 16 >= bm.SCREEN_W, (
        "the band chain must cover the screen at any 16-px scroll phase")
    # the band's panorama size and chain come from its one source
    assert bm.BAND_COLS == _define(BAND_MAP_H, "BAND_COLS") == 48
    assert bm.BAND_ROWS == _define(BAND_MAP_H, "BAND_ROWS") == 2
    assert j["GROUND_SPRITE"] + j["GROUND_COUNT"] == j["MTN_SPRITE"]
    assert j["MTN_SPRITE"] + j["MTN_COUNT"] == j["BAND_SPRITE"]
    assert j["BAND_SPRITE"] + j["BAND_COUNT"] == j["PROP_SPRITE"]
    assert j["PROP_SPRITE"] + j["PROP_BACK_COUNT"] == j["MIS_BEHIND_SPRITE"]
    assert j["MIS_BEHIND_SPRITE"] + j["MIS_BEHIND_COUNT"] \
        == j["SMOKE_BACK_SPRITE"]
    assert j["SMOKE_BACK_SPRITE"] + j["SMOKE_BACK_COUNT"] == j["DOME_SPRITE"]
    assert j["DOME_SPRITE"] + j["DOME_COUNT"] == j["BROKEN_SLOT_BASE"]
    assert j["BROKEN_SLOT_BASE"] + j["BROKEN_SLOT_COUNT"] \
        == j["BROKEN_SLOT_AFTER"]
    assert j["BROKEN_SLOT_AFTER"] == j["SHIP_SPRITE"]
    assert j["SHIP_SPRITE"] + j["SHIP_COUNT"] == j["PROP_FRONT_SPRITE"]


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


def test_the_flying_letter_is_one_slot_above_the_ring():
    """K2: the ring is the highest group (320..357, 38 slots) and the one
    flying-letter copy takes the next slot (358), so it draws over the
    ring's front letter; the map still ends within the hardware's 381
    sprites."""
    j = load_json()
    assert j["FLY_COUNT"] == 1
    assert j["RING_SPRITE"] == j["RADAR_SPRITE"] + j["RADAR_COUNT"] == 326
    assert j["FLY_SPRITE"] == j["RING_SPRITE"] + j["RING_COUNT"] == 364
    names = [n for n, _ in ORDER]
    assert names.index("RING_SPRITE") == names.index("RADAR_SPRITE") + 1
    assert names.index("FLY_SPRITE") == names.index("RING_SPRITE") + 1
    # above the ring's top slot (the front letter/pointer), not inside it
    assert j["FLY_SPRITE"] > j["RING_SPRITE"] + j["RING_COUNT"] - 1
    assert j["FLY_SPRITE"] <= LAST_SLOT_MAX
    assert parse_slots_h()["FLY_SPRITE"] == 364


def test_overlay_count_equals_render_broken():
    """the map's BROKEN_SLOT_COUNT is the generator's own slot span:
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
    # the ship starts at the overlays' end and the front prop pool right
    # after it (Task 15; the ship moved under the front props on 10-26)
    assert rb.SLOT_AFTER == j["SHIP_SPRITE"]
    assert j["SHIP_SPRITE"] + j["SHIP_COUNT"] == j["PROP_FRONT_SPRITE"]


def _all_defines(path):
    """evaluate a generated header's plain-number #defines, in order (the
    names before an expression are substituted into it)."""
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


def test_the_collapse_sub_map_fits_the_overlay_range():
    """Task C2: the collapse's sprites share the broken overlays' range,
    in draw order (smoke, fragments, fireball, puffs — a higher slot draws
    on top), and the last puff ends at or before the overlays' end, so the
    main map does not move. Each count equals the collapse header's art:
    NPLUMES x SMOKE_COLS, NFRAGS, FIRE_COLS, and 3 puff pairs x PUFF_COLS
    (at most 3 puffs at once, each 2 columns)."""
    j = load_json()
    c = _all_defines(COLLAPSE_MAP_H)
    assert j["COLLAPSE_SMOKE_COUNT"] == 3 * c["SMOKE_COLS"] == 6
    assert j["SMOKE_BACK_COUNT"] == 3 * c["SMOKE_COLS"] == 6
    assert c["NPLUMES"] * c["SMOKE_COLS"] \
        == j["SMOKE_BACK_COUNT"] + j["COLLAPSE_SMOKE_COUNT"]
    assert j["COLLAPSE_FRAG_COUNT"] == c["NFRAGS"] == 49
    assert j["COLLAPSE_FIRE_COUNT"] == c["FIRE_COLS"] == 12
    assert j["COLLAPSE_PUFF_COUNT"] == 3 * c["PUFF_COLS"] == 6
    assert j["COLLAPSE_SMOKE_SPRITE"] == j["BROKEN_SLOT_BASE"]
    assert j["SMOKE_BACK_SPRITE"] + j["SMOKE_BACK_COUNT"] == j["DOME_SPRITE"]
    assert (j["COLLAPSE_FRAG_SPRITE"]
            == j["COLLAPSE_SMOKE_SPRITE"] + j["COLLAPSE_SMOKE_COUNT"])
    assert (j["COLLAPSE_FIRE_SPRITE"]
            == j["COLLAPSE_FRAG_SPRITE"] + j["COLLAPSE_FRAG_COUNT"])
    assert (j["COLLAPSE_PUFF_SPRITE"]
            == j["COLLAPSE_FIRE_SPRITE"] + j["COLLAPSE_FIRE_COUNT"])
    assert (j["COLLAPSE_PUFF_SPRITE"] + j["COLLAPSE_PUFF_COUNT"]
            <= j["BROKEN_SLOT_AFTER"])
    # the sub-map is inside the overlay range and in draw order
    starts = [j["COLLAPSE_SMOKE_SPRITE"], j["COLLAPSE_FRAG_SPRITE"],
              j["COLLAPSE_FIRE_SPRITE"], j["COLLAPSE_PUFF_SPRITE"]]
    assert starts[0] == j["BROKEN_SLOT_BASE"]
    assert starts == sorted(starts) and len(set(starts)) == 4
    for a, nxt in zip(starts, starts[1:]):
        assert a < nxt
    # the main map does not move: the ship (since 10-26; the front prop
    # pool before) still starts at the overlays' end, and the overlays
    # still end where they did.
    assert j["SHIP_SPRITE"] == j["BROKEN_SLOT_AFTER"]
    assert j["BROKEN_SLOT_BASE"] + j["BROKEN_SLOT_COUNT"] \
        == j["BROKEN_SLOT_AFTER"]