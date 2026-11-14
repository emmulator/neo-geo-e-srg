"""The star field's pure logic against the reference model (M5 Task 2).

  test_stars.py   (host, pytest)

The C module src/stars.c (built for the host as build/stars_sim) must match
tests/stars_model.py — the task's formulas applied to the Vectrex stars.s
table — EXACTLY, on integers:

  - the 12 mapped rest positions (x0, y): every star, and the y band
    8..68 (just above the dome box's top 72 — the band's bottom is
    DOME_Y - 4, read from src/dome.h — by construction);
  - the per-frame position for every star and EVERY dome_angle 0..239:
    x = (x0 - round(da * 320 / 240)) mod 320, y = y0;
  - the heading rule: as dome_angle grows, the stars move left (each step
    moves 1 or 2 px — the drift round(da*4/3), which lands on both — never
    right and never more than 2);
  - one whole dome turn scrolls one screen width: the 240 per-step moves
    sum to 320 px (the task's "one turn is one screen width"), so a star
    covers every screen x exactly once per turn, and da 239 -> 0 wraps
    seamlessly (a star at da 240 is back at its da 0 rest position);
  - the round() ties: x0 for stars 4 and 8 (x_v 42 and -6) is the
    round-half-up 213 / 153, not banker's 212 / 152 (stated in
    tests/stars_model.py; the C uses the same rule).

The C is exercised through build/stars_sim, a tiny driver that prints
stars_pos(i, da) for all i and da on stdin-requested rows (see
tests/stars_sim.c).
"""
import os
import re
import subprocess
import sys

import numpy as np

import stars_model as stm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "stars_sim")
ROM = os.path.join(ROOT, "build", "rom")
STARS_MAP = os.path.join(ROOT, "build", "stars_map.h")
C1 = os.path.join(ROM, "esrg-c1.c1")
C2 = os.path.join(ROM, "esrg-c2.c2")


def _decode_tile(c1, c2, tile):
    """the tile's 16x16 index array from the two plane files (tiletool's
    decode_crom_tile layout; the same decoder tests/test_broken_rom.py
    uses)."""
    p1 = c1[tile * 64:(tile + 1) * 64]
    p2 = c2[tile * 64:(tile + 1) * 64]
    out = np.zeros((16, 16), np.uint8)
    for i, off in enumerate((8, 136, 0, 128)):
        sy, sx = off // 16, off % 16
        for y in range(8):
            b0 = p1[2 * (8 * i + y)]
            b1 = p1[2 * (8 * i + y) + 1]
            b2 = p2[2 * (8 * i + y)]
            b3 = p2[2 * (8 * i + y) + 1]
            for x in range(8):
                px = (b0 >> x & 1) | ((b1 >> x & 1) << 1) | \
                     ((b2 >> x & 1) << 2) | ((b3 >> x & 1) << 3)
                out[sy + y][sx + x] = px
    return out


def _stars_map_defs():
    txt = open(STARS_MAP).read()
    return {m.group(1): int(m.group(2))
            for m in re.finditer(r"#define\s+(\w+)\s+(\d+)", txt)}


def c_all_positions():
    """{i: {da: (x, y)}} from build/stars_sim (the compiled src/stars.c)."""
    if not os.path.exists(SIM):
        raise SystemExit(f"{SIM} missing — run make first")
    out = subprocess.run([SIM, "all"], capture_output=True, text=True, check=True).stdout
    table = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) == 4:
            table.setdefault(int(p[0]), {})[int(p[1])] = (int(p[2]), int(p[3]))
    if len(table) != stm.NSTARS:
        raise AssertionError(f"stars_sim printed {len(table)} stars, want {stm.NSTARS}")
    if any(len(v) != 240 for v in table.values()):
        raise AssertionError("stars_sim must print all 240 dome_angle steps")
    return table


def test_every_star_every_angle_matches_the_model():
    want = {i: {da: stm.pos(i, da) for da in range(240)} for i in range(stm.NSTARS)}
    assert c_all_positions() == want


def test_rest_positions_are_the_vectrex_table_mapped():
    # the 12 (x0, y) rest positions, exact (y from the band's bottom,
    # DOME_Y - 4 = stm.BAND_BOTTOM, read from src/dome.h)
    assert stm.all_pos() == [(196, stm.BAND_BOTTOM - 21), (98, stm.BAND_BOTTOM - 19),
                             (146, stm.BAND_BOTTOM - 60), (309, stm.BAND_BOTTOM - 34),
                             (213, stm.BAND_BOTTOM - 3), (59, stm.BAND_BOTTOM - 50),
                             (118, stm.BAND_BOTTOM - 11), (249, stm.BAND_BOTTOM - 3),
                             (153, stm.BAND_BOTTOM - 47), (5, stm.BAND_BOTTOM - 30),
                             (195, stm.BAND_BOTTOM - 46), (95, stm.BAND_BOTTOM - 38)]
    # the band the task promises: every star below the dome box's top
    # (DOME_Y - 4 = the band's bottom by construction; at today's DOME_Y 72
    # this is the 8..68 band), and none inside the dome box
    ys = [y for x, y in stm.all_pos()]
    assert min(ys) == stm.BAND_BOTTOM - 60 and max(ys) == stm.BAND_BOTTOM - 3
    assert all(stm.BAND_BOTTOM - 60 <= y <= stm.BAND_BOTTOM for y in ys)
    assert all(stm.y(i) < stm.DOME_Y for i in range(stm.NSTARS))  # no star in the box
    assert all(0 <= x <= 319 for x, _ in stm.all_pos())


