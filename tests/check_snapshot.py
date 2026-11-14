#!/usr/bin/env python3
"""Assertions on a MAME snapshot of the cart.

  check_snapshot.py SNAP text    the title text is on screen (the title palette's
                                 amber 1..4 / gold 6..9 fill pixels in the top rows;
                                 attract Task A1 makes the text gold, outlined)
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
import neo_palette as npal  # noqa: E402  (the play backdrop: the sky)

DOME_X = lay.d.DOME_X
DOME_Y = lay.d.DOME_Y
DOME_W = lay.d.DOME_W
DOME_H = lay.d.DOME_H
# the score's fix row (HUD-layout Task 2; dome-scenery Task 8 moved the HUD
# down onto the console's bottom line): row 28 -> screen y 208..215, and the
# widest centred number (8 chars, cols 16..23) -> x 128..191
HUD_SCORE_ROW = lay.d.hud("HUD_SCORE_ROW")
SCORE_SX0 = ((40 - 8) // 2) * 8
SCORE_SX1 = SCORE_SX0 + 8 * 8


def lit(px):
    """a drawn pixel: dome-scenery Task 4's play backdrop is the sky
    (117,182,233), so a pixel is lit only if it is not the sky. (The old
    max-channel > 40 rule counted every sky pixel.) Dome-scenery Task 5's
    ground adds a second backdrop-like picture below the horizon, so the
    dome's box scans (which start at DOME_Y 104, over the grass) must also
    leave the grass out: see dome_lit below."""
    return npal.is_lit(px, npal.SKY_RGB)


def is_grass(px):
    """dome-scenery Task 5: a pixel of the static ground picture (either
    palette), from the generated build/ground_map.h (neo_palette)."""
    return npal.is_grass(px)


def is_mountain(px):
    """dome-scenery Task 6: a pixel of the static mountain picture, from the
    generated build/mountain_map.h (neo_palette)."""
    return npal.is_mountain(px)


def is_console(px):
    """dome-scenery Task 7: a pixel of the static console picture, from the
    generated build/console_map.h (neo_palette)."""
    return npal.is_console_only(px)


def is_prop(px):
    """dome-scenery Task 12: a pixel of a prop's own palette, from the
    generated build/props_map.h (neo_palette)."""
    return npal.is_prop(px)


def is_band(px):
    """dome-scenery Task 17: a pixel of the towns-and-forests band, from the
    generated build/band_map.h (neo_palette)."""
    return npal.is_band(px)


def dome_lit(px):
    """a lit pixel of the DOME (or a sprite over it): not the sky, not the
    grass, not the mountains, not the band, not the console, not a prop. The
    ground spans y GROUND_Y..223 across the whole width, so the dome box's
    lower rows sit over it; the mountain band's bottom rows sit over the dome
    box's top; the towns-and-forests band (dome-scenery Task 17) reaches y 99,
    just above the box, and its rows are scanned by the "above the box"
    check; the console (dome-scenery Tasks 7 and 8) covers y 176..223 (the
    wings) and y 192..223 (the strip) across the whole width, over the dome
    box's lower half and the ships; and the props (dome-scenery Task 12)
    stand on the grass with their tall columns reaching above DOME_Y, so
    their own colours must be left out of the box scan too. Only a pixel
    that is none of the static scenery is the dome's (or the
    ship's/missiles', which the box checks tolerate and count)."""
    return lit(px) and not is_grass(px) and not is_mountain(px) \
        and not is_band(px) and not is_console(px) and not is_prop(px)


def check_text(im):
    # attract Task A1: the title's fill is the amber 1..4 gradient and the
    # logo's gold 6..9 (no more white), the outline black. Count the fill
    # pixels in the top quarter (the logo on rows 2..5 and the level row 7).
    pal = npal.fix_pal_rgb()
    fill = set(pal[1:5]) | set(pal[6:10])
    w, h = im.size
    n = sum(1 for y in range(0, h // 4) for x in range(w)
            if tuple(im.getpixel((x, y))[:3]) in fill)
    return n >= 20, f"title fill (amber/gold) pixels in the top quarter: {n}"


def check_dome(im):
    # the dome box: 128x96 px centred horizontally, its bottom 8 px above
    # the bottom of a 320x224 screen (MAME snapshots may be scaled: use
    # fractions). Above the box is only the sky backdrop (dome-scenery
    # Task 4 retired the star field), so the old "nothing lit above the
    # box" band (DOME_Y - 4 to the box's top) is empty by construction at
    # today's DOME_Y 104: the stars' old band bottom and the box's top are
    # the same row.
    w, h = im.size
    x0, x1 = int(w * DOME_X / 320), int(w * (DOME_X + DOME_W) / 320)
    y0, y1 = int(h * DOME_Y / 224), int(h * (DOME_Y + DOME_H) / 224)
    inside = sum(1 for y in range(y0, y1, 2) for x in range(x0, x1, 2) if dome_lit(im.getpixel((x, y))))
    # (review of Task 4: the old DOME_Y - 4 .. y0 - 4 band became empty at
    # DOME_Y 104, so it scans the 8 rows right above the box instead)
    above = sum(1 for y in range(int(h * (DOME_Y - 8) / 224), y0, 2) for x in range(x0, x1, 2)
                if dome_lit(im.getpixel((x, y))))
    ok = inside > 500 and above < 20
    return ok, f"lit samples inside dome box: {inside}, above it: {above}"


_SHIP_RGB = None


def ship_rgb_set():
    """the hovercraft's palette, from the generated assets/ship.pal
    (the one bank the ship's tiles draw through, src/ship_gfx.h's PAL_SHIP)."""
    global _SHIP_RGB
    if _SHIP_RGB is None:
        _SHIP_RGB = set(npal.ship_palette_rgb()[1:])
    return _SHIP_RGB


def is_ship(px):
    """a pixel of the ship's own palette. The console shares one of its
    dark colours ((8,8,8)), so a box scan over the panel must leave the
    console's own pixels out: they are static scenery, not the ship."""
    return tuple(px[:3]) in ship_rgb_set() and not npal.is_console_only(px)


