#!/usr/bin/env python3
"""synth_sfx.py OUTDIR: the player's sound effects, synthesised (the user
picked these from mockups: the spider's set 10-26, the hovercraft's hover
and bolt 10-28, https://claude.ai/artifact/KKgLAnfGNPKkvNLTABSPfM).

E-SRG is a retro arcade video game; these are its game sounds. Each effect is
written as a mono 16-bit WAV at 18500 Hz (the ADPCM-A encoder's rate):

  move.wav   the hovercraft's hover: a low soft rush, like a fan through a
             duct, with one gentle swell per step; no whine, no flutter.
             Exactly one cell step long (19 frames) and periodic, so steps
             join without a seam; RMS 0.04, under a third of the other
             effects' level                                          (hover D)
  jump.wav   the legs creak as they load (stick-slip pulses through two
             resonances), then a rising springy 'boing'           (jump A)
  fire.wav   the laser bolt: a falling blaster 'pew' (bolt B without
             its metallic ring)
  hit.wav    a missile shot down: a crack, a dull bang, debris     (airburst B)
  crack.wav  a missile hits the dome: a thud, glass splintering, a long
             low rumble as the dome shudders                      (dome hit B)

The high-score initials picker's (the user's picks 10-30 from the mockup
https://claude.ai/artifact/1tkdUiELoYjaNsXuFGqdVp; seed 1030, its eight
candidates rendered in the mockup's order and the four picks kept):

  tick.wav       a letter reaches the ring's front: a dry wooden ratchet
                 knock, 25 ms, quiet                         (wood ratchet)
  (type.wav     no longer written: the user replaced the synthesized
                 strike with a real recording on 10-31, assets/sfx/type.wav,
                 see CREDITS.md; picker_type is still rendered for the rng
                 order)
  bell.wav       END: the carriage-return bell, 0.9 s
  backspace.wav  the erase arrow removes an initial: the backspace key and
                 the escapement pawl kicked back

The noise comes from seeded generators consumed in the mockups' order
(seed 7: scuttle A, rendered and dropped, then jump A; seed 11: the lava,
airburst and dome-hit A variants and lava B are rendered and dropped
before airburst B and dome-hit B; the hover's air is seed 41), so the
files are exactly the ones the user approved. The lock-on pip stays the Vectrex's
(tools/render_sfx.py)."""
import sys
import wave

import numpy as np

SR = 18500
def t_(dur): return np.arange(int(dur * SR)) / SR

def bp(x, lo, hi):
    """band-pass by FFT mask (offline, so exact)"""
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))

def reson(x, f0, q):
    """two-pole resonator"""
    w = 2 * np.pi * f0 / SR; r = np.exp(-w / (2 * q))
    a1, a2 = -2 * r * np.cos(w), r * r
    y = np.zeros_like(x); y1 = y2 = 0.0
    for i, v in enumerate(x):
        y0 = v - a1 * y1 - a2 * y2; y[i] = y0; y2, y1 = y1, y0
    return y * (1 - r)

def sweep_reson(x, f_of_t, q):
    w = 2 * np.pi * f_of_t / SR; r = np.exp(-w / (2 * q))
    y = np.zeros_like(x); y1 = y2 = 0.0
    for i, v in enumerate(x):
        a1, a2 = -2 * r[i] * np.cos(w[i]), r[i] * r[i]
        y0 = v - a1 * y1 - a2 * y2; y[i] = y0 * (1 - r[i]); y2, y1 = y1, y0
    return y

def tick(partials, dur, decay, noise=0.3, hp=1500):
    """one metal leg-tip tap: a noise click plus inharmonic ringing partials"""
    t = t_(dur)
    s = sum(a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t / (decay * d))
            for f, a, d in partials)
    n = bp(rng.normal(size=len(t)), hp, 9000) * np.exp(-t / 0.0025) * noise * 3
    return s + n

def norm(x, peak=0.85):
    return x / np.abs(x).max() * peak

