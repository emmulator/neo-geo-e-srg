"""The five-entry per-level high-score board, high-score boards Task B1:
build/board_sim (the C, src/board.c) must equal tests/board_model.py —
exact equality of the struct's 126 bytes after every operation — over the
defaults, every rank boundary (equal, one more, above the 1st), insert
boundaries, and two seeded random sequences of 200 steps each. The
hand-written asserts below are not from the model: the reset image, the
rank table and each rejection, exactly as the task promises.

The byte layout being locked: the 126-byte struct (u32 magic + 3 x 5
entries of init[3] + pad + u32 score10 + u16 sum), big-endian as the 68000
stores it, with sum the 16-bit wrap-around byte sum of the 124 bytes before
it. The host build must give the same bytes (the host sim serialises
through the fields, never raw host memory).
"""
import os
import random
import subprocess

import board_model as bm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "board_sim")

DEFAULT_IMAGE = (
    "45 53 52 32 53 52 47 00 00 00 13 88 48 45 58 00 00 00 0f a0 "
    "44 4f 4d 00 00 00 0b b8 5a 41 50 00 00 00 07 d0 56 45 43 00 "
    "00 00 03 e8 53 52 47 00 00 00 13 88 48 45 58 00 00 00 0f a0 "
    "44 4f 4d 00 00 00 0b b8 5a 41 50 00 00 00 07 d0 56 45 43 00 "
    "00 00 03 e8 53 52 47 00 00 00 13 88 48 45 58 00 00 00 0f a0 "
    "44 4f 4d 00 00 00 0b b8 5a 41 50 00 00 00 07 d0 56 45 43 00 "
    "00 00 03 e8 19 f7"
)


def run(script):
    """one board_sim invocation: the script's lines of ops, its output
    lines."""
    out = subprocess.run([SIM], input=script, capture_output=True,
                         text=True, check=True).stdout
    return out.splitlines()


def _hex(img):
    return " ".join("%02x" % x for x in img)


def _image_with_sum(img):
    """the image with its sum field recomputed (to isolate another fault)"""
    b = bytearray(img)
    bm._put_u16(b, bm.SUM_OFF, bm.byte_sum(b))
    return b


def check_seq(name, ops):
    """feed the SAME ops to the C sim and the model; assert the C's 126
    bytes equal the model's after every step, and its rank=/valid= returns
    equal the model's."""
    m = bm.Board()
    m.reset()
    script = ["R\n", "H\n"]
    expect = [("h", m.hexb())]
    for op in ops:
        kind = op[0]
        if kind == "R":
            m.reset()
            script.append("R\n")
        elif kind == "K":
            level, score = op[1], op[2]
            script.append("K %d %d\n" % (level, score))
            expect.append(("c", "rank=%d" % m.rank(level, score)))
        elif kind == "I":
            level, rank, init, score = op[1], op[2], op[3], op[4]
            script.append("I %d %d %s %d\n"
                          % (level, rank, " ".join("%02x" % x for x in init),
                             score))
            m.insert(level, rank, init, score)
        elif kind == "L":
            script.append("L %s\n" % op[1])
            m.load(op[1])
        script.append("H\n")
        expect.append(("h", m.hexb()))
    script.append("V\n")
    expect.append(("c", "valid=%d" % m.valid()))
    lines = run("".join(script))
    assert len(lines) == len(expect), \
        f"{name}: C printed {len(lines)} lines, expected {len(expect)}"
    for i, ((kind, want), got) in enumerate(zip(expect, lines)):
        if kind == "h":
            assert got.endswith("(126 bytes)"), f"{name} step {i}: {got!r}"
            fields = got.split()
            assert len(fields) == 128, f"{name} step {i}: {got!r}"
            got_img = " ".join(fields[:126])
            assert got_img == want, \
                f"{name} step {i}: C {got_img!r} model {want!r}"
        else:
            assert got == want, f"{name} step {i}: C {got!r} model {want!r}"


