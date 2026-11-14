"""Reference model of the Vectrex game's missiles and bullets (vectrex-e-srg
v1.1.0: e-srg.c rand8/spawn/free_target/fire/collide/missiles_update,
missile_draw.s missiles_step), written from that code. Ring tables and
flight starts come from the Vectrex (tools/vectrex_missiles.json), speeds
are its per-frame values x 50/59 (speed_easy for EASY, 0.75x of speed_val,
v1.1.0), frame counts x 59/50; only the bullets' lives, which depend on the
Neo Geo screen, come from build/missiles_tables.h.
tests/test_missile_play.py runs it beside src/missiles.c and requires the
same state every frame.

The target rings open to every ring once 6 missiles were shot down
(low_rings_at) OR 6 missiles have hit the dome, each breaking a whole cell
(hits, e-srg.c v1.0.1: hits++ in break_tile after its is_broken early
return — a missile landing on a cell that broke after it launched does not
count). The count resets where kills resets, at a new game. Everything else
stays v1.1.0: the random sequence, the 8 tries, the spawn timing. mis_frame
(the M3 path, no rules and no broken set) counts every landing, because it
can't know — only mis_update's landings run through the rules."""
import json
import os
import re

import ship_model as sm

ROOT = os.path.join(os.path.dirname(__file__), "..")
V = json.load(open(os.path.join(ROOT, "tools", "vectrex_missiles.json")))
_T = open(os.path.join(ROOT, "build", "missiles_tables.h")).read()
BUL_LIFE = [int(x) for x in re.findall(r"\d+", re.search(r"bul_life\[[^=]*=\s*\{(.*?)\}", _T, re.S).group(1))]
BUL_LIFE_FAR = int(re.search(r"#define BUL_LIFE_FAR\s+(\d+)", _T).group(1))
RING_END, CELL_RING, CELL_PHI = V["ring_end"], V["cell_ring"], V["cell_phi"]
R_SPAWN, LAND = V["r_spawn"], V["r_unit"]
DR = [round(v * 64 * 50 / 59) for v in V["speed_val"]]
DR_EASY = [round(v * 64 * 50 / 59) for v in V["speed_easy"]]
BUL_R0, BUL_DR = V["bullet_r0"], round(V["bullet_dr"] * 50 / 59)
NMIS, NBUL = V["nmis"], V["nbul"]
MIS_SPEEDS = len(DR)
WAVE_RINGS, LOW_RINGS_AT = V["wave_rings"], V["low_rings_at"]
# v1.1.0 (e-srg.c): hits and kills open the rings at the same low_rings_at.
# The M3 frame (mis_frame) keeps counting every landing and opening at
# LOW_RINGS_AT too (see the module docstring).
LEVEL_EASY, LEVEL_NORMAL, LEVEL_HARD = 0, 1, 2
A = 16
# M7: the frame's sound events, the same bitmask as src/missiles.h (SFX_FIRE
# = a bullet left, SFX_HIT = a missile shot down, SFX_CRACK = a landing
# broke a fresh cell)
SFX_FIRE, SFX_HIT, SFX_CRACK = 1, 2, 4
RNG_SEED = V["rng_seed"]


def mis_seed_from(frames):
    """src/missiles.c's mis_seed_from: RNG_SEED ^ frames, and RNG_SEED
    instead if that is 0 (xorshift16 never leaves 0)."""
    s = (RNG_SEED ^ frames) & 0xFFFF
    return s if s else RNG_SEED



class Obj:
    def __init__(self):
        self.state = self.kind = self.ring = self.phi = self.life = self.r = self.dr = 0

    def row(self):
        return (self.state, self.kind, self.ring, self.phi, self.life, self.r)