def scuttle(variant):
    dur = 19 / 59.185
    out = np.zeros(int(dur * SR) + 400)
    if variant == 0:      # six quick taps, alternating two leg-tips: light and skittery
        times = [0.0, 0.045, 0.105, 0.15, 0.21, 0.255]
        sets = [[(2900, 1, 1), (4630, .6, .7), (6900, .35, .5)],
                [(3350, 1, 1), (5210, .55, .7), (7600, .3, .5)]]
        for k, tt in enumerate(times):
            j = tt + rng.uniform(-0.006, 0.006)
            tk = tick(sets[k % 2], 0.05, 0.012, noise=0.5) * rng.uniform(0.7, 1.0)
            i = int(max(0, j) * SR); out[i:i + len(tk)] += tk
    else:                 # heavier: clicky taps plus a low servo whirr under them
        times = np.linspace(0, dur - 0.05, 8)
        for k, tt in enumerate(times):
            p = [(2100 + 300 * (k % 3), 1, 1), (3700, .5, .6), (5900, .3, .4)]
            tk = tick(p, 0.04, 0.009, noise=0.8, hp=1200) * (0.6 + 0.4 * (k % 2))
            i = int(tt * SR); out[i:i + len(tk)] += tk
        t = t_(len(out) / SR)
        whirr = np.sign(np.sin(2 * np.pi * (180 + 40 * np.sin(2 * np.pi * 6 * t)) * t))
        whirr = bp(whirr, 150, 1800) * 0.18 * np.sin(np.pi * np.clip(t / dur, 0, 1))
        out += whirr
    return norm(out, 0.7)

def jump(variant):
    dur = 28 / 59.185 + 0.12
    t = t_(dur)
    out = np.zeros(len(t))
    # creak: stick-slip pulses (rate rises as the legs load) through a wooden/metal resonance
    cre_end = 0.13
    rate = 55 + 260 * (t / cre_end) ** 1.5
    ph = np.cumsum(rate / SR); pulses = (np.diff(np.floor(ph), prepend=0) > 0).astype(float)
    pulses[t > cre_end] = 0
    pulses *= rng.uniform(0.5, 1.0, len(t))
    creak = reson(pulses, 1150, 9) + 0.6 * reson(pulses, 2400, 12)
    out += norm(creak, 0.55)
    # spring: a twangy 'boing' at launch, pitch with a fast wobble, rising then settling
    s = t - cre_end; on = s > 0; s = np.clip(s, 0, None)
    if variant == 0:
        f = 240 + 420 * (1 - np.exp(-s / 0.06)) - 120 * s
        wob = 1 + 0.22 * np.sin(2 * np.pi * 26 * s) * np.exp(-s / 0.18)
    else:
        f = 520 - 260 * (1 - np.exp(-s / 0.09))
        wob = 1 + 0.30 * np.sin(2 * np.pi * 34 * s) * np.exp(-s / 0.25)
    ph = 2 * np.pi * np.cumsum(f * wob) / SR
    tw = (np.sin(ph) + 0.45 * np.sin(2 * ph + 0.3) + 0.25 * np.sin(3.01 * ph)) * np.exp(-s / 0.16) * on
    attack = np.clip(s / 0.004, 0, 1)
    out += norm(tw * attack, 0.8)
    return norm(out, 0.8)

def write(path, x):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())

def lp(x, fc):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / fc) ** 4)
    return np.fft.irfft(X, len(x))

def bubbles(n, dur, lo, hi, rate, seed):
    """lava bubbles: short sine blips whose pitch rises as they pop"""
    r = np.random.default_rng(seed); t = t_(dur); out = np.zeros(len(t))
    k = int(rate * dur)
    for _ in range(k):
        st = r.uniform(0, dur * 0.85); ln = r.uniform(0.025, 0.06)
        f0 = r.uniform(lo, hi); tt = t_(ln)
        f = f0 * (1 + 1.8 * (tt / ln) ** 2)
        b = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt / ln) ** 2
        i = int(st * SR); out[i:i + len(b)] += b[:len(out) - i] * r.uniform(0.5, 1)
    return out

def lava(variant):
    dur = 0.40
    t = t_(dur)
    env = np.clip(t / 0.015, 0, 1) * np.exp(-np.clip(t - 0.015, 0, None) / 0.10)
    roar = lp(rng.normal(size=len(t)), 700 if variant == 0 else 500)
    # the throw: a low swell of thick noise, the pitch of its rumble falling
    fc = (700 if variant == 0 else 520) * np.exp(-t / 0.18) + 160
    gl = sweep_reson(rng.normal(size=len(t)), fc, 1.1)
    bub = bubbles(len(t), dur, 90, 260, 45 if variant == 0 else 30, 3 + variant)
    out = norm(roar, 1) * 0.6 * env + norm(gl, 1) * 0.7 * env + norm(bub, 1) * 0.55 * np.exp(-t / 0.22)
    if variant == 1:   # a sticky 'splort' at the start
        sp = np.sin(2 * np.pi * np.cumsum(70 + 160 * np.exp(-t / 0.02)) / SR) * np.exp(-t / 0.035)
        out += 0.7 * sp
    return norm(out, 0.85)

