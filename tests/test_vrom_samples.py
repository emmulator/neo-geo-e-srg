"""The V ROM's ADPCM-A samples (R1 proof 4, K1 proof 3).

  test_vrom_samples.py   (host, pytest)

build/samples.inc (vromtool.py's ASM map) gives each sample's byte offset in
the V ROM; build/rom/esrg-v1.v1 is the packed 524288-byte V ROM. This test
re-encodes the source WAVs with ngdevkit's YM2610 ADPCM-A encoder
(adpcmtool.py's ym2610_adpcma, the same encoder vromtool uses) and requires
each sample's bytes in the V ROM to equal that encoding:

  - move/jump/fire/hit/crack: tools/synth_sfx.py's WAVs (18500 Hz; the
    Makefile's sox pass at the same rate is bit-identical, so the packed
    bytes are the encoding of the generator's own output); H5 moves move
    to the hovercraft's quieter hover D, jump/fire/hit/crack stay as they
    were (byte-identical);
  - pip: tools/render_sfx.py's WAV resampled to 18500 Hz
    (build/sfx/pip.wav);
  - tick/type/bell/backspace (K1): tools/synth_sfx.py's picker WAVs at
    18500 Hz, the map's new entries after the old six, so no old sample's
    offset (or bytes) moved; since 10-31 type is the CC0 recording
    assets/sfx/type.wav (CREDITS.md), not a synth_sfx output.

The test needs the cart build (make test builds it first); if the V ROM or
a source WAV is missing it returns without failing, like the resampled
WAV leg.
"""
import os
import re
import struct
import sys
import wave

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SAMPLES_INC = os.path.join(ROOT, "build", "samples.inc")
VROM = os.path.join(ROOT, "build", "rom", "esrg-v1.v1")
SFX = os.path.join(ROOT, "build", "sfx")
SYNTH = os.path.join(ROOT, "build", "sfx-synth")
VROM_SIZE = 524288
NAMES = ("move", "jump", "fire", "hit", "crack", "pip",
         "tick", "type", "bell", "backspace")

# the ngdevkit tools live beside the compiler (AGENTS.md)
BIN = os.path.expanduser(
    os.environ.get("NGDEVKIT_PREFIX",
                   "~/Development/github/dciabrin/ngdevkit/local") + "/bin")


def adpcm_a(path):
    """the ADPCM-A bytes of one mono WAV, as vromtool.py encodes it."""
    from adpcmtool import ym2610_adpcma

    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1, path
        assert w.getcomptype() == "NONE", path
        n = w.getnframes()
        data = w.readframes(n)
        width = w.getsampwidth()
    codec = ym2610_adpcma()
    if width == 1:
        adpcms = codec.encode_u8(struct.unpack("<%dB" % len(data), data))
    else:
        adpcms = codec.encode_s16(struct.unpack("<%dh" % (len(data) >> 1), data))
    return bytes((adpcms[i] << 4) | adpcms[i + 1]
                 for i in range(0, len(adpcms), 2))


def parse_start(text, name):
    lsb = int(re.search(r"\.equ\s+%s_START_LSB,\s*0x([0-9a-fA-F]+)"
                        % name.upper(), text).group(1), 16)
    msb = int(re.search(r"\.equ\s+%s_START_MSB,\s*0x([0-9a-fA-F]+)"
                        % name.upper(), text).group(1), 16)
    return (msb << 16) | (lsb << 8)


def source_for(name):
    """the WAV the V ROM was packed from: synth_sfx.py's output for the
    five spider effects, render_sfx.py's resampled pip."""
    if name == "pip":
        return os.path.join(SFX, "pip.wav")
    if name == "type":
        return os.path.join(ROOT, "assets", "sfx", "type.wav")
    path = os.path.join(SYNTH, name + ".wav")
    if os.path.exists(path):
        return path
    return os.path.join(SFX, name + ".wav")


def test_vrom_samples_equal_the_adpcm_encoding():
    if not os.path.exists(SAMPLES_INC) or not os.path.exists(VROM):
        return
    sys.path.insert(0, BIN)
    text = open(SAMPLES_INC).read()
    vrom = open(VROM, "rb").read()
    assert len(vrom) == VROM_SIZE, (len(vrom), VROM_SIZE)

    spans = []
    for name in NAMES:
        path = source_for(name)
        if not os.path.exists(path):
            return
        packed = adpcm_a(path)
        start = parse_start(text, name)
        assert vrom[start:start + len(packed)] == packed, (
            f"{name}: V ROM at 0x{start:x} ({len(packed)} bytes) is not the "
            f"ADPCM-A encoding of {os.path.relpath(path, ROOT)}")
        spans.append((start, start + len(packed), name))
        print(f"{name}: {len(packed)} bytes at 0x{start:x} equal the encoding "
              f"of {os.path.relpath(path, ROOT)}")

    spans.sort()
    for (s0, e0, n0), (s1, _e1, n1) in zip(spans, spans[1:]):
        assert e0 <= s1, f"{n0} (ends 0x{e0:x}) overlaps {n1} (starts 0x{s1:x})"


def test_type_is_the_credited_recording():
    """the typewriter strike is the CC0 recording CREDITS.md credits, at the
    encoder's rate, and synth_sfx no longer writes a type.wav"""
    path = os.path.join(ROOT, "assets", "sfx", "type.wav")
    with wave.open(path, "rb") as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 18500, 2)
    credits = open(os.path.join(ROOT, "CREDITS.md")).read()
    assert "assets/sfx/type.wav" in credits and "freesound.org/s/145534" in credits
    assert "CC0" in credits
    assert 'out["type"]' not in open(os.path.join(ROOT, "tools", "synth_sfx.py")).read()
