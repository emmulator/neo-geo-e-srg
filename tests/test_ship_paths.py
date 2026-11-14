"""src/ship.c (built for the host as build/ship_sim) against the reference
model of the Vectrex game's movement (tests/ship_model.py): same input,
same cells, rotation, latitude and lift, every frame."""
import os
import random
import subprocess

import ship_model as sm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "ship_sim")
STICKS = [0, sm.UP, sm.DOWN, sm.LEFT, sm.RIGHT, sm.UP | sm.LEFT, sm.UP | sm.RIGHT,
          sm.DOWN | sm.LEFT, sm.DOWN | sm.RIGHT]


def run_both(script):
    """script: ("P", cell) | ("B", cell) | (input, pressed). Returns (c, model) state lists."""
    text = "".join(f"{a} {b}\n" for a, b in script)
    out = subprocess.run([SIM], input=text, capture_output=True, text=True, check=True).stdout
    c_states = [tuple(map(int, line.split())) for line in out.splitlines()]
    ship, m_states = sm.Ship(), []
    for a, b in script:
        if a == "P":
            ship.place(b)
        elif a == "B":
            ship.broken.add(b)
        else:
            ship.frame(a, b)
            m_states.append(ship.state() + (ship.jumped,))   # M7: the jump flag
    return c_states, m_states


def random_play(seed, frames=3000, broken=()):
    rng = random.Random(seed)
    script = [("B", c) for c in broken]
    while len(script) < frames:
        inp = rng.choice(STICKS)
        for k in range(rng.randint(1, 40)):
            jump = k == 0 and rng.random() < 0.3
            script.append((inp | (sm.B if jump else 0), sm.B if jump else 0))
    return script


def assert_same(c, m):
    assert len(c) == len(m)
    for i, (a, b) in enumerate(zip(c, m)):
        assert a == b, f"frame {i}: ship.c {a} != model {b} (cell, left, angle, lat, lift, jumped)"


def test_random_play_matches_the_vectrex_model():
    for seed in range(1, 6):
        assert_same(*run_both(random_play(seed)))


def test_random_play_with_broken_cells_matches():
    for seed in range(6, 9):
        assert_same(*run_both(random_play(seed, broken=(13, 26, 29, 12, 2))))


def test_every_cell_every_direction():
    # from rest on each cell, one push in each of the 8 directions, held
    # long enough to land (and, at the peak, to spin)
    script = []
    for cell in range(len(sm.STEP)):
        for inp in STICKS[1:]:
            script.append(("P", cell))
            script += [(inp, 0)] * (sm.MOVE + 2)
            script.append(("P", cell))
            script += [(inp | sm.B, sm.B)] + [(inp, 0)] * (sm.JUMP + 2)
    assert_same(*run_both(script))


def test_the_ship_reaches_every_cell():
    seen = set()
    for seed in range(1, 6):
        c, _ = run_both(random_play(seed, frames=6000))
        seen |= {s[0] for s in c if s[1] == 0}
    assert seen == set(range(len(sm.STEP)))