def airburst(variant):
    """a missile shot down: a sharp crack, a fiery bang, debris pattering away"""
    dur = 0.75
    t = t_(dur)
    snap = bp(rng.normal(size=len(t)), 1500, 8500) * np.exp(-t / 0.012)
    boom = lp(rng.normal(size=len(t)), 900 if variant == 0 else 600) * np.exp(-t / (0.16 if variant == 0 else 0.22))
    thump = np.sin(2 * np.pi * np.cumsum(120 * np.exp(-t / 0.08) + 45) / SR) * np.exp(-t / 0.09)
    deb = np.zeros(len(t))
    for _ in range(40 if variant == 0 else 25):
        st = rng.uniform(0.05, dur * 0.9); i = int(st * SR)
        c = bp(rng.normal(size=300), 2000, 8000) * np.exp(-np.arange(300) / 40)
        deb[i:i + 300] += c[:len(deb) - i] * rng.uniform(0.2, 1) * np.exp(-st / 0.3)
    out = 0.8 * norm(snap, 1) + norm(boom, 1) + 0.7 * thump + 0.35 * norm(deb, 1)
    return norm(out, 0.9)

def dome_hit(variant):
    """a missile striking the glass dome: a heavy impact, the panel cracking
    (bright splintering), then a low rumble"""
    dur = 0.9
    t = t_(dur)
    thud = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-t / 0.05) + 38) / SR) * np.exp(-t / 0.14)
    boom = lp(rng.normal(size=len(t)), 400) * np.exp(-t / 0.3)
    # glass: inharmonic high partials, struck, plus splintering ticks
    gl = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / dcy) for f, a, dcy in
             ((2310, 1, .09), (3170, .8, .07), (4420, .6, .05), (5830, .4, .04), (7090, .3, .03)))
    spl = np.zeros(len(t)); n = 60 if variant == 0 else 25
    for _ in range(n):
        st = abs(rng.normal(0, 0.06 if variant == 0 else 0.12)); i = int(st * SR)
        c = bp(rng.normal(size=200), 3000, 9000) * np.exp(-np.arange(200) / 25)
        spl[i:i + 200] += c[:len(spl) - i] * rng.uniform(0.3, 1)
    if variant == 1:   # a deeper, longer rumble: the dome shudders
        boom = lp(rng.normal(size=len(t)), 250) * np.exp(-t / 0.45)
    out = norm(thud, 1) + 0.8 * norm(boom, 1) + 0.45 * norm(gl, 1) * (0.7 if variant else 1) + 0.5 * norm(spl, 1)
    return norm(out, 0.9)

STEP = 19 / 59.185               # one cell step (SHIP_MOVE_FRAMES at 59.185 Hz)
HOVER_RMS = 0.04                 # the user's pick (hover D, 10-28): quieter and airier than C1


def hover():
    """a low soft rush: periodic air band-limited to 250..4000 Hz, tilted
    down (1/f^0.6) and low-passed at 1800 Hz, swelling gently (25%) once
    per step; whole cycles of everything per step."""
    n = int(round(STEP * SR)); t = np.arange(n) / SR
    X = np.fft.rfft(np.random.default_rng(41).normal(size=n)); f = np.fft.rfftfreq(n, 1 / SR)
    X[(f < 250) | (f > 4000)] = 0
    X[f > 0] /= (f[f > 0] / 1000) ** 0.6
    air = lp(norm(np.fft.irfft(X, n), 1), 1800)
    swell = 1 - 0.25 * 0.5 * (1 - np.cos(2 * np.pi * np.arange(n) / n))
    x = norm(air * swell, 0.6)
    x = (np.clip(x, -1, 1) * 32767).astype('<i2') / 32768    # as written, then levelled
    return x * HOVER_RMS / np.sqrt((x ** 2).mean())


def bolt():
    """the laser bolt: three partials of a pitch falling 1580 -> 180 Hz."""
    dur = 0.30; t = t_(dur)
    f = 1400 * np.exp(-t / 0.08) + 180
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = (np.sin(ph) + 0.5 * np.sin(1.5 * ph + 0.4) + 0.3 * np.sin(2.76 * ph)) * np.exp(-t / 0.11)
    return norm(x * np.clip(t / 0.002, 0, 1), 0.85)



# ---- the initials picker (10-30) ----
def _env(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))

