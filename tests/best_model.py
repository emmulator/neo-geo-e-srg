"""The per-level high-score table, as a pure model: the reference
tests/test_best.py holds the C's src/best.c (built for the host as
build/best_sim) to, exact bytes included, after every operation (M6
Task 8).

The rules (from the plan):

  - best_t is 18 bytes, laid out as the 68000 stores it (big-endian, no
    padding — the C declares the struct packed so the host build gives the
    same bytes):
        u32 magic;         'ESRG' = 0x45535247, bytes 45 53 52 47
        u32 score10[3];    the per-level scores (score / 10), big-endian
        u16 sum;           the 16-bit wrap-around byte sum of the 16 bytes
                           before it, read as bytes in memory order
  - best_reset: magic set, all scores 0, sum fixed.
  - best_valid: 1 iff the magic and the sum are right and every score is
    <= SCORE_MAX (9,999,999, src/missiles.h).
  - best_update(b, level, score10): keeps the higher of the stored and
    given score for that level, fixes the sum when it stores, returns 1
    iff the stored score changed; level > 2 changes nothing and returns 0.

The model works on the bytes: every mutation stores through the same
big-endian byte encoding the C's packed struct has in memory, so the two
cannot drift apart in layout.
"""

SCORE_MAX = 9999999          # src/missiles.h, score / 10
MAGIC = 0x45535247           # 'ESRG'


def _u32be(v):
    return bytes([(v >> 24) & 0xff, (v >> 16) & 0xff,
                  (v >> 8) & 0xff, v & 0xff])


def byte_sum(magic, score10):
    """the 16-bit wrap-around sum of the 16 bytes, in memory order."""
    total = 0
    for x in _u32be(magic):
        total += x
    for s in score10:
        for x in _u32be(s):
            total += x
    return total & 0xffff


class Best:
    def __init__(self):
        self.reset()

    def reset(self):
        self.magic = MAGIC
        self.score10 = [0, 0, 0]
        self.sum = byte_sum(self.magic, self.score10)

    def bytes18(self):
        b = _u32be(self.magic)
        for s in self.score10:
            b += _u32be(s)
        b += bytes([(self.sum >> 8) & 0xff, self.sum & 0xff])
        assert len(b) == 18, len(b)
        return b

    def hexb(self):
        return " ".join("%02x" % x for x in self.bytes18())

    def valid(self):
        if self.magic != MAGIC:
            return 0
        if self.sum != byte_sum(self.magic, self.score10):
            return 0
        if any(s > SCORE_MAX for s in self.score10):
            return 0
        return 1

    def update(self, level, score10):
        if level > 2:
            return 0
        if score10 <= self.score10[level]:
            return 0                    # equal and lower change nothing
        self.score10[level] = score10
        self.sum = byte_sum(self.magic, self.score10)
        return 1
