#!/usr/bin/env python3
"""render_radar.py HEADER.h [FRAME_C1 FRAME_C2 STICK_C1 STICK_C2 HEAD_C1 HEAD_C2]

The M5 Task 4 radar's pictures and tables.

The radar is the Vectrex Elite-style scanner mapped to a corner of the Neo
Geo screen (src/radar.h holds the user's constants: CX/CY the ellipse's
centre, RX/RY its radii, H the stick height at 6.0 radii straight up).
Three sorts of picture are pre-rendered as 16x16 C ROM tiles:

  FRAME — one static picture, 4 x 2 tiles (64 x 32 px), centred on
      (CX, CY): a 1-px ellipse of radii (RX, RY) plus the Vectrex's roof
      (tools/gen_dome.py radar_frame, scaled to px): the roof's half-width
      is RX/6 * sin(rim), its rim height H/6 * cos(rim) (rim = the dome's
      RIM_DEG 63.5), its peak H/6. Colour index 1, in its own palette (the
      blink writes one palette entry: dim (40,120,165) / bright
      (175,228,245) — the dome's glow ramp colours, the radar's palette).

  STICKS — per height 0..32 px, a 1-px vertical line (2 px wide locked) in
      a 1-tile-wide, 3-tile-tall (48 px) sprite, ending at the picture's
      BOTTOM row, in colour index 1. The sprite is placed so the line's
      foot is at (sx, sy), the spot; the picture is 48 px tall so a
      32-px stick plus the ellipse's lower half fits above the bottom row.

  HEADINGS — the heading lines: one per (dx, dy) 0..16 x 0..16, made by
      the hardware shrinking a pre-rendered 1-tile staircase diagonal
      (16 x 16: a 1-px stepped line from the tile's top-left to its
      bottom-right; colour index 1). Horizontal shrink by hz = dx - 1
      turns the diagonal into an (about) dx x dy px line; h-flip and
      v-flip pick the quadrant, so the four headings (±dx, ±dy) share one
      tile. dx = 0 (or dy = 0) uses a 1-px straight picture (vertical /
      horizontal), drawn by the same mechanism: the straight pictures are
      the diagonal's degenerate row/column.

The pictures' tile order and the per-(dx,dy) heading tables live in the
generated header (build/radar_map.h). The C ROM payload files are emitted
in the Makefile's part order (tiles concatenated back to back), one file
pair per picture family: frame, then sticks, then headings.

The art's geometry is proved in tests/test_radar_render.py: each stick
picture has exactly `h` lit pixels in the column 7 (8 for the hidden
2-px-wide locked variant centers on columns 7..8), and the frame's lit
pixels lie within 1 px of the ellipse and roof curves (computed from the
same constants, in floats).
"""
import argparse
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
import render_broken as rb  # noqa: E402  (TILE_BASE + N_TILES: where the stars start)

TILE = 16                       # C ROM tile size, px
STICK_H = 48                    # the stick pictures are 3 tiles tall
STICK_H_TILES = STICK_H // TILE
H_MAX = 32                      # the tallest stick (must fit STICK_H - 8)
H_N = H_MAX + 1                 # one stick picture per height 0..32
HEAD_MAX = 16                   # |dx|, |dy| <= 16 (the task's bound)
DX_N = HEAD_MAX + 1
# the palette's colour index 1 is the drawn colour (index 0 transparent):
PIX = 1                         # the stick and heading line colour index

# the C ROM position: exactly one tile after the star tile (the Makefile
# emits the radar parts after the stars').
_FRAME_TILE_BASE = rb.TILE_BASE + rb.N_TILES + 1   # = 19138

# the radar's constants, read from src/radar.h (the one tuning block)
_HDR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "src", "radar.h")

