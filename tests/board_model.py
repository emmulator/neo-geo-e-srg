"""The five-entry per-level high-score board, as a pure model: the
reference tests/test_board.py holds the C's src/board.c (built for the host
as build/board_sim) to, exact bytes included, after every operation
(high-score boards Task B1).

The rules (from the task and the approved design):

  - board_t is 126 bytes, laid out as the 68000 stores it (big-endian, no
    implicit padding — the C declares the struct packed with one explicit
    pad byte per entry, so the host build gives the same offsets):
        offset 0    u32 magic;         'ESR2' = 0x45535232, bytes 45 53 52 32
        offset 4    the entries: 3 levels x 5 entries, each 8 bytes:
              +0  init[3]   the three initials (single bytes)
              +3  pad       0 (keeps score10 at an even 68000 address)
              +4  u32 score10  the score / 10, big-endian
        offset 124  u16 sum;           the 16-bit wrap-around byte sum of
                                       bytes 0..123, in memory order
  - the defaults, on every level, are the design's displayed scores
    SRG 50,000 ... VEC 10,000; stored as score/10 (5000 ... 1000) and
    shown x 10 on the title (the existing best-line convention).
  - board_valid: 1 iff the magic and sum are right, every score is
    <= SCORE_MAX (9,999,999, src/missiles.h), and each level's entries are
    descending. Initials are any bytes.
  - board_rank(b, level, score10): the first index i with
    score10 > entry[i].score10, else 5 — strictly greater, so an equal
    score goes below the entries it equals and an equal-to-5th score does
    not qualify. level >= 3 -> 5.
  - board_insert(b, level, rank, init, score10): shifts entries [rank..3]
    down to [rank+1..4] (dropping the 5th), stores init and score10 at
    rank with pad 0, and fixes the sum. level >= 3 or rank >= 5 changes
    nothing.

The model works on the bytes: every mutation stores through the same
big-endian encoding the C's packed struct has in memory, so the two cannot
drift apart in layout.
"""

SCORE_MAX = 9999999          # src/missiles.h, score / 10
MAGIC = 0x45535232           # 'ESR2'
NLEVELS = 3
NENTRIES = 5
NINIT = 3
ENTRY_BASE = 4
ENTRY_SIZE = 8
SCORE_OFF = 4                # within an entry, after init[3] + pad
SUM_OFF = ENTRY_BASE + NLEVELS * NENTRIES * ENTRY_SIZE   # 124
BYTES = SUM_OFF + 2          # 126

# the design's displayed defaults = these score10 values x 10
DEFAULTS = [("SRG", 5000), ("HEX", 4000), ("DOM", 3000),
            ("ZAP", 2000), ("VEC", 1000)]


def _u32be(v):
    return bytes([(v >> 24) & 0xff, (v >> 16) & 0xff,
                  (v >> 8) & 0xff, v & 0xff])


def _u16be(v):
    return bytes([(v >> 8) & 0xff, v & 0xff])


def _get_u32(buf, off):
    return int.from_bytes(bytes(buf[off:off + 4]), "big")


def _put_u32(buf, off, v):
    buf[off:off + 4] = _u32be(v)


def _get_u16(buf, off):
    return int.from_bytes(bytes(buf[off:off + 2]), "big")


def _put_u16(buf, off, v):
    buf[off:off + 2] = _u16be(v)


def entry_offset(level, e):
    """the byte offset of entry e (0..4) on level (0..2)"""
    return ENTRY_BASE + (level * NENTRIES + e) * ENTRY_SIZE


def byte_sum(buf):
    """the 16-bit wrap-around sum of the 124 bytes before the sum."""
    return sum(buf[0:SUM_OFF]) & 0xffff


class Board:
    def __init__(self):
        self.reset()

    def reset(self):
        b = bytearray(BYTES)
        _put_u32(b, 0, MAGIC)
        for level in range(NLEVELS):
            for e, (name, score) in enumerate(DEFAULTS):
                o = entry_offset(level, e)
                b[o:o + NINIT] = name.encode("ascii")
                b[o + NINIT] = 0                 # pad
                _put_u32(b, o + SCORE_OFF, score)
        _put_u16(b, SUM_OFF, byte_sum(b))
        self.b = b

    def bytes126(self):
        assert len(self.b) == BYTES, len(self.b)
        return bytes(self.b)

    def hexb(self):
        return " ".join("%02x" % x for x in self.b)

    def load(self, image):
        """load a 126-byte image (bytes or a hex string)"""
        if isinstance(image, str):
            image = bytes(int(x, 16) for x in image.split())
        assert len(image) == BYTES, len(image)
        self.b = bytearray(image)

    def entry(self, level, e):
        """(init bytes, pad, score10) of an entry"""
        o = entry_offset(level, e)
        return (bytes(self.b[o:o + NINIT]), self.b[o + NINIT],
                _get_u32(self.b, o + SCORE_OFF))

    def valid(self):
        if _get_u32(self.b, 0) != MAGIC:
            return 0
        if _get_u16(self.b, SUM_OFF) != byte_sum(self.b):
            return 0
        for level in range(NLEVELS):
            prev = None
            for e in range(NENTRIES):
                s = _get_u32(self.b, entry_offset(level, e) + SCORE_OFF)
                if s > SCORE_MAX:
                    return 0
                if prev is not None and s > prev:
                    return 0             # not descending
                prev = s
        return 1

    def rank(self, level, score10):
        if level >= NLEVELS:
            return NENTRIES
        for e in range(NENTRIES):
            if score10 > _get_u32(self.b, entry_offset(level, e) + SCORE_OFF):
                return e                 # strictly greater: below equals
        return NENTRIES

    def insert(self, level, rank, init, score10):
        if level >= NLEVELS or rank >= NENTRIES:
            return
        o = entry_offset(level, rank)
        for e in range(NENTRIES - 1, rank, -1):
            src = entry_offset(level, e - 1)
            dst = entry_offset(level, e)
            self.b[dst:dst + ENTRY_SIZE] = self.b[src:src + ENTRY_SIZE]
        self.b[o:o + NINIT] = bytes(init)
        self.b[o + NINIT] = 0
        _put_u32(self.b, o + SCORE_OFF, score10)
        _put_u16(self.b, SUM_OFF, byte_sum(self.b))
