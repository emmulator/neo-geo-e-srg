"""The title's eleven pages of fix text, as a pure function of (page, level,
t, board, credits): the reference tests/test_title.py holds the C's
src/title.c (built for the host as build/title_sim) to, exact string
equality on all 30 rows (M6 Task 5; high-score boards Task B3).

The rules (from the plan; the Vectrex's title_screen / text_lines in
vectrex-e-srg 1.1.0 src/e-srg.c; the approved high-score mockup for the
board pages):

  - rows 0..29, 40 chars each, spaces where empty;
  - lines are centred: col = (40 - len) / 2, rounded down;
  - a run of "|"-prefixed lines (the "|" is not drawn) is one block: every
    line of the run starts at the same column, which centres the run's
    longest line (the Vectrex's \\x01 column rule);
  - pages 4..10: lines start on row 6 and step 2 rows per line; an empty
    string is an empty line that still takes its 2 rows;
  - every text line's row r gets its cap row r + 1 (attract Task A1): the
    cap tile's row 0 is the glyph's bottom outline row, so the row's
    characters repeat the text row's characters at the same columns (the
    caps' tile numbers are TITLE_CAP_BASE + code; src/title.h);
  - page 0 (the dome page; the M8 art pass): rows LOGO_ROW.. hold the
    "E-SRG" logo's fix tiles — LOGO_COLS x LOGO_ROWS tile codes from
    LOGO_FIRST, row by row, from col LOGO_COL (the row's characters are
    the codes, chr(code)); the logo's outline is inside its own block, so
    its rows get no caps; row TITLE_LEVEL_ROW the level name; row
    TITLE_BEST_ROW the level's board's top entry score10 x 10, no leading
    zeros ("0" if 0); row TITLE_PRESS_ROW, above the console, "B TO CHANGE
    LEVEL" when (t * 50 // 59) & 64, else "PRESS START" (credits 0 = AES,
    2 = MVS after a coin) or "INSERT COIN" (credits 1 = MVS before a
    coin). The other rows stay blank. Row 28 is never written (the MVS
    countdown owns it: flow.c, at cols 19..20). The numbers come from
    src/title.h (tests/layout.py).
  - pages 1..3 are the high-score boards, one per difficulty (EASY,
    NORMAL, HARD; high-score boards Task B3):
      row TITLE_BOARD_HEADER_ROW "HIGH SCORES";
      row TITLE_BOARD_LEVEL_ROW the level's name;
      rows TITLE_BOARD_FIRST_ROW.. step TITLE_BOARD_STEP, five entries:
      the rank ("1ST".."5TH"), two spaces, the three initials, two spaces
      and the score10 x 10 right-aligned in TITLE_BOARD_SCORE_WIDTH
      columns, the whole entry centred (the mockup's "1ST  SRG   50000").
      The star/heart initials are their codes 1/2 (B4's font draws them;
      until then the old title font's tiles 1/2 are blank).
      Each line's cap row repeats it (rows 7, 9 and 12, 14, 16, 18, 20);
      row 10 is blank.

The board is a tests/board_model.Board: its entries give the initials and
score10 values the C reads from the packed board_t.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layout import d as _lay  # noqa: E402
import board_model as bm  # noqa: E402

COLS = 40
LOGO_FIRST, LOGO_COLS, LOGO_ROWS, LOGO_COL, LOGO_ROW = (
    _lay.title(n) for n in ("LOGO_FIRST", "LOGO_COLS", "LOGO_ROWS", "LOGO_COL", "LOGO_ROW"))
LEVEL_ROW, BEST_ROW, VER_ROW, PRESS_ROW = (
    _lay.title(n) for n in ("TITLE_LEVEL_ROW", "TITLE_BEST_ROW", "TITLE_VER_ROW",
                            "TITLE_PRESS_ROW"))
# the release: src/title.h's E_SRG_VERSION, shown as "V" + it
VERSION = "V" + re.search(
    r'#define E_SRG_VERSION\s+"([^"]*)"',
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src",
                      "title.h")).read()).group(1)
BOARD_HEADER_ROW, BOARD_LEVEL_ROW, BOARD_FIRST_ROW, BOARD_STEP, BOARD_ROWS, \
    BOARD_SCORE_WIDTH = (_lay.title(n) for n in (
        "TITLE_BOARD_HEADER_ROW", "TITLE_BOARD_LEVEL_ROW",
        "TITLE_BOARD_FIRST_ROW", "TITLE_BOARD_STEP", "TITLE_BOARD_ROWS",
        "TITLE_BOARD_SCORE_WIDTH"))


def logo_row(i):
    """the logo's i-th fix row (0..LOGO_ROWS-1) as a 40-char string"""
    row = [" "] * COLS
    for c in range(LOGO_COLS):
        row[LOGO_COL + c] = chr(LOGO_FIRST + i * LOGO_COLS + c)
    return "".join(row)
ROWS = 30                     # the title's own rows are 0..27; rows 28/29
                              # exist so the rows title_rows must NEVER write
                              # (28: the MVS countdown's row) are compared too
PAGES = _lay.title("TITLE_PAGES")

LEVEL_NAMES = ("EASY", "NORMAL", "HARD")
RANKS = ("1ST", "2ND", "3RD", "4TH", "5TH")

