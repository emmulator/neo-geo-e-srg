"""Reference model of the Vectrex game's rules around the missiles
(vectrex-e-srg v1.1.0: e-srg.c crack/surrounded/break_tile/
integrity_update/kill_ship/new_dome/respawn/new_game/missiles_update and the
dead_t/game_over handling in game_step), written from that code. The
movement and missiles come from the models tests/test_missile_play.py uses
(tests/ship_model.py, tests/mis_model.py); this adds the broken cells,
lives, integrity, deaths, respawn and GAME OVER layer. tests/test_rules_play.py
runs it beside src/rules.c + src/missiles.c (as build/rules_sim) and requires
the same state every frame.

The frame order mirrors e-srg.c game_step exactly:
  1. GAME OVER: A (button 1) starts a new game; else the dead ship's
     countdown (which may respawn it, or end the game). During these the
     ship neither moves nor fires.
  2. the ship's move and fire, and missiles_update (which can launch on the
     very frame the ship came back, and breaks tiles that reached the dome).
  3. the death checks (integrity gone -> dome death; the ship resting on a
     broken cell) and the integrity recast, so a kill next frame scores the
     integrity this frame's landings left."""
import json
import os

import mis_model as mm
import ship_model as sm

ROOT = os.path.join(os.path.dirname(__file__), "..")
V = json.load(open(os.path.join(ROOT, "tools", "vectrex_missiles.json")))
_F = json.load(open(os.path.join(ROOT, "tests", "fixtures", "vectrex_cells.json")))
ADJ = _F["cell_adj"]
# The reference values come from the Vectrex (e-srg.c v1.1.0), not from
# src/rules.h: a C constant that drifts from the Vectrex must show up as a
# difference here. (collapse count: COLLAPSE_EASY - level as in e-srg.c)
COLLAPSE_EASY = 5
DOME_LIMIT = 38
DEAD_FRAMES = 100
DEAD_FRAMES_NEO = round(DEAD_FRAMES * 59 / 50)      # 118: see ship.h's note
LEVELS = 3
A = 16


def neighbours(c):
    out = []
    for i in range(0, len(ADJ[c]), 2):
        if ADJ[c][i + 1] == 255:
            break
        out.append(ADJ[c][i + 1])
    return out


class Rules:
    def __init__(self, level=1):
        self.level = level
        self.broken = []                      # in the order they broke
        self.lives = 3
        self.integ = 100
        self.dead_t = 0
        self.dome_dead = 0
        self.game_over = 0

    # -- e-srg.c break_tile ------------------------------------------------
    def _surrounded(self, c, broken_set):
        n = b = 0
        at = COLLAPSE_EASY - self.level
        for j in neighbours(c):
            n += 1
            if j in broken_set:
                b += 1
        return b >= (n if n < at else at)

    def break_cell(self, ship, c):
        """e-srg.c break_tile: cell c breaks; whole cells with enough broken
        neighbours collapse too (COLLAPSE_EASY - level of them, all of them
        if it has fewer: rim cells), spreading from cell to cell (the
        Vectrex's todo stack). Returns the cells that broke (all of them),
        in the order they were cracked."""
        if c in ship.broken:
            return []
        broke = []
        ship.broken.add(c)
        self.broken.append(c)
        broke.append(c)
        todo = [c]
        while todo:
            x = todo.pop()
            for j in neighbours(x):
                if j not in ship.broken and self._surrounded(j, ship.broken):
                    ship.broken.add(j)
                    self.broken.append(j)
                    broke.append(j)
                    if len(todo) < 16:
                        todo.append(j)
        return broke

    # -- e-srg.c integrity_update -----------------------------------------
    def integrity_update(self):
        n = len(self.broken)
        self.integ = 0 if n >= DOME_LIMIT else 100 - ((n * 100 + DOME_LIMIT // 2) // DOME_LIMIT)

    # -- e-srg.c kill_ship / new_dome / respawn / new_game -----------------
    def kill_ship(self, ship, m, dome):
        for o in m.obj:
            o.state = 0
        ship.left = ship.lift = 0            # e-srg.c kill_ship: move_left = ship_lift = 0
        if not dome or self.level == 1:      # NORMAL: any death costs a life
            self.lives -= 1
        elif self.level == 2:                # HARD: a dome death ends the game
            self.lives = 0                   # (EASY: a dome death is free)
        self.dead_t, self.dome_dead = DEAD_FRAMES_NEO, dome

    def new_dome(self, ship):
        self.broken = []
        ship.broken = set()

    def restart(self, ship, missiles):
        """the C's new_game's clears (rules.c): the counts reset where kills
        resets, the broken state clears, and the missiles' level follows the
        rules'. fire_req is NOT cleared — the C never clears it at a new
        game (only mis_reset does, at boot), so a latched request fires in
        the new game."""
        self.broken = []
        ship.broken = set()
        missiles.level = self.level
        missiles.kills, missiles.dome_hits, missiles.score = 0, 0, 0

    def _place_only(self, ship, c):
        """as the C's ship_locate: the respawn sets the position and the
        rest state (clearing a lingering jump request — the C's
        ship_locate; the Vectrex's respawn leaves it, a quirk this port
        drops). Keeps ship.broken: only a dome death's new_dome clears it."""
        ship.cell, ship.angle, ship.lat = c, sm.STEP[c], sm.LAT[c]
        ship.left = ship.mlen = ship.lift = ship.jump_req = 0
        ship.last_dir = 8
        ship.spinning = ship.spin_acc = 0   # (ship_locate)
        ship.acc_s = ship.acc_l = ship.inc_s = ship.inc_l = 0

    def respawn(self, ship, missiles):
        if self.dome_dead:
            self.new_dome(ship)
        c = sm.FIX["cell_start"]             # the start cell, or the next whole one
        while c in ship.broken:
            c += 1
            if c == 76:
                c = 1
        self._place_only(ship, c)
        missiles.timer = round(V["spawn_first"] * 59 / 50)

    def new_game(self, ship, missiles):
        self.lives = 3
        self.restart(ship, missiles)
        self.game_over = 0
        self.dome_dead = 1
        self.respawn(ship, missiles)
        self.integrity_update()

    # -- e-srg.c game_step ------------------------------------------------
    def begin(self, ship, missiles, pressed):
        """the early branches. Returns 'busy' (the ship does not move/fire)."""
        if self.game_over:
            if pressed & A:
                self.new_game(ship, missiles)
            return True
        if self.dead_t:
            self.dead_t -= 1
            if self.dead_t == 0:
                if self.lives:
                    self.respawn(ship, missiles)
                else:
                    self.game_over = 1
            return True
        return False

    def end(self, ship, missiles):
        """the death checks and the integrity recast (e-srg.c game_step's
        late checks, gated on not dead and not game over — a death counts
        its full DEAD_FRAMES before anything is checked again). Returns
        `died`."""
        if self.dead_t or self.game_over:
            return False
        if len(self.broken) >= DOME_LIMIT:
            self.kill_ship(ship, missiles, 1)
            self.integrity_update()
            return True
        if ship.left == 0 and ship.cell in ship.broken:
            self.kill_ship(ship, missiles, 0)
            self.integrity_update()
            return True
        self.integrity_update()
        return False
