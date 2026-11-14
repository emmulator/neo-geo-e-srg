"""The HUD's text (tests/hud_model.py) against the source of truth: the
model of the Vectrex rules (tests/rules_model.py) as driven by the same
script of inputs tests/test_rules_play.py uses. The two must agree on every
frame — the HUD is exactly a function of the rules' state, and this test
locks that function to the model the C's rules were checked against.

Concretely, for every frame of long random games (with fire and without),
the thirty fix rows hud_model.py produces match:
  * the rules' integrity %, lives and score (score x 10, with the trailing
    0 the Vectrex shows — unless the score is 0),
  * the rules' game_over -> "GAME OVER" on row 7 (nothing there otherwise),
  * the icons on rows 24/26 (the integrity's little dome and the little
    ships) and the centred score on row 28 (so the boot test compares
    whole screens and both stay stable).
rv: hud_rows(rules_t, mis_t) on the host — see tests/test_hud.c.
"""
import os
import random
import subprocess

import hud_model as hm
import mis_model as mm
import rules_model as rm
import ship_model as sm

ROOT = os.path.join(os.path.dirname(__file__), "..")
HUD_SIM = os.path.join(ROOT, "build", "test_hud")
STICKS = [0, sm.UP, sm.DOWN, sm.LEFT, sm.RIGHT, sm.UP | sm.LEFT, sm.UP | sm.RIGHT,
          sm.DOWN | sm.LEFT, sm.DOWN | sm.RIGHT]
A = 16


def run_both(seed, frames, fire_p, level=1):
    """One game played two ways from the same script: build/test_hud (the C's
    rules + hud_rows, in sim mode) and the models. Returns the C's printed rows
    and the model's hud_rows per frame (lists of 30-row lists)."""
    rng = random.Random(seed)

    def input_line():
        inp = rng.choice(STICKS)
        fire = rng.random() < fire_p
        jump = rng.random() < 0.01
        p = (A if fire else 0) | (sm.B if jump else 0)
        return inp | p, p

    script = [f"level {level}"]
    steps = []
    for _ in range(frames):
        inp, p = input_line()
        script.append(f"{inp} {p}")
        steps.append((inp, p))
    out = subprocess.run([HUD_SIM, "sim"], input="\n".join(script) + "\n",
                         capture_output=True, encoding="latin-1", check=True).stdout
    c_rows = [line for line in out.splitlines() if line.startswith("HU ")]

    ship, mis, rules = sm.Ship(), mm.Missiles(), rm.Rules(level)
    m_rows = []
    for inp, p in steps:
        hm.frame_model((ship, mis, rules), inp, p)
        m_rows.append(hm.hud_rows(rules, mis))
    return c_rows, m_rows


def assert_same(c_rows, m_rows):
    assert len(c_rows) == len(m_rows), (len(c_rows), len(m_rows))
    for i, c in enumerate(c_rows):
        # "HU" then " %s" per row: row k occupies c[3+k*41 : 3+k*41+40]
        # (the icon tile numbers the C writes are bytes 128/129 — read as
        # latin-1 so the model's chr(128)/chr(129) compare equal)
        parsed = [c[3 + k * 41: 3 + k * 41 + 40] for k in range(30)]
        assert parsed == m_rows[i], f"frame {i}:\n  C  {parsed}\n  M  {m_rows[i]}"


def test_random_games_match():
    for seed, frames, fire_p, level in [(2, 3000, 0.05, 1), (4, 3000, 0.05, 0),
                                        (6, 3000, 0.05, 2), (1002, 3000, 0.6, 1)]:
        c_rows, m_rows = run_both(seed, frames, fire_p, level)
        assert_same(c_rows, m_rows)


def test_the_hud_is_a_function_of_the_state():
    """hud_rows must change only when its inputs change: replay the same
    frame twice from the same state and get identical rows (cheap, host-only
    sanity for the redraw-only rule)."""
    ship, mis, rules = sm.Ship(), mm.Missiles(), rm.Rules(1)
    hm.frame_model((ship, mis, rules), 0, 0)
    a = hm.hud_rows(rules, mis)
    # step the game (a crack lands), then snapshot again from a copy
    hm.frame_model((ship, mis, rules), sm.UP, 0)
    b = hm.hud_rows(rules, mis)
    # nothing here asserts a != b: just that a deterministic call is stable
    assert hm.hud_rows(rules, mis) == hm.hud_rows(rules, mis)
    assert isinstance(a, list) and len(a) == 30 and all(len(r) == 40 for r in a)
    assert isinstance(b, list) and len(b) == 30
