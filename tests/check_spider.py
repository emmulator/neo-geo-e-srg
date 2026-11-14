#!/usr/bin/env python3
"""The stopper-spider's animation proof (Task S2).

  check_spider.py --host
      runs build/spider_sim (the real ship.c / missiles.c / rules.c and
      ship_frame_of) and tests/ship_anim_model.py on one scripted run that
      walks, jumps over a move-end (Review Focus 1), fires on the landing
      frame (Review Focus 2), fires again inside the heave (the restart),
      dies in the heave and respawns (Review Focus 3). Every frame's
      ship_frame_of must equal the model's.

  check_spider.py PROBE
      scripts/spider_probe.lua's log: one full demo cycle on the title
      (Review Focus 4) and a scripted game that walks, jumps, fires, dies
      and respawns. For every logged cart frame, the ship's SCB1 tiles must
      equal ship_anim_tile[heading][lat][frame_of(previous state)] (the
      heading read from the cart, the vblank commit is one frame behind the
      state), and the driver's SCB3 must be hidden while the previous state
      is dead and the expected REST/pose elsewhere (ship_oy[heading][lat]).
      It also states how many distinct headings the demo/game leg saw.

The Python model of ship_frame_of is tests/ship_anim_model.py; it is the
same model the host proof uses, so the cart's picture choice and the model
cannot drift apart.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
import ship_anim_model as sam  # noqa: E402
import ship_model as sm        # noqa: E402
import check_demo as cd        # noqa: E402  (the demo's model hash)

BUILD = os.path.join(ROOT, "build")
SHIP_MAP = os.path.join(BUILD, "ship_map.h")
SIM = os.path.join(BUILD, "spider_sim")

DOME_Y = 104
SHIP_ROWS = 2


def header_ints(name):
    text = open(SHIP_MAP).read()
    body = re.search(r"%s\[[^=]*=\s*\{(.*?)\};" % name, text, re.S).group(1)
    return [int(n) for n in re.findall(r"-?\d+", body)]


def anim_table():
    """[heading][view][frame][column][row] from build/ship_map.h."""
    text = open(SHIP_MAP).read()
    h = int(re.search(r"#define SHIP_HEADINGS (\d+)", text).group(1))
    v = int(re.search(r"#define SHIP_VIEWS (\d+)", text).group(1))
    f = int(re.search(r"#define SHIP_FRAMES (\d+)", text).group(1))
    c = int(re.search(r"#define SHIP_COLS (\d+)", text).group(1))
    r = int(re.search(r"#define SHIP_ROWS (\d+)", text).group(1))
    flat = header_ints("ship_anim_tile")
    assert len(flat) == h * v * f * c * r, (len(flat), h * v * f * c * r)
    out, k = [], 0
    for _ in range(h):
        hv = []
        for _ in range(v):
            vf = []
            for _ in range(f):
                fc = []
                for _ in range(c):
                    fc.append(flat[k:k + r])
                    k += r
                vf.append(fc)
            hv.append(vf)
        out.append(hv)
    return out


def oy_table():
    oy = header_ints("ship_oy")
    assert len(oy) == 8 * 48, len(oy)
    return [oy[h * 48:(h + 1) * 48] for h in range(8)]


def scb3_for(heading, lat, lift):
    y = DOME_Y + OY[heading][lat] - lift
    return ((496 - y) << 7) | SHIP_ROWS


# ------------------------------------------------------------------ host
HOST_SCRIPT = []


def host_commands():
    """the scripted game: frame numbers are game-session frames (fc)."""
    cmds = [("G", 0xACE1, 1)]
    prev = 0
    for f in range(1, 63):
        if f < 7:
            cur = 0
        elif f < 11:
            cur = sm.UP
        elif f == 11:
            cur = sm.UP | sm.B
        elif f < 31:
            cur = sm.UP
        elif f < 56:
            cur = sm.UP | 16                  # A latched: fires on the landing
        elif f < 59:
            cur = sm.UP
        elif f == 59:
            cur = sm.UP | 16                  # a new shot inside the heave
        else:
            cur = 0
        pressed = 0 if f == 1 else (cur & ~prev)
        cmds.append((cur, pressed))
        prev = cur
    # die while the heave is still running: cell 0 is the ship's cell.
    cmds.append(("B", 0))
    for _ in range(125):                      # death, 118 dead frames, respawn
        cmds.append((0, 0))
    return cmds


def run_sim(cmds):
    text = "".join(" ".join(str(x) for x in c) + "\n" for c in cmds)
    out = subprocess.run([SIM], input=text, capture_output=True, text=True,
                         check=True).stdout
    return [tuple(int(x) for x in line.split()) for line in out.splitlines()]


def host():
    model = sam.run_commands(host_commands())
    cart = run_sim(host_commands())
    failures = []
    if len(cart) != len(model):
        failures.append(f"spider_sim printed {len(cart)} frames, model {len(model)}")
    else:
        for i, (c, m) in enumerate(zip(cart, model)):
            if c != m:
                failures.append(f"frame {i + 1}: spider_sim {c} != model {m}")
                break
    # the review focuses, stated from the model's own frame sequence
    fr = [m[9] for m in model]
    alive = [not m[10] for m in model]
    walk_jump = None
    landing_shot = None
    restart = None
    death = None
    respawn = None
    for i, m in enumerate(model):
        if i and fr[i - 1] == sam.F_WALK + 3 and fr[i] == sam.F_JUMP:
            walk_jump = i + 1
        if (landing_shot is None and m[2] == sm.JUMP and m[1] == 0 and m[8]
                and fr[i] == sam.F_HEAVE):
            landing_shot = i + 1
        if (restart is None and m[8] and i and fr[i] == sam.F_HEAVE
                and fr[i - 1] in (sam.F_HEAVE, sam.F_HEAVE + 1,
                                  sam.F_HEAVE + 2, sam.F_HEAVE + 3)):
            restart = i + 1
        if not alive[i] and death is None:
            death = i + 1
        if death is not None and alive[i] and respawn is None:
            respawn = i + 1
    if walk_jump is None:
        failures.append("no walk -> jump transition (Review Focus 1)")
    if landing_shot is None:
        failures.append("no shot on the landing frame (Review Focus 2)")
    if restart is None:
        failures.append("no shot restarting the heave")
    if death is None or respawn is None:
        failures.append("the run never died and respawned (Review Focus 3)")
    elif fr[respawn - 1] != sam.F_REST:
        failures.append(f"the respawn frame is picture {fr[respawn - 1]}, not REST")
    if not failures:
        before = death - 1
        print(f"PASS spider host: {len(model)} frames equal the model; "
              f"walk->jump at {walk_jump}, landing shot at {landing_shot}, "
              f"heave restart at {restart}, died at {death} in picture "
              f"{fr[before - 1]}, respawn at {respawn} in REST")
        return 0
    print("FAIL spider host:")
    for f in failures:
        print("  - " + f)
    return 1


# ------------------------------------------------------------------ MAME
class Rec:
    def __init__(self, kind, n, ctr, heading, lat, left, mlen, lift, spinning,
                 shot, dead, scb3, tiles, hash):
        self.kind = kind
        self.n = n
        self.ctr = ctr
        self.heading = heading
        self.lat = lat
        self.left = left
        self.mlen = mlen
        self.lift = lift
        self.spinning = spinning
        self.shot = shot
        self.dead = dead
        self.scb3 = scb3
        self.tiles = tiles
        self.hash = hash
        self.alive = (dead == 0)


def parse(path):
    recs = []
    for raw in open(path, "rb"):
        p = raw.decode("ascii", "replace").split()
        if not p or p[0] not in ("D", "G"):
            continue
        kind = p[0]
        if kind == "D":
            n, epoch, ctr, heading = int(p[1]), int(p[2]), int(p[3]), int(p[4])
            rest = p[5:]
        else:
            n, ctr, heading = int(p[1]), int(p[2]), int(p[3])
            epoch = None
            rest = p[4:]
        lat, left, mlen, lift, spinning, shot, dead = (
            int(x) for x in rest[:7])
        scb3 = int(rest[7], 16)
        tiles = tuple(int(x, 16) for x in rest[8:12])
        hash = int(rest[12], 16)
        r = Rec(kind, n, ctr, heading, lat, left, mlen, lift, spinning, shot,
                dead, scb3, tiles, hash)
        r.epoch = epoch
        recs.append(r)
    return recs


def check_probe(path):
    global OY, ANIM
    OY = oy_table()
    ANIM = anim_table()
    recs = parse(path)
    failures = []
    if not recs:
        print("FAIL spider: the probe wrote no D/G records")
        return 1

    # one full demo cycle: some demo epoch's dfc reaches 3245 and its cart
    # hash equals the model's full-cycle hash. The hash covers every frame
    # the cart ran, so a D line the MAME notifier missed (the demo probe
    # documents the same miss) does not hide a frame; the dfc order must
    # still be strictly increasing. Epoch 1 is only 3242 frames on the first
    # entry (title_t starts at 2); the probe lets epoch 2 run the whole
    # cycle before pressing Start.
    seed, level, frames, inputs = cd.parse_header()
    states, _ev = cd.model_states(inputs, seed, level)
    want_hash = cd.model_hashes(states)[-1]
    demo = [r for r in recs if r.kind == "D"]
    epochs = {}
    for r in demo:
        epochs.setdefault(r.epoch, []).append(r.ctr)
    full = None
    last = {}
    for ep, ct in epochs.items():
        last[ep] = max((r for r in demo if r.epoch == ep),
                       key=lambda r: r.ctr).hash
        if (max(ct) >= 3245 and last[ep] == want_hash
                and all(a < b for a, b in zip(ct, ct[1:]))):
            full = (ep, len(ct), max(ct))
    if full is None:
        failures.append("no full demo epoch: " + ", ".join(
            f"epoch {ep}: {len(ct)} frames, max dfc {max(ct)}, last hash "
            f"{last[ep]:#010x}"
            for ep, ct in epochs.items())
            + f" (want max dfc >= 3245 and hash {want_hash:#010x})")
    game = [r for r in recs if r.kind == "G"]
    if not game:
        failures.append("the probe wrote no game frames (no Start)")

    anim = sam.Anim()
    prev = None
    counts = dict(rest=0, walk=0, jump=0, heave=0)
    transitions = []
    bad_tiles = 0
    bad_vis = 0
    bad_y = 0
    frames = 0
    landing_shot = None
    restart = None
    death = None
    respawn = None
    death_rec = respawn_rec = None
    prev_frame = None       # the picture chosen for prev, shown on this frame
    last_display = None     # the picture shown on the previous frame
    seen_headings = set()   # the headings the logged displays used
    for r in recs:
        if prev is not None:
            # the frame just shown uses the picture chosen for prev's state
            # (the vblank commit is one frame behind the state)
            trans = (prev.kind != r.kind
                     or (r.kind == "D" and r.epoch != prev.epoch)
                     or (r.kind == "D" and r.ctr <= prev.ctr))
            if prev.alive:
                seen_headings.add(prev.heading)
                counts["rest" if prev_frame == sam.F_REST
                       else "walk" if prev_frame < sam.F_JUMP
                       else "jump" if prev_frame < sam.F_HEAVE else "heave"] += 1
                want = tuple(x for c in ANIM[prev.heading][prev.lat][prev_frame]
                             for x in c)
                if r.tiles != want:
                    bad_tiles += 1
                    if bad_tiles == 1:
                        failures.append(
                            f"frame {r.n} ({r.kind} {r.ctr}): SCB1 tiles "
                            f"{r.tiles} != ship_anim_tile[{prev.heading}]"
                            f"[{prev.lat}][{prev_frame}] {want}")
                if (r.scb3 & 0x3f) != SHIP_ROWS:
                    bad_vis += 1
                    if bad_vis == 1:
                        failures.append(f"frame {r.n}: ship height "
                                        f"{r.scb3 & 0x3f}, want {SHIP_ROWS}")
                if not trans and r.scb3 != scb3_for(prev.heading, prev.lat,
                                                   prev.lift):
                    bad_y += 1
                    if bad_y == 1:
                        failures.append(f"frame {r.n}: SCB3 {r.scb3:04x} != "
                                        f"expected {scb3_for(prev.heading, prev.lat, prev.lift):04x}")
                if (last_display is not None
                        and sam.F_WALK <= last_display < sam.F_JUMP
                        and prev_frame == sam.F_JUMP):
                    transitions.append((r.n, last_display, prev_frame))
                last_display = prev_frame
            else:
                if (r.scb3 & 0x3f) != 0:
                    bad_vis += 1
                    if bad_vis == 1:
                        failures.append(f"frame {r.n}: the dead ship is not "
                                        f"hidden (SCB3 height {r.scb3 & 0x3f})")
                last_display = sam.F_REST
            frames += 1
            if prev.alive and not r.alive and death is None:
                death, death_rec = r.n, r
            if death is not None and not prev.alive and r.alive and respawn is None:
                respawn, respawn_rec = r.n, r
        # a new shot inside the heave restarts it (the animation was still
        # in the heave before this frame's shot is applied)
        if r.alive and r.shot and anim.heave_t != sam.HEAVE_NONE:
            restart = r.ctr
        # a shot on the landing frame: the previous state was the jump's
        # last step (left 1), this state is the landing (left 0)
        if (r.alive and r.shot and r.mlen == sm.JUMP and r.left == 0
                and prev is not None and prev.mlen == sm.JUMP
                and prev.left > 0):
            landing_shot = r.ctr
        # resets the cart performs before this frame's prepare
        if r.kind == "D" and prev is not None and prev.kind == "D" \
                and (r.epoch != prev.epoch or r.ctr <= prev.ctr):
            anim.rest()
        if r.kind == "G" and prev is not None and prev.kind != "G":
            anim.rest()
        if not r.alive:
            anim.rest()
            prev_frame = sam.F_REST
        else:
            prev_frame = anim.frame_of(_ship(r), r.shot)
        prev = r

    if not transitions:
        failures.append("no walk -> jump transition (Review Focus 1)")
    if landing_shot is None:
        failures.append("no shot on the landing frame (Review Focus 2)")
    if restart is None:
        failures.append("no shot restarting the heave")
    if death is None or respawn is None:
        failures.append("the game did not die and respawn (Review Focus 3)")
    else:
        # the respawn frame's own display is still the death's hidden slots
        # (the vblank commit lags); the next frame shows the respawn state.
        idx = recs.index(respawn_rec)
        nxt = recs[idx + 1] if idx + 1 < len(recs) else None
        if nxt is None or nxt.tiles != tuple(
                x for c in ANIM[nxt.heading][nxt.lat][sam.F_REST] for x in c):
            failures.append("the first frame after the respawn is not REST")
    death_fc = death_rec.ctr if death_rec is not None else None
    respawn_fc = respawn_rec.ctr if respawn_rec is not None else None
    if len(seen_headings) < 4:
        failures.append(f"the leg saw only {len(seen_headings)} headings "
                        f"{sorted(seen_headings)}, want at least 4")
    if full is not None:
        print(f"demo epoch {full[0]}: the cart hash covers all {full[2]} "
              f"frames (dfc 1..{full[2]}, {full[1]} logged), "
              f"{counts['walk']} walk, {counts['jump']} jump, "
              f"{counts['heave']} heave frames")
    if game:
        print(f"game: {len(game)} frames (fc {game[0].ctr}..{game[-1].ctr}), "
              f"death at fc {death_fc}, respawn at fc {respawn_fc}")
    print(f"  checked {frames} frame displays; "
          f"{len(seen_headings)} distinct headings {sorted(seen_headings)}; "
          f"bad tiles {bad_tiles}, bad visibility {bad_vis}, bad Y {bad_y}; "
          f"walk->jump {len(transitions)}, landing shot {landing_shot}, "
          f"heave restart {restart}")
    if failures:
        print("FAIL spider:")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"PASS spider: every shown frame's SCB1 tiles equal "
          f"ship_anim_tile[heading][lat][frame_of(previous state)] and its "
          f"Y ship_oy[heading][lat]; one demo cycle and the scripted game "
          f"included; no bad visibility or Y")
    return 0


class _ShipView:
    """the fields ship_frame_of reads, from a probe record."""
    def __init__(self, r):
        self.left = r.left
        self.mlen = r.mlen
        self.spinning = r.spinning


def _ship(r):
    return _ShipView(r)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--host":
        return host()
    if len(sys.argv) == 2:
        return check_probe(sys.argv[1])
    print("usage: check_spider.py --host | PROBE")
    return 1


if __name__ == "__main__":
    sys.exit(main())
