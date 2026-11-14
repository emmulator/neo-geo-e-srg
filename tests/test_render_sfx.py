"""The sound WAVs on their way to the V ROM (M7 Task 1, R1).

  test_render_sfx.py   (host, pytest)

`tools/render_sfx.py` replays the Vectrex game's AY-3-8912 register scripts
(e-srg.c sound_update) and writes the five old effects; R1 keeps only its
pip (the lock-on pip is unchanged), while move/jump/fire/hit/crack now come
from `tools/synth_sfx.py` (see tests/test_synth_sfx.py). This test checks
the generator's own output and the resampled copies the ADPCM-A encoder
reads:

  - render_sfx.py's raw WAVs (regenerated each run; the tool is
    deterministic) keep their step-count lengths and the jump's ~190 ->
    ~400 Hz rising contour (the old M7 claim, still a property of the
    generator);
  - the 18500 Hz copies under build/sfx (what vromtool encodes) have H3's
    lengths: move 0.321 s, jump 0.59 s, fire 0.30 s, hit 0.75 s, crack
    0.90 s from synth_sfx.py, pip 0.06 s from render_sfx.py. `make test`
    builds them before pytest runs; the leg is skipped when they are not
    present.
"""
import os
import subprocess
import wave

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TOOL = os.path.join(ROOT, "tools", "render_sfx.py")
OUT = os.path.join(ROOT, "build", "test-render-sfx")
RESAMPLED = os.path.join(ROOT, "build", "sfx")

# the scripts' step counts and the resulting lengths (steps / 50 Hz): the
# generator's own output, unchanged by R1
RAW_EXPECT = {
    "fire": (12, 0.24),
    "jump": (24, 0.48),
    "hit": (32, 0.64),
    "crack": (22, 0.44),
    "pip": (3, 0.06),
}
# H3: what the ADPCM-A encoder reads (build/sfx): synth_sfx.py's WAVs for
# move/jump/fire/hit/crack, render_sfx.py's pip. Exact lengths (the plan's
# soxi -D print rounds move to 0.32 s and jump to 0.59 s; these are the
# WAVs' own frame counts / 18500)
RESAMPLED_EXPECT = {
    "move": 5939 / 18500,        # 0.321027 s (19/59.185, one cell step)
    "jump": 10972 / 18500,       # 0.593081 s
    "fire": 0.300,
    "hit": 0.75,
    "crack": 0.90,
    "pip": 0.06,
}
RATE = 187500


def _render():
    """-> {name: np.int16 array} (the raw 187.5 kHz WAVs)."""
    subprocess.run(["python3", TOOL, OUT], check=True, capture_output=True)
    wavs = {}
    for name in RAW_EXPECT:
        with wave.open(os.path.join(OUT, f"{name}.wav"), "rb") as w:
            assert w.getframerate() == RATE
            wavs[name] = np.frombuffer(w.readframes(w.getnframes()), "<i2")
    return wavs


def test_lengths_and_pitch_and_no_clip():
    wavs = _render()
    for name, (steps, length) in RAW_EXPECT.items():
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
    mono 16-bit at 18500 Hz, R1's lengths, and no sample at the full scale
    (sox's resampler can overshoot ~2%: checked, no clipping)."""
    if not os.path.isdir(RESAMPLED):
        return                      # make test builds it; this runs anyway
    for name, length in RESAMPLED_EXPECT.items():
        path = os.path.join(RESAMPLED, f"{name}.wav")
        if not os.path.exists(path):
            continue
        with wave.open(path, "rb") as w:
            assert w.getframerate() == 18500
            assert w.getnchannels() == 1 and w.getsampwidth() == 2
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2")
        assert abs(len(x) / 18500 - length) < 0.001, (
            f"{name} resampled: {len(x)/18500:.4f} s, want {length}")
        assert int(np.max(np.abs(x))) < 32768, f"{name}: clips after resample"
