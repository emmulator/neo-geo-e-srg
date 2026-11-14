"""The Neo Geo's on-screen RGB from a 15-bit palette word, and the
composited picture the `broken` boot-test compares a MAME snapshot against.

The game stores each colour as a 15-bit word (paltool.py's rgb24_to_packed15
= tools/render_missiles.py's neo()). MAME decodes the word to a 32-bit RGB
pixel through a resistor-network DAC (neogeo_v.cpp create_rgb_lookups /
resnet.cpp compute_resistor_weights, reproduced below) — this is the exact
pipeline the snapshot's colours go through, so an expected picture built with
neo_rgb() matches a MAME snapshot pixel for pixel.

The `broken` checker builds the expected picture from the REAL C ROM and the
REAL VRAM the cartridge wrote (scripts/broken_probe.lua reads every shown
sprite slot's SCB1 tile numbers):

  - slot_rgb_tiles(c1, c2, slot) decodes the slot's 16 SCB1 tile rows from
    the assembled cartridge C ROM (tile number N sits at byte N*64 of each
    plane file) and maps them through the palette bank the slot's attribute
    word picks (dome, ship or broken);
  - composite(scr, tiles, x, y) pastes a slot's non-transparent pixels at its
    on-screen position (SCB4>>7, 496-(SCB3>>7)).

Compositing order is the hardware's: higher sprite slot number draws on top,
so the checker pastes dome, then overlays, then ship (the ranges come from
the one slot map, build/slots.json — M5 Task 1). The front missiles and
explosions are NOT composited (their shrunk rendering is a separate,
already-tested path): the checker compares only the dome-box pixels OUTSIDE
their on-screen boxes.
"""
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_missiles as rm  # noqa: E402

BUILD = os.path.join(ROOT, "build")
ROM = os.path.join(BUILD, "rom")
import layout as lay  # noqa: E402
DOME_X, DOME_Y = lay.d.DOME_X, lay.d.DOME_Y    # src/dome.h
DOME_COLS, DOME_ROWS = 11, 8
# the one sprite slot map (src/slots.h -> build/slots.json)
_SLOTS = json.load(open(os.path.join(BUILD, "slots.json")))
DOME_SPRITE = _SLOTS["DOME_SPRITE"]
SHIP_SPRITE = _SLOTS["SHIP_SPRITE"]

# ---- MAME's Neo Geo 15-bit -> RGB pipeline (neogeo_v.cpp, resnet.cpp) ----

_RESISTANCES = [3900, 2200, 1000, 470, 220]


def _compute_resistor_weights(count, resistances, pulldown, pullup, scaler=-1.0):
    """port of compute_resistor_weights (src/emu/video/resnet.cpp): one
    network, the output range 0..255, autoscale unless scaler is given; the
    neogeo call uses the same scaler for every net."""
    r = [1.0 * x for x in resistances]
    w = []
    for n in range(count):
        r0 = 1.0 / 1e12 if pulldown == 0 else 1.0 / pulldown
        r1 = 1.0 / 1e12 if pullup == 0 else 1.0 / pullup
        for j in range(count):
            if r[j] != 0.0:
                if j == n:
                    r1 += 1.0 / r[j]
                else:
                    r0 += 1.0 / r[j]
        r0, r1 = 1.0 / r0, 1.0 / r1
        v = (255.0 - 0.0) * r0 / (r1 + r0) + 0.0
        w.append(min(max(v, 0.0), 255.0))
    max_out = sum(w)
    if scaler < 0.0:
        scaler = 255.0 / max_out
    return scaler, [x * scaler for x in w]


_SCALER, _WEIGHTS_NORMAL = _compute_resistor_weights(5, _RESISTANCES, 0, 0)
_, _WEIGHTS_DARK = _compute_resistor_weights(5, _RESISTANCES, 8200, 0, _SCALER)


def _lookup(i, dark):
    """combine_weights of the 5 DAC input bits -> the channel's 8-bit value."""
    wt = _WEIGHTS_DARK if dark else _WEIGHTS_NORMAL
    return int(sum(wt[k] * ((i >> k) & 1) for k in range(5)) + 0.5)


def neo_rgb(packed):
    """the RGB24 a Neo Geo pixel of the 15-bit colour `packed` shows in MAME
    (paletteram_w: 5-bit channels through the normal/dark resistor nets)."""
    dark = (packed >> 15) & 1
    r = ((packed >> 14) & 1) | ((packed >> 7) & 0x1e)
    g = ((packed >> 13) & 1) | ((packed >> 3) & 0x1e)
    b = ((packed >> 12) & 1) | ((packed << 1) & 0x1e)
    return _lookup(r, dark), _lookup(g, dark), _lookup(b, dark)


# ---- the palettes (the game's palette banks, from the built assets) ----

def _pal_words(path):
    """parse a .pal C initialiser list of 0xNNNN words."""
    txt = open(path).read()
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", txt)]


def _bank_rgb(words):
    """the palette bank's 16 on-screen RGBs: index 0 is ALWAYS transparent
    (the game writes 0x8000 there, whatever the art's key colour), the rest
    are the .pal's 15 colours through the DAC."""
    rgb = [neo_rgb(w) for w in words[:16]]
    rgb[0] = (0, 0, 0)
    return rgb


def dome_palette_rgb():
    return _bank_rgb(_pal_words(os.path.join(BUILD, "assets", "dome.pal")))


def ship_palette_rgb():
    return _bank_rgb(_pal_words(os.path.join(BUILD, "assets", "ship.pal")))


