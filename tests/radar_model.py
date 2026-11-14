"""Reference model of the Vectrex game's radar (M5 Task 3): the Elite-style
scanner of vectrex-e-srg v1.0.0 (tools/gen_dome.py radar_k/radar_frame and
src/radar.s) mapped to the Neo Geo screen by the task's formulas, plus the
lock-on of e-srg.c's lock_update. tests/test_radar.py holds src/radar.c (as
build/radar_sim) to this model: positions within 1 px, and the lock state
exactly on every frame of the long seeded games.

The radar's constants (the task's block; the user tunes these in
src/radar.h — this module is the REFERENCE, so it states them itself and
tests/test_radar.py proves the C's header still says the same — except
RADAR_CY, which is defined in terms of the dome: DOME_Y + 112, read from
src/dome.h through tests/layout.py so the radar keeps its place beside
the dome's rim when the dome moves):

    CX, CY = 38, 184      the ellipse's centre (px; CY = DOME_Y + 112)
    RX     = 30           x radius (px)
    RY     = 8.4          y radius (px): RX * 0.28, the Vectrex's RADAR_FLAT
    H      = 30           stick height for R = 6.0 radii straight up (px)
    H_POW  = 2            stick height ~ R/6 * cos(theta)^2 (the Vectrex's)
    RANGE  = 6.0          radii at the ellipse's edge (the Vectrex's RADAR_RANGE)
    BLINK  = 5            4 Vectrex frames x 59/50, rounded

Per flying missile in range (state == 1 and r < RANGE * 2^19), with R = r in
radii and theta its ring's polar angle (in rotation steps, 240 per turn):

    j    = (phi + dome_angle) mod 240
    sx   = round(CX + R/6 * RX * sin(theta) * sin(j))
    sy   = round(CY + R/6 * RY * sin(theta) * cos(j))   (y down: the near
                                                         side is the bottom)
    h    = round(R/6 * H * cos(theta)^H_POW)             the stick's top is
                                                         (sx, sy - h)
    hx   = round(top_x + (CX - top_x) * frac)   frac = 1/4 (locked: 1/2,
    hy   = round(top_y + (CY - top_y) * frac)    radar.s's HEAD_SHIFT)

`round` is Python's (half-even on exact .5s): the C uses half-up and the
task's bound is 1 px, which covers the difference.

Lock-on (e-srg.c lock_update): while the ship is at rest (move_left == 0),
its cell's (ring, phi) is the lock target; when some flying missile IN
RANGE has it, locked = 1, lock_t counts frames (wrapping at 256, as the C's
u8) and resets to 0 otherwise; the ellipse blinks bright while locked and
(lock_t / BLINK) is odd."""
import json
import os
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_radar  # noqa: E402  (the ring polar angles are shared geometry)

V = json.load(open(os.path.join(ROOT, "tools", "vectrex_missiles.json")))
CELL_RING, CELL_PHI = V["cell_ring"], V["cell_phi"]
NMIS = V["nmis"]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout as _lay  # noqa: E402
CX, CY = 38, _lay.d.RADAR_CY    # CY = DOME_Y + 112 (src/dome.h -> radar.h)
RX, RY = 30, 8.4
H, H_POW = 30, 2
RANGE = 6.0
BLINK = 5
UNIT = 1 << 19                      # 2^-19 radii, the missile r unit
R_LIMIT = round(RANGE * UNIT)       # 6 << 19: strictly inside is shown
STEPS = 240

TH = np.array(gen_radar.ring_thetas())


def j_of(phi, dome_angle):
    """(phi + dome_angle) mod 240 — the on-screen azimuth."""
    return (phi + dome_angle) % STEPS


def blip(ring, j, r_units, locked):
    """the C's radar_blip: (shown, sx, sy, h, hx, hy) — all ints, from the
    formulas above (float maths, rounded to px). ring is the missile's ring
    (its polar angle TH[ring]), j its on-screen azimuth, r_units its
    distance in 2^-19 radii, locked the lock flag (longer heading)."""
    if r_units >= R_LIMIT:
        return (0, 0, 0, 0, 0, 0)
    r6 = r_units / (6 * UNIT)               # R/6 in radii, exact
    th = TH[ring]
    a = (np.pi * 2 * j) / STEPS
    sx = round(CX + r6 * RX * np.sin(th) * np.sin(a))
    sy = round(CY + r6 * RY * np.sin(th) * np.cos(a))
    h = round(r6 * H * np.cos(th) ** H_POW)
    top_x, top_y = sx, sy - h
    frac = 0.5 if locked else 0.25
    hx = round(top_x + (CX - top_x) * frac)
    hy = round(top_y + (CY - top_y) * frac)
    return (1, sx, sy, h, hx, hy)


class Radar:
    """the lock-on state (e-srg.c lock_update), carried over frames: what
    the frame-by-frame tests compare EXACTLY (locked, lock_t,
    ellipse_bright, and each blip's shown/locked flags)."""

    def __init__(self):
        self.lock_t = 0
        self._lock_frames = 0

    def lock_frames(self):
        """how many of the frames played so far were locked (the task's
        "make sure some lock frames occur, and assert there are at least
        50")."""
        return self._lock_frames

    def frame(self, ship, mis):
        """one frame, after the ship's move and the missiles update (the
        Vectrex runs lock_update after game_step)."""
        ring = phi = None
        if ship.left == 0:                  # at rest: the ship's cell is the target
            ring, phi = CELL_RING[ship.cell], CELL_PHI[ship.cell]
        shown, lcked, locked = [], [], 0
        for o in mis.obj[:NMIS]:
            sh = 1 if (o.state == 1 and o.r < R_LIMIT) else 0
            l = 1 if (sh and ring is not None and o.ring == ring and o.phi == phi) else 0
            shown.append(sh)
            lcked.append(l)
            locked |= l
        if locked:
            self.lock_t = (self.lock_t + 1) & 0xFF
            self._lock_frames += 1
        else:
            self.lock_t = 0
        self.locked = locked
        self.bright = 1 if (locked and (self.lock_t // BLINK) & 1) else 0
        self.blips = list(zip(shown, lcked))
        return self

    def line(self):
        """the per-frame row the sims print (locked, lock_t, bright, then
        each blip's shown and locked)."""
        return ("r %d %d %d |" % (self.locked, self.lock_t, self.bright)
                + "".join(" %d %d" % p for p in self.blips))
