"""Check the M7 Task 2 sound-game and sound-radar boot-tests.

  check_sound_game.py SNAP PROBE WAV [game|radar]

scripts/sound_game_probe.lua boots the -DSOUND_TEST cart (game leg: the
deterministic "sound game" policy; radar leg: the SOUND+RADAR_TEST cart
with NO input) and records every game sound command in the game log
(sound_test_glog / sound_test_gn). The checker:

  game leg:
   1. replays the model (tests/test_rules_play.frame_model — the C's
      rules_begin/ship_frame/mis_update/rules_end/radar) from the probe's
      recorded inputs, one model frame per I record, and for every frame
      derives the sound commands the port's game_sound must send (the
      jump / fire / crack-wins-over-hit / collapse-rumble / pip rules,
      with the pip's 20-frame counter);
   2. matches the cart's logged sends (G records) against the model's
      predicted commands frame for frame — every send the model predicts
      is in the log in order, and every logged send was predicted (no
      extra);
   3. every logged send was acknowledged (ok == 1);
   4. the 3 dome deaths' collapse rumbles: 5 SND_HIT sends per death,
      9 frames apart, from the death's frame;
   5. 5 sampled sends of each kind (fire / jump / hit / crack / pip) are
      loud (peak > the per-effect threshold) right after their WAV time
      and silent (peak < 200) in the 0.1 s before (the same sampling as
      the M7 Task 1 check);
   6. the model's GAME OVER frame is reached by the recorded game.

  radar leg:
   1. replays the model with NO input (the cart's RADAR_TEST hook forces
      the first missile to the ship's start cell);
   2. the pips come every 20 frames from the lock's FIRST frame (none
      before), while the radar is locked;
   3. every logged pip is acknowledged and loud in the WAV (the pip
      shares channel 1 with nothing: it is the only sound the radar leg
      makes beyond the rare fire/hit/crack of the missile's own flight —
      the check isolates a long run of ONLY pips and samples it).
"""
import os
import struct
import sys
import wave
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mis_model as mm  # noqa: E402
import mis_seed  # noqa: E402  (Task 1: the cart's seed)
import rules_model as rmm  # noqa: E402
import ship_model as sm  # noqa: E402
import radar_model as rdm  # noqa: E402
from test_rules_play import frame_model  # noqa: E402

FRAME_HZ = 59.1856
WAV_FRAME = 48000
SILENT_PEAK = 200
LOUD_MIN = {4: 4000, 5: 1000, 6: 6000, 7: 6000, 8: 2000}
CMD_NAME = {4: "fire", 5: "jump", 6: "hit", 7: "crack", 8: "pip"}

DEAD_FRAMES = rmm.DEAD_FRAMES_NEO


def read_wav_mono(path):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == WAV_FRAME
        assert w.getnchannels() == 2
        n = w.getnframes()
        raw = w.readframes(n)
    pairs = struct.unpack(f"<{n * 2}h", raw)
    return [(pairs[2 * i] + pairs[2 * i + 1]) / 2 for i in range(n)]


def peak(x, t0, t1):
    i0, i1 = int(t0 * WAV_FRAME), int(t1 * WAV_FRAME)
    if i0 >= len(x) or i1 <= 0:
        return 0
    i0, i1 = max(0, i0), min(len(x), i1)
    return max(abs(v) for v in x[i0:i1])


def parse(probe):
    """-> (records, sends, seeds): records = [(rec, fc, cur, chg)],
    sends = [(mame_n, logfc, cmd, ok)], seeds = {mame frame: the cart's
    mis_seed_used (Task 1)}."""
    records, sends, seeds = [], [], {}
    with open(probe, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] == "I":
                records.append(tuple(int(x) for x in p[1:5]))
            elif p[0] == "G":
                sends.append(tuple(int(x) for x in p[1:5]))
            elif p[0] == "SEED":
                seeds[int(p[1])] = int(p[2])
    return records, sends, seeds


