"""Check the M7 Task 1 sound-pipeline boot-test.

  check_sound.py SNAP PROBE WAV [mvs]

scripts/sound_probe.lua boots the -DSOUND_TEST cart (build/rom-soundtest.zip)
with MAME's -wavwrite recording the audio, and logs each sound command send
with the MAME frame it was noticed on. This checker proves:

  1. every command in the log was acknowledged (ok == 1 for all 8 sends:
     the six singles at title frames 100/160/220/280/340/460 and the 6+8
     pair at frame 400 — "two acks in one frame");
  2. for each of the six singles, the recorded WAV is silent (peak < 200)
     in the 0.1 s before the send's time and loud (peak > the per-effect
     threshold) right after, and the audible length matches the sample's
     length within 0.05 s;
  3. at frame 400 both 6 and 8 were acknowledged, and the audio after it
     lasts the hit's 0.75 s (the shared-channel rule: the pip on channel 1
     cannot cut the hit on channel 2, so the whole 0.75 s plays);
  4. with mvs=1 the whole thing runs under the MVS BIOS (`neogeo -bios
     euro`), proving the same driver + samples play on MVS.

The WAV is MAME's -wavwrite output: 48 kHz stereo. MAME's frame rate is
59.1856 Hz, so MAME frame n starts at n / 59.1856 s in the WAV (both
confirmed 2026-10-19). H5's sample lengths (soxi -D on
tools/synth_sfx.py's output): move 0.32 s (5939 samples, RMS 0.040),
jump 0.59 s, fire 0.30 s, hit 0.75 s, crack 0.90 s; the pip stays
tools/render_sfx.py's 0.06 s. The ADPCM playback adds ~0.02 s of block
padding.
The probe's S record for a send is noticed on the MAME frame AFTER the
send (the frame notifier runs with the previous frame's output), so the
checker places each send at (mame_n - 1) / 59.1856 and is generous around
it (~0.1 s windows; the audio onset is ~2.6 ms later still, well inside
the windows). The audible length stops at the first sustained quiet gap,
so a sample never measures into the next send (the last sample's ADPCM
tail runs to the recording's end).
"""
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mis_model as mm            # noqa: E402
import radar_model as radm        # noqa: E402
import rules_model as rm          # noqa: E402
import ship_model as sm           # noqa: E402
import sound_model                # noqa: E402  (R1: the scuttle/rumble/pip)
from test_rules_play import frame_model       # noqa: E402

FRAME_HZ = 59.1856          # MAME's neogeo frame rate (confirmed)
WAV_FRAME = 48000           # MAME's -wavwrite rate (confirmed: 48 kHz)
SILENT_PEAK = 200           # the WAV is silent below this (the task's)
# ADPCM-A playback scales the samples to ~half amplitude. The thresholds
# below are half the per-effect peaks the synth WAVs measured in MAME (see
# the run's printed peaks); the task's "loud" standard still requires
# each sample to be clearly audible. The pip stays the old Vectrex sample,
# so its old measured threshold is kept.
LOUD_MIN = {
    4: 4000,     # fire: measured 13130 (H3 bolt)
    5: 1000,     # jump: measured 11895
    6: 6000,     # hit: measured 12754
    7: 6000,     # crack: measured 13873
    8: 2000,     # pip: measured 3698 (old, unchanged sample)
    9: 900,      # move: measured 1830 (H5 hover D, ~half its peak)
}
AUDIBLE_MIN = 200           # a sample is "audible" while |x| > this
LEN_TOL = 0.05              # the audible length matches the WAV's within this
# H5: the synth lengths (soxi -D on tools/synth_sfx.py's output), the
# pip's old 0.06 s: move 0.32 jump 0.59 fire 0.30 hit 0.75 crack 0.90
LEN = {4: 0.30, 5: 0.59, 6: 0.75, 7: 0.90, 8: 0.06, 9: 0.32}

