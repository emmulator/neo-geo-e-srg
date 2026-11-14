"""The title's eleven pages of fix text: src/title.c (built for the host as
build/title_sim) must equal tests/title_model.py on every page 0..10, every
level, t at each edge of the prompt swap (0..294), every credits value, and
three high-score boards. The spot asserts below are written by hand (not
from the model): the literal strings and columns the plan promises, checked
against the C's output directly (the task's proof 1).

The rule being locked: page 0 (the M8 art pass) has the logo's tiles on
rows 2..5 (130..193, 16 a row, from col 12), the level on row 7, its board's
top entry score10 x 10 on row 9 (ends at screen y 63, above the lifted
dome's top, 72) and, above the console on row 21, the prompt that swaps on
the Vectrex's t & 64 in its 50 Hz frames; every other row blank. Row 28 is
never written (the MVS countdown owns it: flow.c).

High-score boards Task B3: pages 1..3 are the boards for EASY, NORMAL and
HARD. Row 6 "HIGH SCORES", row 8 the level's name, rows 11..19 step 2 the
five entries: the rank, two spaces, the three initials, and the score10 x 10
right-aligned in a 6-wide field, the whole entry centred (the mockup's
"1ST  SRG   50000"). The star/heart initials are stored as codes 1/2 and
printed as those codes.

Pages 4..10 are the old pages 2..8: their centred lines start at row 6 and
step 2 rows, and the "|" block rule — a run of "|"-prefixed lines (the "|"
not drawn) starts every line at one column, the column that centres the
block's longest line (the Vectrex's \\x01 column rule).

Attract Task A1 adds the cap rows: every text line's row r is copied into
row r + 1, where the caps' tiles draw the glyphs' bottom outline row (the
blank row between lines). The logo's outline fits inside its 16 x 4 block,
so its rows get no caps. The model and src/title.c build the caps the same
way.

The S ROM checks (proof 2) read the built cartridge:
  * every FONT57 glyph has a new outlined title tile at TITLE_FONT_BASE +
    code: the glyph at cols 1..5, rows 1..7, filled with the 1..4 amber
    gradient, colour 5 exactly on its 8-neighbourhood outline inside the
    tile;
  * its cap tile at TITLE_CAP_BASE + code has the outline's bottom row in
    row 0 and nothing else;
  * the in-play HUD's glyph (and icon) tiles are byte-identical to before
    (a SHA-256 of the built S ROM's first 130 tiles);
  * the title palette (PAL_HUD 7) is the HUD amber gradient 1..4, black 5,
    the logo's gold gradient 6..9; the in-play palette (PAL_HUD_PLAY 11)
    keeps today's words.
"""
import hashlib
import os
import re
import subprocess
import sys

import title_model as tm
import hud_model as hm
import mis_model as mm
import rules_model as rm
import board_model as bm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "title_sim")
SROM = os.path.join(ROOT, "build", "rom", "esrg-s1.s1")
FIX_PAL = os.path.join(ROOT, "build", "fix_pal.h")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import generate_srom as gs  # noqa: E402
import layout as lay  # noqa: E402

TS = [0, 75, 76, 151, 152, 226, 227, 294]   # the swap's edges: t * 50 // 59 crosses 64, 128, 192

# the pre-A1 S ROM's first 130 tiles (tiles 0..127 the FONT57/ASCII glyphs,
# 128/129 the HUD's ship/dome icons), so a change to the HUD's glyph tiles
# fails this. Captured from the built S ROM on trunk before A1 (2026-10-26).
HUD_TILES_SHA256 = \
    "f98c4670078446161911cb125e5c0cb69b9673c16609742eb191e43f2593ef45"


def board_with(entries_by_level=None):
    """a Board whose levels' five entries are (initials, score10) pairs;
    the default board when entries_by_level is None. The packed image's
    sum is fixed as board_model's operations do."""
    b = bm.Board()
    if entries_by_level is not None:
        for level, entries in enumerate(entries_by_level):
            for e, (init, score10) in enumerate(entries):
                o = bm.entry_offset(level, e)
                b.b[o:o + bm.NINIT] = bytes(init)
                b.b[o + bm.NINIT] = 0
                bm._put_u32(b.b, o + bm.SCORE_OFF, score10)
        bm._put_u16(b.b, bm.SUM_OFF, bm.byte_sum(b.b))
    return b


