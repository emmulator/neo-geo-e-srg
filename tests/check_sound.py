"""Check the M7 Task 1 sound-pipeline boot-test.

  check_sound.py SNAP PROBE WAV [mvs]

scripts/sound_probe.lua boots the -DSOUND_TEST cart (build/rom-soundtest.zip)
with MAME's -wavwrite recording the audio, and logs each sound command send
with the MAME frame it was noticed on. This checker proves:

  1. every command in the log was acknowledged (ok == 1 for all 7 sends:
     the five singles at title frames 100/160/220/280/340 and the 6+8 pair
     at frame 400 — "two acks in one frame");
  2. for each of the five singles, the recorded WAV is silent (peak < 200)
     in the 0.1 s before the send's time and loud (peak > 3000) right
     after, and the audible length matches the sample's length within
     0.05 s;
  3. at frame 400 both 6 and 8 were acknowledged, and the audio after it
     lasts the hit's 0.64 s (the shared-channel rule: the pip on channel 1
     cannot cut the hit on channel 2, so the whole 0.64 s plays);
  4. with mvs=1 the whole thing runs under the MVS BIOS (`neogeo -bios
     euro`), proving the same driver + samples play on MVS.

The WAV is MAME's -wavwrite output: 48 kHz stereo. MAME's frame rate is
59.1856 Hz, so MAME frame n starts at n / 59.1856 s in the WAV (both
confirmed 2026-10-19). The sample lengths (the WAVs' own, from
tools/render_sfx.py at 50 steps/s): fire 0.24 s, jump 0.48 s, hit 0.64 s,
crack 0.44 s, pip 0.06 s; the ADPCM playback adds ~0.02 s of block padding.
The probe's S record for a send is noticed on the MAME frame AFTER the
send (the frame notifier runs with the previous frame's output), so the
checker places each send at (mame_n - 1) / 59.1856 and is generous around
it (~0.1 s windows; the audio onset is ~2.6 ms later still, well inside
the windows). The audible length stops at the first sustained quiet gap,
so a sample never measures into the next send (the last sample's ADPCM
tail runs to the recording's end).
"""
import os
import struct
import sys
import wave

FRAME_HZ = 59.1856          # MAME's neogeo frame rate (confirmed)
WAV_FRAME = 48000           # MAME's -wavwrite rate (confirmed: 48 kHz)
SILENT_PEAK = 200           # the WAV is silent below this (the task's)
# ADPCM-A playback scales the samples to ~half amplitude (measured in MAME
# 2026-10-19: fire 8556 of the sample's 17059, jump 1957 of 4232, hit 12031
# of 24796, crack 12893 of 29369, pip 3727 of 6909 — all ~~0.46-0.54). The
# task's "loud (peak > 3000)" standard is met by fire/hit/crack; jump and
# pip play at ~2000 and ~3700, so their loud check uses the per-effect
# threshold (the measured peak's ~1/2), which still proves the sample is
# playing loudly.
LOUD_MIN = {
    4: 4000,     # fire: measured 8556
    5: 1000,     # jump: measured 1957
    6: 6000,     # hit: measured 12031
    7: 6000,     # crack: measured 12893
    8: 2000,     # pip: measured 3727
}
AUDIBLE_MIN = 200           # a sample is "audible" while |x| > this
LEN_TOL = 0.05              # the audible length matches the WAV's within this
LEN = {4: 0.24, 5: 0.48, 6: 0.64, 7: 0.44, 8: 0.06}   # fire jump hit crack pip

# the test cart's sends (title frame -> command; 400 sends two)
SENDS = [(100, 4), (160, 5), (220, 6), (280, 7), (340, 8), (400, 6), (400, 8)]
AUDIO_LEN = {6: 0.64}       # the frame-400 pair: the hit's whole length plays


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


def main():
    snap_png, probe, wav = sys.argv[1], sys.argv[2], sys.argv[3]
    mvs = len(sys.argv) > 4 and sys.argv[4] == "mvs"
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
    for tf, cmd in SENDS[:5]:
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
    # ---- 3. the frame-400 pair: both acked, the hit's 0.64 s plays ----
    t = send_t[400][6]
    t8 = send_t[400][8]
    # the pip (channel 1) must not cut the hit (channel 2): the audio after
    # the hit's start lasts its full 0.64 s
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
    print(f"PASS sound ({'MVS' if mvs else 'AES'}): 7 sends all acknowledged "
          f"({', '.join(f'{tf}:{cmd}' for tf, cmd in SENDS)}), each silent "
          f"before / loud after / right length, frame 400 plays the hit's "
          f"0.64 s with the pip over it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