# the test cart's single sends (title frame -> command) and the frame-400
# two-sounds-in-one-frame pair (6 then 8)
SINGLES = [(100, 4), (160, 5), (220, 6), (280, 7), (340, 8), (460, 9)]
PAIR = [(400, 6), (400, 8)]
SENDS = SINGLES + PAIR
AUDIO_LEN = {6: 0.75}       # the frame-400 pair: the hit's whole length plays


def parse(probe):
    """-> (log, mame_frames): log = [(mame_n, tf, log_tf, cmd, ok), ...]."""
    log, end = [], 0
    with open(probe, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] == "S":
                log.append(tuple(int(x) for x in p[1:6]))
            elif p[0] == "pc_in_cart":
                end = int(p[1].split("=")[1])
    return log, end


def read_wav_mono(path):
    """the WAV as a mono float array at 48 kHz (mix the stereo pair)."""
    with wave.open(path, "rb") as w:
        assert w.getframerate() == WAV_FRAME
        assert w.getnchannels() == 2
        n = w.getnframes()
        raw = w.readframes(n)
    pairs = struct.unpack(f"<{n * 2}h", raw)
    return [(pairs[2 * i] + pairs[2 * i + 1]) / 2 for i in range(n)]


def peak(x, t0, t1):
    """the max |sample| in WAV time [t0, t1) (s)."""
    i0, i1 = int(t0 * WAV_FRAME), int(t1 * WAV_FRAME)
    if i0 >= len(x) or i1 <= 0:
        return 0
    i0, i1 = max(0, i0), min(len(x), i1)
    return max(abs(v) for v in x[i0:i1])


def audible_len(x, t0):
    """the time from t0 until the first sustained gap: the audible part of
    the sample, stopping at the first run of ~0.05 s of silence (a real
    gap — the samples' quiet ADPCM tails stay above AUDIBLE_MIN, and the
    next send is 60 title frames away, so the first gap is the sample's
    own end, not the next send's start)."""
    i0 = int(t0 * WAV_FRAME)
    if i0 >= len(x):
        return 0.0
    gap = int(0.05 * WAV_FRAME)
    i = i0 + gap
    while i < len(x):
        if abs(x[i]) < AUDIBLE_MIN:
            # a 0.05 s run of quiet = a gap; the sample ended
            run = 1
            while run < gap and i + run < len(x) and abs(x[i + run]) < AUDIBLE_MIN:
                run += 1
            if run >= gap:
                return (i - i0) / WAV_FRAME
        i += 1
    return (len(x) - i0) / WAV_FRAME


# --------------------------------------------------------- Attract A4/D1 ----
# The demo-sound leg runs the normal cart (the demo compiled in) under the
# MVS BIOS. The probe taps the 68k's REG_SOUND writes and bios_game_dip[6]
# (the DEMO SOUND enum), and gives three windows: the header default OFF
# for the entry cycle and a full 3245-frame cycle (a 60-frame D hold there
# proves MVS ignores D and writes no confirmation), then a full cycle with
# the DIP ON, then a real game started after the OFF demo.


def parse_demo_header():
    """(seed, level, frames, input bytes per frame) from build/demo_map.h."""
    text = open(os.path.join(HERE, "..", "build", "demo_map.h")).read()
    seed = int(re.search(r"#define DEMO_SEED\s+0x([0-9a-fA-F]+)", text).group(1), 16)
    level = int(re.search(r"#define DEMO_LEVEL\s+(\d+)", text).group(1))
    frames = int(re.search(r"#define DEMO_FRAMES\s+(\d+)", text).group(1))
    runs = [(int(b, 16), int(n))
            for b, n in re.findall(r"\{\s*0x([0-9a-fA-F]+)\s*,\s*(\d+)\s*\}", text)]
    inputs = []
    for b, n in runs:
        inputs.extend([b] * n)
    if len(inputs) != frames:
        raise ValueError(f"build/demo_map.h has {len(inputs)} frames, "
                         f"DEMO_FRAMES says {frames}")
    return seed, level, frames, inputs


