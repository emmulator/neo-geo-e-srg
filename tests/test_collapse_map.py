"""The collapse's generated part (the collapse redo's Task C1).

  test_collapse_map.py   (host, pytest)

tools/render_collapse.py writes build/collapse_map.h and the collapse part's
c1/c2 payloads. Tasks C1/V1/V2 use the ruin's numbers:

  RUIN_COLS x RUIN_ROWS   the ruin picture's 16-px columns and tile rows
                          (drawn in the dome's box from RUIN_TOP down);
  RUIN_TOP                the ruin's first pixel row below the dome box's
                          top: the box's top tile row is empty in every
                          view, so V2 drops it and draws the ruin one tile
                          row shorter, starting 16 px down the box;
  RUIN_VIEWS              the ruin's 48 views: scene step a shows view
                          a % RUIN_VIEWS, as the dome's columns do;
  COLLAPSE_TILES          the part's tile count (the rest of the header's
                          tables are for Tasks C2-C4/V1);
  ruin_tile[v][c][r]      the SCB1 tile numbers RELATIVE to the part's first
                          C ROM tile (0 is the part's own blank tile);
  ruin_pal[16]            the ruin's one palette (entry 0 transparent).

The host test proves the header and the payloads agree with the C ROM the
cart will fetch:

  1. RUIN_COLS equals the dome's DOME_COLS and RUIN_ROWS equals DOME_ROWS
     minus the dropped top row (RUIN_TOP / 16 = 1) from build/dome_map.h
     (the ruin stands in the dome's own 8 columns, one row shorter);
  2. COLLAPSE_TILES * 64 equals the size of both collapse.c1 and collapse.c2
     (one 64-byte tile per plane);
  3. RUIN_VIEWS is 48, ruin_pal[0] is 0x8000 (transparent), and every one of
     the 48 views' ruin_tile entries is a real tile number below
     COLLAPSE_TILES;
  4. COLLAPSE_WORST_LINE <= 92 (the generator's sprite-per-scanline budget,
     measured against the collapse's baseline).

The absolute tile numbers the runtime writes are COLLAPSE_TILE_BASE +
ruin_tile[c][r]; the boot-test checker re-derives that base from the parts'
generated headers (the collapse part is LAST after the band).
"""
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BUILD = os.path.join(ROOT, "build")
COLLAPSE_MAP_H = os.path.join(BUILD, "collapse_map.h")
DOME_MAP_H = os.path.join(BUILD, "dome_map.h")
C1 = os.path.join(BUILD, "assets", "collapse.c1")
C2 = os.path.join(BUILD, "assets", "collapse.c2")
LINE_LIMIT = 92


def _defines(path):
    """the header's plain-number #defines (the collapse header's are all
    plain; expressions are substituted from the names before them)."""
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
            pass                        # a comment or an unparsed expression
    return out


def _palette(name):
    txt = open(COLLAPSE_MAP_H).read()
    m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name, txt, re.S)
    assert m, f"{name} missing from build/collapse_map.h"
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    assert len(words) == 16, (name, len(words))
    return words


def _ruin_tiles(views, cols, rows):
    txt = open(COLLAPSE_MAP_H).read()
    m = re.search(r"static const u16 ruin_tile\[%d\]\[%d\]\[%d\] = \{(.*?)\};"
                  % (views, cols, rows), txt, re.S)
    assert m, "ruin_tile missing from build/collapse_map.h"
    vals = [int(x) for x in re.findall(r"\d+", m.group(1))]
    assert len(vals) == views * cols * rows, (len(vals), views * cols * rows)
    out = []
    for v in range(views):
        base = v * cols * rows
        out.append([vals[base + c * rows:base + (c + 1) * rows]
                    for c in range(cols)])
    return out


def test_the_ruin_is_the_domes_box_below_its_empty_top_row():
    d = _defines(COLLAPSE_MAP_H)
    dome = _defines(DOME_MAP_H)
    assert d["RUIN_COLS"] == dome["DOME_COLS"], (
        f"RUIN_COLS {d['RUIN_COLS']} != DOME_COLS {dome['DOME_COLS']}")
    assert d["RUIN_TOP"] == 16, (
        f"RUIN_TOP {d.get('RUIN_TOP')} != one 16-px tile row")
    assert d["RUIN_ROWS"] == dome["DOME_ROWS"] - d["RUIN_TOP"] // 16, (
        f"RUIN_ROWS {d['RUIN_ROWS']} != DOME_ROWS {dome['DOME_ROWS']} - "
        f"RUIN_TOP {d['RUIN_TOP']} / 16")
    assert d["RUIN_ROWS"] == 5, d["RUIN_ROWS"]
    print(f"ruin {d['RUIN_COLS']}x{d['RUIN_ROWS']} starts {d['RUIN_TOP']} px "
          f"below the dome's {dome['DOME_COLS']}x{dome['DOME_ROWS']} box top")


def test_the_part_payloads_are_the_tile_count():
    d = _defines(COLLAPSE_MAP_H)
    want = d["COLLAPSE_TILES"] * 64
    for name, p in (("collapse.c1", C1), ("collapse.c2", C2)):
        got = os.path.getsize(p)
        assert got == want, f"{name} is {got} bytes, want {want}"
    print(f"collapse part: {d['COLLAPSE_TILES']} tiles, "
          f"{os.path.getsize(C1)} bytes per plane")


def test_the_ruins_palette_and_tile_numbers():
    d = _defines(COLLAPSE_MAP_H)
    pal = _palette("ruin_pal")
    assert pal[0] == 0x8000, f"ruin_pal[0] is {pal[0]:#06x}, want 0x8000"
    assert d["RUIN_VIEWS"] == 48, d["RUIN_VIEWS"]
    tiles = _ruin_tiles(d["RUIN_VIEWS"], d["RUIN_COLS"], d["RUIN_ROWS"])
    bad = [(v, c, r, t) for v, view in enumerate(tiles)
           for c, row in enumerate(view) for r, t in enumerate(row)
           if t >= d["COLLAPSE_TILES"]]
    assert not bad, (
        f"{len(bad)} ruin_tile entries are not below COLLAPSE_TILES "
        f"{d['COLLAPSE_TILES']}: {bad[:10]}")
    print(f"ruin palette entry 0: 0x8000; {d['RUIN_VIEWS']} views x "
          f"{d['RUIN_COLS'] * d['RUIN_ROWS']} tile numbers all below "
          f"COLLAPSE_TILES {d['COLLAPSE_TILES']}")


def test_the_worst_line_is_within_the_budget():
    d = _defines(COLLAPSE_MAP_H)
    assert d["COLLAPSE_WORST_LINE"] <= LINE_LIMIT, (
        f"COLLAPSE_WORST_LINE {d['COLLAPSE_WORST_LINE']} > {LINE_LIMIT}")
    print(f"COLLAPSE_WORST_LINE {d['COLLAPSE_WORST_LINE']} <= {LINE_LIMIT}")