def red(px):
    r, g, b = px[:3]
    return r > 180 and r - g > 100 and abs(g - b) < 40   # a missile's body and edges


def ship_centre_y(im):
    """(count, centre y on a 224-line screen) of the ship's pixels in the
    dome's columns. The scan is the DOME BOX's y span only (DOME_Y ..
    DOME_Y+DOME_H-1): the ship is drawn on the dome, so it is always inside
    that span, while the in-play HUD's score now sits on fix row 28
    (screen y 208..215), BELOW the box's bottom (199), and since
    dome-scenery Task 9 the score is amber — the same colour family as the
    ship — so a whole-screen scan would count its lit pixels as the ship's
    (Task 9 caught ship-top at 55 pixels instead of ~36). Excluding the
    HUD by position (not by colour: the ship and the amber HUD share two
    colours) restores the old counts."""
    w, h = im.size
    sx, sy = w / 320.0, h / 224.0
    x0, x1 = int(w * DOME_X / 320), int(w * (DOME_X + DOME_W) / 320)
    y0, y1 = int(h * DOME_Y / 224), int(h * (DOME_Y + DOME_H) / 224)
    pts = [y for y in range(y0, y1) for x in range(x0, x1)
           if is_ship(im.getpixel((x, y)))]
    return len(pts), (sum(pts) / len(pts) * 224 / h if pts else -1)


def check_ship(im):
    # the start cell 27's projected centre is at DOME_Y + 47.6 = 151.6 (a
    # 128x96 box at (96, 104); the full-dome cell was DOME_Y + 56.3 = 128.3
    # with DOME_Y 72, hence the old 109..149 window of +-20). Dome-scenery
    # Task 2 keeps that +-20 and moves it to the new box: 131..171. The
    # 8-heading hovercraft's up-right REST picture (heading 1, H4) measures
    # 197 pixels of its own palette at the start cell; the bound stays
    # >= 175 (about 89% of the new picture, stricter than the old 75% of the
    # one-heading art's 233).
    n, cy = ship_centre_y(im)
    return n >= 175 and 131 <= cy <= 171, f"ship pixels: {n} (measured 197 at rest: >= 175), centre y {cy:.0f} (start cell: 131..171)"


def check_ship_top(im):
    # holding up climbs to the peak, where the craft faces up (heading 2:
    # H4). The top cell 0's projected centre is at DOME_Y + 12.2 = 116.2
    # (the full-dome cell 0 was DOME_Y + 6.6 = 78.6 with DOME_Y 72; the old
    # bound was < 94, 15.4 px above the centre). The same 15.4 px above the
    # centre gives < 131. The up-facing peak snapshot measures 106 pixels of
    # its own palette (the one-heading art's up-right picture measured 157),
    # so the bound is >= 80 (about 75% of the new picture).
    n, cy = ship_centre_y(im)
    return n >= 80 and cy < 131, f"ship pixels: {n} (measured 106 at the peak: >= 80), centre y {cy:.0f} (peak: < 131)"


def check_missile(im):
    w, h = im.size
    n = sum(1 for y in range(h) for x in range(w) if red(im.getpixel((x, y))))
    return n >= 20, f"missile pixels: {n}"


def check_dome_lift(im):
    """HUD-layout Task 1 proof 2: the dome's lowest lit pixel is at
    y 196..200 (a lifted dome: 198 with DOME_Y 72, the box's bottom at
    200), and no lit pixel sits in y 200..223 under the dome's columns
    (x 72..247) except the ship (its own palette), missiles (red), and — since
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
            if dome_lit(im.getpixel((x, y))):
                lowest = y
    for y in below:
        for x in cols:
            p = im.getpixel((x, y))
            if dome_lit(p) and not is_ship(p) and not red(p) \
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
