"""The player's synthesised effects (R1, H3, H5).

  test_synth_sfx.py   (host, pytest)

tools/synth_sfx.py writes the approved sounds (the spider's set 10-26 and
the hovercraft's hover/bolt 10-28) as mono 16-bit WAVs at 18500 Hz, the
ADPCM-A encoder's rate. The Makefile feeds them straight to vromtool.py
(sox at the same rate is bit-identical: checked when R1 was written). This
test regenerates them and checks:

  - the lengths from the generator: move 0.321 s, jump 0.59 s, fire 0.30 s,
    hit 0.75 s, crack 0.90 s (the plan's soxi -D numbers; jump is
    28/59.185 + 0.12 = 0.593081 s, move is 19/59.185 = round(5939) samples);
  - mono 16-bit at 18500 Hz;
  - no clipping (the generator normalises below full scale);
  - H5's level: the hover's WAV RMS is 0.040, under a third of the mean
    RMS of jump/fire/hit/crack (0.1465): the hover is the quiet bed, the
    effects are the events.

The raw render_sfx.py effects are still checked by
tests/test_render_sfx.py; only the pip is still the cart's.
"""
import os
import subprocess
import wave

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TOOL = os.path.join(ROOT, "tools", "synth_sfx.py")
OUT = os.path.join(ROOT, "build", "test-synth-sfx")
RATE = 18500
# the generator's exact lengths (the plan's soxi -D print rounded move to
# 0.32 s and jump to 0.59 s; these are the WAVs' own frame counts / 18500)
EXPECT = {
    "move": 5939 / 18500,        # 0.321027 s (19/59.185, one cell step)
    "jump": 10972 / 18500,       # 0.593081 s (28/59.185 + 0.12 s)
    "fire": 0.300,
    "hit": 0.75,
    "crack": 0.90,
}
# H5: the hover's level (the WAV RMS the synth's HOVER_RMS sets)
HOVER_RMS = 0.04


def test_synth_lengths_no_clip_and_hover_level():
    os.makedirs(OUT, exist_ok=True)          # synth_sfx.py does not create it
    subprocess.run(["python3", TOOL, OUT], check=True, capture_output=True)
    rms = {}
    for name, length in EXPECT.items():
        path = os.path.join(OUT, f"{name}.wav")
        with wave.open(path, "rb") as w:
            assert w.getframerate() == RATE, f"{name}: rate {w.getframerate()}"
            assert w.getnchannels() == 1 and w.getsampwidth() == 2, name
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2")
        got = len(x) / RATE
        assert abs(got - length) < 0.001, f"{name}: {got:.6f} s, want {length}"
        assert int(np.max(np.abs(x))) < 32768, f"{name}: clips"
        assert int(np.max(np.abs(x))) > 1000, f"{name}: silent or nearly so"
        rms[name] = np.sqrt((x.astype(np.float64) ** 2).mean()) / 32768

    # H5: move is the quiet hover bed; the events average over three times
    # its level
    others = np.mean([rms[n] for n in ("jump", "fire", "hit", "crack")])
    assert abs(rms["move"] - HOVER_RMS) < 0.001, (
        f"move RMS {rms['move']:.6f}, want {HOVER_RMS} (H5's hover level)")
    assert rms["move"] < others / 3, (
        f"move RMS {rms['move']:.6f}, want under a third of the others' mean "
        f"{others:.6f} (third {others / 3:.6f})")
    print(f"move RMS {rms['move']:.6f} is under a third of the others' mean "
          f"{others:.6f} (third {others / 3:.6f})")
