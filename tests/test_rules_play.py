"""src/ship.c + src/missiles.c + src/rules.c + src/radar.c (as
build/rules_sim) against the reference models of the Vectrex game
(tests/ship_model.py, mis_model.py, rules_model.py, radar_model.py): over
long seeded random games that run all the way to GAME OVER — with heavy
fire and with none — the C and the model must agree on every frame on the
broken set (which cells, and in what order), integrity, lives, score,
deaths (dead_t, dome_dead), the ship's cell, every missile's state, and
the radar's lock state (locked, lock_t, ellipse_bright — M5 Task 3).

run_both plays one game two ways from the same script of inputs: the C sim
(build/rules_sim) and the models, then compares their per-frame dumps."""
import os
import random
import subprocess

import mis_model as mm
import radar_model as rm
import rules_model as rm0
import ship_model as sm

ROOT = os.path.join(os.path.dirname(__file__), "..")
SIM = os.path.join(ROOT, "build", "rules_sim")
STICKS = [0, sm.UP, sm.DOWN, sm.LEFT, sm.RIGHT, sm.UP | sm.LEFT, sm.UP | sm.RIGHT,
          sm.DOWN | sm.LEFT, sm.DOWN | sm.RIGHT]
A = 16


def fresh(level):
    """fresh model objects as the C's (ship_reset/mis_reset/rules_reset)."""
    return sm.Ship(), mm.Missiles(level), rm0.Rules(level), rm.Radar()


def frame_model(state, inp, pressed):
    """one frame exactly as the C (rules_sim): rules_begin (which may take
    the turn: GAME OVER + A restarts, or a dead ship's countdown), then —
    only on a live frame — the ship's move, and the missiles update; then
    the rules_end death checks and integrity recast; then the radar's lock
    state (the Vectrex's lock_update after game_step)."""
    ship, mis, rules, radar = state
    busy = rules.begin(ship, mis, pressed)
    died = False
    fires = 0
    if not busy:
        ship.frame(inp, pressed)
    # e-srg.c's fire + missiles_update (the C's mis_update): while the early
    # branches took the turn (busy), the fire branch is skipped but the
    # missiles still step, land and break; launches wait for a live frame
    if not busy:
        if pressed & A:
            mis.fire_req = 1
        if mis.fire_req and not ship.left:
            fires = 1 if mis.fire(ship.cell) else 0
            mis.fire_req = 0
    mis.hits, mis.lands = [], []
    for o in mis.obj:                              # missiles_step
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
    for b in mis.obj[mm.NMIS:]:                    # collide
        if b.state != 1:
            continue
        for o in mis.obj[:mm.NMIS]:
            if o.state == 1 and o.phi == b.phi and o.ring == b.ring and b.r >= o.r:
                mis.hits.append((o.ring, o.phi, o.r))
                mis.kills = min(255, mis.kills + 1)
                mis.score = min(9999999, mis.score + rules.integ)
                o.state = b.state = 0
                break
    live = 0
    mis.sfx = 0                      # M7: the frame's sound events, as the C's
                                     # mis_update clears and gathers them
    if fires:
        mis.sfx |= mm.SFX_FIRE
    if mis.hits:
        mis.sfx |= mm.SFX_HIT
    for o in mis.obj[:mm.NMIS]:                    # landings break tiles
        if o.state == 2:
            c = mm.RING_END[o.ring - 1] if o.ring else 0
            while mm.CELL_PHI[c] != o.phi:
                c += 1
            mis.lands.append(c)
            if c not in ship.broken:     # a landing that broke a whole cell
                mis.dome_hits = min(255, mis.dome_hits + 1)  # counts as a hit
                mis.sfx |= mm.SFX_CRACK  # M7: and sounds the crack
            rules.break_cell(ship, c)
            o.state = 0
        if o.state:
            live += 1
    if rules.dead_t or rules.game_over:
        pass                                     # no launches while the ship is gone
    elif mis.timer:
        mis.timer -= 1
    elif live >= mm.V["wave_live"]:
        pass
    else:
        o = next(o for o in mis.obj if not o.state)
        mis.spawn(o, ship.broken)
        mis.timer = ((mm.V["spawn_gap"] + (mis.rand8() & 63)) * 59 + 25) // 50
    died = rules.end(ship, mis)
    mis.integ = rules.integ                  # r->integ_pct -> m->integ_pct
    rules._died = died
    radar.frame(ship, mis)                   # after the frame's logic
    return state