def _pad(x, dur):
    out = np.zeros(int(dur * SR)); out[:min(len(x), len(out))] += x[:len(out)]; return out

def _at(buf, x, t):
    i = int(t * SR); n = min(len(x), len(buf) - i); buf[i:i + n] += x[:n]

def _partials(fs, amps, dur, taus):
    t = np.arange(int(dur * SR)) / SR
    return sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / tau) for f, a, tau in zip(fs, amps, taus))

def _click(dur, f0, q, tau, gain=1.0):
    n = int(dur * SR); x = rng.standard_normal(n) * _env(n, tau)
    return reson(x, f0, q) * gain

def picker_tick(variant):
    """0 a metal detent, 1 a wooden ratchet knock (picked), 2 a soft tok"""
    if variant == 0:
        x = _pad(_click(0.02, 3600, 6, 0.0015), .03) + 0.35 * _partials([3150, 5200], [1, .5], 0.03, [.006, .004])
        return norm(x, 0.30)
    if variant == 1:
        x = _click(0.025, 1900, 5, 0.002) + 0.6 * _click(0.025, 900, 4, 0.003)
        return norm(x, 0.30)
    x = _partials([1250, 2500], [1, .25], 0.03, [.008, .004]) * np.minimum(1, np.arange(int(.03 * SR)) / 20)
    return norm(x, 0.22)

def _strike(body_f, slap_f, ring_fs, ring_tau, esc_t, esc_f, heavy):
    out = np.zeros(int(0.22 * SR))
    _at(out, _click(0.04, body_f, 2.5, 0.006, 0.9 * heavy), 0.0)          # the key bottoms out
    slap = _click(0.03, slap_f, 3, 0.0018, 1.0) + _click(0.03, slap_f * 1.9, 4, 0.0012, 0.6)
    _at(out, slap, 0.018)                                                # the type bar hits
    _at(out, _partials(ring_fs, [.35, .2, .12], 0.18, [ring_tau, ring_tau * .7, ring_tau * .5]), 0.018)
    _at(out, _click(0.02, 160, 1.5, 0.008, 0.8 * heavy), 0.018)           # the platen thump
    _at(out, _click(0.02, esc_f, 6, 0.0012, 0.45), esc_t)                 # the carriage steps
    return norm(out, 0.80)

def picker_type(variant):
    """0 classic manual, 1 heavy office (picked), 2 light portable"""
    return [lambda: _strike(420, 2600, [1180, 2730, 4100], .03, .055, 3300, 1.0),
            lambda: _strike(300, 2100, [880, 2150, 3600], .045, .065, 2900, 1.5),
            lambda: _strike(560, 3300, [1500, 3400, 5100], .02, .045, 3900, 0.7)][variant]()

def picker_bell():
    x = _partials([2093, 5230, 3170], [1, .35, .2], 0.9, [.35, .12, .2])
    x[:40] *= np.linspace(0, 1, 40)
    return norm(x, 0.55)

def picker_backspace():
    out = np.zeros(int(0.15 * SR))
    _at(out, _click(0.04, 380, 2.5, 0.006, 0.8), 0)
    _at(out, _click(0.02, 2700, 5, 0.0015, 0.7), 0.03)   # the escapement pawl kicked back
    _at(out, _click(0.02, 2200, 5, 0.0015, 0.5), 0.045)
    return norm(out, 0.65)


def render_all():
    """{name: samples}: the approved effects, in the mockups' rng order."""
    global rng
    out = {}
    rng = np.random.default_rng(7)
    scuttle(0)                     # (the spider's move: rendered for the rng order)
    out["jump"] = jump(0)
    rng = np.random.default_rng(11)
    lava(0); airburst(0); dome_hit(0)
    lava(1)                        # (the spider's fire: rendered for the rng order)
    out["hit"] = airburst(1)
    out["crack"] = dome_hit(1)
    out["move"] = hover()
    out["fire"] = bolt()
    rng = np.random.default_rng(1030)
    picker_tick(0)                 # (the mockup's candidates: rendered for the rng order)
    out["tick"] = picker_tick(1)
    picker_tick(2)
    picker_type(0)
    picker_type(1)                 # (replaced by assets/sfx/type.wav, 10-31)
    picker_type(2)
    out["bell"] = picker_bell()
    out["backspace"] = picker_backspace()
    return out


def main():
    d = sys.argv[1]
    for name, x in render_all().items():
        write(f"{d}/{name}.wav", x)


if __name__ == "__main__":
    main()
