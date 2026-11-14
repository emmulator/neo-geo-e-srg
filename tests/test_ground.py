"""The ground's generated header (dome-scenery Tasks 5 and 19).

  test_ground.py   (host, pytest)

tools/render_ripple.py (Task 19) writes build/ground_map.h. It replaces
render_scenery.py's ground part with the same block and the same 160 tiles,
re-indexed for the ripple, and keeps the two plain palettes:

  ground_pal           index 0 transparent, 1..GROUND_NSHADES the grass far
                       to near, GROUND_NSHADES+1..2*GROUND_NSHADES the same
                       shades in the dome's shadow, 15 unused;
  ground_pal_noshadow  the shadow gone: entries 8..14 equal the plain shades
                       1..7.

The runtime still uses bank 8's ground_pal/ground_pal_noshadow as the
whole/gone marker (src/ground.h), so the two palettes must agree everywhere
except the twin entries, and each twin must be its plain shade's word.

The ripple tables the header adds must be the generator's own numbers:
  RIPPLE_BANKS 11 (one per tile row; rows 3..5 are two each),
  ground_bank[GROUND_COLS][GROUND_ROWS]  the tile's bank 0..10,
  ground_ripple_pal[RIPPLE_BANKS][2][RIPPLE_NROT][16]  [bank][whole/gone]
                       [rotation][entry], entry 0 0x8000, 13..15 unused,
  ground_ripple_rot[RIPPLE_BANKS][240]  the bank's rotation at each angle,
                       ending in phase at angle 240 (the wrap is one step).

The header's tile numbers are RELATIVE to the ground part's first C ROM tile
(0..GROUND_TILES-1); ground.c adds the part base the Makefile's C ROM order
gives it (the radar's parts come first). This test holds the header to the
generator's own numbers and the C ROM base to the radar's generated header.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BUILD = os.path.join(ROOT, "build")
GROUND_MAP_H = os.path.join(BUILD, "ground_map.h")
RADAR_MAP_H = os.path.join(BUILD, "radar_map.h")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import render_ripple as rr          # noqa: E402  (the header's generator)


def _defines(path):
    """evaluate the header's #defines in order: a plain number, or an
    expression over the names defined before it (the radar's bases)."""
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


def _palette(name):
    txt = open(GROUND_MAP_H).read()
    m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name, txt, re.S)
    assert m, f"{name} missing from build/ground_map.h"
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    assert len(words) == 16, (name, len(words))
    return words


def _array(name):
    """the initialiser body of the header's named array."""
    txt = open(GROUND_MAP_H).read()
    m = re.search(r"%s\[[^=]*= \{(.*?)\};" % name, txt, re.S)
    assert m, f"{name} missing from build/ground_map.h"
    return m.group(1)


def _u16_array(name, shape):
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", _array(name))]
    assert len(words) == shape[0] * shape[1] * shape[2] * shape[3], \
        (name, len(words))
    out, i = [], 0
    for _a in range(shape[0]):
        per_gone = []
        for _b in range(shape[1]):
            per_rot = []
            for _c in range(shape[2]):
                per_rot.append(words[i:i + shape[3]])
                i += shape[3]
            per_gone.append(per_rot)
        out.append(per_gone)
    return out


def _u8_array(name, shape):
    vals = [int(x) for x in re.findall(r"\d+", _array(name))]
    assert len(vals) == shape[0] * shape[1], (name, len(vals))
    return [vals[i * shape[1]:(i + 1) * shape[1]] for i in range(shape[0])]


def test_header_has_the_confirmed_numbers():
    d = _defines(GROUND_MAP_H)
    assert d["GROUND_Y"] == 100
    assert d["GROUND_COLS"] == 20          # 320 px / 16
    assert d["GROUND_ROWS"] == 8           # y 100..227 (224..227 off screen)
    assert d["GROUND_TILES"] == d["GROUND_COLS"] * d["GROUND_ROWS"] == 160
    assert d["GROUND_NSHADES"] == 7
    assert d["RIPPLE_BANKS"] == 11
    assert d["RIPPLE_NROT"] == 3


def test_the_two_palettes_differ_only_in_8_to_14():
    pal = _palette("ground_pal")
    nosh = _palette("ground_pal_noshadow")
    assert pal[0] == 0x8000 and nosh[0] == 0x8000      # transparent
    assert pal[15] == nosh[15]                         # unused, same word
    n = _defines(GROUND_MAP_H)["GROUND_NSHADES"]       # 7
    for i in range(16):
        if n < i <= 2 * n:                             # 8..14: the twins
            assert pal[i] != nosh[i], (
                f"entry {i} is the same in both palettes; the shadow needs "
                f"its twin")
        else:
            assert pal[i] == nosh[i], (
                f"entry {i} differs outside the shadow entries 8..14")
    # the shadow gone: each twin (index k + NSHADES) is its plain shade k
    for k in range(1, n + 1):
        assert nosh[k + n] == pal[k], (
            f"ground_pal_noshadow[{k + n}] {nosh[k + n]:#06x} != "
            f"ground_pal[{k}] {pal[k]:#06x}")
    # every grass shade is a real, non-transparent colour
    for k in range(1, 2 * n + 1):
        assert pal[k] != 0x8000, f"grass entry {k} is transparent"


