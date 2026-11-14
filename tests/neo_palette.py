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
DOME_COLS, DOME_ROWS = lay.d.DOME_COLS, lay.d.DOME_ROWS   # the size knob
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


# ---- the backdrop (dome-scenery Task 4) ----
# The play backdrop is the sky: RGB (120, 176, 228), packed exactly as
# generate_srom.neo_colour packs a colour. MAME shows it as SKY_RGB. On the
# title the backdrop is black. The boot-test checkers that count "lit"
# pixels must not count the sky as a drawn pixel: a pixel is lit only if it
# differs from the backdrop (see is_lit below).
SKY_RGB_WORD = 0x47be
SKY_RGB = neo_rgb(SKY_RGB_WORD)          # (117, 182, 233) on screen
BLACK_RGB = (0, 0, 0)


def is_lit(px, backdrop):
    """True if the snapshot pixel `px` is a drawn pixel (not the backdrop):
    a pixel whose RGB differs from `backdrop` at all. The old rule
    (max(channel) > 40) counted the sky's every pixel as lit; this one
    leaves the backdrop out."""
    return tuple(px[:3]) != tuple(backdrop)


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


def ground_palettes_rgb():
    """dome-scenery Task 5: the two ground banks' RGBs (ground_pal and
    ground_pal_noshadow), from the generated build/ground_map.h. The
    runtime writes one or the other depending on the dome's whole/gone
    state, so a checker that must tell the grass from a drawn sprite needs
    both."""
    txt = open(os.path.join(BUILD, "ground_map.h")).read()
    out = []
    for name in ("ground_pal", "ground_pal_noshadow"):
        m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name, txt, re.S)
        out.append(_bank_rgb([int(x, 16) for x in
                              re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]))
    return out


# ---- the mountains (dome-scenery Task 6) ----
# The mountain band is a second static picture: y MTN_Y..MTN_Y+47, the same
# width. Its non-transparent colours must not be mistaken for the dome or a
# sprite by the checkers that scan the dome box (the band's bottom rows
# overlap the dome box's top). src/mountains.c writes mtn_pal into bank 9.

_MTN_RGB = None


def mountain_palette_rgb():
    """the mountain bank's 16 RGBs, from the generated build/mountain_map.h;
    index 0 is transparent."""
    txt = open(os.path.join(BUILD, "mountain_map.h")).read()
    m = re.search(r"static const u16 mtn_pal\[16\] = \{(.*?)\};", txt, re.S)
    return _bank_rgb([int(x, 16) for x in
                      re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))])


def mountain_rgb_set():
    """every non-transparent colour of the mountain bank, as a set — the
    static mountain picture's possible pixels."""
    global _MTN_RGB
    if _MTN_RGB is None:
        _MTN_RGB = set(mountain_palette_rgb()[1:11])   # 11..15 unused (black)
    return _MTN_RGB


def is_mountain(px):
    """is a snapshot pixel one of the static mountain picture's colours?"""
    return tuple(px[:3]) in mountain_rgb_set()


# ---- the band of towns and forests (dome-scenery Task 17) ----
# The band is a third static picture: y BAND_Y..BAND_Y+31, right above the
# horizon. Its non-transparent colours must not be mistaken for the dome or a
# sprite by the checkers that scan the rows just above the dome box (the band
# reaches y 99; the dome box starts at y 104). src/band.c writes band_pal into
# bank 12.

_BAND_RGB = None


def band_palette_rgb():
    """the band bank's 16 RGBs, from the generated build/band_map.h;
    index 0 is transparent."""
    txt = open(os.path.join(BUILD, "band_map.h")).read()
    m = re.search(r"static const u16 band_pal\[16\] = \{(.*?)\};", txt, re.S)
    return _bank_rgb([int(x, 16) for x in
                      re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))])


def band_rgb_set():
    """every non-transparent colour of the band bank, as a set — the static
    band picture's possible pixels."""
    global _BAND_RGB
    if _BAND_RGB is None:
        _BAND_RGB = set(band_palette_rgb()[1:13])      # 13..15 unused (black)
    return _BAND_RGB


