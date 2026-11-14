"""The ship's movement tables: the same as the Vectrex game's (v1.0.0), so
the same stick input moves the ship along the same cells."""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_cells  # noqa: E402

FIX = json.load(open(os.path.join(ROOT, "tests", "fixtures", "vectrex_cells.json")))
HEADER = os.path.join(ROOT, "build", "cells.h")


def test_tables_match_the_vectrex():
    c = gen_cells.tables()
    assert c["n"] == len(FIX["cell_step"]) == 76
    assert c["step"] == FIX["cell_step"]
    assert c["lat"] == FIX["cell_lat"]
    assert [[x for pair in row for x in pair] for row in c["adj"]] == FIX["cell_adj"]
    assert c["peak_down"] == FIX["peak_down"]
    assert gen_cells.start_cell(c) == FIX["cell_start"]


def toward(adj, c, d):              # e-srg.c cell_toward
    best, bd, want = 255, 32, (d * 8) & 255
    for i in range(6):
        if adj[c][2 * i + 1] == 255:
            break
        e = (adj[c][2 * i] - want) & 255
        e = (256 - e) & 255 if e & 128 else e
        if e < bd:
            best, bd = adj[c][2 * i + 1], e
    return best


def test_eight_directions_reach_every_neighbour():
    # the Vectrex stick has 32 directions, the Neo Geo's 8: every neighbour
    # of every cell (but the peak, which moves by "down") must still be one
    # push away
    adj = FIX["cell_adj"]
    for c in range(1, 76):
        nbrs = {adj[c][2 * i + 1] for i in range(6)} - {255}
        got = {toward(adj, c, d) for d in range(0, 32, 4)} - {255}
        assert nbrs == got, f"cell {c}: unreachable {sorted(nbrs - got)}"


def array(text, name):
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % re.escape(name), text, re.S).group(1)
    return [int(n) for n in re.findall(r"\d+", body)]


def test_header_holds_the_tables():
    text = open(HEADER).read()
    assert "#define NCELLS     76" in text
    assert "#define CELL_START %d" % FIX["cell_start"] in text
    assert array(text, "cell_step") == FIX["cell_step"]
    assert array(text, "cell_lat") == FIX["cell_lat"]
    assert array(text, "cell_adj") == [x for row in FIX["cell_adj"] for x in row]
    assert array(text, "peak_down") == FIX["peak_down"]
