"""The Vectrex 1.1.0 stall check (tools/fewest_landings.py): the target rings
open at LOW_RINGS_AT (6) kills OR 6 hits that broke a whole cell, so a game
that breaks the whole wave first can never withhold launches — the stall is
closed on every level. Reachable iff the fewest landings that break all 26
wave cells is <= LOW_RINGS_AT - 1 (the 6th fresh hit opens every ring); the
tool must print NO for EASY, NORMAL and HARD."""
import os
import subprocess

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_fewest_landings_closes_the_stall():
    out = subprocess.run(["python3", os.path.join(ROOT, "tools", "fewest_landings.py")],
                         capture_output=True, text=True, check=True).stdout
    for level in (0, 1, 2):
        line = next(l for l in out.splitlines() if l.startswith(f"level {level} "))
        assert line.rstrip().endswith("NO"), line