def test_y_band_is_dome_y_minus_4():
    # the band's bottom is the header's DOME_Y - 4: the stars sit just
    # above the dome box, and lifting the dome lifts them (the task's
    # "band's bottom is DOME_Y - 4 (68)"). The asserts follow the header
    # (the HUD-layout plan's mutation rule: with DOME_Y at 88 the same
    # checks pass, because the band follows the header). At today's DOME_Y
    # 72 the band is exactly y 8..68 and the box is y 72..199, so the
    # committed build also proves the task's concrete numbers.
    assert stm.BAND_BOTTOM == stm.DOME_Y - 4
    assert min(stm.y(i) for i in range(stm.NSTARS)) == stm.BAND_BOTTOM - 60   # the topmost star
    assert max(stm.y(i) for i in range(stm.NSTARS)) == stm.BAND_BOTTOM - 3    # the lowest
    assert all(stm.y(i) < stm.DOME_Y for i in range(stm.NSTARS))              # none in the box
    if stm.DOME_Y == 72:                 # the committed build: the task's own numbers
        assert all(8 <= stm.y(i) <= 68 for i in range(stm.NSTARS)), \
            [stm.y(i) for i in range(stm.NSTARS)]
        assert all(not (72 <= stm.y(i) <= 199) for i in range(stm.NSTARS))


def test_round_half_up_ties():
    # x_v 42 -> (170)*5/4 = 212.5 and x_v -6 -> (122)*5/4 = 152.5: the two
    # exact half ties in the table. Half-up rounds both up (213, 153); the
    # C (round()) and the model agree on this — a banker's rounding would
    # give 212/152 and fail this test and the C comparison.
    assert stm.x0(4) == 213
    assert stm.x0(8) == 153
    assert stm.X_TIES[4] == (212.5, 213)
    assert stm.X_TIES[8] == (152.5, 153)


def test_stars_move_left_as_dome_angle_grows():
    # the Vectrex relationship (plan: stars move left as dome_angle grows).
    # The drift round(da*4/3) steps 1 or 2 px per step (the 4/3 slope), so
    # each consecutive step moves a star 1..2 px left (mod 320 — the 2-px
    # steps are where round(4k/3) rounds up), never right and never more.
    for i in range(stm.NSTARS):
        for da in range(240):
            x, _ = stm.pos(i, da)
            xn, _ = stm.pos(i, (da + 1) % 240)
            d = (x - xn) % 320
            assert d in (1, 2), (i, da, x, xn, d)


def test_whole_turn_is_one_screen_width():
    # one dome turn (240 steps) scrolls the stars one whole screen width:
    # the 240 per-step moves sum to 320 px (the task's "one turn is one
    # screen width, leftward"), and a star returns to its rest x after a
    # full turn (dome_angle 240 == 0: the 239->0 wrap is seamless).
    for i in range(stm.NSTARS):
        dist = 0
        for da in range(240):
            x, _ = stm.pos(i, da)
            xn, _ = stm.pos(i, (da + 1) % 240)
            dist += (x - xn) % 320
        assert dist == 320, (i, dist)
        assert stm.pos(i, 240) == stm.pos(i, 0)


def test_star_tile_is_a_top_left_2x2_dot_in_the_built_rom():
    """the look: one 1-tile sprite, a 2x2 px dot at the tile's top-left
    (so the sprite's X and Y are the dot's). Decode the tile the
    cartridge actually holds at STAR_TILE_BASE and check exactly the 2x2
    top-left block is colour 1, everything else 0."""
    defs = _stars_map_defs()
    base = defs["STAR_TILE_BASE"]
    c1 = open(C1, "rb").read()
    c2 = open(C2, "rb").read()
    t = _decode_tile(c1, c2, base)
    ones = np.argwhere(t == 1)
    assert ones.tolist() == [[0, 0], [0, 1], [1, 0], [1, 1]], ones.tolist()
    assert (t == 0).all() or (t <= 1).all()
    assert (t[2:, :] == 0).all() and (t[:, 2:] == 0).all()


def test_star_tile_number_follows_the_broken_sheet():
    """STAR_TILE_BASE is one tile after render_broken's sheet end (the
    Makefile concatenates the parts back to back): the header's value
    equals TILE_BASE + N_TILES, and the built ROM's tile at that number
    is the star's (the previous tile is the broken sheet's last, and the
    file's size covers it)."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import render_broken as rb  # noqa: E402

    defs = _stars_map_defs()
    assert defs["STAR_TILE_BASE"] == rb.TILE_BASE + rb.N_TILES
    c1 = open(C1, "rb").read()
    assert len(c1) > (defs["STAR_TILE_BASE"] + 1) * 64
