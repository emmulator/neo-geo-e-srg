#!/usr/bin/env python3
"""render_rockets.py OUTDIR HEADER.h [--preview PNG]

The incoming missile as a classic cartoon rocket (the user's call, 10-26):
a white body with a red nose and red fins, a 1-px black outline, and an
exhaust flame out of the back that flickers through MIS_FRAMES (4)
pictures. It replaces tools/render_missiles.py's tetrahedral dart and
writes the same outputs, so the flight code is unchanged:

  mis_l.gif  48x48 px pictures (3x3 tiles)  \\  every ring x 25 views,
  mis_m.gif  32x32 (2x2)                     >  each tile's 4 flame frames
  mis_s.gif  16x16 (1x1)                    /   side by side (see below)
  expl.gif   the explosion, unchanged (render_missiles.explosion)

The rocket stands where the dart stood: its nose is the dart's tip (on the
missile's line, at R_REP, pointing at the centre), its body is the dart's
length (gen_missiles.DART_LEN), and the header's tip and drawn length mean
what they meant, so src/mis_gfx.c's placement and shrink arithmetic stays.
The flame trails behind the body and is not part of the drawn length. All 4
frames of a picture share one scale and placement (computed with the
longest flame), so only the flame moves between frames.

The flicker is the LSPC's 4-frame auto-animation (SCB1 attribute bit 2):
the hardware replaces a tile number's low 2 bits with its counter, so each
tile's 4 frames are 4 consecutive tile numbers starting on a multiple of 4.
A sheet is 64 px wide: tile row i holds tile i's frames 0..3 left to right,
and tiletool numbers them i*4 + frame. So the tile of size l, ring k, view
v, row r, column c, frame f is

    mis_tile_base[l] + (((k * MIS_VIEWS + v) * cols + r) * cols + c) * 4 + f

(the runtime writes frame 0 with the animation bit; every base is a
multiple of 4). The BIOS-zero tiles 0..3 are blank in every frame, so a
blank tile (0) may carry the animation bit too.

Palette (mis_pal, PAL_MISSILE): 0 transparent, 1 the outline's black, 2..6
the body's whites (shade), 7..10 the red trim (shade), 11..15 the flame
(red edge to white-yellow core). HEADER also keeps bul_pal and expl_pal
(render_missiles' palettes, unchanged)."""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
import gen_missiles as gm  # noqa: E402
import render_missiles as rm  # noqa: E402

FRAMES = 4                 # the flame's flicker (LSPC 4-frame auto-animation)
SS = 8                     # supersampling
L = gm.DART_LEN            # body length (sphere radii): the dart's
RB = 0.030                 # body radius
NOSE = 0.30                # the nose cone, of L (red)
FIN0, FINR = 0.74, 2.0     # fins from 74% of L, out to FINR x RB (red)
FT = 0.30                  # fin half-thickness, x RB (an edge-on fin still shows)
FIN_ROOT = 0.7             # fins start inside the body (x RB), so they always join it
FLAME = 0.55               # flame length, of L, at FLICKER 1.0
FLICKER = (1.0, 0.8, 1.15, 0.9)     # the 4 frames' flame lengths (and widths)
N = 12                     # facets around the body

ROCKET = [(255, 0, 255),                                        # 0 transparent (key)
          (0, 0, 0),                                            # 1 outline
          (150, 150, 160), (185, 185, 195), (215, 215, 222),    # 2..6 body
          (238, 238, 242), (255, 255, 255),
          (160, 30, 35), (200, 45, 45), (230, 70, 60),          # 7..10 red trim
          (250, 100, 90),
          (170, 40, 0), (230, 90, 10), (255, 160, 30),          # 11..15 flame
          (255, 220, 90), (255, 250, 200)]
WHITE = list(range(2, 7))
RED = list(range(7, 11))
FLAME_IDX = {"outer": 12, "inner": 14, "core": 15}


