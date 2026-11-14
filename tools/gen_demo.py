"""gen_demo.py: the attract mode's demo script (the video game playing itself
behind the title pages; design docs/superpowers/specs/2026-10-26-attract-mode-design.md).

    python3 tools/gen_demo.py HEADER [--json JSON]

A simple player "AI" drives the game's own host models (tests/ship_model,
tests/mis_model, tests/rules_model, tests/radar_model, stepped exactly as
tests/hud_model.frame_model does) for one title cycle (11 pages x 295 frames),
and records the joystick byte it pressed each frame. The cart replays those
bytes through the real game code with the same game seed and level, so the
demo on screen is the real game, identical every cycle.

The AI plays in three phases:
  1. DEFEND: walk to the cell an incoming enemy is aimed at and shoot it
     (the radar locks on, enemies are shot down, the score rises);
  2. LET THROUGH: while fewer than two tiles have cracked from page 3 on,
     one enemy at a time is one it misjudges and never corrects in time: it
     fires at most twice at the wrong cell, so it lands; every other enemy
     it plays as usual (there are only two in flight at NORMAL);
  3. JUMP: jump over each cracked tile (B with the stick) when no enemy
     needs shooting.
It never steps onto a cracked tile (the model refuses that move anyway) and
it never lets an enemy land on the tile it stands on.

It plays like a person (10-28, the user's notes): one shot at a time (it
fires again only when its bullet has hit or flown off, since every bullet
from a cell flies the same line); it notices a new enemy only after a
reaction delay; and it sometimes misjudges where an enemy will land (a
neighbouring cell), fires from there and misses for real, then corrects
itself a moment after seeing the miss. Its choices come from a
random.Random seeded by the game seed, so the demo is still identical every
cycle.

The seed search keeps the first game seed whose demo shows every goal
(design goal 2): at least DEMO_MIN_KILLS enemies shot down, at least 2
cracked tiles, at least 2 jumps over a cracked tile, at least
DEMO_MIN_LOCK radar-lock frames, the ship on at least 3 different rings
(it climbs), the dome turning through at least 120 of its 240 angles; and
no ship loss, no dome collapse, no GAME OVER.

The header gives the cart:
    DEMO_SEED, DEMO_LEVEL, DEMO_FRAMES
    demo_input[] as (byte, count) runs: the BIOS-style current-input byte
                 (bit 0 up, 1 down, 2 left, 3 right, 4 A, 5 B), held for
                 count frames; the pressed byte is current & ~previous,
                 as the BIOS computes it
and the JSON (for the tests) gives the frames at which each goal happened.
"""
import argparse
import copy
import json
import os
import random
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tests"))
import hud_model as hm           # noqa: E402
import mis_model as mm           # noqa: E402
import radar_model as radm       # noqa: E402
import rules_model as rm         # noqa: E402
import ship_model as sm          # noqa: E402

PAGE_FRAMES = 295                # src/flow.c TITLE_PAGE_FRAMES
DEMO_FRAMES = 11 * PAGE_FRAMES   # one title cycle (11 pages since the high-score boards)
DEMO_LEVEL = 1                   # NORMAL (the design's call)
DEMO_MIN_KILLS = 4
DEMO_MIN_LOCK = 60
UP, DOWN, LEFT, RIGHT, A, B = 1, 2, 4, 8, 16, 32
STICKS = [UP, UP | RIGHT, RIGHT, DOWN | RIGHT, DOWN, DOWN | LEFT, LEFT, UP | LEFT]
LET_THROUGH_AT = 3 * PAGE_FRAMES     # phase 2 starts on page 3
NOTICE = (18, 50)                # frames before the AI notices a new enemy
MISJUDGE_P = 0.35                # chance it first picks a neighbouring cell
REALISE = (8, 22)                # frames after its missed bullet is gone
CELL_OF = {}
for c in range(len(mm.CELL_RING)):
    CELL_OF[(mm.CELL_RING[c], mm.CELL_PHI[c])] = c


def moves(cell, broken):
    """{next cell: (stick byte, is_jump)} reachable from a whole cell at
    rest: a walk to a whole neighbour, or a jump over a cracked one."""
    out = {}
    if cell == 0:
        return out                        # the AI never uses the peak
    for st in STICKS:
        d = sm.stick(st)
        m = sm.toward(cell, d)
        if m in (255, 0):
            continue
        if m not in broken:
            out.setdefault(m, (st, False))
        else:
            j = sm.toward(m, d)
            if j not in (255, 0) and j != cell and j not in broken:
                out.setdefault(j, (st, True))
    return out


