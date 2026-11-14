#!/usr/bin/env python3
"""render_missiles.py OUTDIR HEADER.h [--preview PNG]

Pre-renders the missile (the Vectrex game's dart: a tetrahedron, tip first)
for every ring of cells and every 7.5 degrees of screen azimuth (25 views,
mirrored for the rest), at three sizes, plus the explosion, as indexed
16-colour sprite sheets in OUTDIR:

  mis_l.gif  48x48 px views (3x3 tiles): a 2/3-scale 64x64 picture
  mis_m.gif  32x32 (2x2): a 2/3-scale 32x32 picture
  mis_s.gif  16x16 (1x1): a 2/3-scale 16x16 picture
  expl.gif   16 frames of 48x48: fragments flying out (the Vectrex's 2D
             animation), a 2/3-scale 64x64 picture

Dome-scenery Task 2: the pictures are scaled at generation time, not by
hardware shrink. Each dart is drawn with the full-dome art's own clamp
(room and strokes: box0/16 px), then its *geometry* is scaled by 2/3 and
centred in the smallest 16-px tile box that holds it (48/32/16 px); the
explosion is drawn at the full-dome 64x64, 0.6 px per Vectrex unit, and
centred in 48x48. Scaling the geometry (not the finished RGBA picture)
keeps the strokes' proportions right at every view. The header's tip and
drawn length are scaled with it, so the runtime's shrink arithmetic is
unchanged. Timings (EXPL_FRAMES 16) do not scale.

A bullet is the dart turned tip-outward at half size: the same pictures
flipped both ways, in another palette. HEADER gets the tile numbers (after
the ship's, in this order), each view's tip position in its picture, and the
three palettes (missile, bullet, explosion) as Neo Geo colour words."""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
import gen_missiles as gm  # noqa: E402
import render_dome as rd  # noqa: E402
import render_hovercraft as rs  # noqa: E402

VIEWS = 25                          # 7.5 deg steps of screen azimuth, 0..180 (mirrored beyond)
STEP = g.STEPS // 48                # rotation steps per view
# name, tile box px (canvas), full-dome picture box px, full-dome dart length px
LEVELS = [("l", 48, 64, 48), ("m", 32, 32, 24), ("s", 16, 16, 12)]
ART = 2.0 / 3.0                    # the art's scale (the dome's DOME_SCALE)
R_REP = 1.6                         # the dart's shape is taken at this distance (the Vectrex's)
DART_W = 0.075                      # base corner distance from the axis (the Vectrex's MIS_WIDTH)
TILE_BASE = rs.TILE_BASE + rs.TILES   # after the ship's 2500 tiles
EXPL_FRAMES, EXPL_BOX0, EXPL_PX = 16, 64, 0.6
EXPL_BOX = 48                      # 64 x 2/3, rounded up to a 16-px tile box

MISSILE = [(255, 0, 255),                                      # 0 transparent (key colour)
           (70, 10, 20), (110, 18, 30), (150, 28, 40), (190, 40, 50), (225, 60, 64), (250, 90, 80),  # 1-6 body
           (120, 20, 30),                                      # 7 spare
           (160, 40, 50), (200, 60, 60), (235, 90, 80),        # 8-10 glow ramp
           (250, 130, 110), (255, 170, 150), (255, 200, 185),  # 11-13
           (255, 228, 220), (255, 255, 250)]                   # 14-15 core
BULLET = [(255, 0, 255),                                       # the same layout, a pale
          (140, 128, 80), (170, 158, 100), (200, 190, 125),   # tracer (M8 art pass: the
          (225, 215, 150), (242, 235, 180), (252, 248, 210),  # player's shot reads light,
          (170, 158, 100),                                    # against the orange ship and
          (200, 190, 125), (225, 215, 150), (245, 238, 180),  # the red missiles; it was green)
          (250, 245, 200), (253, 250, 215), (255, 252, 230),
          (255, 255, 240), (255, 255, 250)]