# pages 4..10; pages 0..3 are built directly in title_rows.
PAGE_TABLES = [
    None, None, None, None,
    # 4: CONTROLS — the five "|" lines are one block (the Vectrex \x01 rule)
    ["CONTROLS", "", "|STICK  MOVE", "|A      FIRE", "|B      JUMP, LEVEL",
     "|C      NEXT PAGE", "|START  PLAY"],
    # 5
    ["DEFEND THE DOME", "", "SHOOT MISSILES", "BEFORE THEY HIT", "",
     "HITS CRACK TILES", "", "JUMP OVER CRACKS", "", "AT 0% DOME COLLAPSES"],
    # 6: LEVELS (cracks) — the three "|" lines are one block
    ["LEVELS", "", "A TILE CRACKS WITH", "N CRACKED NEIGHBORS", "",
     "|EASY   N = 5", "|NORMAL N = 4", "|HARD   N = 3"],
    # 7: LEVELS (collapse costs) — three "|" lines, one block
    ["LEVELS", "", "DOME COLLAPSE COSTS", "", "|EASY   NOTHING",
     "|NORMAL ONE LIFE", "|HARD   THE GAME", "", "MISSILES ARE SLOWER ON EASY"],
    # 8: RADAR / score
    ["RADAR", "", "BLINKS AND BEEPS", "WHEN LOCKED ON", "", "SCORE", "",
     "1000 POINTS TIMES", "DOME INTEGRITY", "PER MISSILE"],
    # 9: CREDITS
    ["CREDITS", "", "GAME DESIGN:", "JOHN EMMER", "", "IMPLEMENTATION:",
     "CLAUDE OPUS 5.5", "AND DEEPSEEK V4.1 FLASH 1017", "", "(C) 2026"],
    # 10: BUILT WITH
    ["BUILT WITH", "", "NGDEVKIT: DAMIEN CIABRINI", "GCC 15.3", "MAME"],
]


def entry_line(e, init, score10):
    """one board entry: rank, two spaces, initials, two spaces and the score
    right-aligned in BOARD_SCORE_WIDTH columns (the mockup's layout)."""
    # the font's tables cover 0..127 and map unknown codes to space; the C
    # writer (B4) also draws a saved initial above 126 as a space, so the
    # model must too.
    initials = "".join(chr(b if b in (1, 2) or 32 <= b <= 126 else 32)
                       for b in init)
    return (RANKS[e] + "  " + initials + "  "
            + str(score10 * 10).rjust(BOARD_SCORE_WIDTH))


def _put(row, text, col):
    for i, ch in enumerate(text):
        if 0 <= col + i < COLS:
            row[col + i] = ch


def _centre(row, text):
    _put(row, text, (COLS - len(text)) // 2)


def title_rows(page, level, t, board, credits):
    """the 30 fix rows (list of 40-char strings) the title must show
    (rows 0..25 the title's text and caps, 28/29 blank: the countdown's own
    pair). board is the tests/board_model.Board."""
    rows = [[" "] * COLS for _ in range(ROWS)]
    text_rows = []
    if page == 0:
        for i in range(LOGO_ROWS):
            rows[LOGO_ROW + i] = list(logo_row(i))
        _centre(rows[LEVEL_ROW], LEVEL_NAMES[level])
        text_rows.append(LEVEL_ROW)
        top = board.entry(level, 0)[2] * 10
        _centre(rows[BEST_ROW], str(top))
        text_rows.append(BEST_ROW)
        _centre(rows[VER_ROW], VERSION)
        text_rows.append(VER_ROW)
        if (t * 50 // 59) & 64:      # the Vectrex's title_t & 64, in its 50 Hz frames
            _centre(rows[PRESS_ROW], "B TO CHANGE LEVEL")
        else:
            _centre(rows[PRESS_ROW], "INSERT COIN" if credits == 1 else "PRESS START")
        text_rows.append(PRESS_ROW)
    elif page <= 3:
        board_level = page - 1
        _centre(rows[BOARD_HEADER_ROW], "HIGH SCORES")
        text_rows.append(BOARD_HEADER_ROW)
        _centre(rows[BOARD_LEVEL_ROW], LEVEL_NAMES[board_level])
        text_rows.append(BOARD_LEVEL_ROW)
        row = BOARD_FIRST_ROW
        for e in range(BOARD_ROWS):
            init, _pad, score10 = board.entry(board_level, e)
            _centre(rows[row], entry_line(e, init, score10))
            text_rows.append(row)
            row += BOARD_STEP
    else:
        lines = PAGE_TABLES[page]
        row = 6                       # pages other than 0: start at row 6,
        i = 0
        while i < len(lines):         # step 2 rows per line
            line = lines[i]
            if line.startswith("|"):
                j = i
                while j < len(lines) and lines[j].startswith("|"):
                    j += 1                            # the block's span: i..j-1
                maxn = max(len(lines[k][1:]) for k in range(i, j))
                col = (COLS - maxn) // 2              # centres the longest line
                for k in range(i, j):
                    _put(rows[row], lines[k][1:], col)
                    text_rows.append(row)
                    row += 2
                i = j
            else:
                _centre(rows[row], line)
                text_rows.append(row)
                row += 2
                i += 1
    # attract Task A1: every text row's caps sit in the blank row below it
    for r in text_rows:
        rows[r + 1] = list(rows[r])
    return ["".join(r) for r in rows]
