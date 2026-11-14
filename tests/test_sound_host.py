"""R1 proof 1: the frame's sound command list, on every frame of one
scripted game, equals tests/sound_model.py.

build/sound_sim links the real src/ship.c / src/missiles.c / src/rules.c /
src/radar.c and src/sound.h's sound_frame_cmds (the function flow.c's
game_sound calls). The script:
  - spins at the peak, stops, and spins again (Review Focus 2: the scuttle
    restarts on the new spin's first frame, not mid-period);
  - walks a step and jumps off the step's end (Review Focus 1: the jump
    sound takes channel 0 and the scuttle is not re-sent);
  - fires, kills a missile (a harness-placed bullet and missile on one line),
    and takes a crack (a harness-placed missile one step from a fresh cell);
  - breaks the dome and runs the collapse's five rumble beats.

The harness-placed missiles/bullets are injected identically in the C and
the model, so the frame-by-frame comparison still covers the real game logic
and the real sound decision. The test also states the review focuses from
the model's own command lists.
"""
import os
import subprocess

import mis_model as mm
import radar_model as radm
import rules_model as rm
import ship_model as sm

import sound_model
from test_rules_play import frame_model

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SIM = os.path.join(ROOT, "build", "sound_sim")
SEED = 0xACE1
LEVEL = 1
CELL_KILL = 13
CELL_CRACK = 13


def script():
    """the scripted game, one item per stdin line (a tuple is a frame)."""
    out = [("G", SEED, LEVEL), ("P", 0)]
    out += [(sm.RIGHT, 0)] * 40          # a spin at the peak
    out += [(0, 0)] * 5                  # stop
    out += [(sm.LEFT, 0)] * 40           # restart
    out += [("P", 0)]
    out += [(sm.DOWN, 0)] * 19           # a walk down from the peak
    out += [(sm.DOWN | sm.B, sm.B)]      # jump on the step-ending frame
    out += [(0, 0)] * 32                 # the jump and its landing
    out += [("P", 27), (mm.A, mm.A)]     # fire from the start cell
    out += [(0, 0)] * 2
    out += [("K", CELL_KILL), (0, 0)]    # shoot a missile down
    out += [("M", CELL_CRACK), (0, 0)]   # a missile breaks a fresh cell
    out += [("B", c) for c in range(76)] # the whole dome breaks
    out += [(0, 0)] * 45                 # the death and the collapse's beats
    return out


def run_sim(cmds):
    text = "".join(" ".join(str(x) for x in c) + "\n" for c in cmds)
    out = subprocess.run([SIM], input=text, capture_output=True, text=True,
                         check=True).stdout
    frames = []
    for line in out.splitlines():
        p = line.split()
        assert p and p[0] == "S", line
        n = int(p[1])
        cmds = [int(x) for x in p[2:]]
        assert len(cmds) == n, line
        frames.append(cmds)
    return frames


def run_model(cmds):
    ship, mis, rules, radar = sm.Ship(), mm.Missiles(seed=SEED), rm.Rules(LEVEL), radm.Radar()
    state = (ship, mis, rules, radar)
    sound = sound_model.Sound()
    frames, states = [], []
    for cmd in cmds:
        if cmd[0] == "G":
            ship = sm.Ship()
            mis = mm.Missiles(level=cmd[2], seed=cmd[1])
            rules = rm.Rules(cmd[2])
            radar = radm.Radar()
            state = (ship, mis, rules, radar)
            sound = sound_model.Sound()
        elif cmd[0] == "P":
            ship.place(cmd[1])
        elif cmd[0] == "L":
            broken = set(ship.broken)
            ship.place(cmd[1])
            ship.broken = broken
        elif cmd[0] == "B":
            rules.break_cell(ship, cmd[1])
        elif cmd[0] == "M":
            o = mis.obj[0]
            o.state, o.kind = 1, 0
            o.ring, o.phi = mm.CELL_RING[cmd[1]], mm.CELL_PHI[cmd[1]]
            o.r, o.dr, o.life = mm.LAND + 1, 1, 0
        elif cmd[0] == "K":
            o, b = mis.obj[0], mis.obj[mm.NMIS]
            o.state, o.kind = 1, 0
            o.ring, o.phi = mm.CELL_RING[cmd[1]], mm.CELL_PHI[cmd[1]]
            o.r, o.dr, o.life = 600000, 60000, 0
            b.state, b.kind = 1, 1
            b.ring, b.phi = o.ring, o.phi
            b.r, b.dr, b.life = 590000, mm.BUL_DR, 10
        else:
            cur, pressed = cmd
            frame_model(state, cur, pressed)
            frames.append(sound.cmds(ship, mis, rules, radar, rules._died))
            states.append(dict(
                left=ship.left, mlen=ship.mlen, spinning=ship.spinning,
                jumped=ship.jumped, sfx=mis.sfx, died=rules._died,
                dead_t=rules.dead_t, dome_dead=rules.dome_dead,
                alive=not (rules.dead_t or rules.game_over),
                frac=(rm.DEAD_FRAMES_NEO - rules.dead_t
                      if rules.dead_t and rules.dome_dead else 0)))
    return frames, states


