"""Reference model of the props' layout (dome-scenery Tasks 11, 14 and 15),
built from build/props_map.h and tools/render_props.py's drawn() — never
from the C.

The props are the 22 trees and rocks of tools/render_props.py (the
orchestrator's art). For a dome angle da:

  * the visible props are those with prop_se[i][da] != 0. A visible prop
    whose prop_front[i][da] is 1 goes to the FRONT pool (over the dome),
    every other visible prop to the BACK pool; each pool is ordered by foot
    y prop_y[i][da], smallest first (far first), ties to the lower index i;
  * prop i's LOD is the smallest l with prop_lod_ppu[l] >= se, its picture
    is prop_tree_pic or prop_rock_pic[shape][l], k = se / ppu,
    hz = round(16 k) - 1 (at least 0), v = round(256 k) - 1 (0..255), and
    the picture's top-left is (x - round(ax k), y - round(ay k)); column c
    sits at left + c (hz + 1);
  * each column's words are SCB2 (hz << 8) | v, SCB3 ((496 - top) << 7) |
    rows, SCB4 ((col_x & 0x1ff) << 7), and the first SCB1 tile
    first + c * rows (relative to the props part);
  * each pool's unused slots have shown 0 and SCB3 0.

Task 14 adds the dome's shadow: a shown prop's variant is 1 when the dome
is drawn whole AND prop_dark[i][da] is 1, else 0; its bank is
prop_pal[i][variant], with entries 1 and 13 from prop_shadow[variant][y]
(y = the foot's row prop_y[i][da] clamped to 0..223). bank() returns those
16 words; dark_props() lists the shown props whose variant is 1.

The model's maximum slots used per pool and its worst props-per-scanline
(over both pools) are held to the header's PROP_BACK_SLOTS,
PROP_FRONT_SLOTS and PROP_WORST_LINE by tests/test_props.py.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import render_props as rp  # noqa: E402  (the art's drawn() and props())

HEADER = os.path.join(ROOT, "build", "props_map.h")


def _defines(path=HEADER):
    """evaluate a generated header's #defines in order."""
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
            pass
    return out


_TXT = open(HEADER).read()
_D = _defines()


def _rows(name):
    """a [NPROPS][PROP_NDA] array's rows as int lists."""
    m = re.search(r"static const (?:u8|u16|s16) %s\[NPROPS\]\[PROP_NDA\] = "
                  r"\{(.*?)\n\};" % name, _TXT, re.S)
    assert m, name
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip().rstrip(",").strip()
        if line.startswith("{"):
            rows.append([int(x) for x in line.strip("{}").split(",")])
    assert len(rows) == _D["NPROPS"], (name, len(rows))
    return rows


def _row(name):
    """a [NPROPS] array as an int list."""
    m = re.search(r"static const u8 %s\[NPROPS\] = \{([^}]*)\};" % name,
                  _TXT)
    assert m, name
    out = [int(x) for x in m.group(1).split(",") if x.strip()]
    assert len(out) == _D["NPROPS"], (name, len(out))
    return out


def _pics(name, nshapes):
    """a [nshapes][PROP_NLOD] picture table as (cols, rows, first, ax, ay)."""
    m = re.search(r"static const prop_pic_t %s\[%d\]\[PROP_NLOD\] = "
                  r"\{(.*?)\n\};" % (name, nshapes), _TXT, re.S)
    assert m, name
    vals = [tuple(int(x) for x in v) for v in re.findall(
        r"\{(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\}", m.group(1))]
    nl = _D["PROP_NLOD"]
    assert len(vals) == nshapes * nl, (name, len(vals))
    return [vals[k * nl:(k + 1) * nl] for k in range(nshapes)]


NPROPS = _D["NPROPS"]
NDA = _D["PROP_NDA"]
NLOD = _D["PROP_NLOD"]
SLOTS = _D["PROP_SLOTS"]
BACK_SLOTS = _D["PROP_BACK_SLOTS"]
FRONT_SLOTS = _D["PROP_FRONT_SLOTS"]
WORST_LINE = _D["PROP_WORST_LINE"]
PROP_TILES = _D["PROP_TILES"]
LODS = [int(x) for x in re.search(
    r"prop_lod_ppu\[PROP_NLOD\] = \{([^}]*)\}", _TXT).group(1).split(",")]
assert len(LODS) == NLOD, LODS

KIND = _row("prop_kind")
SHAPE = _row("prop_shape")
X = _rows("prop_x")
Y = _rows("prop_y")
SE = _rows("prop_se")
DARK = _rows("prop_dark")
FRONT = _rows("prop_front")

PICS_HEADER = {}
for _kind, _nshapes, _name in ((0, _D["PROP_NTREES"], "prop_tree_pic"),
                               (1, _D["PROP_NROCKS"], "prop_rock_pic")):
    _t = _pics(_name, _nshapes)
    for _s in range(_nshapes):
        for _l in range(NLOD):
            PICS_HEADER[(_kind, _s, _l)] = _t[_s][_l]

# the generator's own pictures and props, only for the cross-checks in
# tests/test_props.py (the layout below never reads them)
PICS = rp.pictures()
OBJS = rp.props()
SCREEN_H = rp.SCREEN_H
TILE = rp.TILE


