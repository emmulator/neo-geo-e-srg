"""The radar's pure logic against the reference model (M5 Task 3).

  tests/test_radar.py   (host, pytest; runs build/radar_sim)

1. Positions: src/radar.c (as build/radar_sim, driven over the task's full
   grid — every ring, phi 0..239, dome_angle 0..239 in steps of 7, r from 0
   to 6.0 radii in steps of 0.05, locked and not) must be within 1 px of
   tests/radar_model.py — the formulas of the task and radar.s in floats.
   The blip depends only on j = (phi + dome_angle) mod 240, so the sim
   emits each distinct (ring, j, k, locked) once; the wrap sweep holds the
   C's radar_j to (phi + da) mod 240 on every (phi, da) of the grid.
2. The constants in src/radar.h equal the model's (the user's tuning block
   stays the one source; the model is the independent reference).
3. The lock-on's per-missile flags: locked blips are exactly the flying
   in-range missiles aimed at the ship's resting cell; the range edge (r =
   6.0 radii) shows nothing; the heading of a locked blip is twice as long.
   (The locked/lock_t/ellipse_bright frame-by-frame comparison lives in
   tests/test_missile_play.py and tests/test_rules_play.py.)

`make test` builds build/radar_sim; run `make clean && make` first.
"""
import os
import re
import subprocess
import sys

import numpy as np

import radar_model as rm
import layout

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "radar_sim")
H = os.path.join(ROOT, "src", "radar.h")
TOL = 1                     # px: the task's bound


def _h_defs():
    txt = open(H).read()
    out = {}
    for m in re.finditer(r"#define\s+(RADAR_\w+)\s+([^\n]+)", txt):
        out[m.group(1)] = m.group(2).split("/*")[0].strip()
    return out


def c_positions():
    """the sim's records as a Nx9 int array (ring, j, k, locked, sx, sy, h,
    hx, hy), one per distinct (ring, j, k, locked)."""
    out = subprocess.run([SIM, "pos"], capture_output=True, text=True,
                         check=True).stdout
    rows = [line.split()[1:] for line in out.splitlines()]
    a = np.array(rows, dtype=np.int64)
    assert a.ndim == 2 and a.shape[1] == 9, a.shape
    return a


def test_radar_h_constants_equal_the_model():
    d = _h_defs()
    assert d["RADAR_CX"] == "38"
    # RADAR_CY is a plain number: Dome-scenery Task 2 made it the literal
    # 184, and Task 8 moved it 22 px down to 206 (onto the console's left
    # wing, its disc's bottom on y 215 with the lives and the score). The
    # model reads the same value through tests/layout.py.
    assert d["RADAR_CY"] == "206"
    assert rm.CY == layout.d.RADAR_CY         # both follow src/radar.h
    assert d["RADAR_RX"] == "30"
    assert d["RADAR_RY"] == "84"            # 8.4 px in tenths
    assert d["RADAR_H"] == "30"
    assert d["RADAR_H_POW"] == "2"
    assert d["RADAR_RANGE"] == str(6 << 19) or d["RADAR_RANGE"] == "(6 << 19)"
    assert d["RADAR_BLINK"] == "5"
    assert d["RADAR_HEAD_SHIFT"] == "2"
    assert d["RADAR_HEAD_SHIFT_LOCKED"] == "1"