def radar_h_defs():
    txt = open(_HDR).read()
    out = {}
    for name in ("RADAR_CX", "RADAR_CY", "RADAR_RX", "RADAR_RY", "RADAR_H"):
        m = re.search(r"#define\s+%s\s+(.+)$" % name, txt, re.M)
        assert m, f"{name} missing from src/radar.h"
        value = m.group(1).split("/*")[0].strip()
        if "DOME_Y" in value:                # RADAR_CY = DOME_Y + 112: follow
            dome = open(os.path.join(os.path.dirname(_HDR), "dome.h")).read()
            dy = int(re.search(r"#define\s+DOME_Y\s+(\d+)", dome).group(1))
            value = value.replace("DOME_Y", str(dy))
        out[name] = eval(value)              # a plain int, or DOME_Y + 112
    return out

# the roof's geometry (gen_dome.py radar_frame): the dome cut at the
# camera-facing rim RIM_DEG, its picture scaled so the radar's ellipse edge
# (RADAR_RANGE = 6.0 radii) holds the rim: half-width RX/6 * sin(rim), rim
# height H/6 * cos(rim), peak H/6.
RADAR_RANGE = 6.0
RIM = math.radians(g.RIM_DEG)


def roof(d):
    """the roof's three landmark values (px, floats): half-width, rim
    height, peak height — from the task's formulas and src/radar.h."""
    return (d["RADAR_RX"] / RADAR_RANGE * math.sin(RIM),
            d["RADAR_H"] / RADAR_RANGE * math.cos(RIM),
            d["RADAR_H"] / RADAR_RANGE)


def rgb_to_neo15(rgb):
    """ngdevkit paltool's rgb24_to_packed15 (as render_stars.py)."""
    r, gg, b = [c >> 2 for c in rgb]
    dark = 1 if ((r & 1) + (gg & 1) + (b & 1)) == 0 else 0
    r, gg, b = r >> 1, gg >> 1, b >> 1
    lsb = ((r & 1) << 2) | ((gg & 1) << 1) | (b & 1)
    r, gg, b = r >> 1, gg >> 1, b >> 1
    return (dark << 15) | (lsb << 12) | (r << 8) | (gg << 4) | b


# ---- the frame (ellipse + roof) -----------------------------------------

def frame_bitmap():
    """the 64 x 32 palette-index picture: a 1-px ellipse (RX, RY) centred
    on (CX, CY) plus the roof, with the roof over the ellipse's upper half.
    Lit pixels are index PIX, everything else 0."""
    d = radar_h_defs()
    cx, cy = d["RADAR_CX"], d["RADAR_CY"]
    rx, ry = d["RADAR_RX"], d["RADAR_RY"] / 10.0
    hw, hrim, hpk = roof(d)
    # the picture's canvas: a 4 x 2 tile block whose centre is (CX, CY)
    w, h = 4 * TILE, 2 * TILE
    img = np.zeros((h, w), np.uint8)
    x0, y0 = cx - w // 2, cy - h // 2
    for yy in range(h):
        for xx in range(w):
            px, py = x0 + xx, y0 + yy          # screen px (y down)
            # the ellipse: (px-cx)^2 / rx^2 + (py-cy)^2 / ry^2 == 1 (a
            # 1-px curve: the pixel centre is within 0.5 px of the curve)
            ex = (px - cx) / rx
            ey = (py - cy) / ry
            r2 = ex * ex + ey * ey
            if abs(r2 - 1.0) <= 0.5 * math.hypot(2 * ex / rx, 2 * ey / ry) \
               and r2 <= 1.5:
                img[yy, xx] = PIX
    # the roof: the Vectrex's two lines — from the base-left point
    # (cx-w, cy-hrim) up to the peak (cx, cy-hpk), then down to the
    # base-right point (cx+w, cy-hrim); y down, so the roof is an arch
    # (the /\ seen from the side) sitting just above the ellipse's centre.
    rim_y, peak_y = cy - hrim, cy - hpk
    roof_pts = [(cx - hw, rim_y), (cx, peak_y), (cx + hw, rim_y)]
    for (ax, ay), (bx, by) in zip(roof_pts, roof_pts[1:]):
        n = max(1, int(math.ceil(max(abs(bx - ax), abs(by - ay)))) + 1)
        for i in range(n):
            t = i / (n - 1) if n > 1 else 0.0
            px, py = round(ax + (bx - ax) * t), round(ay + (by - ay) * t)
            xx, yy = px - x0, py - y0
            if 0 <= xx < w and 0 <= yy < h:
                img[yy, xx] = PIX
    return img


