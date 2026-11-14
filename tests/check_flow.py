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
                   Task 6): prove the title's nine pages turn every 295
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
Task 3 MVS proofs (HUD-layout Task 3: the prompt moved to row 9): the
title's row 9 says INSERT COIN before the coin and PRESS START after it
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
  whole chain on page 0, all 11 columns hidden on pages 1..8, and the
  rebuilt chain after the wrap equal to the first page-0 frame's.
  `flow-pages-c` (MVS, no coin/Start): main() enters at ~frame 749, so page
  0 spans 749..1043; a C tap on MAME frames 900 and 1000 turns the page
  0 -> 1 -> 2 on (or within 2 frames of) those frames, and title_t resets
  to 0 at each turn. The dome dumps at pages 0, 1, 2 prove page 1 and 2
  hide every column (SCB3 height 0) while page 0 has the chain.

The M6 Task 6 proof 6 mutations, each seen to fail its check and then
reverted: (a) the page time 250 instead of 295; (b) hiding the dome by
zeroing only the driver's SCB3; (c) writing every title row every frame.
All three are proven by check_pages / check_pages_c below.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import hud_model as hm  # noqa: E402
import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import rules_model as rm  # noqa: E402
import ship_model as sm  # noqa: E402
import title_model as tm  # noqa: E402
import layout as lay  # noqa: E402