EXPLOSION = [(255, 0, 255),
             (60, 10, 0), (110, 25, 0), (160, 45, 0), (205, 70, 0), (235, 105, 10), (250, 140, 30),
             (255, 170, 50), (255, 195, 80), (255, 215, 110), (255, 230, 140), (255, 240, 170),
             (255, 248, 200), (255, 252, 220), (255, 255, 240), (255, 255, 255)]


def neo(col):
    """ngdevkit paltool's rgb24_to_packed15."""
    r, g_, b = [c >> 2 for c in col]
    dark = 1 if ((r & 1) + (g_ & 1) + (b & 1)) == 0 else 0
    r, g_, b = r >> 1, g_ >> 1, b >> 1
    lsb = ((r & 1) << 2) | ((g_ & 1) << 1) | (b & 1)
    r, g_, b = r >> 1, g_ >> 1, b >> 1
    return dark << 15 | lsb << 12 | r << 8 | g_ << 4 | b


def dart(t, j):
    """the dart's 4 corners (tip first) on ring angle t at screen azimuth j,
    tip at R_REP, pointing at the centre; the faces; and the tip's depth."""
    a = 2 * math.pi * j / g.STEPS
    c = gm.world(1.0, t, j)
    north = -np.array([math.cos(t) * math.sin(a), -math.sin(t), math.cos(t) * math.cos(a)])
    east = np.array([math.cos(a), 0.0, -math.sin(a)])
    tip = R_REP * c
    base = tip + gm.DART_LEN * c
    P = np.array([tip] + [base + DART_W * (math.cos(b) * north + math.sin(b) * east)
                          for b in (0, 2 * math.pi / 3, 4 * math.pi / 3)])
    return P, [[1, 2, 3], [0, 1, 2], [0, 2, 3], [0, 3, 1]]


_FIT = []