# the boards the proof grid runs: the defaults; star/heart and a 6-digit
# top; an 8-digit top; and short scores so the 6-wide score field pads.
BOARDS = [bm.Board()]
_b = bm.Board()
_b.insert(0, 0, b"\x01\x02A", 12345)       # star, heart, A; 123450 displayed
_b.insert(1, 4, b"ABC", 1001)               # 10010 displayed
BOARDS.append(_b)
_b = bm.Board()
_b.insert(2, 0, b"Q  ", 9999999)            # 99999990 displayed
BOARDS.append(_b)
BOARDS.append(board_with([[(b"SRG", 5000), (b"HEX", 400), (b"DOM", 30),
                           (b"ZAP", 2), (b"VEC", 0)]] * 3))


def run_one(page, level, t, board, credits):
    """the C's TITLE_ROWS rows for one call (one title_sim invocation)."""
    out = subprocess.run(
        [SIM],
        input=f"{page} {level} {t} {credits} {board.bytes126().hex()}\n",
        capture_output=True, encoding="latin-1", check=True).stdout
    lines = out.split("\n")[:-1]   # (not splitlines: logo tile 0x85 is a line break to it)
    assert len(lines) == tm.ROWS, lines
    return lines


def run_many(cases):
    """the C's rows for every (page, level, t, board, credits) case."""
    script = "".join(f"{p} {l} {t} {c} {b.bytes126().hex()}\n"
                     for p, l, t, b, c in cases)
    out = subprocess.run([SIM], input=script, capture_output=True,
                         encoding="latin-1", check=True).stdout
    lines = out.split("\n")[:-1]   # (not splitlines: logo tile 0x85 is a line break to it)
    assert len(lines) == len(cases) * tm.ROWS, (len(lines), len(cases))
    return lines


def test_title_sim_matches_the_model_every_page_level_t_credits_board():
    cases = [(p, l, t, b, c)
             for p in range(tm.PAGES)
             for l in range(3)
             for t in TS
             for b in BOARDS
             for c in range(3)]
    lines = run_many(cases)
    for k, (p, l, t, b, c) in enumerate(cases):
        got = lines[k * tm.ROWS:(k + 1) * tm.ROWS]
        want_rows = tm.title_rows(p, l, t, b, c)
        assert got == want_rows, \
            f"page {p} level {l} t {t} board {k} credits {c}:\n" + \
            "\n".join(f"{i:2}: C    {got[i]!r}\n   model {want_rows[i]!r}"
                      for i in range(tm.ROWS) if got[i] != want_rows[i])


def test_page0_logo_level_and_best():
    b = board_with([[(b"SRG", 12340), (b"HEX", 4000), (b"DOM", 3000),
                     (b"ZAP", 2000), (b"VEC", 1000)]] * 3)
    rows = run_one(0, 1, 0, b, 0)
    # best[1] * 10 = 123400, 6 chars, centred: (40 - 6) / 2 = 17, row 9
    assert rows[9] == " " * 17 + "123400" + " " * 17
    assert rows[10] == rows[9]       # the best line's cap row
    b = bm.Board()
    rows = run_one(0, 1, 0, b, 0)
    # the logo: tiles 130.. on rows 2..5, 16 a row, cols 12..27
    for i in range(4):
        assert rows[2 + i] == (" " * 12 + "".join(chr(130 + 16 * i + c) for c in range(16))
                               + " " * 12)
    # row 7 the level name (`NORMAL`, 6 chars, centred at 17), row 8 its
    # cap row; row 9 its best (the default top 50000), row 10 its cap
    assert rows[7] == " " * 17 + "NORMAL" + " " * 17
    assert rows[8] == rows[7]
    assert rows[9] == " " * 17 + "50000" + " " * 18
    assert rows[10] == rows[9]
    assert rows[6] == " " * 40
    assert rows[11] == " " * 40
    # row 24 the release ("V" + E_SRG_VERSION, 6 chars, centred at 17),
    # row 25 its cap row
    assert rows[24] == " " * 17 + tm.VERSION + " " * 17
    assert rows[25] == rows[24]


def test_page0_row21_prompt_and_cols():
    b = bm.Board()
    rows = run_one(0, 0, 76, b, 0)
    # "B TO CHANGE LEVEL", 17 chars, (40 - 17) / 2 = 11 (from t 76: the
    # Vectrex's 64 frames at 50 Hz are 75.5 here), above the console: row 21
    assert rows[21] == " " * 11 + "B TO CHANGE LEVEL" + " " * 12
    assert rows[22] == rows[21]      # the prompt's cap row
    assert run_one(0, 0, 75, b, 0)[21] == " " * 14 + "PRESS START" + " " * 15
    rows = run_one(0, 0, 0, b, 1)
    # "INSERT COIN", 11 chars, (40 - 11) / 2 = 14
    assert rows[21] == " " * 14 + "INSERT COIN" + " " * 15
    assert rows[22] == rows[21]
    # credits 2 (a credit on MVS) presses start, AES presses start too
    rows = run_one(0, 0, 0, b, 2)
    assert rows[21] == " " * 14 + "PRESS START" + " " * 15