def r2check(px, py, cx, cy, rx, ry):
    return ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 - 1.0


# ---- the sticks ----------------------------------------------------------

def stick_bitmap(h, wide):
    """the stick picture (STICK_H x STICK_H... actually 1 tile wide x 3
    tiles tall: 16 x 48): a 1-px (2-px when `wide`) vertical line in
    column 7 (columns 7..8 when wide) ending at the picture's bottom row
    (the foot, where the spot is), `h` px tall. Returns the palette-index
    array (16 x 48, index PIX or 0)."""
    img = np.zeros((STICK_H, TILE), np.uint8)
    if h == 0:
        return img
    if wide:
        for r in range(STICK_H - h, STICK_H):
            img[r, 7] = PIX
            img[r, 8] = PIX
    else:
        for r in range(STICK_H - h, STICK_H):
            img[r, 7] = PIX
    return img


# ---- the headings --------------------------------------------------------

# The Neo Geo's horizontal and vertical zoom tables (the "000-lo.lo" part
# of aes.zip; MAME's neosprite.cpp zoom_x_tables / m_region_zoomy). A
# 1-tile sprite's box is 16 px wide and 16 screen lines tall (height 1);
# the k-th drawn box column reads art column p_k (ZOOM_X set-bit
# positions), the l-th box line reads art row A_l (ZOOM_Y's low nibble;
# the high nibble is the SCB1 column row, 0 for exactly the first dy lines
# at the vz we pick). The heading pictures are solved against these EXACT
# tables, so the drawn line lands at the box position the runtime (and the
# boot-test's model) expects.
import zipfile as _zipfile

_HOME = os.path.expanduser("~")
_AES = os.path.join(_HOME, "Development", "emulators", "roms", "mame-neogeo",
                    "aes.zip")
if not os.path.exists(_AES):
    raise RuntimeError(f"aes.zip not found at {_AES}: the heading art is "
                       "solved against the hardware's zoom tables")
_ZOOM_Y = _zipfile.ZipFile(_AES).read("000-lo.lo")

# MAME's horizontal zoom tables (neosprite.cpp zoom_x_tables): bit 15 of a
# 16-bit mask tells whether the pixel at that step is drawn; the drawn
# pixels land at the box's screen columns 0..n-1 in order, sampling the art
# columns with the set bits (the position of the k-th set bit from the
# top). ZOOM_X_COLS[hz] = the art columns read, in box-column order.
ZOOM_X = [0x0080, 0x0880, 0x0888, 0x2888, 0x288a, 0x2a8a, 0x2aaa, 0xaaaa,
          0xaaea, 0xbaea, 0xbaeb, 0xbbeb, 0xbbef, 0xfbef, 0xfbff, 0xffff]
ZOOM_X_COLS = []
for _t in ZOOM_X:
    cols = []
    _x = _t
    for _i in range(16):
        if _x & 0x8000:
            cols.append(_i)
        _x = (_x << 1) & 0xffff
        if _x == 0:
            break
    ZOOM_X_COLS.append(cols)
assert [len(c) for c in ZOOM_X_COLS] == list(range(1, 17))  # hz+1 columns


def zoom_rows(vz):
    """(SCB1-row, art-row) per box line 0..15 at vertical zoom vz."""
    out = []
    for l in range(16):
        v = _ZOOM_Y[(vz << 8) | l]
        out.append((v >> 4, v & 0x0f))
    return out


# vz = 16*(dy-1) + 1 draws exactly dy box lines all from SCB1 row 0; the
# art rows they read are the low nibbles. Cache them.
_VZ_FOR_DY = {}
for _dy in range(1, 17):
    _vz = 16 * (_dy - 1) + 1
    _t = zoom_rows(_vz)
    _rows = [a for _tr, a in _t if _tr == 0]
    assert len(_rows) == _dy, (_dy, _rows)
    _VZ_FOR_DY[_dy] = (_vz, _rows)