def model_line(state):
    ship, mis, rules, radar = state
    bstring = " ".join(map(str, rules.broken))
    if rules.broken:
        bstring = " " + bstring
    b = (f"b {rules.dead_t} {len(rules.broken)} {rules.lives} {rules.integ}"
         f" {rules.game_over} | {ship.cell} {ship.left} |{bstring}")
    lands = " ".join(map(str, mis.lands))
    if lands:
        lands = " " + lands
    l = (f"l {len(mis.lands)}{lands} | {mis.timer} {mis.kills} {mis.dome_hits} "
         f"{mis.score} |" +
         "".join(f" {o.state} {o.kind} {o.ring} {o.phi} {o.life} {o.r}"
                 for o in mis.obj) +
         f" | {mis.sfx}")                 # M7: the frame's sound-event bitmask
    e = (f"e {rules.dead_t} {len(rules.broken)} {rules.integ} {rules.dome_dead}"
         f" {rules.lives} {rules.game_over} | {1 if rules._died else 0}")
    return b, l, e, radar.line()


def run_both(seed, frames, fire_p, level=1, pre_broken=()):
    rng = random.Random(seed)

    def input_line():
        inp = rng.choice(STICKS)
        fire = rng.random() < fire_p
        jump = rng.random() < 0.01
        p = (A if fire else 0) | (sm.B if jump else 0)
        return inp | p, p

    script = [f"level {level}"] + [f"B {c}" for c in pre_broken]
    steps = []
    for _ in range(frames):
        inp, p = input_line()
        script.append(f"{inp} {p}")
        steps.append((inp, p))

    out = subprocess.run([SIM], input="\n".join(script) + "\n",
                         capture_output=True, text=True, check=True).stdout
    c_lines = out.splitlines()
    assert len(c_lines) == 4 * frames, (len(c_lines), 4 * frames)

    ship, mis, rules, radar = fresh(level)
    rules.saw_game_over = False            # reached GAME OVER at least once
    rules.seen_dome_death = False          # a dome death happened (M4-fixes Task 2)
    rules.game_over_integ = None           # the integrity at GAME OVER
    for c in pre_broken:
        rules.break_cell(ship, c)
    m_lines = []
    for inp, p in steps:
        frame_model((ship, mis, rules, radar), inp, p)
        if rules._died and rules.dome_dead:
            rules.seen_dome_death = True
        if rules.game_over:
            rules.saw_game_over = True
            if rules.game_over_integ is None:
                rules.game_over_integ = rules.integ
        m_lines.append(model_line((ship, mis, rules, radar)))
    return c_lines, m_lines, (ship, mis, rules, radar)


def assert_same(c_lines, m_lines):
    assert len(c_lines) == 4 * len(m_lines), (len(c_lines), len(m_lines))
    for i, m in enumerate(m_lines):
        c = tuple(f.split() for f in c_lines[4 * i:4 * i + 4])
        mm_ = tuple(line.split() for line in m)
        assert c == mm_, f"frame {i}:\n  C  {c}\n  M  {mm_}"


def test_random_games_to_game_over_match():
    # seed 2 at NORMAL passes the score's 6-kill wall (the dome dies: all 38
    # cells break), then keeps playing past the rebuild and the deaths, to
    # GAME OVER at frame ~18626. The other seeds and levels may not end
    # (EASY's dome deaths are free, HARD's games end early or the score
    # never unlocks the outer rings) — what must hold is that the C and the
    # model agree on every frame. The games walk the ship onto targeted
    # cells, so the radar locks on often (M5 Task 3): assert that here.
    c, m, (_, _, rules, radar) = run_both(2, 70000, 0.05, 1)
    assert_same(c, m)
    assert rules.saw_game_over, "seed 2 at NORMAL must reach GAME OVER"
    assert radar.lock_frames() >= 50, "seed 2 must produce radar lock-on frames"
    for seed in (4, 6):
        for level in (0, 1, 2):
            c, m, _ = run_both(seed, 50000, 0.05, level)
            assert_same(c, m)