def parse_demo_probe(path):
    """-> (sends, es, ds, fs): sends = (mame_n, phase, epoch, fc, cmd,
    user_mode); es / ds = the E/D tuples (n, [prev_epoch,] epoch, fc, dip);
    fs = (n, epoch, fc, row-21 text) from the F records."""
    sends, es, ds, fs = [], [], [], []
    with open(path, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "replace")
            p = line.split()
            if not p:
                continue
            if p[0] == "S":
                sends.append((int(p[1]), p[2], int(p[3]), int(p[4]),
                              int(p[5]), int(p[6])))
            elif p[0] == "E":
                es.append(tuple(int(x) for x in p[1:]))
            elif p[0] == "D":
                ds.append(tuple(int(x) for x in p[1:]))
            elif p[0] == "F":
                fs.append((int(p[1]), int(p[2]), int(p[3]),
                           bytes.fromhex(p[4]).decode("ascii", "replace")))
    return sends, es, ds, fs


def demo_commands(inputs, seed, level, nframes):
    """the demo's sound commands, frame by frame, from the same model the
    M7 game-sound checker uses: tests/sound_model.py's Sound.cmds (the
    scuttle's spin period, the collapse's alternating beats, the pip's
    20-frame counter) around the rules/ship/missiles/radar frame model."""
    ship = sm.Ship()
    mis = mm.Missiles(level=level, seed=seed)
    rules = rm.Rules(level)
    radar = radm.Radar()
    state = (ship, mis, rules, radar)
    sound = sound_model.Sound()
    pred = []
    prev = 0
    for f, cur in enumerate(inputs[:nframes], 1):
        pressed = cur & ~prev
        frame_model(state, cur, pressed)
        for c in sound.cmds(ship, mis, rules, radar, rules._died):
            pred.append((f, c))
        prev = cur
    return pred


def _tool(name):
    path = shutil.which(name)
    if path:
        return path
    path = os.path.expanduser(
        "~/Development/github/dciabrin/ngdevkit/local/bin/" + name)
    if os.path.exists(path):
        return path
    raise FileNotFoundError(name)


def decode_soft_dip(elf):
    """the cart's .text.boot soft-DIP tables, decoded with ngdevkit's
    rom_dip_t format (name 16, 2 time DIPs, 2 int DIPs, 10 enum DIPs,
    then 12-byte strings)."""
    nm = _tool("m68k-neogeo-elf-nm")
    objcopy = _tool("m68k-neogeo-elf-objcopy")
    syms = {}
    for line in subprocess.check_output([nm, elf], text=True).splitlines():
        parts = line.split()
        if len(parts) >= 3:
            try:
                syms[parts[2]] = int(parts[0], 16)
            except ValueError:
                pass
    with tempfile.NamedTemporaryFile() as tmp:
        subprocess.check_call([objcopy, "-O", "binary", "-j", ".text.boot",
                               elf, tmp.name])
        blob = open(tmp.name, "rb").read()
    out = []
    for region in ("jp", "us", "eu"):
        sym = f"dip_{region}_rom"
        if sym not in syms:
            raise ValueError(f"{sym} is not in {elf}: the cart has no soft-DIP "
                             f"table")
        addr = syms[sym]
        d = blob[addr:addr + 68]
        if len(d) < 68:
            raise ValueError(f"{sym}: only {len(d)} bytes in .text.boot")
        name = d[0:16].decode("ascii", "replace").rstrip()
        enum = d[22:32]
        selected, length = enum[0] >> 4, enum[0] & 0xf
        strings = [d[32 + i * 12:32 + (i + 1) * 12]
                   .decode("ascii", "replace").rstrip() for i in range(3)]
        out.append(dict(region=region, addr=addr, name=name,
                        selected=selected, length=length, strings=strings))
    return out


