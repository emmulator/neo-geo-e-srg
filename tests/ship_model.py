"""Reference model of the Vectrex game's ship movement (vectrex-e-srg v1.0.0:
e-srg.c ship_input/cell_toward, ship_move.s), written from that code against
the Vectrex's own tables (tests/fixtures/vectrex_cells.json), with the Neo
Geo's frame counts (src/ship.h). tests/test_ship_paths.py runs it beside
src/ship.c on the same input and requires identical states every frame."""
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIX = json.load(open(os.path.join(ROOT, "tests", "fixtures", "vectrex_cells.json")))
_H = open(os.path.join(ROOT, "src", "ship.h")).read()
MOVE, JUMP, LIFT, TURN = (int(re.search(r"#define %s\s+(\d+)" % n, _H).group(1))
                          for n in ("SHIP_MOVE_FRAMES", "SHIP_JUMP_FRAMES", "SHIP_LIFT_PX", "SHIP_TURN"))
SPIN_NUM, SPIN_DEN = (int(re.search(r"#define %s\s+(\d+)" % n, _H).group(1))
                      for n in ("SHIP_SPIN_NUM", "SHIP_SPIN_DEN"))
STEP, LAT, ADJ, PEAK_DOWN = FIX["cell_step"], FIX["cell_lat"], FIX["cell_adj"], FIX["peak_down"]
UP, DOWN, LEFT, RIGHT, B = 1, 2, 4, 8, 32


def tdiv(a, b):
    """C's integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def stick(inp):
    """8-way stick -> Vectrex stick direction (0 right, 8 up, ... of 32); None = centred."""
    x = (1 if inp & RIGHT else 0) - (1 if inp & LEFT else 0)
    y = (1 if inp & UP else 0) - (1 if inp & DOWN else 0)
    return {(1, 0): 0, (1, 1): 4, (0, 1): 8, (-1, 1): 12, (-1, 0): 16,
            (-1, -1): 20, (0, -1): 24, (1, -1): 28}.get((x, y))


def toward(c, d):
    best, bd, want = 255, 32, (d * 8) & 255
    a = ADJ[c]
    for i in range(6):
        if a[2 * i + 1] == 255:
            break
        e = (a[2 * i] - want) & 255
        if e & 128:
            e = (256 - e) & 255
        if e < bd:
            best, bd = a[2 * i + 1], e
    return best


class Ship:
    def __init__(self, cell=FIX["cell_start"]):
        self.place(cell)

    def place(self, cell):
        self.cell, self.angle, self.lat = cell, STEP[cell], LAT[cell]
        self.left = self.mlen = self.lift = self.jump_req = 0
        self.last_dir = 8
        self.jumped = 0                 # M7: 1 on the frame a jump started
        self.spinning = self.spin_acc = 0
        self.acc_s = self.acc_l = self.inc_s = self.inc_l = 0
        self.broken = set()

    def state(self):
        return (self.cell, self.left, self.angle, self.lat, self.lift)

    def start(self, to, n):
        self.mlen = self.left = n
        self.cell = to
        self.jumped = 1 if n == JUMP else 0     # M7: a jump just started
        ds = 0
        if to != 0:
            ds = STEP[to] - self.angle
            if ds > TURN // 2:
                ds -= TURN
            elif ds < -(TURN // 2):
                ds += TURN
        self.inc_s = tdiv(ds << 16, n)
        self.inc_l = tdiv((LAT[to] - self.lat) << 16, n)
        self.acc_s, self.acc_l = self.angle << 16, self.lat << 16

    def step(self):
        self.acc_s += self.inc_s
        if self.acc_s >= TURN << 16:
            self.acc_s -= TURN << 16
        elif self.acc_s < 0:
            self.acc_s += TURN << 16
        self.angle = (self.acc_s + 0x8000) >> 16
        if self.angle >= TURN:
            self.angle = 0
        self.acc_l += self.inc_l
        self.lat = (self.acc_l + 0x8000) >> 16
        self.left -= 1
        if self.mlen == JUMP:
            k = self.left
            self.lift = 4 * LIFT * k * (JUMP - k) // (JUMP * JUMP)
        if self.left == 0:
            self.lift = 0
            if self.cell != 0:
                self.angle = STEP[self.cell]
            self.lat = LAT[self.cell]

    def spin_due(self, was):
        """the peak's spin at the Vectrex's 50 steps a second (src/ship.c spin_due)"""
        self.spinning = 1
        if not was:
            self.spin_acc = SPIN_DEN - SPIN_NUM
        self.spin_acc += SPIN_NUM
        if self.spin_acc < SPIN_DEN:
            return False
        self.spin_acc -= SPIN_DEN
        return True

    def frame(self, inp, pressed):
        self.jumped = 0                 # M7: cleared at the frame's start
        was, self.spinning = self.spinning, 0
        if pressed & B:
            self.jump_req = 1
        if self.left:
            self.step()
            return
        d = stick(inp)
        if d is None:
            if not self.jump_req:
                return
            d = self.last_dir
        else:
            self.last_dir = d
        v = self.angle % len(PEAK_DOWN)
        if self.jump_req:
            self.jump_req = 0
            if self.cell != 0:
                m = toward(self.cell, d)
            else:
                m = PEAK_DOWN[v] if 19 <= d <= 29 else 255
            if m not in (255, 0):
                m = toward(m, d)
                if m != 255 and m != self.cell and m not in self.broken:
                    self.start(m, JUMP)
            return
        if self.cell != 0:
            m = toward(self.cell, d)
            if m != 255 and m not in self.broken:
                self.start(m, MOVE)
            return
        if 19 <= d <= 29:
            if PEAK_DOWN[v] not in self.broken:
                self.start(PEAK_DOWN[v], MOVE)
        elif inp & (LEFT | RIGHT) == RIGHT:
            if self.spin_due(was):
                self.angle = TURN - 1 if self.angle == 0 else self.angle - 1
        elif inp & (LEFT | RIGHT) == LEFT:
            if self.spin_due(was):
                self.angle = 0 if self.angle == TURN - 1 else self.angle + 1
