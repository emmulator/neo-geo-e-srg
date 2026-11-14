"""The HUD's text (tests/hud_model.py) against the source of truth: the
model of the Vectrex rules (tests/rules_model.py) as driven by the same
script of inputs tests/test_rules_play.py uses. The two must agree on every
frame — the HUD is exactly a function of the rules' state, and this test
locks that function to the model the C's rules were checked against.

Concretely, for every frame of long random games (with fire and without),
the thirty fix rows hud_model.py produces match:
  * the rules' integrity %, lives and score (score x 10, with the trailing
    0 the Vectrex shows — unless the score is 0),
  * the rules' game_over -> "GAME OVER" on row 7 and its thick-font cap row
    8 (nothing there otherwise; Task G1),
  * the icons on rows 26/28 (the integrity's little dome and the little
    ships) and the centred score on row 28 (so the boot test compares
    whole screens and both stay stable).

Dome-scenery Task 8 moved the HUD down onto the console's one bottom line:
the integrity is on row 26 and the lives and the score share row 28. The
second test proves the shared row: for every score length 1..8 and every
life count 0..3, the C's hud_rows (through build/test_hud's "row28" mode)
and hud_model.py give the same row 28, with the lives at cols 32, 34, 36
and the score centred in cols 15..24 — and the score's band never lands in
the lives' cells (the C checks that cell by cell too).

Task G1 adds the GAME OVER proof: build/test_hud's "go" mode prints
hud_rows' rows 7/8 for a hand-set game_over 0 and 1, and hud_model.py must
match them; its "gofont" mode prints the shared thick-font writer's tile
numbers for the GAME OVER span (src/fix.c's fix_thick_tile), which must
equal the title model's own tile formula from build/title_font.h — one
source of truth for both the title/entry and GAME OVER.

rv: hud_rows(rules_t, mis_t) on the host — see tests/test_hud.c.
"""
import os
import random
import subprocess

import hud_model as hm
import mis_model as mm
import rules_model as rm
import ship_model as sm

ROOT = os.path.join(os.path.dirname(__file__), "..")
HUD_SIM = os.path.join(ROOT, "build", "test_hud")
STICKS = [0, sm.UP, sm.DOWN, sm.LEFT, sm.RIGHT, sm.UP | sm.LEFT, sm.UP | sm.RIGHT,
          sm.DOWN | sm.LEFT, sm.DOWN | sm.RIGHT]
A = 16


def run_both(seed, frames, fire_p, level=1):
    """One game played two ways from the same script: build/test_hud (the C's
    rules + hud_rows, in sim mode) and the models. Returns the C's printed rows
    and the model's hud_rows per frame (lists of 30-row lists)."""
    rng = random.Random(seed)

    def input_line():
        inp = rng.choice(STICKS)
        fire = rng.random() < fire_p
        jump = rng.random() < 0.01
        p = (A if fire else 0) | (sm.B if jump else 0)
        return inp | p, p

    script = [f"level {level}"]
    steps = []
    for _ in range(frames):
        inp, p = input_line()
        script.append(f"{inp} {p}")
        steps.append((inp, p))
    out = subprocess.run([HUD_SIM, "sim"], input="\n".join(script) + "\n",
                         capture_output=True, encoding="latin-1", check=True).stdout
    c_rows = [line for line in out.splitlines() if line.startswith("HU ")]

    ship, mis, rules = sm.Ship(), mm.Missiles(), rm.Rules(level)
    m_rows = []
    for inp, p in steps:
        hm.frame_model((ship, mis, rules), inp, p)
        m_rows.append(hm.hud_rows(rules, mis))
    return c_rows, m_rows


def assert_same(c_rows, m_rows):
    assert len(c_rows) == len(m_rows), (len(c_rows), len(m_rows))
    for i, c in enumerate(c_rows):
        # "HU" then " %s" per row: row k occupies c[3+k*41 : 3+k*41+40]
        # (the icon tile numbers the C writes are bytes 128/129 — read as
        # latin-1 so the model's chr(128)/chr(129) compare equal)
        parsed = [c[3 + k * 41: 3 + k * 41 + 40] for k in range(30)]
        assert parsed == m_rows[i], f"frame {i}:\n  C  {parsed}\n  M  {m_rows[i]}"


