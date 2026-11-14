#!/usr/bin/env python3
"""The Vectrex 1.1.0 stall check: per level, the fewest missile landings
that can break all 26 cells of rings 0-4 (the wave), searched over the
rules.

Until kills >= low_rings_at, e-srg.c v1.1.0 spawn only targets cells in
rings 0-4 (and once hits >= low_rings_at, where a hit is a missile whose
landing broke a whole cell, every ring opens — so the wave must be gone
BEFORE the 6th such hit for a stall to be reachable). If all 26 wave cells
break before either condition opens the outer rings, no launch can succeed
and the game stalls forever. Collapses spread (rules_break_cell: a whole
cell with COLLAPSE_EASY - level broken neighbours breaks too), so one
landing can break several cells: the question is how few landings can do
it.

The break rule is monotone (broken cells only ever accrue) and order-
independent (its least fixpoint), so a sequence of landings is equivalent
to the SET of cells landed on: the fewest landings = the smallest subset of
wave cells whose break-closure covers all 26. (A minimal such set never
contains a cell the cascade breaks early, and the spawned missile always
targets a whole cell, so every landing in it is real.) The search below
enumerates those subsets by branch-and-bound over the wave cells, pruning
with the closure of all remaining candidates.

With the threshold at LOW_RINGS_AT, the stall is reachable iff the fewest
landings is <= LOW_RINGS_AT - 1: each of those landings breaks a whole
cell, so the 6th such hit opens every ring, and the wave must be fully
breakable in at most 5 landings for the game to keep spawning wave-only
missiles at nothing. On this geometry it is not (the exact search finds
the fewest at 7 landings for HARD, 14 for NORMAL, 18 for EASY — verified
by `fewest(level)`, the exact search below), so the answer is NO for all
three levels. The check itself needs only the <= 5 search, which is what
main() bounds itself to (it runs in seconds, so tests/test_fewest_landings.py
runs this tool as a pytest).
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
F = json.load(open(os.path.join(ROOT, "tests", "fixtures", "vectrex_cells.json")))
V = json.load(open(os.path.join(ROOT, "tools", "vectrex_missiles.json")))
ADJ = F["cell_adj"]
RING = V["cell_ring"]
WAVE_RINGS = V["wave_rings"]          # rings 0 .. WAVE_RINGS-1
LOW_RINGS_AT = V["low_rings_at"]      # kills or fresh-break hits: open the rings

NBR = []                              # bitmask of each cell's neighbours
NBIN = []                             # ... and how many
for c in range(76):
    m = 0
    for i in range(0, len(ADJ[c]), 2):
        if ADJ[c][i + 1] == 255:
            break
        m |= 1 << ADJ[c][i + 1]
    NBR.append(m)
    NBIN.append(bin(m).count("1"))

WAVE = [c for c in range(76) if RING[c] < WAVE_RINGS]
WAVE_MASK = 0
for c in WAVE:
    WAVE_MASK |= 1 << c


def closure(mask, level):
    """rules_break_cell's spread to a fixpoint: every whole cell with
    COLLAPSE_EASY - level broken neighbours breaks too (all of its
    neighbours if it has fewer: rim cells)."""
    at = 5 - level
    changed = True
    while changed:
        changed = False
        for x in range(76):
            if mask & (1 << x):
                continue
            b = bin(NBR[x] & mask).count("1")
            n = NBIN[x]
            if b >= (n if n < at else at):
                mask |= 1 << x
                changed = True
    return mask


def fewest(level, kmax=26):
    """the smallest subset of wave cells whose closure covers the wave, by
    branch-and-bound over the cells (try the densest first)."""
    order = sorted(WAVE, key=lambda c: -NBIN[c])
    n = len(order)
    # the closure of all remaining candidates order[i:], the strongest
    # bound on what this branch can still reach.
    suffix = [0] * (n + 1)
    mk = 0
    for i in range(n - 1, -1, -1):
        mk = closure(mk | (1 << order[i]), level)
        suffix[i] = mk
    solutions = []

    def dfs(i, mask, chosen, k):
        if mask & WAVE_MASK == WAVE_MASK:
            solutions.append((len(chosen), list(chosen), bin(mask).count("1")))
            return True
        if len(chosen) >= k or i >= n:
            return False
        c = order[i]
        if closure(mask | suffix[i], level) & WAVE_MASK != WAVE_MASK:
            return False                      # even all the rest cannot cover
        if not (mask & (1 << c)):             # land on c (it is still whole)
            if dfs(i + 1, closure(mask | (1 << c), level), chosen + [c], k):
                return True
        return dfs(i + 1, mask, chosen, k)    # or skip it

    for k in range(1, kmax + 1):
        if dfs(0, 0, [], k):
            return solutions[-1]
    return None


def main():
    ok = True
    for level in (0, 1, 2):
        # the stall check: reachable iff the wave can break in fewer than
        # LOW_RINGS_AT landings (each a fresh break, so hits == landings);
        # the bound search is what the pytest runs. The exact fewest
        # (7 HARD / 14 NORMAL / 18 EASY) is in the module docstring.
        sol = fewest(level, kmax=LOW_RINGS_AT - 1)
        reachable = sol is not None
        if reachable:
            print(f"level {level} (collapse {5 - level}): the wave can break "
                  f"in {sol[0]} landings (<= {LOW_RINGS_AT - 1}): the stall "
                  f"is still reachable — YES")
            ok = False
        else:
            print(f"level {level} (collapse {5 - level}): the wave needs more "
                  f"than {LOW_RINGS_AT - 1} landings to break: it cannot be "
                  f"gone before the {LOW_RINGS_AT}th fresh-break hit opens "
                  f"every ring — NO")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