def _decode_row(raw):
    """a probe W line's 40 chars -> the row as the models build it: the
    probes write the HUD icon tile numbers (>= 0x80) as <NN> escapes (the
    stream is otherwise ASCII)."""
    out = []
    i = 0
    while i < len(raw):
        m = re.match(r"<(\d+)>", raw[i:])
        if m:
            out.append(chr(int(m.group(1))))
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
# probe writes tiles 128..255 as <NN> escapes, decoded to chr(NN)); row 3,
# the logo's second tile row, stays the title gate. The level, best and
# prompt rows come from src/title.h (title_model reads them).
ROW3 = tm.logo_row(3 - tm.LOGO_ROW)
LEVEL_ROW, PROMPT_ROW = tm.LEVEL_ROW, tm.PRESS_ROW
# HUD-layout Task 3: page 0's lines moved to rows 3/5/7/9 (one blank row
# between each) — the prompt is row 9 now, alternating every 64 frames
# between the prompt text (t & 64 clear) and "B TO CHANGE LEVEL" (t & 64
# set).
ROW9_ON = " " * ((40 - 11) // 2) + "PRESS START" + " " * (40 - 11 - (40 - 11) // 2)
ROW9_OFF = " " * 40        # the pre-coin blank row 9 / the prompt's off state
ROW9_B = " " * ((40 - 17) // 2) + "B TO CHANGE LEVEL" + " " * (40 - 17 - (40 - 17) // 2)
# the MVS attract title's row 9 on text (M6 Task 3): "INSERT COIN" is 11
# chars, centred at the same (40 - n) // 2 column as "PRESS START".
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
    b1, b2, hexbytes)} from the B lines (the flow_best backup table, M6
    Task 9); scores: {n: (fc, score10)} from the SC lines (mis.score10 at
    GAME OVER, M6 Task 9); cards: {n: (fc, [(cmd, ans), ...])} from the A
    lines (the card-log pairs, M6 Task 10)."""
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
                # B <n> <fc> <b0> <b1> <b2> <18 hex bytes>: the cart's
                # flow_best backup table (M6 Task 9)
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
                    if len(cur_dome[2]) == 11:
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


def check_pages(samples, title, domes):
    """M6 Task 6, proofs 1 + 2 + 3 (flow-pages, AES no-Start):
    1. every sampled title frame's fix rows 0..27 equal
       tests/title_model.py's rows for the page, level (NORMAL here), t
       and credits read from RAM in the same frame; the count of compared
       frames per page is reported.
    2. the page advances every 295 frames exactly (title_page/title_t from
       RAM), through 8 -> 0.
    3. dome: on page 0 the driver SCB3 has height DOME_ROWS and the 10
       followers have the sticky bit; on pages 1..8 every column's SCB3
       height is 0; back on page 0 after the wrap, all the dome's
       SCB2/SCB3/SCB4 words equal those of the first page-0 frame (the
       chain rebuilt, not half a dome) — checked on the dump blocks the
       probe keys to the PIN frames.
    (Mutation (b) — hide by zeroing only the driver's SCB3 — fails the
    pages 1..8 check: the followers keep their sticky bit and height.
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
        # the title gate: page 0 shows "E-SRG" on row 3 (HUD-layout Task
        # 3); pages 1..8 draw from row 6 (title.c) and row 3 is blank —
        # the T record's page is the authoritative title marker, and for
        # page 0 the row-3 check still runs below.
        if page == 0 and rows[3] != ROW3:
            continue
        if not (0 <= page <= 8):
            failures.append(f"frame {n}: title_page reads {page} (out of 0..8)")
            continue
        if not (0 <= t < TITLE_PAGE_FRAMES):
            failures.append(f"frame {n}: title_t reads {t} (out of 0..294)")
            continue
        # flow-pages is AES (credits 0): the title's own credits value,
        # read from the RAM the cart drew from — the model's credits
        # argument is exactly this byte. Level NORMAL = 1.
        want = tm.title_rows(page, 1, t, [0, 0, 0], cred)
        n_compared += 1
        checked_any = True
        per_page[page] = per_page.get(page, 0) + 1
        for r in range(TITLE_ROWS):    # the model's rows 0..27 (rows 28/29
            # are the countdown's own pair, title_rows never fills them).
            # This leg is AES (cred 0), so no row is ever skipped: page 0's
            # row 9 IS the prompt line (HUD-layout Task 3 — title_rows
            # writes it), unlike the MVS post-coin rows (check_mvs /
            # check_best_* compare those against the model separately).
            if rows[r] != want[r]:
                failures.append(f"frame {n}: row {r} != title_model's "
                                f"(page {page}, t {t}, credits {cred}):\n"
                                f"  drawn {rows[r]!r}\n"
                                f"  model {want[r]!r}")
                break
        # the countdown row stays blank on this AES run (the MVS legs own
        # it; title_rows never writes 28 — the HUD-layout Task 3 rule)
        if rows[28] != " " * 40:
            failures.append(f"frame {n}: row 28 is {rows[28]!r} on an AES "
                            "title frame (the countdown must stay blank "
                            "until a coin, and never come from title_rows)")
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
        failures.append("the title never turned a page (need 0..8 -> 0)")
    else:
        # the run must see pages 0, 1, 2, ... in order through 8 -> 0: the
        # first 9 turns, pages 0->1, 1->2, ..., 8->0 (a long-enough run
        # wraps again past 8 -> 0, and those extra turns are fine).
        want_seq = [(i, (i + 1) % 9) for i in range(9)]
        got_seq = [(a, b) for (_n, a, b, _pt, _t) in turns]
        if got_seq[:9] != want_seq:
            failures.append(f"the page sequence was {got_seq}, expected to "
                            f"begin {want_seq} (0,1,...,8 -> 0 in order)")
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
            for k, (n, a, b, pt, t) in enumerate(turns[:9]):
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

    # ---- 3. the dome: chain on page 0, hidden on 1..8, rebuilt ----
    if not domes:
        failures.append("no dome dumps (is FLOW_DOME_SNAP set?)")
        return 1 if failures else 0
    ev = sorted(domes)
    # the probe dumps the first title frame of every page 0..8 plus the
    # first page-0 frame after the wrap: 10 dumps.
    if len(ev) < 10:
        failures.append(f"expected 10 dome dumps (one per page 0..8 + the "
                        f"wrapped page 0), got {len(ev)}")
    # each dump records the page the probe observed at dump time (the C
    # line's third field) — the page-of mapping is not needed.
    for n in ev:
        _fc, cols, p = domes[n]
        if p == 0:
            # the driver (column 0): a real Y/height word; the followers
            # (1..10): the sticky bit set, no own height.
            d0 = cols[0][1]
            if d0 & 0x3f == 0:
                failures.append(f"page-0 dome dump at frame {n}: the driver "
                                "SCB3 has height 0 (the dome is not shown)")
            if not all(s3 & (1 << 6) and s3 & 0x3f == 0
                       for (_s2, s3, _s4) in cols[1:]):
                failures.append(f"page-0 dome dump at frame {n}: the 10 "
                                "follower columns do not all have the "
                                "sticky bit with no own height")
        elif 1 <= p <= 8:
            if not all(s3 & 0x3f == 0 for (_s2, s3, _s4) in cols):
                failures.append(f"page-{p} dome dump at frame {n}: some "
                                "column has SCB3 height != 0 (the dome "
                                "should be hidden on pages 1..8)")
        else:
            failures.append(f"dome dump at frame {n}: page unknown ({p})")
    # the rebuilt dome: the last dump (the second page 0) must equal the
    # first page-0 dump word for word (SCB2/3/4 all 11 columns).
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
                    x0, x1 = int(w * lay.d.DOME_X / 320), int(w * (lay.d.DOME_X + 176) / 320)
                    y0, y1 = int(h * lay.d.DOME_Y / 224), int(h * (lay.d.DOME_Y + 128) / 224)
                    return sum(1 for yy in range(y0, y1) for xx in range(x0, x1)
                               if max(im.getpixel((xx, yy))[:3]) > 40)
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
    if failures:
        print("FAIL flow-pages:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS flow-pages: pages 0..8 -> 0 in order, one turn every 295 "
          "frames, every sampled frame's rows match the model, the dome is "
          "chained on page 0, hidden on pages 1..8, and rebuilt word-equal "
          "after the wrap")
    return 0


def check_pages_c(title, domes):
    """M6 Task 6, proof 4 (flow-pages-c, MVS, no coin/Start): a C press on
    MAME frames 450 and 550 turns the page 0 -> 1 -> 2 on those frames
    (within 2 frames), and title_t resets to 0 at each turn. With no BIOS
    logo the MVS title starts at ~frame 299, so page 0 spans ~299..592 —
    both C taps land inside it. The dome dumps at pages 0, 1, 2 prove the page-0 chain
    vs the hidden pages (proof 3's second half)."""
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
    # the dome dumps at the pages 0, 1, 2 PINs: page 0's chain vs the
    # hidden pages.
    if not domes:
        failures.append("no dome dumps on the pages-c run")
    else:
        seen_p0 = False
        for n in sorted(domes):
            _fc, cols, p = domes[n]
            if p == 0:
                seen_p0 = True
                if not all(s3 & (1 << 6) and s3 & 0x3f == 0
                           for (_s2, s3, _s4) in cols[1:]):
                    failures.append(f"page-0 dome dump at frame {n}: the "
                                    "followers do not carry the sticky bit")
            elif 1 <= p <= 8:
                if not all(s3 & 0x3f == 0 for (_s2, s3, _s4) in cols):
                    failures.append(f"page-{p} dome dump at frame {n} has "
                                    "columns with SCB3 height != 0 (the "
                                    "dome must be hidden on pages 1..8)")
        if not seen_p0:
            failures.append("no page-0 dome dump on the pages-c run")
    if failures:
        print("FAIL flow-pages-c:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS flow-pages-c: C at 450 and 550 turned the page 0 -> 1 -> 2 "
          "on those frames (title_t reset to 0), the dome is hidden on "
          "pages 1 and 2")
    return 0


def check_mvs(mvs_mode, mrecs, samples, title):
    """the M6 Task 2/3 MVS legs. mrecs: [(n, fc, flag, timer)] from the
    probe's M lines; samples: {n: (fc, rows)} from the F blocks. The
    confirmed numbers (2026-10-17) we assert: bios_mvs_flag == 0x80 all the
    way; a "Coin 1" hold on MAME frames 1500..1504 sets the compulsion timer
    to BCD 0x30; with no Start the BIOS's own player_start (countdown out)
    makes hud_framecnt 1 at frame 3312 (`flow-mvs`); with "1 Player Start"
    on 1800..1804 as well it becomes 1 at frame 1802 (`flow-mvs-start`). The
    M6 Task 3 proofs: the title's row 9 says INSERT COIN before the coin and
    PRESS START after it (each blinking, never the other), row 28 is blank
    before the coin and shows the BCD timer's digits after it, matching the
    timer byte read from RAM in the same frame."""
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
    # here compares like with like: the title's drawn row 9 digits against
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
    # coin, so the row-9 prompt (page 0 only) must be checked on page-0
    # frames. The T records carry the page read in the same frame; row 28's
    # countdown is page-independent and is checked on every page.
    page_at = dict((n, p) for (n, (_fc, p, _t, _c)) in title.items())
    r28_seen = []
    r9_bad = []
    for n in sorted(post):
        fc, rows = post[n]
        if fc != 0:
            continue
        # M6 Task 6: page 0's row 9 alternates every 64 frames (t & 64)
        # between the prompt and "B TO CHANGE LEVEL"; the post-coin prompt
        # is PRESS START (the MVS countdown is live), never the "off" blank
        # of Task 3's blink. Pages 1..8 do not draw row 9 (title.c starts
        # them on row 6) — the gate on page_at keeps the check on page 0.
        if page_at.get(n, 0) == 0:
            r9 = rows[PROMPT_ROW]
            if r9 not in (ROW9_ON, ROW9_B):
                r9_bad.append((n, r9))
        # the countdown, page-independent (HUD-layout Task 3: row 28 under
        # the dome; the probe reads it clean — the HUD rows are read last)
        digits = rows[28][ROW28_LO:ROW28_HI]
        if digits.strip():
            r28_seen.append((n, digits))
            # the drawn digits are exactly the timer byte read in the same
            # frame: high nibble then low nibble, '0' + n (the task's "R" —
            # the FIXMAP read back and the RAM read agree on every sampled
            # frame).
            timer = timer_at.get(n)
            if timer is not None and digits != "%02x" % timer:
                failures.append(f"row 28 shows {digits!r} at frame {n} but "
                                f"the compulsion timer reads {timer:02x} in "
                                "the same frame")
    seen_coin, seen_b = False, False
    for n, (fc, rows) in sorted(pre.items()):
        # M6 Task 6: pre-coin (credits 1) row 9 alternates INSERT COIN with
        # "B TO CHANGE LEVEL" every 64 frames, on page 0 only.
        if page_at.get(n, 0) != 0:
            continue
        if rows[PROMPT_ROW] == ROW9_COIN:
            seen_coin = True
        elif rows[PROMPT_ROW] == ROW9_B:
            seen_b = True
        else:
            failures.append(f"pre-coin row 9 at frame {n}: {rows[PROMPT_ROW]!r}")
        if rows[28] != ROW9_OFF:
            failures.append(f"pre-coin row 28 at frame {n} is not blank: "
                            f"{rows[28]!r}")
    if not seen_coin:
        failures.append("the pre-coin title never showed 'INSERT COIN' on "
                        "row 9")
    if not seen_b:
        failures.append("the pre-coin title never showed 'B TO CHANGE "
                        "LEVEL' on row 9 (the t & 64 alternation)")
    if not post:
        failures.append("no post-coin title rows were sampled")
    for n, r9 in r9_bad:
        failures.append(f"post-coin row 9 at frame {n}: {r9!r}")
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
          f"title row 9 INSERT COIN then PRESS START (each blinking), row 28 "
          f"shows the timer's digits on all {len(r28_seen)} sampled frames "
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
    if nrs[0][1] != 1:
        failures.append(f"first game frame was fc {nrs[0][1]}, expected 1")
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
        # page 1) within 600 MAME frames of GAME OVER. The probe samples
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
            # M6 Task 7: the returned title opens on page 1 (HIGH SCORES),
            # whose row 9 is blank — only a page-0 return shows the prompt
            # on row 9.
            if back[1][6].strip() == "HIGH SCORES":
                pass
            else:
                for r9 in (back[1][PROMPT_ROW],):
                    if r9 not in (ROW9_ON, ROW9_COIN, ROW9_B):
                        failures.append(f"post-return row 9: {r9!r}")
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

# page 0's level-name row (HUD-layout Task 3: row 5), drawn by the title
# from flow_level: the checker reads the SAME byte from RAM (the L records)
# and compares the drawn row 5 against the centred level name — the
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


# ---- M6 Task 9: the backup-RAM high-score table (flow_best) ----

# the 18-byte table, exactly as src/best.c lays it out: u32 magic 'ESRG'
# (0x45535247), u32 score10[3], u16 sum = the 16-bit wrap-around byte sum
# of the 16 bytes before it. best_valid mirrors best.c:
# magic right AND every score <= SCORE_MAX (9,999,999) AND the sum right.
BEST_MAGIC = 0x45535247
BEST_SCORE_MAX = 9999999


def best_valid(hexbytes):
    """the probe's <36 hex chars> as best_valid() sees them: 1 if the
    magic and the sum are right and every score is <= SCORE_MAX."""
    if len(hexbytes) != 36:
        return 0
    try:
        b = bytes(int(hexbytes[i:i + 2], 16) for i in range(0, 36, 2))
    except ValueError:
        return 0
    if int.from_bytes(b[0:4], "big") != BEST_MAGIC:
        return 0
    for i in range(3):
        if int.from_bytes(b[4 + 4 * i:8 + 4 * i], "big") > BEST_SCORE_MAX:
            return 0
    checksum = sum(b[0:16]) & 0xffff
    return int.from_bytes(b[16:18], "big") == checksum


def best_row_value(n, bests):
    """the model's best value for a sampled best record n, as a string."""
    _fc, b0, b1, b2, hexb = bests[n]
    return {0: b0, 1: b1, 2: b2}


# the page 1..8 title headers (pages[1..8][0]), used to recognise a drawn
# non-page-0 title without relying on the RAM page byte alone (the BIOS
# preamble leaves page 0 in RAM and blank rows; the drawn text is the
# truth).
PAGE_TITLES = ("HIGH SCORES", "CONTROLS", "DEFEND THE DOME", "LEVELS",
               "RADAR", "CREDITS", "BUILT WITH")


def title_frame_ok(n, rows, title):
    """is (n, rows) a REAL title sample? fc 0, and either the drawn
    page-0 row 3 is "E-SRG" or the T record's page is 1..8 with a drawn
    page header on row 6 (the BIOS preamble's blank rows / stale page 0
    are rejected)."""
    if rows[3] == ROW3:
        return True
    if n in title and 1 <= title[n][1] <= 8:
        return rows[6].strip() in PAGE_TITLES
    return False


def check_best_mvs(mvs_records, samples, title, levels, bests, scores, go,
                   nvram_leg=1):
    """the M6 Task 9 proofs 1-3 (best-mvs, three MVS runs):
    - run 1 (nvram_leg 1): the centred game to GAME OVER (coin at 1500,
      Start at 1800), mis.score10 > 0 at GAME OVER, the returned title
      opens on page 1 (HIGH SCORES) whose NORMAL row reads score10 * 10,
      and flow_best in RAM is valid and holds it (EASY/HARD 0).
    - run 2 (nvram_leg 2, sharing run 1's nvram): the FIRST page-0 frame's
      row 7 reads the same number (score10 * 10 of the game run 1 played),
      before any game.
    - run 3 (nvram_leg 3, a fresh nvram): the first page-0 frame's row 7
      reads "0" — no garbage, no crash.
    Mutation (a) — never call best_update — fails run 1's NORMAL row ==
    score10*10 (0 != a positive score); mutation (b) — reset the table on
    every entry — fails run 1's NORMAL row too (the entry's best_reset
    wiped the update) and run 2's row 7 (a fresh reset reads 0, not the
    persisted score); mutation (c) — pass zeros to title_rows — fails the
    drawn-vs-table compare on every title frame of every run (the drawn
    row 7 never matches the RAM table). The run-2/3 keys flow in via
    BEST_NVRAM_LEG (boot_test.sh) or the nvram_leg argument."""
    failures = []
    if not mvs_records:
        failures.append("probe wrote no MVS input records")
        return 1
    if not any(flag == 0x80 for (_n, _fc, flag, _t) in mvs_records):
        failures.append("bios_mvs_flag was never 0x80 (not an MVS run?)")
    if not samples:
        failures.append("no fix-row samples")
    if not bests:
        failures.append("no B records (flow_best never read)")
    if failures:
        print("FAIL best-mvs:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    # the first page-0 title frame (fc 0, T record page 0) and its B
    # record. Page 0's row 7 draws best[level] * 10 for the title's level
    # — NORMAL (1) on a fresh entry, so the row-7 key is the RAM table's
    # NORMAL score (b1). Every leg proves the drawn row 7 equals
    # title_model's with the RAM table and the same frame's level (this is
    # what mutation (c) breaks).
    first_p0 = None
    for n4 in sorted(samples):
        fc, rows4 = samples[n4]
        if fc != 0 or n4 not in title:
            continue
        if title[n4][1] == 0 and title_frame_ok(n4, rows4, title):
            first_p0 = (n4, rows4)
            break
    if first_p0 is None:
        failures.append("no page-0 title frame sampled (row 7's score "
                        "never observed)")
    # the model-vs-drawn compare on every REAL title frame: the drawn
    # rows must equal title_model's for the RAM best table, the level
    # (from the same frame's L record, sanitized as flow_level_get does)
    # and the T record's page/t/credits. This is the check that mutation
    # (c) breaks on every leg.
    for n6 in sorted(bests):
        if n6 not in samples:
            continue
        fc6, rows6 = samples[n6]
        if fc6 != 0 or n6 not in title:
            continue
        if not title_frame_ok(n6, rows6, title):
            continue
        _p6, _t6, _c6 = title[n6][1], title[n6][2], title[n6][3]
        _bfc, bb0, bb1, bb2, _hexb = bests[n6]
        lv = 1
        if n6 in levels:
            _lfc, valid, raw = levels[n6]
            if valid == 0x53 and raw <= 2:
                lv = raw
        want6 = tm.title_rows(_p6, lv, _t6, [bb0, bb1, bb2], _c6)
        for r in range(TITLE_ROWS):
            # row 28 is the one row title_rows never fills (the MVS
            # countdown, flow.c, owns it — the model leaves it blank, and
            # on MVS post-coin the drawn digits are the countdown's, not a
            # model row); the checker compares it separately (check_mvs).
            # Every other model row 0..27 must match exactly, whatever the
            # page (page 0's prompt sits on row 9 and IS in the model).
            if r == 28:
                continue
            if rows6[r] != want6[r]:
                failures.append(f"title frame {n6} (page {_p6}): "
                                f"row {r} != title_model with the "
                                f"RAM best ({bb0},{bb1},{bb2}) and "
                                f"level {lv}, t {_t6}")
                break

    if nvram_leg == 1:
        # ---- run 1: the full game proof ----
        if go is None:
            failures.append("GAME OVER was never seen (expected at fc "
                            "~20240 under Task 1's seed 0xadf9)")
            return 1 if failures else 0
        go_fc = go[1]
        if not (20125 <= go_fc <= 20355):
            failures.append(f"GAME OVER came at fc {go_fc}, expected ~20240 "
                            "(the scoring MVS game under Task 1's seed)")
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
            if sc10 <= 0:
                failures.append(f"mis.score10 at GAME OVER reads {sc10}, "
                                "expected > 0 (the centred game's score)")
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
            if 1 <= title[n2][1] <= 8:
                back = (n2, rows)
                break
        if back is None:
            failures.append("no post-return title rows sampled on a "
                            "page-1..8 title frame")
        else:
            n2, rows = back
            page = title[n2][1]
            if page != 1:
                failures.append(f"the returned title opened on page "
                                f"{page}, expected 1 (HIGH SCORES)")
            _t, _c = title[n2][2], title[n2][3]
            # the table check keys on the returned title's B record (the
            # GO frame's B was read a tick before the cart's update landed
            # — the probe reads RAM at the start of the MAME frame).
            b1 = bests[n2][2]              # NORMAL's score in the table
            want_row = " " * ((40 - len(str(sc10 * 10))) // 2) + \
                str(sc10 * 10) + " " * (40 - len(str(sc10 * 10)) -
                                        (40 - len(str(sc10 * 10))) // 2)
            if b1 != sc10:
                failures.append(f"flow_best NORMAL reads {b1} but "
                                f"mis.score10 at GAME OVER was {sc10}")
            if rows[18] != want_row:
                failures.append(f"returned title frame {n2}: row 18 "
                                f"(NORMAL's score) is {rows[18]!r}, "
                                f"expected {want_row!r} (score10 * 10)")
            if not best_valid(bests[n2][4]):
                failures.append(f"flow_best at frame {n2} is not a valid "
                                f"table ({bests[n2][4]!r})")
            if bests[n2][1] != 0 or bests[n2][3] != 0:
                failures.append(f"flow_best EASY/HARD read "
                                f"{bests[n2][1]}/{bests[n2][3]} after the "
                                "game, expected 0/0 (only NORMAL was "
                                "played)")
            # the drawn page-1 rows equal the model's, with the best table
            # from the same frame's B record (post-return samples only)
            for n3 in sorted(bests):
                if n3 not in samples or n3 < go[0] + 280:
                    continue
                fc3, rows3 = samples[n3]
                if fc3 != 0 or n3 not in title:
                    continue
                if not title_frame_ok(n3, rows3, title):
                    continue
                _p3, _t3, _c3 = title[n3][1], title[n3][2], title[n3][3]
                _bfc, bb0, bb1, bb2, _hexb = bests[n3]
                want3 = tm.title_rows(_p3, 1, _t3, [bb0, bb1, bb2], _c3)
                for r in range(TITLE_ROWS):
                    if r == 28:
                        continue         # row 28 is the MVS countdown (flow.c)
                    if rows3[r] != want3[r]:
                        failures.append(f"returned title frame {n3}: row "
                                        f"{r} != title_model page {_p3} with "
                                        f"the RAM best ({bb0},{bb1},{bb2}), "
                                        f"t {_t3}")
                        break
    elif nvram_leg == 2:
        # ---- run 2: the persisted table (shares run 1's nvram) ----
        # nothing may have started a game: the run's fc stays 0, and the
        # first page-0 frame's row 7 shows the table's NORMAL score * 10
        # (the score run 1's game stored at GAME OVER — the title's level
        # is NORMAL on a fresh entry). The compare above already proved the
        # drawn row 7 == the RAM table; here the RAM table itself must
        # still hold run 1's score (a reset-on-entry mutation would zero
        # it).
        if any(fc >= 1 for (_fc, _rows) in samples.values()):
            failures.append("run 2 started a game (fc >= 1); only the "
                            "title may run")
        b0 = None
        if first_p0 is not None and first_p0[0] in bests:
            b0 = bests[first_p0[0]][2]
        if b0 is None or b0 == 0:
            failures.append(f"run 2's flow_best NORMAL reads {b0}, "
                            "expected the persisted score from run 1 "
                            "(> 0)")
        if first_p0 is None or not best_valid(bests[first_p0[0]][4]):
            failures.append("run 2's flow_best is not a valid table "
                            f"({'' if first_p0 is None else bests[first_p0[0]][4]!r})")
    elif nvram_leg == 3:
        # ---- run 3: a fresh nvram — the table resets to zeros ----
        if any(fc >= 1 for (_fc, _rows) in samples.values()):
            failures.append("run 3 started a game (fc >= 1); only the "
                            "title may run")
        b0 = None
        if first_p0 is not None and first_p0[0] in bests:
            b0 = bests[first_p0[0]][2]
        if b0 != 0:
            failures.append(f"run 3's flow_best NORMAL reads {b0}, "
                            "expected 0 (a fresh nvram: no garbage, no "
                            "crash)")
    if failures:
        print("FAIL best-mvs:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    if nvram_leg == 1:
        print(f"PASS best-mvs (run 1): game began at MAME frame {first}, "
              f"GAME OVER at fc {go_fc} with mis.score10 {sc10}; the "
              "returned title opens on page 1 whose NORMAL row reads "
              "score10 * 10 (flow_best in RAM valid and holding it, "
              "EASY/HARD 0); the first page-0 frame's row 7 reads the "
              "table for the title's level (NORMAL)")
    elif nvram_leg == 2:
        print("PASS best-mvs (run 2): with run 1's nvram, the first "
              "page-0 frame's row 7 reads the persisted score before any "
              "game (flow_best valid)")
    else:
        print("PASS best-mvs (run 3): with a fresh nvram, the first "
              "page-0 frame's row 7 reads 0 (no garbage, no crash)")
    return 0


def check_best_aes(samples, title, levels, bests, scores, go, cards,
                   card_leg=1):
    """the M6 Task 10 proofs 1-3 (best-aes, three AES runs):
    - run 1 (card_leg 1): the centred game to GAME OVER (~fc 27142
      Start at 600..604), mis.score10 > 0 at GAME OVER; the card-log
      answers are 0x81 (the fresh card is unformatted), then FORMAT 0,
      then SAVE 0; the returned title opens on page 1 (HIGH SCORES) whose
      NORMAL row reads score10 * 10 (flow_best in RAM valid and holding
      it).
    - run 2 (card_leg 2, sharing run 1's -memcard file with a FRESH
      nvram/cfg — a power-off): the load answers 0 (the card is now
      formatted and holds the save), and the FIRST page-0 frame's row 7
      reads the same number (score10 * 10 of the game run 1 played),
      before any game — the card, not the per-boot backup RAM, kept it.
    - run 3 (card_leg 3, no -memcard): the load answers 0x80, the first
      page-0 frame's row 7 reads "0", no crash; and the game to GAME
      OVER still keeps the score in backup RAM for that run (flow_best in
      RAM holds it, and page 1's NORMAL row shows it).
    The checks are keyed so each task's mutation fails one: (a) never
    save — run 1's page-1 NORMAL row is 0, and run 2's first page-0
    frame would show "0"/a missing slot; (b) never load — run 2's first
    page-0 row 7 is 0 (nothing was copied from the card) and run 1's
    row-7 gets the empty table; (c) skip the FORMAT retry on 0x81 — run
    1's A records lack the "0:0" FORMAT / second "3:0" SAVE, or the save
    failed (a fresh unformatted card cannot be saved to)."""
    failures = []
    if not samples:
        failures.append("no fix-row samples")
    if not bests:
        failures.append("no B records (flow_best never read)")
    if card_leg != 2 and not scores:
        # runs 1 and 3 play a game to GAME OVER whose mis.score10 is the
        # proof's score; run 2 (the title-only persistence run) never
        # plays, so it has no SC record by design
        failures.append("no SC record (mis.score10 at GAME OVER never "
                        "read)")
    if card_leg == 2 and go is not None:
        failures.append("run 2 started a game (fc >= 1, GO seen); only "
                        "the title may run")
    if failures:
        print("FAIL best-aes:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    # the first page-0 title frame (fc 0, T record page 0 and the drawn
    # title), and its B/A records. Page 0's row 7 draws best[level] * 10
    # for the title's level — NORMAL (1) on a fresh entry — so the row-7
    # key is the RAM table's NORMAL score (b1).
    first_p0 = None
    for n4 in sorted(samples):
        fc, rows4 = samples[n4]
        if fc != 0 or n4 not in title or title[n4][1] != 0:
            continue
        if title_frame_ok(n4, rows4, title):
            first_p0 = (n4, rows4)
            break
    if first_p0 is None:
        failures.append("no page-0 title frame sampled (row 7's score "
                        "never observed)")

    # the model-vs-drawn compare on every REAL title frame: the drawn
    # rows must equal title_model's for the RAM best table, the level
    # (same frame's L record, sanitized as flow_level_get does) and the T
    # record's page/t/credits. This is what the "pass zeros to
    # title_rows"-style mutations break.
    for n6 in sorted(bests):
        if n6 not in samples:
            continue
        fc6, rows6 = samples[n6]
        if fc6 != 0 or n6 not in title:
            continue
        if not title_frame_ok(n6, rows6, title):
            continue
        _p6, _t6, _c6 = title[n6][1], title[n6][2], title[n6][3]
        _bfc, bb0, bb1, bb2, _hexb = bests[n6]
        lv = 1
        if n6 in levels:
            _lfc, valid, raw = levels[n6]
            if valid == 0x53 and raw <= 2:
                lv = raw
        want6 = tm.title_rows(_p6, lv, _t6, [bb0, bb1, bb2], _c6)
        for r in range(TITLE_ROWS):
            if rows6[r] != want6[r]:
                failures.append(f"title frame {n6} (page {_p6}): "
                                f"row {r} != title_model with the "
                                f"RAM best ({bb0},{bb1},{bb2}) and "
                                f"level {lv}, t {_t6}")
                break

    # the card-log answers, from the A records. The probe samples the log
    # every frame from GO + 2 while the session is still running (the
    # BIOS card calls span several frames); the LAST A record with a
    # LOAD in it before the return carries the complete sequence.
    # (BIOS-preamble title samples read the .data garbage 0:0,0:0,...
    # before the cart's first entry re-copies card_log — those have no
    # LOAD command and are ignored.) Runs 2/3 only ever make the entry
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
    elif card_leg == 2:
        load_ans = next((a for (c, a) in log_pairs if c == 2), None)
        if load_ans != 0:
            failures.append(f"run 2's load answer is {load_ans}, expected 0 "
                            "(the card holds run 1's save)")
    else:
        load_ans = next((a for (c, a) in log_pairs if c == 2), None)
        if load_ans != 0x80:
            failures.append(f"run 3's load answer is {load_ans}, expected "
                            "0x80 (no card inserted)")

    if card_leg == 1:
        # ---- run 1: the full game proof ----
        if go is None:
            failures.append("GAME OVER was never seen (expected at fc "
                            "~17818 under Task 1's seed 0xaede)")
        if failures:
            print("FAIL best-aes:")
            for f_ in failures:
                print("  - " + f_)
            return 1
        go_fc = go[1]
        if not (17705 <= go_fc <= 17935):
            failures.append(f"GAME OVER came at fc {go_fc}, expected "
                            "~17818 (the scoring AES game under Task 1's "
                            "seed)")
        _n, sc10 = scores[sorted(scores)[0]]
        if sc10 <= 0:
            failures.append(f"mis.score10 at GAME OVER reads {sc10}, "
                            "expected > 0 (the centred game's score)")
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
            _p, t, _c = title[n2][1], title[n2][2], title[n2][3]
            if _p != 1:
                failures.append(f"the returned title opened on page {_p}, "
                                "expected 1 (HIGH SCORES)")
            b1 = bests[n2][2] if n2 in bests else None
            want_row = " " * ((40 - len(str(sc10 * 10))) // 2) + \
                str(sc10 * 10) + " " * (40 - len(str(sc10 * 10)) -
                                        (40 - len(str(sc10 * 10))) // 2)
            if b1 is None:
                failures.append("no B record on the returned title frame")
            elif b1 != sc10:
                failures.append(f"flow_best NORMAL reads {b1} but "
                                f"mis.score10 at GAME OVER was {sc10}")
            if rows[18] != want_row:
                failures.append(f"returned title frame {n2}: row 18 "
                                f"(NORMAL's score) is {rows[18]!r}, "
                                f"expected {want_row!r} (score10 * 10)")
            if n2 in bests and not best_valid(bests[n2][4]):
                failures.append(f"flow_best at frame {n2} is not a valid "
                                f"table ({bests[n2][4]!r})")
            if n2 in bests and (bests[n2][1] != 0 or bests[n2][3] != 0):
                failures.append(f"flow_best EASY/HARD read "
                                f"{bests[n2][1]}/{bests[n2][3]} after the "
                                "game, expected 0/0")
    elif card_leg == 2:
        # ---- run 2: the persisted card (shares run 1's file) ----
        if any(fc >= 1 for (_fc, _rows) in samples.values()):
            failures.append("run 2 started a game (fc >= 1); only the "
                            "title may run")
        b0 = None
        if first_p0 is not None and first_p0[0] in bests:
            b0 = bests[first_p0[0]][2]
        if b0 is None or b0 == 0:
            failures.append(f"run 2's flow_best NORMAL reads {b0}, "
                            "expected the persisted score from run 1 "
                            "(> 0)")
        if first_p0 is not None and first_p0[0] in bests \
           and not best_valid(bests[first_p0[0]][4]):
            failures.append("run 2's flow_best is not a valid table")
    else:
        # ---- run 3: no card at all ----
        # the first page-0 frame's row 7 reads "0" (the load answered
        # 0x80, nothing was copied: no garbage, no crash), and the game
        # to GAME OVER STILL keeps the score in backup RAM for the run:
        # the returned title's page 1 NORMAL row shows score10 * 10 and
        # flow_best in RAM holds it.
        if any(fc >= 1 for (_fc, _rows) in samples.values()) and go is None:
            failures.append("run 3 started a game without a GO record")
        b0 = None
        if first_p0 is not None and first_p0[0] in bests:
            b0 = bests[first_p0[0]][2]
        if b0 != 0:
            failures.append(f"run 3's flow_best NORMAL reads {b0} on the "
                            "first page-0 frame, expected 0 (no card: no "
                            "garbage, no crash)")
        if go is None:
            failures.append("run 3: GAME OVER was never seen (expected at "
                            "fc ~17818 under Task 1's seed 0xaede: a game "
                            "to GAME OVER still keeps the score in backup "
                            "RAM)")
        else:
            go_fc = go[1]
            if not (17705 <= go_fc <= 17935):
                failures.append(f"run 3: GAME OVER came at fc {go_fc}, "
                                "expected ~17818 (the scoring AES game "
                                "under Task 1's seed)")
            _n, sc10 = scores[sorted(scores)[0]]
            if sc10 <= 0:
                failures.append(f"run 3: mis.score10 at GAME OVER reads "
                                f"{sc10}, expected > 0")
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
                failures.append("run 3: no post-return title rows sampled")
            else:
                n2, rows = back
                _p, _t, _c = title[n2][1], title[n2][2], title[n2][3]
                want_row = " " * ((40 - len(str(sc10 * 10))) // 2) + \
                    str(sc10 * 10) + " " * (40 - len(str(sc10 * 10)) -
                                            (40 - len(str(sc10 * 10))) // 2)
                if n2 in bests and bests[n2][2] != sc10:
                    failures.append(f"run 3: flow_best NORMAL reads "
                                    f"{bests[n2][2]} but mis.score10 at "
                                    f"GAME OVER was {sc10}")
                if rows[18] != want_row:
                    failures.append(f"run 3 returned title frame {n2}: row "
                                    f"18 (NORMAL's score) is {rows[18]!r}, "
                                    f"expected {want_row!r} (score10 * 10)")
    if failures:
        print("FAIL best-aes:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    if card_leg == 1:
        print(f"PASS best-aes (run 1): game began, GAME OVER at fc {go_fc} "
              f"with mis.score10 {sc10}; the save's answers were "
              f"{[(hex(c), hex(a)) for (c, a) in log_pairs]} (fresh card: "
              "0x81 then FORMAT 0 then SAVE 0); the returned title opens "
              "on page 1 whose NORMAL row reads score10 * 10 (flow_best "
              "in RAM valid and holding it)")
    elif card_leg == 2:
        print("PASS best-aes (run 2): with run 1's card and a fresh "
              "nvram, the load answered 0 and the first page-0 frame's "
              "row 7 reads the persisted score before any game")
    else:
        print("PASS best-aes (run 3): with no card, the load answered "
              "0x80, the first page-0 frame's row 7 reads 0 (no garbage, "
              "no crash)")
    return 0


def check_best_return(samples, title, bests, scores, go):
    """the M6 Task 9 proof 3 (flow-return, AES): the Up-held game to GAME
    OVER at fc 17525 under Task 1's seed (6509 with RNG_SEED; score 0), and
    the returned title's page 1 shows
    score10 * 10 for NORMAL; EASY and HARD stay 0. (0 is fine — the task
    says state it.) The drawn rows equal title_model's page 1 with the
    best table read in the same frame."""
    failures = []
    if not bests:
        failures.append("no B records (flow_best never read)")
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
        if fc == 0 and n2 in title and 1 <= title[n2][1] <= 8 \
           and title_frame_ok(n2, rows, title):
            back = (n2, rows)
            break
    if back is None:
        failures.append("no post-return page-1 title rows sampled")
    else:
        n2, rows = back
        _p, t, _c = title[n2][1], title[n2][2], title[n2][3]
        _bfc, b0, b1, b2, _hexb = bests[n2]
        want = tm.title_rows(1, 1, t, [b0, b1, b2], _c)
        for r in range(TITLE_ROWS):
            if rows[r] != want[r]:
                failures.append(f"returned title frame {n2}: row {r} != "
                                "title_model page 1 with the RAM best "
                                f"({b0},{b1},{b2}), t {t}")
                break
        want_row = " " * ((40 - len(str(sc10 * 10))) // 2) + \
            str(sc10 * 10) + " " * (40 - len(str(sc10 * 10)) -
                                    (40 - len(str(sc10 * 10))) // 2)
        if rows[18] != want_row:
            failures.append(f"returned title frame {n2}: row 18 "
                            f"(NORMAL's score) is {rows[18]!r}, expected "
                            f"{want_row!r} (score10 * 10)")
        if b0 != 0 or b2 != 0:
            failures.append(f"flow_best EASY/HARD read {b0}/{b2} after the "
                            "Up-held game, expected 0/0")
    if failures:
        print("FAIL flow-return best:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS flow-return best: the Up-held game's score at GAME OVER "
          f"was {sc10} (score10), and the returned title's page 1 shows "
          f"its score x 10 for NORMAL (EASY and HARD 0)")
    return 0


def check_flow_level(records, samples, title, levels, games, first=None,
                     seed=None):
    """the M6 Task 7 proof 1 (flow-level, AES, no Start until frame 1400):
    B on MAME frame 1000 -> row 5 reads "HARD" from frame 1002 on (within 2
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
    # ---- 1d. the row-9 prompt with title_t 0: page 0's row 9 must show
    # the prompt, never 'B TO CHANGE LEVEL', on any sampled title frame
    # whose title_t is 0 (the prompt's t&64 alternation is off at t 0).
    for n in sorted(samples):
        if n not in title:
            continue
        fc, rows = samples[n]
        _tfc, page, t, cred = title[n]
        if fc == 0 and rows[3] == ROW3 and page == 0 and t == 0:
            if rows[PROMPT_ROW] not in (ROW9_ON, ROW9_COIN):
                failures.append(f"page 0, t 0 at frame {n}: row 9 is "
                                f"{rows[PROMPT_ROW]!r}, expected the prompt")
    if failures:
        print("FAIL flow-level:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print("PASS flow-level: B taps at 1000/1100/1200/1300 cycled NORMAL -> "
          "HARD -> EASY -> NORMAL -> HARD on page 0 with title_t 0 (each "
          "within 2 frames, drawn row 5 matching), Start at 1400 began a "
          "HARD game (rules.level and mis.level 2)")
    return 0


def check_flow_return(records, samples, title, levels, games, go, bests,
                      seed=None):
    """the M6 Task 7 proofs 2 + 3 (flow-return, AES): the Up-held game to
    GAME OVER at fc 17525 under Task 1's seed (NORMAL, no A; 6509 with
    RNG_SEED), the 295-frame window expires, and
    the title that comes back opens on page 1 (HIGH SCORES): title_page
    reads 1 and the drawn title rows equal title_model's page 1. The level
    is still the chosen one (the game ran at NORMAL: rules.level and
    mis.level read 1 on the first game frame, and flow_level reads 1 on the
    post-return title). Proof 3 rides on the same run: a fresh boot (a run
    whose nvram was never touched) shows page 0 and NORMAL before Start.
    M6 Task 9: the returned title draws the best table from backup RAM
    (flow_best), so the model compare uses the B record read in the same
    frame (proof 3's "the title shows the game's score")."""
    failures = []
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
    # ---- proof 2c: the title that comes back opens on page 1 (HIGH
    # SCORES): the first sampled frame whose cart title is drawn (fc 0 and
    # — from the T records — a real title page, or row 3's "E-SRG" for
    # page 0) at/after the return, its page reads 1, and all 28 drawn rows
    # equal the model's page 1 (level NORMAL, the t and credits read in
    # the same frame).
    back = None
    for n in sorted(samples):
        fc, rows = samples[n]
        if fc != 0:
            continue
        if rows[3] == ROW3 or (n in title and 1 <= title[n][1] <= 8):
            if mod0 is None or n >= mod0[0]:
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
            _fc, page, t, cred = title[n]
            if page != 1:
                failures.append(f"the returned title opened on page {page}, "
                                "expected 1 (HIGH SCORES)")
            # M6 Task 9: the drawn best table is the backup-RAM one read in
            # the same frame (fall back to zeros only if no B record — the
            # pre-Task-9 build's behaviour).
            bb = [0, 0, 0]
            if n in bests:
                _bfc, bb0, bb1, bb2, _hexb = bests[n]
                bb = [bb0, bb1, bb2]
            want = tm.title_rows(1, 1, t, bb, cred)
            for r in range(TITLE_ROWS):
                if rows[r] != want[r]:
                    failures.append(f"returned title frame {n}: row {r} != "
                                    f"title_model page 1 (t {t}, credits "
                                    f"{cred}, best {bb}):\n  drawn "
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
    # entry opened on page 0, not the HIGH SCORES page, because the GAME
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
          "returned title opens on page 1 (HIGH SCORES) with the level kept")
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
            return check_pages(samples, title, domes)
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
        # page 0's blank gaps (M8 art pass): rows 6 and 8 are the blank
        # rows between the logo (2..5), the level (7) and the best (9).
        if rows[6] != " " * 40 or rows[8] != " " * 40:
            failures.append(f"title page-0 blank rows at frame {n}: "
                            f"row 6 {rows[6]!r}, row 8 {rows[8]!r}")
        # HUD-layout Task 3: page 0's prompt is row 9 now, alternating
        # every 64 frames between "PRESS START" (t & 64 clear) and "B TO
        # CHANGE LEVEL" (t & 64 set).
        if rows[PROMPT_ROW] == ROW9_ON:
            seen_on = True
        elif rows[PROMPT_ROW] == ROW9_B:
            seen_b = True
        else:
            failures.append(f"title row 9 at frame {n}: {rows[PROMPT_ROW]!r}")
        if rows[28] != " " * 40:
            failures.append(f"title row 28 at frame {n} is not blank: "
                            f"{rows[28]!r} (the countdown row must stay "
                            "blank on AES)")
    if not seen_on:
        failures.append("title never showed 'PRESS START' on row 9")
    if not seen_b:
        failures.append("title never showed 'B TO CHANGE LEVEL' on row 9 "
                        "(t & 64 alternation)")
    # every nonzero game-slot count during the title must be 0, and the
    # dome's SCB1 view tile must change (>= 5 distinct tiles) while turning.
    # (Both are sampled in the same title_sample as the rows, so gate them
    # on the row-3-confirmed title frames.)
    title_ns = set(n for (n, _rows) in title)
    for n, (fc, nonzero) in slots.items():
        if n in title_ns and nonzero != 0:
            failures.append(f"title frame {n} had {nonzero} game slots shown "
                            "(all must have SCB3 height 0)")
    dist = set(tile for (nn2, (fc, tile)) in views.items()
               if nn2 in title_ns)
    if len(dist) < 5:
        failures.append(f"the dome's SCB1 tile changed only {len(dist)} "
                        "distinct ways during the title (need >= 5)")
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
            # opens on the HIGH SCORES page (1), which draws no "E-SRG"
            # row — the "back" gate accepts a page-1 title too (the drawn
            # HIGH SCORES text on row 6, pages 1..8's first line).
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