def is_band(px):
    """is a snapshot pixel one of the static band picture's colours?"""
    return tuple(px[:3]) in band_rgb_set()


_GRASS_RGB = None


def ground_ripple_palettes_rgb():
    """dome-scenery Task 19: every ripple bank's palette words from the
    generated build/ground_map.h, as [bank][whole/gone][rotation][16 RGB].
    The tiles use banks 44..54 (RIPPLE_PAL_BANK), not bank 8: bank 8 is only
    the whole/gone marker now."""
    txt = open(os.path.join(BUILD, "ground_map.h")).read()
    m = re.search(r"ground_ripple_pal\[[^=]*= \{(.*?)\};", txt, re.S)
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]
    out, i = [], 0
    while i < len(words):
        per = []
        for _g in (0, 1):
            rots = []
            for _r in range(3):
                rots.append(_bank_rgb(words[i:i + 16]))
                i += 16
            per.append(rots)
        out.append(per)
    return out


def ground_rgb_set():
    """every non-transparent colour of either ground bank and of every
    ripple bank/rotation/gone palette, as a set — the static grass picture's
    possible pixels. Task 19's tiles use the ripple banks, so is_grass must
    accept those colours too."""
    global _GRASS_RGB
    if _GRASS_RGB is None:
        words = set()
        for bank in ground_palettes_rgb():
            words.update(bank[1:15])     # 15 is unused (black): not grass
        for per in ground_ripple_palettes_rgb():
            for gone in per:
                for rot in gone:
                    words.update(rot[1:13])  # 13..15 unused (black)
        _GRASS_RGB = words
    return _GRASS_RGB


def is_grass(px):
    """is a snapshot pixel one of the static ground picture's colours?"""
    return tuple(px[:3]) in ground_rgb_set()


# ---- the console (dome-scenery Task 7) ----
# The panel is a third static picture: CON_COLS columns of the bottom of the
# screen (dome-scenery Task 8 lowered it: the wings start at y 176 and the
# strip at y 192, both down to y 223). src/console.c writes con_pal into
# bank 10. Its colours
# (dark near-blacks, greys and ambers) are not the grass's or the mountains',
# but a checker that scans the dome's box or the ground's band must be able
# to leave the panel out just as it leaves those two out.

_CON_RGB = None


def console_palette_rgb():
    """the console bank's 16 RGBs, from the generated build/console_map.h;
    index 0 is transparent."""
    txt = open(os.path.join(BUILD, "console_map.h")).read()
    m = re.search(r"static const u16 con_pal\[16\] = \{(.*?)\};", txt, re.S)
    return _bank_rgb([int(x, 16) for x in
                      re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))])


def console_rgb_set():
    """every non-transparent colour of the console bank, as a set — the
    static console picture's possible pixels."""
    global _CON_RGB
    if _CON_RGB is None:
        _CON_RGB = set(console_palette_rgb()[1:8])    # 8..15 unused (black)
    return _CON_RGB


def is_console(px):
    """is a snapshot pixel one of the static console picture's colours?"""
    return tuple(px[:3]) in console_rgb_set()


# the console's colours can coincide with the grass's (both dark scenery):
# a checker that subtracts the console from a box scan needs a predicate that
# is true for a console pixel AND not for a grass pixel, so the scans that
# only subtract the console (dome-lift, ships) still leave the grass out.
_CON_ONLY = None


def console_only_rgb_set():
    """the console bank's colours that no ground bank uses — the panel's
    own pixels, distinct from the grass's."""
    global _CON_ONLY
    if _CON_ONLY is None:
        _CON_ONLY = console_rgb_set() - ground_rgb_set()
    return _CON_ONLY


def is_console_only(px):
    """a console picture pixel that is not also a grass colour: safe to
    subtract where the grass must stay out too."""
    return tuple(px[:3]) in console_only_rgb_set()


