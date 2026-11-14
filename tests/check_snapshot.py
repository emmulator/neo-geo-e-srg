#!/usr/bin/env python3
"""Assertions on a MAME snapshot of the cart.

  check_snapshot.py SNAP text    the title text is on screen (white pixels in the top rows)
  check_snapshot.py SNAP dome    the dome is on screen (coloured pixels in its box, none above it)
  check_snapshot.py SNAP ship      the ship is on screen, resting on the start cell
  check_snapshot.py SNAP ship-top  the ship is at the peak (stick held up)
  check_snapshot.py SNAP missile   a missile is on screen (red darts)
  check_snapshot.py SNAP dome-lift  the lifted dome: its lowest lit pixel at y 196..200,
                                  and nothing lit in y 200..223 under the dome's columns
                                  except the ship/missiles (HUD-layout Task 1 proof 2)

The dome box's bounds come from src/dome.h (tests/layout.py), the one
source of truth for the screen positions. The `dome-lift` check is the
plan's hard-coded-72 check: it states the lifted dome's concrete numbers
(pixel 198 at DOME_Y 72) so a regression to the old DOME_Y 88 fails it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402
import layout as lay  # noqa: E402

DOME_X = lay.d.DOME_X
DOME_Y = lay.d.DOME_Y
# the score's fix row (HUD-layout Task 2): row 28 -> screen y 208..215,
# and the widest centred number (8 chars, cols 16..23) -> x 128..191
HUD_SCORE_ROW = lay.d.hud("HUD_SCORE_ROW")
SCORE_SX0 = ((40 - 8) // 2) * 8
SCORE_SX1 = SCORE_SX0 + 8 * 8


def lit(px):
    return max(px[:3]) > 40


def check_text(im):
    w, h = im.size
    top = [im.getpixel((x, y)) for y in range(0, h // 4) for x in range(w)]
    white = sum(1 for p in top if min(p[:3]) > 200)
    return white >= 20, f"white pixels in the top quarter: {white}"


def check_dome(im):
    # the dome box: 176x128 px centred horizontally, its bottom 8 px above
    # the bottom of a 320x224 screen (MAME snapshots may be scaled: use
    # fractions). The star field draws above the box, so the no-lit-above
    # leg scans the band between the stars' bottom (DOME_Y - 4) and the
    # box's top: the stars are at y 8..DOME_Y-5, the box starts at DOME_Y.
    w, h = im.size
    x0, x1 = int(w * DOME_X / 320), int(w * (DOME_X + 176) / 320)
    y0, y1 = int(h * DOME_Y / 224), int(h * (DOME_Y + 128) / 224)
    inside = sum(1 for y in range(y0, y1, 2) for x in range(x0, x1, 2) if lit(im.getpixel((x, y))))
    above = sum(1 for y in range(int(h * (DOME_Y - 4) / 224), y0 - 4, 2) for x in range(x0, x1, 2)
                if lit(im.getpixel((x, y))))
    ok = inside > 500 and above < 20
    return ok, f"lit samples inside dome box: {inside}, above it: {above}"


def amber(px):
    r, g, b = px[:3]
    return r > 150 and g > b + 50               # the ship's hull and glow (missiles: red, g ~ b)


def red(px):
    r, g, b = px[:3]
    return r > 180 and r - g > 100 and abs(g - b) < 40   # a missile's body and edges


def ship_centre_y(im):
    """(count, centre y on a 224-line screen) of the ship's pixels in the dome's columns."""
    w, h = im.size
    x0, x1 = int(w * DOME_X / 320), int(w * (DOME_X + 176) / 320)
    pts = [y for y in range(h) for x in range(x0, x1)
           if amber(im.getpixel((x, y)))]
    return len(pts), (sum(pts) / len(pts) * 224 / h if pts else -1)


def check_ship(im):
    # the start cell's centre: the ship spans about y 119..136 (a lifted
    # dome: the ship moves with DOME_Y, 16 px up from the old 135..152)
    n, cy = ship_centre_y(im)
    return n >= 80 and 109 <= cy <= 149, f"ship pixels: {n} (whole ship ~100, half ~50: >= 80), centre y {cy:.0f} (start cell: 109..149)"


def check_ship_top(im):
    # holding up climbs to the peak in three moves: the ship spans about y 64..80
    n, cy = ship_centre_y(im)
    return n >= 50 and cy < 94, f"ship pixels: {n} (whole ship ~64, half ~32: >= 50), centre y {cy:.0f} (peak: < 94)"


def check_missile(im):
    w, h = im.size
    n = sum(1 for y in range(h) for x in range(w) if red(im.getpixel((x, y))))
    return n >= 20, f"missile pixels: {n}"


def check_dome_lift(im):
    """HUD-layout Task 1 proof 2: the dome's lowest lit pixel is at
    y 196..200 (a lifted dome: 198 with DOME_Y 72, the box's bottom at
    200), and no lit pixel sits in y 200..223 under the dome's columns
    (x 72..247) except the ship (amber), missiles (red), and — since
    HUD-layout Task 2 — the score's fix row 28 (screen y 208..215, the
    text's widest span cols 16..23 -> x 128..191), which is drawn centred
    under the dome on purpose. SNAPshots may be scaled: the bands are
    fractions of the 320x224 screen."""
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    cols = range(int(72 * sx), int(248 * sx))
    low_band = range(int(196 * sy), int(201 * sy))          # y 196..200
    below = range(int(200 * sy), int(224 * sy))             # y 200..223
    # the score's cells (the fix row HUD_SCORE_ROW at y 8*row-16 .. +7; a
    # 1..8-char centred number spans cols 16..23 at most -> x 128..191)
    score_x = range(int(SCORE_SX0 * sx), int(SCORE_SX1 * sx))
    score_y = range(int((8 * HUD_SCORE_ROW - 16) * sy),
                    int((8 * HUD_SCORE_ROW - 8) * sy))
    lowest = -1
    n_below = 0
    for y in low_band:
        for x in cols:
            if lit(im.getpixel((x, y))):
                lowest = y
    for y in below:
        for x in cols:
            p = im.getpixel((x, y))
            if lit(p) and not amber(p) and not red(p) \
               and not (x in score_x and y in score_y):
                n_below += 1
    # the lowest lit pixel must sit in y 196..200 (198: the dome's bottom
    # edge at DOME_Y + 126); nothing may be lit in y 200..223 under the
    # box except the ship, missiles and the score, which the filters above
    # excluded
    ok = int(196 * sy) <= lowest <= int(200 * sy) and n_below == 0
    return ok, (f"dome lowest lit pixel y {lowest} (need 196..200), "
                f"pixels below y 200 under the dome's columns: {n_below}")


def main():
    im = Image.open(sys.argv[1]).convert("RGB")
    checks = {"text": check_text, "dome": check_dome, "ship": check_ship, "ship-top": check_ship_top,
              "missile": check_missile, "dome-lift": check_dome_lift}
    ok, msg = checks[sys.argv[2]](im)
    print(("PASS " if ok else "FAIL ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