def render_view(t, j, box, box0=None, length=None):
    """(picture, tip, length): the dart drawn at the full-dome art's
    `length` px in its `box0` canvas, then its geometry is scaled by ART
    and centred in the `box` tile canvas (Dome-scenery Task 2). `length`
    defaults to box0's full-dome dart length and box0 to box."""
    if box0 is None:
        box0 = box
    if length is None:
        length = 48 * box0 // 64
    if not _FIT:
        _FIT.append(g.fit())
    f = _FIT[0]
    P, faces = dart(t, j)
    pr = [gm.project(p, f) for p in P]
    xy = np.array([[p[0], p[1]] for p in pr])
    nominal = gm.DART_LEN * f[0] / pr[0][2]
    # the art is clamped by the full-dome art's own room and drawn length
    # (box0/16 stroke: 4 at 64, 2 at 32, 1 at 16), and its geometry is then
    # scaled by ART, so the picture is exactly 2/3 of the full-dome
    # picture at every view rather than re-clamped at the smaller canvas
    # (which would flatten the near views' foreshortening). The strokes are
    # pixel constants too, so they scale by ART separately.
    width0 = max(1, box0 // 16)
    room = box0 - 2 - 2 * width0
    # the full-dome drawn length, then the art's 2/3 scale
    drawn = min(length, int(room * nominal / np.ptp(xy, axis=0).max())) * ART
    width = max(1, round(ART * width0))        # the stroke, 2/3: 4 -> 3, 2 -> 1, 1 -> 1
    k = drawn / nominal          # scale the geometry to the drawn length
    xy = (xy - xy[0]) * k
    lo, hi = xy.min(0), xy.max(0)
    tip = np.array([box / 2, box / 2]) - (lo + hi) / 2
    xy = xy + tip
    pos = g.camera()[0]
    ctr = P.mean(axis=0)
    img = Image.new("RGBA", (box * rd.SS, box * rd.SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    vis = set()
    for face in faces:
        Q = P[face]
        n = np.cross(Q[1] - Q[0], Q[2] - Q[0])
        fc = Q.mean(axis=0)
        if n @ (fc - ctr) < 0:
            n = -n
        if n @ (pos - fc) <= 0:
            continue
        shade = round(5 * max(0.0, float(n / np.linalg.norm(n) @ g.LIGHT)))
        d.polygon([tuple(xy[i] * rd.SS) for i in face], fill=MISSILE[1 + shade] + (255,))
        for i in range(3):
            vis.add((min(face[i], face[(i + 1) % 3]), max(face[i], face[(i + 1) % 3])))
    segs = [(xy[a], xy[b]) for a, b in sorted(vis)]
    for colour, w, alpha in ((MISSILE[9], 2 * width, 0.6), (MISSILE[15], width, 1.0)):
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        rd.lines(layer, segs, colour, w, alpha)
        img = Image.alpha_composite(img, layer)
    # the tip is a single dart vertex; at 2/3 with a 1-px stroke its
    # anti-aliased cap can vanish in the quantize, so snap the header's tip
    # to the lit pixel nearest the drawn vertex (it positions the dart at
    # runtime, and must be on the picture)
    small = img.resize((box, box), Image.BOX)
    idx = quantize(small, MISSILE)
    tx, ty = int(round(tip[0])), int(round(tip[1]))
    lit = np.argwhere(idx > 0)
    if len(lit):
        d = np.abs(lit[:, ::-1] - [tx, ty]).max(axis=1)
        k = int(d.argmin())
        if d[k] <= 3:
            tx, ty = int(lit[k, 1]), int(lit[k, 0])
    return small, np.array([tx, ty], float), max(1, round(drawn))


def quantize(img, palette):
    a = np.asarray(img).astype(float)
    pal = np.array(palette[1:], float)
    idx = ((a[..., None, :3] - pal[None, None]) ** 2).sum(-1).argmin(-1) + 1
    idx[a[..., 3] < 128] = 0
    return idx.astype(np.uint8)


def explosion(t):
    """frame t: the Vectrex's fragments (make_explosion), as glowing strokes,
    after a flash that swells and fades over the first frames. Drawn in the
    full-dome 64x64 canvas at its 2/3 pixel scale, then centred in a 48x48
    tile canvas (Dome-scenery Task 2)."""
    box = EXPL_BOX
    k = EXPL_PX * rd.SS * ART
    img = Image.new("RGBA", (box * rd.SS, box * rd.SS), (0, 0, 0, 0))
    c0 = np.array([box / 2, box / 2]) * rd.SS
    d = ImageDraw.Draw(img)
    if t < 4:                                    # the flash
        rad = (6 + 4 * t) * k
        d.ellipse([c0[0] - rad, c0[1] - rad, c0[0] + rad, c0[1] + rad], fill=EXPLOSION[12 - 2 * t] + (255,))
        rad *= 0.55
        d.ellipse([c0[0] - rad, c0[1] - rad, c0[0] + rad, c0[1] + rad], fill=EXPLOSION[15] + (255,))
    segs = []
    dist = (4 + 36 * (1 - (1 - t / (EXPL_FRAMES - 1)) ** 2)) * k
    for i in range(6):
        a = 2 * math.pi * (i + 0.3 * (i % 2)) / 6
        spin = a + 0.5 * t * (1 if i % 2 else -1)
        c = c0 + np.array([math.cos(a), math.sin(a)]) * dist * (0.8 + 0.4 * ((i * 7) % 5) / 4)
        h = np.array([math.cos(spin), math.sin(spin)]) * 6 * k
        segs.append((c - h, c + h))
    heat = 1 - t / EXPL_FRAMES                   # cools from white to dark red
    glow, core = EXPLOSION[max(1, round(3 + 7 * heat))], EXPLOSION[max(2, round(5 + 10 * heat))]
    for colour, w in ((glow, round(4 * ART) * rd.SS), (core, round(2 * ART) * rd.SS)):
        for p, q in segs:
            d.line([tuple(p), tuple(q)], fill=colour + (255,), width=w)
    return img.resize((EXPL_BOX, EXPL_BOX), Image.BOX)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("header")
    ap.add_argument("--preview")
    args = ap.parse_args()
    th = gm.tables()["th"]
    flat = lambda pal: [c for rgb in pal for c in rgb]   # noqa: E731

    bases, anchors, base = [], [], TILE_BASE
    for name, box, box0, length in LEVELS:
        sheet = np.zeros((box * len(th) * VIEWS, box), np.uint8)
        anc = []
        for k, t in enumerate(th):
            for v in range(VIEWS):
                img, tip, used = render_view(t, v * STEP, box, box0, length)
                sheet[(k * VIEWS + v) * box:(k * VIEWS + v + 1) * box] = quantize(img, MISSILE)
                anc.append((round(tip[0]), round(tip[1]), used))
        im = Image.fromarray(sheet, "P")
        im.putpalette(flat(MISSILE))
        im.save(os.path.join(args.outdir, f"mis_{name}.gif"))
        bases.append(base)
        anchors.append(anc)
        base += len(th) * VIEWS * (box // 16) ** 2
    ex = np.vstack([quantize(explosion(t), EXPLOSION) for t in range(EXPL_FRAMES)])
    im = Image.fromarray(ex, "P")
    im.putpalette(flat(EXPLOSION))
    im.save(os.path.join(args.outdir, "expl.gif"))
    if args.preview:
        row = [Image.open(os.path.join(args.outdir, f"mis_{n}.gif")).convert("RGB")
               .crop((0, (6 * VIEWS + v) * b, b, (6 * VIEWS + v + 1) * b)).resize((64, 64), Image.NEAREST)
               for n, b, _, _ in LEVELS for v in (0, 6, 12, 18, 24)]
        out = Image.new("RGB", (64 * len(row), 64 * 2))
        for i, r in enumerate(row):
            out.paste(r, (64 * i, 0))
        for i in range(EXPL_FRAMES):
            out.paste(im.convert("RGB").crop((0, i * 64, 64, i * 64 + 64)), (64 * i, 64))
        out.resize((out.width * 2, out.height * 2), Image.NEAREST).save(args.preview)

    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/render_missiles.py: do not edit */\n#ifndef MISSILE_MAP_H\n#define MISSILE_MAP_H\n")
        w(f"#define MIS_VIEWS   {VIEWS}      /* per ring: screen azimuth 0..180 deg, 7.5 deg apart */\n")
        w(f"#define MIS_LEVELS  {len(LEVELS)}\n")
        w("/* per size: first tile, columns (= rows), dart length (px) */\n")
        w("static const u16 mis_tile_base[MIS_LEVELS] = {" + ", ".join(map(str, bases)) + "};\n")
        w("static const u8 mis_cols[MIS_LEVELS] = {" + ", ".join(str(b // 16) for _, b, _, _ in LEVELS) + "};\n")
        w("static const u8 mis_len[MIS_LEVELS] = {" + ", ".join(str(max(1, round(n * ART))) for _, _, _, n in LEVELS) + "};\n")
        w("/* tile of size l, ring k, view v, column c, row r:\n"
          "   mis_tile_base[l] + ((k * MIS_VIEWS + v) * cols + r) * cols + c */\n")
        w("/* each picture's tip (px) and the dart's length drawn (px; mis_len[size] unless\n"
          "   that would not fit): [size][ring * MIS_VIEWS + view][x, y, length] */\n")
        w("static const u8 mis_tip[MIS_LEVELS][%d][3] = {\n" % (len(th) * VIEWS))
        w(",\n".join("  {" + ", ".join("{%d, %d, %d}" % a for a in anc) + "}" for anc in anchors) + "\n};\n")
        w(f"#define EXPL_TILE_BASE {base}\n#define EXPL_FRAMES {EXPL_FRAMES}\n#define EXPL_COLS {EXPL_BOX // 16}\n")
        for name, pal in (("mis_pal", MISSILE), ("bul_pal", BULLET), ("expl_pal", EXPLOSION)):
            w(f"static const u16 {name}[16] = {{0x8000, " + ", ".join("0x%04x" % neo(c) for c in pal[1:]) + "};\n")
        w("#endif\n")


if __name__ == "__main__":
    main()
