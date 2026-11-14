"""The high-score initials ring's state machine, as a pure model: the
reference tests/test_entry.py holds the C's src/entry.c (built for the host
as build/entry_sim) to, exact state equality after every frame (high-score
boards Task B5).

The rules (from the task and the approved design):

  - the ring has RING_N positions (A-Z, space, . ! ? - & ', a star, a
    heart, the erase arrow and END; build/ring_map.h's ring_code) and
    RING_SUB animation phases per position, so RING_PHASES = RING_N *
    RING_SUB. Phase p shows the ring turned p / RING_SUB positions:
    position k is at the front when p = k * RING_SUB. The last two
    positions store RING_ERASE (254) and RING_END (255).
  - entry_begin: phase 0 (A at the front), target 0, no initials.
  - entry_frame, per frame:
      * a newly pressed right/left sets the target one position on/back
        (wrapping). A held direction repeats after 16 frames, then every
        8 frames. The phase moves one sub-step per frame toward the target
        the short way (forward on a tie).
      * A at rest (phase == target and a multiple of RING_SUB) picks the
        position at the front: a letter/symbol appends ring_code[k] if
        fewer than three initials are stored; after the third, the target
        becomes END's phase the short way (the ring still turns after it,
        so ERASE can fix a typo; a letter is not appended while three are
        stored). ERASE (254) removes the last initial (nothing if none);
        END (255) sets done and pads the missing initials with spaces.
        A while moving is ignored. B does nothing.
      * each frame's sound events are reported in sfx (cleared first, a done
        frame included): TICK when a move left the phase on a multiple of
        RING_SUB (a held turn ticks once per position; the jump's two
        sub-steps never tick twice), TYPE on an appended letter, BACK only
        when an erase removed one, BELL on END.
      * K2: a picked letter's copy flies to its initials slot. A pick of a
        letter sets fly_k = the position and fly_t = 1 on the pick frame;
        each later frame increments fly_t, and the frame it would pass
        FLY_FRAMES it becomes 0 (landed, pick + 20). A new letter pick while
        flying, an erase or END ends the flight first (fly_t 0) then applies
        as today (a new letter starts its own flight).
      * done freezes the machine.
  - entry_dome_angle: base - the phase's share (the dome turns with the
    ring: Right lowers the angle as in play, the user's pick 10-30) of one full 240-step turn,
    (phase * 240 + RING_PHASES / 2) / RING_PHASES, mod 240. Since the 37
    positions are exactly one turn (phase 0 and phase RING_PHASES both map
    to the same angle), holding through a full left turn returns the dome
    to its starting angle.

The model stores the state the C struct does: phase, target, ninit, the
three initial bytes, hold (frames since the last step of a held
direction), dir (0 none, 1 right, 2 left), done, the frame's sfx, and K2's
flight fields fly_t (frames shown, 0 = none) and fly_k (the picked
position). It uses 0 for the bytes not yet set; END pads them with spaces.
"""

N = 37                       # ring positions
SUB = 6                      # animation phases per position
PHASES = N * SUB             # 222
ERASE = 254                  # RING_ERASE
END = 255                    # RING_END
END_POS = N - 1              # 36
END_PHASE = END_POS * SUB    # 216
DIR_JUMP = 3                 # entry.h ENTRY_DIR_JUMP: the jump to END
ERASE_POS = N - 2            # 35

INIT_MAX = 3
REPEAT_FIRST = 16            # held frames before the first repeat
REPEAT_EVERY = 8             # held frames between repeats after that
FLY_FRAMES = 20              # build/ring_map.h's flight length (K2)

RIGHT = 1 << 3               # as ngdevkit's bios-ram.h
LEFT = 1 << 2
A = 1 << 4
B = 1 << 5

# entry.h's ENTRY_SFX_* bits
SFX_TICK = 1
SFX_TYPE = 2
SFX_BACK = 4
SFX_BELL = 8

# the code a picked position stores (build/ring_map.h ring_code)
RING_CODE = (list(range(65, 91)) + [32, 46, 33, 63, 45, 38, 39, 1, 2,
                                    ERASE, END])