def check_demo_sound(probe, wav, elf):
    """Attract A4/D1's proofs 1, 2 and 4 on the MVS demo-sound leg."""
    failures = []
    seed, level, frames, inputs = parse_demo_header()
    sends, es, ds, fs = parse_demo_probe(probe)

    # proof 1a: the header default is OFF; the entry cycle and a full cycle
    # must send nothing
    default = [(fc, cmd) for _n, ph, _ep, fc, cmd, _um in sends
               if ph == "default"]
    if default:
        failures.append(f"demo sound default OFF: {len(default)} command(s) "
                        f"were sent during the default demo: {default[:8]}")
    else:
        print(f"demo sound default OFF: the entry cycle and epoch 2 "
              f"({frames} demo frames) sent no REG_SOUND command")
    e1 = next((m for m in es if m[2] == 1), None)
    e2 = next((m for m in es if m[2] == 2), None)
    if e1 is None or e1[4] != 1:
        failures.append(f"the header default DIP is not OFF: E epoch 1 "
                        f"{e1!r} (want dip 1)")
    if e2 is None or e2[4] != 1:
        failures.append(f"epoch 2 did not run with the default OFF: E "
                        f"{e2!r} (want dip 1)")
    if e1 is not None and e1[4] == 1 and e2 is not None and e2[4] == 1:
        print("demo sound default: the BIOS DIP byte is OFF (1) for epochs "
              "1 and 2")

    # proof 4: an MVS D hold never writes the row-21 confirmation
    conf = [r for r in fs if "DEMO SOUND" in r[3]]
    if conf:
        failures.append(f"MVS D press: the row-21 confirmation appeared: "
                        f"{conf[:4]}")
    else:
        print(f"MVS D hold: no row-21 confirmation in {len(fs)} F records")

    # proof 1b: the ON phase (a full cycle), every command equals the model's
    pred = demo_commands(inputs, seed, level, frames)
    on = [(fc, cmd) for _n, ph, _ep, fc, cmd, _um in sends if ph == "on"]
    if on == pred:
        by = {}
        for _fc, c in on:
            by[c] = by.get(c, 0) + 1
        print(f"demo sound ON: {len(on)} commands in epoch 3 equal the model's "
              f"{len(pred)} (fire {by.get(4, 0)}, jump {by.get(5, 0)}, "
              f"hit {by.get(6, 0)}, crack {by.get(7, 0)}, pip {by.get(8, 0)}, "
              f"move {by.get(9, 0)})")
    else:
        if len(on) != len(pred):
            failures.append(f"demo sound ON: {len(on)} cart commands, the "
                            f"model predicts {len(pred)}")
        for i, (a, b) in enumerate(zip(on, pred)):
            if a != b:
                failures.append(f"demo sound ON: command {i} is cart {a}, "
                                f"model {b}")
                break
        if len(on) != len(pred) and on and pred and on[:len(pred)] == pred:
            failures.append(f"demo sound ON: cart has extra commands "
                            f"{on[len(pred):]}")

    # proof 1c: a real game started after the OFF demo still sounds
    game = [(n, fc, cmd) for n, ph, _ep, fc, cmd, um in sends
            if ph == "game" and um == 2]
    if not game:
        failures.append("the real game started after the OFF demo sent no "
                        "sound command")
    else:
        print(f"real game after OFF: {len(game)} command(s), first "
              f"(mame {game[0][0]}, fc {game[0][1]}, cmd {game[0][2]})")

    # proof 1d: the recorded WAV proves the ON demo's pip and the real
    # game's first sound are audible on MVS (the driver is playing).
    try:
        x = read_wav_mono(wav)
    except Exception as e:      # noqa: BLE001
        x = None
        failures.append(f"the WAV could not be read: {e}")
    if x is not None:
        on_pip = next(((n, fc, cmd) for n, ph, _ep, fc, cmd, _um in sends
                       if ph == "on" and cmd == 8), None)
        if on_pip is None:
            failures.append("no ON-demo pip send to sample in the WAV")
        else:
            n, fc, _cmd = on_pip
            # the tap runs during the cart frame; one frame either side is
            # inside the pip's 0.06 s + the sample's ~0.02 s ADPCM padding
            pk = max(peak(x, (n - 1) / FRAME_HZ, (n + 2) / FRAME_HZ),
                     peak(x, n / FRAME_HZ, (n + 2) / FRAME_HZ))
            if pk <= LOUD_MIN[8]:
                failures.append(f"demo sound ON: the WAV is not loud after "
                                f"the pip at demo frame {fc} (peak {pk}, "
                                f"want > {LOUD_MIN[8]})")
            else:
                print(f"demo sound ON: the pip at demo frame {fc} is loud in "
                      f"the WAV (peak {pk})")
        if game:
            n, fc, cmd = game[0]
            pk = peak(x, (n - 1) / FRAME_HZ, (n + 3) / FRAME_HZ)
            if pk <= LOUD_MIN.get(cmd, 1000):
                failures.append(f"real game after OFF: the WAV is not loud "
                                f"after command {cmd} at fc {fc} (peak {pk}, "
                                f"want > {LOUD_MIN.get(cmd, 1000)})")
            else:
                print(f"real game after OFF: command {cmd} at fc {fc} is loud "
                      f"in the WAV (peak {pk})")

        # R1 proof 2: the ON demo is a real game, and its move, jump, fire,
        # hit and crack samples must be loud in the WAV. Pick the first
        # frame whose only send is that command (isolated), then the send
        # time from the probe's S record (it notices the send on the MAME
        # frame after the cart's) and peak right after it. The dense demo
        # overlaps effects, so only the "loud after" claim is made (the
        # frame-for-frame comparison already proves the send is at that fc).
        pred_by_fc = {}
        for fc, cmd in pred:
            pred_by_fc.setdefault(fc, []).append(cmd)
        for kind, name in ((9, "move"), (5, "jump"), (4, "fire"),
                           (6, "hit"), (7, "crack")):
            frames = [fc for fc, cs in sorted(pred_by_fc.items())
                      if cs == [kind]]
            if not frames:
                failures.append(f"the ON demo has no isolated {name} send "
                                f"to sample in the WAV")
                continue
            fc = frames[0]
            rec = next(((n, _fc) for n, ph, _ep, _fc, cmd, _um in sends
                        if ph == "on" and _fc == fc and cmd == kind), None)
            if rec is None:
                failures.append(f"the ON demo's {name} at fc {fc} is not in "
                                f"the probe's log")
                continue
            n = rec[0]
            t = (n - 1) / FRAME_HZ
            pk = peak(x, t, t + 0.2)
            if pk <= LOUD_MIN[kind]:
                failures.append(f"demo sound ON: the {name} at demo frame "
                                f"{fc} is not loud in the WAV (peak {pk}, "
                                f"want > {LOUD_MIN[kind]})")
            else:
                print(f"demo sound ON: the {name} at demo frame {fc} is loud "
                      f"in the WAV (peak {pk})")

    # proof 2: the ROM header's soft-DIP table, decoded with ngdevkit's
    # rom_dip_t format, names the DIP and its ON/OFF choices with OFF
    # selected by default (the BIOS game-settings screen reads this).
    try:
        dips = decode_soft_dip(elf)
    except Exception as e:      # noqa: BLE001
        failures.append(f"soft-DIP table: {e}")
    else:
        for d in dips:
            want = (d["name"] == "E-SRG" and d["selected"] == 1
                    and d["length"] == 2
                    and d["strings"] == ["DEMO SOUND", "ON", "OFF"])
            if not want:
                failures.append(
                    f"soft DIP {d['region']} at 0x{d['addr']:x}: name "
                    f"{d['name']!r}, selected {d['selected']}, length "
                    f"{d['length']}, strings {d['strings']!r}; want 'E-SRG', "
                    f"selected 1 (OFF), length 2, ['DEMO SOUND', 'ON', 'OFF']")
        if not failures or not any("soft DIP" in f for f in failures):
            print(f"soft DIP: {len(dips)} region table(s) decode to E-SRG / "
                  f"'DEMO SOUND' / 'ON' / 'OFF' with OFF (selected 1) the "
                  f"default")
    return failures


