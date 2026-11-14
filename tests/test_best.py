"""The per-level high-score table, M6 Task 8: build/best_sim (the C,
src/best.c) must equal tests/best_model.py — exact equality of the
struct's 18 bytes after every operation — for update sequences: higher,
lower, equal, SCORE_MAX, each level, level 3, and a 200-step seeded
random sequence. The hand-written asserts below are not from the model:
the 18-byte encoding and each rejection, exactly as the plan promises.

The byte layout being locked: the 18-byte struct (u32 magic + u32
score10[3] + u16 sum), big-endian as the 68000 stores it, with sum the
16-bit wrap-around byte sum of the 16 bytes before it. The host build
must give the same bytes (the host sim serialises through the fields,
never raw host memory: the struct is packed so the layout is the same
and the sim's H/L ops encode/decode big-endian).
"""
import os
import random
import subprocess

import best_model as bm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "best_sim")


def run(script):
    """one best_sim invocation: the script's lines of ops, its output
    lines."""
    out = subprocess.run([SIM], input=script, capture_output=True,
                         text=True, check=True).stdout
    return out.splitlines()


def check_seq(name, ops):
    """feed the SAME ops to the C sim and the model; assert the C's 18
    bytes equal the model's after every step, and its changed=/valid=
    returns equal the model's."""
    m = bm.Best()
    m.reset()
    script = ["R\n", "H\n"]
    expect = [("h", m.hexb())]
    for op in ops:
        if op[0] == "R":
            m.reset()
            script.append("R\n")
        else:
            script.append("U %d %d\n" % (op[1], op[2]))
            expect.append(("c", "changed=%d" % m.update(op[1], op[2])))
        script.append("H\n")
        expect.append(("h", m.hexb()))
    script.append("V\n")
    expect.append(("c", "valid=%d" % m.valid()))
    lines = run("".join(script))
    assert len(lines) == len(expect), \
        f"{name}: C printed {len(lines)} lines, expected {len(expect)}"
    for i, ((kind, want), got) in enumerate(zip(expect, lines)):
        if kind == "h":
            assert got.endswith("(18 bytes)"), f"{name} step {i}: {got!r}"
            assert " ".join(got.split()[:18]) == want, \
                f"{name} step {i}: C {' '.join(got.split()[:18])!r} " \
                f"model {want!r}"
        else:
            assert got == want, f"{name} step {i}: C {got!r} model {want!r}"


def test_update_sequences():
    """higher, lower, equal, SCORE_MAX, each level, level 3: every step's
    bytes and returns equal the model's."""
    cases = [
        ("higher", [("U", 0, 5)]),
        ("lower", [("U", 0, 5), ("U", 0, 3)]),
        ("equal", [("U", 0, 5), ("U", 0, 5)]),
        ("max", [("U", 0, bm.SCORE_MAX)]),
        ("each level", [("U", 0, 1), ("U", 1, 2), ("U", 2, 3)]),
        ("level 3", [("U", 3, 5), ("U", 0, 5), ("U", 0, 6)]),
        ("level 3 max", [("U", 3, bm.SCORE_MAX), ("U", 0, bm.SCORE_MAX)]),
        ("mixed", [("U", 1, 1000), ("U", 0, 900), ("U", 2, 800),
                   ("U", 1, 999), ("U", 2, 801)]),
    ]
    for name, ops in cases:
        check_seq(name, ops)


def test_random_sequence_seeded():
    """a 200-step seeded random sequence, level 0..3 (so level 3 and
    lower/equal/higher all occur), scores across the whole range."""
    rng = random.Random(20261017)
    ops = []
    for k in range(200):
        if k % 20 == 0:
            ops.append(("R",))
        ops.append(("U", rng.randrange(4), rng.randrange(bm.SCORE_MAX + 1)))
    check_seq("random200", ops)


def test_reset_bytes_hand_written():
    """after best_reset, the 18 bytes are 45 53 52 47, twelve 00, then
    the sum 01 31 (0x45+0x53+0x52+0x47 = 0x131) — asserted on the C's own
    dump, and on the model, from the literal bytes."""
    lines = run("R\nH\n")
    assert lines[0] == ("45 53 52 47 00 00 00 00 00 00 00 00 "
                        "00 00 00 00 01 31 (18 bytes)"), lines[0]
    m = bm.Best()
    m.reset()
    assert m.hexb() == ("45 53 52 47 00 00 00 00 00 00 00 00 "
                        "00 00 00 00 01 31")


def test_valid_rejects():
    """best_valid rejects a wrong magic, a wrong sum, an all-zero struct,
    and a score of SCORE_MAX + 1 with a correct sum. Each image is loaded
    byte-for-byte into the C (the sim's L op) and into the model, and both
    must reject; the reset table must be accepted."""
    reset_img = "45 53 52 47 " + "00 " * 12 + "01 31"
    cases = [
        # wrong magic (0x45535248): the sum is the correct byte sum of
        # those 16 bytes (0x45+0x53+0x52+0x48 = 0x132), so only the magic
        # check can reject.
        ("45 53 52 48 " + "00 " * 12 + "01 32", "wrong magic"),
        # wrong sum: the reset table with sum 0x132 (the right sum is
        # 0x131).
        ("45 53 52 47 " + "00 " * 12 + "01 32", "wrong sum"),
        # all-zero backup RAM / freshly formatted card.
        ("00 " * 18, "all zero"),
        # score 10,000,000 (SCORE_MAX + 1) with the correct sum:
        # 0x131 + (0x00+0x98+0x96+0x80) = 0x2DF.
        ("45 53 52 47 00 98 96 80 " + "00 " * 12 + "02 df",
         "score over max"),
    ]

    def model_of(img):
        b16 = bytes(int(x, 16) for x in img.split())
        m = bm.Best()
        m.magic = int.from_bytes(b16[0:4], "big")
        m.score10 = [int.from_bytes(b16[4:8], "big"),
                     int.from_bytes(b16[8:12], "big"),
                     int.from_bytes(b16[12:16], "big")]
        m.sum = int.from_bytes(b16[16:18], "big")
        return m

    script = "R\nH\n"
    for img, _ in cases:
        script += "L %s\nV\n" % img
    script += "L %s\nV\n" % reset_img
    lines = run(script)
    assert lines[0] == reset_img + " (18 bytes)", lines[0]
    for k, (img, what) in enumerate(cases):
        got = lines[1 + k]
        assert got == "valid=0", f"{what}: C said {got}"
        assert model_of(img).valid() == 0, what
    assert lines[1 + len(cases)] == "valid=1"
    assert model_of(reset_img).valid() == 1