def heading_vz(dy):
    """the SCB2 vertical byte for a heading `dy` px long (1..16): the
    first vz whose box draws exactly dy lines, all from SCB1 row 0."""
    return _VZ_FOR_DY[dy][0]


def heading_art(dx, dy, hflip):
    """the 16x16 heading tile for a heading |dx| x |dy| px (0..16 each).
    `hflip` is the SCB1 horizontal flip the RUNTIME will set; the art is
    solved so that AT THE DRAW time the lit box pixels form a 1-px
    staircase across the box:
        hflip 0: box (0,0) .. (dy-1, dx-1)   (down-right; runtime hf=0)
        hflip 1: box (0, dx-1) .. (dy-1, 0)  (down-left; runtime hf=1)
    The runtime picks hflip = (sdx < 0) XOR (sdy < 0) and places the box
    with its T corner at the stick's top (see the header). The art is
    solved against the hardware's zoom tables: the drawn pixel at box
    (line l, drawn col k) reads art row A_l (ZOOM_Y low nibble) and art
    column p_k (ZOOM_X set-bit positions); `hflip` mirrors the art columns
    read. dx = 0 or dy = 0 make a straight 1-px vertical / horizontal line
    (the same inversion). (dx, dy) = (0, 0) is never drawn."""
    img = np.zeros((TILE, TILE), np.uint8)
    if dx == 0 and dy == 0:
        return img
    hz = max(0, dx - 1)
    p = ZOOM_X_COLS[hz]                       # art cols for drawn cols 0..dx-1
    AC = (lambda c: c) if not hflip else (lambda c: 15 - c)
    if dy == 0 or dy == 1:                    # a 1-line heading: the drawn
        art_rows = [_ZOOM_Y[(1 << 8) | 0] & 0x0f]  # staircase is one box
        r = art_rows[0]                       # line: light every sampled col
        for c in p:
            img[r, AC(c)] = PIX
        return img
    if dx == 0:                               # vertical: 1 box column
        vz, art_rows = _VZ_FOR_DY[dy]
        for l in range(dy):
            img[art_rows[l], AC(p[0])] = PIX
        return img
    vz, art_rows = _VZ_FOR_DY[dy]
    n_m1 = dx - 1
    d_m1 = dy - 1
    if not hflip:                             # down-right: col l -> l
        for l in range(dy):
            c = round(l * n_m1 / d_m1)
            img[art_rows[l], AC(p[c])] = PIX
    else:                                     # down-left: col l -> n-1-l
        for l in range(dy):
            c = n_m1 - round(l * n_m1 / d_m1)
            img[art_rows[l], AC(p[c])] = PIX
    return img


# the heading tiles: 2 per (|dx|, |dy|) — art[hflip][dy][dx]
HEADING_TILES = []
for _dy in range(DX_N):
    for _dx in range(DX_N):
        HEADING_TILES.append(heading_art(_dx, _dy, 0))
        HEADING_TILES.append(heading_art(_dx, _dy, 1))
assert len(HEADING_TILES) == 2 * DX_N * DX_N


# ---- C ROM tiles ---------------------------------------------------------

def encode_tile(img):
    """one 16x16 tile's c1/c2 bytes (the same order render_broken.py and
    render_stars.py use: 8x8 sub-tiles at file offsets 8, 136, 0, 128, each
    row two bytes, LSB-first). Returns (c1_bytes, c2_bytes)."""
    assert img.shape == (TILE, TILE), img.shape
    c1 = bytearray(64)
    c2 = bytearray(64)
    pos = 0
    for off in (8, 136, 0, 128):
        sy, sx = off // 16, off % 16
        for y in range(8):
            p0 = p1 = p2 = p3 = 0
            for x in range(8):
                px = int(img[sy + y][sx + x])
                p0 |= (px & 1) << x
                p1 |= ((px >> 1) & 1) << x
                p2 |= ((px >> 2) & 1) << x
                p3 |= ((px >> 3) & 1) << x
            c1[pos] = p0
            c1[pos + 1] = p1
            c2[pos] = p2
            c2[pos + 1] = p3
            pos += 2
    return bytes(c1), bytes(c2)


