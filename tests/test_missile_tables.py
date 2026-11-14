"""The missile tables: rings and azimuths as the Vectrex game's, its flight
starts, its speeds x 50/59, and the projection constants."""
import json
import math
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_missiles as gm  # noqa: E402

V = json.load(open(os.path.join(ROOT, "tools", "vectrex_missiles.json")))
H = open(os.path.join(ROOT, "build", "missiles_tables.h")).read()


def arr(name):
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % re.escape(name), H, re.S).group(1)
    return [int(n) for n in re.findall(r"-?\d+", body)]


def define(name):
    return int(re.search(r"#define %s\s+(-?\d+)" % name, H).group(1))


def test_rings_match_the_vectrex():
    T = gm.tables()
    assert len(T["th"]) == 12
    assert T["ring_end"] == V["ring_end"] == arr("mis_ring_end")
    assert T["ring"] == V["cell_ring"] == arr("mis_cell_ring")
    assert T["phi"] == V["cell_phi"] == arr("mis_cell_phi")


def test_flights_are_the_vectrex_ones_at_59_hz():
    assert arr("mis_r_spawn") == V["r_spawn"]
    assert define("MIS_R_LAND") == V["r_unit"] == 1 << 19
    assert arr("mis_dr") == [round(v * 64 * 50 / 59) for v in V["speed_val"]]
    assert arr("mis_dr_easy") == [round(v * 64 * 50 / 59) for v in V["speed_easy"]]
    assert len(arr("mis_dr_easy")) == len(arr("mis_dr"))
    assert define("BUL_R0") == V["bullet_r0"]
    assert define("BUL_DR") == round(V["bullet_dr"] * 50 / 59)
    # a missile launched at the base speed takes as long (in seconds) as on the Vectrex
    for k in range(12):
        ng = (V["r_spawn"][k] - V["r_unit"]) / arr("mis_dr")[0] / 59.185
        vx = (V["r_spawn"][k] - V["r_unit"]) / (64 * V["speed_val"][0]) / 50
        assert abs(ng - vx) / vx < 0.005, k
    # EASY's missiles are 0.75x of NORMAL's at every speed step (v1.1.0):
    # the Vectrex's own table, {61, 73, 86, 98, 123}, is 0.75x rounded to
    # its whole units, so the check is on its units, not on mis_dr's
    assert V["speed_easy"] == [61, 73, 86, 98, 123]
    for e, v in zip(V["speed_easy"], V["speed_val"]):
        assert abs(e - 0.75 * v) <= 0.5, (e, v)


def test_bullet_lives():
    life = arr("bul_life")
    assert len(life) == 12 and all(1 <= x <= 255 for x in life)
    far = define("BUL_LIFE_FAR")
    assert far == math.ceil((6.0 * V["r_unit"] - V["bullet_r0"]) / define("BUL_DR"))
    # far enough to meet a missile anywhere up to its launch
    assert V["bullet_r0"] + far * define("BUL_DR") >= max(V["r_spawn"])


def test_projection_tables():
    s = arr("mis_sin")
    assert len(s) == 240 and s[0] == 0 and s[60] == 16384 and s[120] == 0 and s[180] == -16384
    occ = arr("mis_occ")
    assert len(occ) == 12 * 121
    rows = [occ[k * 121:(k + 1) * 121] for k in range(12)]
    assert all(r[0] == 4096 for r in rows)               # nothing hides a missile over the front
    assert all(x >= 4096 for x in occ)                   # (never below the surface)
    assert all(rows[k][120] > 4096 for k in range(4, 12))   # the dome hides the back
