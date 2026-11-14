"""The high-score initials ring's state machine, high-score boards Task B5,
picker sounds Task K1 and flying letter Task K2: build/entry_sim (the C,
src/entry.c) must equal tests/entry_model.py on every frame, exact state
equality (phase, target, ninit, the three initial bytes, hold, dir, done,
sfx, fly_t, fly_k), over scripted taps, holds across a full turn both ways,
A while moving, erase on empty and on a stored initial, END with 0..3
initials, and the jump to END after the third initial from every position.

The K1 sequences pin the sfx bits: a tap (one tick on arrival, none on the
5 frames before), a 37-position held turn (37 ticks), the third-initial
jump from position 18 (18 ticks, never two in a frame), A on the arrival
frame (TICK|TYPE), erase with none and with one initial, and END (BELL,
then cleared on the done frames).

The K2 sequences pin the flight: a pick flies 20 frames and lands on
pick + 20; a second pick at flight frame 8 lands the first at once and
starts its own flight (fly_k = the new position, fly_t = 1); an erase at
flight frame 5 ends the flight and removes the letter; END during the
third initial's flight ends it and finishes. All the K1 sequences above
also compare the flight fields frame by frame.

The hand-written asserts below are not from the model: they state the
behaviour the plan promises (the first position is A, a tap animates over
RING_SUB frames, a held direction repeats after 16 then every 8, the full
left turn returns the dome to its starting angle, END pads with spaces, and
a fourth letter cannot happen).

The state machine's constants are locked to the generated ring header
(build/ring_map.h, tools/render_ring.py): RING_N, RING_SUB, RING_PHASES,
RING_ERASE, RING_END, ring_code and FLY_FRAMES (the flight's 20 frames).
The model spells them out; the header must agree, so the C's table and the
model's cannot drift.

The C's entry_dome_angle is checked against the model for every phase
0..RING_PHASES-1 and several bases, including the rounding at the last
phase (239 of 239) and phase 0 (base exactly).
"""
import os
import re
import subprocess

import entry_model as em

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "entry_sim")
RING_MAP = os.path.join(ROOT, "build", "ring_map.h")


def run(script):
    """one entry_sim invocation: its output lines"""
    return subprocess.run([SIM], input=script, capture_output=True, text=True,
                          check=True).stdout.splitlines()


def _define(text, name):
    return int(re.search(r"#define %s (-?\d+)" % name, text).group(1))


def _ring_code(text):
    body = re.search(r"ring_code\[[^=]*=\s*\{(.*?)\};", text, re.S).group(1)
    return [int(n, 0) for n in body.split(",")]


def check_seq(name, ops):
    """feed the SAME ops to the C sim and the model; assert every output
    line equals the model's and return the C's lines."""
    e = em.Entry()
    script = []
    expected = []
    for op in ops:
        kind = op[0]
        if kind == "B":
            e.begin()
            script.append("B\n")
            expected.append(("state", e.state()))
        elif kind == "F":
            cur, change = op[1], op[2]
            e.frame(cur, change)
            script.append("F %d %d\n" % (cur, change))
            expected.append(("state", e.state()))
        elif kind == "W":
            e.warp(op[1])
            script.append("W %d\n" % op[1])
            expected.append(("state", e.state()))
        elif kind == "P":
            e.warp_phase(op[1])
            script.append("P %d\n" % op[1])
            expected.append(("state", e.state()))
        elif kind == "D":
            script.append("D %d\n" % op[1])
            expected.append(("angle", e.dome_angle(op[1])))
        elif kind == "S":
            script.append("S\n")
            expected.append(("state", e.state()))
        else:
            raise AssertionError("bad op %r" % (op,))

    lines = run("".join(script))
    assert len(lines) == len(expected), \
        f"{name}: C printed {len(lines)} lines, expected {len(expected)}"
    for i, ((kind, want), got) in enumerate(zip(expected, lines)):
        if kind == "state":
            fields = got.split()
            assert len(fields) == 12, f"{name} step {i}: {got!r}"
            got_state = tuple(int(x) for x in fields)
            assert got_state == want, \
                f"{name} step {i} ({script[i].strip()!r}): " \
                f"C {got_state} model {want}"
        else:
            assert got == "angle=%d" % want, \
                f"{name} step {i} ({script[i].strip()!r}): " \
                f"C {got!r} model angle={want}"
    return lines


def _states(lines):
    return [tuple(int(x) for x in line.split()) for line in lines
            if not line.startswith("angle=")]


