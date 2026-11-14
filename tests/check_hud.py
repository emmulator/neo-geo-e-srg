"""Assertions for the M4 Task 3 HUD boot-test (HUD-layout Task 2).

  check_hud.py SNAP PROBE [EVENTS_ADDR [FRAMECNT_ADDR]]
    SNAP        the MAME snapshot (taken by scripts/hud_probe.lua)
    PROBE       the probe dump:
                  I <rec> <fc> <bios_p1current> <bios_p1change>   every record
                  F <fc>                                          a read follows
                  E <fc> <hud_dbg_events>                         (if addr known)
                  R <r> <40 chars>                                fix row
                  V <fc> <lives>          the rules' lives at a snapshot frame
                  SNAP <fc>
    EVENTS_ADDR 0 disables the event check. FRAMECNT_ADDR 0 disables the
    exact-frame alignment (then the probe's I records carry the record
    number as fc too).

scripts/hud_probe.lua drives the normal cart through a deterministic game by
setting the joypad ioports (the BIOS fills bios_p1current/bios_p1change from
them) and records both bytes once per record, in order, together with the
cart's frame counter (hud_framecnt). The cart's rules (src/rules.c, held to
the model by tests/test_rules_play.py) saw exactly the inputs this checker
replays into tests/hud_model.py's model, one record per model frame. The
BIOS preamble (about 470 MAME frames) and the cart's startup hold
hud_framecnt at 0 for the first records, so the model replay does not start
until the record where fc first reaches 1; after that fc counts 1, 2, ...
per record. On every sampled cart frame the decoded FIXMAP rows must equal
the model's hud_rows — the task's checks are then all visible:

  * the starting values (integ 100, lives 3, score 0),
  * after a crack (integ < 100),
  * after a death (lives < 3),
  * at GAME OVER (centred text on row 7),
  * after A starts a new game (GAME OVER gone, lives 3, integ 100 again),

and with EVENTS_ADDR the probe's hud_dbg_events (the cart's line-commit
count) must equal the number of commits the model's values imply over the
same frames — the HUD really did redraw only when a value changed.

The HUD-layout Task 2 proofs on top of the row match:

  * the rows cover fix rows 0..29, and rows 2..25 (except row 7's GAME
    OVER) hold only spaces during play — the top of the screen is empty
    (dome-scenery Task 8: the HUD moved down, so the integrity is on row
    26 and the lives and the score share row 28);
  * proof 2 (the icons): the fc-100 snapshot (before the first death, lives
    3) shows exactly 18 lit pixels in each of the 3 ship-icon cells (8 x 8
    at the HUD's lives cols 32/34/36 -> x 256/272/288, y 208 on row 28);
    the snapshot at the first death (the probe's V record reads
    rules.lives == 2) shows 2 cells with 18 and the third with 0;
  * proof 3 (the top of the screen during play): no lit fix pixel in
    y 0..71 outside rows 7/8 (y 40..55, where GAME OVER's thick text and
    its cap row may be drawn).

The dome-scenery Task 9 proofs (the HUD in amber; the second fix palette):

  * proof 2: on every sampled PLAY frame, every non-space FIXMAP cell of
    rows 26, 28 carries the PAL_HUD_PLAY nibble 11 and Task G1's GAME OVER
    cells on rows 7/8 carry the PAL_HUD nibble 7 (the P records), and
    palette RAM bank 11 equals fix_pal_amber while bank 7 equals fix_pal
    (the B records). The count of cells checked and the mismatches (0) are
    stated.
  * proof 3: on every sampled TITLE frame (fc 0, row 3 == the logo row),
    every non-space FIXMAP cell of the title's own rows (0..25) carries the
    PAL_HUD nibble 7 (the TP/TR records). Attract Task A2 draws the fresh
    game's HUD on rows 26/28 in the play palette (PAL_HUD_PLAY 11), so those
    rows are not title text and are excluded here (their content is checked
    against the fresh HUD by check_flow); the count is stated.
  * proof 4: in the fc-100 play snapshot, the integrity's and the lives'
    lit pixels are fix_pal_amber's colours as MAME shows them (neo_rgb),
    and none is one of fix_pal's 1..5; the counts per cell are stated.

Mutations (each failing one proof, then reverted; the FAIL lines are in
the commit message): (a) the score written with PAL_HUD -> proof 2;
(b) bank 11 loaded with fix_pal -> proof 4; (c) the title's prompt written
with PAL_HUD_PLAY -> proof 3.

One detail: the probe records the joypad RAM read-back at the end of a MAME
frame; the cart's main loop read it at some point inside that same frame.
The replay therefore starts at the record where fc first reaches 1 (the
cart's first main-loop frame) and consumes records one per model frame
(PHASE = 0: the recorded read-back for a frame is the input that frame
saw). If a future BIOS revision shifts the joypad polling by a frame, only
PHASE needs to change; the row comparison below checks it empirically.
"""
import os
import re
import sys

