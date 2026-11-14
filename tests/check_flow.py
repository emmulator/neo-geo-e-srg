"""Assertions for the M6 flow boot-test (scripts/flow_probe.lua).

  check_flow.py SNAP PROBE FRAMECNT_ADDR [restart [mvs_mode]]
    SNAP          the MAME snapshot (unused by the checks)
    PROBE         the probe dump:
                    I <n> <fc> <cur> <chg> <mod1>     every frame (AES)
                    M <n> <fc> <flag> <timer>         every frame (MVS:
                                                      bios_mvs_flag and
                                                      bios_compulsion_timer)
                    R <n> <fc> <lives> <go> <mod1>    every game frame, the
                                                      flow-mvs-norestart leg
                                                      (the cart's
                                                      rules.lives/game_over
                                                      and bios_player_mod1)
                    F <n> <fc>                        fix rows follow
                    W <r> <40 chars>                  a fix row
                    Z <n> <fc> <nonzero>              game-slot height count
                    V <n> <fc> <scb1sig>             the dome's SCB1 first-column
                                                      row-0/1 tile signature (the view)
                    T <n> <fc> <page> <t> <cred>      the cart's title state
                                                      (title_page / title_t /
                                                      credits, M6 Task 6)
                    L <n> <fc> <valid> <level>      the cart's title level
                                                      (flow_level_valid /
                                                      flow_level, the
                                                      backup-RAM bytes read
                                                      from RAM, M6 Task 7)
                    G <n> <fc> <rules_level> <mis_level> a game frame's
                                                      rules.level / mis.level
                                                      (read from RAM, M6
                                                      Task 7)
                    C <n> <fc>                        a title frame's 11 dome
                                                      SCB2/3/4 words follow
                                                      (M6 Task 6)
                    D <c> <scb2> <scb3> <scb4>        one dome column
                    SEED <n> <seed>                   the cart's mis_seed_used
                                                      (Task 1)
                    FIRST <n> <ring> <phi>            the first missile's
                                                      target (Task 1)
                    GO <n> <fc>                       GAME OVER first seen
                    SNAP <n> <fc>
                    EXIT ...
    FRAMECNT_ADDR 0 disables the exact fc alignment
    restart        1: prove the A-at-GAME OVER+60 restart (the task's d);
                   else prove the no-A return to the title (the task's c).
    mvs_mode      flow-mvs, flow-mvs-start: prove the MVS harness (M6
                   Task 2); flow-mvs-norestart: prove the M6 Task 4 rule —
                   on MVS, A at GAME OVER does nothing, the 295-frame
                   return still happens. flow-pages / flow-pages-c (M6
                   Task 6): prove the title's eleven pages turn every 295
                   frames (or on a C press), that the dome is drawn on
                   page 0 only and rebuilt after the wrap, and that every
                   sampled title frame's fix rows equal tests/title_model.py
                   for the page/level/t/credits read from RAM in the same
                   frame (checked by check_pages / check_pages_c).

The AES legs boot the NORMAL cart with the Start window shifted to MAME
frame 1200, so the title runs for over a second (proof a) then a game begins
(proof b). Proof c holds Up to GAME OVER, lets the 295-frame window expire,
and the cart returns to the title; proof d presses A at GAME OVER + 60 and
sees a new game instead. Every number below (game 1's GAME OVER, the
295-frame window, the 300-MAME-frame return bound) comes from the model
and the plan's confirmed facts. Task 1 seeds the missiles from the
title's time, so game 1's GAME OVER is 8188 at the flow legs' Start
window (1200..1204; the old RNG_SEED game ended at 6509), and 17525 at
flow-return's default Start (600..604) — the checker keys it to the
model's frame, not a fixed one.

The MVS legs run `neogeo -bios euro -cart1 esrg` (the plan's confirmed
facts, 2026-10-17): bios_mvs_flag (0x10FD82) reads 0x80 from frame 280; a
"Coin 1" hold on frames 1500..1504 makes the BIOS set bios_compulsion_timer
(0x10FDDA) to BCD 0x30 seconds, counted down; with no Start the BIOS calls
the cart's player_start itself when the countdown runs out, so hud_framecnt
first becomes 1 at frame 3312 (`flow-mvs`); with "1 Player Start" held on
1800..1804 as well it becomes 1 at frame 1802 (`flow-mvs-start`). The M6
Task 3 MVS proofs (HUD-layout Task 3 / attract A1: the prompt is row 21):
the title's prompt row says INSERT COIN before the coin and PRESS START after it
(each alternating with "B TO CHANGE LEVEL" every 64 frames, neither text
ever in the other window), row 28 is blank on AES and before a coin, and
after the coin (main_mvs_title) row 28 cols 19..20 carry the BCD
compulsion timer's two digits, high nibble then low nibble, matching the
timer byte read from RAM in the same frame, with at least 20 different
digit pairs seen.

The M6 Task 4 leg (`flow-mvs-norestart`) plays the Up-held game on MVS
(coin at 1500, Start at 1800, so the game begins at frame 1802 — held Up
from the first game frame, GAME OVER at fc 6965 under Task 1's seed
(6509 was the RNG_SEED game)), taps A at GAME OVER + 60,
and proves A does not restart the game: the rules' lives stay 0 and
game_over stays set through the whole 295-frame window, bios_player_mod1
reads 0 at GAME OVER + 295..+300, and the title rows are back within 600
MAME frames of GAME OVER (the 295-frame session window plus the ~200-frame
BIOS rebuild).

The M6 Task 6 legs:
  `flow-pages` (AES, no Start at all, 3200 MAME frames): the title starts
  at ~frame 477 (the AES BIOS preamble ~470 + margin), so pages 0 .. 8 then
  0 are all seen inside the run — the 8 -> 0 wrap lands at ~frame 3132
  (page 0's first frame + 9 x 295). The page advances every 295 frames
  exactly (title_page/title_t read from the cart's RAM), every sampled
  title frame's fix rows 0..27 equal tests/title_model.py's rows for the
  same frame's page/level/t/credits, and the dome's SCB words show the
  whole chain on every page 0..10 (attract A2 draws the scene under the
  title), and the rebuilt chain after the wrap equal to the first page-0
  frame's.
  `flow-pages-c` (MVS, no coin/Start): main() enters at ~frame 749, so page
  0 spans 749..1043; a C tap on MAME frames 900 and 1000 turns the page
  0 -> 1 -> 2 on (or within 2 frames of) those frames, and title_t resets
  to 0 at each turn. The dome dumps at pages 0, 1, 2 prove the dome is
  drawn as in play on every page: the driver has a real height there and
  the followers stay sticky, just as on page 0.

The M6 Task 6 proof 6 mutations, each seen to fail its check and then
reverted: (a) the page time 250 instead of 295; (b) hiding the dome by
zeroing only the driver's SCB3; (c) writing every title row every frame.
All three are proven by check_pages / check_pages_c below.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import board_model as bm  # noqa: E402  (high-score boards Task B2)
import hud_model as hm  # noqa: E402
import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import rules_model as rm  # noqa: E402
import ship_model as sm  # noqa: E402
import title_model as tm  # noqa: E402
import layout as lay  # noqa: E402
import neo_palette as npal  # noqa: E402  (the play backdrop: the sky)
import check_snapshot as cs  # noqa: E402  (the scene-aware dome pixel count)


_TITLE2 = None


def _title2():
    """(TITLE2_NPROF, TITLE2_ROW_BASE, TITLE2_CAP_BASE, title2_idx,
    title2_rprof, index -> character) from build/title_font.h (tools/
    generate_srom.py --title2-header, high-score boards Task B4)."""
    global _TITLE2
    if _TITLE2 is None:
        text = open(os.path.join(ROOT, "build", "title_font.h")).read()
        nprof = int(re.search(r"#define TITLE2_NPROF (\d+)", text).group(1))
        row_base = int(re.search(r"#define TITLE2_ROW_BASE (\d+)", text).group(1))
        cap_base = int(re.search(r"#define TITLE2_CAP_BASE (\d+)", text).group(1))
        idx = [int(x) for x in re.search(
            r"title2_idx\[128\] = \{(.*?)\}", text).group(1).split(",")]
        rprof = [int(x) for x in re.search(
            r"title2_rprof\[128\] = \{(.*?)\}", text).group(1).split(",")]
        # title2_idx maps every code without a glyph to the space's index,
        # so an inverse lookup must not pick code 0 for the space: use the
        # real space code, and the smallest code for the other indices.
        sp_i = idx[ord(' ')]
        chars = []
        for i in range(max(idx) + 1):
            if i == sp_i:
                chars.append(ord(' '))
            else:
                chars.append(min(c for c in range(128) if idx[c] == i))
        _TITLE2 = (nprof, row_base, cap_base, idx, rprof, chars)
    return _TITLE2


def _decode_row(raw):
    """a probe W line's 40 chars -> the row as the models build it: the
    probes write every S ROM tile >= 0x80 as a <NN> escape (the stream is
    otherwise ASCII). The HUD's icons (128/129) and the title's logo tiles
    (130..193) pass through as chr(NN). A title text/cap cell (B4) is
    TITLE2 base + title2_idx[character] * TITLE2_NPROF +
    title2_rprof[left neighbour], so the character is recovered from the
    tile's index; the cell after a line's last character decodes to the
    space the model stores. The in-play HUD's own tiles are all below 128,
    so this map never touches a game row."""
    nprof, row_base, cap_base, _idx, _rprof, chars = _title2()
    out = []
    i = 0
    while i < len(raw):
        m = re.match(r"<(\d+)>", raw[i:])
        if m:
            tile = int(m.group(1))
            if tile >= row_base:
                off = tile - (cap_base if tile >= cap_base else row_base)
                ci = off // nprof
                # the S ROM's padding tiles (past the font's last block) and
                # a cleared fix cell's 0x0fff read as blank.
                out.append(chr(chars[ci]) if ci < len(chars) else ' ')
                i += m.end()
                continue
            out.append(chr(tile))
            i += m.end()
        else:
            out.append(raw[i])
            i += 1
    return "".join(out)

GAME_OVER_WAIT = 295
TITLE_PAGE_FRAMES = 295          # the Vectrex's 250 x 59/50: one page turn
ROW_COUNT = 30                   # HUD-layout Task 2: the dump now carries rows 0..29
# HUD-layout Task 3: title_model now builds 30 rows; the title's own text
# lives in rows 0..27, and rows 28/29 hold the MVS countdown's two digits
# (row 28) or stay blank (row 29) — the "title rows" the model compares
# are still 0..27, exactly as title_rows never writes 28/29.
TITLE_ROWS = 28
# the title rows, centred exactly as src/fix.c's fix_center places them (the
# same (40 - n) // 2 formula hud_model uses for its own centred rows).
# M8 art pass: page 0's name is the logo's fix tiles on rows 2..5 (the
# probe writes every tile >= 0x80 as <NN> escapes); row 3, the logo's second
# tile row, stays the title gate. The level, best and prompt rows come from
# src/title.h (title_model reads them). Attract Task A1: the text glyph
# tiles are TITLE_FONT_BASE + code and their caps TITLE_CAP_BASE + code
# (src/title.h); _decode_row maps them back to the model's characters.
ROW3 = tm.logo_row(3 - tm.LOGO_ROW)
LEVEL_ROW, PROMPT_ROW = tm.LEVEL_ROW, tm.PRESS_ROW
# high-score boards Task B4: the title's text/cap tiles come from the
# thick-outline font (build/title_font.h); the old TITLE_FONT_BASE blocks
# stay in the S ROM but are no longer drawn by the title.
# HUD-layout Task 3 / attract Task A1: page 0's lines are the level and best
# on rows 7/9 and the prompt on row 21 (above the console), each with its
# cap in the row below; the prompt alternates every 64 frames between the
# prompt text (t & 64 clear) and "B TO CHANGE LEVEL" (t & 64 set).
ROW9_ON = " " * ((40 - 11) // 2) + "PRESS START" + " " * (40 - 11 - (40 - 11) // 2)
ROW9_OFF = " " * 40        # a blank prompt row (e.g. pages 1..10's cap)
ROW9_B = " " * ((40 - 17) // 2) + "B TO CHANGE LEVEL" + " " * (40 - 17 - (40 - 17) // 2)
# the MVS attract title's prompt row on text (M6 Task 3; attract A1 puts it
# on row 21): "INSERT COIN" is 11 chars, centred at the same
# (40 - n) // 2 column as "PRESS START".
ROW9_COIN = " " * ((40 - 11) // 2) + "INSERT COIN" + " " * (40 - 11 - (40 - 11) // 2)
# the MVS title row 28: the BIOS compulsion timer's two BCD digits, high
# nibble then low nibble, at cols 19 and 20 — the countdown's position from
# src/title.h via tests/layout.py (the plan's one source of truth).
ROW28_LO, ROW28_HI = lay.d.title("TITLE_COUNTDOWN_COL"), \
    lay.d.title("TITLE_COUNTDOWN_COL") + 2      # row28[19:21]
# the MVS title-row windows the probe samples (M6 Task 3): 300..590 is
# the plain main() attract title's page 0 before a coin (with no BIOS logo,
# main() starts the title at MAME frame ~299 and page 0 lasts 295 frames),
# 1530..3300 the post-coin main_mvs_title() title (the countdown row is
# live there).
MVS_PRE_LO, MVS_PRE_HI = 300, 590
MVS_POST_LO, MVS_POST_HI = 1530, 3300


def parse(fname):
    """(records, mvs_records, norestart_records, samples, slots, views,
    title, levels, games, domes, go, snap, exit, bests, scores, seeds,
    first) — seeds: {mame frame: the cart's mis_seed_used (Task 1)}; first:
    the first missile the cart launched (mame frame, ring, phi) from the
    FIRST line, or None.
    records: [(n, fc, cur, chg, mod1)] (AES, from the I lines);
    mvs_records: [(n, fc, flag, timer)] (MVS, from the M lines);
    norestart_records: [(n, fc, lives, game_over, mod1)] (the Task 4 leg,
    from the R lines); samples: {n: (fc, rows)} from the F blocks; slots:
    {n: (fc, nonzero)} from the Z lines; views: {n: (fc, tile)}; title:
    {n: (fc, page, t, cred)} from the T lines (M6 Task 6); levels: {n:
    (fc, level)} from the L lines (the flow_level backup-RAM byte, M6 Task
    7); games: {n: (fc, rules_level, mis_level)} from the G lines (M6 Task
    7); domes: {n: (fc, [11 x (scb2, scb3, scb4)])} from the C/D blocks;
    go: (n, fc); snap: (n, fc); exit: (n, fc, mod1); bests: {n: (fc, b0,
    b1, b2, hexbytes)} from the B lines (the flow_board backup board, Task
    B2: b0..b2 are the three top entries, hexbytes the 126-byte image);
    scores: {n: (fc, score10)} from the SC lines (mis.score10 at GAME OVER,
    M6 Task 9); cards: {n: (fc, [(cmd, ans), ...])} from the A lines (the
    card-log pairs, M6 Task 10)."""
    (records, mvs_records, norestart_records, samples, slots, views, title) = \
        [], [], [], {}, {}, {}, {}
    levels, games = {}, {}
    domes = {}
    bests, scores = {}, {}
    cards = {}                       # {n: (fc, [(cmd, ans), ...])} (M6 Task 10)
    seeds = {}                       # {n: mis_seed_used} (Task 1)
    first = None                     # the first missile (Task 1)
    go = snap = exit_ = None
    cur_f, cur_rows, last_fc, cur_dome = None, None, 0, None
    with open(fname, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            tag = p[0]
            if tag == "I":
                n, fc, cur, chg, mod1 = (int(x) for x in p[1:6])
                records.append((n, fc, cur, chg, mod1))
                last_fc = fc
            elif tag == "M":
                n, fc = int(p[1]), int(p[2])
                flag, timer = int(p[3], 16), int(p[4], 16)   # both hex bytes
                mvs_records.append((n, fc, flag, timer))
                last_fc = fc
            elif tag == "R":
                n, fc = int(p[1]), int(p[2])
                lives, go_, mod1 = (int(x, 16) for x in p[3:6])
                norestart_records.append((n, fc, lives, go_, mod1))
                last_fc = fc
            elif tag == "L":
                # L <n> <fc> <valid> <level>: the cart's flow_level_valid
                # and flow_level backup-RAM bytes (M6 Task 7)
                levels[int(p[1])] = (int(p[2]), int(p[3]), int(p[4]))
            elif tag == "G":
                games[int(p[1])] = (int(p[2]), int(p[3]), int(p[4]))
            elif tag == "B":
                # B <n> <fc> <b0> <b1> <b2> <126 hex bytes>: the cart's
                # flow_board backup board (high-score boards Task B2)
                bests[int(p[1])] = (int(p[2]), int(p[3]), int(p[4]),
                                    int(p[5]), p[6])
            elif tag == "SC":
                # SC <n> <fc> <score10>: mis.score10 at GAME OVER (M6
                # Task 9)
                scores[int(p[1])] = (int(p[2]), int(p[3]))
            elif tag == "A":
                # A <n> <fc> <cmd:ans>,...: the card-log pairs — the
                # commands and answers of the cart's card calls (M6 Task
                # 10), hex command/answer pairs joined by commas
                try:
                    pairs = [tuple(int(x, 16) for x in q.split(":"))
                             for q in p[3].split(",")]
                except (ValueError, IndexError):
                    pairs = []
                cards[int(p[1])] = (int(p[2]), pairs)
            elif tag == "F":
                cur_f = int(p[1])          # the MAME frame n
                cur_fc = int(p[2])         # the game-session fc
                cur_rows = [None] * ROW_COUNT
            elif tag == "W":
                if cur_rows is not None:
                    cur_rows[int(p[1])] = _decode_row(line.split(" ", 2)[2].rstrip("\n"))
                    if all(r is not None for r in cur_rows):
                        samples[cur_f] = (cur_fc, cur_rows)
                        cur_f, cur_rows = None, None
            elif tag == "Z":
                slots[int(p[1])] = (int(p[2]), int(p[3]))
            elif tag == "V":
                views[int(p[1])] = (int(p[2]), int(p[3], 16))
            elif tag == "T":
                n, fc = int(p[1]), int(p[2])
                title[n] = (fc, int(p[3]), int(p[4]), int(p[5]))
            elif tag == "C":
                cur_dome = [int(p[1]), int(p[2]), [], int(p[3])]
            elif tag == "D":
                if cur_dome is not None:
                    # D <n> <c> <scb2> <scb3> <scb4> (all hex)
                    cur_dome[2].append((int(p[3], 16), int(p[4], 16),
                                        int(p[5], 16)))
                    if len(cur_dome[2]) == lay.d.DOME_COLS:
                        domes[cur_dome[0]] = (cur_dome[1], cur_dome[2],
                                              cur_dome[3])
                        cur_dome = None
            elif tag == "GO":
                go = (int(p[1]), int(p[2]))
            elif tag == "SNAP":
                snap = (int(p[1]), int(p[2]))
            elif tag == "SEED":
                seeds[int(p[1])] = int(p[2])
            elif tag == "FIRST":
                first = (int(p[1]), int(p[2]), int(p[3]))
            elif tag == "EXIT":
                exit_ = (int(p[1]), int(p[2]), int(p[3]))
    return records, mvs_records, norestart_records, samples, slots, views, \
        title, levels, games, domes, go, snap, exit_, bests, scores, cards, \
        seeds, first


def title_samples(samples, title):
    """the title-condition samples: (n, rows) for each sampled frame where
    the region is unambiguously the title: fc == 0 AND row 3 shows the
    cart's "E-SRG" (HUD-layout Task 3: page 0's name row moved from 4 to
    3; the probe dumps rows unconditionally while fc == 0, and the checker
    gates on row 3 — see scripts/flow_probe.lua: a pre-read corrupted the
    FIXMAP read-back of the later rows in MAME)."""
    out = []
    for n in sorted(samples):
        fc, rows = samples[n]
        if fc == 0 and rows[3] == ROW3:
            out.append((n, rows))
    return out


def title_rows(samples, slots, views):
    """backwards-compatible alias: the title samples as (n, rows)."""
    return title_samples(samples, {})


def first_game_frame(records, samples):
    """(fc of the first game frame seen as a sampled-row fc, or None)."""
    fcs = [fc for (fc, _rows) in samples.values() if fc >= 1]
    return min(fcs) if fcs else None


def model_first_rows(seed=None):
    ships, mis, rules = sm.Ship(), mm.Missiles(seed=seed), rm.Rules(1)
    return hm.hud_rows(rules, mis)


def hud_integ_present(row):
    """the integrity row is drawn: its icon tile plus "100%" (the icon is a
    raw tile byte, so the word "INTEG" is not in the probe's row string)."""
    return "%" in row and any(ch.isdigit() for ch in row)


def hud_score_present(row):
    """the score/lives row is drawn: at least the score's digit."""
    return any(ch.isdigit() for ch in row)


# ---- attract Task A1 proof 3: the title text is gold/amber, outlined black ----

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SROM_PATH = os.path.join(ROOT, "build", "rom", "esrg-s1.s1")
_SROM_DATA = None


def _srom_data():
    global _SROM_DATA
    if _SROM_DATA is None:
        _SROM_DATA = open(SROM_PATH, "rb").read()
    return _SROM_DATA


def _srom_tile_pixels(tile):
    """one 32-byte S ROM tile -> its 64 colour indices, row-major."""
    data = _srom_data()[tile * 32:(tile + 1) * 32]
    px = [0] * 64
    i = 0
    for xa, xb in ((4, 5), (6, 7), (0, 1), (2, 3)):
        for y in range(8):
            b = data[i]
            i += 1
            px[y * 8 + xa] = b & 0x0f
            px[y * 8 + xb] = (b >> 4) & 0x0f
    return px


def _title_cell_tile(page, row, ch, left):
    """the S ROM tile the title's fix cell (row, col, ch) draws: logo tiles
    on page 0's logo rows (tile = code), or the thick font's
    base + title2_idx[ch] * TITLE2_NPROF + title2_rprof[left] on a text/cap
    row; None for a blank row. `left` is the cell's left neighbour (a space
    at a line's start); the cell after a line's last character is a space
    with the line's last character as its left neighbour."""
    code = ord(ch)
    if page == 0:
        if tm.LOGO_ROW <= row < tm.LOGO_ROW + tm.LOGO_ROWS:
            return code
        if row in (tm.LEVEL_ROW, tm.BEST_ROW, tm.VER_ROW, tm.PRESS_ROW):
            base = _title2()[1]
        elif row in (tm.LEVEL_ROW + 1, tm.BEST_ROW + 1, tm.VER_ROW + 1,
                    tm.PRESS_ROW + 1):
            base = _title2()[2]
        else:
            return None
    elif page <= 3:                  # Task B3: the board pages' layout
        if row in (tm.BOARD_HEADER_ROW, tm.BOARD_LEVEL_ROW):
            base = _title2()[1]
        elif row in (tm.BOARD_HEADER_ROW + 1, tm.BOARD_LEVEL_ROW + 1):
            base = _title2()[2]
        elif tm.BOARD_FIRST_ROW <= row < tm.BOARD_FIRST_ROW + \
                tm.BOARD_ROWS * tm.BOARD_STEP:
            base = _title2()[1 if (row - tm.BOARD_FIRST_ROW) % tm.BOARD_STEP == 0
                             else 2]
        else:
            return None
    elif 6 <= row <= 24 and (row - 6) % 2 == 0:
        base = _title2()[1]
    elif 7 <= row <= 25 and (row - 7) % 2 == 0:
        base = _title2()[2]
    else:
        return None
    nprof, _rb, _cb, idx, rprof, _chars = _title2()
    code = code if code < 128 else ord(' ')
    left_code = ord(left) if ord(left) < 128 else ord(' ')
    return base + idx[code] * nprof + rprof[left_code]


def check_title_pixels(samples, domes, ev, snap_files, snap_dir):
    """Attract Task A1 / high-score boards B4 proof 3 (the flow-pages
    leg): a snapshot of page 0 and of one text page. For every fix cell the
    title draws, decode its S ROM tile (the logo, or the thick font's
    TITLE2_ROW_BASE / TITLE2_CAP_BASE + title2_idx[ch] * TITLE2_NPROF +
    title2_rprof[left]) and compare the snapshot pixel with the title
    palette's colour for that index: every text fill pixel is amber 1..4,
    every logo fill pixel is gold 1/3/6..9, every outline pixel (index 5)
    is black. The snapshots are
    taken at the page PINs (one per page 0..10 + the wrapped page 0), so the
    chosen frames' rows are the model's page 0 and a text page (page 0's
    first frame is also a sampled frame; a text page's rows do not depend on
    t). Returns the failure strings (the caller prints them)."""
    failures = []
    from PIL import Image
    pal = npal.fix_pal_rgb()
    p0s = [n for n in ev if domes[n][2] == 0]
    texts = [n for n in ev if 1 <= domes[n][2] <= 10]
    if not p0s:
        return ["no page-0 snapshot for the title pixel proof"]
    if not texts:
        return ["no text-page snapshot for the title pixel proof"]
    picks = [(p0s[0], 0), (texts[0], domes[texts[0]][2])]
    counts = []
    for n, page in picks:
        if n in samples:
            rows = samples[n][1]
        else:
            rows = tm.title_rows(page, 1, 0, DEFAULT_BOARD, 0)
        fname = snap_files[ev.index(n)]
        im = Image.open(os.path.join(snap_dir, fname)).convert("RGB")
        w, h = im.size
        sx, sy = w / 320.0, h / 224.0
        text_fill = text_outline = logo_fill = logo_outline = 0
        bad = []
        for row in range(TITLE_ROWS):
            for col in range(40):
                ch = rows[row][col]
                left = rows[row][col - 1] if col else ' '
                tile = _title_cell_tile(page, row, ch, left)
                if tile is None:
                    continue
                idxs = _srom_tile_pixels(tile)
                is_logo = page == 0 and tm.LOGO_ROW <= row < tm.LOGO_ROW + tm.LOGO_ROWS
                allowed_fill = ({1, 3, 6, 7, 8, 9} if is_logo
                                else {1, 2, 3, 4})
                for yy in range(8):
                    for xx in range(8):
                        idx = idxs[yy * 8 + xx]
                        if idx == 0:
                            continue
                        if idx == 5:
                            if is_logo:
                                logo_outline += 1
                            else:
                                text_outline += 1
                        elif idx in allowed_fill:
                            if is_logo:
                                logo_fill += 1
                            else:
                                text_fill += 1
                        else:
                            bad.append((row, col, xx, yy, "colour %d" % idx))
                            continue
                        want = pal[idx]
                        X, Y = col * 8 + xx, row * 8 - 16 + yy
                        xa = int(X * sx)
                        xb = max(xa + 1, int((X + 1) * sx))
                        ya = int(Y * sy)
                        yb = max(ya + 1, int((Y + 1) * sy))
                        hit = None
                        for py in range(ya, yb):
                            for px in range(xa, xb):
                                got = tuple(im.getpixel((px, py))[:3])
                                if got != want:
                                    hit = (got, want)
                                    break
                            if hit is not None:
                                break
                        if hit is not None:
                            bad.append((row, col, xx, yy, hit[0], hit[1]))
        counts.append((n, page, text_fill, text_outline, logo_fill,
                       logo_outline, len(bad)))
        if text_fill == 0:
            failures.append(f"page {page} snapshot at frame {n} has no text "
                            "fill pixels")
        if text_outline == 0:
            failures.append(f"page {page} snapshot at frame {n} has no text "
                            "outline pixels")
        if page == 0 and logo_fill == 0:
            failures.append(f"page 0 snapshot at frame {n} has no logo fill "
                            "pixels")
        if page == 0 and logo_outline == 0:
            failures.append(f"page 0 snapshot at frame {n} has no logo "
                            "outline pixels")
        if bad:
            failures.append(f"page {page} snapshot at frame {n}: {len(bad)} "
                            f"title pixels differ from the palette/S ROM; "
                            f"first {bad[:5]}")
    n0, p0, tf0, to0, lf0, lo0, b0 = counts[0]
    n1, p1, tf1, to1, _lf1, _lo1, b1 = counts[1]
    print(f"title pixels: page 0 frame {n0}: {tf0} text fill (amber 1..4), "
          f"{to0} text outline (black), {lf0} logo fill (gold 1/3/6..9), "
          f"{lo0} logo outline (black), {b0} mismatches; page {p1} frame "
          f"{n1}: {tf1} text fill (amber 1..4), {to1} outline (black), "
          f"{b1} mismatches")
    return failures


# Task G1: the GAME OVER rows are the thick font's text row (row 7) and its
# cap row (row 8), with the same tile formula as the title's text rows.
def gameover_model_rows():
    """the model's 30 rows for a game_over state: rows 7/8 are "GAME OVER"
    and its cap (the rest only matters for the rows the check compares)."""
    rules = rm.Rules(1)
    rules.game_over = 1
    mis = mm.Missiles(seed=1)
    return hm.hud_rows(rules, mis)


def gameover_rows_failures(samples, go):
    """rows 7/8 at the probe's GAME OVER sample must equal the model's."""
    if go is None:
        return []
    hit = samples.get(go[0])
    if hit is None:
        return ["no fix-row sample at the GAME OVER frame"]
    fc, rows = hit
    want = gameover_model_rows()
    out = []
    for r in (hm.HUD_GAMEOVER_ROW, hm.HUD_GAMEOVER_CAP_ROW):
        if rows[r] != want[r]:
            out.append(f"GAME OVER frame {fc}: row {r} {rows[r]!r} != "
                       f"model {want[r]!r}")
    return out


def _gameover_cell_tile(row, ch, left):
    """the S ROM tile a GAME OVER cell draws: the thick font's text base on
    row 7, its cap base on row 8, + title2_idx[ch] * NPROF +
    title2_rprof[left] (the title's own formula)."""
    nprof, row_base, cap_base, idx, rprof, _chars = _title2()
    base = row_base if row == hm.HUD_GAMEOVER_ROW else cap_base
    code = ord(ch) if ord(ch) < 128 else ord(' ')
    lc = ord(left) if ord(left) < 128 else ord(' ')
    return base + idx[code] * nprof + rprof[lc]


def check_gameover_pixels(snap_png, rows):
    """Task G1 proof 3: a GAME OVER snapshot's text/cap pixels equal the
    thick font's S ROM tiles through PAL_HUD (the title's fix palette): fill
    pixels are the amber gradient 1..4, the 2-px outline is black 5."""
    failures = []
    from PIL import Image
    pal = npal.fix_pal_rgb()
    im = Image.open(snap_png).convert("RGB")
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    fill = outline = bad = 0
    first = None
    for row in (hm.HUD_GAMEOVER_ROW, hm.HUD_GAMEOVER_CAP_ROW):
        for col in range(40):
            ch = rows[row][col]
            left = rows[row][col - 1] if col else ' '
            idxs = _srom_tile_pixels(_gameover_cell_tile(row, ch, left))
            for yy in range(8):
                for xx in range(8):
                    idx = idxs[yy * 8 + xx]
                    if idx == 0:
                        continue
                    if idx == 5:
                        outline += 1
                    elif 1 <= idx <= 4:
                        fill += 1
                    else:
                        bad += 1
                        continue
                    want = pal[idx]
                    X, Y = col * 8 + xx, row * 8 - 16 + yy
                    xa = int(X * sx)
                    xb = max(xa + 1, int((X + 1) * sx))
                    ya = int(Y * sy)
                    yb = max(ya + 1, int((Y + 1) * sy))
                    hit = None
                    for py in range(ya, yb):
                        for px in range(xa, xb):
                            got = tuple(im.getpixel((px, py))[:3])
                            if got != want:
                                hit = (got, want)
                                break
                        if hit is not None:
                            break
                    if hit is not None:
                        bad += 1
                        if first is None:
                            first = (row, col, xx, yy, hit[0], hit[1])
    if fill == 0:
        failures.append("the GAME OVER snapshot has no thick-font fill "
                        "pixels on rows 7/8")
    if outline == 0:
        failures.append("the GAME OVER snapshot has no black outline pixels "
                        "(the 2-px border is missing)")
    if bad:
        failures.append(f"the GAME OVER snapshot has {bad} pixels differing "
                        f"from the S ROM + PAL_HUD; first {first}")
    else:
        print(f"GAME OVER pixels: {fill} fill (amber 1..4), {outline} black "
              f"outline pixels on rows 7/8, 0 mismatches")
    return failures


def check_pages(samples, title, domes, views, bests):
    """M6 Task 6 / high-score boards Task B3, proofs 1 + 2 + 3
    (flow-pages, AES no-Start):
    1. every sampled title frame's fix rows 0..27 equal
       tests/title_model.py's rows for the page, level (NORMAL here), t
       and credits read from RAM in the same frame; the count of compared
       frames per page is reported.
    2. the page advances every 295 frames exactly (title_page/title_t from
       RAM), through 10 -> 0 (11 pages: the dome, the three boards and the
       seven info pages).
    3. dome: on every page the driver SCB3 has a real height and the 10
       followers have the sticky bit with no own height (attract A2 draws
       the game's scene, dome included, on every page); back on page 0
       after the wrap, all the dome's SCB2/SCB3/SCB4 words equal those of
       the first page-0 frame (the chain rebuilt, not half a dome) —
       checked on the dump blocks the probe keys to the PIN frames.
    (Mutation (b) — hide by zeroing only the driver's SCB3 — fails the
    pages 1..10 check: the followers keep their sticky bit and height.
    Mutation (a) — 250 instead of 295 — fails the turn check.)"""
    failures = []
    if not samples:
        failures.append("no fix-row samples at all (did the run start?)")
        return 1
    # ---- 1. the model-vs-drawn rows, gated on the RAM state read in the
    # same frame (title_page / title_t / credits from the T records) ----
    per_page = {}
    n_compared = 0
    checked_any = False
    for n in sorted(samples):
        fc, rows = samples[n]
        trec = title.get(n)
        if trec is None:
            failures.append(f"no T record for sampled frame {n}; "
                            "is FLOW_PAGE_ADDR set and the addresses right?")
            continue
        _tfc, page, t, cred = trec
        if fc != 0:
            continue
        # Attract Task A2: title_commit() writes the rows staged by the
        # previous title frame, so the fix layer is one vblank behind the
        # T record's RAM state. Compare the drawn rows with the model of
        # the state that produced them: t-1, and on a turn (t 0) the
        # previous page's last frame. flow-pages has only automatic turns
        # (no B/C), so the previous page is page-1 mod 11.
        if t == 0:
            prev_page = (page - 1) % tm.PAGES
            prev_t = TITLE_PAGE_FRAMES - 1
        else:
            prev_page = page
            prev_t = t - 1
        # the title gate: page 0 shows "E-SRG" on row 3 (HUD-layout Task
        # 3); pages 1..10 draw from row 6 (title.c; the board pages 1..3
        # all draw "HIGH SCORES") and row 3 is blank — the drawn page is
        # the authoritative title marker, and for drawn page 0 the row-3
        # check still runs below.
        if prev_page == 0:
            if rows[3] != ROW3:
                continue
        elif rows[6].strip() not in PAGE_TITLES:
            # the entry's first frames can still be blank (the scene/rows
            # are drawn over the entry's two vblanks); skip until the drawn
            # page is unambiguous.
            continue
        if not (0 <= prev_page < tm.PAGES):
            failures.append(f"frame {n}: drawn title_page reads {prev_page} "
                            f"(out of 0..{tm.PAGES - 1})")
            continue
        if not (0 <= prev_t < TITLE_PAGE_FRAMES):
            failures.append(f"frame {n}: drawn title_t reads {prev_t} "
                            "(out of 0..294)")
            continue
        # flow-pages is AES (credits 0): the title's own credits value,
        # read from the RAM the cart drew from — the model's credits
        # argument is exactly this byte. Level NORMAL = 1.
        want = tm.title_rows(prev_page, 1, prev_t, board_at(n, bests), cred)
        n_compared += 1
        checked_any = True
        per_page[prev_page] = per_page.get(prev_page, 0) + 1
        for r in range(TITLE_ROWS):    # the model's rows 0..27.
            # Attract Task A2: the HUD now draws its rows under the title;
            # row 26 is the HUD's integrity, not a title row. A3: the title
            # HUD is the demo's, so its exact values are the demo boot-test's
            # proof; here only require the rows to stay drawn.
            if r == hm.HUD_INTEG_ROW:
                continue
            # This leg is AES (cred 0), so no title row is ever skipped:
            # page 0's row 21 IS the prompt line (HUD-layout Task 3 /
            # attract A1 — title_rows writes it), unlike the MVS post-coin
            # rows (check_mvs / check_best_* compare those against the
            # model separately).
            if rows[r] != want[r]:
                failures.append(f"frame {n}: row {r} != title_model's "
                                f"(page {prev_page}, t {prev_t}, credits {cred}):\n"
                                f"  drawn {rows[r]!r}\n"
                                f"  model {want[r]!r}")
                break
        # Attract Task A3: the demo's HUD is drawn on every title page. Its
        # exact score/integrity/lives are proved frame by frame by
        # tests/check_demo.py; the flow legs only require the HUD rows to
        # remain present (the page/Start proof is this checker's job).
        if not hud_integ_present(rows[hm.HUD_INTEG_ROW]):
            failures.append(f"frame {n}: HUD row {hm.HUD_INTEG_ROW} is "
                            f"{rows[hm.HUD_INTEG_ROW]!r} (the demo's HUD is "
                            f"not drawn)")
        if not any(ch.isdigit() for ch in rows[hm.HUD_LIVES_ROW]):
            failures.append(f"frame {n}: HUD row {hm.HUD_LIVES_ROW} is "
                            f"{rows[hm.HUD_LIVES_ROW]!r} (the demo's score/"
                            f"lives row is not drawn)")
    if not checked_any:
        failures.append("no title frames were compared to the model")
    else:
        seen = ", ".join(f"page {p}: {c}" for p, c in sorted(per_page.items()))
        print(f"pages: compared {n_compared} title frames to title_model "
              f"({seen})")

    # ---- 2. the page every 295 frames ----
    # the turns, defined on the T records (the pages run's T lines are the
    # every-6-frame title samples, so a turn's observed frame is within 6
    # of the true one; the t reset a turn causes is the primary evidence,
    # and it is exact — title_t is 0..294, so a reset from a high value is
    # unambiguous: the post-turn sample's t is small).
    ts = sorted(title)
    prev_page, prev_t, turns, first = None, None, [], None
    for n in ts:
        fc, page, t, cred = title[n]
        if fc != 0:
            continue
        if prev_page is None:
            prev_page, prev_t, first = page, t, n
            continue
        if page != prev_page:
            turns.append((n, prev_page, page, prev_t, t))
        prev_page, prev_t = page, t
    if not turns:
        failures.append(f"the title never turned a page (need 0.."
                        f"{tm.PAGES - 1} -> 0)")
    else:
        # the run must see pages 0, 1, 2, ... in order through 10 -> 0: the
        # first 11 turns, pages 0->1, 1->2, ..., 10->0 (a long-enough run
        # wraps again past 10 -> 0, and those extra turns are fine).
        want_seq = [(i, (i + 1) % tm.PAGES) for i in range(tm.PAGES)]
        got_seq = [(a, b) for (_n, a, b, _pt, _t) in turns]
        if got_seq[:tm.PAGES] != want_seq:
            failures.append(f"the page sequence was {got_seq}, expected to "
                            f"begin {want_seq} (0,1,...,{tm.PAGES - 1} -> 0 "
                            "in order)")
        # the turn time: each turn lands exactly 295 title frames after the
        # last, from the title's first frame. The T records are the title
        # pages read from RAM; the turn's observed frame (within the 6-frame
        # sample cadence) plus the pre-turn title_t gives the true turn
        # frame — and title_t itself must reset (post-turn t < 12). The
        # title's first frame is found from page 0's t 0 at the run's start.
        # the title's first frame: the first row-3-confirmed title sample
        # (the T records at the very start read the BIOS's RAM-clear zeros
        # as page 0/t 0 — the drawn row 3 "E-SRG" is the reliable anchor).
        first_n = None
        for n in sorted(samples):
            fc, rows = samples[n]
            if fc == 0 and rows[3] == ROW3:
                first_n = n
                break
        if first_n is None:
            failures.append("could not find the title's first frame")
        else:
            # each turn's true frame ~ the observed frame minus the
            # pre-turn title_t (the sample that first saw the new page is
            # at most 6 frames after the turn): t0 + 295*k = the turn.
            for k, (n, a, b, pt, t) in enumerate(turns[:tm.PAGES]):
                if t >= 12:
                    failures.append(f"page {a} -> {b} at frame {n}: title_t "
                                    f"reads {t} right after the turn, "
                                    "expected a reset to 0 (within the "
                                    "~6-frame sample cadence)")
                    continue
                # the title frames elapsed at the observed turn: n - first_n
                # (MAME frames) is within 6 of the true turn (295*(k+1))
                # title frames — the AES title runs 1:1 with MAME frames.
                expect = (k + 1) * TITLE_PAGE_FRAMES
                if abs((n - first_n) - expect) > 8:
                    failures.append(f"page {a} -> {b} at frame {n}: the "
                                    f"turn is {(n - first_n)} title frames "
                                    f"after the first, expected {expect} "
                                    f"(every {TITLE_PAGE_FRAMES})")

    # ---- 3. the dome: drawn as in play on every page, rebuilt ----
    if not domes:
        failures.append("no dome dumps (is FLOW_DOME_SNAP set?)")
        return 1 if failures else 0
    ev = sorted(domes)
    # the probe dumps the first title frame of every page 0..10 plus the
    # first page-0 frame after the wrap: 12 dumps.
    if len(ev) < 12:
        failures.append(f"expected 12 dome dumps (one per page 0..10 + the "
                        f"wrapped page 0), got {len(ev)}")
    # each dump records the page the probe observed at dump time (the C
    # line's third field) — the page-of mapping is not needed.
    for n in ev:
        _fc, cols, p = domes[n]
        if not (0 <= p < tm.PAGES):
            failures.append(f"dome dump at frame {n}: page unknown ({p})")
            continue
        # Attract Task A2: the dome is drawn as in play on EVERY page (the
        # title's own spin/hide is gone). The driver (column 0) has a real
        # Y/height word; the followers (1..10) have the sticky bit set and
        # no own height.
        d0 = cols[0][1]
        if d0 & 0x3f == 0:
            failures.append(f"page-{p} dome dump at frame {n}: the driver "
                            "SCB3 has height 0 (the dome is not shown)")
        if not all(s3 & (1 << 6) and s3 & 0x3f == 0
                   for (_s2, s3, _s4) in cols[1:]):
            failures.append(f"page-{p} dome dump at frame {n}: the 10 "
                            "follower columns do not all have the sticky "
                            "bit with no own height")
    # the rebuilt dome: the last dump (the second page 0) must equal the
    # first page-0 dump word for word (SCB2/3/4 all 8 columns).
    p0s = [n for n in ev if domes[n][2] == 0]
    if len(p0s) >= 2:
        first_n, last_n = p0s[0], p0s[-1]
        if domes[first_n][1] != domes[last_n][1]:
            failures.append("the rebuilt dome (second page 0) SCB2/3/4 "
                            "words differ from the first page-0 frame's:\n"
                            f"  first {domes[first_n][1]}\n"
                            f"  last  {domes[last_n][1]}")
        else:
            print(f"pages: rebuilt dome SCB2/3/4 == first page 0's "
                  f"(11 slots, frames {first_n} and {last_n})")
    else:
        failures.append(f"saw {len(p0s)} page-0 dumps, need >= 2 for the "
                        "rebuilt-dome proof")

    # ---- the snapshot pixel proof (proof 3's last clause): the dome's
    # pixel count on the second page 0 is within 2% of the first ----
    # The probe snapshots once per C block, in order (0000.png = the first
    # page-0 frame, ... the wrapped page-0 last). The snapshots live in the
    # run's snap directory (boot_test.sh passes FLOW_SNAP_DIR).
    import os as _os
    snap_dir = _os.environ.get("FLOW_SNAP_DIR", "")
    if snap_dir:
        snaps = sorted(_os.listdir(snap_dir))
        # MAME writes the machine driver subdir (aes/ or neogeo/)
        if snaps and _os.path.isdir(_os.path.join(snap_dir, snaps[0])):
            snap_dir = _os.path.join(snap_dir, snaps[0])
            snaps = sorted(_os.listdir(snap_dir))
        # map the C blocks' SNAP records to the png files in order
        snap_files = [f for f in snaps if f.endswith(".png")]
        if len(snap_files) < len(ev):
            failures.append(f"{len(snap_files)} snapshots for {len(ev)} "
                            "dome dumps")
        else:
            try:
                from PIL import Image
            except Exception:
                failures.append("PIL missing: the pixel proof cannot run")
            else:
                def dome_px(fname):
                    im = Image.open(_os.path.join(snap_dir, fname)).convert("RGB")
                    w, h = im.size
                    x0, x1 = int(w * lay.d.DOME_X / 320), int(w * (lay.d.DOME_X + lay.d.DOME_W) / 320)
                    y0, y1 = int(h * lay.d.DOME_Y / 224), int(h * (lay.d.DOME_Y + lay.d.DOME_H) / 224)
                    return sum(1 for yy in range(y0, y1) for xx in range(x0, x1)
                               if cs.dome_lit(im.getpixel((xx, yy))[:3]))
                # C blocks are in ev order (0000 = ev[0] = first page 0)
                p0_idx = [i for i, n in enumerate(ev) if domes[n][2] == 0]
                if len(p0_idx) >= 2:
                    i0, i1 = p0_idx[0], p0_idx[-1]
                    c0 = dome_px(snap_files[i0])
                    c1 = dome_px(snap_files[i1])
                    print(f"pages: dome pixels page-0 first {c0}, after the "
                          f"wrap {c1}")
                    if c0 == 0:
                        failures.append(f"first page-0 snapshot has no dome "
                                        f"pixels at all ({c0})")
                    elif abs(c1 - c0) / c0 > 0.02:
                        failures.append(f"the wrapped page-0 dome has {c1} "
                                        f"pixels vs the first page 0's {c0} "
                                        "(need within 2%)")
                else:
                    failures.append(f"only {len(p0_idx)} page-0 snapshots "
                                    "(need the first and the wrapped)")
                # Attract Task A3: the title's dome is the demo's, so its
                # SCB1 view turns (check_demo.py proves the exact per-frame
                # state). The pages leg only requires the live demo range.
                title_ns = set(n for (n, _rows) in title_samples(samples, {}))
                dist = set(tile for (nn2, (fc, tile)) in views.items()
                           if nn2 in title_ns)
                if len(dist) < 2:
                    failures.append("the demo's dome SCB1 view never changed "
                                    "during the title (the demo is not "
                                    "playing)")
                elif len(dist) > 48:
                    failures.append(f"the dome's SCB1 view changed "
                                    f"{len(dist)} ways during the title "
                                    "(out of the 48 dome views)")
                else:
                    print(f"pages: the demo's dome uses {len(dist)} SCB1 "
                          f"views over the title frames")
                failures.extend(check_title_pixels(samples, domes, ev,
                                                   snap_files, snap_dir))
    if failures:
        print("FAIL flow-pages:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS flow-pages: pages 0..10 -> 0 in order, one turn every 295 "
          "frames, every sampled frame's rows match the model, the dome is "
          "drawn as in play on every page, and rebuilt word-equal after the "
          "wrap")
    return 0


def check_pages_c(title, domes):
    """M6 Task 6, proof 4 (flow-pages-c, MVS, no coin/Start): a C press on
    MAME frames 450 and 550 turns the page 0 -> 1 -> 2 on those frames
    (within 2 frames), and title_t resets to 0 at each turn. With no BIOS
    logo the MVS title starts at ~frame 299, so page 0 spans ~299..592 —
    both C taps land inside it. The dome dumps at pages 0, 1, 2 prove the
    same whole sticky chain on every page (attract A2: the game's scene is
    drawn under the title)."""
    failures = []
    if not title:
        failures.append("no T records (is FLOW_PAGES_C set and the page "
                        "address right?)")
        return 1
    # the per-frame T records: find, for each tap frame, the first title
    # frame whose page differs from the previous one.
    taps = [450, 550, 650]
    for want_n, tap in enumerate(taps[:2]):
        prev = None
        got = None
        for n in sorted(title):
            if title[n][1] < 0:
                continue
            if n < tap - 4:
                prev = title[n][1]
                continue
            if prev is not None and title[n][1] != prev:
                got = (n, prev, title[n][1], title[n][2])
                break
            prev = title[n][1]
        if got is None:
            failures.append(f"C tap at frame {tap}: the page never changed "
                            "near it")
            continue
        n, a, b, t = got
        if not (tap <= n <= tap + 2):
            failures.append(f"C tap at frame {tap}: the page turned at "
                            f"frame {n} (must be within 2)")
        if (a, b) != (want_n, want_n + 1):
            failures.append(f"C tap at frame {tap}: the page went "
                            f"{a} -> {b}, expected {want_n} -> {want_n + 1}")
        if t != 0:
            failures.append(f"C tap at frame {tap}: title_t reads {t} "
                            "right after the turn, expected 0 (the reset)")
    # the dome dumps at the pages 0, 1, 2 PINs: the whole chain on each.
    if not domes:
        failures.append("no dome dumps on the pages-c run")
    else:
        seen_p0 = False
        for n in sorted(domes):
            _fc, cols, p = domes[n]
            if not (0 <= p < tm.PAGES):
                failures.append(f"dome dump at frame {n}: page unknown ({p})")
                continue
            if p == 0:
                seen_p0 = True
            # Attract Task A2: the dome is drawn as in play on every page,
            # so the C-turn pages 1 and 2 carry the whole sticky chain too.
            if cols[0][1] & 0x3f == 0:
                failures.append(f"page-{p} dome dump at frame {n}: the "
                                "driver SCB3 has height 0 (the dome is not "
                                "shown)")
            if not all(s3 & (1 << 6) and s3 & 0x3f == 0
                       for (_s2, s3, _s4) in cols[1:]):
                failures.append(f"page-{p} dome dump at frame {n}: the "
                                "followers do not carry the sticky bit with "
                                "no own height")
        if not seen_p0:
            failures.append("no page-0 dome dump on the pages-c run")
    if failures:
        print("FAIL flow-pages-c:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS flow-pages-c: C at 450 and 550 turned the page 0 -> 1 -> 2 "
          "on those frames (title_t reset to 0), the dome is drawn as in "
          "play on pages 1 and 2")
    return 0


def check_mvs(mvs_mode, mrecs, samples, title):
    """the M6 Task 2/3 MVS legs. mrecs: [(n, fc, flag, timer)] from the
    probe's M lines; samples: {n: (fc, rows)} from the F blocks. The
    confirmed numbers (2026-10-17) we assert: bios_mvs_flag == 0x80 all the
    way; a "Coin 1" hold on MAME frames 1500..1504 sets the compulsion timer
    to BCD 0x30; with no Start the BIOS's own player_start (countdown out)
    makes hud_framecnt 1 at frame 3312 (`flow-mvs`); with "1 Player Start"
    on 1800..1804 as well it becomes 1 at frame 1802 (`flow-mvs-start`). The
    M6 Task 3 proofs: the title's prompt row (21, attract A1) says INSERT
    COIN before the coin and PRESS START after it (each blinking, never the
    other), row 28 is blank before the coin and shows the BCD timer's digits
    after it, matching the timer byte read from RAM in the same frame."""
    failures = []
    if not mrecs:
        failures.append("probe wrote no MVS input records")
    else:
        # 1. the machine is MVS: bios_mvs_flag (0x10FD82) reads 0x80 from
        # frame 280 (the confirmed fact). Before the BIOS's RAM clear the
        # byte is leftover garbage, so only frames >= 280 are asserted.
        mvs_flag_recs = [(n, flag) for (n, _fc, flag, _t) in mrecs
                         if n >= 280]
        if not mvs_flag_recs:
            failures.append("no records from frame 280 on")
        elif not all(flag == 0x80 for (_n, flag) in mvs_flag_recs):
            bad = [n for (n, flag) in mvs_flag_recs if flag != 0x80]
            failures.append(f"bios_mvs_flag was not 0x80 on {len(bad)} "
                            f"frames from 280 on (first bad: {bad[0]})")
        # the timer starts counting down only once a coin has been inserted
        # (1500..1504); the pre-coin 0x00 bytes are part of the record.
        coin = [(n, fc, t) for (n, fc, f, t) in mrecs if n >= 1500 and t != 0]
        if not coin:
            failures.append("the compulsion timer never counted (no nonzero "
                            "byte from frame 1500 on) — was the coin seen?")
        else:
            # the first nonzero read must be the fresh BCD 0x30, within 5
            # frames of the coin hold (the hold spans 1500..1504, and the
            # BIOS samples the coin edge; we assert <= 1509).
            f = coin[0][0]
            if f > 1509:
                failures.append(f"timer first read {coin[0][2]:02x} only at "
                                f"frame {f}, expected within 5 of the coin "
                                "(<= 1509)")
            if coin[0][2] != 0x30:
                failures.append(f"timer read {coin[0][2]:02x} at frame {f}, "
                                "expected 0x30 (BCD 30 s) just after the coin")
        # the first game-session frame: fc >= 1. With the countdown alone the
        # BIOS's own player_start fires when the timer hits 0 (frame 3313 in
        # MAME); with the Start hold it fires on the hold (frame 1802). Only
        # frames >= 280 are considered: before the BIOS's RAM clear (and the
        # cart's .bss zeroing at main entry ~749) the fc word reads leftover
        # garbage and would masquerade as a game.
        mvs_from_280 = [(n, fc) for (n, fc, _f, _t) in mrecs if n >= 280]
        first = mvs_first_game_frame(mvs_from_280)
        if first is None:
            failures.append("the game never started (hud_framecnt never "
                            "reached 1)")
        else:
            lo, hi = ((1800, 1810) if mvs_mode == "flow-mvs-start"
                      else (3300, 3330))
            if not (lo <= first <= hi):
                failures.append(f"first game frame was MAME frame {first}, "
                                f"expected in [{lo}, {hi}]")
            if mvs_mode == "flow-mvs":
                # 2. the timer reached 0x01 (or 0x00) before the game began:
                # the countdown (not a Start press) is what started it.
                # only frames after the timer's first count: before the
                # coin it reads 0x00 too, which would pass trivially.
                pre = [t for (n, fc, _f, t) in mrecs
                       if fc == 0 and coin and n > coin[0][0]]
                if not any(t in (0x00, 0x01) for t in pre):
                    failures.append("the compulsion timer never reached 0x01 "
                                    "or 0x00 before the game started")

    # ---- M6 Task 3: the MVS title text and the countdown row ----
    # (applies to both MVS legs). The rows were sampled with the timer byte
    # read from RAM in the same frame (the probe's F blocks), so every count
    # here compares like with like: the title's drawn row 28 digits against
    # the very byte the BIOS wrote that frame. Only fc == 0 samples are
    # title frames: in the start leg the game begins at frame 1802 and
    # hud_clear blanks the title rows, so post-Start samples must not be
    # counted as title content.
    pre = {n: (fc, rows) for (n, (fc, rows)) in samples.items()
           if MVS_PRE_LO <= n <= MVS_PRE_HI}
    post = {n: (fc, rows) for (n, (fc, rows)) in samples.items()
            if MVS_POST_LO <= n <= MVS_POST_HI}
    timer_at = dict((n, t) for (n, _fc, _f, t) in mrecs)
    # M6 Task 6: the title's pages turn every 295 frames even before the
    # coin, so the prompt row (21, page 0 only) must be checked on page-0
    # frames. Attract Task A2 stages the rows for the next vblank, so the
    # drawn page/t are one frame behind the T record; derive them as
    # check_pages does (MVS has only automatic turns). Row 28's countdown
    # is page-independent and is checked on every page.
    page_at = dict((n, p) for (n, (_fc, p, _t, _c)) in title.items())
    t_at = dict((n, t) for (n, (_fc, _p, t, _c)) in title.items())
    def drawn_page(n):
        page = page_at.get(n, 0)
        t = t_at.get(n, 0)
        return (page - 1) % tm.PAGES if t == 0 else page
    r28_seen = []
    prompt_bad = []
    for n in sorted(post):
        fc, rows = post[n]
        if fc != 0:
            continue
        # the entry's first frames can still be blank (the scene/rows are
        # drawn over the entry's two vblanks); skip until a page is drawn.
        if rows[3] != ROW3 and rows[6].strip() not in PAGE_TITLES:
            continue
        # Attract Task A3: the demo's HUD row 26 is drawn under the title.
        if not hud_integ_present(rows[hm.HUD_INTEG_ROW]):
            failures.append(f"post-coin HUD row {hm.HUD_INTEG_ROW} at frame "
                            f"{n} is {rows[hm.HUD_INTEG_ROW]!r} (the demo's "
                            f"HUD is not drawn)")
        # M6 Task 6: page 0's prompt row alternates every 64 frames (t & 64)
        # between the prompt and "B TO CHANGE LEVEL"; the post-coin prompt
        # is PRESS START (the MVS countdown is live), never the "off" blank
        # of Task 3's blink. Pages 1..8 draw row 21 as a blank cap (their
        # empty line's cap) — the gate on page_at keeps the check on page 0.
        if drawn_page(n) == 0:
            r9 = rows[PROMPT_ROW]
            if r9 not in (ROW9_ON, ROW9_B):
                prompt_bad.append((n, r9))
        # the countdown, page-independent (HUD-layout Task 3: row 28 under
        # the dome; the probe reads it clean — the HUD rows are read last)
        digits = rows[28][ROW28_LO:ROW28_HI]
        if digits.strip():
            r28_seen.append((n, digits))
            # the drawn digits are exactly the timer byte read in the same
            # frame: high nibble then low nibble, '0' + n (the task's "R" —
            # the FIXMAP read back and the RAM read agree on every sampled
            # frame).
            # the staged commit writes the timer the previous frame read;
            # the probe's M lines have every frame, so compare with n-1.
            prev_timer = timer_at.get(n - 1)
            if prev_timer is not None and digits != "%02x" % prev_timer:
                failures.append(f"row 28 shows {digits!r} at frame {n} but "
                                f"the previous frame's compulsion timer "
                                f"reads {prev_timer:02x}")
        # Attract Task A3: row 28 is the demo's score/lives row, with only
        # cols 19..20 replaced by the countdown. The exact score/lives are
        # check_demo.py's proof; here require the countdown to own exactly
        # those cells and the demo's row to stay drawn around them.
        around = rows[28][:ROW28_LO] + rows[28][ROW28_HI:]
        if not around.strip():
            failures.append(f"post-coin row 28 at frame {n} lost the demo's "
                            f"score/lives around the countdown: "
                            f"{rows[28]!r}")
    seen_coin, seen_b = False, False
    for n, (fc, rows) in sorted(pre.items()):
        if rows[3] != ROW3 and rows[6].strip() not in PAGE_TITLES:
            continue
        # M6 Task 6: pre-coin (credits 1) prompt row 21 alternates INSERT
        # COIN with "B TO CHANGE LEVEL" every 64 frames, on page 0 only.
        if drawn_page(n) != 0:
            continue
        if rows[PROMPT_ROW] == ROW9_COIN:
            seen_coin = True
        elif rows[PROMPT_ROW] == ROW9_B:
            seen_b = True
        else:
            failures.append(f"pre-coin prompt row {PROMPT_ROW} at frame "
                            f"{n}: {rows[PROMPT_ROW]!r}")
        # Attract Task A3: before a coin the countdown is off and the
        # demo's HUD rows are drawn (exact values are check_demo.py's).
        if not hud_integ_present(rows[hm.HUD_INTEG_ROW]):
            failures.append(f"pre-coin HUD row {hm.HUD_INTEG_ROW} at frame "
                            f"{n} is {rows[hm.HUD_INTEG_ROW]!r} (the demo's "
                            f"HUD is not drawn)")
        if not any(ch.isdigit() for ch in rows[28]):
            failures.append(f"pre-coin row 28 at frame {n} is {rows[28]!r} "
                            f"(the demo's score/lives row is not drawn)")
    if not seen_coin:
        failures.append(f"the pre-coin title never showed 'INSERT COIN' on "
                        f"row {PROMPT_ROW}")
    if not seen_b:
        failures.append(f"the pre-coin title never showed 'B TO CHANGE "
                        f"LEVEL' on row {PROMPT_ROW} (the t & 64 alternation)")
    if not post:
        failures.append("no post-coin title rows were sampled")
    for n, r9 in prompt_bad:
        failures.append(f"post-coin prompt row {PROMPT_ROW} at frame {n}: "
                        f"{r9!r}")
    # the countdown row must show at least 20 different digit pairs — the
    # task's count for the flow-mvs leg, whose window 1530..3300 spans the
    # timer's whole BCD run (0x30 down to 0x00, 31 distinct seconds, sampled
    # every 6 frames). The start leg begins a game at frame 1802, so its
    # title row only lives for ~13 seconds of countdown (26..30); the
    # same-frame digit check above still proves its drawing.
    if mvs_mode == "flow-mvs" and len(set(d for (_n, d) in r28_seen)) < 20:
        failures.append(f"the countdown row showed only "
                        f"{len(set(d for (_n, d) in r28_seen))} different "
                        "digit pairs (need >= 20: the BCD timer 0x30 down to "
                        "0x00)")
    if failures:
        print(f"FAIL {mvs_mode}:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    first = mvs_first_game_frame([(n, fc) for (n, fc, _f, _t) in mrecs
                                  if n >= 280])
    print(f"PASS {mvs_mode}: MVS flag 0x80, compulsion timer 0x30 after the "
          f"coin counting down to 0, game began at MAME frame {first}; "
          f"title prompt row {PROMPT_ROW} INSERT COIN then PRESS START "
          f"(each blinking), row 28 shows the timer's digits on all "
          f"{len(r28_seen)} sampled frames "
          f"({len(set(d for (_n, d) in r28_seen))} different values)")
    return 0