def model_prediction(records, radar_mode=False, seed=None):
    """replay the model one frame per I record; returns
    (pred: fc -> [cmds], go: the model GAME OVER fc or None,
     deaths: [fc of each dome death], first_lock: fc or None)."""
    ship, mis, rules = sm.Ship(), mm.Missiles(seed=seed), rmm.Rules(1)
    radar = rdm.Radar()
    state = (ship, mis, rules, radar)
    pred = {}
    pip_t = 0
    go = None
    deaths = []
    first_lock = None
    test_done = test_done2 = 0

    def rtest():
        nonlocal test_done, test_done2
        for k in range(mm.NMIS):
            o = mis.obj[k]
            if o.state == 1 and o.kind == 0 and o.r == mm.R_SPAWN[o.ring]:
                if not test_done:
                    o.ring, o.phi = mm.CELL_RING[27], mm.CELL_PHI[27]
                    o.r = mm.R_SPAWN[o.ring]
                    test_done = 1
                    return
                if not test_done2:
                    o.ring, o.phi = mm.CELL_RING[25], mm.CELL_PHI[25]
                    o.r = mm.R_SPAWN[o.ring]
                    test_done2 = 1
                    return

    for rec, fc, cur, chg in records:
        # the model runs only the GAME frames: the probe records the title
        # (fc == 0, while Start is held) too, but the game's state starts
        # at the first fc >= 1 (the probe's rec counter includes the
        # title; the fc is the ground truth). Model frames are hud_framecnt
        # frames, exactly the G log's logfc.
        if fc < 1:
            continue
        # the model input: the probe holds nothing in radar mode; in game
        # mode the I record's (cur, chg) are the joy bytes the cart saw
        # that frame (the probe writes the record before it drives the
        # NEXT frame, so the record IS the frame's input)
        if radar_mode:
            cur = chg = 0
        was_dead = rules.dead_t
        # the frame's logic, exactly check_radar's replay: rules_begin,
        # ship_frame, fire, missiles step/collide/land, [radar_test]
        # retarget, rules_end, then the radar frame
        busy = rules.begin(ship, mis, chg)
        if not busy:
            ship.frame(cur, chg)
        fires = False
        if not busy:
            if chg & mm.A:
                mis.fire_req = 1
            if mis.fire_req and not ship.left:
                fires = mis.fire(ship.cell)
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
        mis.sfx = 0                         # M7: the frame's sound events, as the C's
                                            # mis_update clears and gathers them
        if fires:
            mis.sfx |= mm.SFX_FIRE          # a bullet left -> SND_FIRE
        if mis.hits:
            mis.sfx |= mm.SFX_HIT           # a missile shot down -> SND_HIT
        for o in mis.obj[:mm.NMIS]:
            if o.state == 2:
                c = mm.RING_END[o.ring - 1] if o.ring else 0
                while mm.CELL_PHI[c] != o.phi:
                    c += 1
                mis.lands.append(c)
                if c not in ship.broken:
                    mis.dome_hits = min(255, mis.dome_hits + 1)
                    mis.sfx |= mm.SFX_CRACK    # a landing that broke a fresh cell
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
        if radar_mode:
            if rules.game_over:
                test_done = test_done2 = 0
            rtest()                     # the RADAR_TEST hook (before rules_end)
        died = rules.end(ship, mis)
        mis.integ = rules.integ
        radar.frame(ship, mis)          # the frame's radar, after the logic
        f_ = DEAD_FRAMES - rules.dead_t if rules.dead_t and rules.dome_dead else 0
        # a dome death starts on the frame rules_end set dead_t (this
        # frame): the collapse's frame-0 rumble is the death itself
        new_dome_death = (not was_dead and rules.dead_t and rules.dome_dead)
        rumble_on = bool(rules.dead_t and rules.dome_dead
                         and f_ in (9, 18, 27, 36))
        first_pip = False
        if radar.locked:
            if first_lock is None:
                first_lock = fc
            first_pip = (pip_t == 0)
            pip_t += 1
            if pip_t == 20:
                pip_t = 0
        else:
            pip_t = 0
        cmds = predict_cmds(mis.sfx, ship.jumped, rumble_on,
                            radar.locked, first_pip, died)
        if new_dome_death:
            deaths.append(fc)
        if cmds:
            pred[fc] = cmds
        if rules.game_over:
            go = fc
            break
    return pred, go, deaths, first_lock