from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import hud_model as hm  # noqa: E402
import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import neo_palette as npal  # noqa: E402  (the play backdrop: the sky)
import rules_model as rm  # noqa: E402
import ship_model as sm  # noqa: E402
import check_flow as cf  # noqa: E402  (the thick title font's row decoder)

ROW_COUNT = 30
PHASE = 0                    # records the model frame lags the cart frame by

# the icon cells (HUD-layout Task 2; dome-scenery Task 8 moved the lives
# onto fix row 28): the fixes' cols/row come from src/hud.h (tests/layout
# .py), never as new copies — fix cols 32/34/36 -> x 8*c = 256/272/288,
# row 28 -> y 8*28 - 16 = 208; each 8 x 8 cell holds the ICON_SHIP tile
# (18 lit pixels) while a life is left, 0 after.
import layout as lay  # noqa: E402
LIVES_ROW = lay.d.hud("HUD_LIVES_ROW")
LIVES_COL = lay.d.hud("HUD_LIVES_COL")
LIVES_STEP = lay.d.hud("HUD_LIVES_STEP")
LIVES_Y = 8 * LIVES_ROW - 16
LIVES_XS = tuple(8 * (LIVES_COL + i * LIVES_STEP) for i in range(3))
ICON_LIT = 18                # the tile's lit pixel count (generate_srom.py)

# the fix palette banks (src/hud.h; Task 9): the title's blue is PAL_HUD 7,
# the in-play HUD's amber is PAL_HUD_PLAY 11.
PAL_HUD = 7
PAL_HUD_PLAY = 11

# the "top of the screen" during play: fix rows 2..25 (row 2 is the first
# visible row: fix row r is at y 8r - 16) hold only spaces, row 7 (GAME
# OVER) is y 40..47. The task's band is y 0..71 outside row 7's y 40..47.
TOP_BAND = (0, 71)
GO_BAND = (40, 47)
TOP_BLANK_ROWS = list(range(2, 7)) + list(range(9, lay.d.hud("HUD_INTEG_ROW")))


def decode_row(raw):
    """a probe R line's 40 chars -> the row as the model builds it: the
    probe writes every tile >= 0x80 as a <NN> escape, the HUD icons as their
    raw 128/129 and Task G1's GAME OVER thick-font tiles as the title font's
    base + title2_idx * NPROF + title2_rprof[left] (check_flow's decoder
    recovers the characters from the shared build/title_font.h tables)."""
    return cf._decode_row(raw)