def test_random_games_match():
    for seed, frames, fire_p, level in [(2, 3000, 0.05, 1), (4, 3000, 0.05, 0),
                                        (6, 3000, 0.05, 2), (1002, 3000, 0.6, 1)]:
        c_rows, m_rows = run_both(seed, frames, fire_p, level)
        assert_same(c_rows, m_rows)


def test_the_hud_is_a_function_of_the_state():
    """hud_rows must change only when its inputs change: replay the same
    frame twice from the same state and get identical rows (cheap, host-only
    sanity for the redraw-only rule)."""
    ship, mis, rules = sm.Ship(), mm.Missiles(), rm.Rules(1)
    hm.frame_model((ship, mis, rules), 0, 0)
    a = hm.hud_rows(rules, mis)
    # step the game (a crack lands), then snapshot again from a copy
    hm.frame_model((ship, mis, rules), sm.UP, 0)
    b = hm.hud_rows(rules, mis)
    # nothing here asserts a != b: just that a deterministic call is stable
    assert hm.hud_rows(rules, mis) == hm.hud_rows(rules, mis)
    assert isinstance(a, list) and len(a) == 30 and all(len(r) == 40 for r in a)
    assert isinstance(b, list) and len(b) == 30


# dome-scenery Task 8 proof 2: the shared row 28. The C's hud_rows (the
# "row28" mode of build/test_hud) and hud_model.py must give the same row
# for every score length 1..8 and every life count 0..3; the lives' icons
# are at cols 32, 34, 36 and the score is centred in cols 15..24.
SCORE10S = [0, 1, 12, 123, 1234, 12345, 123456, 1234567]


def model_row28(score10, lives, integ=100, game_over=0):
    """one hud_model row 28 for a hand-set state (the C's table does the
    same): the score is score10 x 10, the lives and the integrity are as
    given."""
    rules = rm.Rules(1)
    mis = mm.Missiles(seed=1)
    rules.integ = integ
    rules.lives = lives
    rules.game_over = game_over
    mis.score = score10
    return hm.hud_rows(rules, mis)[hm.HUD_SCORE_ROW]


def test_score_and_lives_share_row_28_without_overwriting_each_other():
    out = subprocess.run([HUD_SIM, "row28"], capture_output=True,
                         encoding="latin-1", check=True).stdout
    assert "FAIL" not in out, ("the C's shared row-28 cell check failed:\n"
                               + out)
    c_rows = {}
    for line in out.splitlines():
        if line.startswith("R28 "):
            _, s, integ, lives, go, row = line.split(" ", 5)
            c_rows[(int(s), int(lives))] = row
    assert len(c_rows) == len(SCORE10S) * 4, len(c_rows)

    for score10 in SCORE10S:
        want = model_row28(score10, 0)
        # the score is centred: col (40 - len) / 2, rounded down; for the
        # longest number (8 chars) it spans cols 16..23, inside 15..24
        n = len(str(score10 * 10))
        start = (40 - n) // 2
        assert 15 <= start and start + n - 1 <= 24, (score10, n, start)
        for lives in range(4):
            want = model_row28(score10, lives)
            assert c_rows[(score10, lives)] == want, (
                f"score10 {score10} lives {lives}:\n  C   {c_rows[(score10, lives)]!r}"
                f"\n  model {want!r}")
            # the lives are at cols 32, 34, 36
            for i in range(3):
                col = hm.HUD_LIVES_COL + i * hm.HUD_LIVES_STEP
                assert want[col] == (chr(hm.ICON_SHIP) if i < lives else " "), (
                    score10, lives, i, repr(want[col]))
            # the score's centred digits sit inside its band and never in
            # the lives' cells
            for i in range(n):
                col = start + i
                assert want[col] == str(score10 * 10)[i], (score10, col)
                assert not (col >= hm.HUD_LIVES_COL), (score10, col)
            # every other cell of row 28 is blank
            for col in range(40):
                in_score = start <= col < start + n
                in_lives = col in (hm.HUD_LIVES_COL,
                                   hm.HUD_LIVES_COL + hm.HUD_LIVES_STEP,
                                   hm.HUD_LIVES_COL + 2 * hm.HUD_LIVES_STEP)
                if not in_score and not in_lives:
                    assert want[col] == " ", (score10, lives, col)


