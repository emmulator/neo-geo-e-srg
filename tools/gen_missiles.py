#!/usr/bin/env python3
"""gen_missiles.py HEADER.h: the tables for missiles and bullets as a C header.

A missile flies a straight line through a cell's centre toward the centre of
the sphere the dome is cut from, fixed in the dome's frame (so it turns with
the dome); a bullet flies the same kind of line outward from the ship's cell.
Both are just a distance R from the sphere's centre (units of 2^-19 radii,
as on the Vectrex) on a ring of cells (polar angle) at an azimuth.

- rings: the cells grouped by polar angle (mis_rings, copied from the
  Vectrex generator), each cell's ring and azimuth;
- flights: start distances per ring are the Vectrex's (tools/
  vectrex_missiles.json), so a missile takes as long to arrive; speeds and
  the bullet's are the Vectrex's per-frame values x 50/59 (59.2 Hz) —
  mis_dr_easy is EASY's 0.75x table (v1.1.0);
- bullet lives: frames until a bullet leaves the Neo Geo screen at every
  rotation, or (fired at a missile on its line) reaches the radar's edge;
- projection: fixed-point constants for src/mis_view.c (Q12 lengths, Q14
  sines, Q4 pixels in the dome box), and per ring and screen azimuth the
  distance below which a missile is behind the dome (drawn under it)."""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tests"))
import layout as lay  # noqa: E402

VEC = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectrex_missiles.json")))
UNIT = VEC["r_unit"]            # R units: 2^-19 radii
HZ = (50, 59)                   # Vectrex frames : Neo Geo frames
RADAR_RANGE = 6.0               # the radar's edge (sphere radii), the Vectrex's
FLOOR_Y = math.cos(math.radians(66))    # the dome's solid floor, the Vectrex's MIS_FLOOR_Y
ZMIN = 0.35                     # nearer than this to the camera: not drawn (the Vectrex's)
DART_LEN = 0.22                 # tip to base, sphere radii (the Vectrex's MIS_LEN)
SCREEN_W, SCREEN_H = 320, 224
# the dome box on screen, from src/dome.h (tests/layout.py): the missiles'
# on-screen margin test follows the dome's position
DOME_X, DOME_Y = lay.d.DOME_X, lay.d.DOME_Y


# ---- copied verbatim from vectrex-e-srg tools/gen_dome.py (v1.0.0) ----
def mis_rings(cells):
    th = sorted({round(t, 6) for t in cells["theta"]})
    ring = [min(range(len(th)), key=lambda k: abs(th[k] - t)) for t in cells["theta"]]
    return th, ring
# ---- end of copied code ----


def tables():
    pts, _, faces = g.build_mesh()
    cells = g.make_cells(pts, faces)
    th, ring = mis_rings(cells)
    assert ring == sorted(ring), "cells must be sorted by ring"
    ring_end = [sum(1 for r in ring if r <= k) for k in range(len(th))]
    phi = [(-s) % g.STEPS for s in cells["step"]]
    return dict(cells=cells, th=th, ring=ring, ring_end=ring_end, phi=phi)


def world(r, t, j):
    """the point at distance r on ring angle t, at screen azimuth j (steps)."""
    a = 2 * math.pi * j / g.STEPS
    return r * np.array([math.sin(t) * math.sin(a), math.cos(t), math.sin(t) * math.cos(a)])


def project(p, f):
    """exact: (x, y) in the dome box (px) and depth z, or None if z < ZMIN."""
    pos, fwd, right, up = g.camera()
    d = p - pos
    z = d @ fwd
    if z < ZMIN:
        return None
    scale, ox, oy = f
    return ox + scale * (d @ right) / z, oy - scale * (d @ up) / z, z


def on_screen(r, t, j, f, margin=8):
    q = project(world(r, t, j), f)
    return q is not None and -margin <= DOME_X + q[0] <= SCREEN_W + margin \
        and -margin <= DOME_Y + q[1] <= SCREEN_H + margin


def r_offscreen(t, f):
    """the distance beyond which ring t's line is off screen at every rotation."""
    for r in np.arange(1.0, 8.0, 0.02):
        if not any(on_screen(r2, t, j, f) for j in range(0, g.STEPS, 4) for r2 in (r, r + 0.3, r + 0.8)):
            return r + 0.05
    return RADAR_RANGE


def hidden_r(t, j):
    """largest r (1..RADAR_RANGE, 0.01 steps) at which the line from the
    camera to the point crosses the solid dome: inside the sphere (radius
    0.995) and above its floor."""
    pos = g.camera()[0]
    rs = np.arange(1.0, RADAR_RANGE + 0.005, 0.01)
    P = np.outer(rs, world(1.0, t, j))              # the points, one per r
    D = P - pos                                     # segment: pos + s D, s in [0, 1)
    a = (D * D).sum(1)
    b = 2 * D @ pos
    c = pos @ pos - 0.995 ** 2
    disc = b * b - 4 * a * c
    ok = disc > 0
    sq = np.sqrt(np.where(ok, disc, 0))
    s1 = np.clip((-b - sq) / (2 * a), 0, 0.999)     # inside the sphere for s1 < s < s2
    s2 = np.clip((-b + sq) / (2 * a), 0, 0.999)
    y1, y2 = pos[1] + s1 * D[:, 1], pos[1] + s2 * D[:, 1]
    hit = ok & (s2 > s1) & ((y1 > FLOOR_Y) | (y2 > FLOOR_Y))   # y is linear in s
    return float(rs[hit].max()) if hit.any() else 1.0


