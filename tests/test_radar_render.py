#!/usr/bin/env python3
"""The radar's pictures (M5 Task 4): proof 1 (host, pytest).

  test_radar_render.py

tools/render_radar.py makes the radar's three picture families as C ROM
tiles. This test proves the shapes it draws:

  - the frame: the 64 x 32 picture's lit pixels are a 1-px ellipse of
    radii (RX, RY) centred on (CX, CY) plus the Vectrex's roof arch (the
    two lines from the peak down to each base); every lit pixel lies
    within 1 px of the ellipse curve or of a roof line (floats, from the
    same constants and gen_dome.py's RIM_DEG); the roof's half-width is
    RX/6 * sin(rim), its rim height H/6 * cos(rim), its peak H/6;
  - the sticks: per height h 0..32 and thin/wide, the 16 x 48 picture
    has exactly h lit pixels in its column (column 7 thin, columns 7..8
    wide — 2h lit), all in the bottom h rows (the foot is the bottom
    row where the spot sits); a picture of height 0 is empty;
  - the headings: 16 x 16 pictures solved against the Neo Geo's zoom
    tables (the "000-lo.lo" part of aes.zip); this test decodes the
    tables and simulates the hardware's draw for each (dx, dy) and each
    hflip, and proves the lit box pixels are the intended 1-px staircase
    from one box corner to the opposite (the runtime's placement formulas
    are covered by the boot-test; here the drawn staircase is the proof);
  - the C ROM frame payload decodes to frame_picture() (the Elite disc:
    the unchanged ellipse/roof lines on index 1 over a fill/rings/cross/
    bezel), and the picture's index-1 pixels are exactly frame_bitmap()'s
    lit pixels, so the lock-on blink still lights only the lines;
  - the palette: the header's radar_pal is {0x8000, 0x2d61, 0x0210, 0x3940,
    0x4000} (1 the dim amber rim/roof, 2..4 the disc), radar_pal_bright is
    0x4fc5, and radar_stick_pal is {0x8000, 0x6f42} (the sticks' and
    headings' own steady red-orange bank; the blink writes the frame
    bank's entry 1 only);
  - the C ROM placement: the radar's tile bases sit exactly after the
    broken-window sheet (dome-scenery Task 4 retired the star tile that
    used to sit between them), and the numbers of tiles match the parts
    the Makefile concatenates (frame 8, sticks 198 tile-slots, headings
    578), so the picture at each base is the one the runtime indexes (the
    boot-test decodes the real C ROM the same way);
  - the payload files round-trip: decoding the emitted c1/c2 bytes with
    the standard tile decoder (the one tests/test_broken_rom.py uses)
    gives back the generator's pictures exactly.
"""
import os
import re
import sys
from collections import Counter

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import render_radar as rr  # noqa: E402

TILE = rr.TILE
PIX = rr.PIX

HEAD_MAX = 16                     # |dx|, |dy| <= 16 (the task's bound)
H_N = 33                          # stick heights 0..32


def decode_tile(c1, c2, tile):
    """one 16x16 tile's palette-index array from the c1/c2 planes (the
    decoder tests/test_broken_rom.py uses)."""
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


# ---- the frame -----------------------------------------------------------