def broken_palette_rgb():
    txt = open(os.path.join(BUILD, "broken_map.h")).read()
    m = re.search(r"broken_pal\[16\] = \{(.*?)\};", txt, re.S)
    return _bank_rgb([int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))])


# ---- the C ROM tile decode (the assembled cartridge's plane files) ----

_c1 = _c2 = None


def _rom_files():
    """the assembled esrg-c1.c1/c2.c2 (cached); a tile N is at byte N*64."""
    global _c1, _c2
    if _c1 is None:
        _c1 = open(os.path.join(ROM, "esrg-c1.c1"), "rb").read()
        _c2 = open(os.path.join(ROM, "esrg-c2.c2"), "rb").read()
    return _c1, _c2


def decode_tile(tile):
    """the 16x16 index array of C ROM tile `tile` (the 4 8x8 sub-tiles at
    flat offsets (8,136,0,128), each 8 rows of the two plane bytes)."""
    c1, c2 = _rom_files()
    p1 = c1[tile * 64:(tile + 1) * 64]
    p2 = c2[tile * 64:(tile + 1) * 64]
    out = np.zeros((16, 16), np.uint8)
    for i, off in enumerate((8, 136, 0, 128)):
        sy, sx = off // 16, off % 16
        for y in range(8):
            b0 = p1[2 * (8 * i + y)]
            b1 = p1[2 * (8 * i + y) + 1]
            b2 = p2[2 * (8 * i + y)]
            b3 = p2[2 * (8 * i + y) + 1]
            for x in range(8):
                px = (b0 >> x & 1) | ((b1 >> x & 1) << 1) | \
                     ((b2 >> x & 1) << 2) | ((b3 >> x & 1) << 3)
                out[sy + y][sx + x] = px
    return out


def tile_rgb(tile, pal_rgb):
    """the tile's 16x16x3 screen RGB array (index 0 transparent)."""
    idx = decode_tile(tile)
    lut = np.array(pal_rgb, np.uint8)
    return lut[idx]                      # index 0 maps to pal[0] (transparent)


def paste(scr, rgb16, x, y, mask=None):
    """paste a 16x16 RGB tile at screen (x, y), skipping the tile's
    transparent pixels (index 0). `mask` is the 16x16 bool of non-transparent
    pixels (index != 0) when the caller has it — it is REQUIRED for palettes
    whose index-1 colour is black (the broken overlays' hole), because the
    RGB alone cannot tell a transparent index-0 pixel from a black index-1
    pixel. Without a mask the old RGB-based rule applies (skip black). `scr`
    is a (224, 320, 3) uint8 array, mutated in place."""
    h, w = scr.shape[:2]
    for yy in range(16):
        sy = y + yy
        if sy < 0 or sy >= h:
            continue
        for xx in range(16):
            sx = x + xx
            if sx < 0 or sx >= w:
                continue
            if mask is not None:
                if not mask[yy, xx]:
                    continue
            else:
                col = rgb16[yy, xx]
                if not (col[0] or col[1] or col[2]):
                    continue
            scr[sy, sx] = rgb16[yy, xx]
    return scr


def composite_slot(scr, slot, pal_rgb, rows=16):
    """paste a sprite slot at its on-screen position: `slot` is the dict the
    `broken` probe emits (slot, scb2, scb3, scb4, attr, tiles[16]); its box
    is (scb4>>7, 496-(scb3>>7)) with the SCB3 height `h`, and its SCB1 rows
    hold one 16x16 tile each (rows beyond the picture, if any, are
    transparent or stale — the hardware samples only `h` rows). Pastes rows
    0..h-1 at y + row*16, x (one stone column). A sticky follower (SCB3 bit
    6) is placed 16 px right of the caller's given x/y (the caller resolves
    the chain)."""
    x = slot["scb4"] >> 7
    y = 496 - (slot["scb3"] >> 7)
    h = slot["scb3"] & 0x3f
    if slot["scb3"] & (1 << 6):            # sticky: position supplied by caller
        x = slot["sticky_x"]
        y = slot["sticky_y"]
        h = slot["sticky_h"]
    if h > rows:
        h = rows
    for r in range(h):
        tile = slot["tiles"][r]
        paste(scr, tile_rgb(tile, pal_rgb), x, y + r * 16,
              mask=decode_tile(tile) != 0)
    return scr


def composite_run(scr, slots, pal_rgb, first, count):
    """paste a sticky chain's slots (first..first+count-1) at their on-screen
    positions: the first slot is the driver (SCB3 has the real Y/height and
    SCB4 the X); each following sticky slot sits 16 px right, inheriting the
    driver's Y and height. The probe dumps all of them (with their SCB1
    tiles) whether or not they are sticky."""
    driver = None
    for slot in slots:
        if slot["slot"] == first:
            driver = slot
            break
    if driver is None:
        return scr
    x0 = driver["scb4"] >> 7
    y0 = 496 - (driver["scb3"] >> 7)
    h0 = driver["scb3"] & 0x3f
    for k in range(count):
        s = first + k
        slot = next((sl for sl in slots if sl["slot"] == s), None)
        if slot is None:
            continue
        sx = x0 + k * 16
        sy = y0
        sh = h0
        # if this column is a real driver of its own (not sticky), use its
        # own box (the overlays are all independent, the dome/ship are chains)
        if not (slot["scb3"] & (1 << 6)):
            sx = slot["scb4"] >> 7
            sy = 496 - (slot["scb3"] >> 7)
            sh = slot["scb3"] & 0x3f
        for r in range(min(sh, 16)):
            paste(scr, tile_rgb(slot["tiles"][r], pal_rgb), sx, sy + r * 16)
    return scr