def test_the_ring_header_matches_the_model():
    """the generated ring header's constants and codes are the model's, so
    a picked position stores the generator's code, not a copy."""
    text = open(RING_MAP).read()
    assert _define(text, "RING_N") == em.N
    assert _define(text, "RING_SUB") == em.SUB
    assert _define(text, "RING_PHASES") == em.PHASES
    assert _define(text, "RING_ERASE") == em.ERASE
    assert _define(text, "RING_END") == em.END
    assert _define(text, "FLY_FRAMES") == em.FLY_FRAMES == 20
    assert _ring_code(text) == em.RING_CODE
    assert em.RING_CODE[0] == ord("A")
    assert em.RING_CODE[em.ERASE_POS] == em.ERASE
    assert em.RING_CODE[em.END_POS] == em.END


def test_begin_puts_a_at_the_front():
    lines = check_seq("begin", [("B",), ("D", 0), ("D", 137)])
    begin = _states(lines)[0]
    assert begin == (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    assert em.RING_CODE[begin[0] // em.SUB] == ord("A")
    assert lines[1] == "angle=0"
    assert lines[2] == "angle=137"


def test_taps_animate_one_position():
    """one press moves the target one position; the phase takes RING_SUB
    frames to join it, one sub-step a frame. The press frame moves the first
    sub-step, the rest follow with no input."""
    for direction, sign, label in ((em.RIGHT, 1, "right"), (em.LEFT, -1, "left")):
        ops = [("B",)]
        for _ in range(5):
            ops.append(("F", direction, direction))
            ops += [("F", 0, 0)] * em.SUB
        lines = check_seq("taps-" + label, ops)
        states = _states(lines)
        for t in range(5):
            press = states[1 + t * (1 + em.SUB)]
            rest = states[1 + t * (1 + em.SUB) + em.SUB]
            want_target = (sign * (t + 1) * em.SUB) % em.PHASES
            want_press = (sign * (t * em.SUB + 1)) % em.PHASES
            assert press[1] == want_target, (label, t, press)
            assert press[0] == want_press, (label, t, press)
            assert rest[0] == rest[1] == want_target, (label, t, rest)
            assert rest[2] == 0
            assert press[9] == 0, (label, t, press)   # no tick mid-step
            # exactly one tick among the frames after the press: the
            # arrival frame; the frame after it clears the bit.
            base = 1 + t * (1 + em.SUB)
            assert sum(1 for s in states[base + 1:base + 1 + em.SUB]
                       if s[9] & em.SFX_TICK) == 1, (label, t, states[base:])


def test_a_held_direction_repeats_after_16_then_every_8():
    """right held (pressed on the first frame): the target steps on frames
    0, 16, 24 and 32 (16 held frames, then every 8); left the same."""
    for direction, label in ((em.RIGHT, "right"), (em.LEFT, "left")):
        ops = [("B",)]
        for f in range(33):
            ops.append(("F", direction, direction if f == 0 else 0))
        states = _states(check_seq("hold-" + label, ops))
        changes = []
        prev = states[0][1]
        for i, s in enumerate(states[1:]):
            if s[1] != prev:
                changes.append(i)
                prev = s[1]
        assert changes == [0, 16, 24, 32], (label, changes)


def _hold_full_turn_ops(direction):
    """build a script that presses `direction` once, holds it through
    exactly N positions, then releases and waits for the phase to rest."""
    e = em.Entry()
    e.begin()
    ops = [("B",), ("F", direction, direction)]
    e.frame(direction, direction)
    steps = 1
    while steps < em.N:
        before = e.target
        e.frame(direction, 0)
        ops.append(("F", direction, 0))
        if e.target != before:
            steps += 1
    while e.phase != e.target:
        e.frame(0, 0)
        ops.append(("F", 0, 0))
    ops += [("D", 0), ("D", 137)]
    return ops


def test_a_full_left_hold_returns_the_dome_to_base():
    """holding left through all 37 positions moves the target and phase back
    to 0 and entry_dome_angle returns base exactly. Right is symmetric."""
    for direction, label in ((em.LEFT, "left"), (em.RIGHT, "right")):
        lines = check_seq("full-turn-" + label, _hold_full_turn_ops(direction))
        states = _states(lines)
        assert states[-1] == (0, 0, 0, 0, 0, 0, 0, 0, 0, em.SFX_TICK, 0, 0), \
            (label, states[-1])
        assert lines[-2] == "angle=0", (label, lines[-2])
        assert lines[-1] == "angle=137", (label, lines[-1])


def test_a_while_moving_is_ignored_and_a_at_rest_appends():
    """A pressed with the ring mid-animation does nothing; A at rest appends
    the front letter once (holding A does not repeat)."""
    ops = [("B",), ("F", em.RIGHT, em.RIGHT)]
    ops += [("F", 0, 0)] * 2
    ops += [("F", em.A, em.A)]          # moving: ignored
    ops += [("F", 0, 0)] * 4            # reach rest on position 1 (B)
    ops += [("F", em.A, em.A)]          # at rest: appends B
    ops += [("F", em.A, 0)] * 3         # held A: no more letters
    ops += [("F", em.B, em.B)]          # B does nothing
    states = _states(check_seq("a-moving", ops))
    assert states[4][2] == 0, states[4]           # the moving A appended nothing
    assert states[4][0] == 4, states[4]           # still mid-animation
    assert states[6][0] == states[6][1] == em.SUB, states[6]
    assert states[6][2] == 0, states[6]
    assert states[9][2] == 1 and states[9][3] == em.RING_CODE[1], states[9]
    assert states[12][2] == 1, states[12]         # A held: still one
    # B does nothing to the machine; only the independent flight counter
    # advances on this later frame (K2).
    assert states[13][:10] == states[12][:10], (states[12], states[13])
    assert states[13][11] == states[12][11], (states[12], states[13])
    assert states[13][10] == states[12][10] + 1, (states[12], states[13])


def test_erase_on_empty_does_nothing_and_removes_the_last():
    """ERASE with no initials changes nothing; with one stored initial it
    removes it and clears the byte; a second erase is a no-op."""
    ops = [("B",), ("W", em.ERASE_POS), ("F", em.A, em.A)]
    ops += [("W", 0), ("F", em.A, em.A)]
    ops += [("W", em.ERASE_POS), ("F", em.A, em.A)]
    ops += [("W", em.ERASE_POS), ("F", em.A, em.A)]
    states = _states(check_seq("erase", ops))
    assert states[2][2] == 0 and states[2][3:6] == (0, 0, 0), states[2]
    assert states[2][9] == 0, states[2]           # erase on none: no back
    assert states[4][2] == 1 and states[4][3] == ord("A"), states[4]
    assert states[4][9] == em.SFX_TYPE, states[4]
    assert states[6][2] == 0 and states[6][3:6] == (0, 0, 0), states[6]
    assert states[6][9] == em.SFX_BACK, states[6]
    assert states[8][:9] == states[6][:9], states[8]
    assert states[8][9] == 0, states[8]           # a second erase: no back


def test_a_tap_ticks_once_on_arrival():
    """a tap's five frames before the arrival have no tick; the arrival
    frame (the phase reaches a multiple of RING_SUB) ticks once."""
    ops = [("B",), ("F", em.RIGHT, em.RIGHT)] + [("F", 0, 0)] * 5
    states = _states(check_seq("tap-tick", ops))
    assert [s[9] for s in states[1:6]] == [0] * 5, states[1:6]
    assert states[6][0] == states[6][1] == em.SUB, states[6]
    assert states[6][9] == em.SFX_TICK, states[6]
    assert sum(1 for s in states if s[9] & em.SFX_TICK) == 1, states


def test_a_37_position_held_turn_ticks_each_position_once():
    """a held turn through all 37 positions ticks once on each arrival and
    no frame carries more than the one tick."""
    states = _states(check_seq("turn-37-ticks",
                               _hold_full_turn_ops(em.RIGHT)))
    ticks = [s for s in states if s[9] & em.SFX_TICK]
    assert len(ticks) == em.N, len(ticks)
    assert all(s[9] == em.SFX_TICK for s in ticks), ticks
    positions = [s[0] // em.SUB for s in ticks]
    assert len(set(positions)) == em.N, positions


def test_the_jump_to_end_from_18_ticks_each_position_once():
    """the third initial at position 18 sends the ring the short way to
    END (36): 18 positions passed, 18 ticks, at most one per frame (the
    jump's two sub-steps). The third A's own frame types but does not
    tick."""
    ops = [("B",), ("W", 18)]
    for _ in range(3):
        ops += [("F", em.A, em.A), ("F", 0, 0)]
    ops += [("F", 0, 0)] * 60
    states = _states(check_seq("jump-18-ticks", ops))
    third = next((i for i, s in enumerate(states)
                  if s[2] == 3 and s[1] == em.END_PHASE
                  and s[7] == em.DIR_JUMP), None)
    assert third is not None, states
    assert states[third][9] == em.SFX_TYPE, states[third]
    reach = next(i for i in range(third + 1, len(states))
                 if states[i][0] == states[i][1] == em.END_PHASE)
    ticks = [i for i in range(third + 1, reach + 1)
             if states[i][9] & em.SFX_TICK]
    assert len(ticks) == em.END_POS - 18, ticks
    for i in ticks:
        assert states[i][9] == em.SFX_TICK, states[i]
        assert states[i][0] % em.SUB == 0, (i, states[i])


def test_a_on_the_arrival_frame_ticks_and_types():
    """A pressed on the very frame the ring arrives (a tap's last frame)
    appends the front letter and reports both events; nothing before the
    arrival ticked."""
    ops = [("B",), ("F", em.RIGHT, em.RIGHT)]
    ops += [("F", 0, 0)] * 4
    ops += [("F", em.A, em.A)]
    states = _states(check_seq("a-on-arrival", ops))
    assert all(s[9] == 0 for s in states[1:-1]), states[1:-1]
    assert states[-1][9] == em.SFX_TICK | em.SFX_TYPE, states[-1]
    assert states[-1][2] == 1 and states[-1][3] == em.RING_CODE[1], states[-1]


def _end_ops(n):
    """enter n initials (A, B, C at positions 0, 1, 2), reach END (warping
    there for n < 3, waiting for the automatic jump for n = 3), press A,
    then extra input."""
    e = em.Entry()
    e.begin()
    ops = [("B",)]
    for i in range(n):
        e.warp(i)
        ops.append(("W", i))
        e.frame(em.A, em.A)
        ops.append(("F", em.A, em.A))
        if e.ninit < em.INIT_MAX:
            e.frame(0, 0)
            ops.append(("F", 0, 0))
    if e.ninit < em.INIT_MAX:
        e.warp(em.END_POS)
        ops.append(("W", em.END_POS))
    else:
        while e.phase != e.target:
            e.frame(0, 0)
            ops.append(("F", 0, 0))
    e.frame(em.A, em.A)
    ops.append(("F", em.A, em.A))
    e.frame(em.A, em.A)
    ops.append(("F", em.A, em.A))
    e.frame(em.RIGHT, em.RIGHT)
    ops.append(("F", em.RIGHT, em.RIGHT))
    return ops


def test_end_with_0_to_3_initials_pads_with_spaces():
    """END finishes with the initials entered and spaces for the missing
    ones (0, 1, 2 or 3 stored); after done, input does nothing."""
    want_init = {
        0: [32, 32, 32],
        1: [ord("A"), 32, 32],
        2: [ord("A"), ord("B"), 32],
        3: [ord("A"), ord("B"), ord("C")],
    }
    for n in range(4):
        states = _states(check_seq("end-%d" % n, _end_ops(n)))
        done = states[-1]
        assert done[2] == n, (n, done)
        assert list(done[3:6]) == want_init[n], (n, done)
        assert done[8] == 1, (n, done)
        assert done[0] == done[1] == em.END_PHASE, (n, done)
        assert states[-2] == done and states[-2][9] == 0, (n, states[-3:])
        assert states[-3][:9] == done[:9] and states[-3][9] == em.SFX_BELL, \
            (n, states[-3:])


def test_third_initial_jumps_to_end_from_every_position():
    """from every appendable position (0..34), the third initial sets the
    target to END's phase the short way; the ring reaches it the shortest
    way at two sub-steps a frame (twice a turn's rate, the user's 10-30
    ask), in half the sub-steps' frames; the ring still turns after the third, so
    the player steps back to ERASE, removes the third initial, returns to
    END and finishes (the missing third is padded with a space)."""
    for k in range(em.ERASE_POS):
        ops = [("B",), ("W", k)]
        for _ in range(3):
            ops.append(("F", em.A, em.A))
            ops.append(("F", 0, 0))
        ops += [("F", 0, 0)] * (18 * em.SUB)   # every short way fits
        ops.append(("F", em.LEFT, em.LEFT))    # still turns: back to ERASE
        ops += [("F", 0, 0)] * em.SUB
        ops.append(("F", em.A, em.A))          # erase the third
        ops.append(("F", em.RIGHT, em.RIGHT))  # on to END again
        ops += [("F", 0, 0)] * em.SUB
        ops.append(("F", em.A, em.A))          # END
        states = _states(check_seq("third-k=%d" % k, ops))

        third = states[6]                      # after the third A press
        assert third[1] == em.END_PHASE, (k, third)
        assert third[2] == em.INIT_MAX, (k, third)
        want_init = [em.RING_CODE[k]] * em.INIT_MAX
        assert list(third[3:6]) == want_init, (k, third)

        # the phase reaches END and the path is the shortest one
        reach = None
        for i in range(6, len(states)):
            if states[i][0] == states[i][1] == em.END_PHASE:
                reach = i
                break
        assert reach is not None, (k, "never reached END")
        d = (em.END_POS - k) % em.N
        if d > em.N // 2:
            d -= em.N
        assert reach - 6 == abs(d) * em.SUB // 2, (k, reach - 6, abs(d) * em.SUB // 2)
        # every frame of the jump moved the phase two sub-steps, and the
        # arrival frame ends the jump (dir back to 0)
        for i in range(7, reach + 1):
            step = (states[i][0] - states[i - 1][0]) % em.PHASES
            assert step in (2, em.PHASES - 2), (k, i, step)
        assert states[reach][7] == 0, (k, states[reach])
        assert states[reach][2] == em.INIT_MAX, (k, states[reach])

        # after the third: left reaches ERASE, A there removes the third
        # initial, right returns to END and A finishes with a space third
        erase_a = len(states) - em.SUB - 3     # the A on ERASE
        assert states[erase_a][0] == states[erase_a][1] == em.END_PHASE - em.SUB, (k, states[erase_a])
        assert states[erase_a][2] == em.INIT_MAX - 1, (k, states[erase_a])
        assert states[-1][8] == 1, (k, states[-1])
        assert list(states[-1][3:6]) == [em.RING_CODE[k]] * 2 + [32], (k, states[-1])


def test_a_pick_starts_a_20_frame_flight_and_lands_on_pick_plus_20():
    """the pick frame sets fly_t 1 and fly_k to the position; each later
    frame increments fly_t; the frame that would pass FLY_FRAMES (the 20th
    later frame, pick + 20) is the landing (fly_t 0), leaving fly_k."""
    ops = [("B",), ("F", em.A, em.A)] + [("F", 0, 0)] * 21
    states = _states(check_seq("flight-pick", ops))
    pick = 1                                # the A press is state index 1
    assert states[pick][10:12] == (1, 0), states[pick]
    for j in range(1, em.FLY_FRAMES):
        assert states[pick + j][10] == 1 + j, (j, states[pick + j])
        assert states[pick + j][11] == 0, (j, states[pick + j])
    assert states[pick + em.FLY_FRAMES - 1][10] == em.FLY_FRAMES, \
        states[pick + em.FLY_FRAMES - 1]
    assert states[pick + em.FLY_FRAMES][10] == 0, \
        states[pick + em.FLY_FRAMES]
    # no frame before the landing shows it already down
    assert all(s[10] > 0 for s in states[pick:pick + em.FLY_FRAMES]), \
        states[pick:pick + em.FLY_FRAMES + 1]
    assert states[pick][2] == 1 and states[pick][3] == em.RING_CODE[0], \
        states[pick]


def test_a_second_pick_at_flight_frame_8_lands_the_first_and_starts_its_own():
    """A at flight frame 8 (after moving to B): the first flight ends at
    once (its letter is in init[0]), and the second letter starts its own
    flight at fly_t 1 with fly_k = B's position."""
    ops = [("B",), ("F", em.A, em.A)]        # first pick: A, fly_t 1
    ops += [("F", em.RIGHT, em.RIGHT)]       # move to B
    ops += [("F", 0, 0)] * 5                 # rest: flight frame 7
    ops += [("F", em.A, em.A)]               # flight frame 8, pick B
    ops += [("F", 0, 0)] * (em.FLY_FRAMES + 1)
    states = _states(check_seq("flight-second-pick", ops))
    # the frame before the second pick is flight frame 7, still flying
    assert states[7][10] == 7 and states[7][0] == states[7][1] == em.SUB, \
        states[7]
    assert states[8][10:12] == (1, 1), states[8]     # B's position, new flight
    assert states[8][2] == 2, states[8]
    assert list(states[8][3:6]) == [em.RING_CODE[0], em.RING_CODE[1], 0], \
        states[8]
    # the first flight never landed before the second pick
    assert all(s[10] > 0 for s in states[1:9]), states[1:9]
    # the second flight lands at pick + 20, both letters still stored
    assert states[8 + em.FLY_FRAMES][10] == 0, states[8 + em.FLY_FRAMES]
    assert states[8 + em.FLY_FRAMES][2] == 2, states[8 + em.FLY_FRAMES]


def test_an_erase_at_flight_frame_5_ends_the_flight_and_removes_the_letter():
    """A tap on ERASE at flight frame 5: the flight ends that frame (fly_t
    0), the initial is removed, and the backspace event is reported."""
    ops = [("B",), ("F", em.A, em.A)]        # first pick: A, fly_t 1
    ops += [("F", 0, 0)] * 3                 # flight frames 2, 3, 4
    ops += [("W", em.ERASE_POS)]             # test setup: rest on ERASE
    ops += [("F", em.A, em.A)]               # flight frame 5, erase
    states = _states(check_seq("flight-erase", ops))
    assert states[4][10] == 4, states[4]
    assert states[5][10] == 4, states[5]     # the erase setup frame
    assert states[6][10] == 0, states[6]     # the 5th flight frame ended it
    assert states[6][9] == em.SFX_BACK, states[6]
    assert states[6][2] == 0 and states[6][3:6] == (0, 0, 0), states[6]


def test_end_during_the_thirds_flight_ends_it_and_finishes():
    """after the third initial at position 34 the ring jumps to END (two
    sub-steps a frame, six frames), still flying; A at END on flight frame
    8 ends the flight (fly_t 0) and finishes with all three initials."""
    ops = [("B",), ("W", 34)]
    for _ in range(3):
        ops.append(("F", em.A, em.A))
        ops.append(("F", 0, 0))
    ops += [("F", 0, 0)] * 5                 # reach END at rest, still flying
    ops.append(("F", em.A, em.A))            # END on flight frame 8
    ops += [("F", 0, 0)] * 3                 # done freezes the machine
    states = _states(check_seq("flight-end", ops))
    third = 6
    assert states[third][2] == em.INIT_MAX and states[third][7] == em.DIR_JUMP, \
        states[third]
    assert states[third][10:12] == (1, 34), states[third]
    rest = 12
    assert states[rest][0] == states[rest][1] == em.END_PHASE, states[rest]
    assert states[rest][10] == 7, states[rest]     # flight frame 7 at END
    assert states[13][10] == 0 and states[13][8] == 1, states[13]
    assert states[13][9] == em.SFX_BELL, states[13]
    assert list(states[13][3:6]) == [em.RING_CODE[34]] * em.INIT_MAX, states[13]


def test_dome_angle_for_every_phase_and_base():
    """the C's entry_dome_angle equals (base - (phase * 240 +
    RING_PHASES / 2) / RING_PHASES) mod 240 for every phase and three bases
    (the dome turns with the ring, 10-30); phase 0 is exactly base, the
    last phase is base - 239."""
    for base in (0, 17, 239):
        ops = []
        for p in range(em.PHASES):
            ops.append(("P", p))
            ops.append(("D", base))
        lines = check_seq("angle-base-%d" % base, ops)
        angles = [int(line.split("=")[1]) for line in lines
                  if line.startswith("angle=")]
        assert len(angles) == em.PHASES
        for p, got in enumerate(angles):
            want = (base - (p * 240 + em.PHASES // 2) // em.PHASES) % 240
            assert got == want, (base, p, got, want)
            assert got == (base - p * 240 // em.PHASES
                           - (1 if (p * 240) % em.PHASES
                              >= em.PHASES // 2 else 0)) % 240, (base, p)
        assert angles[0] == base
        assert angles[em.PHASES - 1] == (base - 239) % 240


def test_right_turns_the_dome_down_like_play():
    """10-30, the user's pick ("with"): the dome turns with the ring, so a
    Right step lowers the dome angle, as Right spins the dome in play
    (ship.c). One Right step at rest (phase RING_SUB) from base 100 is
    100 - round(6 * 240 / 222) = 94; one Left step from base 0 wraps to 6."""
    ops = [("B",), ("F", em.RIGHT, em.RIGHT)] + [("F", 0, 0)] * 6 + [("D", 100)]
    lines = check_seq("right-down", ops)
    assert _states(lines)[-1][0] == em.SUB, lines
    assert lines[-1] == "angle=94", lines[-1]
    ops = [("B",), ("F", em.LEFT, em.LEFT)] + [("F", 0, 0)] * 6 + [("D", 0)]
    lines = check_seq("left-up", ops)
    assert lines[-1] == "angle=6", lines[-1]