# ---- the radar (dome-scenery Task 10: the Elite-style scanner) ----
# The generated build/radar_map.h holds the radar's two banks: radar_pal
# (bank 20: 1 the dim amber rim/roof, 2..4 the disc's fill/rings/bezel) with
# radar_pal_bright (the lock-on blink's entry 1), and radar_stick_pal
# (bank 21: index 1 the sticks'/headings' steady red-orange). The checkers
# use these helpers to decode the snapshot's colours and to tell a radar
# pixel (the sticks are red-orange) from a missile's.
RADAR_PAL_BANK = 20
RADAR_STICK_PAL_BANK = 21


def radar_pal_words():
    """radar_pal's 16 words (bank 20), from build/radar_map.h."""
    txt = open(os.path.join(BUILD, "radar_map.h")).read()
    m = re.search(r"static const u16 radar_pal\[16\] = \{(.*?)\};", txt, re.S)
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]


def radar_pal_bright_word():
    """the blink's bright word (radar_pal_bright) from build/radar_map.h."""
    txt = open(os.path.join(BUILD, "radar_map.h")).read()
    m = re.search(r"static const u16 radar_pal_bright = (0x[0-9a-fA-F]{4});",
                  txt)
    return int(m.group(1), 16)


def radar_stick_pal_words():
    """radar_stick_pal's 16 words (bank 21), from build/radar_map.h."""
    txt = open(os.path.join(BUILD, "radar_map.h")).read()
    m = re.search(r"static const u16 radar_stick_pal\[16\] = \{(.*?)\};",
                  txt, re.S)
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]


def radar_palette_rgb(bright=False):
    """the radar frame bank's 16 on-screen RGBs (index 0 transparent); with
    bright=True entry 1 is the lock-on blink's word instead of the dim one."""
    words = radar_pal_words()
    if bright:
        words = list(words)
        words[1] = radar_pal_bright_word()
    return _bank_rgb(words)


def radar_stick_palette_rgb():
    """the sticks'/headings' bank's 16 on-screen RGBs (index 0 transparent);
    entry 1 is the steady red-orange."""
    return _bank_rgb(radar_stick_pal_words())


def radar_rgb_set():
    """every drawn colour of the frame bank (entries 1..4, dim and bright):
    the picture's possible pixels."""
    dim = set(radar_palette_rgb()[1:5])
    bright = set(radar_palette_rgb(True)[1:5])
    return dim | bright


def radar_stick_rgb_set():
    """the sticks'/headings' drawn colours (entries 1..; the rest unused)."""
    return set(radar_stick_palette_rgb()[1:2])


def is_radar(px):
    """is a snapshot pixel one of the radar frame picture's colours?"""
    return tuple(px[:3]) in radar_rgb_set()


def is_radar_stick(px):
    """is a snapshot pixel one of the radar sticks'/headings' colours?"""
    return tuple(px[:3]) in radar_stick_rgb_set()


# ---- the fix palettes (dome-scenery Task 9: the HUD in amber) ----
# The generated build/fix_pal.h holds BOTH fix palettes: fix_pal[16] (the
# title's blue, the same words generate_srom.py always wrote) and
# fix_pal_amber[16] (the in-play HUD's amber: the same words except entries
# 1..5, the font's top-lit gradient 1..4, icons on 1, and the shadow 5).
# The title's rows use bank PAL_HUD 7 (fix_pal), the play rows bank
# PAL_HUD_PLAY 11 (fix_pal_amber); both are loaded once at boot.
FIX_PAL_H = os.path.join(BUILD, "fix_pal.h")


def _fix_pal_words(name):
    """a fix_pal.h array (`fix_pal` / `fix_pal_amber`) as its 16 words."""
    txt = open(FIX_PAL_H).read()
    m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name, txt, re.S)
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]


def fix_pal_words():
    """the title's blue fix palette, 16 words (entry 0 transparent)."""
    return _fix_pal_words("fix_pal")


def fix_pal_amber_words():
    """the in-play HUD's amber fix palette, 16 words (entry 0 transparent)."""
    return _fix_pal_words("fix_pal_amber")


def fix_pal_rgb(words=None):
    """a fix palette's 16 on-screen RGBs through MAME's DAC; index 0 is
    ALWAYS transparent (the game writes 0x8000 there)."""
    return _bank_rgb(fix_pal_words() if words is None else words)