def mesh(t, j, fl):
    """the rocket's triangles [(3 points, kind, ramp)] on ring t at screen
    azimuth j (nose at R_REP on the missile's line), with flame scale fl;
    and the nose and base points."""
    c, n, e = _axes(t, j)
    tip = rm.R_REP * c
    tris = []
    prof = [(NOSE * L * k / 6, RB * math.sqrt(k / 6) ** 0.9 if k else 0.0) for k in range(7)]
    prof.append((L, RB))

    def ring(s, r):
        return [tip + s * c + r * (math.cos(2 * math.pi * i / N) * n
                                   + math.sin(2 * math.pi * i / N) * e) for i in range(N)]
    rings = [ring(s, r) for s, r in prof]
    for a in range(len(rings) - 1):
        ramp = RED if prof[a + 1][0] <= NOSE * L + 1e-9 else WHITE
        for i in range(N):
            p0, p1 = rings[a][i], rings[a][(i + 1) % N]
            q0, q1 = rings[a + 1][i], rings[a + 1][(i + 1) % N]
            tris.append(([p0, q0, q1], "body", ramp))
            tris.append(([p0, q1, p1], "body", ramp))
    base = tip + L * c
    for i in range(N):
        tris.append(([base, rings[-1][i], rings[-1][(i + 1) % N]], "body", WHITE))
    for k in range(4):                          # side fins, FT x RB thick
        b = k * math.pi / 2
        d = math.cos(b) * n + math.sin(b) * e
        w = np.cross(c, d) * FT * RB
        for sgn in (-1, 1):
            f0 = tip + FIN0 * L * c + FIN_ROOT * RB * d + sgn * w
            f1 = tip + L * c + FIN_ROOT * RB * d + sgn * w
            f2 = tip + L * 1.04 * c + RB * FINR * d + sgn * w
            f3 = tip + (FIN0 + 0.12) * L * c + RB * FINR * d + sgn * w
            tris.append(([f0, f1, f2], "fin", RED))
            tris.append(([f0, f2, f3], "fin", RED))
        r1, r2 = tip + L * c + FIN_ROOT * RB * d, tip + L * 1.04 * c + RB * FINR * d
        tris.append(([r1 - w, r1 + w, r2 + w], "fin", RED))       # the trailing edge (seen
        tris.append(([r1 - w, r2 + w, r2 - w], "fin", RED))       # from behind: a bar)
        e2, e3 = (tip + L * 1.04 * c + RB * FINR * d, tip + (FIN0 + 0.12) * L * c + RB * FINR * d)
        tris.append(([e2 - w, e2 + w, e3 + w], "fin", RED))       # the fin's outer edge
        tris.append(([e2 - w, e3 + w, e3 - w], "fin", RED))
    for scale, kind, rr in ((1.0, "outer", 0.85), (0.62, "inner", 0.55), (0.32, "core", 0.32)):
        apex = base + FLAME * L * fl * scale * c
        r0 = RB * rr * (0.9 + 0.2 * fl)
        rim = [base + 0.01 * c + r0 * (math.cos(2 * math.pi * i / N) * n
                                       + math.sin(2 * math.pi * i / N) * e) for i in range(N)]
        for i in range(N):
            tris.append(([rim[i], rim[(i + 1) % N], apex], kind, None))
    return tris, tip, base


def _axes(t, j):
    a = 2 * math.pi * j / g.STEPS
    c = gm.world(1.0, t, j)                     # outward
    north = -np.array([math.cos(t) * math.sin(a), -math.sin(t), math.cos(t) * math.cos(a)])
    east = np.array([math.cos(a), 0.0, -math.sin(a)])
    return c, north, east


_FIT = []


def project_many(P, f):
    """gen_missiles.project for an array of points: [n, 2] screen px."""
    pos, fwd, right, up = g.camera()
    d = np.asarray(P) - pos
    z = d @ fwd
    scale, ox, oy = f
    return np.stack([ox + scale * (d @ right) / z, oy - scale * (d @ up) / z], -1)


def placement(t, j, box, box0, length):
    """(k, off, drawn): the screen scale and offset that put every frame's
    rocket in `box` (all 4 frames: the longest flame sets the room), and the
    body's drawn length in px. The body is the full-dome art's `length` x
    ART unless the rocket with its flame would not fit, as the dart's
    clamp did."""
    if not _FIT:
        _FIT.append(g.fit())
    f = _FIT[0]
    tris, tip, base = mesh(t, j, max(FLICKER))
    P0 = gm.project(tip, f)
    nominal = gm.DART_LEN * f[0] / P0[2]
    pts = project_many([p for tri, _, _ in tris for p in tri], f) - P0[:2]
    want = length * rm.ART / nominal
    room = box - 2 - 2                          # 1 px clear + the outline, each side
    ext = np.ptp(pts, axis=0).max()
    k = min(want, room / ext)
    lo, hi = pts.min(0) * k, pts.max(0) * k
    off = np.array([box / 2, box / 2]) - (lo + hi) / 2
    return k, off, nominal * k