def main():
    snap_png, probe, wav = sys.argv[1], sys.argv[2], sys.argv[3]
    mode = sys.argv[4] if len(sys.argv) > 4 else "aes"
    if mode == "demo":
        elf = (sys.argv[5] if len(sys.argv) > 5
               else os.path.join(HERE, "..", "build", "rom.elf"))
        failures = check_demo_sound(probe, wav, elf)
        if failures:
            print("FAIL demo-sound:", *("  - " + f for f in failures), sep="\n")
            return 1
        print("PASS demo-sound")
        return 0
    mvs = mode == "mvs"
    log, _end = parse(probe)
    failures = []

    # ---- 1. every send present and acknowledged ----
    by_cmd = {}
    for mame_n, tf, log_tf, cmd, ok in log:
        by_cmd.setdefault((tf, cmd), []).append((mame_n, log_tf, ok))
    for tf, cmd in SENDS:
        recs = by_cmd.get((tf, cmd), [])
        if not recs:
            failures.append(f"title frame {tf}: command {cmd} never logged")
            continue
        for mame_n, log_tf, ok in recs:
            if log_tf != tf:
                failures.append(f"frame {tf} cmd {cmd}: log title frame "
                                f"{log_tf} != {tf}")
            if ok != 1:
                failures.append(f"frame {tf} cmd {cmd}: not acknowledged "
                                f"(ok={ok})")
    if failures:
        print("FAIL sound:", *("  - " + f for f in failures), sep="\n")
        return 1

    # the send times: the probe notices a send on the MAME frame AFTER the
    # cart's frame that made it, so the send was on frame (mame_n - 1).
    # The WAV onset sits ~2.6 ms later still, but the 0.1 s before/after
    # windows are generous enough that (mame_n-1)/FRAME_HZ places them
    # correctly (measured: the fire's first sample at 9.988 s = frame 591
    # for a probe notice at 592).
    send_t = {tf: {} for tf, _ in SENDS}
    for mame_n, tf, log_tf, cmd, ok in log:
        send_t[tf][cmd] = (mame_n - 1) / FRAME_HZ

    x = read_wav_mono(wav)
    # ---- 2. each single: silent before, loud after, right length ----
    for tf, cmd in SINGLES:
        t = send_t[tf][cmd]
        if peak(x, t - 0.1, t) >= SILENT_PEAK:
            failures.append(f"frame {tf} ({cmd}): not silent in 0.1 s "
                            f"before t={t:.4f}")
        pk = peak(x, t, t + 0.2)
        if pk <= LOUD_MIN[cmd]:
            failures.append(f"frame {tf} ({cmd}): not loud right after "
                            f"t={t:.4f} (peak {pk}, want > {LOUD_MIN[cmd]})")
        alen = audible_len(x, t)
        if abs(alen - LEN[cmd]) > LEN_TOL:
            failures.append(f"frame {tf} ({cmd}): audible length {alen:.3f} s, "
                            f"want {LEN[cmd]} ±{LEN_TOL}")
    # ---- 3. the frame-400 pair: both acked, the hit's 0.75 s plays ----
    t = send_t[400][6]
    t8 = send_t[400][8]
    # the pip (channel 1) must not cut the hit (channel 2): the audio after
    # the hit's start lasts its full 0.75 s
    alen = audible_len(x, t)
    if abs(alen - AUDIO_LEN[6]) > LEN_TOL:
        failures.append(f"frame 400: audio after 6 lasts {alen:.3f} s, "
                        f"want the hit's {AUDIO_LEN[6]} ±{LEN_TOL}")
    # both are acknowledged (2-by-cmd check above already proved it; the
    # pair's own records must BOTH be present — the shared-frame send)
    if len(by_cmd.get((400, 6), [])) < 1 or len(by_cmd.get((400, 8), [])) < 1:
        failures.append("frame 400: both 6 and 8 must be logged")
    # the pip is audible too (it plays on its own channel, over the hit)
    if peak(x, t8, t8 + 0.2) <= LOUD_MIN[8]:
        failures.append(f"frame 400: pip not loud after t={t8:.4f}")

    if failures:
        print("FAIL sound:", *("  - " + f for f in failures), sep="\n")
        return 1
    print(f"PASS sound ({'MVS' if mvs else 'AES'}): {len(SENDS)} sends all "
          f"acknowledged ({', '.join(f'{tf}:{cmd}' for tf, cmd in SENDS)}), "
          f"each silent before / loud after / right length, frame 400 plays "
          f"the hit's 0.75 s with the pip over it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