def test_positions_within_1px_of_the_model():
    a = c_positions()
    ring, j, k, lock = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
    r_units = (262144 * k + 5) // 10        # the sim's r, in 2^-19 radii
    # the model's expected fields, vectorised (shape = the records')
    th = rm.TH[ring]
    ang = np.pi * 2 * j / rm.STEPS
    r6 = r_units / (6 * rm.UNIT)
    shown = r_units < rm.R_LIMIT          # r = exactly 6.0 radii is NOT shown
    sx = np.where(shown, np.round(rm.CX + r6 * rm.RX * np.sin(th) * np.sin(ang)), 0)
    sy = np.where(shown, np.round(rm.CY + r6 * rm.RY * np.sin(th) * np.cos(ang)), 0)
    h = np.where(shown, np.round(r6 * rm.H * np.cos(th) ** rm.H_POW), 0)
    top_x, top_y = sx, sy - h
    frac = np.where(lock, 0.5, 0.25)
    hx = np.where(shown, np.round(top_x + (rm.CX - top_x) * frac), 0)
    hy = np.where(shown, np.round(top_y + (rm.CY - top_y) * frac), 0)
    for name, c, m in (("sx", a[:, 4], sx), ("sy", a[:, 5], sy),
                       ("h", a[:, 6], h), ("hx", a[:, 7], hx),
                       ("hy", a[:, 8], hy)):
        d = np.abs(c - m)
        bad = np.argwhere(d > TOL)[:5]
        assert not len(bad), (f"{name} off by > {TOL} px at "
                              + str([(int(ring[i]), int(j[i]), int(k[i]),
                                      int(lock[i]), int(c[i]), int(m[i]))
                                     for i in bad.ravel()]))
    # the grid covered everything: one record per distinct (ring, j, k,
    # locked), all 12 rings x 240 j x 121 r steps x both lock states
    keys = ring * (240 * 121 * 2) + j * (121 * 2) + k * 2 + lock
    assert len(np.unique(keys)) == 12 * 240 * 121 * 2


def test_every_grid_phi_da_pairs_wrap_like_the_model():
    out = subprocess.run([SIM, "wrap"], capture_output=True, text=True,
                         check=True).stdout
    for line in out.splitlines():
        phi, da, j = (int(x) for x in line.split()[1:])
        assert j == rm.j_of(phi, da), (phi, da, j)


def test_locked_headings_are_twice_the_length():
    # for a ring-4 (mid-dome) missile at the rim of the radar, the heading
    # runs from the stick's top toward the centre: the unlocked one ends at
    # top + (centre - top) / 4, the locked one at / 2 — i.e. the heading
    # end is 3/4 (unlocked) or 1/2 (locked) of the way from the centre to
    # the top (radar.s's HEAD_SHIFT / HEAD_SHIFT - 1)
    r_units = rm.R_LIMIT - 1
    for j in (0, 30, 90, 150, 210, 239):
        u = rm.blip(4, j, r_units, 0)
        l = rm.blip(4, j, r_units, 1)
        assert l[0] == u[0] == 1
        # du = the distance from the centre to the stick's top
        # (u = (shown, sx, sy, h, hx, hy))
        du = ((u[1] - rm.CX) ** 2 + (u[2] - u[3] - rm.CY) ** 2) ** 0.5
        hu = ((u[4] - rm.CX) ** 2 + (u[5] - rm.CY) ** 2) ** 0.5
        hl = ((l[4] - rm.CX) ** 2 + (l[5] - rm.CY) ** 2) ** 0.5
        assert abs(hu - du * 3 / 4) <= 1.5, (j, du, hu)
        assert abs(hl - du / 2) <= 1.5, (j, du, hl)


def test_peak_ring_blips_sit_at_the_centre():
    # ring 0's polar angle is 0: the spot is always the ellipse's centre,
    # the stick is the full height at the radar's edge (R = 6.0), and the
    # heading runs straight down from the stick's top a quarter of the way
    # to the centre: (CY - H) + H/4 = 183.5 -> 184 px at CY 206 (both the
    # C's half-up and the model's half-even round it up). The expected end
    # y derives from the model's CY and H, so it follows the header.
    hy = rm.CY - (3 * rm.H) // 4
    for j in range(240):
        assert rm.blip(0, j, rm.R_LIMIT - 1, 0) == (1, rm.CX, rm.CY, rm.H,
                                                    rm.CX, hy)
    assert rm.blip(0, 0, rm.R_LIMIT, 0) == (0, 0, 0, 0, 0, 0)   # the edge


if __name__ == "__main__":
    sys.exit(test_positions_within_1px_of_the_model())