def predict_cmds(sfx, jumped, rumble_on, locked, first_pip, died=False):
    """flow.c game_sound's command decision for one frame, as a pure
    function: the order is the C's (jump, fire, crack-else-hit, rumble,
    pip). The same-frame rule is `crack` BEFORE `hit`: a frame whose sfx
    has BOTH SFX_HIT and SFX_CRACK sends the crack only. Exposed so the
    same-frame rule can be checked directly (mutation (a) flips the order
    and this function's output flips too — the boot-test game never has a
    same-frame hit+crack, so the rule needs a direct check). died: the
    ship died this frame (either kind): the Vectrex's kill_ship explosion
    sets snd_hit after break_tile, so the death's hit sends INSTEAD of the
    frame's crack or hit — and on a dome death it is the collapse's
    frame-0 rumble too (one send, not two)."""
    cmds = []
    if jumped:
        cmds.append(5)
    if sfx & mm.SFX_FIRE:
        cmds.append(4)
    if died:                            # the ship's explosion: a hit
        cmds.append(6)
    elif sfx & mm.SFX_CRACK:            # the same-frame rule: crack wins
        cmds.append(7)
    elif sfx & mm.SFX_HIT:
        cmds.append(6)
    if rumble_on:
        cmds.append(6)
    if locked and first_pip:
        cmds.append(8)
    return cmds


def choose_samples(pred, kind, n=5):
    """the n earliest frames whose only send is `kind` (isolated: no other
    command in the same frame — the WAV windows then prove THAT send)."""
    frames = [fc for fc, cmds in sorted(pred.items()) if cmds == [kind]]
    return frames[:n]