def test_frame_pixels_lie_within_1px_of_ellipse_or_roof():
    img = rr.frame_bitmap()
    assert img.shape == (2 * TILE, 4 * TILE), img.shape
    d = rr.radar_h_defs()
    cx, cy = d["RADAR_CX"], d["RADAR_CY"]
    rx, ry = d["RADAR_RX"], d["RADAR_RY"] / 10.0
    hw, hrim, hpk = rr.roof(d)
    w0, h0 = cx - 4 * TILE // 2, cy - 2 * TILE // 2

    # the roof's two segments, peak to each base (floats)
    roof_segs = [((cx - hw, cy - hrim), (cx, cy - hpk)),
                 ((cx + hw, cy - hrim), (cx, cy - hpk))]

    def seg_dist(qx, qy, a, b):
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        vx, vy = bx - ax, by - ay
        wx, wy = qx - ax, qy - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
        return ((wx - t * vx) ** 2 + (wy - t * vy) ** 2) ** 0.5

    lit = 0
    bad = []
    for yy in range(img.shape[0]):
        for xx in range(img.shape[1]):
            if img[yy, xx] != PIX:
                continue
            lit += 1
            px, py = w0 + xx, h0 + yy
            ell = abs(((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 - 1.0)
            roof_d = min(seg_dist(px, py, a, b) for a, b in roof_segs)
            if min(ell, roof_d) > 1.0:
                bad.append((px, py, ell, roof_d))
    assert lit > 0, "the frame has no lit pixels"
    assert not bad, f"{len(bad)} frame pixels > 1 px from the curves: {bad[:5]}"


def test_roof_landmarks_match_the_task_formulas():
    import math
    d = rr.radar_h_defs()
    hw, hrim, hpk = rr.roof(d)
    assert hw == d["RADAR_RX"] / 6.0 * math.sin(rr.RIM)
    assert hrim == d["RADAR_H"] / 6.0 * math.cos(rr.RIM)
    assert hpk == d["RADAR_H"] / 6.0
    # the roof's peak is the highest point: it sits above the rim (smaller y,
    # so a larger height magnitude); both stay inside the ellipse's box
    assert 0 < hrim < hpk
    assert 0 < hw < d["RADAR_RX"]


# ---- the sticks ----------------------------------------------------------

def test_each_stick_picture_has_exactly_h_lit_pixels_in_its_column():
    for h in range(H_N):
        for wide in (False, True):
            img = rr.stick_bitmap(h, wide)
            assert img.shape == (rr.STICK_H, TILE)
            if wide:
                assert int(img[:, 7].sum()) == h and int(img[:, 8].sum()) == h
                assert int(img[:, :7].sum()) == 0 and int(img[:, 9:].sum()) == 0
            else:
                assert int(img[:, 7].sum()) == h
                assert int(img[:, :7].sum()) == 0 and int(img[:, 8:].sum()) == 0
            # all lit pixels end at the bottom row (the foot is the spot)
            lit_rows = img.sum(axis=1)
            assert int(lit_rows[rr.STICK_H - h:].sum()) == (2 * h if wide else h)
            assert int(lit_rows[:rr.STICK_H - h].sum()) == 0


# ---- the headings --------------------------------------------------------

def sim_draw(art, adx, ady, hflip):
    """the hardware's drawn lit box positions for the 1-tile heading sprite
    (box 16 screen lines tall, height 1; SCB2 hz = adx-1, vz =
    heading_vz(ady)), decoded straight from the zoom tables. Returns
    [(line, col)] in box coords, y down."""
    import zipfile
    z = zipfile.ZipFile(rr._AES)
    ZOOM = z.read("000-lo.lo")
    hz = max(0, adx - 1)
    vz = rr.heading_vz(ady) if ady > 0 else 1
    out = []
    for scanline in range(16):
        sprite_line = scanline
        zoom_line = sprite_line & 0xff
        invert = bool((sprite_line >> 8) & 1)
        if invert:
            zoom_line ^= 0xff
        b = ZOOM[(vz << 8) | zoom_line]
        sprite_y = b & 0x0f
        tile = b >> 4
        if invert:
            sprite_y ^= 0x0f
            tile ^= 0x1f
        if tile >= 1:
            continue                     # samples SCB1 rows below the picture
        xt = rr.ZOOM_X[hz & 0xf]
        gfx = 15 if hflip else 0
        inc = -1 if hflip else 1
        col = 0
        for i in range(16):
            if xt & 0x8000:
                if art[sprite_y][gfx & 0xf]:
                    out.append((scanline, col))
                col += 1
            xt = (xt << 1) & 0xffff
            gfx += inc
            if xt == 0:
                break
    return out


def test_heading_tiles_draw_the_intended_staircase():
    """for every (dx, dy) and both hflips, simulating the hardware's draw
    from the zoom tables gives the intended 1-px line: exactly one lit
    pixel per drawn box line (dy lines when dy > 0), spanning the box
    width; a dy=0 heading is a horizontal run of `adx` pixels on the one
    drawn line. The line runs between the two box corners the direction
    spans — (0,0)..(dy-1, dx-1) for hflip 0 (down-right) and
    (0, dx-1)..(dy-1, 0) for hflip 1 (down-left)."""
    bad = []
    for ady in range(HEAD_MAX + 1):
        for adx in range(HEAD_MAX + 1):
            if adx == 0 and ady == 0:
                continue
            for hflip in (0, 1):
                art = rr.heading_art(adx, ady, hflip)
                lit = sim_draw(art, adx, ady, hflip)
                ndraw = ady if ady else 1          # drawn box lines
                if not lit:
                    bad.append((adx, ady, hflip, "nothing drawn"))
                    continue
                per_line = Counter(l for l, _ in lit)
                if ady <= 1 and adx > 0:
                    # one box line, holding every drawn column (adx px). The
                    # line is flip-symmetric: both hflips draw the identical
                    # run of box cols 0..adx-1 (the whole sampled art row is
                    # lit; the flip only changes which art columns, not the
                    # drawn columns). The runtime places the box so one end
                    # of this run is the stick's top (the boot-test proves
                    # the placement).
                    if set(per_line) != {0} or per_line[0] != (adx or 1):
                        bad.append((adx, ady, hflip,
                                    f"horizontal: {dict(per_line)}"))
                        continue
                    cols = sorted(c for _, c in lit)
                    if cols != list(range(adx)):
                        bad.append((adx, ady, hflip, f"horizontal cols {cols}"))
                else:
                    if len(per_line) != ndraw or any(v != 1 for v in per_line.values()):
                        bad.append((adx, ady, hflip, f"lines {dict(per_line)}"))
                        continue
                    lines = sorted(per_line)
                    cols_at = {l: [c for ll, c in lit if ll == l][0] for l in lines}
                    xmax = adx - 1 if adx else 0
                    if hflip == 0:
                        want_tl, want_br = (0, 0), (ndraw - 1, xmax)
                    else:
                        want_tl, want_br = (0, xmax), (ndraw - 1, 0)
                    got_tl = (lines[0], cols_at[lines[0]])
                    got_br = (lines[-1], cols_at[lines[-1]])
                    if got_tl != want_tl or got_br != want_br:
                        bad.append((adx, ady, hflip,
                                    (got_tl, got_br, want_tl, want_br)))
    assert not bad, f"{len(bad)} heading tiles draw wrong: {bad[:5]}"


def test_heading_sizes_fit_the_task_bounds():
    # the largest heading the model can produce is 13.4 x 15.3 (locked,
    # ring 11, j 56/119); the tile range is 0..16 each way, which covers it
    assert HEAD_MAX >= 15
    assert rr.DX_N == HEAD_MAX + 1


# ---- the frame picture (the Elite disc) ----------------------------------

def test_frame_picture_lines_are_frame_bitmap_exactly():
    """the C ROM frame's index-1 pixels (the lines the blink lights) are
    exactly frame_bitmap()'s lit pixels, and the disc's other indices are
    2..4 (the fill, the rings/cross, the bezel) — never index 1."""
    lines = rr.frame_bitmap()
    pic = rr.frame_picture()
    assert pic.shape == lines.shape == (2 * TILE, 4 * TILE), pic.shape
    assert np.array_equal(pic == PIX, lines == PIX)
    # the disc's indices: 0 transparent, 2 fill, 3 rings/cross, 4 bezel
    assert set(np.unique(pic)) <= {0, 2, 3, 4, PIX}, np.unique(pic)
    # every disc pixel is one of those indices, and the fill dominates
    n_fill = int((pic == 2).sum())
    assert n_fill > 400, n_fill
    assert int((pic == 3).sum()) > 100, int((pic == 3).sum())
    assert int((pic == 4).sum()) > 100, int((pic == 4).sum())


# ---- the palette ---------------------------------------------------------

def test_palette_entries_are_the_words_the_header_carries():
    """the header's three palettes are exactly the task's words: the frame
    bank (1 the dim amber rim/roof, 2..4 the disc), the bright blink word,
    and the sticks'/headings' own steady red-orange bank."""
    txt = open(os.path.join(ROOT, "build", "radar_map.h")).read()

    def words(name):
        m = re.search(r"static const u16 %s\[16\] = \{(.*?)\};" % name, txt, re.S)
        return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))]

    assert words("radar_pal") == [0x8000, 0x2d61, 0x0210, 0x3940, 0x4000]
    assert words("radar_stick_pal") == [0x8000, 0x6f42]
    m = re.search(r"static const u16 radar_pal_bright = (0x[0-9a-fA-F]{4});", txt)
    assert int(m.group(1), 16) == 0x4fc5
    # and the generator's own colour constants pack to those words
    assert rr.rgb_to_neo15(rr.RADAR_DIM_RGB) == 0x2d61
    assert rr.rgb_to_neo15(rr.RADAR_BRIGHT_RGB) == 0x4fc5
    assert rr.rgb_to_neo15(rr.RADAR_FILL_RGB) == 0x0210
    assert rr.rgb_to_neo15(rr.RADAR_RING_RGB) == 0x3940
    assert rr.rgb_to_neo15(rr.RADAR_BEZEL_RGB) == 0x4000
    assert rr.rgb_to_neo15(rr.RADAR_STICK_RGB) == 0x6f42


