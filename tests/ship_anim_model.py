"""Reference model of src/ship_gfx.c's ship_frame_of and of the game's frame
order around it (the C sim tests/spider_sim.c links the real ship.c /
missiles.c / rules.c and calls the real ship_frame_of; this model is the
host and MAME checker's expected picture sequence).

The timing is the stopper-spider design's (docs/superpowers/specs/
2026-10-26-stopper-spider-design.md, the plan's Global Constraints):

  walk   F_WALK + elapsed * 4 / SHIP_MOVE_FRAMES while a move runs or the
         ship spins at the peak; the frame a move ends keeps the last walk
         picture, so a jump that starts next frame goes walk -> scrunch
         with no REST between (Review Focus 1);
  jump   over SHIP_JUMP_FRAMES: scrunch 0..6, launch 7..10, airborne
         11..20, land 21..27;
  heave  4 pictures of 3 game frames each from the frame a shot leaves
         (Review Focus 2: a shot on the landing frame starts it at once);
         a new shot restarts it;
  REST   otherwise.

The animation state is the cart's ship_anim_t: walk_t, heave_t (None when
idle), was_moving and was_move. It is reset to REST by a hide/respawn, a
game start and a demo restart.
"""
import os
import re

import mis_model
import rules_model
import ship_model as sm

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_H = open(os.path.join(ROOT, "build", "ship_map.h")).read()
F_REST, F_WALK, F_JUMP, F_HEAVE = (
    int(re.search(r"#define SHIP_F_%s\s+(\d+)" % n, _H).group(1))
    for n in ("REST", "WALK", "JUMP", "HEAVE"))
HEAVE_NONE = 0xff
HEAVE_FRAMES = 12


class Anim:
    def __init__(self):
        self.rest()

    def rest(self):
        self.walk_t = 0
        self.heave_t = HEAVE_NONE
        self.was_moving = 0
        self.was_move = 0

    def frame_of(self, ship, shot):
        """src/ship_gfx.c ship_frame_of, field by field."""
        move = 1 if ship.left else 0
        moving = 1 if (move or ship.spinning) else 0
        jump = 1 if (move and ship.mlen == sm.JUMP) else 0
        walk_end = 1 if (not moving and self.was_move
                         and ship.mlen == sm.MOVE) else 0

        if shot:
            self.heave_t = 0
            self.was_moving = moving
            self.was_move = move
            return F_HEAVE

        if self.heave_t != HEAVE_NONE:
            self.heave_t += 1
            if self.heave_t >= HEAVE_FRAMES:
                self.heave_t = HEAVE_NONE

        if moving:
            if not self.was_moving:
                self.walk_t = 0
            elif self.walk_t < sm.MOVE:
                self.walk_t += 1
            self.heave_t = HEAVE_NONE
        elif walk_end:
            if self.walk_t < sm.MOVE:
                self.walk_t += 1
        else:
            self.walk_t = 0
        self.was_moving = moving
        self.was_move = move

        if jump:
            t = sm.JUMP - ship.left
            if t <= 6:
                return F_JUMP
            if t <= 10:
                return F_JUMP + 1
            if t <= 20:
                return F_JUMP + 2
            return F_JUMP + 3
        if moving or walk_end:
            t = self.walk_t
            if t >= sm.MOVE:
                t = sm.MOVE - 1
            return F_WALK + (t * 4) // sm.MOVE
        if self.heave_t != HEAVE_NONE:
            return F_HEAVE + self.heave_t // 3
        return F_REST


def game_frame(ship, mis, rules, inp, pressed):
    """one frame as src/flow.c game_frame_in and src/missiles.c mis_update:
    rules_begin, ship_frame (when not busy), mis_update, rules_end. Returns
    (shot, frame, dead); the animation is not advanced here."""
    busy = rules.begin(ship, mis, pressed)
    if not busy:
        ship.frame(inp, pressed)
    mis.sfx = 0
    if not busy:
        if pressed & mis_model.A:
            mis.fire_req = 1
        if mis.fire_req and not ship.left:
            mis.fire(ship.cell)
            mis.fire_req = 0
    mis.hits, mis.lands = [], []
    for o in mis.obj:
        if o.state != 1:
            continue
        if o.kind:
            o.r += o.dr
            o.life -= 1
            if o.life == 0:
                o.state = 0
        else:
            o.r -= o.dr
            if o.r <= mis_model.LAND:
                o.state = 2
    for b in mis.obj[mis_model.NMIS:]:
        if b.state != 1:
            continue
        for o in mis.obj[:mis_model.NMIS]:
            if o.state == 1 and o.phi == b.phi and o.ring == b.ring and b.r >= o.r:
                mis.hits.append((o.ring, o.phi, o.r))
                mis.kills = min(255, mis.kills + 1)
                mis.score = min(9999999, mis.score + rules.integ)
                mis.sfx |= mis_model.SFX_HIT
                o.state = b.state = 0
                break
    live = 0
    for o in mis.obj[:mis_model.NMIS]:
        if o.state == 2:
            c = mis_model.RING_END[o.ring - 1] if o.ring else 0
            while mis_model.CELL_PHI[c] != o.phi:
                c += 1
            mis.lands.append(c)
            if c not in ship.broken:
                mis.dome_hits = min(255, mis.dome_hits + 1)
                mis.sfx |= mis_model.SFX_CRACK
                rules.break_cell(ship, c)
            o.state = 0
        if o.state:
            live += 1
    if not (rules.dead_t or rules.game_over):
        if mis.timer:
            mis.timer -= 1
        elif live < mis_model.V["wave_live"]:
            o = next(o for o in mis.obj if not o.state)
            mis.spawn(o, ship.broken)
            mis.timer = ((mis_model.V["spawn_gap"] + (mis.rand8() & 63)) * 59 + 25) // 50
    rules.end(ship, mis)
    mis.integ = rules.integ
    dead = 1 if (rules.dead_t or rules.game_over) else 0
    return (mis.sfx & mis_model.SFX_FIRE), dead


def run_commands(commands):
    """drive the same commands tests/spider_sim.c reads and return one
    output tuple per frame: (cell, move_left, mlen, angle, lat, lift,
    jumped, spinning, shot, frame, dead, game_over)."""
    ship = sm.Ship()
    mis = mis_model.Missiles()
    rules = sm_rules()
    anim = Anim()
    out = []
    for cmd in commands:
        if cmd[0] == "G":
            _, seed, level = cmd
            ship = sm.Ship()
            mis = mis_model.Missiles(level=level, seed=seed)
            rules = sm_rules()
            anim.rest()
        elif cmd[0] == "P":
            ship.place(cmd[1])
            anim.rest()
        elif cmd[0] == "L":
            # ship_locate: cell/angle/lat and the move fields, keeping broken
            broken = set(ship.broken)
            ship.place(cmd[1])
            ship.broken = broken
            anim.rest()
        elif cmd[0] == "B":
            ship.broken.add(cmd[1])
        elif cmd[0] == "R":
            anim.rest()
        else:
            inp, pressed = cmd
            shot, dead = game_frame(ship, mis, rules, inp, pressed)
            if dead:
                anim.rest()
                frame = F_REST
            else:
                frame = anim.frame_of(ship, shot)
            out.append((ship.cell, ship.left, ship.mlen, ship.angle, ship.lat,
                        ship.lift, ship.jumped, ship.spinning, shot, frame,
                        dead, rules.game_over))
    return out


def sm_rules():
    return rules_model.Rules(1)