def check_mvs_norestart(nrs, mrecs, samples):
    """the M6 Task 4 leg (flow-mvs-norestart): on MVS, A at GAME OVER does
    nothing — the 295-frame A-restart window (the rules' rules_begin A
    check, gated off by flow.c) must never open — and the return to the
    title still happens when the session window expires. nrs: [(n, fc,
    lives, game_over, mod1)] from the probe's R lines (the rules' bytes at
    their confirmed m68k offsets, plus bios_player_mod1); mrecs: the M
    lines; samples: the F blocks (the post-return title rows).

    The confirmed numbers (2026-10-17 / model): the coin at 1500 and the
    Start hold at 1800 begin the game at MAME frame 1802; held Up from the
    first game frame is the hud probe's game 1, GAME OVER at fc 16551
    under Task 1's seed 0xadf9 (6509 with RNG_SEED); the
    A tap at GAME OVER + 60 .. +64 must change nothing; the 295-frame
    session window then expires and the cart returns to the title (the
    plan's GAME_OVER_WAIT 295 = 250 Vectrex frames x 59/50)."""
    failures = []
    if not nrs:
        failures.append("probe wrote no Task 4 game-state records (the R "
                        "lines) — is FLOW_NORESTART set and FLOW_RULES_ADDR "
                        "nonzero?")
        return 1
    if not mrecs:
        failures.append("probe wrote no MVS input records")
    if not any(flag == 0x80 for (_n, _fc, flag, _t) in mrecs):
        failures.append("bios_mvs_flag was never 0x80 (not an MVS run?)")

    # 1. the game really began (the Start at 1800, frame 1802) and reached
    # GAME OVER at fc 16551 under Task 1's seed 0xadf9 with the Up-held
    # policy (the R records key on
    # fc, so the first fc >= 1 is the game start; the game-over marker is
    # the GO line's fc.
    # the MAME notifier can catch the first game frame after hud_frame has
    # already advanced to fc 2 (the cart may run one frame between two
    # notifier ticks); the game demonstrably began either way.
    if nrs[0][1] not in (1, 2):
        failures.append(f"first game frame was fc {nrs[0][1]}, expected 1..2")
    go = None
    for n, fc, lives, go_, mod1 in nrs:
        if go_:
            go = (n, fc, lives, go_, mod1)
            break
    if go is None:
        failures.append("GAME OVER was never seen (expected at the model's "
                        "fc 16551 under Task 1's seed 0xadf9)")
        return 1
    go_fc = go[1]
    go_row_bad = gameover_rows_failures(samples, go)
    failures.extend(go_row_bad)
    if not go_row_bad:
        print(f"GAME OVER rows 7/8 at the sampled frame {go[0]} equal the "
              f"model (thick text + its cap)")
    if not (16521 <= go_fc <= 16581):
        failures.append(f"GAME OVER came at fc {go_fc}, expected the "
                        "model's ~16551 (the Up-held MVS game under "
                        "Task 1's seed 0xadf9)")
    # the A tap at GAME OVER + 60 .. +64 must have been pressed (the probe
    # drives it; without a game-over marker it could not have) — the proof
    # is in the state that follows, below.

    # 2. from GAME OVER on, the lives stay 0 and rules.game_over stays set
    # until the return: the A-restart never ran. The window is fc
    # [go_fc, go_fc + 295); the first R record whose game_over byte is
    # clear (a new game) must be beyond it. Between GAME OVER and the
    # return every recorded frame has game_over set with lives 0; BIOS-side
    # writes (like an A-restart's new_game) are the only way they could
    # change.
    early_restart = None
    for n, fc, lives, go_, mod1 in nrs:
        if fc < go_fc:
            continue
        if not go_:
            early_restart = (n, fc, lives, go_, mod1)
            break
        if lives != 0:
            failures.append(f"frame {n} (fc {fc}): lives {lives} != 0 under "
                            "GAME OVER — the A-restart ran (it sets 3)")
            break
    if early_restart is not None:
        failures.append(f"the A-restart ran on MVS at fc {early_restart[1]} "
                        f"(game_over cleared, lives {early_restart[2]}) — "
                        "A at GAME OVER must do nothing on MVS")
    # the window really expired: some R record past GAME OVER + 295 exists
    # with the game still over (so the mod1-cleared return below is a real
    # expiry, not the MAME run ending early).
    past = [r for r in nrs if r[1] >= go_fc + GAME_OVER_WAIT]
    if not past:
        failures.append(f"no game-state records past GAME OVER + "
                        f"{GAME_OVER_WAIT} — the run was too short to watch "
                        "the 295-frame window expire")

    # 3. bios_player_mod1 reads 0 at GAME OVER + 295..+300 (the return to
    # the title path: flow_run sets bios_player_mod1 = 0 before returning).
    mod0 = None
    for n, fc, lives, go_, mod1 in nrs:
        if mod1 == 0 and go_fc + GAME_OVER_WAIT <= fc <= go_fc + GAME_OVER_WAIT + 5:
            mod0 = (n, fc, mod1)
            break
    if mod0 is None:
        failures.append("bios_player_mod1 never read 0 within "
                        f"[GAME OVER+{GAME_OVER_WAIT}, +{GAME_OVER_WAIT}+5] "
                        "(the return to the title never happened)")
    else:
        # the title rows are back by GAME OVER + 600: a sampled post-return
        # frame (fc 0, either row 3 = the title's "E-SRG" on page 0, or the
        # drawn HIGH SCORES text on row 6 — the M6 Task 7 return opens on
        # page 2) within 600 MAME frames of GAME OVER. The probe samples
        # the post-return title from MAME frame GO + 290 every 6 frames;
        # the ~200-frame BIOS rebuild after the return sits inside the 600
        # bound.
        back = None
        for n2 in sorted(samples):
            if n2 < mod0[0]:
                continue
            fc, rows = samples[n2]
            if fc != 0:
                continue
            if rows[3] == ROW3 or rows[6].strip() in (
                    "HIGH SCORES", "CONTROLS", "DEFEND THE DOME",
                    "LEVELS", "RADAR", "CREDITS", "BUILT WITH"):
                back = (n2, rows)
                break
        if back is None:
            failures.append("the title rows never came back after the "
                            "window expired (no fc 0 title sample)")
        else:
            if back[0] - go[0] > 600:
                failures.append(f"the title returned {back[0] - go[0]} MAME "
                                "frames after GAME OVER; need within 600")
            # M6 Task 7 / B3: the returned title opens on the played level's
            # whose prompt row 21 is a blank cap — only a page-0 return
            # shows the prompt on row 21.
            if back[1][6].strip() == "HIGH SCORES":
                pass
            else:
                for r9 in (back[1][PROMPT_ROW],):
                    if r9 not in (ROW9_ON, ROW9_COIN, ROW9_B):
                        failures.append(f"post-return prompt row "
                                        f"{PROMPT_ROW}: {r9!r}")
    if failures:
        print("FAIL flow-mvs-norestart:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    first = mvs_first_game_frame([(n, fc) for (n, fc, _f, _t) in mrecs
                                  if n >= 280])
    print(f"PASS flow-mvs-norestart: game began at MAME frame {first}, "
          f"GAME OVER at fc {go_fc}, A at GAME OVER + 60 did not restart "
          f"(lives 0, game_over set to the return), bios_player_mod1 0 at "
          f"fc {mod0[1]}, title back {back[0] - go[0]} MAME frames after "
          "GAME OVER")
    return 0


