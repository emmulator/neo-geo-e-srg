"""The title's nine pages of fix text, as a pure function of (page, level,
t, best, credits): the reference tests/test_title.py holds the C's
src/title.c (built for the host as build/title_sim) to, exact string
equality on all 28 rows (M6 Task 5).

The rules (from the plan; the Vectrex's title_screen / text_lines in
vectrex-e-srg 1.1.0 src/e-srg.c):

  - rows 0..27, 40 chars each, spaces where empty;
  - lines are centred: col = (40 - len) / 2, rounded down;
  - a run of "|"-prefixed lines (the "|" is not drawn) is one block: every
    line of the run starts at the same column, which centres the run's
    longest line (the Vectrex's \\x01 column rule);
  - pages other than 0: lines start on row 6 and step 2 rows per line; an
    empty string is an empty line that still takes its 2 rows;
  - page 0 (the dome page; the M8 art pass): rows LOGO_ROW.. hold the
    "E-SRG" logo's fix tiles — LOGO_COLS x LOGO_ROWS tile codes from
    LOGO_FIRST, row by row, from col LOGO_COL (the row's characters are
    the codes, chr(code)); row TITLE_LEVEL_ROW the level name; row
    TITLE_BEST_ROW the level's best score best[level]*10, no leading zeros
    ("0" if 0); row TITLE_PRESS_ROW, under the dome, "B TO CHANGE LEVEL"
    when (t * 50 // 59) & 64, else "PRESS START" (credits 0 = AES, 2 = MVS
    after a coin) or "INSERT COIN" (credits 1 = MVS before a coin). The
    other rows stay blank. Row 28 is never written (the MVS countdown owns
    it: flow.c, at cols 19..20 under the prompt). The numbers come from
    src/title.h (tests/layout.py).

A ("best", k) entry in a page table is the k-th level's best score
(best[k] * 10) as its own centred line.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layout import d as _lay  # noqa: E402

COLS = 40
LOGO_FIRST, LOGO_COLS, LOGO_ROWS, LOGO_COL, LOGO_ROW = (
    _lay.title(n) for n in ("LOGO_FIRST", "LOGO_COLS", "LOGO_ROWS", "LOGO_COL", "LOGO_ROW"))
LEVEL_ROW, BEST_ROW, PRESS_ROW = (
    _lay.title(n) for n in ("TITLE_LEVEL_ROW", "TITLE_BEST_ROW", "TITLE_PRESS_ROW"))


def logo_row(i):
    """the logo's i-th fix row (0..LOGO_ROWS-1) as a 40-char string"""
    row = [" "] * COLS
    for c in range(LOGO_COLS):
        row[LOGO_COL + c] = chr(LOGO_FIRST + i * LOGO_COLS + c)
    return "".join(row)
ROWS = 30                     # the title's own rows are 0..27; rows 28/29
                              # exist so the rows title_rows must NEVER write
                              # (28: the MVS countdown's row) are compared too
PAGES = 9

LEVEL_NAMES = ("EASY", "NORMAL", "HARD")

# pages 1..8; page 0 (the dome page) is built directly in title_rows.
PAGE_TABLES = [
    None,
    # 1: HIGH SCORES — each <bestN> its own centred line
    ["HIGH SCORES", "", "EASY", ("best", 0), "", "NORMAL", ("best", 1), "",
     "HARD", ("best", 2)],
    # 2: CONTROLS — the five "|" lines are one block (the Vectrex \x01 rule)
    ["CONTROLS", "", "|STICK  MOVE", "|A      FIRE", "|B      JUMP, LEVEL",
     "|C      NEXT PAGE", "|START  PLAY"],
    # 3
    ["DEFEND THE DOME", "", "SHOOT MISSILES", "BEFORE THEY HIT", "",
     "HITS CRACK TILES", "", "JUMP OVER CRACKS", "", "AT 0% DOME COLLAPSES"],
    # 4: LEVELS (cracks) — the three "|" lines are one block
    ["LEVELS", "", "A TILE CRACKS WITH", "N CRACKED NEIGHBORS", "",
     "|EASY   N = 5", "|NORMAL N = 4", "|HARD   N = 3"],
    # 5: LEVELS (collapse costs) — three "|" lines, one block
    ["LEVELS", "", "DOME COLLAPSE COSTS", "", "|EASY   NOTHING",
     "|NORMAL ONE LIFE", "|HARD   THE GAME", "", "EASY MISSILES ARE SLOWER"],
    # 6: RADAR / score
    ["RADAR", "", "BLINKS AND BEEPS", "WHEN LOCKED ON", "", "SCORE", "",
     "1000 POINTS TIMES", "DOME INTEGRITY", "PER MISSILE"],
    # 7: CREDITS
    ["CREDITS", "", "GAME DESIGN:", "JOHN EMMER", "", "IMPLEMENTATION:",
     "CLAUDE OPUS 5.5", "AND DEEPSEEK V4 FLASH", "", "(C) 2026"],
    # 8: BUILT WITH
    ["BUILT WITH", "", "NGDEVKIT: DAMIEN CIABRINI", "GCC 15.3", "MAME"],
]


def _put(row, text, col):
    for i, ch in enumerate(text):
        if 0 <= col + i < COLS:
            row[col + i] = ch


def _centre(row, text):
    _put(row, text, (COLS - len(text)) // 2)


def title_rows(page, level, t, best, credits):
    """the 30 fix rows (list of 40-char strings) the title must show
    (rows 0..27 the title's text, 28/29 blank: the countdown's own pair)."""
    rows = [[" "] * COLS for _ in range(ROWS)]
    if page == 0:
        for i in range(LOGO_ROWS):
            rows[LOGO_ROW + i] = list(logo_row(i))
        _centre(rows[LEVEL_ROW], LEVEL_NAMES[level])
        _centre(rows[BEST_ROW], str(best[level] * 10))
        if (t * 50 // 59) & 64:      # the Vectrex's title_t & 64, in its 50 Hz frames
            _centre(rows[PRESS_ROW], "B TO CHANGE LEVEL")
        else:
            _centre(rows[PRESS_ROW], "INSERT COIN" if credits == 1 else "PRESS START")
        return ["".join(r) for r in rows]
    lines = PAGE_TABLES[page]
    row = 6                       # pages other than 0: start at row 6,
    i = 0
    while i < len(lines):         # step 2 rows per line
        line = lines[i]
        if isinstance(line, tuple):               # ("best", k)
            text = str(best[line[1]] * 10)
            _centre(rows[row], text)
            row += 2
            i += 1
        elif line.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1                            # the block's span: i..j-1
            maxn = max(len(lines[k][1:]) for k in range(i, j))
            col = (COLS - maxn) // 2              # centres the longest line
            for k in range(i, j):
                _put(rows[row], lines[k][1:], col)
                row += 2
            i = j
        else:
            _centre(rows[row], line)
            row += 2
            i += 1
    return ["".join(r) for r in rows]