class Entry:
    def __init__(self):
        self.begin()

    def begin(self):
        self.phase = 0
        self.target = 0
        self.ninit = 0
        self.init = [0, 0, 0]
        self.hold = 0
        self.dir = 0
        self.done = 0
        self.sfx = 0
        self.fly_t = 0
        self.fly_k = 0

    def warp(self, k):
        """test setup: put the ring at rest on position k"""
        self.phase = self.target = (k * SUB) % PHASES
        self.hold = 0
        self.dir = 0

    def warp_phase(self, p):
        """test setup: put the ring at rest on phase p (0..PHASES-1)"""
        self.phase = self.target = p % PHASES
        self.hold = 0
        self.dir = 0

    def state(self):
        return (self.phase, self.target, self.ninit, self.init[0],
                self.init[1], self.init[2], self.hold, self.dir, self.done,
                self.sfx, self.fly_t, self.fly_k)

    def _add(self, p, d):
        t = p + d
        if t >= PHASES:
            t -= PHASES
        return t

    def _sub(self, p, d):
        t = p
        if t < d:
            t += PHASES
        return t - d

    def _move(self):
        if self.phase != self.target:
            fwd = (self.target - self.phase) % PHASES
            if fwd <= PHASES // 2:
                self.phase = (self.phase + 1) % PHASES
            else:
                self.phase = (self.phase + PHASES - 1) % PHASES
            if self.phase % SUB == 0:
                self.sfx |= SFX_TICK       # a position reached the front

    def _flight(self):
        """K2: one later frame of a flight; the frame that would pass
        FLY_FRAMES is the landing (fly_t 0, pick + 20)."""
        if self.fly_t > 0:
            self.fly_t += 1
            if self.fly_t > FLY_FRAMES:
                self.fly_t = 0

    def frame(self, cur, change):
        self.sfx = 0                       # the frame's events start empty
        if self.done:
            return
        self._flight()
        # a new press steps at once (also after the third initial: the
        # player may turn back to ERASE; no fourth letter is appended)
        if change & RIGHT:
            self.dir = 1
            self.hold = 0
            self.target = self._add(self.target, SUB)
        elif change & LEFT:
            self.dir = 2
            self.hold = 0
            self.target = self._sub(self.target, SUB)
        elif self.dir == 1 and (cur & RIGHT):
            self.hold += 1
            if self.hold >= REPEAT_FIRST:
                self.target = self._add(self.target, SUB)
                self.hold = REPEAT_FIRST - REPEAT_EVERY
        elif self.dir == 2 and (cur & LEFT):
            self.hold += 1
            if self.hold >= REPEAT_FIRST:
                self.target = self._sub(self.target, SUB)
                self.hold = REPEAT_FIRST - REPEAT_EVERY
        else:
            if self.dir != DIR_JUMP:    # the jump runs on with no press
                self.dir = 0
            self.hold = 0

        # one sub-step toward the target, the short way (forward on a tie);
        # the third initial's jump to END takes two a frame (10-30)
        self._move()
        if self.dir == DIR_JUMP:
            self._move()
            if self.phase == self.target:
                self.dir = 0

        if (change & A) and self.phase == self.target \
                and self.phase % SUB == 0:
            code = RING_CODE[self.phase // SUB]
            if code == ERASE:
                self.fly_t = 0             # an erase ends the flight
                if self.ninit > 0:
                    self.ninit -= 1
                    self.init[self.ninit] = 0
                    self.sfx |= SFX_BACK   # nothing to erase sends nothing
            elif code == END:
                self.fly_t = 0             # END ends the flight
                self.done = 1
                for j in range(self.ninit, INIT_MAX):
                    self.init[j] = 32
                self.sfx |= SFX_BELL
            elif self.ninit < INIT_MAX:
                self.fly_t = 0             # a new pick lands the old one
                self.init[self.ninit] = code
                self.ninit += 1
                self.sfx |= SFX_TYPE
                self.fly_k = self.phase // SUB
                self.fly_t = 1             # the pick frame's flight
                if self.ninit == INIT_MAX:
                    self.target = END_PHASE
                    self.dir = DIR_JUMP
                    self.hold = 0

    def dome_angle(self, base):
        share = (self.phase * 240 + PHASES // 2) // PHASES
        return (base - share) % 240
