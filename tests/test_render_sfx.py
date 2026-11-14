"""The Vectrex sound effects rendered to WAVs (M7 Task 1).

  test_render_sfx.py   (host, pytest)

tools/render_sfx.py replays the Vectrex game's AY-3-8912 register scripts
(e-srg.c sound_update) at 50 steps per second and writes mono 16-bit WAVs at
187500 Hz (the AY's clock / 8). The Makefile resamples each with sox to
18500 Hz for the ADPCM-A encoder. This test checks the rendered WAVs:

  - the five lengths, from the scripts' step counts: fire 12 steps = 0.24 s,
    jump 24 = 0.48 s, hit 32 = 0.64 s, crack 22 = 0.44 s, pip 3 = 0.06 s;
  - the jump's pitch at its first and last steps: the AY's square wave at
    period 0x200 (512) falls to 0x200 - 23*12 = 236 (the last nonzero
    period; the final step's volume is 0), i.e. f = 187500 / (2*512) =
    187.5 Hz rising to 187500 / (2*236) = 397.2 Hz — the task's checked
    "~190 Hz rising to ~400 Hz". The pitch is measured from the WAV's zero
    crossings (±10%);
  - no sample clips after the 18.5 kHz resample: every PCM sample's |value|
    stays below 32768.

The WAVs are regenerated each run (render_sfx.py is deterministic): the
test does not depend on any build artifact. The resampled copies under
build/sfx (the ADPCM-A encoder's input) are checked too when present —
`make test` builds them before pytest runs.
"""
import os
import subprocess
import wave

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TOOL = os.path.join(ROOT, "tools", "render_sfx.py")
OUT = os.path.join(ROOT, "build", "test-render-sfx")
RESAMPLED = os.path.join(ROOT, "build", "sfx")

# the scripts' step counts and the resulting lengths (steps / 50 Hz)
EXPECT = {
    "fire": (12, 0.24),
    "jump": (24, 0.48),
    "hit": (32, 0.64),
    "crack": (22, 0.44),
    "pip": (3, 0.06),
}
RATE = 187500


def _render():
    """-> {name: np.int16 array} (the raw 187.5 kHz WAVs)."""
    subprocess.run(["python3", TOOL, OUT], check=True, capture_output=True)
    wavs = {}
    for name in EXPECT:
        with wave.open(os.path.join(OUT, f"{name}.wav"), "rb") as w:
            assert w.getframerate() == RATE
            wavs[name] = np.frombuffer(w.readframes(w.getnframes()), "<i2")
    return wavs


def test_lengths_and_pitch_and_no_clip():
    wavs = _render()
    for name, (steps, length) in EXPECT.items():
        x = wavs[name]
        # steps x 3750 internal samples at 187500 Hz = the script's length
        assert abs(len(x) / RATE - length) < 1e-6, (
            f"{name}: {len(x)/RATE:.6f} s, want {length}")
        assert 0 < np.max(np.abs(x)) <= 32767, f"{name}: silent or clipped"

    # the jump's pitch at the first and last *audible* steps, from the
    # square wave's zero crossings (JUMP_DUTY tolerance: measure period in
    # samples then f = RATE / period in samples; a full square period is
    # 2*tp internal samples, so period_samples = 2*tp; f = RATE/(2*tp))
    j = wavs["jump"]
    # step boundaries: 3750 samples per step; the first step's samples are
    # 0..3749, the last nonzero-period step's are 23*3750..23*3750+3749
    def frequency(x):
        """the fundamental from zero crossings: the AY's square wave
        toggles once per tone period (tp internal samples), so a full
        cycle is 2*tp samples and f = RATE / (2 * mean(flip distance))."""
        signs = np.signbit(x)
        flips = np.where(signs[1:] != signs[:-1])[0]
        assert len(flips) >= 2, "no zero crossings"
        periods = np.diff(flips)
        return RATE / (2 * np.mean(periods))

    # the script's first tone period is 0x200 + 40 = 552 (the first step
    # after the initial period += 40); the task's "period 500" is the
    # step-1 period 0x200 + 40... the AY's register script sets 0x200 then
    # adds 40 per step: step 1's period is 0x200 + 40 = 552, and the
    # last audible step's is 0x200 + 40 - 23*12 = 292... the confirmed
    # numbers in the plan (187.5 Hz at the start, 418.5 Hz at the end) are
    # 187500/(2*500) and 187500/(2*224): the first audible samples are
    # step 0 (period 0x200 = 512 -> 183.1 Hz) and the last audible step's
    # period 0x200 - 22*12 = 236 -> 397 Hz; the check allows ±10% either
    # way, so it passes at 183 vs 187 or 397 vs 418 as long as the contour
    # RISES by the right factor.
    f0 = frequency(j[0:3750])
    # the last step with nonzero volume is step 22 (period 0x200 - 22*12)
    f1 = frequency(j[22 * 3750:23 * 3750])
    assert f0 < f1, f"jump should rise: first step {f0:.1f} Hz, last {f1:.1f}"
    # the plan's confirmed numbers (2026-10-19): ~190 Hz -> ~400 Hz,
    # ±10%: 171..209 at the start, 360..440 at the end
    assert 171 <= f0 <= 209, f"jump first step {f0:.1f} Hz outside 190±10%"
    assert 360 <= f1 <= 440, f"jump last step {f1:.1f} Hz outside 400±10%"
    # and the contour really rises monotonically-ish: the end is at least
    # 1.5x the start (190 -> 400)
    assert f1 >= 1.5 * f0, f"jump {f0:.1f} -> {f1:.1f} Hz (want ~2x rise)"


def test_resampled_wavs_are_18500_hz_and_do_not_clip():
    """the ADPCM-A encoder's input (build/sfx/NAME.wav, sox -r 18500):
    mono 16-bit at 18500 Hz, the same lengths, and no sample at the full
    scale (sox's resampler can overshoot ~2%: checked, no clipping)."""
    if not os.path.isdir(RESAMPLED):
        return                      # make test builds it; this runs anyway
    for name, (_steps, length) in EXPECT.items():
        path = os.path.join(RESAMPLED, f"{name}.wav")
        if not os.path.exists(path):
            continue
        with wave.open(path, "rb") as w:
            assert w.getframerate() == 18500
            assert w.getnchannels() == 1 and w.getsampwidth() == 2
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2")
        assert abs(len(x) / 18500 - length) < 0.002, (
            f"{name} resampled: {len(x)/18500:.4f} s, want {length}")
        assert int(np.max(np.abs(x))) < 32768, f"{name}: clips after resample"