def pack_tiles(images, out_c1, out_c2):
    """write the tiles (a list of 16x16 palette-index arrays) to the c1/c2
    payload files, back to back."""
    c1 = bytearray()
    c2 = bytearray()
    for img in images:
        a, b = encode_tile(img)
        c1 += a
        c2 += b
    with open(out_c1, "wb") as f:
        f.write(bytes(c1))
    with open(out_c2, "wb") as f:
        f.write(bytes(c2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("frame_c1", nargs="?")
    ap.add_argument("frame_c2", nargs="?")
    ap.add_argument("stick_c1", nargs="?")
    ap.add_argument("stick_c2", nargs="?")
    ap.add_argument("head_c1", nargs="?")
    ap.add_argument("head_c2", nargs="?")
    args = ap.parse_args()

    d = radar_h_defs()

    # ---- the frame picture (4 x 2 tiles) ----
    frame = frame_bitmap()
    assert frame.shape == (2 * TILE, 4 * TILE)
    n_frame = 8
    # the frame's lit pixels: within 1 px of the ellipse curve or a roof
    # line (the roof is the Vectrex's two lines, peak to each base)
    hw, hrim, hpk = roof(d)
    cx, cy = d["RADAR_CX"], d["RADAR_CY"]
    w0, h0 = cx - 4 * TILE // 2, cy - 2 * TILE // 2
    rx, ry = d["RADAR_RX"], d["RADAR_RY"] / 10.0
    roof_segs = [((cx - hw, cy - hrim), (cx, cy - hpk)),
                 ((cx + hw, cy - hrim), (cx, cy - hpk))]

    def seg_dist(qx, qy, a, b):
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        vx, vy = bx - ax, by - ay
        wx, wy = qx - ax, qy - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
        return math.hypot(wx - t * vx, wy - t * vy)

    n_lit = 0
    for yy in range(frame.shape[0]):
        for xx in range(frame.shape[1]):
            if frame[yy, xx] != PIX:
                continue
            n_lit += 1
            px, py = w0 + xx, h0 + yy
            ell = abs(((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 - 1.0)
            roof_d = min(seg_dist(px, py, a, b) for a, b in roof_segs)
            if min(ell, roof_d) > 1.0:
                raise SystemExit(
                    f"frame pixel ({px},{py}) not within 1 px of the "
                    f"ellipse or roof (ell {ell:.3f}, roof {roof_d:.3f})")
    assert n_lit > 0

    # ---- the sticks: h = 0..32, thin and wide ----
    sticks = []
    for h in range(H_N):
        sticks.append(stick_bitmap(h, False))
        sticks.append(stick_bitmap(h, True))
    assert len(sticks) == 2 * H_N
    for h in range(H_N):
        for wide in (False, True):
            img = sticks[2 * h + (1 if wide else 0)]
            assert img.shape == (STICK_H, TILE)
            # exactly h lit pixels in the column(s), ending at the bottom
            col = 7 if not wide else slice(7, 9)
            n = int(img[STICK_H - h:, col].sum()) if h else 0
            assert n == (2 * h if wide else h), (h, wide, n)
            assert int(img[:STICK_H - h, col].sum()) == 0

    # ---- the headings: 2 tiles per (dx, dy) 0..16 (hflip 0 and 1) ----
    heads = []
    for dy in range(DX_N):
        for dx in range(DX_N):
            heads.append(heading_art(dx, dy, 0))
            heads.append(heading_art(dx, dy, 1))
    assert len(heads) == 2 * DX_N * DX_N

    # ---- the header ----
    pal_dim = rgb_to_neo15((40, 120, 165))
    pal_bright = rgb_to_neo15((175, 228, 245))
    with open(args.header, "w") as hf:
        w = hf.write
        w("/* generated by tools/render_radar.py: do not edit */\n"
          "#ifndef RADAR_MAP_H\n#define RADAR_MAP_H\n")
        w(f"#define RADAR_FRAME_TILES {n_frame}   /* the frame: 4 x 2 tiles */\n")
        w(f"#define RADAR_STICK_TILES {2 * H_N}  /* h 0..32, thin then "
          f"wide */\n")
        w(f"#define RADAR_HEAD_TILES {2 * DX_N * DX_N}  /* 2 tiles x "
          f"(dy, dx), 0..16: hflip 0 then hflip 1 */\n")
        w(f"#define RADAR_HEAD_MAX {HEAD_MAX}\n")
        w(f"#define RADAR_STICK_H {STICK_H}      /* px: the stick pictures "
          f"are {STICK_H_TILES} tiles tall */\n")
        w(f"/* C ROM tile bases: the radar's pictures are the LAST parts of "
          f"the C ROM,\n   after the broken-window sheet AND the star tile "
          f"(STAR_TILE_BASE = 19137,\n   render_stars). Frame = 19138, "
          f"sticks = 19138+8 = 19146, headings =\n   19146+66*3 = 19344 "
          f"(each of the 66 stick pictures is\n   {STICK_H_TILES} tiles "
          f"tall, so the sticks occupy 66*{STICK_H_TILES} = "
          f"{2 * H_N * STICK_H_TILES} tile-slots):\n   2 x (17 x 17) = 578 "
          f"heading tiles. The Makefile\n   emits the parts in this order "
          f"(frame, sticks, headings) right after\n   stars.c1/c2, so the "
          f"tile at each number is exactly the picture's tile. */\n")
        w(f"#define RADAR_FRAME_TILE_BASE {_FRAME_TILE_BASE}\n")
        w(f"#define RADAR_STICK_TILE_BASE (RADAR_FRAME_TILE_BASE + "
          f"RADAR_FRAME_TILES)\n")
        w(f"#define RADAR_STICK_TILE_SLOTS (RADAR_STICK_TILES * "
          f"{STICK_H_TILES})  /* the sticks' tile-slots in the C ROM "
          f"({2 * H_N} pictures x {STICK_H_TILES} tiles each = "
          f"{2 * H_N * STICK_H_TILES}) */\n")
        w(f"#define RADAR_HEAD_TILE_BASE (RADAR_STICK_TILE_BASE + "
          f"RADAR_STICK_TILE_SLOTS)\n")
        w(f"/* the frame's palette bank: entry 1 = the ellipse/roof colour —\n"
          f"   dim (40,120,165), bright (175,228,245); the lock-on blink "
          f"writes\n   exactly this one entry. The sticks and headings share "
          f"it. */\n")
        w("static const u16 radar_pal[16] = {0x8000, 0x%04x};\n" % pal_dim)
        w("/* the bright colour (the lock-on blink's palette entry) */\n")
        w("static const u16 radar_pal_bright = 0x%04x;\n" % pal_bright)
        w("#endif\n")

    # ---- the payload files ----
    if args.frame_c1 and args.frame_c2:
        pack_tiles([frame[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE]
                    for r in range(2) for c in range(4)],
                   args.frame_c1, args.frame_c2)
    if args.stick_c1 and args.stick_c2:
        pack_tiles([sticks[i][r * TILE:(r + 1) * TILE, :]
                    for i in range(len(sticks)) for r in range(STICK_H_TILES)],
                   args.stick_c1, args.stick_c2)
    if args.head_c1 and args.head_c2:
        pack_tiles(heads, args.head_c1, args.head_c2)
    print(f"radar art: frame {n_frame} tiles, sticks {2 * H_N} "
          f"({2 * H_N * STICK_H_TILES} tile-slots), headings "
          f"{2 * DX_N * DX_N}")


if __name__ == "__main__":
    main()