def test_defaults():
    """the defaults: SRG 50,000 ... VEC 10,000 on every level, stored as
    score/10. The C's 126 bytes equal the model's and the hand-written
    image; the entries decode to the defaults and the reset table is
    valid."""
    lines = run("R\nH\nV\n")
    assert lines[0] == DEFAULT_IMAGE + " (126 bytes)", lines[0]
    assert lines[1] == "valid=1", lines[1]
    m = bm.Board()
    m.reset()
    assert m.hexb() == DEFAULT_IMAGE
    assert m.bytes126() == bytes(int(x, 16) for x in DEFAULT_IMAGE.split())
    for level in range(bm.NLEVELS):
        entries = [m.entry(level, e) for e in range(bm.NENTRIES)]
        assert [e[0] for e in entries] == \
            [b"SRG", b"HEX", b"DOM", b"ZAP", b"VEC"]
        assert [e[2] for e in entries] == [5000, 4000, 3000, 2000, 1000]
        assert all(e[1] == 0 for e in entries)
    assert m.valid() == 1


def test_rank_boundaries():
    """every boundary on every level, against a hand-written table (and the
    model): equal to the 5th does not qualify; one more than the 5th takes
    the 5th; equal to an entry goes below it; one more than the 1st, and
    above the 1st, become the 1st. level 3 and a zero score do not
    qualify."""
    cases = [
        (1000, 5, "equal to the 5th"),
        (1001, 4, "one more than the 5th"),
        (2000, 4, "equal to the 4th"),
        (2001, 3, "one more than the 4th"),
        (3000, 3, "equal to the 3rd"),
        (3001, 2, "one more than the 3rd"),
        (4000, 2, "equal to the 2nd"),
        (4001, 1, "one more than the 2nd"),
        (5000, 1, "equal to the 1st"),
        (5001, 0, "one more than the 1st"),
        (0, 5, "zero"),
        (bm.SCORE_MAX, 0, "SCORE_MAX"),
    ]
    script = ["R\n"]
    expect = []
    m = bm.Board()
    m.reset()
    for level in range(bm.NLEVELS):
        for score, rank, label in cases:
            got = m.rank(level, score)
            assert got == rank, f"model level {level} {label}: {got} != {rank}"
            script.append("K %d %d\n" % (level, score))
            expect.append("rank=%d" % rank)
    script.append("K 3 1000000\n")
    expect.append("rank=5")
    lines = run("".join(script))
    assert lines == expect, "\n".join(
        f"{i}: C {got!r} expected {want!r}"
        for i, (got, want) in enumerate(zip(lines, expect)) if got != want)


def test_insert_and_drop():
    """insert at the 1st and at the 5th: the rest shifts down, the 5th is
    dropped, the initials/score land at the rank and the sum is fixed;
    rank 5 and level 3 change nothing. Every state equals the model and is
    valid."""
    cases = [
        (0, 0, (0x41, 0x41, 0x41), 9000, "above the 1st"),
        (0, 4, (0x42, 0x42, 0x42), 1500, "into the 5th"),
        (1, 2, (0x01, 0x20, 0x02), 3500, "star, space, heart"),
        (2, 5, (0x43, 0x43, 0x43), 1, "rank 5 changes nothing"),
        (3, 0, (0x44, 0x44, 0x44), bm.SCORE_MAX, "level 3 changes nothing"),
    ]
    m = bm.Board()
    m.reset()
    script = ["R\n"]
    expect = []
    for level, rank, init, score, _ in cases:
        script.append("I %d %d %s %d\n"
                      % (level, rank, " ".join("%02x" % x for x in init),
                         score))
        m.insert(level, rank, init, score)
        script.append("H\nV\n")
        expect.append(m.hexb())
        expect.append("valid=%d" % m.valid())
    lines = run("".join(script))
    for i, (want, got) in enumerate(zip(expect, lines)):
        if i % 2 == 0:
            assert got.endswith("(126 bytes)"), got
            got_img = " ".join(got.split()[:126])
            assert got_img == want, f"step {i}: C {got_img!r} model {want!r}"
        else:
            assert got == want, f"step {i}: C {got!r} model {want!r}"

    # the order the drops must leave, hand-written from the defaults
    b = bm.Board()
    b.reset()
    b.insert(0, 0, (0x41, 0x41, 0x41), 9000)
    assert [b.entry(0, e)[0] for e in range(5)] == \
        [b"AAA", b"SRG", b"HEX", b"DOM", b"ZAP"]
    assert [b.entry(0, e)[2] for e in range(5)] == [9000, 5000, 4000, 3000, 2000]
    b.insert(0, 4, (0x42, 0x42, 0x42), 1500)
    assert [b.entry(0, e)[2] for e in range(5)] == [9000, 5000, 4000, 3000, 1500]
    assert b.entry(0, 4)[0] == b"BBB"
    assert b.valid() == 1