def q(x, bits):
    return int(round(x * (1 << bits)))


def c_array(name, ctype, values, per_line=12):
    rows = [", ".join(map(str, values[i:i + per_line])) for i in range(0, len(values), per_line)]
    return f"static const {ctype} {name} = {{\n  " + ",\n  ".join(rows) + "\n};\n"


def main():
    T = tables()
    th, f = T["th"], g.fit()
    scale, ox, oy = f
    pos, fwd, right, up = g.camera()
    assert abs(right[0] - 1) < 1e-9 and abs(fwd[0]) < 1e-9 and abs(up[0]) < 1e-9
    n_rings = len(th)
    assert T["ring_end"] == VEC["ring_end"] and T["ring"] == VEC["cell_ring"] and T["phi"] == VEC["cell_phi"]

    dr = [round(v * 64 * HZ[0] / HZ[1]) for v in VEC["speed_val"]]   # the Vectrex's 64 v, x 50/59
    dr_easy = [round(v * 64 * HZ[0] / HZ[1]) for v in VEC["speed_easy"]]   # EASY: 0.75x (v1.1.0)
    bul_dr = round(VEC["bullet_dr"] * HZ[0] / HZ[1])
    r0 = VEC["bullet_r0"] / UNIT
    bul_life = [min(255, math.ceil((r_offscreen(t, f) - r0) * UNIT / bul_dr)) for t in th]
    bul_far = min(255, math.ceil((RADAR_RANGE - r0) * UNIT / bul_dr))
    occ = [[q(hidden_r(t, j), 12) if t > 0.01 else q(1.0, 12) for j in range(g.STEPS // 2 + 1)] for t in th]

    with open(sys.argv[1], "w") as h:
        w = h.write
        w("/* generated by tools/gen_missiles.py: do not edit */\n#ifndef MISSILES_TABLES_H\n#define MISSILES_TABLES_H\n")
        w(f"#define MIS_RINGS   {n_rings}\n#define MIS_SPEEDS  {len(dr)}\n")
        w("#define MIS_R_LAND  %d      /* R units: 2^-19 radii; a missile lands at R <= 1.0 */\n" % UNIT)
        w("/* cells by ring: ring k is cells mis_ring_end[k-1] .. mis_ring_end[k]-1 */\n")
        w(c_array("mis_ring_end[MIS_RINGS]", "u8", T["ring_end"]))
        w(c_array("mis_cell_ring[NCELLS]", "u8", T["ring"], 16))
        w("/* cell azimuth in rotation steps (on screen: + dome_angle) */\n")
        w(c_array("mis_cell_phi[NCELLS]", "u8", T["phi"], 16))
        w("/* flight start by ring (the Vectrex's), per-frame approach by speed step */\n")
        w(c_array("mis_r_spawn[MIS_RINGS]", "s32", VEC["r_spawn"], 6))
        w(c_array("mis_dr[MIS_SPEEDS]", "s32", dr))
        w(c_array("mis_dr_easy[MIS_SPEEDS]", "s32", dr_easy))
        w(f"#define BUL_R0      {VEC['bullet_r0']}   /* the head starts 0.12 above the cell */\n")
        w(f"#define BUL_DR      {bul_dr}\n#define BUL_LIFE_FAR {bul_far}   /* to the radar's edge */\n")
        w("/* frames until off screen at every rotation */\n")
        w(c_array("bul_life[MIS_RINGS]", "u8", bul_life))
        w("/* ---- projection (src/mis_view.c): Q12 lengths, Q14 sines, Q4 px in the dome box */\n")
        w(c_array("mis_sin[240]", "s16", [q(math.sin(2 * math.pi * j / g.STEPS), 14) for j in range(g.STEPS)]))
        w(c_array("ring_sin[MIS_RINGS]", "s16", [q(math.sin(t), 14) for t in th]))
        w(c_array("ring_cos[MIS_RINGS]", "s16", [q(math.cos(t), 14) for t in th]))
        w(f"#define CAM_PY      {q(pos[1], 12)}\n#define CAM_PZ      {q(pos[2], 12)}\n")
        w(f"#define CAM_FY      {q(fwd[1], 14)}\n#define CAM_FZ      {q(fwd[2], 14)}\n")
        w(f"#define CAM_UY      {q(up[1], 14)}\n#define CAM_UZ      {q(up[2], 14)}\n")
        w(f"#define VIEW_S4     {q(scale, 4)}   /* px per unit of x/z, Q4 */\n")
        w(f"#define VIEW_OX4    {q(ox, 4)}\n#define VIEW_OY4    {q(oy, 4)}\n")
        w(f"#define VIEW_ZMIN   {q(ZMIN, 12)}\n")
        w(f"#define DART_LEN4   {q(DART_LEN * scale * 16, 12)}   /* / z (Q12): the dart's length, Q4 px */\n")
        w("/* behind the dome while R (Q12) < mis_occ[ring][j], j = screen azimuth mirrored to 0..120 */\n")
        w("static const u16 mis_occ[MIS_RINGS][121] = {\n"
          + ",\n".join("  {" + ", ".join(map(str, row)) + "}" for row in occ) + "\n};\n")
        w("#endif\n")


if __name__ == "__main__":
    main()