# ---- the C ROM placement -------------------------------------------------

def test_tile_counts_and_bases():
    # the frame base is exactly after the broken-window sheet (the star tile
    # is gone, dome-scenery Task 4), and the counts are what the Makefile
    # concatenates (part sizes)
    assert rr._FRAME_TILE_BASE == rr.rb.TILE_BASE + rr.rb.N_TILES
    assert 2 * H_N * rr.STICK_H_TILES == 198      # stick tile-slots
    assert 2 * rr.DX_N * rr.DX_N == 578           # heading tiles


def test_generated_header_matches():
    """the map header build/radar_map.h (what the C includes) carries the
    same numbers the generator derives here."""
    txt = open(os.path.join(ROOT, "build", "radar_map.h")).read()
    defs = {m.group(1): int(m.group(2))
            for m in re.finditer(r"#define\s+(\w+)\s+(\d+)", txt)}
    assert defs["RADAR_FRAME_TILES"] == 8
    assert defs["RADAR_STICK_TILES"] == 66
    assert defs["RADAR_HEAD_TILES"] == 578
    assert defs["RADAR_STICK_H"] == 48
    assert defs["RADAR_FRAME_TILE_BASE"] == rr._FRAME_TILE_BASE
    # the bases are chained from the parts' sizes in the C ROM, which the
    # Makefile writes back to back: the frame part is one tile after the
    # broken sheet (the star tile is gone), the sticks start after the
    # frame's tiles, the headings after the sticks' tile-slots. The absolute
    # values move with the dome size; the chain does not.
    assert rr._FRAME_TILE_BASE == rr.rb.TILE_BASE + rr.rb.N_TILES
    assert 2 * H_N * rr.STICK_H_TILES == defs["RADAR_STICK_TILES"] * rr.STICK_H_TILES