def test_board_pages_show_their_levels_five_entries():
    # different top entry per level, so the page picks the right board
    b = bm.Board()
    b.insert(0, 0, b"EAS", 6000)        # 60000 displayed
    b.insert(1, 0, b"NOR", 7000)        # 70000 displayed
    b.insert(2, 0, b"HAR", 8000)        # 80000 displayed
    for page, name, init, top in ((1, "EASY", "EAS", "60000"),
                                  (2, "NORMAL", "NOR", "70000"),
                                  (3, "HARD", "HAR", "80000")):
        rows = run_one(page, 1, 0, b, 0)
        # "HIGH SCORES", 11 chars, (40 - 11) / 2 = 14
        assert rows[6] == " " * 14 + "HIGH SCORES" + " " * 15
        assert rows[7] == rows[6]
        assert rows[8] == " " * ((40 - len(name)) // 2) + name + \
            " " * (40 - len(name) - (40 - len(name)) // 2)
        assert rows[9] == rows[8]
        assert rows[10] == " " * 40
        # entries: rank, two spaces, initials, two spaces, score in a 6-wide
        # right-aligned field; the whole 16-char line centred at col 12
        assert rows[11] == " " * 12 + "1ST  " + init + "   " + top + " " * 12
        assert rows[12] == rows[11]
        assert rows[13].startswith(" " * 12 + "2ND  ")
        assert rows[19].startswith(" " * 12 + "5TH  ")
        assert rows[20] == rows[19]
        assert rows[21] == " " * 40        # no prompt on a board page
    # page 0's best line is the level's top entry, not another level's
    assert run_one(0, 0, 0, b, 0)[9] == " " * 17 + "60000" + " " * 18
    assert run_one(0, 1, 0, b, 0)[9] == " " * 17 + "70000" + " " * 18
    assert run_one(0, 2, 0, b, 0)[9] == " " * 17 + "80000" + " " * 18


def test_board_entry_score_field_is_right_aligned_and_centred():
    # 123450 is 6 chars: no pad; "1ST  \x01\x02A  123450" would be 12 chars?
    # rank 3 + 2 + initials 3 + 2 + 6 = 16, centred at 12
    b = BOARDS[1]
    rows = run_one(1, 0, 0, b, 0)
    assert rows[11] == " " * 12 + "1ST  " + "\x01\x02A" + "  123450" + " " * 12
    # a 4-digit displayed score pads to the 6-wide field, so the line stays
    # 16 chars and its score still ends at the same column
    b = BOARDS[3]
    rows = run_one(1, 0, 0, b, 0)
    assert rows[11] == " " * 12 + "1ST  SRG   50000" + " " * 12
    assert rows[12] == rows[11]
    assert rows[13] == " " * 12 + "2ND  HEX    4000" + " " * 12
    assert rows[19] == " " * 12 + "5TH  VEC       0" + " " * 12


def test_page4_controls_block_lines_all_start_at_col_11():
    rows = run_one(4, 0, 0, bm.Board(), 0)
    # the five "|" lines are one block: every line starts at the column
    # that centres the longest, "B      JUMP, LEVEL" (18 chars) -> col 11.
    # Page 4's lines sit at rows 6 (CONTROLS), 8 (empty), then the block
    # at 10, 12, 14, 16, 18; each line's cap is the row below it.
    assert rows[6] == " " * 16 + "CONTROLS" + " " * 16
    assert rows[7] == rows[6]
    assert rows[8] == " " * 40
    assert rows[9] == " " * 40        # the empty line's cap
    assert rows[10] == " " * 11 + "STICK  MOVE" + " " * 18
    assert rows[11] == rows[10]
    assert rows[12] == " " * 11 + "A      FIRE" + " " * 18
    assert rows[13] == rows[12]
    assert rows[14] == " " * 11 + "B      JUMP, LEVEL" + " " * 11
    assert rows[15] == rows[14]
    assert rows[16] == " " * 11 + "C      NEXT PAGE" + " " * 13
    assert rows[17] == rows[16]
    assert rows[18] == " " * 11 + "START  PLAY" + " " * 18
    assert rows[19] == rows[18]
    assert rows[20] == " " * 40
    # "START  PLAY" (11 chars) would centre at col 14 on its own: the
    # block pushes it (and everything else) to 11.
    assert (40 - len("START  PLAY")) // 2 == 14


def test_page0_row28_never_written_and_rows_beyond_blank():
    b = bm.Board()
    for credits in range(3):
        for t in TS:
            rows = run_one(0, 2, t, b, credits)
            # row 28 is the MVS countdown's row (flow.c), never title_rows'
            assert rows[28] == " " * 40
            # the page 0 rows that are not the logo (2..5), level (7) and
            # its cap (8), best (9) and its cap (10), prompt (21) and its cap (22), or
            # version (24) and its cap (25) stay blank
            for r in ([0, 1, 6] + list(range(11, 21)) + [23, 26,
                                                        27, 28, 29]):
                assert rows[r] == " " * 40, (r, rows[r])
            # the level/best caps repeat their lines
            assert rows[8] == rows[7]
            assert rows[10] == rows[9]
            assert rows[22] == rows[21]
            assert rows[25] == rows[24]


def test_fix_layer_ownership_title_hud_and_countdown_do_not_overlap():
    """Attract Task A2 proof 3: the fix layer has three owners, and no title
    cell can overwrite either of the other two.

    The title's own cells are the C's actual rows (title_sim), for every page
    and the visible inputs, not a hand-kept table: rows 2..25 only, including
    the logo (2..5), the level/best (7..10), the prompt (21) and every cap
    row. The HUD's cells are hud_model's fresh game rows (row 26's integrity and
    row 28's score/lives). The MVS countdown owns row 28 cols 19..20. On a
    fresh game the countdown overwrites the score's "0" at col 19, which is
    why flow.c commits the countdown after the HUD/title rows; the title
    itself must never reach any of those cells.
    """
    b = bm.Board()
    cases = [(p, l, t, b, c)
             for p in range(tm.PAGES)
             for l in range(3)
             for t in TS
             for c in range(3)]
    lines = run_many(cases)

    top_row = lay.d.title("TITLE_TOP_ROW")
    bottom_row = lay.d.title("TITLE_BOTTOM_ROW")
    cd_row = lay.d.title("TITLE_COUNTDOWN_ROW")
    cd_col = lay.d.title("TITLE_COUNTDOWN_COL")

    title_cells = set()
    for k in range(len(cases)):
        rows = lines[k * tm.ROWS:(k + 1) * tm.ROWS]
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch != " ":
                    title_cells.add((r, c))
    assert title_cells, "the title's cells are empty?"
    assert min(r for r, _c in title_cells) >= top_row, "a title cell is above its span"
    assert max(r for r, _c in title_cells) <= bottom_row, \
        f"a title cell is below row {bottom_row}: {sorted(title_cells)[-1]}"

    # the HUD's own cells at a fresh game (the title scene's HUD state)
    hud_rows = hm.hud_rows(rm.Rules(1), mm.Missiles())
    hud_cells = set((r, c) for r, row in enumerate(hud_rows)
                    for c, ch in enumerate(row) if ch != " ")
    assert hud_cells, "the fresh HUD has no cells?"
    assert {r for r, _c in hud_cells} <= {hm.HUD_INTEG_ROW, hm.HUD_LIVES_ROW, hm.HUD_GAMEOVER_ROW}, \
        "the HUD's cells escaped its rows"

    countdown_cells = {(cd_row, cd_col), (cd_row, cd_col + 1)}
    assert countdown_cells <= {(28, 19), (28, 20)}
    assert (28, 19) in hud_cells, "the fresh score's 0 is not at row 28 col 19"

    overlap_hud = title_cells & hud_cells
    overlap_cd = title_cells & countdown_cells
    assert not overlap_hud, \
        f"title cells overlap the HUD's: {sorted(overlap_hud)}"
    assert not overlap_cd, \
        f"title cells overlap the MVS countdown's: {sorted(overlap_cd)}"
    print(f"fix ownership: {len(title_cells)} title cells in rows "
          f"{top_row}..{bottom_row}; {len(hud_cells)} HUD cells on "
          f"rows {sorted(set(r for r, _c in hud_cells))}; "
          f"{len(countdown_cells)} countdown cells at row {cd_row} "
          f"cols {cd_col}..{cd_col + 1}; no overlaps")


# ---- proof 2: the built S ROM's title glyphs, caps and HUD tiles ----

def decode_srom_tile(data):
    """one 32-byte S ROM tile -> its 64 pixel colour indices, row-major."""
    px = [0] * 64
    i = 0
    for xa, xb in ((4, 5), (6, 7), (0, 1), (2, 3)):
        for y in range(8):
            b = data[i]
            i += 1
            px[y * 8 + xa] = b & 0x0f
            px[y * 8 + xb] = (b >> 4) & 0x0f
    return px


def expected_title_glyph(glyph):
    """the outlined title glyph tile, computed independently of the
    generator: the FONT57 glyph at cols 1..5, rows 1..7, its 1..4 gradient
    fill, colour 5 exactly on the 8-neighbourhood outline inside the tile."""
    px = [0] * 64
    for r in range(7):
        for c in range(5):
            if glyph[r][c] == '#':
                px[(r + 1) * 8 + c + 1] = gs.ROW_COLOUR[r]
    for r in range(7):
        for c in range(5):
            if glyph[r][c] != '#':
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    gy, gx = r + 1 + dy, c + 1 + dx
                    if gy < 0 or gy > 7 or gx < 0 or gx > 7:
                        continue
                    is_glyph = (1 <= gy <= 7 and 1 <= gx <= 5
                                and glyph[gy - 1][gx - 1] == '#')
                    if not is_glyph:
                        px[gy * 8 + gx] = gs.SHADOW
    return px


def expected_title_cap(glyph):
    """the cap tile: row 0 holds the outline's bottom row (the glyph's
    bottom row's 8-neighbourhood one row down); rows 1..7 are blank."""
    px = [0] * 64
    for c in range(5):
        if glyph[6][c] == '#':
            for dx in (-1, 0, 1):
                gx = c + 1 + dx
                if 0 <= gx <= 7:
                    px[gx] = gs.SHADOW
    return px


def test_title_glyph_tiles_are_outlined_and_caps_match():
    data = open(SROM, "rb").read()
    # high-score boards Task B4: the thick-outline font grows the S ROM to
    # 128 KB; the old 1-px-outline blocks (checked here) stay byte-identical.
    assert len(data) == 131072, f"S ROM is {len(data)} bytes, want 131072"
    font_base = lay.d.title("TITLE_FONT_BASE")
    cap_base = lay.d.title("TITLE_CAP_BASE")
    assert font_base + 95 < cap_base, "the title font and cap blocks may not overlap"
    assert cap_base + 95 < 512, "the title cap block must fit the 512-tile S ROM"
    checked = 0
    for ch, glyph in gs.FONT57.items():
        code = ord(ch)
        ftile = font_base + code
        ctile = cap_base + code
        fpx = decode_srom_tile(data[ftile * 32:(ftile + 1) * 32])
        cpx = decode_srom_tile(data[ctile * 32:(ctile + 1) * 32])
        assert fpx == expected_title_glyph(glyph), \
            f"title glyph tile {ftile} ({ch!r}) is not the outlined FONT57 glyph"
        assert cpx == expected_title_cap(glyph), \
            f"title cap tile {ctile} ({ch!r}) is not the glyph's bottom outline row"
        checked += 1
    assert checked == len(gs.FONT57)


def test_hud_glyph_and_icon_tiles_are_byte_identical_to_before():
    data = open(SROM, "rb").read()
    got = hashlib.sha256(data[:130 * 32]).hexdigest()
    assert got == HUD_TILES_SHA256, \
        "the in-play HUD's glyph/icon tiles (tiles 0..129) changed"


# ---- the title palette (PAL_HUD 7) and the in-play one (PAL_HUD_PLAY 11) ----

def _fix_pal_words(name):
    txt = open(FIX_PAL).read()
    m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name, txt, re.S)
    assert m, f"{name} not found in fix_pal.h"
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]


def test_title_palette_is_gold_with_a_black_outline():
    title = _fix_pal_words("fix_pal")
    hud = _fix_pal_words("fix_pal_amber")
    amber = [(255, 222, 150), (255, 190, 92), (255, 156, 44), (232, 116, 20)]
    gold = [(255, 226, 140), (255, 190, 80), (240, 150, 40), (200, 104, 16)]
    assert title[1:5] == [gs.neo_colour(c) for c in amber], \
        "the title's fill is not the HUD amber gradient"
    assert title[5] == 0x0000, "the title's outline colour 5 is not black"
    assert title[6:10] == [gs.neo_colour(c) for c in gold], \
        "the logo's gold gradient is not the plan's four colours"
    # the in-play HUD keeps today's palette: 1..5 the amber and shadow,
    # 6..9 the old logo blues
    assert hud[1:6] == [0x6fd9, 0x7fb5, 0x7f92, 0x4e71, 0x2410]
    assert hud[6:10] == [0x05be, 0x339c, 0x127a, 0x1158]
    assert title[1:5] == hud[1:5]        # the title uses the HUD's amber fill