def test_heavy_fire_matches():
    # heavy fire: kills unlock the outer rings and the score races ahead;
    # the dome still dies (missiles land between shots) and the game ends —
    # both seeds reach GAME OVER, and each locks the radar on for at least 50
    # frames (the ship walks onto targeted cells). Seeds picked under the
    # v1.1.0 rules (the 6-hit ring rule changed every game) and the HUD-layout
    # dome lift (2026-10-18: DOME_Y 88 -> 72 shortens the bullets' on-screen
    # lives, and that table's RNG draws shift every seeded game): 1019 locks
    # 75, 1023 locks 57.
    locks = 0
    for seed in (1019, 1023):
        c, m, (_, _, rules, radar) = run_both(seed, 30000, 0.6)
        assert_same(c, m)
        assert rules.saw_game_over, f"seed {seed} heavy fire must reach GAME OVER"
        assert radar.lock_frames() >= 50, f"seed {seed} must produce radar lock-on frames"
        locks += radar.lock_frames()
    assert locks >= 100, "the heavy-fire games must produce radar lock-on frames"


def test_no_fire_reaches_game_over():
    # with no fire kills stay below LOW_RINGS_AT, but the v1.1.0 rule opens
    # the target rings at 6 missiles that hit the dome (each breaking a
    # whole cell), so missiles keep coming even once the whole wave breaks:
    # the dome reaches DOME_LIMIT and dies (a dome death, integrity 0), and
    # the three NORMAL lives run out. The point is that the C and the model
    # agree all the way there — the no-fire game is what used to reach the
    # stall (v1.0.0 never widens the rings).
    # (seed 230: chosen under the v1.1.0 rules; 237 now ends on ship deaths)
    c, m, (_, _, rules, _) = run_both(230, 20000, 0.0)
    assert_same(c, m)
    assert rules.saw_game_over, "a game with no fire must end under the new rule"
    assert rules.seen_dome_death, "a no-fire game must widen the rings and kill the dome"
    assert rules.game_over_integ == 0, "the game must end with a dome death (integrity 0)"


def test_no_input_reaches_game_over():
    # the pure stall scenario: the ship never moves, never fires. v1.0.0
    # stalls forever once the wave (all 26 cells of rings 0..4) breaks —
    # nothing to launch at, no kills to open the rings (and with no motion
    # the ship never rests on a broken cell, so it cannot die that way
    # either). Under the v1.1.0 rule the 6th missile to hit the dome (whose
    # landing broke a whole cell) opens every ring, a ring-5 cell under the
    # ship cracks, and the game ends. This is the game the user's playtest
    # stalled on.
    n = 30000
    out = subprocess.run([SIM], input="level 1\n" + "0 0\n" * n + "",
                         capture_output=True, text=True, check=True).stdout
    c_lines = out.splitlines()
    ship, mis, rules, radar = fresh(1)
    m_lines = []
    for _ in range(n):
        frame_model((ship, mis, rules, radar), 0, 0)
        m_lines.append(model_line((ship, mis, rules, radar)))
        if rules.game_over:
            break
    for i, m_ in enumerate(m_lines):
        c = tuple(f.split() for f in c_lines[4 * i:4 * i + 4])
        mm = tuple(line.split() for line in m_)
        assert c == mm, f"frame {i}:\n  C  {c}\n  M  {mm}"
    assert len(m_lines) < n, "the no-input no-fire game must end, not stall"
    assert rules.game_over, "a no-input game must reach GAME OVER under the new rule"
    # the ending is plausible: the ship dies three times as its own cell
    # cracks (no input, so a dome death never gets the chance). What must
    # not happen is the old stall — game over with the wave broken and
    # nothing ever ending the game — so any real end is the proof here.
    print(f"no-input no-fire game: GAME OVER at frame {len(m_lines)}, "
          f"integrity {rules.integ}, {len(rules.broken)} cells broken")


def run_both_easy(seed, frames, fire_p):
    """like run_both but on EASY: the model gets the level and the missiles
    use the EASY speed table (v1.1.0); the C sim applies the level through
    the rules_sim 'level 0' line and the rules set the missiles' level."""
    rng = random.Random(seed)

    def input_line():
        inp = rng.choice(STICKS)
        fire = rng.random() < fire_p
        jump = rng.random() < 0.01
        p = (A if fire else 0) | (sm.B if jump else 0)
        return inp | p, p

    script = ["level 0"] + [f"B {c}" for c in ()]
    steps = []
    for _ in range(frames):
        inp, p = input_line()
        script.append(f"{inp} {p}")
        steps.append((inp, p))

    out = subprocess.run([SIM], input="\n".join(script) + "\n",
                         capture_output=True, text=True, check=True).stdout
    c_lines = out.splitlines()
    assert len(c_lines) == 4 * frames, (len(c_lines), 4 * frames)

    ship, mis, rules, radar = fresh(0)
    m_lines = []
    for inp, p in steps:
        frame_model((ship, mis, rules, radar), inp, p)
        m_lines.append(model_line((ship, mis, rules, radar)))
    return c_lines, m_lines, (ship, mis, rules, radar)