def _raster(tris2d, depth, box, colours, zbuf, cbuf, painter=False):
    """fill triangles (screen px, already x SS) into the sample buffers:
    depth-tested (nearest wins) unless painter (later wins, depth kept as
    the nearest)."""
    H = box * SS
    for q, zq, col in zip(tris2d, depth, colours):
        x0, y0 = np.floor(q.min(0)).astype(int)
        x1, y1 = np.ceil(q.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, H - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        px, py = xs + 0.5, ys + 0.5
        (ax, ay), (bx, by), (cx, cy) = q
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        l0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
        l1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
        l2 = 1 - l0 - l1
        inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        z = l0 * zq[0] + l1 * zq[1] + l2 * zq[2]
        zs, cs = zbuf[y0:y1 + 1, x0:x1 + 1], cbuf[y0:y1 + 1, x0:x1 + 1]
        win = inside if painter else inside & (z < zs)
        cs[win] = col
        zs[inside] = np.minimum(zs[inside], z[inside])


def render_frame(t, j, box, k, off, fl):
    """one frame's indexed picture (box x box), z-buffered: the body and
    fins hide each other and the flame by depth (a rocket flying away from
    the camera shows its flame in front); the flame's three cones layer
    outer, inner, core. A pixel is the body's when most of its samples are
    body, so where the flame is behind the body every frame's body pixels
    are the same. The outline rings the body where nothing else is."""
    f = _FIT[0]
    pos, fwd = g.camera()[:2]
    tris, tip, base = mesh(t, j, fl)
    P0 = np.array(gm.project(tip, f)[:2])
    allw = np.array([p for tri, _, _ in tris for p in tri])
    allp = ((project_many(allw, f) - P0) * k + off) * SS
    alld = (allw - pos) @ fwd
    H = box * SS
    zb, cb = np.full((H, H), np.inf), np.zeros((H, H), np.uint8)
    zf, cf = np.full((H, H), np.inf), np.zeros((H, H), np.uint8)
    solid, sd, scol = [], [], []
    for i, (tri, kd, ramp) in enumerate(tris):
        if kd not in ("body", "fin"):
            continue
        P = np.array(tri)
        nrm = np.cross(P[1] - P[0], P[2] - P[0])
        ln = np.linalg.norm(nrm)
        if ln < 1e-12:
            continue
        nrm /= ln
        if nrm @ (pos - P.mean(0)) < 0:
            nrm = -nrm
        shade = max(0.0, float(nrm @ g.LIGHT)) * 0.8 + 0.2
        solid.append(allp[3 * i:3 * i + 3]); sd.append(alld[3 * i:3 * i + 3])
        scol.append(ramp[min(len(ramp) - 1, int(shade * len(ramp)))])
    _raster(solid, sd, box, scol, zb, cb)
    for kind in ("outer", "inner", "core"):
        ids = [i for i, (_, kd, _) in enumerate(tris) if kd == kind]
        _raster([allp[3 * i:3 * i + 3] for i in ids], [alld[3 * i:3 * i + 3] for i in ids], box,
                [FLAME_IDX[kind]] * len(ids), zf, cf, painter=True)
    body_wins = (cb > 0) & ((cf == 0) | (zb <= zf))
    flame_wins = (cf > 0) & ~body_wins
    samples = np.where(body_wins, cb, np.where(flame_wins, cf, 0)).astype(np.uint8)
    b = samples.reshape(box, SS, box, SS).transpose(0, 2, 1, 3).reshape(box, box, SS * SS)
    counts = np.stack([(b == i).sum(-1) for i in range(len(ROCKET))], -1)
    bc, fc = counts[..., 2:11].sum(-1), counts[..., 11:].sum(-1)
    thresh = SS * SS * 0.43
    bcol = (counts[..., 2:11].argmax(-1) + 2).astype(np.uint8)
    fcol = (counts[..., 11:].argmax(-1) + 11).astype(np.uint8)
    idx = np.zeros((box, box), np.uint8)
    both = bc + fc > thresh
    idx[both] = np.where(bc >= fc, bcol, fcol)[both]
    idx[bc > thresh] = bcol[bc > thresh]
    body = (idx >= 2) & (idx <= 10)
    pad = np.pad(body, 1)
    nb = pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
    idx[nb & (idx == 0)] = 1                    # the outline (not over the flame)
    return idx


def render_view(t, j, box, box0, length):
    """(frames [4 x box x box], tip (x, y), drawn length px)."""
    k, off, drawn = placement(t, j, box, box0, length)
    frames = [render_frame(t, j, box, k, off, fl) for fl in FLICKER]
    tx, ty = off                                 # the nose before snapping
    lit = np.argwhere(frames[0] >= 2)
    if len(lit):                                 # snap to the nearest body pixel
        dd = np.abs(lit[:, ::-1] - [tx, ty]).max(axis=1)
        i = int(dd.argmin())
        if dd[i] <= 3:
            tx, ty = lit[i, 1], lit[i, 0]
    return frames, (int(round(tx)), int(round(ty))), max(1, round(drawn))


def sheet(pictures, box):
    """[(frames)] -> the 64-px-wide sheet: tile row i = tile i's 4 frames."""
    cols = box // 16
    rows = []
    for frames in pictures:
        for r in range(cols):
            for c in range(cols):
                rows.append(np.hstack([fr[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] for fr in frames]))
    return np.vstack(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("header")
    ap.add_argument("--preview")
    args = ap.parse_args()
    th = gm.tables()["th"]
    flat = [c for rgb in ROCKET for c in rgb]

    bases, anchors, base, previews = [], [], rm.TILE_BASE, []
    assert base % FRAMES == 0
    for name, box, box0, length in rm.LEVELS:
        pics, anc = [], []
        for t in th:
            for v in range(rm.VIEWS):
                frames, tip, used = render_view(t, v * rm.STEP, box, box0, length)
                pics.append(frames)
                anc.append((tip[0], tip[1], used))
        im = Image.fromarray(sheet(pics, box), "P")
        im.putpalette(flat)
        im.save(os.path.join(args.outdir, f"mis_{name}.gif"))
        bases.append(base)
        anchors.append(anc)
        previews.append((box, pics))
        base += len(th) * rm.VIEWS * (box // 16) ** 2 * FRAMES
    ex = np.vstack([rm.quantize(rm.explosion(t), rm.EXPLOSION) for t in range(rm.EXPL_FRAMES)])
    im = Image.fromarray(ex, "P")
    im.putpalette([c for rgb in rm.EXPLOSION for c in rgb])
    im.save(os.path.join(args.outdir, "expl.gif"))
    if args.preview:
        k = len(th) // 2
        out = Image.new("RGB", (9 * 52, 3 * 52 * FRAMES), (40, 44, 60))
        for fi in range(FRAMES):
            for row, (box, pics) in enumerate(previews):
                for col, v in enumerate(range(0, 25, 3)):
                    p = Image.fromarray(pics[k * rm.VIEWS + v][fi], "P")
                    p.putpalette(flat)
                    p.info["transparency"] = 0
                    out.paste(p.convert("RGBA"), (col * 52 + (52 - box) // 2,
                                                  (fi * 3 + row) * 52 + (52 - box) // 2),
                              p.convert("RGBA"))
        out.resize((out.width * 2, out.height * 2), Image.NEAREST).save(args.preview)

    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/render_rockets.py: do not edit */\n#ifndef MISSILE_MAP_H\n#define MISSILE_MAP_H\n")
        w(f"#define MIS_VIEWS   {rm.VIEWS}      /* per ring: screen azimuth 0..180 deg, 7.5 deg apart */\n")
        w(f"#define MIS_LEVELS  {len(rm.LEVELS)}\n")
        w(f"#define MIS_FRAMES  {FRAMES}       /* the flame's flicker: LSPC 4-frame auto-animation */\n")
        w("/* per size: first tile, columns (= rows), body length (px) */\n")
        w("static const u16 mis_tile_base[MIS_LEVELS] = {" + ", ".join(map(str, bases)) + "};\n")
        w("static const u8 mis_cols[MIS_LEVELS] = {" + ", ".join(str(b // 16) for _, b, _, _ in rm.LEVELS) + "};\n")
        w("static const u8 mis_len[MIS_LEVELS] = {" + ", ".join(str(max(1, round(n * rm.ART))) for _, _, _, n in rm.LEVELS) + "};\n")
        w("/* frame 0 of the tile of size l, ring k, view v, column c, row r (frames\n"
          "   1..3 follow it; the LSPC's 4-frame auto-animation picks one):\n"
          "   mis_tile_base[l] + (((k * MIS_VIEWS + v) * cols + r) * cols + c) * MIS_FRAMES */\n")
        w("/* each picture's tip (the nose, px) and the body's length drawn (px; mis_len[size]\n"
          "   unless the rocket and its flame would not fit): [size][ring * MIS_VIEWS + view][x, y, length] */\n")
        w("static const u8 mis_tip[MIS_LEVELS][%d][3] = {\n" % (len(th) * rm.VIEWS))
        w(",\n".join("  {" + ", ".join("{%d, %d, %d}" % a for a in anc) + "}" for anc in anchors) + "\n};\n")
        w(f"#define EXPL_TILE_BASE {base}\n#define EXPL_FRAMES {rm.EXPL_FRAMES}\n#define EXPL_COLS {rm.EXPL_BOX // 16}\n")
        for name, pal in (("mis_pal", ROCKET), ("bul_pal", rm.BULLET), ("expl_pal", rm.EXPLOSION)):
            w(f"static const u16 {name}[16] = {{0x8000, " + ", ".join("0x%04x" % rm.neo(c) for c in pal[1:]) + "};\n")
        w("#endif\n")


if __name__ == "__main__":
    main()