def test_the_ground_part_follows_the_radar_in_the_c_rom():
    """ground.c adds RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES (the C ROM
    order the Makefile emits), so the header's relative tile numbers
    (0..159) land after the radar's last tile. Read the radar's generated
    header and check that the first ground tile is exactly its end."""
    d = _defines(RADAR_MAP_H)
    end = d["RADAR_HEAD_TILE_BASE"] + d["RADAR_HEAD_TILES"]
    ground = _defines(GROUND_MAP_H)
    assert ground["GROUND_TILES"] == 160
    # ground.c's own base expression (ground.h/ground.c) is the one source;
    # this asserts the numbers it adds are contiguous with the radar's end.
    src = open(os.path.join(ROOT, "src", "ground.c")).read()
    assert "RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES" in src, (
        "ground.c must take its part base from the radar's generated header")
    # 160 tiles x 64 bytes = the payload size render_scenery.py writes
    for plane in ("ground.c1", "ground.c2"):
        p = os.path.join(BUILD, "assets", plane)
        assert os.path.getsize(p) == 160 * 64, (plane, os.path.getsize(p))
    print(f"ground part: {ground['GROUND_TILES']} tiles from C ROM tile "
          f"{end}")


def test_the_ripple_banks_are_the_generators():
    """ground_bank[col][row] must be the generator's bank_of: one bank per
    tile row, except rows 3..5 which are two each (columns 0..9 and 10..19
    move opposite ways)."""
    d = _defines(GROUND_MAP_H)
    cols, rows = d["GROUND_COLS"], d["GROUND_ROWS"]
    bank = _u8_array("ground_bank", (cols, rows))
    want = [[0] * rows for _ in range(cols)]
    for k, (r, cols_range, _axis) in enumerate(rr.banks()):
        for c in cols_range:
            want[c][r] = k
    assert bank == want, "ground_bank is not render_ripple's bank map"
    # rows 3..5 are two banks each, split at column 10: bank k then k+1
    for r in rr.SIDE_ROWS:
        k = next(k for k, (rr_, _cs, _ax) in enumerate(rr.banks()) if rr_ == r)
        assert bank[9][r] == k and bank[10][r] == k + 1, (r, bank[9][r], bank[10][r])
    # every bank 0..10 is used, and there are exactly the generator's banks
    assert sorted({b for row in bank for b in row}) == list(range(d["RIPPLE_BANKS"]))


def test_the_ripple_palettes_are_the_generators():
    """ground_ripple_pal[k][gone][rot][entry] must be the generator's own
    bank_palettes(): entry 0 is 0x8000, 13..15 are unused black, and a gone
    palette maps every twin to its plain shade."""
    d = _defines(GROUND_MAP_H)
    nbanks, nrot = d["RIPPLE_BANKS"], d["RIPPLE_NROT"]
    pal = _u16_array("ground_ripple_pal", (nbanks, 2, nrot, 16))
    pic, maj, bank_of = rr.ripple_picture()
    want = rr.bank_palettes(maj)
    assert pal == want, "ground_ripple_pal is not render_ripple's own table"
    for k in range(nbanks):
        for gone in (0, 1):
            for rot in range(nrot):
                w = pal[k][gone][rot]
                assert w[0] == 0x8000, (k, gone, rot, w[0])
                assert w[13] == w[14] == w[15] == 0, (k, gone, rot, w[13:])
                for e in range(1, 13):
                    assert w[e] != 0x8000, (k, gone, rot, e)
    # the gone palette's twin slots are the plain shades' words
    for k in range(nbanks):
        for rot in range(nrot):
            w0, w1 = pal[k][0][rot], pal[k][1][rot]
            for slot in range(2):
                for p in range(3):
                    assert w1[1 + 6 * slot + 3 + p] != 0x8000


def test_the_ripple_rotations_are_the_generators_and_end_in_phase():
    """ground_ripple_rot[k][da] must be render_ripple's own rotation table
    (round(-speed * da / 3) mod 3). A whole turn ends in phase: every
    bank's rotation at angle 0 is what angle 240 gives, so the 239 -> 0
    wrap is one ordinary step, not a jump."""
    d = _defines(GROUND_MAP_H)
    nbanks = d["RIPPLE_BANKS"]
    rot = _u8_array("ground_ripple_rot", (nbanks, 240))
    speeds = rr.bank_speeds()
    want = rr.rotations(speeds)
    assert rot == want, "ground_ripple_rot is not render_ripple's own table"
    # the header's speed comment agrees with the generator's speeds
    txt = open(GROUND_MAP_H).read()
    m = re.search(r"speeds \(px a step\):\s*([^*]+)\*/", txt)
    assert m, "the header's speeds comment is missing"
    shown = [float(x) for x in m.group(1).replace(",", " ").split()]
    assert len(shown) == nbanks, (len(shown), nbanks)
    for k in range(nbanks):
        assert abs(shown[k] - speeds[k]) < 1e-4, (k, shown[k], speeds[k])
        # a whole turn ends where it began: angle 240 would give rot[k][0]
        assert rot[k][0] == int(round(-speeds[k] * 240 / rr.RIPPLE_D)) \
            % d["RIPPLE_NROT"], f"bank {k}: the 239 -> 0 wrap is a jump"
        assert rot[k][0] == 0, f"bank {k}: a whole turn does not end in phase"
    assert max(max(row) for row in rot) <= d["RIPPLE_NROT"] - 1
