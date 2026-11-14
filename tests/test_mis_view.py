"""src/mis_view.c (as build/view_sim) against exact projection: the missile's
tip within a pixel, the dart's length within 3%, and 'behind the dome'
exactly as the generator's table says."""
import math
import os
import random
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_missiles as gm  # noqa: E402
import geometry as g  # noqa: E402

SIM = os.path.join(ROOT, "build", "view_sim")
T = gm.tables()
F = g.fit()


def run(cases):
    text = "".join(f"{k} {j} {r}\n" for k, j, r in cases)
    out = subprocess.run([SIM], input=text, capture_output=True, text=True, check=True).stdout
    return [tuple(map(int, line.split())) for line in out.splitlines()]


def cases(n, seed):
    rng = random.Random(seed)
    return [(rng.randrange(12), rng.randrange(240), rng.randrange(gm.UNIT, 6 * gm.UNIT)) for _ in range(n)]


def test_tip_and_length_match_exact_projection():
    cs = cases(3000, 1)
    worst = 0.0
    for (k, j, r), (shown, _, x, y, len4) in zip(cs, run(cs)):
        exact = gm.project(gm.world(r / gm.UNIT, T["th"][k], j), F)
        assert shown == (exact is not None), (k, j, r)
        if not shown:
            continue
        ex, ey, z = exact
        if not (-64 <= gm.DOME_X + ex <= gm.SCREEN_W + 64 and -64 <= gm.DOME_Y + ey <= gm.SCREEN_H + 64):
            continue                    # far off screen: never drawn
        worst = max(worst, abs(x - ex), abs(y - ey))
        assert abs(x - ex) <= 1.0 and abs(y - ey) <= 1.0, (k, j, r, x, y, ex, ey)
        want = gm.DART_LEN * F[0] / z * 16
        assert abs(len4 - want) <= max(2, 0.03 * want), (k, j, r, len4, want)


def test_behind_the_dome_follows_the_table():
    cs = cases(3000, 2)
    for (k, j, r), (_, behind, *_rest) in zip(cs, run(cs)):
        rh = gm.hidden_r(T["th"][k], j) if T["th"][k] > 0.01 else 1.0
        # the table is rounded to Q12: decide with the table's own value
        assert behind == ((r >> 7) < round(rh * 4096)), (k, j, r, rh)


def test_a_missile_landing_on_the_back_is_behind_and_one_on_the_front_is_not():
    # ring 8 (52 deg), just above the surface: at the back (j 120) the dome
    # hides it, at the front (j 0) it is in plain view
    (_, back, *_), (_, front, *_) = run([(8, 120, int(1.02 * gm.UNIT)), (8, 0, int(1.02 * gm.UNIT))])
    assert back == 1 and front == 0
