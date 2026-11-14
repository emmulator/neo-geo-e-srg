"""The star field model (M5 Task 2): the 12 stars of the Vectrex's stars.s
table mapped to the Neo Geo screen, and their per-frame turning with the
dome. This is the reference tests/test_stars.py holds src/stars.c to (exact
integer equality).

The mapping is the task's formulas:

    x0 = round((x_v + 128) * 320 / 256)
    y  = round((DOME_Y - 4) - (y_v - 8) * 60 / 103)
    x  = (x0 - round(dome_angle * 320 / 240)) mod 320

where (y_v, x_v) is a star's (y, x) Vectrex units from stars.s, DOME_Y is
the dome box's top from src/dome.h (read via tests/layout.py — the stars'
band's bottom is DOME_Y - 4, just above the box, so lifting the dome lifts
the stars with it; at DOME_Y 72 the band is y 8..68), and dome_angle is the
ship's rotation step (0..239). One dome turn (240 steps) scrolls the stars
one whole screen width, leftward as dome_angle grows.

`round` here is round-half-up on the exact rational (what C's round() does
for these positive values). Two x0 values hit an exact half (x_v 42 and -6:
212.5 and 152.5): banker's rounding would give 212/152, half-up 213/153 —
the two agree on nothing else, so this module's choice is the rule the C
must match. Added to tests/test_stars.py below the equality proof.
"""

import os
import sys

STARS = [(44, 29), (41, -50), (111, -11), (67, 119), (13, 42),
         (93, -81), (27, -34), (13, 71), (89, -6), (60, -124),
         (87, 28), (73, -52)]
NSTARS = len(STARS)

X_TIES = {4: (212.5, 213), 8: (152.5, 153)}   # star index -> (banker's, half-up)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import layout as _lay  # noqa: E402
DOME_Y = _lay.d.DOME_Y          # the dome box's top (src/dome.h)
BAND_BOTTOM = DOME_Y - 4        # the stars' band's bottom, just above the box


def x0(i):
    """round-half-up((x_v + 128) * 320 / 256) = (5 * (x_v + 128) + 2) // 4."""
    _, xv = STARS[i]
    return (5 * (xv + 128) + 2) // 4


def y(i):
    """round-half-up((DOME_Y - 4) - (y_v - 8) * 60 / 103) =
    (DOME_Y - 4) - floor((y_v - 8) * 60 / 103 + 0.5) =
    (DOME_Y - 4) - (120 * (y_v - 8) + 103) // 206."""
    yv, _ = STARS[i]
    return BAND_BOTTOM - (120 * (yv - 8) + 103) // 206


def x_drift(dome_angle):
    """round-half-up(dome_angle * 320 / 240); da * 320 / 240 = da * 4/3 has no
    exact .5 ties, so this equals (da * 320 + 120) // 240 for every step."""
    return (dome_angle * 320 + 120) // 240


def pos(i, dome_angle):
    return ((x0(i) - x_drift(dome_angle)) % 320, y(i))


def all_pos():
    return [(x0(i), y(i)) for i in range(NSTARS)]
