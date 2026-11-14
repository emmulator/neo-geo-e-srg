"""The towns-and-forests band's scroll, shared by the host test and the boot
checker (dome-scenery Task 17).

One turn of the dome (dome_angle 0..239) is the whole 768 px panorama, so
the scroll is

    s = round(da * 768 / 240) = (16 * da + 2) / 5     px, 0..765

768/240 = 3.2 never lands exactly on a half step, so the C's integer
division equals Python's round() for all 240 angles. The screen shows
panorama columns s .. s + 319 (mod 768); as the angle grows the band moves
LEFT.

The chain is BAND_SHOWN full-size 16-px columns (21 x 16 = 336 covers 320 at
any 16-px phase), in slots BAND_SPRITE .. BAND_SPRITE + BAND_SHOWN - 1. Its
driver X is `-(s & 15)` as a 9-bit value (`512 - (s & 15)` when that is not
0), and chain column k shows panorama column `((s >> 4) + k) mod 48` (a
conditional subtract).

This module is the model the boot checker (tests/check_band.py) uses; it
deliberately never calls into the C, so the boot test compares the cart
against an independent derivation.
"""

BAND_W = 768                # build/band_map.h: BAND_W
BAND_COLS = 48              # build/band_map.h: BAND_COLS
BAND_ROWS = 2               # build/band_map.h: BAND_ROWS
BAND_Y = 68                 # build/band_map.h: BAND_Y
SCREEN_W = 320
BAND_SHOWN = 21             # src/band.h: BAND_SHOWN (21 x 16 >= 320)
BAND_COLS_MOD = BAND_COLS


def band_scroll(da):
    """s = round(da * 768 / 240), the panorama's left pixel, 0..765."""
    return int(round(da * BAND_W / 240.0))


def c_scroll(da):
    """the C's 16-bit formula: (u16)((16 * (u8)da + 2) / 5)."""
    return (16 * da + 2) // 5


def driver_x(s):
    """the 9-bit driver X: -(s & 15), i.e. 512 - (s & 15) when nonzero."""
    ph = s & 15
    return 0 if ph == 0 else 512 - ph


def driver_scb4(s):
    return driver_x(s) << 7


def column_panorama(s, k):
    """the panorama column chain column k shows: ((s >> 4) + k) mod 48."""
    p = (s >> 4) + k
    if p >= BAND_COLS_MOD:
        p -= BAND_COLS_MOD
    return p


def column_tiles(s, k, tile_base):
    """the 2 C ROM tile numbers of chain column k, top to bottom."""
    p = column_panorama(s, k)
    return [tile_base + p * BAND_ROWS + r for r in range(BAND_ROWS)]


def scb3_driver():
    """(496 - BAND_Y) << 7 | BAND_ROWS: y BAND_Y, 2 tiles tall."""
    return ((496 - BAND_Y) << 7) | BAND_ROWS


def scb3_follower():
    return 1 << 6


def panorama_column(s, x):
    """the panorama column screen pixel x shows on a frame scrolled to s."""
    return (s + x) % BAND_W
