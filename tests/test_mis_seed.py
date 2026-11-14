"""src/missiles.c's mis_seed_from against tests/mis_model.py's mirror (Task
1): the seed a new game starts the missile RNG from, given the number of
title frames the title has been up at Start.

build/test_missiles prints one "SEED <frames> <seed>" line per case; this
test reads them and compares with the model. The frames cover 0, 1, 0xACE1
(where RNG_SEED ^ frames is 0: the zero case must return RNG_SEED), 0xFFFF
and several others, so both the XOR and the zero fallback are checked.

A game's seed must also never be 0 (xorshift16 never leaves 0: every rand8
would return 0, putting every missile at cell 0 forever), so the C checks
that itself and this test re-checks the printed seeds.
"""
import os
import subprocess

import mis_model as mm

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEST = os.path.join(ROOT, "build", "test_missiles")

FRAMES = [0, 1, 2, 0xFF, 0x100, 0x1234, 0xACE1, 0xFFFE, 0xFFFF]


def seeds_from_c():
    """[(frames, seed)] from the host test's SEED lines."""
    out = subprocess.run([TEST], capture_output=True, text=True, check=True).stdout
    seeds = []
    for line in out.splitlines():
        p = line.split()
        if p and p[0] == "SEED":
            seeds.append((int(p[1]), int(p[2])))
    return seeds


def test_mis_seed_from_matches_the_model():
    seeds = seeds_from_c()
    assert seeds, "build/test_missiles printed no SEED lines"
    got = dict(seeds)
    # the C's own cases (tests/test_missiles.c): every one must equal the model
    for f in FRAMES:
        assert f in got, f"the C did not test frame {f:#06x}"
        assert got[f] == mm.mis_seed_from(f), (
            f"frames {f:#06x}: C {got[f]:#06x} != model {mm.mis_seed_from(f):#06x}")
    # the stated properties: the XOR, except at 0 where it falls back
    assert got[0] == 0xACE1
    assert got[0xACE1] == 0xACE1
    assert got[1] == 0xACE0
    assert got[0xFFFF] == 0x531E
    assert all(s != 0 for _f, s in seeds)


def test_the_zero_case_is_the_seed_itself():
    """the model's mirror of the C's fallback: RNG_SEED ^ 0 is RNG_SEED (not
    0), and RNG_SEED ^ RNG_SEED is 0 -> RNG_SEED."""
    assert mm.mis_seed_from(0) == mm.RNG_SEED
    assert mm.mis_seed_from(mm.RNG_SEED) == mm.RNG_SEED
    for f in range(0, 0x10000, 0x101):
        assert mm.mis_seed_from(f) != 0