class Missiles:
    def __init__(self, level=LEVEL_NORMAL, seed=None):
        self.level = level
        self.obj = [Obj() for _ in range(NMIS + NBUL)]
        # a new game's seed comes from the title's time (flow.c game_begin):
        # the boot checkers pass the cart's mis_seed_used; the host tests
        # leave it RNG_SEED, as mis_reset does
        self.rng = RNG_SEED if seed is None else seed
        self.timer = round(V["spawn_first"] * 59 / 50)
        self.kills = self.score = self.fire_req = 0
        self.dome_hits = 0              # missiles whose landing broke a cell
        self.integ = 100
        self.hits, self.lands = [], []
        self.sfx = 0                    # M7: this frame's sound events

    def rand8(self):
        r = self.rng
        r ^= (r << 7) & 0xFFFF
        r ^= r >> 9
        r ^= (r << 8) & 0xFFFF
        self.rng = r
        return r & 0xFF

    def rand_below(self, n):
        r = self.rand8()
        while r >= n:
            r -= n
        return r

    def free_target(self, c, broken):
        if c in broken:
            return False
        return not any(o.state == 1 and o.ring == CELL_RING[c] and o.phi == CELL_PHI[c]
                       for o in self.obj[:NMIS])

    def speed(self, k):
        """the speed step's per-frame approach: EASY's own table (0.75x),
        NORMAL/HARD the Vectrex's (e-srg.c v1.1.0 spawn: fl_spd =
        (level ? speed_val : speed_easy)[k])."""
        return (DR_EASY if self.level == LEVEL_EASY else DR)[k]

    def spawn(self, o, broken):
        rings = 12 if self.kills >= V["low_rings_at"] or self.dome_hits >= V["low_rings_at"] \
            else V["wave_rings"]
        k = 8
        while True:
            c = self.rand_below(RING_END[rings - 1])
            if self.free_target(c, broken):
                break
            k -= 1
            if k == 0:
                break
        if not self.free_target(c, broken):
            return
        o.ring, o.phi = CELL_RING[c], CELL_PHI[c]
        o.r = R_SPAWN[o.ring]
        k = max(i for i, s in enumerate(V["speed_score"]) if self.score >= s)
        o.dr, o.kind, o.state = self.speed(k), 0, 1

    def fire(self, cell):
        free = [b for b in self.obj[NMIS:] if not b.state]
        if not free:
            return False                 # no free slot: no shot, no sound
        b = free[0]
        b.ring, b.phi, b.r, b.dr = CELL_RING[cell], CELL_PHI[cell], BUL_R0, BUL_DR
        b.life = BUL_LIFE[b.ring]
        if any(o.state == 1 and o.ring == b.ring and o.phi == b.phi for o in self.obj[:NMIS]):
            b.life = BUL_LIFE_FAR
        b.kind, b.state = 1, 1
        self.sfx |= SFX_FIRE            # M7: a bullet left
        return True

    def frame(self, ship, pressed):
        self.sfx = 0                    # M7: cleared at the frame's start
        if pressed & A:
            self.fire_req = 1
        if self.fire_req and not ship.left:
            self.fire(ship.cell)
            self.fire_req = 0
        self.hits, self.lands = [], []
        for o in self.obj:                                  # missiles_step
            if o.state != 1:
                continue
            if o.kind:
                o.r += o.dr
                o.life -= 1
                if o.life == 0:
                    o.state = 0
            else:
                o.r -= o.dr
                if o.r <= LAND:
                    o.state = 2
        for b in self.obj[NMIS:]:                           # collide
            if b.state != 1:
                continue
            for o in self.obj[:NMIS]:
                if o.state == 1 and o.phi == b.phi and o.ring == b.ring and b.r >= o.r:
                    self.hits.append((o.ring, o.phi, o.r))
                    self.kills = min(255, self.kills + 1)
                    self.score = min(9999999, self.score + self.integ)
                    self.sfx |= SFX_HIT         # M7: a missile shot down
                    o.state = b.state = 0
                    break
        live = 0
        for o in self.obj[:NMIS]:
            if o.state == 2:
                c = RING_END[o.ring - 1] if o.ring else 0
                while CELL_PHI[c] != o.phi:
                    c += 1
                self.lands.append(c)
                # the M3 frame (mis_frame): every landing counts, because it
                # has no rules and no broken set (see the module docstring);
                # mis_update's landings go through the rules and count only
                # the fresh breaks.
                broke = 1 if c not in ship.broken else 0
                if broke:
                    self.sfx |= SFX_CRACK      # M7: a landing broke a fresh cell
                self.dome_hits = min(255, self.dome_hits + 1)
                o.state = 0
            if o.state:
                live += 1
        if self.timer:
            self.timer -= 1
            return
        if live >= V["wave_live"]:
            return
        o = next(o for o in self.obj if not o.state)
        self.spawn(o, ship.broken)
        self.timer = ((V["spawn_gap"] + (self.rand8() & 63)) * 59 + 25) // 50

    def line(self, ship):
        out = f"{ship.cell} {ship.left} | {self.timer} {self.kills} {self.dome_hits} {self.score} |"
        out += "".join(f" h{r}:{p}:{x}" for r, p, x in self.hits)
        out += "".join(f" l{c}" for c in self.lands)
        out += " |" + "".join(" %d %d %d %d %d %d" % o.row() for o in self.obj)
        out += f" | {self.sfx}"          # M7: the frame's sound-event bitmask
        return out
