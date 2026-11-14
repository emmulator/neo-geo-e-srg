"""src/ship.c + src/missiles.c + src/radar.c (as build/mis_sim) against the
reference models of the Vectrex game (tests/ship_model.py, tests/mis_model.py,
tests/radar_model.py): the same input gives the same launches, flights,
shots, hits, landings, kills and score, every frame — and the radar's lock
state (locked, lock_t, ellipse_bright and each blip's shown/locked, M5
Task 3) on every frame too."""
import os
import random
import subprocess

import mis_model as mm
import radar_model as rm
import ship_model as sm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "mis_sim")
STICKS = [0, sm.UP, sm.DOWN, sm.LEFT, sm.RIGHT, sm.UP | sm.LEFT, sm.DOWN | sm.RIGHT]


def play(seed, frames, fire_rate, broken=()):
    rng = random.Random(seed)
    script = [("B", c) for c in broken]
    while len(script) < frames:
        inp = rng.choice(STICKS)
        for _ in range(rng.randint(1, 50)):
            p = (mm.A if rng.random() < fire_rate else 0) | (sm.B if rng.random() < 0.01 else 0)
            script.append((inp | p, p))
    return script


def run_both(script):
    text = "".join(f"{a} {b}\n" for a, b in script)
    c = subprocess.run([SIM], input=text, capture_output=True, text=True, check=True).stdout.splitlines()
    ship, mis, model = sm.Ship(), mm.Missiles(), []
    radar = rm.Radar()
    for a, b in script:
        if a == "B":
            ship.broken.add(b)
            continue
        ship.frame(a, b)
        mis.frame(ship, b)
        model.append(mis.line(ship))
        radar.frame(ship, mis)
        model.append(radar.line())
    return c, model, mis, radar


def assert_same(c, model):
    assert len(c) == len(model)
    for i, (x, y) in enumerate(zip(c, model)):
        assert x.split() == y.split(), f"frame {i}:\n  missiles.c {x}\n  model      {y}"


def test_play_matches_the_vectrex_model():
    c, model, mis, radar = run_both(play(1, 12000, 0.05))
    assert_same(c, model)
    assert mis.kills >= 5                       # (the play shot some down ...
    assert any(" l" in line for line in model)  # ... and let some land)
    # the radar locks on when the ship rests on a cell a missile is aimed
    # at (M5 Task 3): this game alone shows 160 locked frames; the task
    # wants at least 50 somewhere
    assert radar.lock_frames() >= 50


def test_play_with_broken_cells_matches():
    c, model, _, radar = run_both(play(2, 6000, 0.03, broken=(13, 2, 27, 40, 5)))
    assert_same(c, model)
    assert radar.lock_frames() >= 10


def test_heavy_fire_matches():
    # fire nearly every frame: both bullet slots busy, shots dropped.
    # (seed 7: locks 38 at today's dome and also at the size knob's
    # 0.9/10-column proof; seed 3, the old one, only manages 7-9 frames
    # there because the shorter bullets shift which missiles reach a
    # resting ship's cell.)
    c, model, _, radar = run_both(play(7, 4000, 0.6))
    assert_same(c, model)
    assert radar.lock_frames() >= 10


def test_launches_follow_the_rules():
    # never more than two missiles at once, never two at one cell, and the
    # target rings stay rings 0..4 until six kills or six hits that broke a
    # whole landing cell (the M3 frame — test_missile_play's mis_frame —
    # counts every landing, because it has no rules and no broken set, so
    # the model's dome_hits can only be at least the true count; it opens
    # at LOW_RINGS_AT too)
    _, model, _, radar = run_both(play(4, 12000, 0.05))
    assert radar.lock_frames() >= 10
    for line in model:
        if not line or line[0] != " ":       # skip the radar lines (r ...)
            continue
        head, objs = line.split("|")[1], line.split("|")[3].split()
        kills, dome_hits = (int(x) for x in head.split()[1:3])
        flying = [tuple(map(int, objs[i:i + 6])) for i in range(0, 6 * mm.NMIS, 6)]
        flying = [o for o in flying if o[0] == 1]
        assert len(flying) <= 2
        assert len({(o[2], o[3]) for o in flying}) == len(flying)
        if kills < mm.LOW_RINGS_AT and dome_hits < mm.LOW_RINGS_AT:
            assert all(o[2] < mm.WAVE_RINGS for o in flying)