def fix_pal_amber_rgb():
    """the amber bank's 16 on-screen RGBs (index 0 transparent)."""
    return _bank_rgb(fix_pal_amber_words())


def hud_play_lit_rgb_set():
    """the amber bank's drawn colours, entries 1..5 (the font's gradient
    and its shadow): what the in-play integrity/lives/score/GAME OVER
    pixels are, and what the blue's 1..5 must NOT be."""
    return set(fix_pal_amber_rgb()[1:6])


def title_lit_rgb_set():
    """the blue bank's drawn colours, entries 1..5: what the title's text
    pixels are."""
    return set(fix_pal_rgb()[1:6])


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


# ---- the props (dome-scenery Task 12: the trees and rocks) ----
# The props are one pool over the grass and the mountains (slots right after
# the mountains, under everything but those two). Their pictures can reach
# into the dome box's y span -- a prop's foot is on the grass (y GROUND_Y +
# ...), and a near tree's 5-tile column rises above DOME_Y -- so a checker
# that scans the dome box must be able to leave the props' own colours out,
# and the `broken` composite must paste them under the dome (their slots are
# lower than the dome's).
#
# The palette is build/props_map.h's prop_pal[i][0] (the lit one): bank
# PROP_PAL_BANK + i, entry 0 transparent, entries 1 and 13 the runtime's
# prop_shadow[0][y]. tests/check_props.py owns their proof; these helpers
# only let the older scene checkers tell a prop pixel from a dome one.

PROP_PAL_BANK = 22             # src/props.h
_PROP_RGB = None


def _prop_header():
    txt = open(os.path.join(BUILD, "props_map.h")).read()
    return txt


def prop_palette_words():
    """prop_pal[NPROPS][2][16]'s lit (index 0) banks, from the generated
    build/props_map.h, as one word list per prop."""
    txt = _prop_header()
    m = re.search(r"static const u16 prop_pal\[NPROPS\]\[2\]\[16\] = "
                  r"\{(.*?)\n\};", txt, re.S)
    out = []
    for line in m.group(1).splitlines():
        words = re.findall(r"0x[0-9a-fA-F]{4}", line)
        if not words:
            continue
        out.append([int(w, 16) for w in words[:16]])
    return out


def prop_palettes_rgb():
    """every prop's lit bank's 16 RGBs (index 0 transparent), in bank
    order: bank PROP_PAL_BANK + i is prop i's."""
    return [_bank_rgb(words) for words in prop_palette_words()]


def prop_shadow_words():
    """prop_shadow[0]'s 224 (entry1, entry13) pairs, from the generated
    build/props_map.h: the runtime writes one pair into a shown prop's bank
    (entries 1 and 13) when the foot's row changes, so these are colours a
    prop pixel can carry even though they are not in prop_pal[i][0]."""
    txt = _prop_header()
    m = re.search(r"static const u16 prop_shadow\[2\]\[224\]\[2\] = "
                  r"\{(.*?)\n\};", txt, re.S)
    pairs = [(int(a, 16), int(b, 16)) for a, b in
             re.findall(r"\{(0x[0-9a-fA-F]{4}),(0x[0-9a-fA-F]{4})\}", m.group(1))]
    return pairs[:224]


def prop_rgb_set():
    """every non-transparent colour a prop can show on screen, as a set: the
    lit banks' colours plus the runtime shadow entries (prop_shadow[0], which
    the runtime writes into entries 1 and 13 of a shown prop's bank)."""
    global _PROP_RGB
    if _PROP_RGB is None:
        _PROP_RGB = set()
        for bank in prop_palettes_rgb():
            _PROP_RGB.update(bank[1:])
        for a, b in prop_shadow_words():
            for w in (a, b):
                px = neo_rgb(w)
                if px != BLACK_RGB:
                    _PROP_RGB.add(px)
    return _PROP_RGB


def is_prop(px):
    """is a snapshot pixel one of a prop's own colours?"""
    return tuple(px[:3]) in prop_rgb_set()