def test_fresh_breaks_only_count_as_dome_hits():
    """The v1.1.0 hits rule: a missile landing on a cell that broke after
    it launched (a collapse or another missile's break) is not a hit.
    Heavy fire with collapses produces such landings, so the model's
    dome_hits must stay below its landing count somewhere, and the C and
    the model must agree on dome_hits every frame (assert_same compares
    the whole per-frame line, dome_hits included)."""
    c, m, (_, mis, rules, _) = run_both(1000, 30000, 0.6)
    assert_same(c, m)
    hits, lands = mis_hit_counts(m), mis_land_counts(m)
    # a frame with a landing that did not add a hit, before the rings open
    # (dome_hits < 6): the landed cell was already broken
    uncounted = [i for i in range(1, len(m))
                 if lands[i] > hits[i] - hits[i - 1] and hits[i] < mm.LOW_RINGS_AT]
    assert uncounted, \
        "the seeded game must land on an already-broken cell before the rings open"
    assert sum(lands) > hits[-1], "the model's hits must be fewer than its landings"
    assert rules.saw_game_over, "seed 1000 heavy fire must reach GAME OVER"


def test_rings_open_at_six_hits_before_six_kills():
    """The first launch into a ring-5+ cell must come after dome_hits
    reaches 6 with kills below 6 — the model's own frame."""
    # (seed 34: after the HUD-layout dome lift (2026-10-18) its first
    # ring-5+ launch comes with 2 kills and 7 hits; seed 2's game no longer
    # reaches GAME OVER inside the window because the bullets' on-screen
    # lives changed with the dome's Y)
    _, m, (_, mis, rules, _) = run_both(34, 20000, 0.05)
    assert rules.saw_game_over, "the seeded game must reach GAME OVER"
    for i, line in enumerate(mis_line(m)):
        head = line.split("|")[1].split()
        timer, kills, dome_hits, score = (int(x) for x in head[:4])
        objects = line.split("|")[2].split()
        flying = [int(objects[j * 6 + 2]) for j in range(mm.NMIS)
                  if int(objects[j * 6]) == 1]
        if any(r >= mm.WAVE_RINGS for r in flying):
            assert kills < mm.LOW_RINGS_AT, \
                f"first ring-5+ launch at frame {i} with {kills} kills, want < 6"
            assert dome_hits >= mm.LOW_RINGS_AT, \
                f"first ring-5+ launch at frame {i} with {dome_hits} hits, want >= 6"
            return
    assert False, "the game never launched into ring 5 or beyond"


def mis_line(m_lines):
    """the model's missile line (the tuple's 2nd string) at each frame."""
    return [line[1] for line in m_lines]


def mis_land_counts(m_lines):
    """the model's landing count at each frame line."""
    return [int(line.split("|")[0].split()[1]) for line in mis_line(m_lines)]


def mis_hit_counts(m_lines):
    """the model's dome_hits at each frame line."""
    return [int(line.split("|")[1].split()[2]) for line in mis_line(m_lines)]


def test_easy_game_matches_the_model_framebyframe():
    """A seeded EASY game matches the model frame by frame (the C applies
    the level through the rules; the rules set the missiles' level, so
    EASY's missiles fly at 0.75x). It must reach score 1000 so that at
    least two speed steps are used; assert the score and that a missile
    actually flew with the EASY table."""
    c, m, (_, mis, rules, _) = run_both_easy(5, 30000, 0.3)
    assert_same(c, m)
    assert mis.score >= 1000, f"EASY game must pass the 1000-score step, got {mis.score}"
    assert any(o.dr == mm.DR_EASY[k] for o in mis.obj for k in range(mm.MIS_SPEEDS)), \
        "no missile flew at an EASY speed"


def test_pre_broken_cells_still_match():
    c, m, _ = run_both(7, 20000, 0.05, pre_broken=(13, 26, 29, 12, 2))
    assert_same(c, m)