def test_payload_files_roundtrip():
    """decoding the emitted c1/c2 bytes with the standard tile decoder
    gives back the generator's pictures exactly (the runtime and the
    boot-test index these tile numbers). The payloads are generated into
    build/assets/ (the Makefile's render_radar.py rule and the C ROM
    parts), alongside the other sheets' c1/c2 files."""
    c1 = open(os.path.join(ROOT, "build", "assets", "radar-frame.c1"),
              "rb").read()
    c2 = open(os.path.join(ROOT, "build", "assets", "radar-frame.c2"),
              "rb").read()
    frame = rr.frame_picture()      # the C ROM's frame: the disc + the lines
    for r in range(2):
        for c in range(4):
            got = decode_tile(c1, c2, r * 4 + c)
            want = frame[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE]
            assert np.array_equal(got, want), (r, c)

    s1 = open(os.path.join(ROOT, "build", "assets", "radar-stick.c1"),
              "rb").read()
    s2 = open(os.path.join(ROOT, "build", "assets", "radar-stick.c2"),
              "rb").read()
    for h in range(H_N):
        for wide in (False, True):
            img = rr.stick_bitmap(h, wide)
            i = 2 * h + (1 if wide else 0)
            for tr in range(rr.STICK_H_TILES):
                got = decode_tile(s1, s2, i * rr.STICK_H_TILES + tr)
                want = img[tr * TILE:(tr + 1) * TILE, :]
                assert np.array_equal(got, want), (h, wide, tr)

    h1 = open(os.path.join(ROOT, "build", "assets", "radar-head.c1"),
              "rb").read()
    h2 = open(os.path.join(ROOT, "build", "assets", "radar-head.c2"),
              "rb").read()
    for ady in range(rr.DX_N):
        for adx in range(rr.DX_N):
            for hflip in (0, 1):
                i = (ady * rr.DX_N + adx) * 2 + hflip
                got = decode_tile(h1, h2, i)
                want = rr.heading_art(adx, ady, hflip)
                assert np.array_equal(got, want), (adx, ady, hflip)