def parse(fname):
    """(records, samples, events, veg, snaps, seeds, pal) — records:
    [(rec, fc, cur, chg)] in order; samples: {fc: rows} (30 strings);
    events: {fc: count}; veg: {fc: lives} (the snapshot-frame V records);
    snaps: the snapshot frames in order; seeds: {mame frame: seed} (the
    cart's mis_seed_used, Task 1). pal: {"play": {fc: {row: [(col, nibble),
    ...]}}, "title": [(fc, {row: [(col, nibble), ...]})], "banks": {fc:
    {7: [16 words], 11: [16 words]}}} — Task 9's palette records."""
    records, samples, events, veg, seeds = [], {}, {}, {}, {}
    snaps = []
    pal = {"play": {}, "title": [], "banks": {}}
    cur_f, cur_rows = None, None
    with open(fname, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] in ("I", b"I"):
                rec, fc, cur, chg = (int(x) for x in p[1:5])
                records.append((rec, fc, cur, chg))
            elif p[0] == "F":
                cur_f = int(p[1])
                cur_rows = [None] * ROW_COUNT
            elif p[0] == "E":
                events[int(p[1])] = int(p[2])
            elif p[0] == "R":
                if cur_rows is not None:
                    cur_rows[int(p[1])] = decode_row(line.split(" ", 2)[2].rstrip("\n"))
            elif p[0] == "P":
                # P <fc> <row> <c>:<nibble>,...
                fc, row = int(p[1]), int(p[2])
                cells = [tuple(int(x) for x in q.split(":")) for q in p[3].split(",")]
                pal["play"].setdefault(fc, {})[row] = cells
            elif p[0] == "B":
                # B <fc> <bank> <16 hex words, comma-separated>
                fc, bank = int(p[1]), int(p[2])
                pal["banks"].setdefault(fc, {})[bank] = [
                    int(x, 16) for x in p[3].split(",")]
            elif p[0] == "TP":
                pal["title"].append((int(p[1]), {}))
            elif p[0] == "TR":
                fc, row = int(p[1]), int(p[2])
                cells = [tuple(int(x) for x in q.split(":")) for q in p[3].split(",")]
                pal["title"][-1][1][row] = cells
            elif p[0] == "V":
                veg[int(p[1])] = int(p[2])
            elif p[0] == "SEED":
                seeds[int(p[1])] = int(p[2])
            elif p[0] == "SNAP":
                snaps.append(int(p[1]))
            if cur_f is not None and cur_rows is not None and all(r is not None for r in cur_rows):
                samples[cur_f] = cur_rows
                cur_f, cur_rows = None, None
    return records, samples, events, veg, snaps, seeds, pal


def commits(prev, rules, mis):
    """line-commits hud_frame makes when the state moves from prev to now."""
    v = (rules.integ, rules.lives, mis.score * 10, rules.game_over)
    if prev is None:
        return 4
    return sum(1 for a, b in zip(v, prev) if a != b)


def icon_counts(im):
    """(n0, n1, n2): the lit pixel counts in the three ship-icon cells."""
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    out = []
    for x in LIVES_XS:
        x0, x1 = int(x * sx), int((x + 8) * sx)
        y0, y1 = int(LIVES_Y * sy), int((LIVES_Y + 8) * sy)
        n = 0
        for py in range(y0, y1):
            for px in range(x0, x1):
                px_rgb = im.getpixel((px, py))
                # dome-scenery Task 5: the icons sit inside the ground's
                # band (y 192..199), so the static grass must not count.
                # Dome-scenery Task 7: the console's recess frame sits in
                # the same cells (y 172..203, x 250..309), so its static
                # picture must not count either (its own colours; the
                # grass's are subtracted separately, the two sets are
                # disjoint).
                if npal.is_lit(px_rgb, npal.SKY_RGB) \
                   and not npal.is_grass(px_rgb) and not npal.is_console(px_rgb):
                    n += 1
        out.append(n)
    return tuple(out)


def play_palette_cells(pal):
    """proof 2's cell count and mismatches: every P record's non-space cell
    on rows 26/28 must carry PAL_HUD_PLAY nibble 11; Task G1's GAME OVER
    cells on rows 7/8 carry PAL_HUD nibble 7 (the title/entry text's bank,
    so GAME OVER matches the entry that can follow it)."""
    n, bad = 0, []
    for fc in sorted(pal["play"]):
        for row, cells in sorted(pal["play"][fc].items()):
            want = PAL_HUD if row in (hm.HUD_GAMEOVER_ROW,
                                      hm.HUD_GAMEOVER_CAP_ROW) else PAL_HUD_PLAY
            for col, nib in cells:
                n += 1
                if nib != want:
                    bad.append((fc, row, col, nib, want))
    return n, bad


def palette_bank_mismatches(pal):
    """proof 2's bank check: on every B record, bank 11 == fix_pal_amber
    and bank 7 == fix_pal. Returns (checked pairs, [(fc, bank, word, got,
    want), ...])."""
    want = {PAL_HUD: npal.fix_pal_words(),
            PAL_HUD_PLAY: npal.fix_pal_amber_words()}
    n, bad = 0, []
    for fc in sorted(pal["banks"]):
        for bank, words in sorted(pal["banks"][fc].items()):
            if bank not in want:
                continue
            n += 1
            for i, got in enumerate(words):
                if got != want[bank][i]:
                    bad.append((fc, bank, i, got, want[bank][i]))
    return n, bad