def test_random_sequences_seeded():
    """two seeded random sequences, 200 steps each: one over the whole score
    range, one around the defaults (0..6000) so the rank boundaries and the
    shifts both occur. Each step picks a level, gets the model's rank, and
    inserts (with random initials) only when rank < 5; a reset every 40
    steps re-seeds the defaults."""
    def sequence(seed, hi):
        rng = random.Random(seed)
        ops = []
        for k in range(200):
            if k % 40 == 0:
                ops.append(("R",))
            level = rng.randrange(bm.NLEVELS)
            score = rng.randrange(hi + 1)
            if rng.randrange(3) == 0:
                ops.append(("K", level, score))
            ops.append(("PICK", level, score))
        return ops

    def expand(ops):
        """turn each (PICK, level, score) into a K or an I, with the model's
        rank and random initials at the time."""
        rng = random.Random(1234)
        out = []
        m = bm.Board()
        m.reset()
        for op in ops:
            if op[0] == "R":
                m.reset()
                out.append(op)
                continue
            if op[0] == "K":
                out.append(op)
                continue
            _, level, score = op
            rank = m.rank(level, score)
            if rank == bm.NENTRIES:
                out.append(("K", level, score))
            else:
                init = tuple(rng.choice((0x20, 0x41, 0x5a, 0x01, 0x02, 0x2e))
                             for _ in range(bm.NINIT))
                out.append(("I", level, rank, init, score))
                m.insert(level, rank, init, score)
        return out

    check_seq("random-full", expand(sequence(20261029, bm.SCORE_MAX)))
    check_seq("random-near", expand(sequence(20261030, 6000)))


def test_corrupted_bytes_fail_valid():
    """a single flipped byte in the magic, an initial, the pad, a score or
    the sum fails board_valid (the sum is left wrong for these). With the
    sum fixed, a wrong (old 'ESRG') magic, an unsorted level and a score of
    SCORE_MAX + 1 still fail. The reset image passes. Each image is loaded
    byte-for-byte into the C (the sim's L op) and into the model."""
    reset = bytearray(bm.Board().bytes126())
    cases = [
        ("magic byte", _flip(reset, 0)),
        ("initial byte", _flip(reset, 4)),
        ("pad byte", _flip(reset, 7)),
        ("score byte", _flip(reset, 8)),
        ("last score byte", _flip(reset, 123)),
        ("sum byte", _flip(reset, 124)),
        ("all zero", bytes(bm.BYTES)),
    ]

    # wrong magic 'ESRG', sum fixed: only the magic check can reject
    img = bytearray(reset)
    bm._put_u32(img, 0, 0x45535247)
    cases.append(("old ESRG magic", _image_with_sum(img)))

    # unsorted level 0 (5000, 4000 swapped), sum fixed
    img = bytearray(reset)
    bm._put_u32(img, bm.entry_offset(0, 0) + bm.SCORE_OFF, 4000)
    bm._put_u32(img, bm.entry_offset(0, 1) + bm.SCORE_OFF, 5000)
    cases.append(("unsorted", _image_with_sum(img)))

    # a score over SCORE_MAX, sum fixed
    img = bytearray(reset)
    bm._put_u32(img, bm.entry_offset(1, 0) + bm.SCORE_OFF, bm.SCORE_MAX + 1)
    cases.append(("score over max", _image_with_sum(img)))

    script = ""
    expect = []
    for _, img in cases:
        m = bm.Board()
        m.load(bytes(img))
        assert m.valid() == 0
        script += "L %s\nV\n" % _hex(img)
        expect.append("valid=0")
    script += "L %s\nV\n" % _hex(reset)
    expect.append("valid=1")
    lines = run(script)
    assert lines == expect, "\n".join(
        f"{name}: C {got!r} expected {want!r}"
        for (name, _), got, want in zip(cases, lines, expect) if got != want)
    m = bm.Board()
    m.load(bytes(reset))
    assert m.valid() == 1


def _flip(img, pos):
    """a copy of img with byte `pos` bit 0 flipped (the sum left wrong)"""
    b = bytearray(img)
    b[pos] ^= 0x01
    return b
