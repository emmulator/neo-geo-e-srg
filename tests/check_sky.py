#!/usr/bin/env python3
"""Assertions for the dome-scenery Task 4 sky boot-test.

  check_sky.py SNAP PROBE

scripts/sky_probe.lua boots the normal cart, snapshots the title (before
Start) and a frame in play (after Start), in that order. This checker:

  1. reads the two snapshots in order from the MAME snapshot directory
     (the probe's TITLE / PLAY records state the frames), and
  2. proves the backdrop pixel with no sprite or fix tile over it (the
     top-left corner) is the SKY colour on the title and in play, the colour
     MAME's resistor-network DAC renders for the palette word the cart writes
     (RGB (120, 176, 228) packed exactly as generate_srom.py's neo_colour
     packs it, 0x47be -> (117, 182, 233) on screen). Attract Task A2 put the
     game's scene behind the title, so the title's backdrop is the sky too.

The corner is a blank fix tile (a space) on both, so the fix layer does not
draw there: the pixel is the backdrop. Both readings are printed.
"""
import os
import sys

from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import neo_palette as npal  # noqa: E402  (MAME's 15-bit -> RGB pipeline)

SKY = (120, 176, 228)                # the task's RGB
SKY_WORD = 0x47be                    # generate_srom.neo_colour((120, 176, 228))
SKY_RGB = npal.neo_rgb(SKY_WORD)     # what MAME shows: (117, 182, 233)


def parse(fname):
    """{'TITLE': (n, fc), 'PLAY': (n, fc)} from the probe's records."""
    out = {}
    with open(fname) as fh:
        for line in fh:
            p = line.split()
            if len(p) >= 3 and p[0] in ("TITLE", "PLAY"):
                out[p[0]] = (int(p[1]), int(p[2]))
    return out


def snaps_snap(snap_png):
    """the MAME snapshot directory (its machine subdir) in order."""
    base = os.path.dirname(os.path.abspath(snap_png))
    for root in (os.path.join(base, "snap"), base):
        if not os.path.isdir(root):
            continue
        pngs = sorted(os.path.join(r, fn) for r, _, fs in os.walk(root)
                      for fn in fs if fn.endswith(".png"))
        if pngs:
            return pngs
    return [snap_png]


def corner(im):
    """the top-left corner pixel (a blank fix tile, so the backdrop shows)."""
    return tuple(im.convert("RGB").getpixel((1, 1)))


def main():
    snap_png, probe = sys.argv[1], sys.argv[2]
    recs = parse(probe)
    pngs = snaps_snap(snap_png)
    failures = []

    if recs.get("TITLE") is None:
        failures.append("the probe never snapshotted the title")
    if recs.get("PLAY") is None:
        failures.append("the probe never snapshotted a game frame")
    if len(pngs) < 2:
        failures.append(f"only {len(pngs)} snapshot(s); need the title and a "
                        "game frame")
    if failures:
        print("FAIL sky:")
        for f_ in failures:
            print("  - " + f_)
        return 1

    title_rgb = corner(Image.open(pngs[0]))
    play_rgb = corner(Image.open(pngs[1]))
    print(f"title backdrop pixel (1,1): {title_rgb}; "
          f"play backdrop pixel (1,1): {play_rgb}")

    if title_rgb != SKY_RGB:
        failures.append(f"title backdrop pixel is {title_rgb}, want the sky "
                        f"{SKY_RGB} (MAME's rendering of 0x{SKY_WORD:04x} = "
                        f"RGB {SKY})")
    if play_rgb != SKY_RGB:
        failures.append(f"play backdrop pixel is {play_rgb}, want the sky "
                        f"{SKY_RGB} (MAME's rendering of 0x{SKY_WORD:04x} = "
                        f"RGB {SKY})")

    if failures:
        print("FAIL sky:")
        for f_ in failures:
            print("  - " + f_)
        return 1
    print(f"PASS sky: title backdrop sky {title_rgb}, play backdrop sky "
          f"{play_rgb} == MAME rendering of 0x{SKY_WORD:04x} (RGB {SKY})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
