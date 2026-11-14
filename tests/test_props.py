"""The props' layout (dome-scenery Tasks 11 and 15): src/props_layout.c,
built for the host as build/props_sim, against tests/props_model.py — the
model written from build/props_map.h and tools/render_props.drawn(), never
from the C.

  1. For all 240 dome angles, the sim's two pools equal the model's, slot
     for slot and word for word (shown, prop, lod, col, SCB2, SCB3, SCB4,
     the first SCB1 tile). Each pool's maximum slots used equals the
     header's PROP_BACK_SLOTS / PROP_FRONT_SLOTS, and the worst
     props-per-scanline over both pools equals PROP_WORST_LINE.
  2. The header's prop_front is render_props.in_front() for every
     (prop, angle): a front-pool prop is in front of the dome's centre and
     its body covers the dome on screen.
  3. Every picture's anchor lies inside it; the props part's tile count
     (sum of cols * rows) equals PROP_TILES and each generated plane is
     PROP_TILES * 64 bytes.
  4. The header's per-angle tables are the generator's drawn() output (the
     layout model's own source), so a drift between the two shows here.
"""
import os
import subprocess

import props_model as pm

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SIM = os.path.join(ROOT, "build", "props_sim")
HEADER = os.path.join(ROOT, "build", "props_map.h")
C1 = os.path.join(ROOT, "build", "assets", "props.c1")
C2 = os.path.join(ROOT, "build", "assets", "props.c2")

POOL_LINES = pm.BACK_SLOTS + pm.FRONT_SLOTS


def sim_layout():
    """the sim's output: {(da, pool): [(shown, prop, lod, col, scb2, scb3,
    scb4, tile), ...]} with each pool's slots in order."""
    out = subprocess.run([SIM], capture_output=True, text=True, check=True).stdout
    rows = [tuple(int(x) for x in line.split())
            for line in out.splitlines()]
    want = pm.NDA * POOL_LINES
    assert len(rows) == want, f"{len(rows)} slot lines, wanted {want}"
    pools = {}
    for k, r in enumerate(rows):
        assert len(r) == 11, (k, r)
        da = k // POOL_LINES
        off = k % POOL_LINES
        pool = 0 if off < pm.BACK_SLOTS else 1
        slot = off if pool == 0 else off - pm.BACK_SLOTS
        assert r[0] == da, (k, r)
        assert r[1] == pool, (k, r)
        assert r[2] == slot, (k, r)
        pools.setdefault((da, pool), []).append(r[3:])
    return pools


def test_every_angle_every_slot_matches_the_model():
    c = sim_layout()
    mismatches = []
    for da in range(pm.NDA):
        model_back, model_front = pm.layout(da)
        for pool, model in ((0, model_back), (1, model_front)):
            cap = pm.BACK_SLOTS if pool == 0 else pm.FRONT_SLOTS
            got = c[(da, pool)]
            assert len(got) == cap, (da, pool, len(got), cap)
            for k in range(cap):
                if got[k] != model[k]:
                    mismatches.append((da, pool, k, got[k], model[k]))
                    if len(mismatches) > 20:
                        break
            if len(mismatches) > 20:
                break
        if len(mismatches) > 20:
            break
    assert not mismatches, (
        f"{len(mismatches)} mismatches (angle, pool, slot, sim, model): "
        f"{mismatches[:10]}")
    front = [da for da in range(pm.NDA) if any(s[0] for s in c[(da, 1)])]
    print(f"angles compared: {pm.NDA}; slots per angle: back "
          f"{pm.BACK_SLOTS}, front {pm.FRONT_SLOTS}; mismatches: 0; "
          f"front pool used at {len(front)} angles (da {min(front)}.."
          f"{max(front)})")


def test_the_model_maximums_are_the_headers():
    back, front = pm.max_slots()
    worst = pm.worst_line()
    assert back == pm.BACK_SLOTS, (back, pm.BACK_SLOTS)
    assert front == pm.FRONT_SLOTS, (front, pm.FRONT_SLOTS)
    assert worst == pm.WORST_LINE, (worst, pm.WORST_LINE)
    print(f"max slots used: back {back} (header PROP_BACK_SLOTS "
          f"{pm.BACK_SLOTS}), front {front} (header PROP_FRONT_SLOTS "
          f"{pm.FRONT_SLOTS}); worst props per scanline over both pools: "
          f"{worst} (header PROP_WORST_LINE {pm.WORST_LINE})")


def test_the_header_front_is_the_generators_in_front():
    """prop_front[i][da] is render_props.in_front() for every prop and
    angle: the same rule the generator used to write the header."""
    pics = pm.rp.pictures()
    objs = pm.rp.props()
    dome = pm.rp.dome_mask()
    bad = []
    n = 0
    for da in range(pm.NDA):
        for i, o in enumerate(objs):
            dr = pm.rp.drawn(o, da, pics)
            got = pm.FRONT[i][da]
            want = 0 if dr is None else pm.rp.in_front(o, da, dr, pics, dome)
            n += 1
            if got != want:
                bad.append((i, da, got, want))
    assert not bad, (f"{len(bad)} prop_front entries differ from in_front(): "
                     f"{bad[:10]}")
    print(f"prop_front checked against in_front(): {n} (prop, angle) pairs; "
          f"mismatches: 0")


def test_every_pictures_anchor_lies_inside_it():
    n = 0
    for key, (cols, rows, _first, ax, ay) in sorted(pm.PICS_HEADER.items()):
        assert 0 <= ax < cols * pm.TILE, (key, ax, cols)
        assert 0 <= ay < rows * pm.TILE, (key, ay, rows)
        n += 1
    print(f"pictures with an anchor inside: {n}")


def test_the_part_tile_count_is_prop_tiles():
    n = sum(cols * rows
            for (cols, rows, _f, _ax, _ay) in pm.PICS_HEADER.values())
    assert n == pm.PROP_TILES, (n, pm.PROP_TILES)
    for plane in (C1, C2):
        assert os.path.getsize(plane) == n * 64, (plane, os.path.getsize(plane))
    print(f"pictures' tiles: {n} = PROP_TILES; each plane: {n * 64} bytes")


def test_the_header_tables_are_the_generators_drawn():
    """the header's X/Y/SE are drawn()'s, prop for prop, angle for angle;
    its kind/shape and picture tables are the generator's too."""
    bad = []
    for da in range(pm.NDA):
        for i in range(pm.NPROPS):
            dr = pm.rp.drawn(pm.OBJS[i], da, pm.PICS)
            if dr is None:
                assert pm.SE[i][da] == 0, (i, da)
                continue
            x, y, se, lod, left, top, right, bottom = dr
            if (pm.X[i][da], pm.Y[i][da], pm.SE[i][da]) != (x, y, se):
                bad.append((i, da, (pm.X[i][da], pm.Y[i][da], pm.SE[i][da]),
                            (x, y, se)))
    assert not bad, f"{len(bad)} header rows differ from drawn(): {bad[:5]}"
    for i in range(pm.NPROPS):
        assert pm.KIND[i] == pm.OBJS[i]['kind'], i
        assert pm.SHAPE[i] == pm.OBJS[i]['shape'], i
    for key, pic in sorted(pm.PICS.items()):
        cols, rows, first, ax, ay = pm.PICS_HEADER[key]
        assert (cols, rows, ax, ay) == (pic[1], pic[2], pic[3], pic[4]), key
    print(f"header rows checked against drawn(): {pm.NPROPS * pm.NDA}; "
          f"mismatches: 0")
