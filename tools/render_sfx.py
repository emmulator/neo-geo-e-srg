#!/usr/bin/env python3
"""render_sfx.py — the Vectrex game's sound effects, rendered as WAV files.

    render_sfx.py OUTDIR

The Vectrex game (vectrex-e-srg 1.1.0, src/e-srg.c sound_update) plays its
effects by writing the AY-3-8912 directly, a few registers per game-loop
step. This tool replays exactly those register writes, one step every 1/50 s
(the rate the scripts were written for), through a model of the AY at the
Vectrex's 1.5 MHz clock, and writes each effect alone as a mono 16-bit WAV at
the AY's internal rate (clock / 8 = 187500 Hz). The Makefile resamples them
to 18.5 kHz with sox for the ADPCM-A encoder.

The effects (one WAV each):
  fire   channel A, 12 steps: tone period 0x60 + 40 per step (pitch falls),
         volume 14 .. 4, then off
  jump   channel A, 24 steps: tone period 0x200 - 12 per step (rises),
         volume 10, then off
  hit    channel C, 32 steps: noise only, period 31 - (t >> 1) (deepens),
         volume min(15, t >> 1) (fades); also the dome death's rumble
  crack  channel C, 22 steps: a bright noise snap (noise 3, volume 15,
         tone C mixed in), then deep noise (31) with a falling thud (tone C
         period 0x300 + 40 per step), volume min(15, t)
  pip    channel B, 3 steps: tone period 0x50 (~1.2 kHz), volume 12 — the
         lock-on pip, which the game repeats every 16 steps while locked

Every effect is rendered at the same scale (AY full volume = FULL of int16),
so their relative loudness is the Vectrex's.
"""
import os
import sys
import wave

import numpy as np

CLOCK = 1_500_000          # the Vectrex's AY clock (Hz)
RATE = CLOCK // 8          # the AY's internal step rate: tone/noise counters
STEP_HZ = 50               # one sound_update per 1/50 s
SPS = RATE // STEP_HZ      # internal samples per step (3750)
FULL = 0.75                # AY full volume, of int16 full scale: the hit peaks ~0.67, and
                           # the 18.5 kHz resample's overshoot stays unclipped

# the AY-3-8910's 16 volume levels (MAME's ay8910 measured table, normalised)
VOL = np.array([0.0, 0.0106, 0.0150, 0.0222, 0.0320, 0.0466, 0.0665, 0.1039,
                0.1237, 0.1986, 0.2803, 0.3548, 0.4702, 0.6030, 0.7530, 1.0])


class AY:
    """one AY channel's tone and the shared noise, at RATE (= clock / 8)."""

    def __init__(self):
        self.tone_count = 0
        self.tone_out = 0
        self.noise_count = 0
        self.lfsr = 1
        self.noise_out = 1

    def run(self, n, tone_period, noise_period, tone_on, noise_on, vol):
        """n internal samples; returns the channel's level per sample (0..1)."""
        out = np.zeros(n)
        tp = max(1, tone_period & 0xFFF)
        np_ = max(1, noise_period & 0x1F)
        level = VOL[vol & 15]
        for i in range(n):
            # the tone flips every tp steps of clock/8 (so f = clock / (16 tp))
            self.tone_count += 1
            if self.tone_count >= tp:
                self.tone_count = 0
                self.tone_out ^= 1
            # the noise LFSR (17 bits, taps 0 and 3) shifts every 2 np steps
            self.noise_count += 1
            if self.noise_count >= 2 * np_:
                self.noise_count = 0
                bit = (self.lfsr ^ (self.lfsr >> 3)) & 1
                self.lfsr = (self.lfsr >> 1) | (bit << 16)
                self.noise_out = self.lfsr & 1
            t = self.tone_out | (0 if tone_on else 1)
            z = self.noise_out | (0 if noise_on else 1)
            out[i] = level if (t & z) else 0.0
        return out


def render(steps):
    """steps: a list of (tone_period, noise_period, tone_on, noise_on, vol),
    one per 1/50 s; returns the samples (float, DC removed)."""
    ay = AY()
    parts = [ay.run(SPS, *s) for s in steps]
    x = np.concatenate(parts) if parts else np.zeros(0)
    if len(x):
        x = x - x.mean()                # the AY's output is unipolar: centre it
    return x


def fire():
    period, steps = 0x60, []
    for left in range(11, -1, -1):      # snd_fire 12: decremented first
        period += 40
        steps.append((period, 0, True, False, left + 3 if left else 0))
    return steps


def jump():
    period, steps = 0x200, []
    for left in range(23, -1, -1):      # snd_jump 24
        period -= 12
        steps.append((period, 0, True, False, 10 if left else 0))
    return steps


def hit():
    steps = []
    for t in range(31, -1, -1):         # snd_hit 32: decremented first
        steps.append((0, 31 - (t >> 1), False, True, min(15, t >> 1)))
    return steps


def crack(prev_thud=0x300 + 40 * 20):
    """tone C keeps the previous crack's last thud period during the snap
    (the registers are only rewritten from step 3 on); the default is the
    period every crack after the first one ends on."""
    steps, thud, tone, noise, vol = [], 0x300, prev_thud, 3, 15
    for c in range(22, 0, -1):          # snd_crack 22 .. 1
        if c == 22:
            noise, vol = 3, 15
        elif c == 19:
            noise = 31
        if c < 20:
            thud += 40
            tone = thud
            vol = min(15, c)
        if c == 1:
            vol = 0                     # --snd_crack == 0 silences it in the same step
        steps.append((tone, noise, True, True, vol))
    return steps


def pip():
    return [(0x50, 0, True, False, 12)] * 3


EFFECTS = {"fire": fire, "jump": jump, "hit": hit, "crack": crack, "pip": pip}


def write_wav(path, x):
    pcm = np.clip(np.round(x * FULL * 32767), -32768, 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for name, steps in EFFECTS.items():
        write_wav(os.path.join(out, f"{name}.wav"), render(steps()))


if __name__ == "__main__":
    main()
