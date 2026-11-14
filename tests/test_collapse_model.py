"""The collapse effect's C (src/rules.c, as build/collapse_sim — see
tests/collapse_sim.c) against tests/collapse_model.py, the model of the
Vectrex's collapse_update scaled x 59/50. Over the whole death of every
death the C and the model must agree on the five numbers the drawing
reads: the draw flag, the shake, the burst, the fall and the dim.

collapse_sim prints, after each frame:
    C <dead_t> <nbroken> <lives> <game_over> | <state> <frac> <shake> <burst> <fall> <dim>
This test replays the same game (drive = dome deaths only, so no missiles)
and compares state/frac/shake/burst/fall/dim with collapse_model(dead_t,
dome_dead) — the model is a pure function of the same dead_t/dome_dead
pair the C prints, so the replay is exact (there is no sampling).
"""
import os
import subprocess

import collapse_model as cm
import ship_model as sm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "collapse_sim")


def run(script):
    out = subprocess.run([SIM], input="\n".join(script) + "\n",
                         capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line.startswith("C ")]


def frame_lines(frames):
    """many no-input frames, then a 'GO' command that kills the ship with a
    dome death (rules_end sees 38 broken); then more no-input frames."""
    lines = ["GO"]
    for _ in range(frames):
        lines.append("0 0")
    return lines


def _parse(line):
    left, right = line.split("|")
    p = left.split()
    q = right.split()
    dead_t, nbroken, dome_dead, lives, go = (int(x) for x in p[1:6])
    state, frac, shake, burst, fall, dim = (int(x) for x in q)
    return dead_t, nbroken, dome_dead, lives, go, state, frac, shake, burst, fall, dim


def _check(line):
    """the C's state/effects must be exactly the model's (which is a pure
    function of dead_t/dome_dead). The C's state 2 means "the collapse is
    running" (gate on and frac < COLLAPSE_GONE); state 1 covers both the
    whole dome and the gone case, so the model's drawing is checked through
    the effect values."""
    dead_t, nbroken, dome_dead, lives, go, state, frac, shake, burst, fall, dim = _parse(line)
    draw, mshake, mburst, mfall, mdim = cm.collapse(dead_t, dome_dead)
    running = bool(dead_t and dome_dead and frac < cm.COLLAPSE_GONE)
    assert (state == 2) == running, line
    if running:
        assert shake == mshake and burst == mburst and fall == mfall and dim == mdim, line
        assert draw == 1, line
    else:
        assert shake == burst == fall == dim == 0, line
        assert mshake == mburst == mfall == mdim == 0, line
        if dead_t and dome_dead:
            assert draw == 0, line            # gone: the model doesn't draw


def test_every_effect_matches_the_model_through_a_dome_death():
    c = run(frame_lines(40) + ["GO"] + frame_lines(118))
    # 40 normal frames, the death frame (GO + its own '0 0' frame), then
    # the 118 countdown frames
    for line in c:
        _check(line)


def test_non_dome_death_has_no_collapse():
    c = run(frame_lines(20) + ["CELLDEATH"] + frame_lines(118))
    for line in c:
        _check(line)