def _pal():
    """the header's prop_pal[NPROPS][2][16] as per-prop [lit, dark] banks."""
    m = re.search(r"static const u16 prop_pal\[NPROPS\]\[2\]\[16\] = "
                  r"\{(.*?)\n\};", _TXT, re.S)
    assert m, "prop_pal"
    rows = []
    for line in m.group(1).splitlines():
        words = re.findall(r"0x[0-9a-fA-F]{4}", line)
        if not words:
            continue
        assert len(words) == 32, (len(words), line[:60])
        rows.append([[int(w, 16) for w in words[k * 16:(k + 1) * 16]]
                     for k in range(2)])
    assert len(rows) == NPROPS, (len(rows), NPROPS)
    return rows


def _shadow():
    """the header's prop_shadow[2][224][2] as [lit, dark] lists of
    (entry1, entry13) word pairs."""
    m = re.search(r"static const u16 prop_shadow\[2\]\[224\]\[2\] = "
                  r"\{(.*?)\n\};", _TXT, re.S)
    assert m, "prop_shadow"
    pairs = [(int(a, 16), int(b, 16)) for a, b in
             re.findall(r"\{(0x[0-9a-fA-F]{4}),(0x[0-9a-fA-F]{4})\}",
                        m.group(1))]
    assert len(pairs) == 2 * SCREEN_H, (len(pairs), 2 * SCREEN_H)
    return [pairs[:SCREEN_H], pairs[SCREEN_H:]]


PAL = _pal()
SHADOW = _shadow()


def variant(i, da, dome_whole=1):
    """a shown prop's palette variant: 1 only while the dome is whole and
    prop_dark[i][da] says its foot is in the dome's shadow."""
    return 1 if dome_whole and DARK[i][da] else 0


def bank(i, da, dome_whole=1):
    """the 16 words prop i's palette bank holds at da: prop_pal[i][variant]
    with entries 1 and 13 from prop_shadow[variant][foot row] (clamped to
    0..223)."""
    d = variant(i, da, dome_whole)
    words = list(PAL[i][d])
    y = max(0, min(SCREEN_H - 1, Y[i][da]))
    words[1], words[13] = SHADOW[d][y]
    return words


def dark_props(da, dome_whole=1):
    """the shown props whose variant is 1 at da."""
    return [i for i in range(NPROPS)
            if SE[i][da] and variant(i, da, dome_whole)]


def lod_of(se):
    """the smallest l with prop_lod_ppu[l] >= se."""
    for l in range(NLOD):
        if LODS[l] >= se:
            return l
    return NLOD - 1


def visible(da):
    """(foot y, prop index) of ALL the visible props, far first, ties lower
    i — both pools together (the worst-line census is over both)."""
    out = [(Y[i][da], i) for i in range(NPROPS) if SE[i][da] != 0]
    out.sort()                      # tuple order: y, then i (lower first)
    return out


def _pool(da, front):
    """the visible props of one pool, far first, ties lower i."""
    out = [(Y[i][da], i) for i in range(NPROPS)
           if SE[i][da] != 0 and FRONT[i][da] == front]
    out.sort()
    return out


def _slots_of(da, front, cap):
    """one pool's cap slots at da."""
    slots = []
    for _, i in _pool(da, front):
        se = SE[i][da]
        lod = lod_of(se)
        ppu = LODS[lod]
        cols, rows, first, ax, ay = PICS_HEADER[(KIND[i], SHAPE[i], lod)]
        k = se / ppu
        hz = max(0, int(round(16 * k)) - 1)
        v = min(255, max(0, int(round(256 * k)) - 1))
        left = X[i][da] - int(round(ax * k))
        top = Y[i][da] - int(round(ay * k))
        for c in range(cols):
            col_x = left + c * (hz + 1)
            slots.append((1, i, lod, c, (hz << 8) | v,
                          ((496 - top) << 7) | rows,
                          ((col_x & 0x1ff) << 7), first + c * rows))
    assert len(slots) <= cap, (da, front, len(slots), cap)
    slots.extend([(0, 0, 0, 0, 0, 0, 0, 0)] * (cap - len(slots)))
    return slots


def layout(da):
    """(back, front): each pool's slots' (shown, prop, lod, col, scb2, scb3,
    scb4, tile) at da."""
    return _slots_of(da, 0, BACK_SLOTS), _slots_of(da, 1, FRONT_SLOTS)


def max_slots():
    """(back, front): the most sprite columns each pool uses at once."""
    back = front = 0
    for da in range(NDA):
        b, f = layout(da)
        back = max(back, sum(1 for s in b if s[0]))
        front = max(front, sum(1 for s in f if s[0]))
    return back, front


def worst_line():
    """the most prop columns on one scanline, over every angle (the
    generator's own per-line census: every drawn column counts, even one
    off the screen's side)."""
    worst = 0
    for da in range(NDA):
        lines = [0] * SCREEN_H
        for _, i in visible(da):
            se = SE[i][da]
            lod = lod_of(se)
            ppu = LODS[lod]
            cols, rows, _first, _ax, ay = PICS_HEADER[(KIND[i], SHAPE[i], lod)]
            k = se / ppu
            v = min(255, max(0, int(round(256 * k)) - 1))
            top = Y[i][da] - int(round(ay * k))
            bottom = top + int(rows * TILE * (v + 1) / 256) - 1
            for yy in range(max(0, top), min(SCREEN_H, bottom + 1)):
                lines[yy] += cols
        worst = max(worst, max(lines))
    return worst