def title_palette_cells(pal):
    """proof 3's cell count and mismatches: every non-space FIXMAP cell of
    the title's own rows on a title frame must carry the PAL_HUD nibble 7.
    Rows 26/28 are the fresh HUD's (attract A2) in PAL_HUD_PLAY 11."""
    n, bad = 0, []
    for fc, rows in pal["title"]:
        for row, cells in sorted(rows.items()):
            if row in (INTEG_ROW, LIVES_ROW):
                continue
            for col, nib in cells:
                n += 1
                if nib != PAL_HUD:
                    bad.append((fc, row, col, nib))
    return n, bad


# the integrity and lives cells (dome-scenery Task 8's row 26/28, src/hud.h
# via tests/layout.py): the integrity occupies cols 32..37 (ICON_DOME at 32,
# its right-aligned value ending at 36, '%' at 37); the lives' three ship
# icons are at cols 32/34/36. The proof scans whole 8x8 cells; only the lit
# pixels of the font/icon are counted, so blank pixels of those cells do
# not matter.
INTEG_ROW = lay.d.hud("HUD_INTEG_ROW")
INTEG_COLS = tuple(range(lay.d.hud("HUD_INTEG_ICON_COL"),
                         lay.d.hud("HUD_PCT_COL") + 1))


def cell_lit_pixels(im, row, col):
    """the RGBs of the lit pixels in one 8x8 fix cell (x 8c, y 8r-16), with
    the static scenery left out: returns (amber, blue, other) counts, where
    amber/blue are the sets fix_pal_amber/fix_pal show (neo_rgb)."""
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    x0, x1 = int(col * 8 * sx), int((col + 1) * 8 * sx)
    y0 = 8 * row - 16
    y0, y1 = int(y0 * sy), int((y0 + 8) * sy)
    amber = blue = other = 0
    for py in range(y0, y1):
        for px in range(x0, x1):
            rgb = tuple(im.getpixel((px, py))[:3])
            if rgb == npal.SKY_RGB or npal.is_grass(rgb) \
               or npal.is_console(rgb) or npal.is_mountain(rgb):
                continue                      # static scenery, not text
            if rgb in npal.hud_play_lit_rgb_set():
                amber += 1
            elif rgb in npal.title_lit_rgb_set():
                blue += 1
            else:
                other += 1
    return amber, blue, other


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    events_addr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    framecnt_addr = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0
    records, samples, events, veg, snaps, seeds, pal = parse(probe)
    seed = mis_seed.cart_seed(probe, seeds)   # Task 1: the cart's seed
    print(f"mis_seed_used: {seed:#06x}")
    failures = []

    if not records:
        failures.append("probe wrote no input records")
        return 1
    if not samples:
        failures.append("probe wrote no decoded rows")
        return 1

    # the model's frame 1 is the first record whose cart frame is 1 (the
    # first main-loop frame); records before it are the BIOS preamble and
    # the cart's startup, which saw none of the game. fc==0 repeats while
    # startup runs, so find the first 0 -> 1 edge.
    first = None
    for i, (rec, fc, cur, chg) in enumerate(records):
        if fc == 1:
            first = i
            break
    if first is None:
        # the framecnt address was 0: the probe wrote rec as fc, so the
        # game starts at record 1
        first = 0
    first_rec = records[first][0]

    # replay: model frame m consumes record (first + m - 1 + PHASE). Its
    # state after frame m is the rows the cart's fix layer showed at cart
    # frame m (the sample key). Events accumulate the same way.
    ship, mis, rules = sm.Ship(), mm.Missiles(seed=seed), rm.Rules(1)
    model_events = 0
    prev = None
    state_by_fc = {}                   # cart frame m -> (integ, lives, score, go)
    rows_by_fc = {}                    # cart frame m -> hud_rows (30 strings)
    events_by_fc = {}                  # cart frame m -> model commits through m
    n = len(records)
    m = 0
    i = first + PHASE
    while 0 <= i < n:
        rec, fc, cur, chg = records[i]
        hm.frame_model((ship, mis, rules), cur, chg)
        v = (rules.integ, rules.lives, mis.score * 10, rules.game_over)
        model_events += commits(prev, rules, mis)
        prev = v
        m += 1
        state_by_fc[m] = v
        rows_by_fc[m] = hm.hud_rows(rules, mis)
        events_by_fc[m] = model_events
        i += 1

    # compare the sampled rows with the model at the same cart frames
    for g in sorted(samples):
        if g not in rows_by_fc:
            continue
        if samples[g] != rows_by_fc[g]:
            for r in range(ROW_COUNT):
                if samples[g][r] != rows_by_fc[g][r]:
                    failures.append(
                        f"frame {g} row {r}:\n  cart  {samples[g][r]!r}"
                        f"\n  model {rows_by_fc[g][r]!r}")
        if events_addr and g in events_by_fc:
            if events[g] != events_by_fc[g]:
                failures.append(
                    f"frame {g}: cart redrew {events[g]} lines, the model implies "
                    f"{events_by_fc[g]} (the HUD must redraw only when a value changes)")

    # ---- HUD-layout Task 2 proof 3 (rows): nothing at the top of the
    # screen — rows 0..6 and 8..23 hold only spaces during play (row 7's
    # GAME OVER excepted). The whole-row equality above already proves the
    # cart drew exactly the model's rows, so checking the model's rows is
    # checking the cart's.
    top_bad = [g for g in sorted(samples) if g in rows_by_fc
               and any(rows_by_fc[g][r].strip() for r in TOP_BLANK_ROWS)]
    if top_bad:
        failures.append(f"the model's rows above the lower-right HUD are not "
                        f"blank on frames {top_bad[:5]} (rows 2..6, "
                        f"9..{lay.d.hud('HUD_INTEG_ROW') - 1}; 7/8 are GAME "
                        f"OVER's)")

    # ---- the task's checkpoints: the text is proven above (whole rows ==
    # the model), so the checkpoints are the moments the script drove the
    # game to, read from the model at the sampled frames ----
    seen_int100 = seen_crack = seen_lives3 = seen_death = False
    seen_go = seen_restart = seen_score0 = seen_score = False
    prev_go = 0
    for g in sorted(samples):
        if g not in state_by_fc:
            continue
        integ, lives, score, go = state_by_fc[g]
        if integ == 100:
            seen_int100 = True
        else:
            seen_crack = True
        if lives == 3:
            seen_lives3 = True
        else:
            seen_death = True
        if score == 0:
            seen_score0 = True
        else:
            seen_score = True
        if go and not prev_go:
            seen_go = True
        if not go and prev_go:
            seen_restart = True
        prev_go = go
    if not seen_int100:
        failures.append("no sampled frame showed the starting integrity 100%")
    if not seen_crack:
        failures.append("no sampled frame showed a crack (integrity below 100)")
    if not seen_lives3:
        failures.append("no sampled frame showed 3 lives")
    if not seen_death:
        failures.append("no sampled frame showed a death (fewer than 3 lives)")
    if not seen_go:
        failures.append("no sampled frame showed GAME OVER")
    if not seen_restart:
        failures.append("no sampled frame showed A starting a new game (GAME OVER gone)")
    if not seen_score0:
        failures.append("no sampled frame showed score 0 at the start")
    if not seen_score:
        failures.append("the score never grew (no kill) in the sampled frames")

    # ---- dome-scenery Task 8 proof 3: a frame where the score's length
    # changes (e.g. 0 -> a two-digit score) still shows every life's icon
    # on row 28, read from the CART's own decoded row (the whole-row
    # equality above proves it equals the model's). The score's length
    # differs from the previous sampled frame's, the lives are still 3 (so
    # all 3 icons must be there), and the score's digits sit in their
    # centred columns while cols 32/34/36 hold the 3 icons.
    len_change = None
    prev_g = None
    for g in sorted(samples):
        if g not in state_by_fc:
            continue
        score = state_by_fc[g][2]
        if prev_g is not None:
            pscore = state_by_fc[prev_g][2]
            if len(str(score)) != len(str(pscore)):
                len_change = (prev_g, g, pscore, score)
                break
        prev_g = g
    if len_change is None:
        failures.append("no sampled frame pair showed the score's length "
                        "changing (the shared-row proof needs one)")
    else:
        g0, g1, s0, s1 = len_change
        row = samples[g1][hm.HUD_SCORE_ROW]
        n = len(str(s1))
        start = (40 - n) // 2
        icons = tuple(row[hm.HUD_LIVES_COL + i * hm.HUD_LIVES_STEP]
                      for i in range(3))
        if state_by_fc[g1][1] != 3:
            failures.append(f"the score-length-change frame {g1} (score "
                            f"{s0} -> {s1}) does not show 3 lives in the model")
        elif icons != (chr(hm.ICON_SHIP),) * 3:
            failures.append(f"frame {g1} (score {s0} -> {s1}): the cart's "
                            f"row 28 shows {icons!r} at the lives' cols "
                            "32/34/36, want 3 ship icons — the score's write "
                            "touched them")
        elif samples[g1][hm.HUD_SCORE_ROW] != rows_by_fc[g1][hm.HUD_SCORE_ROW]:
            failures.append(f"frame {g1} (score {s0} -> {s1}): the cart's row "
                            f"28 {row!r} is not the model's "
                            f"{rows_by_fc[g1][hm.HUD_SCORE_ROW]!r}")
        else:
            digits = row[start:start + n]
            if digits != str(s1) or not (start + n - 1 <= lay.d.hud("HUD_SCORE_COL0") + lay.d.hud("HUD_SCORE_W") - 1):
                failures.append(f"frame {g1}: the score's digits {digits!r} "
                                f"are not {str(s1)!r} centred at col {start}")
            else:
                print(f"score length change {s0} -> {s1} at frame {g1}: "
                      f"the cart's row 28 shows {row!r} (3 ship icons at cols "
                      f"32/34/36, the score at cols {start}..{start + n - 1})")

    # ---- HUD-layout Task 2 proof 2: the icons on the snapshots ----
    if len(snaps) < 2:
        failures.append(f"the probe took {len(snaps)} snapshots, need 2 "
                        "(before the first death and after it)")
    else:
        im1 = Image.open(snaps_snap(snap_png, probe, 1)).convert("RGB")
        c1 = icon_counts(im1)
        # the first snapshot keys the model: it must be on a frame the
        # model shows lives 3 (before the first death — fc 100, the probe's
        # snap frame, is before the first landing ~fc 285)
        g1 = snaps[0]
        if g1 in state_by_fc and state_by_fc[g1][1] != 3:
            failures.append(f"snapshot 1 at fc {g1} shows lives "
                            f"{state_by_fc[g1][1]} in the model, want 3")
        if c1 != (ICON_LIT, ICON_LIT, ICON_LIT):
            failures.append(f"snapshot 1 (fc {g1}): icon cells have "
                            f"{c1} lit pixels, want {18, 18, 18} "
                            "(3 lives: 3 ships)")
        print(f"icons before the first death (fc {g1}): {c1} lit pixels "
              f"in the 3 cells, want (18, 18, 18)")
        # the second snapshot: the probe's V record reads rules.lives == 2
        # on that frame (the first death has happened) — the model must
        # agree, and 2 of the 3 cells must still be ships.
        if veg:
            vfc, vlives = sorted(veg.items())[0]
            st = state_by_fc.get(vfc)
            if vlives != 2:
                failures.append(f"the probe's V record at fc {vfc} reads "
                                f"lives {vlives}, want 2 (the first death)")
            elif st is not None and st[1] != 2:
                failures.append(f"the model at fc {vfc} shows lives {st[1]}, "
                                f"the probe's {vlives} (snapshot misaligned)")
            im2 = Image.open(snaps_snap(snap_png, probe, 2)).convert("RGB")
            c2 = icon_counts(im2)
            if c2 != (ICON_LIT, ICON_LIT, 0):
                failures.append(f"after the first death (fc {vfc}): icon "
                                f"cells have {c2} lit pixels, want "
                                f"(18, 18, 0) (2 lives left)")
            print(f"icons after the first death (fc {vfc}, lives {vlives}): "
                  f"{c2} lit pixels, want (18, 18, 0)")
        else:
            failures.append("the probe wrote no V record (no after-death "
                            "snapshot)")

    # ---- dome-scenery Task 9 proof 2: the in-play rows' palette nibble 11
    # and the two palette banks ----
    n_cells, pal_bad = play_palette_cells(pal)
    n_banks, bank_bad = palette_bank_mismatches(pal)
    if n_cells == 0:
        failures.append("no play-frame palette records (P lines) were "
                        "written")
    else:
        print(f"play palette: {n_cells} non-space cells on rows 26, 28 and "
              f"(when shown) 7/8 checked, {len(pal_bad)} mismatches (want 0)")
        if pal_bad:
            for fc, row, col, nib, want in pal_bad[:10]:
                failures.append(f"play frame {fc}: row {row} col {col} has "
                                f"palette nibble {nib}, want {want}")
    if n_banks == 0:
        failures.append("no palette-bank records (B lines) were written")
    else:
        print(f"palette banks: {n_banks} bank pairs checked (bank "
              f"{PAL_HUD_PLAY} vs fix_pal_amber, bank {PAL_HUD} vs "
              f"fix_pal), {len(bank_bad)} mismatches (want 0)")
        if bank_bad:
            for fc, bank, i, got, want in bank_bad[:10]:
                failures.append(f"palette bank {bank} at frame {fc} entry "
                                f"{i} is {got:#06x}, want {want:#06x}")

    # ---- dome-scenery Task 9 proof 3: every title cell is PAL_HUD 7 ----
    n_title, title_bad = title_palette_cells(pal)
    if n_title == 0:
        failures.append("no title-frame palette records (TP/TR lines) were "
                        "written")
    else:
        print(f"title palette: {n_title} non-space title cells on rows "
              f"0..25 checked over {len(pal['title'])} title frames, "
              f"{len(title_bad)} mismatches (want 0)")
        if title_bad:
            for fc, row, col, nib in title_bad[:10]:
                failures.append(f"title frame {fc}: row {row} col {col} has "
                                f"palette nibble {nib}, want {PAL_HUD}")

    # ---- dome-scenery Task 9 proof 4: the integrity's and the lives' lit
    # pixels are the amber bank's colours, none the blue's 1..5 ----
    if snaps:
        im = Image.open(snaps_snap(snap_png, probe, 1)).convert("RGB")
        amber_n = blue_n = other_n = 0
        for col in INTEG_COLS:
            a, b, o = cell_lit_pixels(im, INTEG_ROW, col)
            amber_n += a
            blue_n += b
            other_n += o
        for col in LIVES_XS:
            a, b, o = cell_lit_pixels(im, LIVES_ROW, col // 8)
            amber_n += a
            blue_n += b
            other_n += o
        print(f"pixels (fc {snaps[0]}): integrity's {len(INTEG_COLS)} cells "
              f"+ lives' 3 cells: {amber_n} amber (fix_pal_amber) pixels, "
              f"{blue_n} blue (fix_pal 1..5) pixels, {other_n} other lit")
        if amber_n == 0:
            failures.append("the integrity/lives cells have no amber pixels "
                            "at all (the play palette was not in the cells)")
        if blue_n != 0:
            failures.append(f"the integrity/lives cells show {blue_n} "
                            "fix_pal's 1..5 pixels, want 0 (the play text "
                            "must be amber)")

    if failures:
        print("FAIL hud:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    n_s = len([g for g in samples if g in state_by_fc])
    print(f"PASS hud: {n_s} sampled frames (rows 0..29) match the model, "
          f"score/icon rows part of the match, icons (18,18,18) -> "
          f"(18,18,0), top rows 2..6/9..{lay.d.hud('HUD_INTEG_ROW') - 1} "
          f"blank, checkpoints all seen; play palette {n_cells} cells all "
          f"as expected (26/28 nibble {PAL_HUD_PLAY}, 7/8 nibble {PAL_HUD}), "
          f"{n_banks} bank pairs match, title "
          f"{n_title} cells all nibble {PAL_HUD}, integrity/lives "
          f"{amber_n} amber pixels / {blue_n} blue"
          + (f", events={model_events}" if events_addr else ""))
    return 0


def snaps_snap(snap_png, probe, idx):
    """MAME writes 0000.png, 0001.png, ... in the snapshot directory (its
    own subdir, $OUT/snap/aes) as the probe's snapshots happen, one file
    per session snapshot in order. boot_test.sh copies the first PNG to
    $OUT/snap.png afterwards — that copy must NOT be indexed (it would be
    the first candidate and throw every index off by one), so this walks
    ONLY the MAME-managed snapshot directory ($OUT/snap, the `snap` dir
    next to snap.png), never $OUT itself."""
    snap_dir = os.path.join(os.path.dirname(os.path.abspath(snap_png)), "snap")
    if not os.path.isdir(snap_dir):
        return snap_png
    pngs = sorted(os.path.join(r, fn) for r, _, fs in os.walk(snap_dir)
                  for fn in fs if fn.endswith(".png"))
    if len(pngs) >= idx:
        return pngs[idx - 1]
    return snap_png


if __name__ == "__main__":
    sys.exit(main())