def _prop_pool_slots(da, pool):
    """the model's drawn slots of one pool at `da`: pool 0 = the back pool
    (under the dome), 1 = the front pool (over the dome), None = both in
    drawing order (back first, then front)."""
    import props_model as pm
    back, front = pm.layout(da)
    if pool is None:
        return [s for s in back + front if s[0]]
    assert pool in (0, 1), pool
    return [s for s in (back if pool == 0 else front) if s[0]]


def prop_slot_boxes(da, pool=None):
    """the props' on-screen boxes at dome angle `da`, from Task 11/15's model
    (tests/props_model.py, written from the header and the art generator,
    never from the C): a list of (x0, y0, x1, y1, prop), one per drawn
    column -- x0 = scb4>>7, y0 = 496-(scb3>>7), x1 = x0 + hz+1,
    y1 = y0 + rows*16 (the column's box; a column is hz+1 px wide).
    `pool` picks the back (0) or front (1) pool; None gives both, back
    first (drawing order)."""
    import props_model as pm
    pics = pm.rp.pictures()
    out = []
    for slot in _prop_pool_slots(da, pool):
        _, i, lod, _c, scb2, scb3, scb4, _tile = slot
        _pic, _cols, rows, _ax, _ay = pics[(pm.KIND[i], pm.SHAPE[i], lod)]
        x0 = scb4 >> 7
        y0 = 496 - (scb3 >> 7)
        out.append((x0, y0, x0 + ((scb2 >> 8) & 0x0f) + 1,
                    y0 + rows * 16, i))
    return out


def props_picture(da, pool=None):
    """(RGB image, drawn mask) of the props at dome angle `da`: Task 11/15's
    model layout, each column drawn through the hardware's zoom tables (the
    decode tests/test_radar_render.py uses: ZOOM_X_COLS gives the art
    columns drawn, _ZOOM_Y[(vz << 8) | line] the SCB1 row and art row of each
    box line), far to near, in the model's lit palette with entries 1 and 13
    the runtime's shadow row for the prop's foot.

    `pool` picks the back pool (0, drawn under the dome) or the front pool
    (1, drawn over the dome and its overlays and under the ship); None gives
    both in drawing order (back first). A checker compositing the scene must
    use pool 0 before the dome and pool 1 after the overlays.

    The modules are imported here (not at the top) so a checker that never
    scans the props does not pay for decoding the BIOS's zoom table."""
    import props_model as pm
    import render_radar as rr
    pics = pm.rp.pictures()
    frame = np.zeros((224, 320, 3), np.uint8)
    drawn = np.zeros((224, 320), bool)
    for slot in _prop_pool_slots(da, pool):
        if not slot[0]:
            continue
        _, i, lod, _c, scb2, _scb3, _scb4, _tile = slot
        se = pm.SE[i][da]
        hz = (scb2 >> 8) & 0x0f
        v = scb2 & 0xff
        pic, cols, rows, ax, ay = pics[(pm.KIND[i], pm.SHAPE[i], lod)]
        left = pm.X[i][da] - int(round(ax * se / pm.LODS[lod]))
        top = pm.Y[i][da] - int(round(ay * se / pm.LODS[lod]))
        pal = list(prop_palette_words()[i])
        y = max(0, min(223, pm.Y[i][da]))
        pal[1], pal[13] = prop_shadow_words()[y]
        lut = np.array([neo_rgb(w) for w in pal], np.uint8)
        for line in range(rows * 16):       # the column's box lines
            b = rr._ZOOM_Y[(v << 8) | (line & 0xff)]
            row, artrow = b >> 4, b & 0x0f
            if row >= rows:                 # below the picture: blank
                continue
            sy = top + line
            if sy < 0 or sy >= 224:
                continue
            for col in range(cols):
                for j, artcol in enumerate(rr.ZOOM_X_COLS[hz]):
                    idx = int(pic[row * 16 + artrow][col * 16 + artcol])
                    if not idx:
                        continue
                    sx = left + col * (hz + 1) + j
                    if sx < 0 or sx >= 320:
                        continue
                    frame[sy, sx] = lut[idx]
                    drawn[sy, sx] = True
    return frame, drawn