def route(cell, goal, broken):
    """the first move of a shortest path from cell to goal, or None."""
    if cell == goal:
        return None
    prev = {cell: None}
    q = deque([cell])
    while q:
        c = q.popleft()
        for n, mv in moves(c, broken).items():
            if n not in prev:
                prev[n] = (c, mv)
                if n == goal:
                    while prev[n][0] != cell:
                        n = prev[n][0]
                    return prev[n][1]
                q.append(n)
    return None


def enemies(mis):
    return [o for o in mis.obj[:mm.NMIS] if o.state == 1]


def neighbours(cell, broken):
    return [m for m in {sm.toward(cell, sm.stick(st)) for st in STICKS}
            if m not in (255, 0, cell) and m not in broken]


def play(seed):
    """one demo cycle under the AI; returns (bytes per frame, events)."""
    ship, mis, rules = sm.Ship(), mm.Missiles(level=DEMO_LEVEL, seed=seed), rm.Rules(DEMO_LEVEL)
    radar = radm.Radar()
    rnd = random.Random(seed)
    cur_prev, out = 0, []
    ev = dict(kills=[], cracks=[], crack_jumps=[], lock=0, rings=set(), angles=set(),
              lost=None, misses=0)
    to_jump = []                          # cracked tiles still to jump over
    seen = {}                             # slot -> the AI's view of that enemy
    was_live = [False] * mm.NMIS
    shot = None                           # (slot, fired from a wrong cell) of the bullet in flight
    for f in range(DEMO_FRAMES):
        cur = 0
        broken = set(ship.broken)
        letting = f >= LET_THROUGH_AT and len(ev["cracks"]) < 2
        # new enemies: when the AI will notice each, and where it first thinks it lands
        for i, o in enumerate(mis.obj[:mm.NMIS]):
            live = o.state == 1
            if live and not was_live[i]:
                true = CELL_OF.get((o.ring, o.phi))
                wrong, victim = None, False
                victims_live = sum(1 for v in seen.values() if v["victim"])
                if letting and victims_live == 0 and true not in broken:
                    victim = True                 # one at a time: the other enemy is played
                if victim or rnd.random() < MISJUDGE_P:
                    nb = [n for n in neighbours(true, broken) if n != ship.cell] if true else []
                    wrong = rnd.choice(nb) if nb else None
                seen[i] = dict(notice=f + rnd.randint(*NOTICE), wrong=wrong, fix=None,
                               victim=victim, shots=0)
            if not live:
                seen.pop(i, None)
            was_live[i] = live
        bullet_live = any(o.state == 1 for o in mis.obj[mm.NMIS:])
        if shot is not None and not bullet_live:
            i, wrong_cell = shot
            if wrong_cell and i in seen:
                ev["misses"] += 1
                if not seen[i]["victim"]:
                    seen[i]["fix"] = f + rnd.randint(*REALISE)     # it saw the miss
            shot = None

        def aim(i):
            v = seen[i]
            if v["wrong"] is not None and (v["fix"] is None or f < v["fix"]):
                return v["wrong"], True
            o = mis.obj[i]
            return CELL_OF.get((o.ring, o.phi)), False

        if ship.left == 0 and not rules.dead_t:
            known = sorted((i for i in seen if f >= seen[i]["notice"]), key=lambda i: mis.obj[i].r)
            threat = [i for i in enemies_idx(mis) if CELL_OF.get((mis.obj[i].ring, mis.obj[i].phi)) == ship.cell]
            goal, target, jump_now = None, None, None
            defend = None
            for i in known:
                c, wrong = aim(i)
                if seen[i]["victim"] and seen[i]["shots"] >= 2:
                    continue                      # it has given up on this one
                if c is not None and c not in broken:
                    defend = (c, (i, wrong))
                    break
            if threat:
                goal, target = ship.cell, (threat[0], False)   # defend the tile we stand on
            elif defend:
                goal, target = defend             # shooting comes first; jumps fill the lulls
            elif to_jump:
                k = to_jump[0]
                # stand next to k with a whole tile beyond it, then jump
                for st in STICKS:
                    d = sm.stick(st)
                    if sm.toward(ship.cell, d) == k:
                        j = sm.toward(k, d)
                        if j not in (255, 0) and j not in broken:
                            jump_now = st
                            break
                if jump_now is None:
                    near = [n for n in range(1, len(mm.CELL_RING)) if n not in broken
                            and any(sm.toward(n, sm.stick(s)) == k and sm.toward(k, sm.stick(s)) not in (255, 0, *broken)
                                    for s in STICKS)]
                    near.sort(key=lambda n: (route(ship.cell, n, broken) is None, n))
                    goal = near[0] if near else None
            if jump_now is not None:
                cur = jump_now | B
            elif goal is not None and goal != ship.cell:
                mv = route(ship.cell, goal, broken)
                if mv:
                    cur = mv[0] | (B if mv[1] else 0)
            elif goal == ship.cell and target and not bullet_live and not (cur_prev & A):
                cur = A                       # one shot; the next only after it is gone
                shot = target
                seen[target[0]]["shots"] += 1
        pressed = cur & ~cur_prev
        was_cell, was_broken = ship.cell, set(ship.broken)
        hm.frame_model((ship, mis, rules), cur, pressed)
        radar.frame(ship, mis)
        if ship.jumped:
            mid = [k for k in was_broken if sm.toward(was_cell, sm.stick(cur & 15)) == k]
            if mid:
                ev["crack_jumps"].append((f, mid[0]))
                if mid[0] in to_jump:
                    to_jump.remove(mid[0])
        for _ in mis.hits:
            ev["kills"].append(f)
        for c in mis.lands:
            if c not in was_broken:
                ev["cracks"].append((f, c))
                if len(to_jump) + len(ev["crack_jumps"]) < 2:
                    to_jump.append(c)
        ev["lock"] += 1 if radar.locked else 0
        ev["rings"].add(mm.CELL_RING[ship.cell])
        ev["angles"].add(ship.angle)
        if rules.dead_t or rules.game_over or rules.dome_dead:
            ev["lost"] = f
            break
        out.append(cur)
        cur_prev = cur
    return out, ev


