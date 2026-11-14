"""The title's nine pages of fix text: src/title.c (built for the host as
build/title_sim) must equal tests/title_model.py on every page 0..8, every
level, t at each edge of the prompt swap (0..294), every credits value, and three best
tables. The spot asserts below are written by hand (not from the model):
the literal strings and columns the HUD-layout Task 3 plan promises,
checked against the C's output directly (the task's proof 1).

The rule being locked: page 0 (the M8 art pass) has the logo's tiles on
rows 2..5 (130..193, 16 a row, from col 12), the level on row 7, its best
x 10 on row 9 (ends at screen y 63, above the lifted dome's top, 72) and,
under the dome on row 27, the prompt that swaps on the Vectrex's t & 64 in
its 50 Hz frames; every other row blank. Row 28 is never written (the MVS
countdown owns it: flow.c, under the prompt). The
pages' centred lines start at row 6 and step 2 rows, and the "|" block
rule — a run of "|"-prefixed lines (the "|" not drawn) starts every line
at one column, the column that centres the block's longest line (the
Vectrex's \\x01 column rule).
"""
import os
import subprocess

import title_model as tm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "title_sim")

# the three best tables the proof grid runs
BESTS = [(0, 0, 0), (12340, 0, 99999999), (5, 50, 500)]
TS = [0, 75, 76, 151, 152, 226, 227, 294]   # the swap's edges: t * 50 // 59 crosses 64, 128, 192


def run_one(page, level, t, best, credits):
    """the C's TITLE_ROWS rows for one call (one title_sim invocation)."""
    out = subprocess.run(
        [SIM],
        input=f"{page} {level} {t} {best[0]} {best[1]} {best[2]} {credits}\n",
        capture_output=True, encoding="latin-1", check=True).stdout
    lines = out.split("\n")[:-1]   # (not splitlines: logo tile 0x85 is a line break to it)
    assert len(lines) == tm.ROWS, lines
    return lines


def test_title_sim_matches_the_model_every_page_level_t_credits_best():
    cases = [(p, l, t, b, c)
             for p in range(tm.PAGES)
             for l in range(3)
             for t in TS
             for b in BESTS
             for c in range(3)]
    script = "".join(f"{p} {l} {t} {b[0]} {b[1]} {b[2]} {c}\n"
                     for p, l, t, b, c in cases)
    out = subprocess.run([SIM], input=script, capture_output=True,
                         encoding="latin-1", check=True).stdout
    lines = out.split("\n")[:-1]   # (not splitlines: logo tile 0x85 is a line break to it)
    want = len(cases) * tm.ROWS
    assert len(lines) == want, f"{len(lines)} rows, want {want}"
    for k, (p, l, t, b, c) in enumerate(cases):
        got = lines[k * tm.ROWS:(k + 1) * tm.ROWS]
        want_rows = tm.title_rows(p, l, t, b, c)
        assert got == want_rows, \
            f"page {p} level {l} t {t} best {b} credits {c}:\n" + \
            "\n".join(f"{i:2}: C    {got[i]!r}\n   model {want_rows[i]!r}"
                      for i in range(tm.ROWS) if got[i] != want_rows[i])


def test_page0_logo_level_and_best():
    rows = run_one(0, 1, 0, (0, 12340, 0), 0)
    # best[1] * 10 = 123400, 6 chars, centred: (40 - 6) / 2 = 17, row 9
    assert rows[9] == " " * 17 + "123400" + " " * 17
    rows = run_one(0, 1, 0, (0, 0, 0), 0)
    # the logo: tiles 130.. on rows 2..5, 16 a row, cols 12..27
    for i in range(4):
        assert rows[2 + i] == (" " * 12 + "".join(chr(130 + 16 * i + c) for c in range(16))
                               + " " * 12)
    # row 7 the level name (`NORMAL`, 6 chars, centred at 17), row 9 its best
    assert rows[7] == " " * 17 + "NORMAL" + " " * 17
    assert rows[9] == " " * 19 + "0" + " " * 20
    assert rows[6] == " " * 40
    assert rows[8] == " " * 40


def test_page0_row27_prompt_and_cols():
    rows = run_one(0, 0, 76, (0, 0, 0), 0)
    # "B TO CHANGE LEVEL", 17 chars, (40 - 17) / 2 = 11 (from t 76: the
    # Vectrex's 64 frames at 50 Hz are 75.5 here), under the dome: row 27
    assert rows[27] == " " * 11 + "B TO CHANGE LEVEL" + " " * 12
    assert run_one(0, 0, 75, (0, 0, 0), 0)[27] == " " * 14 + "PRESS START" + " " * 15
    rows = run_one(0, 0, 0, (0, 0, 0), 1)
    # "INSERT COIN", 11 chars, (40 - 11) / 2 = 14
    assert rows[27] == " " * 14 + "INSERT COIN" + " " * 15
    # credits 2 (a credit on MVS) presses start, AES presses start too
    rows = run_one(0, 0, 0, (0, 0, 0), 2)
    assert rows[27] == " " * 14 + "PRESS START" + " " * 15


def test_page2_controls_block_lines_all_start_at_col_11():
    rows = run_one(2, 0, 0, (0, 0, 0), 0)
    # the five "|" lines are one block: every line starts at the column
    # that centres the longest, "B      JUMP, LEVEL" (18 chars) -> col 11.
    # Page 2's lines sit at rows 6 (CONTROLS), 8 (empty), then the block
    # at 10, 12, 14, 16, 18.
    assert rows[6] == " " * 16 + "CONTROLS" + " " * 16
    assert rows[8] == " " * 40
    assert rows[10] == " " * 11 + "STICK  MOVE" + " " * 18
    assert rows[12] == " " * 11 + "A      FIRE" + " " * 18
    assert rows[14] == " " * 11 + "B      JUMP, LEVEL" + " " * 11
    assert rows[16] == " " * 11 + "C      NEXT PAGE" + " " * 13
    assert rows[18] == " " * 11 + "START  PLAY" + " " * 18
    # "START  PLAY" (11 chars) would centre at col 14 on its own: the
    # block pushes it (and everything else) to 11.
    assert (40 - len("START  PLAY")) // 2 == 14


def test_page1_best_rows_centred():
    rows = run_one(1, 0, 0, (5, 50, 500), 0)
    assert rows[6] == " " * 14 + "HIGH SCORES" + " " * 15
    assert rows[10] == " " * 18 + "EASY" + " " * 18
    assert rows[12] == " " * 19 + "50" + " " * 19
    assert rows[16] == " " * 17 + "NORMAL" + " " * 17
    assert rows[18] == " " * 18 + "500" + " " * 19
    assert rows[22] == " " * 18 + "HARD" + " " * 18
    assert rows[24] == " " * 18 + "5000" + " " * 18


def test_page0_row28_never_written_and_rows_beyond_blank():
    for credits in range(3):
        for t in TS:
            rows = run_one(0, 2, t, (99999999, 99999999, 99999999), credits)
            # row 28 is the MVS countdown's row (flow.c), never title_rows'
            assert rows[28] == " " * 40
            for r in ([0, 1, 6, 8] + list(range(10, 27)) + [29]):
                assert rows[r] == " " * 40
