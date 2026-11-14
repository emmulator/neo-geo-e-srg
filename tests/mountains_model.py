"""The mountains' scroll, shared by the host test and the boot checker.

Dome-scenery Task 16: one turn of the dome (dome_angle 0..239) is the whole
960 px panorama, so the scroll is

    s = da * 960 / 240 = 4 * da               px, 0..956

with no rounding and no divide (960/240 is exactly 4). The screen shows
panorama columns s .. s + 319 (mod 960); as the angle grows the mountains
move LEFT.

The chain is MTN_SHOWN full-size 16-px columns (21 x 16 = 336 covers 320 at
any 16-px phase), in slots MTN_SPRITE .. MTN_SPRITE + MTN_SHOWN - 1. Its
driver X is `-(s & 15)` as a 9-bit value (`512 - (s & 15)` when that is not
0), and chain column k shows panorama column `((s >> 4) + k) mod 60` (a
conditional subtract).

This module is the model the boot checker (tests/check_mountains.py) uses;
it deliberately never calls into the C, so the boot test compares the cart
against an independent derivation.
"""

MTN_W = 960                 # build/mountain_map.h: MTN_W
MTN_COLS = 60               # build/mountain_map.h: MTN_COLS
MTN_ROWS = 3                # build/mountain_map.h: MTN_ROWS
MTN_Y = 52                  # build/mountain_map.h: MTN_Y
SCREEN_W = 320
MTN_SHOWN = 21               # src/mountains.h: MTN_SHOWN (21 x 16 >= 320)
MTN_COLS_MOD = MTN_COLS


def mtn_scroll(da):
    """s = 4 * da, the panorama's left column, 0..956."""
    return da * 4


def c_scroll(da):
    """the C's 16-bit formula: (u16)(4 * (u8)da) = 4 * da."""
    return 4 * da


def driver_x(s):
    """the 9-bit driver X: -(s & 15), i.e. 512 - (s & 15) when nonzero."""
    ph = s & 15
    return 0 if ph == 0 else 512 - ph


def driver_scb4(s):
    return driver_x(s) << 7


def column_panorama(s, k):
    """the panorama column chain column k shows: ((s >> 4) + k) mod 60."""
    p = (s >> 4) + k
    if p >= MTN_COLS_MOD:
        p -= MTN_COLS_MOD
    return p


def column_tiles(s, k, tile_base):
    """the 3 C ROM tile numbers of chain column k, top to bottom."""
    p = column_panorama(s, k)
    return [tile_base + p * MTN_ROWS + r for r in range(MTN_ROWS)]


def scb3_driver():
    """(496 - MTN_Y) << 7 | MTN_ROWS: y MTN_Y, 3 tiles tall."""
    return ((496 - MTN_Y) << 7) | MTN_ROWS


def scb3_follower():
    return 1 << 6


def panorama_column(s, x):
    """the panorama column screen pixel x shows on a frame scrolled to s."""
    return (s + x) % MTN_W