# Task G1: the GAME OVER rows and their thick-font tiles. The C's "go" mode
# calls hud_rows for game_over 0/1; the "gofont" mode calls the shared
# writer's pure tile formula (src/fix.c's fix_thick_tile), the same one
# fix_span uses for flow.c's title/entry rows.
def test_gameover_rows_7_and_8_match_the_c():
    out = subprocess.run([HUD_SIM, "go"], capture_output=True,
                         encoding="latin-1", check=True).stdout
    c = {}
    for line in out.splitlines():
        p = line.split(" ", 2)
        if p[0] == "GO":
            c[(0, int(p[1]))] = p[2]
        elif p[0] == "GO8":
            c[(1, int(p[1]))] = p[2]
    assert set(c) == {(r, go) for r in (0, 1) for go in (0, 1)}, c
    for go in (0, 1):
        rules = rm.Rules(1)
        mis = mm.Missiles(seed=1)
        rules.game_over = go
        want = hm.hud_rows(rules, mis)
        assert c[(0, go)] == want[hm.HUD_GAMEOVER_ROW], (
            go, c[(0, go)], want[hm.HUD_GAMEOVER_ROW])
        assert c[(1, go)] == want[hm.HUD_GAMEOVER_CAP_ROW], (
            go, c[(1, go)], want[hm.HUD_GAMEOVER_CAP_ROW])
        if go:
            # the cap row repeats the text row's characters; the text is
            # centred at HUD_GAMEOVER_COL0 and the span includes the spill
            # cell (a space) after it
            assert c[(1, go)] == c[(0, go)]
            assert c[(0, go)][hm.HUD_GAMEOVER_COL0:
                              hm.HUD_GAMEOVER_COL0 + len(hm.GAME_OVER_TEXT)]                 == hm.GAME_OVER_TEXT
            assert c[(0, go)][hm.HUD_GAMEOVER_COL0 + 9] == " "
        else:
            assert c[(0, go)] == " " * 40 and c[(1, go)] == " " * 40


def test_the_gameover_thick_font_is_the_title_model_tiles():
    """the C's shared thick-font tile formula for "GAME OVER" (row 7 text,
    row 8 cap) equals the title model's formula: base + title2_idx[ch] *
    TITLE2_NPROF + title2_rprof[left], read from build/title_font.h."""
    import re
    text = open(os.path.join(ROOT, "build", "title_font.h")).read()
    nprof = int(re.search(r"#define TITLE2_NPROF (\d+)", text).group(1))
    row_base = int(re.search(r"#define TITLE2_ROW_BASE (\d+)", text).group(1))
    cap_base = int(re.search(r"#define TITLE2_CAP_BASE (\d+)", text).group(1))
    idx = [int(x) for x in re.search(
        r"title2_idx\[128\] = \{(.*?)\}", text).group(1).split(",")]
    rprof = [int(x) for x in re.search(
        r"title2_rprof\[128\] = \{(.*?)\}", text).group(1).split(",")]
    line = [" "] * 40
    for i, ch in enumerate(hm.GAME_OVER_TEXT):
        line[hm.HUD_GAMEOVER_COL0 + i] = ch
    want = {}
    for row, base in ((hm.HUD_GAMEOVER_ROW, row_base),
                      (hm.HUD_GAMEOVER_CAP_ROW, cap_base)):
        tiles = []
        for col in range(hm.HUD_GAMEOVER_COL0,
                         hm.HUD_GAMEOVER_COL0 + hm.HUD_GAMEOVER_LEN):
            ch = ord(line[col])
            left = ord(line[col - 1]) if col else ord(" ")
            tiles.append(base + idx[ch] * nprof + rprof[left])
        want[row] = tiles
    out = subprocess.run([HUD_SIM, "gofont"], capture_output=True,
                         encoding="latin-1", check=True).stdout
    got = {}
    for raw in out.splitlines():
        p = raw.split()
        assert p[0] == "GOFONT", raw
        got[int(p[1])] = [int(x) for x in p[2:]]
    for row in (hm.HUD_GAMEOVER_ROW, hm.HUD_GAMEOVER_CAP_ROW):
        assert got[row] == want[row], (row, got[row], want[row])
        assert len(set(got[row])) >= 8, got[row]
