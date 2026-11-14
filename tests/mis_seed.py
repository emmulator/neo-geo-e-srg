"""The shared Task 1 helper the missile-model boot checkers use: where the
cart's new game started the missile RNG.

A game's seed is mis_seed_from(the title frames at Start) (src/flow.c
game_begin, src/missiles.c) instead of RNG_SEED, so a checker that replays
tests/mis_model.py from a probe's recorded inputs must start its Missiles at
the CART's seed — mis_seed_used, which the probe writes as

    SEED <mame frame> <seed>

(scripts/mis_seed.lua). The probes write it once the game has begun; the
parsers in the checkers pick the SEED line up like their other records and
pass the seed here. Before Task 1 no SEED line existed and every checker
built its model at 0xACE1 (mis_model.RNG_SEED); the fallback below keeps
that for an old probe dump (or a build whose seed address was not read).
"""
import mis_model as mm


def cart_seed(probe, seeds=None):
    """the cart's mis_seed_used from a probe dump, or mis_model.RNG_SEED when
    the probe recorded none. `probe` is the dump path; `seeds` an already
    parsed {mame frame: seed} (the checkers' parse() builds these)."""
    if seeds:
        return seeds[min(seeds)]
    if probe is None:
        return mm.RNG_SEED
    best = None
    with open(probe, "rb") as fh:
        for raw in fh:
            p = raw.decode("ascii", "replace").split()
            if p and p[0] == "SEED":
                n, s = int(p[1]), int(p[2])
                if best is None or n < best[0]:
                    best = (n, s)
    return best[1] if best is not None else mm.RNG_SEED


def first_missile(probe):
    """the first missile the cart launched: (mame frame, ring, phi) from the
    probe's FIRST line, or None (the variety proof)."""
    with open(probe, "rb") as fh:
        for raw in fh:
            p = raw.decode("ascii", "replace").split()
            if p and p[0] == "FIRST":
                return int(p[1]), int(p[2]), int(p[3])
    return None