def test_sound_commands_match_the_model_every_frame():
    cmds = script()
    cart = run_sim(cmds)
    model, states = run_model(cmds)
    assert len(cart) == len(model), (len(cart), len(model))
    for i, (c, m) in enumerate(zip(cart, model)):
        assert c == m, f"frame {i + 1}: sound_sim {c} != model {m}"

    # the scuttle at the peak: the spin's first frame and every 19 frames
    spin_frames = [i for i, s in enumerate(states) if s["spinning"]]
    assert spin_frames, "the script never spun at the peak"
    first = spin_frames[0]
    assert 9 in model[first], "no scuttle on the spin's first frame"
    spin_scuttles = [i for i in spin_frames if 9 in model[i]]
    assert spin_scuttles[:3] == [first, first + 19, first + 38], \
        f"spin scuttles at {spin_scuttles[:3]}, want {[first, first + 19, first + 38]}"

    # stop and restart: the restart's first frame carries the scuttle, not
    # a mid-period frame (Review Focus 2)
    restart = None
    for i in range(1, len(states)):
        if states[i]["spinning"] and not states[i - 1]["spinning"]:
            restart = i
            break
    assert restart is not None, "the script never restarted the spin"
    assert 9 in model[restart], "the restart's first frame has no scuttle"
    assert 9 not in model[restart - 1], "the stop frame has a scuttle"

    # the walk's first frame and the jump at the step's end (Review Focus 1)
    walk = next(i for i, s in enumerate(states)
                if s["left"] == sm.MOVE and s["mlen"] == sm.MOVE)
    assert 9 in model[walk], "the walk's first frame has no scuttle"
    jump = next(i for i, s in enumerate(states) if s["jumped"])
    assert 5 in model[jump], "the jump's frame has no jump sound"
    assert 9 not in model[jump], "the jump's frame re-sent the scuttle"
    assert all(9 not in model[i] for i, s in enumerate(states) if s["jumped"]), \
        "a jump frame has a scuttle"
    assert all(9 not in model[i] for i, s in enumerate(states) if not s["alive"]), \
        "a dead frame has a scuttle"

    # fire, kill, crack
    assert any(4 in c for c in model), "no fire command"
    assert any(6 in c for c in model), "no hit command (the kill)"
    assert any(7 in c for c in model), "no crack command"

    # the collapse's five beats: HIT (frame 0), CRACK 9, HIT 18, CRACK 27,
    # HIT 36
    death = next(i for i, s in enumerate(states) if s["died"] and s["dome_dead"])
    beats = [(death + k * 9, want) for k, want in
             enumerate((6, 7, 6, 7, 6))]
    for i, want in beats:
        assert states[i]["frac"] == (i - death), \
            f"frame {i}: collapse_frac {states[i]['frac']} != {i - death}"
        assert want in model[i], f"collapse beat at frame {i}: {model[i]}, want {want}"

    print(f"PASS sound host: {len(model)} frames equal the model; spin "
          f"scuttles at {spin_scuttles[:3]}, restart at {restart}, walk at "
          f"{walk}, jump at {jump}, collapse beats "
          f"{[model[i] for i, _ in beats]}")


def main():
    test_sound_commands_match_the_model_every_frame()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