def enemies_idx(mis):
    return [i for i, o in enumerate(mis.obj[:mm.NMIS]) if o.state == 1]


def ok(ev):
    return (ev["lost"] is None and len(ev["kills"]) >= DEMO_MIN_KILLS
            and len(ev["cracks"]) >= 2 and len(ev["crack_jumps"]) >= 2
            and ev["lock"] >= DEMO_MIN_LOCK and len(ev["rings"]) >= 3
            and len(ev["angles"]) >= 120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("--json")
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--tries", type=int, default=400)
    args = ap.parse_args()
    for seed in range(args.first_seed, args.first_seed + args.tries):
        seed &= 0xFFFF
        if not seed:
            continue
        inputs, ev = play(seed)
        if ok(ev):
            break
    else:
        sys.exit("gen_demo: no seed in range gives a demo with every goal")
    runs = []
    for b in inputs:
        if runs and runs[-1][0] == b and runs[-1][1] < 255:
            runs[-1][1] += 1
        else:
            runs.append([b, 1])
    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/gen_demo.py: do not edit */\n")
        w("#ifndef DEMO_MAP_H\n#define DEMO_MAP_H\n")
        w(f"#define DEMO_SEED 0x{seed:04x}\n#define DEMO_LEVEL {DEMO_LEVEL}\n"
          f"#define DEMO_FRAMES {DEMO_FRAMES}\n#define DEMO_RUNS {len(runs)}\n")
        w("/* (current-input byte, frames held) */\n")
        w("static const u8 demo_input[DEMO_RUNS][2] = {\n")
        for i in range(0, len(runs), 8):
            w("  " + ", ".join(f"{{0x{b:02x},{n}}}" for b, n in runs[i:i + 8]) + ",\n")
        w("};\n#endif\n")
    summary = dict(seed=seed, level=DEMO_LEVEL, frames=DEMO_FRAMES, runs=len(runs),
                   kills=ev["kills"], cracks=ev["cracks"], crack_jumps=ev["crack_jumps"],
                   lock_frames=ev["lock"], rings=sorted(ev["rings"]), angles=len(ev["angles"]))
    if args.json:
        json.dump(summary, open(args.json, "w"), indent=1)
    print(f"seed 0x{seed:04x}: {len(ev['kills'])} shot down (first f {ev['kills'][:1]}), "
          f"cracks {ev['cracks']}, jumps over cracks {ev['crack_jumps']}, "
          f"lock frames {ev['lock']}, rings {sorted(ev['rings'])}, "
          f"{len(ev['angles'])} dome angles, {len(runs)} input runs")


if __name__ == "__main__":
    main()