def mvs_first_game_frame(records):
    """the first MAME frame whose record shows hud_framecnt (fc) >= 1."""
    for n, fc, *_ in records:
        if fc >= 1:
            return n
    return None


# ---- M6 Task 7: level select (B), the level in backup RAM, and the HIGH
# SCORES return (modes flow-level and flow-return) ----

# page 0's level-name row (HUD-layout Task 3: row 7), drawn by the title
# from flow_level: the checker reads the SAME byte from RAM (the L records)
# and compares the drawn row 7 against the centred level name — the
# drawn-vs-drawn check that closes the loop without assuming BTN mapping
# details.
REV = {0: "EASY", 1: "NORMAL", 2: "HARD"}


def _row5_is(rows, level):
    want = " " * ((40 - len(REV[level])) // 2) + REV[level] + \
        " " * (40 - len(REV[level]) - (40 - len(REV[level])) // 2)
    return rows[LEVEL_ROW] == want


def sanitized_levels(levels):
    """the levels dict (n -> (fc, valid, raw)) as the cart's flow_level_get
    sees it: (n, fc, sanitized) for the frames the probe sampled. The
    sanitize mirrors src/flow.c — a level byte is only used when the VALID
    marker matches and the byte is 0..2; otherwise (fresh/garbage backup
    RAM, e.g. the 0x00 bytes of a new MVS board) it is NORMAL (1). The
    checker compares the drawn row 5 against THIS value, the very byte the
    cart drew with."""
    MAGIC = 0x53
    out = {}
    for n in sorted(levels):
        fc, valid, raw = levels[n]
        lv = raw if (valid == MAGIC and raw <= 2) else 1
        out[n] = (fc, lv)
    return out


# ---- high-score boards Task B2: the backup-RAM board (flow_board) ----

# high-score boards Task B2: the board's 126-byte image, exactly as
# src/board.c lays it out (tests/board_model.py): u32 magic 'ESR2' at 0,
# 3 levels x 5 entries of init[3] + pad + u32 score10, u16 sum at 124.
def board_from_hex(hexbytes):
    """the probe's B record as a board_model.Board, or None if the image is
    not 126 bytes / not hex."""
    if len(hexbytes) != bm.BYTES * 2:
        return None
    try:
        board = bm.Board()
        board.load(" ".join(hexbytes[i:i + 2]
                            for i in range(0, len(hexbytes), 2)))
        return board
    except (ValueError, AssertionError):
        return None


def board_valid(hexbytes):
    """1 if the probe's image passes board_valid(), else 0."""
    board = board_from_hex(hexbytes)
    return 0 if board is None else board.valid()


def board_top(board_or_hex, level):
    """the level's top entry score10 (entry 0) from a Board or a B hex."""
    board = board_or_hex
    if not isinstance(board, bm.Board):
        board = board_from_hex(board_or_hex)
    if board is None:
        return None
    return board.entry(level, 0)[2]


def board_inserted_at(board, level, score10, init=b"   "):
    """the rank of a board entry with the given score10 and initials (the
    three spaces B2 stores), or None."""
    for e in range(bm.NENTRIES):
        got_init, _pad, got_score = board.entry(level, e)
        if got_init == init and got_score == score10:
            return e
    return None


# the pages 1..10 title headers (pages[4..10][0] plus the boards' row 6
# "HIGH SCORES"), used to recognise a drawn non-page-0 title without relying
# on the RAM page byte alone (the BIOS preamble leaves page 0 in RAM and
# blank rows; the drawn text is the truth).
PAGE_TITLES = ("HIGH SCORES", "CONTROLS", "DEFEND THE DOME", "LEVELS",
               "RADAR", "CREDITS", "BUILT WITH")
# high-score boards Task B2/B3: the five defaults put the same top score10
# on every level (50,000 points); a fresh AES boot (the flow-pages leg) draws
# these on page 0's row 9 and the board pages' entries.
DEFAULT_BOARD_TOPS = [bm.DEFAULTS[0][1]] * bm.NLEVELS
DEFAULT_BOARD = bm.Board()


def board_at(n, bests):
    """the board whose B record was read in the same frame (Task B2's
    flow_board image); the fresh-boot defaults when the probe did not dump
    one on that frame."""
    if n in bests:
        b = board_from_hex(bests[n][4])
        if b is not None:
            return b
    return DEFAULT_BOARD


def title_frame_ok(n, rows, title):
    """is (n, rows) a REAL title sample? fc 0, and either the drawn
    page-0 row 3 is "E-SRG" or the T record's page is 1..8 with a drawn
    page header on row 6 (the BIOS preamble's blank rows / stale page 0
    are rejected)."""
    if rows[3] == ROW3:
        return True
    if n in title and 1 <= title[n][1] < tm.PAGES:
        return rows[6].strip() in PAGE_TITLES
    return False


def drawn_title(n, title):
    """Attract Task A2: the page/t that produced the drawn rows. The title
    staging runs after the vblank's commit, so the fix layer is one title
    frame behind the T record: t-1, and on a turn (t 0) the previous page's
    last frame. The title legs have only automatic turns (no B/C), so the
    previous page is page-1 mod 11."""
    if n not in title:
        return None
    _fc, page, t, cred = title[n]
    if t == 0:
        return (page - 1) % tm.PAGES, TITLE_PAGE_FRAMES - 1, cred
    return page, t - 1, cred


def drawn_title_ok(n, rows, title):
    """is (n, rows) a drawn title frame, recognised by the drawn page
    itself (not the T record's page, which is one frame ahead)?"""
    st = drawn_title(n, title)
    if st is None:
        return False
    page = st[0]
    if page == 0:
        return rows[3] == ROW3
    return rows[6].strip() == \
        tm.title_rows(page, 1, 0, DEFAULT_BOARD, 0)[6].strip()


def check_best_mvs(mvs_records, samples, title, levels, bests, scores, go,
                   nvram_leg=1):
    """high-score boards Task B2, the MVS backup-RAM proof (best-mvs, four
    MVS runs):
    - run 1 (nvram_leg 1): the aiming game to GAME OVER (coin at 1500, Start
      at 1800), mis.score10 > the default 5th entry (10,000 points, score10
      1000) at GAME OVER, the returned title opens on page 2 (NORMAL's
      whose NORMAL row reads the board's top entry x 10, and flow_board in
      RAM is valid and holds the game's entry (three spaces) at its rank.
    - run 2 (nvram_leg 2, sharing run 1's nvram): the FIRST page-0 frame's
      row reads the persisted board's top entry before any game, and the
      board still holds run 1's three-space entry (not the defaults).
    - run 3 (nvram_leg 3, reusing the nvram with the saved magic patched to
      the old 'ESRG'): board_valid rejects it, so the entry starts from the
      five defaults.
    - run 4 (nvram_leg 4, a fresh nvram): the first page-0 frame reads the
      default board — no garbage, no crash.
    The drawn rows are compared against title_model with the board's top
    entries read in the same frame (mutation: pass zeros to title_rows
    fails every title frame; never insert fails run 1's three-space entry;
    reset on every entry fails run 2's persisted entry)."""
    failures = []
    go_row_bad = gameover_rows_failures(samples, go)
    failures.extend(go_row_bad)
    if not go_row_bad and go is not None:
        print(f"GAME OVER rows 7/8 at frame {go[0]} equal the model")
    if not mvs_records:
        failures.append("probe wrote no MVS input records")
        return 1
    if not any(flag == 0x80 for (_n, _fc, flag, _t) in mvs_records):
        failures.append("bios_mvs_flag was never 0x80 (not an MVS run?)")
    if not samples:
        failures.append("no fix-row samples")
    if not bests:
        failures.append("no B records (flow_board never read)")
    if failures:
        print("FAIL best-mvs:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    # the first page-0 title frame (fc 0, T record page 0) and its B
    # record. Page 0's row 9 draws the board's top entry for the title's
    # level x 10 — NORMAL (1) on a fresh entry. Every leg proves the drawn
    # rows equal title_model's with the board tops and the same frame's
    # level (this is what a zeros mutation breaks).
    first_p0 = None
    for n4 in sorted(samples):
        fc, rows4 = samples[n4]
        if fc != 0 or n4 not in title:
            continue
        if title[n4][1] == 0 and title_frame_ok(n4, rows4, title):
            first_p0 = (n4, rows4)
            break
    if first_p0 is None:
        failures.append("no page-0 title frame sampled (the board's top "
                        "entry never observed)")
    # the model-vs-drawn compare on every REAL title frame: the drawn
    # rows must equal title_model's for the board's top entries, the level
    # (from the same frame's L record, sanitized as flow_level_get does)
    # and the T record's page/t/credits.
    for n6 in sorted(bests):
        if n6 not in samples:
            continue
        fc6, rows6 = samples[n6]
        if fc6 != 0 or n6 not in title:
            continue
        if not drawn_title_ok(n6, rows6, title):
            continue
        _p6, _t6, _c6 = drawn_title(n6, title)
        _bfc, bb0, bb1, bb2, hexb6 = bests[n6]
        if not board_valid(hexb6):
            failures.append(f"title frame {n6}: flow_board is not valid "
                            f"({hexb6!r})")
            continue
        lv = 1
        if n6 in levels:
            _lfc, valid, raw = levels[n6]
            if valid == 0x53 and raw <= 2:
                lv = raw
        want6 = tm.title_rows(_p6, lv, _t6, board_at(n6, bests), _c6)
        for r in range(TITLE_ROWS):
            # Attract Task A2: row 26 is the HUD's integrity, drawn under
            # the title, not a title row.
            if r == hm.HUD_INTEG_ROW:
                continue
            # row 28 is the one row title_rows never fills (the MVS
            # countdown, flow.c, owns it — the model leaves it blank, and
            # on MVS post-coin the drawn digits are the countdown's, not a
            # model row); the checker compares it separately (check_mvs).
            # Every other model row 0..27 must match exactly, whatever the
            # page (page 0's prompt sits on row 21 and IS in the model).
            if r == 28:
                continue
            if rows6[r] != want6[r]:
                failures.append(f"title frame {n6} (page {_p6}): "
                                f"row {r} != title_model with the "
                                f"board tops ({bb0},{bb1},{bb2}) and "
                                f"level {lv}, t {_t6}")
                break

    if nvram_leg == 1:
        # ---- run 1: the full game proof ----
        # The aiming game (Left held, A only when a missile is aligned)
        # ends at the measured fc around 25978 under Task 1's seed
        # 0xadf9; the window only has to hold the measured run.
        if go is None:
            failures.append("GAME OVER was never seen (expected after fc "
                            "~25978 under Task 1's seed 0xadf9)")
            return 1 if failures else 0
        go_fc = go[1]
        if not (23000 <= go_fc <= 29000):
            failures.append(f"GAME OVER came at fc {go_fc}, expected ~25978 "
                            "(the aiming MVS game under Task 1's seed)")
        first = mvs_first_game_frame([(n, fc) for (n, fc, _f, _t)
                                      in mvs_records if n >= 280])
        if first is None or not (1795 <= first <= 1810):
            failures.append(f"first game frame was MAME frame {first}, "
                            "expected ~1802 (coin at 1500, Start at 1800)")
        if not scores:
            failures.append("no SC records (mis.score10 never read at GAME "
                            "OVER)")
            sc10 = 0
        else:
            _n, sc10 = scores[sorted(scores)[0]]
            if sc10 <= bm.DEFAULTS[bm.NENTRIES - 1][1]:
                failures.append(f"mis.score10 at GAME OVER reads {sc10}, "
                                f"expected > {bm.DEFAULTS[bm.NENTRIES - 1][1]} "
                                "(above the default 5th entry)")
        # the returned title: a real drawn title sample at/after the
        # return (the probe plays the game from ~1802 and starts sampling
        # the post-return title at GO + 290 MAME frames; the return lands
        # at fc GO+295, so the first real title sample at/after
        # go[0] + 280 is the high-scores return — the pre-coin title
        # samples 900..1499 must not be picked).
        back = None
        for n2 in sorted(samples):
            if n2 < go[0] + 280:
                continue
            fc, rows = samples[n2]
            if fc != 0 or n2 not in title:
                continue
            if not title_frame_ok(n2, rows, title):
                continue
            if 1 <= title[n2][1] < tm.PAGES:
                back = (n2, rows)
                break
        if back is None:
            failures.append("no post-return title rows sampled on a "
                            "page-1..10 title frame")
        else:
            n2, rows = back
            page = title[n2][1]
            if page != 2:
                failures.append(f"the returned title opened on page "
                                f"{page}, expected 2 (NORMAL's board page)")
            _t, _c = title[n2][2], title[n2][3]
            # the board check keys on the returned title's B record (the
            # GO frame's B was read a tick before the cart's update landed
            # — the probe reads RAM at the start of the MAME frame).
            board = board_from_hex(bests[n2][4])
            if board is None or not board.valid():
                failures.append(f"flow_board at frame {n2} is not valid "
                                f"({'' if board is None else bests[n2][4]!r})")
            else:
                init, _pad, top = board.entry(1, 0)
                line = tm.entry_line(0, init, top)
                want_row = " " * ((40 - len(line)) // 2) + line + \
                    " " * (40 - len(line) - (40 - len(line)) // 2)
                if rows[11] != want_row:
                    failures.append(f"returned title frame {n2}: row 11 "
                                    f"(NORMAL's top entry) is {rows[11]!r}, "
                                    f"expected {want_row!r}")
                rank = board_inserted_at(board, 1, sc10)
                if rank is None:
                    failures.append(f"flow_board has no NORMAL entry with "
                                    f"score10 {sc10} and three spaces (the "
                                    "game's qualifying score was not "
                                    "inserted)")
                if board_inserted_at(board, 0, sc10) is not None \
                   or board_inserted_at(board, 2, sc10) is not None:
                    failures.append("the game's three-space entry landed "
                                    "on a level other than NORMAL")
                if board.bytes126() == bm.Board().bytes126():
                    failures.append("flow_board is still the default board "
                                    "after the game (nothing was inserted)")
            # the drawn board-page rows equal the model's, with the board
            # from the same frame's B record (post-return samples only)
            for n3 in sorted(bests):
                if n3 not in samples or n3 < go[0] + 280:
                    continue
                fc3, rows3 = samples[n3]
                if fc3 != 0 or n3 not in title:
                    continue
                if not drawn_title_ok(n3, rows3, title):
                    continue
                _p3, _t3, _c3 = drawn_title(n3, title)
                _bfc, bb0, bb1, bb2, _hexb = bests[n3]
                want3 = tm.title_rows(_p3, 1, _t3, board_at(n3, bests), _c3)
                for r in range(TITLE_ROWS):
                    if r == hm.HUD_INTEG_ROW:
                        continue         # attract A2: the HUD's row 26
                    if r == 28:
                        continue         # row 28 is the MVS countdown (flow.c)
                    if rows3[r] != want3[r]:
                        failures.append(f"returned title frame {n3}: row "
                                        f"{r} != title_model page {_p3} with "
                                        f"the board tops ({bb0},{bb1},{bb2}), "
                                        f"t {_t3}")
                        break
    elif nvram_leg == 2:
        # ---- run 2: the persisted board (shares run 1's nvram) ----
        # nothing may have started a game: the run's fc stays 0, and the
        # first page-0 frame's row 9 shows the board's NORMAL top entry.
        # The compare above already proved the drawn rows == the board;
        # here the board itself must still hold run 1's three-space entry
        # (a reset-on-entry mutation would restore the defaults).
        if any(fc >= 1 for (_fc, _rows) in samples.values()):
            failures.append("run 2 started a game (fc >= 1); only the "
                            "title may run")
        if first_p0 is None or first_p0[0] not in bests:
            failures.append("run 2 has no B record on its first page-0 "
                            "frame")
        else:
            board = board_from_hex(bests[first_p0[0]][4])
            if board is None or not board.valid():
                failures.append("run 2's flow_board is not valid")
            else:
                spaces = [e for e in range(bm.NENTRIES)
                          if board.entry(1, e)[0] == b"   "]
                if not spaces:
                    failures.append("run 2's flow_board has no three-space "
                                    "NORMAL entry (run 1's game did not "
                                    "persist)")
                if board.bytes126() == bm.Board().bytes126():
                    failures.append("run 2's flow_board is the default "
                                    "board (the persisted game entry was "
                                    "lost)")
    elif nvram_leg in (3, 4):
        # ---- run 3: the old 'ESRG' magic; run 4: a fresh nvram ----
        # both must start from the five defaults.
        if any(fc >= 1 for (_fc, _rows) in samples.values()):
            failures.append(f"run {nvram_leg} started a game (fc >= 1); "
                            "only the title may run")
        if first_p0 is None or first_p0[0] not in bests:
            failures.append(f"run {nvram_leg} has no B record on its first "
                            "page-0 frame")
        else:
            board = board_from_hex(bests[first_p0[0]][4])
            if board is None or not board.valid():
                failures.append(f"run {nvram_leg}'s flow_board is not valid")
            elif board.bytes126() != bm.Board().bytes126():
                failures.append(f"run {nvram_leg}'s flow_board is not the "
                                "default board (an old/invalid table was "
                                "not reset)")
            top = board_top(board, 1)
            if top != bm.DEFAULTS[0][1]:
                failures.append(f"run {nvram_leg}'s NORMAL top entry reads "
                                f"{top}, expected the default "
                                f"{bm.DEFAULTS[0][1]}")
    if failures:
        print("FAIL best-mvs:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    if nvram_leg == 1:
        print(f"PASS best-mvs (run 1): game began at MAME frame {first}, "
              f"GAME OVER at fc {go_fc} with mis.score10 {sc10}; the "
              "returned title opens on page 2 (NORMAL's board page) whose "
              "row 11 reads the board's top entry; flow_board in RAM is "
              "valid and holds the game's three-space entry")
    elif nvram_leg == 2:
        print("PASS best-mvs (run 2): with run 1's nvram, the first "
              "page-0 frame reads the persisted board and its three-space "
              "NORMAL entry before any game")
    elif nvram_leg == 3:
        print("PASS best-mvs (run 3): with the saved magic patched to the "
              "old 'ESRG', the entry starts from the five defaults")
    else:
        print("PASS best-mvs (run 4): with a fresh nvram, the first "
              "page-0 frame reads the five defaults (no garbage, no crash)")
    return 0


def check_best_aes(samples, title, levels, bests, scores, go, cards,
                   card_leg=1):
    """high-score boards Task B2, the AES memory-card proof (best-aes, four
    AES runs):
    - run 1 (card_leg 1): the aiming game to GAME OVER (Start at 600..604;
      measured fc ~28348 under Task 1's seed 0xaede), mis.score10 above the
      default 5th entry; the card-log answers are 0x81 (the fresh card is
      unformatted), then FORMAT 0, then SAVE 0; the returned title opens on
      page 2 (NORMAL's board page) whose row 11 reads the board's top entry,
      and flow_board in RAM is valid and holds the game's three-space
      entry.
    - run 2 (card_leg 2, sharing run 1's -memcard file with a FRESH
      nvram/cfg — a power-off): the load answers 0 (the card is now
      formatted and holds the save), and the board (including the game's
      three-space entry) is back before any game — the card, not the
      per-boot backup RAM, kept it.
    - run 3 (card_leg 3, reusing the card with the saved magic patched to
      the old 'ESRG'): the load answers 0 but board_valid rejects it, so the
      entry starts from the five defaults.
    - run 4 (card_leg 4, no -memcard): the load answers 0x80, the first
      page-0 frame reads the default board, no crash; and the game to GAME
      OVER still keeps the board in backup RAM for that run (flow_board in
      RAM holds the entry, and page 2's NORMAL board row shows the top).
    The checks are keyed so each task's mutation fails one: never save —
    run 1's board has no game entry; never load — run 2's board is the
    defaults; skip the FORMAT retry on 0x81 — run 1's A records lack the
    FORMAT / second SAVE."""
    failures = []
    go_row_bad = gameover_rows_failures(samples, go)
    failures.extend(go_row_bad)
    if not go_row_bad and go is not None:
        print(f"GAME OVER rows 7/8 at frame {go[0]} equal the model")
    if not samples:
        failures.append("no fix-row samples")
    if not bests:
        failures.append("no B records (flow_board never read)")
    if card_leg in (1, 4) and not scores:
        # runs 1 and 4 play a game to GAME OVER whose mis.score10 is the
        # proof's score; runs 2/3 (the title-only persistence runs) never
        # play, so they have no SC record by design
        failures.append("no SC record (mis.score10 at GAME OVER never "
                        "read)")
    if card_leg in (2, 3) and go is not None:
        failures.append(f"run {card_leg} started a game (fc >= 1, GO seen); "
                        "only the title may run")
    if failures:
        print("FAIL best-aes:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    # the first page-0 title frame (fc 0, T record page 0 and the drawn
    # title), and its B/A records. Page 0's row 9 draws the board's top
    # entry x 10 for the title's level — NORMAL (1) on a fresh entry.
    first_p0 = None
    for n4 in sorted(samples):
        fc, rows4 = samples[n4]
        if fc != 0 or n4 not in title or title[n4][1] != 0:
            continue
        if title_frame_ok(n4, rows4, title):
            first_p0 = (n4, rows4)
            break
    if first_p0 is None:
        failures.append("no page-0 title frame sampled (the board's top "
                        "entry never observed)")

    # the model-vs-drawn compare on every REAL title frame: the drawn
    # rows must equal title_model's for the board's top entries, the level
    # (same frame's L record, sanitized as flow_level_get does) and the T
    # record's page/t/credits.
    for n6 in sorted(bests):
        if n6 not in samples:
            continue
        fc6, rows6 = samples[n6]
        if fc6 != 0 or n6 not in title:
            continue
        if not drawn_title_ok(n6, rows6, title):
            continue
        _p6, _t6, _c6 = drawn_title(n6, title)
        _bfc, bb0, bb1, bb2, hexb6 = bests[n6]
        if not board_valid(hexb6):
            failures.append(f"title frame {n6}: flow_board is not valid "
                            f"({hexb6!r})")
            continue
        lv = 1
        if n6 in levels:
            _lfc, valid, raw = levels[n6]
            if valid == 0x53 and raw <= 2:
                lv = raw
        want6 = tm.title_rows(_p6, lv, _t6, board_at(n6, bests), _c6)
        for r in range(TITLE_ROWS):
            if r == hm.HUD_INTEG_ROW:
                continue
            if rows6[r] != want6[r]:
                failures.append(f"title frame {n6} (page {_p6}): "
                                f"row {r} != title_model with the "
                                f"board tops ({bb0},{bb1},{bb2}) and "
                                f"level {lv}, t {_t6}")
                break

    # the card-log answers, from the A records. The probe samples the log
    # every frame from GO + 2 while the session is still running (the
    # BIOS card calls span several frames); the LAST A record with a
    # LOAD in it before the return carries the complete sequence.
    # (BIOS-preamble title samples read the .data garbage 0:0,0:0,...
    # before the cart's first entry re-copies card_log — those have no
    # LOAD command and are ignored.) Runs 2/3/4 only ever make the entry
    # LOAD, so their first LOAD-bearing record is the evidence.
    log_pairs = []
    if cards:
        load_recs = [n7 for n7 in cards
                     if any(c == 2 for (c, _a) in cards[n7][1])]
        if load_recs:
            if card_leg == 1:
                log_pairs = cards[max(load_recs)][1]
            else:
                log_pairs = cards[min(load_recs)][1]

    if card_leg == 1:
        # the fresh card's book: the entry LOAD answers 0x81 (the card is
        # unformatted), and the GAME OVER save answers 0x81, FORMAT 0,
        # then SAVE 0 — exactly the confirmed sequence, recorded in
        # card_log's pairs.
        if not log_pairs:
            failures.append("no card-log A records (the save's answers "
                            "never read)")
        elif log_pairs != [(2, 0x81), (3, 0x81), (0, 0), (3, 0)]:
            failures.append(f"run 1's card-log pairs are "
                            f"{[(hex(c), hex(a)) for (c, a) in log_pairs]}, "
                            "expected LOAD 2:81, SAVE 3:81, FORMAT 0:0, "
                            "SAVE 3:0 (fresh card: the save retried after "
                            "FORMAT)")
    elif card_leg in (2, 3):
        load_ans = next((a for (c, a) in log_pairs if c == 2), None)
        if load_ans != 0:
            failures.append(f"run {card_leg}'s load answer is {load_ans}, "
                            "expected 0 (the card holds run 1's save)")
    else:
        load_ans = next((a for (c, a) in log_pairs if c == 2), None)
        if load_ans != 0x80:
            failures.append(f"run 4's load answer is {load_ans}, expected "
                            "0x80 (no card inserted)")

    if card_leg == 1:
        # ---- run 1: the full game proof ----
        # The aiming game (Left held, A only when a missile is aligned)
        # ends at the measured fc around 28348 under Task 1's seed 0xaede.
        if go is None:
            failures.append("GAME OVER was never seen (expected after fc "
                            "~28348 under Task 1's seed 0xaede)")
        if failures:
            print("FAIL best-aes:")
            for f_ in failures:
                print("  - " + f_)
            return 1
        go_fc = go[1]
        if not (25000 <= go_fc <= 31000):
            failures.append(f"GAME OVER came at fc {go_fc}, expected "
                            "~28348 (the aiming AES game under Task 1's "
                            "seed)")
        _n, sc10 = scores[sorted(scores)[0]]
        if sc10 <= bm.DEFAULTS[bm.NENTRIES - 1][1]:
            failures.append(f"mis.score10 at GAME OVER reads {sc10}, "
                            f"expected > {bm.DEFAULTS[bm.NENTRIES - 1][1]} "
                            "(above the default 5th entry)")
        # the returned title: a real drawn title sample at/after the
        # return (GAME OVER + the 295-frame window, in MAME frames)
        back = None
        for n2 in sorted(samples):
            if n2 < go[0] + 250:
                continue
            fc, rows = samples[n2]
            if fc != 0 or n2 not in title:
                continue
            if not title_frame_ok(n2, rows, title):
                continue
            back = (n2, rows)
            break
        if back is None:
            failures.append("no post-return title rows sampled")
        else:
            n2, rows = back
            _p, _t, _c = title[n2][1], title[n2][2], title[n2][3]
            if _p != 2:
                failures.append(f"the returned title opened on page {_p}, "
                                "expected 2 (NORMAL's board page)")
            board = board_from_hex(bests[n2][4]) if n2 in bests else None
            if board is None or not board.valid():
                failures.append(f"flow_board at frame {n2} is not valid "
                                f"({'' if n2 not in bests else bests[n2][4]!r})")
            else:
                init, _pad, top = board.entry(1, 0)
                line = tm.entry_line(0, init, top)
                want_row = " " * ((40 - len(line)) // 2) + line + \
                    " " * (40 - len(line) - (40 - len(line)) // 2)
                if rows[11] != want_row:
                    failures.append(f"returned title frame {n2}: row 11 "
                                    f"(NORMAL's top entry) is {rows[11]!r}, "
                                    f"expected {want_row!r}")
                if board_inserted_at(board, 1, sc10) is None:
                    failures.append(f"flow_board has no NORMAL entry with "
                                    f"score10 {sc10} and three spaces (the "
                                    "game's qualifying score was not "
                                    "inserted)")
                if board_inserted_at(board, 0, sc10) is not None \
                   or board_inserted_at(board, 2, sc10) is not None:
                    failures.append("the game's three-space entry landed "
                                    "on a level other than NORMAL")
                if board.bytes126() == bm.Board().bytes126():
                    failures.append("flow_board is still the default board "
                                    "after the game (nothing was inserted)")
    elif card_leg == 2:
        # ---- run 2: the persisted card (shares run 1's file) ----
        if any(fc >= 1 for (_fc, _rows) in samples.values()):
            failures.append("run 2 started a game (fc >= 1); only the "
                            "title may run")
        if first_p0 is None or first_p0[0] not in bests:
            failures.append("run 2 has no B record on its first page-0 "
                            "frame")
        else:
            board = board_from_hex(bests[first_p0[0]][4])
            if board is None or not board.valid():
                failures.append("run 2's flow_board is not valid")
            else:
                spaces = [e for e in range(bm.NENTRIES)
                          if board.entry(1, e)[0] == b"   "]
                if not spaces:
                    failures.append("run 2's flow_board has no three-space "
                                    "NORMAL entry (run 1's game did not "
                                    "persist on the card)")
                if board.bytes126() == bm.Board().bytes126():
                    failures.append("run 2's flow_board is the default "
                                    "board (the card load lost the game "
                                    "entry)")
    elif card_leg == 3:
        # ---- run 3: the old 'ESRG' magic on the card ----
        if any(fc >= 1 for (_fc, _rows) in samples.values()):
            failures.append("run 3 started a game (fc >= 1); only the "
                            "title may run")
        if first_p0 is None or first_p0[0] not in bests:
            failures.append("run 3 has no B record on its first page-0 "
                            "frame")
        else:
            board = board_from_hex(bests[first_p0[0]][4])
            if board is None or not board.valid():
                failures.append("run 3's flow_board is not valid")
            elif board.bytes126() != bm.Board().bytes126():
                failures.append("run 3's flow_board is not the default "
                                "board (an old 'ESRG' card was not reset)")
            top = board_top(board, 1)
            if top != bm.DEFAULTS[0][1]:
                failures.append(f"run 3's NORMAL top entry reads {top}, "
                                f"expected the default {bm.DEFAULTS[0][1]}")
    else:
        # ---- run 4: no card at all ----
        # the first page-0 frame reads the default board (the load answered
        # 0x80, nothing was copied: no garbage, no crash), and the game to
        # GAME OVER STILL keeps the board in backup RAM for the run: the
        # returned title's page 2 NORMAL board row shows the top entry
        # and flow_board holds the game's three-space entry.
        if any(fc >= 1 for (_fc, _rows) in samples.values()) and go is None:
            failures.append("run 4 started a game without a GO record")
        if first_p0 is None or first_p0[0] not in bests:
            failures.append("run 4 has no B record on its first page-0 "
                            "frame")
        else:
            board = board_from_hex(bests[first_p0[0]][4])
            if board is None or not board.valid():
                failures.append("run 4's first page-0 flow_board is not "
                                "valid")
            elif board.bytes126() != bm.Board().bytes126():
                failures.append("run 4's first page-0 flow_board is not "
                                "the default board")
        if go is None:
            failures.append("run 4: GAME OVER was never seen (expected "
                            "after fc ~28348 under Task 1's seed 0xaede: a "
                            "game to GAME OVER still keeps the board in "
                            "backup RAM)")
        else:
            go_fc = go[1]
            if not (25000 <= go_fc <= 31000):
                failures.append(f"run 4: GAME OVER came at fc {go_fc}, "
                                "expected ~28348 (the aiming AES game "
                                "under Task 1's seed)")
            _n, sc10 = scores[sorted(scores)[0]]
            if sc10 <= bm.DEFAULTS[bm.NENTRIES - 1][1]:
                failures.append(f"run 4: mis.score10 at GAME OVER reads "
                                f"{sc10}, expected > "
                                f"{bm.DEFAULTS[bm.NENTRIES - 1][1]}")
            back = None
            for n2 in sorted(samples):
                if n2 < go[0] + 250:
                    continue
                fc, rows = samples[n2]
                if fc != 0 or n2 not in title:
                    continue
                if not title_frame_ok(n2, rows, title):
                    continue
                back = (n2, rows)
                break
            if back is None:
                failures.append("run 4: no post-return title rows sampled")
            else:
                n2, rows = back
                board = board_from_hex(bests[n2][4]) if n2 in bests else None
                if board is None or not board.valid():
                    failures.append("run 4: flow_board on the returned "
                                    "title is not valid")
                else:
                    init, _pad, top = board.entry(1, 0)
                    line = tm.entry_line(0, init, top)
                    want_row = " " * ((40 - len(line)) // 2) + line + \
                        " " * (40 - len(line) - (40 - len(line)) // 2)
                    if rows[11] != want_row:
                        failures.append(f"run 4 returned title frame {n2}: "
                                        f"row 11 (NORMAL's top entry) is "
                                        f"{rows[11]!r}, expected "
                                        f"{want_row!r}")
                    if board_inserted_at(board, 1, sc10) is None:
                        failures.append("run 4: flow_board has no NORMAL "
                                        f"entry with score10 {sc10} and "
                                        "three spaces (the game's "
                                        "qualifying score was not inserted)")
    if failures:
        print("FAIL best-aes:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    if card_leg == 1:
        print(f"PASS best-aes (run 1): GAME OVER at fc {go_fc} with "
              f"mis.score10 {sc10}; the save's answers were "
              f"{[(hex(c), hex(a)) for (c, a) in log_pairs]} (fresh card: "
              "0x81 then FORMAT 0 then SAVE 0); the returned title opens "
              "on page 2 (NORMAL's board page) whose row 11 reads the "
              "board's top entry and flow_board holds the game's three-space "
              "entry")
    elif card_leg == 2:
        print("PASS best-aes (run 2): with run 1's card and a fresh "
              "nvram, the load answered 0 and the first page-0 frame "
              "reads the persisted board with its three-space entry")
    elif card_leg == 3:
        print("PASS best-aes (run 3): with the card's saved magic patched "
              "to the old 'ESRG', the entry starts from the five defaults")
    else:
        print("PASS best-aes (run 4): with no card, the load answered "
              "0x80, the first page-0 frame reads the five defaults (no "
              "garbage, no crash), and a game to GAME OVER still keeps the "
              "board in backup RAM")
    return 0


def check_best_return(samples, title, bests, scores, go):
    """high-score boards Task B2 (flow-return-best, AES): the Up-held game
    to GAME OVER (score 0) does not beat the default 5th entry, so the board
    stays the five defaults; the returned title's page 2 (NORMAL's board
    page) shows the default top entry. The drawn rows equal title_model's
    page 2 with the board read in the same frame."""
    failures = []
    if not bests:
        failures.append("no B records (flow_board never read)")
    if not scores:
        failures.append("no SC record (mis.score10 at GAME OVER never "
                        "read)")
    if not samples:
        failures.append("no post-return fix-row samples")
    if go is None:
        failures.append("no GAME OVER record (the Up-held game never "
                        "ended)")
    if failures:
        print("FAIL flow-return best:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    sc10 = scores[sorted(scores)[0]][1]
    # the returned title: a sample AFTER the return (frame >= GO + the
    # 295-frame window, in MAME frames), whose T record reads a title page
    # (the game-session counter is 0 again). The pre-game title's own page
    # 1 (the first auto-turn at ~frame 772) must not be picked.
    back = None
    for n2 in sorted(samples):
        if n2 < go[0] + GAME_OVER_WAIT - 100:
            continue
        fc, rows = samples[n2]
        if fc == 0 and n2 in title and drawn_title_ok(n2, rows, title) \
           and 1 <= drawn_title(n2, title)[0] < tm.PAGES:
            back = (n2, rows)
            break
    if back is None:
        failures.append("no post-return board-page title rows sampled")
    else:
        n2, rows = back
        _p, t, _c = drawn_title(n2, title)
        if _p != 2:
            failures.append(f"the returned title opened on page {_p}, "
                            "expected 2 (NORMAL's board page)")
        _bfc, b0, b1, b2, hexb = bests[n2]
        board = board_from_hex(hexb)
        if board is None or not board.valid():
            failures.append(f"flow_board at frame {n2} is not valid "
                            f"({hexb!r})")
        else:
            if board.bytes126() != bm.Board().bytes126():
                failures.append("the Up-held game changed the board "
                                f"(score10 {sc10} should not qualify)")
            if b0 != bm.DEFAULTS[0][1] or b2 != bm.DEFAULTS[0][1]:
                failures.append(f"flow_board EASY/HARD tops read {b0}/{b2} "
                                f"after the Up-held game, expected "
                                f"{bm.DEFAULTS[0][1]}/"
                                f"{bm.DEFAULTS[0][1]}")
        want = tm.title_rows(_p, 1, t, board_at(n2, bests), _c)
        for r in range(TITLE_ROWS):
            if r == hm.HUD_INTEG_ROW:
                continue         # attract A2: the HUD's row 26
            if rows[r] != want[r]:
                failures.append(f"returned title frame {n2}: row {r} != "
                                "title_model page 2 with the board "
                                f"({b0},{b1},{b2}), t {t}")
                break
        init, _pad, top = bm.Board().entry(1, 0)
        line = tm.entry_line(0, init, top)
        want_row = " " * ((40 - len(line)) // 2) + line + \
            " " * (40 - len(line) - (40 - len(line)) // 2)
        if rows[11] != want_row:
            failures.append(f"returned title frame {n2}: row 11 "
                            f"(NORMAL's top entry) is {rows[11]!r}, expected "
                            f"{want_row!r}")
    if failures:
        print("FAIL flow-return best:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS flow-return best: the Up-held game's score at GAME OVER "
          f"was {sc10} (score10), below the default 5th entry, so the "
          f"board stays the five defaults; the returned title's page 2 "
          f"shows NORMAL's top entry {bm.DEFAULTS[0][1] * 10}")
    return 0


def check_flow_level(records, samples, title, levels, games, first=None,
                     seed=None):
    """the M6 Task 7 proof 1 (flow-level, AES, no Start until frame 1400):
    B on MAME frame 1000 -> row 7 reads "HARD" from frame 1002 on (within 2
    frames), page 0, title_t 0; B on 1100 -> "EASY"; B on 1200 -> "NORMAL";
    B on 1300 -> "HARD". Start at 1400 -> rules.level and mis.level in RAM
    read 2 on the first game frame. The level byte only changes on a B
    press (the sequence of distinct values is exactly 1, 2, 0, 1, 2), and
    page 0's row 9 prompt must be visible on every sampled t-0 title frame.
    Mutation (a), B wrapping HARD -> EASY after HARD (instead of HARD ->
    EASY ... no: wrapping HARD -> NORMAL), shows up as a wrong sequence."""
    failures = []
    if not levels:
        failures.append("no L records (is FLOW_LEVEL_ADDR set and the "
                        "address right?)")
    if not title:
        failures.append("no T records (is FLOW_PAGE_ADDR / FLOW_T_ADDR "
                        "right?)")
    if failures:
        print("FAIL flow-level:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    # ---- 1a. the four B taps: the level byte read from RAM (the L
    # records, every frame), the B-press reset (a T record reading page 0,
    # title_t 0 right after the tap), and the drawn row 5 (a fix-row
    # sample close after the change). The level changes must land within 2
    # MAME frames of the tap (the cart polls bios_p1change once per frame;
    # the probe applies the hold on the tap frame n, so the cart sees it on
    # the next frame's poll).
    taps = [1000, 1100, 1200, 1300]
    want_seq = [2, 0, 1, 2]          # NORMAL (1) -> HARD -> EASY -> NORMAL -> HARD
    slv = sanitized_levels(levels)   # (n, fc, sanitized), the cart's view
    ln = sorted(slv)
    for k, tap in enumerate(taps):
        want = want_seq[k]
        seen = None
        for n in ln:
            if n < tap:
                continue
            fc, lv = slv[n]
            if seen is None and lv == want:
                seen = (n, lv)
            if seen and n > seen[0] + 4:
                break
        if seen is None:
            failures.append(f"B tap at frame {tap}: flow_level never read "
                            f"{want} ({REV[want]}) after it")
            continue
        if not (tap <= seen[0] <= tap + 2):
            failures.append(f"B tap at frame {tap}: flow_level went "
                            f"{REV[want]} only at frame {seen[0]} (must be "
                            "within 2 of the tap)")
        # the B-press reset: a T record reads page 0, title_t 0 within 2
        # frames of the tap (B jumps the title to page 0 and resets t).
        reset = None
        for n in sorted(title):
            if n < tap - 1 or n > tap + 3:
                continue
            _fc, page, t, cred = title[n]
            if page == 0 and t == 0:
                reset = n
                break
        if reset is None:
            failures.append(f"B tap at frame {tap}: no T record reads page "
                            "0, title_t 0 within [tap-1, tap+3]")
        # the drawn row 5 must equal the level row for the RAM byte, on a
        # sampled page-0 title frame close after the level change (the fix
        # rows are dumped every 6 MAME frames, so the first dump at/after
        # the change can be up to 5 frames into the new state — within the
        # task's "from that frame on").
        drawn = None
        for n in sorted(samples):
            if n >= seen[0] and n <= seen[0] + 12:
                fc, rows = samples[n]
                if fc != 0 or rows[3] != ROW3:
                    continue
                if n in title:
                    _fc, page, t, cred = title[n]
                    if page != 0:
                        continue
                drawn = (n, rows)
                break
        if drawn is None:
            failures.append(f"B tap at frame {tap}: no drawn page-0 title "
                            "sample within 12 frames of the level change")
        else:
            n, rows = drawn
            if not _row5_is(rows, want):
                failures.append(f"B tap at frame {tap}: drawn row 5 at frame "
                                f"{n} is {rows[LEVEL_ROW]!r}, expected "
                                f"{REV[want]} centred")
    # ---- 1b. the level byte's history: it only changes on a B press, and
    # the sequence of distinct values is exactly 1, 2, 0, 1, 2 (the fresh
    # NORMAL and the four wraps). Any extra change (a stuck B, a spurious
    # write) fails this.
    distinct = []
    for n in sorted(slv):
        if n < 280:
            continue                 # the pre-clear garbage on MVS; AES is 0
        lv = slv[n][1]
        if not distinct or distinct[-1] != lv:
            distinct.append(lv)
    if distinct != [1, 2, 0, 1, 2]:
        failures.append(f"flow_level changed as {distinct} over the taps "
                        "(fresh NORMAL must give 1, 2, 0, 1, 2)")
    # ---- 1c. the Start at 1400: rules.level and mis.level in RAM read 2
    # on the first game frame (the G records; the first G at fc 1).
    gs = sorted(games)
    if not gs:
        failures.append("no G records (rules.level/mis.level never read)")
    else:
        n, fc, rl, ml = (gs[0],) + games[gs[0]]
        if fc != 1:
            failures.append(f"first G record has fc {fc}, expected 1")
        if (rl, ml) != (2, 2):
            failures.append(f"first game frame: rules.level {rl}, "
                            f"mis.level {ml}, expected HARD (2, 2)")
    # ---- 1d. the prompt row (21, attract A1) with title_t 0: page 0's
    # row 21 must show the prompt, never 'B TO CHANGE LEVEL', on any
    # sampled title frame whose title_t is 0 (the prompt's t&64 alternation
    # is off at t 0).
    for n in sorted(samples):
        if n not in title:
            continue
        fc, rows = samples[n]
        _tfc, page, t, cred = title[n]
        if fc == 0 and rows[3] == ROW3 and page == 0 and t == 0:
            if rows[PROMPT_ROW] not in (ROW9_ON, ROW9_COIN):
                failures.append(f"page 0, t 0 at frame {n}: prompt row "
                                f"{PROMPT_ROW} is {rows[PROMPT_ROW]!r}, "
                                "expected the prompt")
    if failures:
        print("FAIL flow-level:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS flow-level: B taps at 1000/1100/1200/1300 cycled NORMAL -> "
          "HARD -> EASY -> NORMAL -> HARD on page 0 with title_t 0 (each "
          "within 2 frames, drawn row 7 matching), Start at 1400 began a "
          "HARD game (rules.level and mis.level 2)")
    return 0


def check_flow_return(records, samples, title, levels, games, go, bests,
                      seed=None):
    """the M6 Task 7 proofs 2 + 3 (flow-return, AES): the Up-held game to
    GAME OVER at fc 17525 under Task 1's seed (NORMAL, no A; 6509 with
    RNG_SEED), the 295-frame window expires, and
    the title that comes back opens on the played level's board page: the
    game ran at NORMAL (1), so title_page reads 2 and the drawn title rows
    equal title_model's page 2. The level is still the chosen one
    (rules.level and mis.level read 1 on the first game frame, and
    flow_level reads 1 on the post-return title). Proof 3 rides on the same
    run: a fresh boot (a run whose nvram was never touched) shows page 0 and
    NORMAL before Start. high-score boards Task B2/B3: the returned title
    draws the board from backup RAM (flow_board), so the model compare uses
    the B record read in the same frame."""
    failures = []
    go_row_bad = gameover_rows_failures(samples, go)
    failures.extend(go_row_bad)
    if not go_row_bad and go is not None:
        print(f"GAME OVER rows 7/8 at frame {go[0]} equal the model")
    if not records:
        failures.append("probe wrote no input records")
        return 1
    if not samples:
        failures.append("no fix-row samples")
        return 1
    if not levels:
        failures.append("no L records (flow_level never read)")
    if not title:
        failures.append("no T records")
    if not games:
        failures.append("no G records")
    if failures:
        print("FAIL flow-return:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    # ---- proof 2a: the game ran at NORMAL — the first game frame's
    # rules.level and mis.level both read 1 (this run never presses B).
    gs = sorted(games)
    if gs:
        n, fc, rl, ml = (gs[0],) + games[gs[0]]
        if fc != 1:
            failures.append(f"first G record has fc {fc}, expected 1")
        if (rl, ml) != (1, 1):
            failures.append(f"first game frame: rules.level {rl}, "
                            f"mis.level {ml}, expected NORMAL (1, 1)")
    # ---- proof 2b: GAME OVER at the model's frame under Task 1's seed
    # (the Up-held game ends at fc 17525 for the default Start 600; 6509
    # was the RNG_SEED game), the 295-frame window, then mod1 cleared.
    if go is None or not (17495 <= go[1] <= 17555):
        failures.append(f"GAME OVER was never seen at the model's fc ~17525 "
                        f"(go={go})")
        return 1
    go_fc = go[1]
    mod0 = None
    for n, fc, cur, chg, mod1 in records:
        if go_fc <= fc <= go_fc + GAME_OVER_WAIT + 8 and mod1 == 0:
            mod0 = (n, fc, mod1)
            break
    if mod0 is None:
        failures.append("bios_player_mod1 never read 0 within "
                        f"[GO+{GAME_OVER_WAIT}, GO+{GAME_OVER_WAIT}+8]")
    # ---- proof 2c: the title that comes back opens on the played level's
    # board page (NORMAL -> page 2): the first sampled frame whose cart
    # title is drawn (fc 0 and — from the T records — a real title page, or
    # row 3's "E-SRG" for page 0) at/after the return, its page reads 2, and
    # all 28 drawn rows equal the model's page 2 (level NORMAL, the t and
    # credits read in the same frame).
    back = None
    for n in sorted(samples):
        fc, rows = samples[n]
        if fc != 0:
            continue
        # Attract Task A2: the returned entry's first frames are blank
        # (the scene/rows are drawn over its two vblanks); require the
        # drawn page, not just the T record's page.
        if drawn_title_ok(n, rows, title):
            dp = drawn_title(n, title)[0]
            if 1 <= dp < tm.PAGES and (mod0 is None or n >= mod0[0]):
                back = (n, rows)
                break
    if back is None:
        failures.append("the title rows never came back after the window "
                        "expired")
    else:
        n, rows = back
        if mod0 is not None and n - mod0[0] > 300:
            failures.append(f"title returned {n - mod0[0]} MAME frames after "
                            "mod1 cleared (need within 300)")
        if n not in title:
            failures.append(f"no T record for the returned title frame {n}")
        else:
            page, t, cred = drawn_title(n, title)
            want_page = 2               # the game ran at NORMAL (1) -> 1 + 1
            if gs:
                want_page = games[gs[0]][1] + 1    # the first G's rules.level
            if page != want_page:
                failures.append(f"the returned title opened on page {page}, "
                                f"expected {want_page} (the played level's "
                                "board page)")
            # high-score boards Task B2/B3: the drawn board is the
            # backup-RAM one read in the same frame (fresh-boot defaults
            # only if the probe did not dump a B record).
            want = tm.title_rows(page, 1, t, board_at(n, bests), cred)
            for r in range(TITLE_ROWS):
                if r == hm.HUD_INTEG_ROW:
                    continue         # attract A2: the HUD's row 26
                if rows[r] != want[r]:
                    failures.append(f"returned title frame {n}: row {r} != "
                                    f"title_model page {want_page} (t {t}, "
                                    f"credits {cred}):\n  drawn "
                                    f"{rows[r]!r}\n  model {want[r]!r}")
                    break
    # ---- proof 2d: the level is still the chosen one: the sanitized
    # flow_level reads 1 (NORMAL) on the post-return title, from backup
    # RAM.
    sv = sanitized_levels(levels)
    post = [(n, lv) for n, (_fc, lv) in sorted(sv.items())
            if mod0 is not None and n >= mod0[0]]
    if not post:
        failures.append("no L records after the return (flow_level never "
                        "read on the returned title)")
    elif post[0][1] != 1:
        failures.append(f"flow_level reads {post[0][1]} after the return, "
                        "expected 1 (the level is kept)")
    # ---- proof 3: a fresh boot shows page 0 and NORMAL. The title's first
    # sampled frame (the title starts at MAME frame ~24 with no BIOS logo;
    # samples come every 6 frames) must show page 0 with title_t < 6, and the sanitized flow_level must read 1 (NORMAL) — the
    # entry opened on page 0, not the played level's board page, because the GAME
    # OVER return did not set the open-high-scores byte on this fresh boot.
    # (This run never presses B.)
    pre = {n: t_ for n, t_ in sorted(title.items())   # the cart's entry title
           if n < 1400 and n >= 20 and t_[2] > 0}      # frames (t 0 before entry)
    if not pre:
        failures.append("no pre-Start title T records")
    else:
        first = sorted(pre)[0]
        _ffc, fpage, ft, fcred = pre[first]
        if fpage != 0 or ft >= 6:
            failures.append(f"the fresh title's first T record (frame "
                            f"{first}) reads page {fpage}, t {ft}, expected "
                            "page 0, t < 6 (a fresh boot must show page 0)")
    pre_levels = [lv for n, (_fc, lv) in sorted(sv.items())
                  if n < 1400 and n >= 280]
    if not pre_levels:
        failures.append("no fresh-boot L records before Start")
    elif pre_levels[0] != 1:
        failures.append(f"flow_level reads {pre_levels[0]} on the fresh "
                        "boot, expected 1 (NORMAL)")
    if failures:
        print("FAIL flow-return:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS flow-return: fresh boot page 0 NORMAL; the Up-held game to "
          f"GAME OVER at fc {go_fc} ran at NORMAL (rules/mis level 1); the "
          "returned title opens on page 2 (the played NORMAL level's board "
          "page) with the level kept")
    return 0


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    framecnt_addr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    restart = (len(sys.argv) > 4 and sys.argv[4] == "1")
    mvs_mode = (sys.argv[5] if len(sys.argv) > 5
                and sys.argv[5] in ("flow-mvs", "flow-mvs-start",
                                    "flow-mvs-norestart", "flow-pages",
                                    "flow-pages-c", "flow-level",
                                    "flow-return", "best-mvs",
                                    "best-aes", "flow-return-best") else "")
    records, mvs_records, nrs_records, samples, slots, views, title, levels, \
        games, domes, go, snap, exit_, bests, scores, cards, seeds, \
        first = parse(probe)
    seed = mis_seed.cart_seed(probe, seeds)   # Task 1: the cart's seed
    if first is not None:
        print(f"first missile: (ring, phi) = ({first[1]}, {first[2]}) at "
              f"MAME frame {first[0]}; mis_seed_used {seed:#06x}")
    # M6 Task 9: boot_test.sh passes the nvram reuse/freshness of a
    # best-mvs run (2 = run 2, sharing the nvram; 3 = run 3, a fresh nvram;
    # anything else = run 1). The checker keys run 2's row-7 persistence
    # proof on it.
    best_leg = int(os.environ.get("BEST_NVRAM_LEG", "1"))
    # M6 Task 10: the card-leg (2 = run 2, sharing the card; 3 = run 3, no
    # card; anything else = run 1), from boot_test.sh
    card_leg = int(os.environ.get("BEST_CARD_LEG", "1"))

    if not records and not mvs_records and not nrs_records:
        failures = ["probe wrote no input records"]
        return 1
    if mvs_mode:
        if mvs_mode == "flow-mvs-norestart":
            return check_mvs_norestart(nrs_records, mvs_records, samples)
        if mvs_mode in ("flow-mvs", "flow-mvs-start"):
            return check_mvs(mvs_mode, mvs_records, samples, title)
        if mvs_mode == "flow-pages":
            return check_pages(samples, title, domes, views, bests)
        if mvs_mode == "flow-pages-c":
            return check_pages_c(title, domes)
        if mvs_mode == "flow-level":
            return check_flow_level(records, samples, title, levels, games,
                                    first, seed)
        if mvs_mode == "flow-return":
            return check_flow_return(records, samples, title, levels,
                                     games, go, bests, seed)
        if mvs_mode == "best-mvs":
            return check_best_mvs(mvs_records, samples, title, levels,
                                  bests, scores, go, best_leg)
        if mvs_mode == "best-aes":
            return check_best_aes(samples, title, levels, bests, scores,
                                  go, cards, card_leg)
        if mvs_mode == "flow-return-best":
            return check_best_return(samples, title, bests, scores, go)

    failures = []
    if not records:
        failures.append("probe wrote no input records")
        return 1
    if not samples:
        failures.append("probe wrote no fix-row samples")
        return 1

    # ---- (a) the title: until Start (MAME 1200..1204) ----
    title = title_rows(samples, slots, views)
    if not title:
        failures.append("no title samples (fc==0) were captured")
    seen_on, seen_b = False, False
    for n, rows in title:
        if rows[3] != ROW3:
            failures.append(f"title row 3 at frame {n}: {rows[3]!r} != {ROW3!r}")
        # page 0's gaps (M8 art pass + attract Task A1's caps): row 6 is
        # blank; rows 8/10 are the cap rows of the level (7) and best (9),
        # so they repeat those rows' characters (their tiles draw the
        # glyphs' bottom outline row); row 22 is the prompt's (21) cap.
        if rows[6] != " " * 40:
            failures.append(f"title page-0 blank row 6 at frame {n}: "
                            f"{rows[6]!r}")
        if rows[8] != rows[7] or rows[10] != rows[9] or rows[22] != rows[21]:
            failures.append(f"title page-0 cap rows at frame {n}: "
                            f"row 8 {rows[8]!r} vs level 7 {rows[7]!r}, "
                            f"row 10 {rows[10]!r} vs best 9 {rows[9]!r}, "
                            f"row 22 {rows[22]!r} vs prompt 21 "
                            f"{rows[21]!r}")
        # HUD-layout Task 3 / attract Task A1: page 0's prompt is row 21
        # now, alternating every 64 frames between "PRESS START" (t & 64
        # clear) and "B TO CHANGE LEVEL" (t & 64 set).
        if rows[PROMPT_ROW] == ROW9_ON:
            seen_on = True
        elif rows[PROMPT_ROW] == ROW9_B:
            seen_b = True
        else:
            failures.append(f"title prompt row {PROMPT_ROW} at frame {n}: "
                            f"{rows[PROMPT_ROW]!r}")
        # Attract Task A3: exact demo HUD values are check_demo.py's proof;
        # here require the two HUD rows to stay drawn under the title.
        if not hud_integ_present(rows[hm.HUD_INTEG_ROW]):
            failures.append(f"title HUD row {hm.HUD_INTEG_ROW} at frame {n} "
                            f"is {rows[hm.HUD_INTEG_ROW]!r} (the demo's HUD "
                            f"is not drawn)")
        if not any(ch.isdigit() for ch in rows[hm.HUD_LIVES_ROW]):
            failures.append(f"title HUD row {hm.HUD_LIVES_ROW} at frame {n} "
                            f"is {rows[hm.HUD_LIVES_ROW]!r} (the demo's "
                            f"score/lives row is not drawn)")
    if not seen_on:
        failures.append(f"title never showed 'PRESS START' on row "
                        f"{PROMPT_ROW}")
    if not seen_b:
        failures.append(f"title never showed 'B TO CHANGE LEVEL' on row "
                        f"{PROMPT_ROW} (t & 64 alternation)")
    # Attract Task A3: the scene under the title is the demo, so the game
    # slots vary (missiles, explosions, broken overlays) and the dome's
    # view turns. check_demo.py proves the exact per-frame state; here gate
    # the flow leg's samples on the scene being live and inside the sprite
    # budget (5 is the ship's driver + the radar frame's 4 columns; 96 is
    # the census limit).
    title_ns = set(n for (n, _rows) in title)
    counts = []
    for n, (fc, nonzero) in slots.items():
        if n in title_ns:
            counts.append(nonzero)
            if nonzero < 5 or nonzero > 96:
                failures.append(f"title frame {n} had {nonzero} game slots "
                                f"shown (want 5..96: the demo's live scene)")
    if len(set(counts)) < 2:
        failures.append("the demo's game slots never changed on the title "
                        f"(only {set(counts)}); the scene is not playing")
    dist = set(tile for (nn2, (fc, tile)) in views.items()
               if nn2 in title_ns)
    if len(dist) < 2:
        failures.append("the dome's SCB1 view never changed during the "
                        "title (the demo is not turning it)")
    elif len(dist) > 48:
        failures.append(f"the dome's SCB1 view changed {len(dist)} ways "
                        "during the title (out of the 48 dome views)")
    else:
        print(f"title scene: game slots {min(counts) if counts else '-'}.."
              f"{max(counts) if counts else '-'} over {len(counts)} samples, "
              f"dome SCB1 views {len(dist)} (the demo is playing)")
    # the game-session counter is 0 throughout the title (checked above via
    # the fc == 0 gate; also every recorded title frame's fc is 0)
    for n, fc, cur, chg, mod1 in records:
        if n < 1199 and fc != 0 and framecnt_addr != 0:
            failures.append(f"frame {n}: hud_framecnt {fc} != 0 on the title")
            break

    # ---- (b) the Start: within a few frames fc >= 1 and the HUD first frame
    # matches the model ----
    gf = first_game_frame(records, samples)
    if gf is None:
        failures.append("the game never started (no fc>=1 sampled rows)")
    else:
        want = model_first_rows(seed)
        got = match = None
        for n in sorted(samples):
            fc, rows = samples[n]
            # the game-frame dumps carry all 30 rows now (HUD-layout Task
            # 2); the hud model's rows cover fix rows 0..29
            if 1 <= fc <= 12 and rows[:len(want)] == want:
                match = rows
                break
        if match is None:
            failures.append(f"no sampled first-game frame (fc 1..12) matched "
                            "hud_model's first frame")
        # the counter reached >= 1 within 10 game frames of fc 1
        if gf > 10:
            failures.append(f"first game frame was fc {gf}, expected <= 10")

    # ---- the GAME OVER ----
    # Task 1 seeds the missiles from the title's time: at the flow legs'
    # Start window (1200..1204) the Up-held game now ends at fc 8188 (the
    # model derivation), where it was 6509 with RNG_SEED. The check is the
    # model's GAME OVER (check_flow_return states it), so only a floor is
    # needed here.
    if go is None or go[1] < 6480:
        failures.append("GAME OVER was never seen (expected under Task 1's "
                        "seed at fc 8188)")
        return 1
    go_fc = go[1]

    # Task G1: the sampled GAME OVER rows equal the model's (thick text on 7,
    # its cap on 8), and the leg's snapshot of that GAME OVER shows the thick
    # font's pixels through PAL_HUD.
    go_row_bad = gameover_rows_failures(samples, go)
    failures.extend(go_row_bad)
    if not go_row_bad:
        print(f"GAME OVER rows 7/8 at the sampled frame {go[0]} equal the "
              f"model (thick text + its cap)")
    if snap is not None and os.path.isfile(snap_png):
        hit = samples.get(snap[0])
        rows_go = hit[1] if hit is not None else gameover_model_rows()
        failures.extend(check_gameover_pixels(snap_png, rows_go))

    if not restart:
        # ---- (c) no A: after the 295-frame window the cart returns to title.
        # Find, among the frames at/after GAME OVER, the first fc in the
        # [GO+295, GO+300] band whose mod1 reads 0.
        mod0 = None
        for n, fc, cur, chg, mod1 in records:
            if go_fc <= fc <= go_fc + GAME_OVER_WAIT + 8 and mod1 == 0:
                mod0 = (n, fc, mod1)
                break
        if mod0 is None:
            failures.append("bios_player_mod1 never read 0 within "
                            f"[GAME OVER+{GAME_OVER_WAIT}, +{GAME_OVER_WAIT}+8]")
        else:
            if not (go_fc + GAME_OVER_WAIT <= mod0[1] <= go_fc + GAME_OVER_WAIT + 5):
                failures.append(f"mod1 cleared at fc {mod0[1]}, expected in "
                                f"[GO+{GAME_OVER_WAIT}, GO+{GAME_OVER_WAIT}+5]")
            # the title is back within 300 MAME frames of that, and the
            # session counter reset to 0. M6 Task 7: the returned title
            # opens on the played level's board page (1..3), which draws no "E-SRG"
            # row — the "back" gate accepts a board-page title too (the
            # drawn HIGH SCORES text on row 6, pages 1..10's first line).
            back = None
            for n2 in sorted(samples):
                if n2 < mod0[0]:
                    continue
                fc, rows = samples[n2]
                if fc != 0:
                    continue
                if rows[3] == ROW3 or rows[6].strip() in (
                        "HIGH SCORES", "CONTROLS", "DEFEND THE DOME",
                        "LEVELS", "RADAR", "CREDITS", "BUILT WITH"):
                    back = (n2, rows)
                    break
            if back is None:
                failures.append("the title rows never came back")
            else:
                if back[0] - mod0[0] > 300:
                    failures.append(f"title returned {back[0]-mod0[0]} MAME "
                                    "frames after mod1 cleared (==0); need "
                                    "within 300")
    else:
        # ---- (d) A at GAME OVER + 60: a new game, lives 3, no title ----
        want = model_first_rows(seed)
        saw_restart = False
        saw_fc_positive_after = False
        for n in sorted(samples):
            fc, rows = samples[n]
            if go_fc + 60 <= fc <= go_fc + 96:
                if rows[:len(want)] == want:
                    saw_restart = True
                if fc > go_fc + 60:
                    saw_fc_positive_after = True
        if not saw_restart:
            failures.append("the A-restart did not show a fresh game's HUD "
                            "rows (lives 3, integ 100, score 0)")
        else:
            print("A-restart: the new game's rows 7/8 are blank (the fresh "
                  "HUD model's rows match)")
        if not saw_fc_positive_after:
            failures.append("the A-restart did not keep the game running "
                            "(no fc beyond GAME OVER + 60)")

    if failures:
        print("FAIL flow" + ("-restart" if restart else "") + ":")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS flow{' (restart leg)' if restart else ' (return leg)'}: "
          f"title ({len(dist)} dome views), Start, game, GAME OVER "
          f"at fc {go_fc}, "
          + ("A-restart to a new game" if restart else "returned to the title"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