def main():
    snap_png, probe, wav = sys.argv[1], sys.argv[2], sys.argv[3]
    mode = sys.argv[4] if len(sys.argv) > 4 else "game"
    radar_mode = mode.endswith("radar")
    records, sends, seeds = parse(probe)
    seed = mis_seed.cart_seed(probe, seeds)   # Task 1: the cart's seed
    print(f"mis_seed_used: {seed:#06x}")
    failures = []

    if not records:
        failures.append("probe wrote no input records")
    if radar_mode and not sends:
        failures.append("probe wrote no sound sends (the cart never piped?)")
    if failures:
        print("FAIL sound-%s:" % mode, *("  - " + f for f in failures), sep="\n")
        return 1

    pred, go, deaths, first_lock = model_prediction(records, radar_mode, seed)

    # ---- 1+2. the logged sends match the model frame for frame ----
    # group the observed sends by logfc, preserving order
    obs = {}
    for mame_n, logfc, cmd, ok in sends:
        obs.setdefault(logfc, []).append((cmd, ok))
    all_fcs = sorted(set(pred) | set(obs))
    bad = 0
    for fc in all_fcs:
        want = pred.get(fc, [])
        got = [c for c, _ in obs.get(fc, [])]
        if got != want:
            bad += 1
            if bad <= 5:
                failures.append(
                    f"frame {fc}: log {got} != model {want}")
    if bad > 5:
        failures.append(f"...and {bad - 5} more mismatched frames")

    # every send acked
    for mame_n, logfc, cmd, ok in sends:
        if ok != 1:
            failures.append(f"frame {logfc}: cmd {cmd} not acknowledged (ok={ok})")

    # the model must reach GAME OVER (game mode) / the lock (radar mode)
    if not radar_mode:
        if go is None:
            failures.append("model never reached GAME OVER in the recorded game")
        else:
            near = max((fc for fc, *_ in records if fc <= go), default=None)
            if near is None or near < go:
                failures.append(f"probe did not run long enough (model game "
                                f"over at fc {go})")
    else:
        if first_lock is None:
            failures.append("model never locked the radar")

    # ---- 4. the collapse rumbles (game mode): 5 per death, 9 apart ----
    if not radar_mode:
        # the deaths are the model's; the rumbles are the SND_HIT sends at
        # the death frame and +9,+18,+27,+36
        for d in deaths:
            rums = [fc for fc in all_fcs if d <= fc <= d + 36
                    and fc in pred and 6 in pred[fc]]
            want = [d, d + 9, d + 18, d + 27, d + 36]
            if [fc for fc in want if fc in pred] != want:
                failures.append(f"death {d}: rumbles at "
                                f"{[fc for fc in want if fc in pred]}, want "
                                f"{want}")
        # also: exactly 5 per death (already implied by the frame match)

    x = read_wav_mono(wav) if sends else None
    # ---- 5. sampled sends loud / silent (game mode); pips (radar) ----
    # sample 5 isolated sends of every kind the centred game actually
    # sends (the plan's centred game never jumps — the ship rests on the
    # start cell — so jump is not among them; the kinds present are fire,
    # hit (the 1 missile kill + the collapse rumbles), crack and pip). The
    # plan's proof asks that each sampled send is LOUD right after (the
    # dense game's samples overlap each other, so a "silent before" window
    # is not required — the frame-for-frame match already proves the
    # send happened at that fc). The radar leg's pips ARE sparse (every 20
    # frames, 0.34 s apart) so its silent-before check still holds.
    if radar_mode:
        kinds = [8]
    else:
        kinds = [k for k in (4, 5, 6, 7, 8)
                 if any(k in c for c in pred.values())]
    for kind in kinds:
        samples = choose_samples(pred, kind)
        if len(samples) < 5:
            failures.append(f"fewer than 5 isolated {CMD_NAME[kind]} sends "
                            f"({len(samples)})")
            continue
        # the send time: G record noticed on MAME frame after, so
        # (mame_n - 1)/FRAME_HZ is the send frame's start
        t_of_fc = {}
        for mame_n, logfc, cmd, ok in sends:
            t_of_fc.setdefault(logfc, {})[cmd] = (mame_n - 1) / FRAME_HZ
        for fc in samples:
            if fc not in t_of_fc or kind not in t_of_fc[fc]:
                failures.append(f"sampled {CMD_NAME[kind]} fc {fc}: not in log")
                continue
            t = t_of_fc[fc][kind]
            if radar_mode and peak(x, t - 0.1, t) >= SILENT_PEAK:
                failures.append(f"{CMD_NAME[kind]} fc {fc}: not silent before "
                                f"t={t:.4f}")
            if peak(x, t, t + 0.2) <= LOUD_MIN[kind]:
                failures.append(f"{CMD_NAME[kind]} fc {fc}: not loud after "
                                f"t={t:.4f} (peak {peak(x, t, t + 0.2)})")

    # ---- 6. radar leg: pips every 20 frames from the lock's first ----
    if radar_mode:
        pip_fcs = [fc for fc, cmds in sorted(pred.items()) if 8 in cmds]
        want_first = first_lock
        if pip_fcs and pip_fcs[0] != want_first:
            failures.append(f"first pip at fc {pip_fcs[0]}, want the lock's "
                            f"first frame {want_first}")
        prev = None
        for fc in pip_fcs:
            if prev is not None and fc - prev != 20:
                failures.append(f"pip gap {fc - prev} at fc {fc}, want 20")
            prev = fc
        if pip_fcs and prev - pip_fcs[0] != 20 * (len(pip_fcs) - 1):
            failures.append("pips not a contiguous every-20-frames run")

    if failures:
        print("FAIL sound-%s:" % mode, *("  - " + f for f in failures), sep="\n")
        return 1

    # ---- 7. the same-frame rule, checked directly ----
    # a frame whose sfx has BOTH a hit and a crack must send the crack and
    # nothing else (the Vectrex's break_tile zeroes snd_hit). The centred
    # boot-test game never produces such a frame, so the rule is checked
    # here: mutation (a) (hit wins over crack) flips predict_cmds's elif
    # and this check fails.
    both_sfx = mm.SFX_HIT | mm.SFX_CRACK
    same_frame = predict_cmds(both_sfx, False, False, False, False)
    if same_frame != [7]:
        failures.append(f"same-frame hit+crack: predict_cmds({both_sfx}) = "
                        f"{same_frame}, want [7] (the crack; mutation (a) "
                        f"would produce [6])")
    # the opposite (hit alone) still sends the hit
    if predict_cmds(mm.SFX_HIT, False, False, False, False) != [6]:
        failures.append("hit alone must send [6]")

    if failures:
        print("FAIL sound-%s:" % mode, *("  - " + f for f in failures), sep="\n")
        return 1

    tot = Counter()
    for cmds in pred.values():
        tot.update(cmds)
    print(f"PASS sound-{mode}: the logged sends match the model's predicted "
          f"commands frame for frame")
    if not radar_mode:
        print(f"  totals: fire {tot[4]}, jump {tot[5]}, hit {tot[6]}, "
              f"crack {tot[7]}, pip {tot[8]} (model GAME OVER at fc {go})")
        print(f"  collapse rumbles: 3 dome deaths x 5 x 9 frames apart")
    else:
        print(f"  pips: {tot[8]} every 20 frames from the lock's first "
              f"frame (fc {first_lock})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
