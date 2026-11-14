"""The HUD's text as a pure function of the rules' state — what the C's
src/hud.c must show (src/hud.h: hud_rows). Written from the HUD-layout Task
2 plan, the dome-scenery Task 8 move (the HUD down onto the console's one
bottom line) and the Vectrex (e-srg.c integrity_update: integrity 100% less
one 38th per broken cell, lives, the score with its trailing 0), as the
reference for tests/test_hud_model.py and the boot test's decoder.

Frame order is exactly tests/test_rules_play.py's (the C's rules_begin /
ship_frame / mis_update / rules_end), reused through frame_model.

The 30 rows cover fix rows 0..29 (40 chars each). The screen is arranged
like the Vectrex's: the score and the lives share the bottom row 28, the
integrity (a little dome icon, then the percent) sits one row above them
(row 26), GAME OVER centred on row 7, and nothing else during play:

  row 26:  "  <dome> 100%"   ICON_DOME at col 32 (the icons are S ROM
                             tiles past the ASCII range, colour index 1:
                             the C writes the tile number, the model uses
                             the same), the value right-aligned so its
                             last digit is at col 36, '%' at col 37
                             ("100%" fills cols 34..37, "5%" cols 36..37)
  row 28:  "  <ship><ship><ship>"   one ICON_SHIP per life at cols 32, 34
                             and 36 (life 1 at col 32), a space for each
                             lost one (lives never exceed 3)
              and the score, centred in cols 15..24: col = (40 - len) / 2,
                             rounded down, the title's rule; score10 x 10
                             (the Vectrex shows the score with its trailing
                             0, except 0). The score's band and the lives'
                             cells do not overlap.
  row 7:   "GAME OVER" centred while game_over, in the thick title font
                             (Task G1); row 8 is its cap row (the same
                             characters, the glyphs' bottom outline row).
                             A fresh game (game_over 1 -> 0) blanks both.
                             Everything else is spaces.

The row and column numbers come from src/hud.h through tests/layout.py — the
header is the one definition, so the model cannot drift from the C.
"""
import mis_model as mm
import rules_model as rm
import ship_model as sm

import layout as _lay

# the icons (tools/generate_srom.py): S ROM tiles past the ASCII range
ICON_SHIP = 128
ICON_DOME = 129

# the layout (src/hud.h, read through tests/layout.py): the model uses the
# same 0-based fix rows
HUD_GAMEOVER_ROW = _lay.d.hud("HUD_GAMEOVER_ROW")
HUD_GAMEOVER_CAP_ROW = _lay.d.hud("HUD_GAMEOVER_CAP_ROW")
HUD_GAMEOVER_COL0 = _lay.d.hud("HUD_GAMEOVER_COL0")
HUD_GAMEOVER_LEN = _lay.d.hud("HUD_GAMEOVER_LEN")
HUD_INTEG_ROW = _lay.d.hud("HUD_INTEG_ROW")
HUD_LIVES_ROW = _lay.d.hud("HUD_LIVES_ROW")
HUD_SCORE_ROW = _lay.d.hud("HUD_SCORE_ROW")
HUD_INTEG_ICON_COL = _lay.d.hud("HUD_INTEG_ICON_COL")
HUD_INTEG_END = _lay.d.hud("HUD_INTEG_END")   # the integrity value's last digit
HUD_PCT_COL = _lay.d.hud("HUD_PCT_COL")
HUD_LIVES_COL = _lay.d.hud("HUD_LIVES_COL")
HUD_LIVES_STEP = _lay.d.hud("HUD_LIVES_STEP")
DUMP_ROWS = _lay.d.hud("HUD_DUMP_ROWS")       # fix rows 0..29, what the boot test checks

GAME_OVER_TEXT = "GAME OVER"


def frame_model(state, inp, pressed):
    """one frame exactly as test_rules_play.py's frame_model (which the C's
    rules_sim mirrors)."""
    ship, mis, rules = state
    busy = rules.begin(ship, mis, pressed)
    if not busy:
        ship.frame(inp, pressed)
    if not busy:
        if pressed & rm.A:
            mis.fire_req = 1
        if mis.fire_req and not ship.left:
            mis.fire(ship.cell)
            mis.fire_req = 0
    mis.hits, mis.lands = [], []
    for o in mis.obj:
        if o.state != 1:
            continue
        if o.kind:
            o.r += o.dr
            o.life -= 1
            if o.life == 0:
                o.state = 0
        else:
            o.r -= o.dr
            if o.r <= mm.LAND:
                o.state = 2
    for b in mis.obj[mm.NMIS:]:
        if b.state != 1:
            continue
        for o in mis.obj[:mm.NMIS]:
            if o.state == 1 and o.phi == b.phi and o.ring == b.ring and b.r >= o.r:
                mis.hits.append(1)
                mis.kills = min(255, mis.kills + 1)
                mis.score = min(9999999, mis.score + rules.integ)
                o.state = b.state = 0
                break
    live = 0
    for o in mis.obj[:mm.NMIS]:
        if o.state == 2:
            c = mm.RING_END[o.ring - 1] if o.ring else 0
            while mm.CELL_PHI[c] != o.phi:
                c += 1
            mis.lands.append(c)
            if c not in ship.broken:     # a landing that broke a whole cell
                mis.dome_hits = min(255, mis.dome_hits + 1)  # counts as a hit
            rules.break_cell(ship, c)
            o.state = 0
        if o.state:
            live += 1
    if not (rules.dead_t or rules.game_over):
        if mis.timer:
            mis.timer -= 1
        elif live >= mm.V["wave_live"]:
            pass
        else:
            o = next(o for o in mis.obj if not o.state)
            mis.spawn(o, ship.broken)
            mis.timer = ((mm.V["spawn_gap"] + (mis.rand8() & 63)) * 59 + 25) // 50
    rules.end(ship, mis)
    mis.integ = rules.integ


def _put(row, s, col):
    for i, ch in enumerate(s):
        if 0 <= col + i < 40:
            row[col + i] = ch


def _right(row, s, end):
    """right-align s so its last char is at column end."""
    _put(row, s, end - (len(s) - 1))


def hud_rows(rules, mis):
    rows = [[" "] * 40 for _ in range(DUMP_ROWS)]
    # row 26: the integrity — ICON_DOME at col 32, the value right-aligned
    # to end at col 36, '%' at 37
    rows[HUD_INTEG_ROW][HUD_INTEG_ICON_COL] = chr(ICON_DOME)
    _right(rows[HUD_INTEG_ROW], str(rules.integ), HUD_INTEG_END)
    rows[HUD_INTEG_ROW][HUD_PCT_COL] = "%"
    # row 28: the lives — one ICON_SHIP per life at cols 32/34/36
    for i in range(3):
        rows[HUD_LIVES_ROW][HUD_LIVES_COL + i * HUD_LIVES_STEP] = \
            chr(ICON_SHIP) if i < rules.lives else " "
    # row 28: the score, centred — col = (40 - len) // 2, rounded down
    score = str(mis.score * 10)
    _put(rows[HUD_SCORE_ROW], score, (40 - len(score)) // 2)
    if rules.game_over:
        _put(rows[HUD_GAMEOVER_ROW], GAME_OVER_TEXT, HUD_GAMEOVER_COL0)
        # Task G1: the thick font's cap row repeats the text row's characters
        # (title_model's cap rows do the same); the span's last cell is the
        # space after the text and draws the last glyph's outline spill.
        rows[HUD_GAMEOVER_CAP_ROW] = list(rows[HUD_GAMEOVER_ROW])
    return ["".join(r) for r in rows]
