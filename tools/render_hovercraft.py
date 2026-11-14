#!/usr/bin/env python3
"""render_hovercraft.py SHEET.gif HEADER.h [--preview PNG]

The player: a cherry-red hovercraft styled like a 1950s finned automobile
crossed with a desert landspeeder (design: docs/superpowers/specs/
2026-10-28-hovercraft-design.md; approved mockup rounds 1-5, 10-28). It
has an open cockpit behind a wraparound windscreen, swept tail fins with
red tail lights, chrome trim and a cream side panel, and no thrusters. A
short cannon stands straight up at the craft's anchor (the cell centre,
where every bullet's line starts), and it fires a short laser bolt.

It replaces tools/render_spider.py and writes the same sheet layout and
header names, so the runtime's frame choice (Task S2) is unchanged:
each latitude view has SHIP_FRAMES (13) pictures: REST, 4 "WALK" (here the
hover bob), 4 JUMP (dip to the ground, launch nose-up, airborne, land), 4
"HEAVE" (here the recoil: the shot pushes the craft down, a muzzle flash,
then it rises back).

The bolt replaces the fireball: BOLT_ANGLES (32) pictures of a short streak
at 11.25-degree steps, BOLT_FRAMES (2) shimmer frames each, one 16 x 16
tile per picture, in the craft's palette (13 red edge, 14 orange, 15 the
white-yellow core). A bullet flies its cell's outward line, and that line's
direction on screen depends on the bullet's ring and screen azimuth, so
bolt_angle[ring][q48] picks the picture (q48 = ((phi + dome_angle) % 240 +
2) / 5 % 48, the missile views' azimuth step before mirroring). The bolt
is placed by its HEAD: bolt_head[angle] is the head's pixel in the tile,
which goes on the bullet's point (the same point the old dart's tip used),
so the streak trails back toward the craft.

The muzzle stands SHIP_MUZZLE_R above the cell (R units: 2^19 per sphere
radius, measured from the sphere's centre like BUL_R0), and a bolt is
BOLT_LEN_R long. The runtime draws a bolt only once its tail is above the
muzzle (head r >= SHIP_MUZZLE_R + BOLT_LEN_R), so it appears above the
cannon, never inside it (the user's call, round 4).

The pictures are rendered in 3D on the game's own camera and light
(geometry.py), point-splatted at 4x, coloured from per-part shade ramps,
and given a 1-px black outline.

The craft faces the way it moves (10-28): SHIP_HEADINGS (8) headings, one
per stick direction, heading h = d / 4 for ship_dir's d (0 right, 8 up, 16
left, 24 down), so h 0 right, 1 up-right, 2 up, ... 7 down-right. Heading h
yaws the craft 90 - 45 h degrees from the dome's up-slope direction (yaw 0
points up the dome, 90 right). Every heading has the full 48 x 13 pictures.
To fit every heading's every pose in 32 x 32 (the up and down headings are
the tallest low on the dome), the scale is K 1.45 (was 1.60).

The sheet is 8 headings side by side (256 px wide: GIF images stop at 65535
px, and 8 x 48 x 13 pictures in one 32-px column would not fit), so with
tiletool's row-major tile order heading h, picture b = v * 13 + f, column
c, row r is tile SHIP_TILE_BASE + (b * 2 + r) * 16 + h * 2 + c. The 64 bolt
tiles follow below, 16 per 16-px row: bolt tile i is SHIP_BOLT_TILE + i.

HEADER (build/ship_map.h): the spider's names, with a heading index first
  SHIP_VIEWS, SHIP_FRAMES, SHIP_COLS, SHIP_ROWS, SHIP_TILE_BASE, SHIP_OX,
  SHIP_F_REST, SHIP_F_WALK, SHIP_F_JUMP, SHIP_F_HEAVE,
  SHIP_HEADINGS,
  ship_tile[h][v][c][r], ship_anim_tile[h][v][f][c][r], ship_oy[h][v]
plus the bolt's
  SHIP_BOLT_TILE, BOLT_ANGLES, BOLT_FRAMES   tile of angle a, frame k:
                                            SHIP_BOLT_TILE + a * BOLT_FRAMES + k
  bolt_head[BOLT_ANGLES][2]                 the head pixel (x, y) in the tile
  bolt_angle[MIS_RINGS][48]                 the picture for ring, q48
  SHIP_MUZZLE_R, BOLT_LEN_R                 R units (2^19 per radius)
TILES (this module) is the part's tile count, for the parts after it."""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
import gen_missiles as gm  # noqa: E402
import render_dome as rd  # noqa: E402

_pts, _, _faces = g.build_mesh()
g.make_cells(_pts, _faces)                  # sets g.SHIP_MAX_DEG
FIT = g.fit()
SS = 4
LIGHT = rd.LIGHT
SIZE = 32
COLS = ROWS = SIZE // 16
OX = g.DOME_W // 2 - SIZE // 2              # sprite x in the dome box (centred)
TILE_BASE = rd.TILE_BASE + g.VIEWS * rd.COLS * rd.ROWS   # C ROM: right after the dome
FRAMES = 13
F_REST, F_WALK, F_JUMP, F_HEAVE = 0, 1, 5, 9
BOLT_ANGLES, BOLT_FRAMES = 32, 2
HEADINGS = 8                      # one per stick direction: h = d / 4 (0 right, 2 up, 4 left, 6 down)
TILES = HEADINGS * g.SHIP_STEPS * FRAMES * COLS * ROWS + BOLT_ANGLES * BOLT_FRAMES
R_UNIT = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "vectrex_missiles.json")))["r_unit"]

# the palette: 1..5 chrome and shadow, 6..8 cherry paint, 9..10 cream,
# 11..12 glass, 13..15 tail light / bolt / muzzle flash (red, orange, core)
BODY = (200, 30, 40)
PALETTE = np.array([(255, 0, 255),
                    (10, 10, 14), (60, 64, 74), (130, 136, 150), (200, 206, 220), (250, 252, 255)]
                   + [tuple(int(c * k) for c in BODY) for k in (0.45, 0.7, 1.0)]
                   + [(170, 160, 135), (235, 225, 195), (90, 150, 190), (190, 230, 250),
                      (200, 20, 20), (255, 140, 40), (255, 245, 170)], float)
RAMP = {0: [2, 3, 4, 5], 1: [6, 7, 8, 8], 2: [9, 10, 10, 5], 3: [11, 11, 12, 12],
        4: [15, 15, 15, 15], 5: [13, 13, 14, 14], 7: [1, 1, 2, 2]}

# the craft, in sphere radii
K = 1.45                          # the largest that fits every heading, view and pose in 32 x 32 with a clear border (10-28)


def heading_yaw(h):
    """the craft's yaw for heading h: 0 points up the dome, 90 degrees right"""
    return math.radians((90 - 45 * h) % 360)
L, W, H = 0.150 * K, 0.064 * K, 0.030 * K       # body length, width, height
FIN_H = 0.042 * K                 # tail fins
RIDE = 0.016 * K                  # the hull's underside above the dome
CANNON_Z = H * 0.90               # the cannon's foot on the deck (at the anchor)
CANNON_LEN = 0.0375 * K           # half the round-3 height (round 4)
MUZZLE_H = RIDE + CANNON_Z + CANNON_LEN          # above the cell, at rest
BODY_SHIFT = 0.10                 # the body forward of the anchor, x L: centres the craft on the anchor


# ---------------------------------------------------------------- geometry (local frame: z up, y toward the peak, x side)
def frame(theta):
    p = np.array([0.0, math.cos(theta), math.sin(theta)])
    f = np.array([0.0, math.sin(theta), -math.cos(theta)])
    s = np.cross(p, f)
    return p, f, s


def to_world(P, theta):
    p, f, s = frame(theta)
    return p + P[:, 0:1] * s + P[:, 1:2] * f + P[:, 2:3] * p


def superellipsoid(a, b, c, e, n, zmin=None):
    u = np.random.default_rng(1).normal(size=(n, 3))
    u /= np.linalg.norm(u, axis=1, keepdims=True)
    P = np.sign(u) * np.abs(u) ** e * [a, b, c]
    N = np.sign(u) * np.abs(u) ** (2 - e) / np.array([a, b, c])
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    if zmin is not None:
        k = P[:, 2] >= zmin
        P, N = P[k], N[k]
    return P, N


def plate(p0, p1, p2, p3, nrm, n=900):
    r = np.random.default_rng(2).random((n, 2))
    P = (1 - r[:, :1]) * ((1 - r[:, 1:]) * p0 + r[:, 1:] * p1) + r[:, :1] * ((1 - r[:, 1:]) * p3 + r[:, 1:] * p2)
    return np.concatenate([P, P]), np.concatenate([np.tile(nrm, (n, 1)), -np.tile(nrm, (n, 1))])


def craft(pose, yaw):
    """pose: dict(ride, pitch, recoil 0..1, flash 0..1). Returns local
    (P, N, kind): kinds 0 chrome, 1 paint, 2 cream, 3 glass, 4 muzzle flash,
    5 tail light, 7 cockpit."""
    ride, pitch = pose['ride'], pose.get('pitch', 0.0)
    parts = []
    P, N = superellipsoid(W / 2, L / 2, H / 2, 0.35, 9000)
    P = P + [0, 0, H / 2]
    side = np.abs(P[:, 0]) > W * 0.40
    cove = side & (P[:, 2] > H * 0.15) & (P[:, 2] < H * 0.50) & (P[:, 1] > -L * 0.40) & (P[:, 1] < L * 0.20)
    kind = np.where(cove, 2, 1)                                        # the cream side panel
    kind = np.where(side & (np.abs(P[:, 2] - H * 0.56) < H * 0.06), 0, kind)   # the chrome spear
    kind = np.where((np.abs(P[:, 1]) > L * 0.47) & (P[:, 2] < H * 0.45), 0, kind)   # bumpers
    pit = (P[:, 2] > H * 0.75) & (np.abs(P[:, 0]) < W * 0.34) & (P[:, 1] > L * 0.04) & (P[:, 1] < L * 0.25)
    kind = np.where(pit, 7, kind)                                      # the open cockpit
    parts.append((P, N, kind))
    for sx in (-1, 1):                                                 # the tail fins
        x = sx * W * 0.46
        p0 = np.array([x, -L * 0.15, H * 0.9]); p1 = np.array([x, -L * 0.50, H * 0.9])
        p2 = np.array([x + sx * W * 0.06, -L * 0.58, H + FIN_H]); p3 = np.array([x + sx * W * 0.02, -L * 0.42, H + FIN_H * 0.7])
        P, N = plate(p0, p1, p2, p3, np.array([1.0, 0, 0]))
        parts.append((P, N, np.where(P[:, 2] > H + FIN_H * 0.55, 0, 1)))
        tl = np.array([x + sx * W * 0.04, -L * 0.56, H + FIN_H * 0.55])   # the tail light
        u = np.random.default_rng(5).normal(size=(300, 3)); u /= np.linalg.norm(u, axis=1, keepdims=True)
        parts.append((tl + u * 0.006, u, np.full(300, 5)))
    P, N = superellipsoid(W * 0.36, L * 0.07, H * 0.42, 0.6, 2000, zmin=0)   # the windscreen
    parts.append((P + [0, L * 0.30, H * 0.95], N, np.full(len(P), 3)))
    # the body sits BODY_SHIFT x L forward of the anchor (the cannon's foot,
    # the bullets' line), which centres the craft on the anchor on screen
    parts = [(P + [0, BODY_SHIFT * L, 0], N, k) for P, N, k in parts]
    rec = pose.get('recoil', 0.0)                                      # the cannon, straight up
    t = np.linspace(0, 1, 60); a = np.linspace(0, 2 * math.pi, 10, endpoint=False)
    T, A = np.meshgrid(t, a)
    r = 0.0085 * K * (1 - 0.25 * T)
    ln = CANNON_LEN * (1 - 0.15 * rec)
    Pc = np.stack([r * np.cos(A), r * np.sin(A), T * ln], -1).reshape(-1, 3)
    Nc = np.stack([np.cos(A), np.sin(A), np.zeros_like(A)], -1).reshape(-1, 3)
    base = np.array([0, 0.0, CANNON_Z])
    parts.append((Pc + base, Nc, np.full(len(Pc), 0)))
    if pose.get('flash'):
        u = np.random.default_rng(6).normal(size=(500, 3)); u /= np.linalg.norm(u, axis=1, keepdims=True)
        parts.append((base + [0, 0, ln] + u * 0.010 * K * pose['flash'], u, np.full(500, 4)))
    P = np.concatenate([p for p, _, _ in parts]); N = np.concatenate([n for _, n, _ in parts])
    Kk = np.concatenate([k for _, _, k in parts])
    cp, sp = math.cos(pitch), math.sin(pitch)
    Rp = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    cy, sy = math.cos(yaw), math.sin(yaw)
    Ry = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    P = P @ Rp.T @ Ry.T; N = N @ Rp.T @ Ry.T
    P[:, 2] += ride
    return P, N, Kk


def render(pose, theta, oy=None, box=None, yaw=heading_yaw(1)):
    """(indices B x B, sprite top-left in the dome box) at latitude theta."""
    P, N, Kk = craft(pose, yaw)
    p, f, s = frame(theta)
    Wd = to_world(P, theta)
    Nw = N[:, 0:1] * s + N[:, 1:2] * f + N[:, 2:3] * p
    raw, world = g.project(Wd, 0)
    px = g.to_px(raw, FIT)
    pos = g.camera()[0]
    view = pos - world; view /= np.linalg.norm(view, axis=1, keepdims=True)
    face = (Nw * view).sum(1) > -0.05
    c = g.to_px(g.project(p[None], 0)[0], FIT)[0]
    B = SIZE if box is None else box
    ox = int(round(c[0] - SIZE / 2)) - (B - SIZE) // 2
    if oy is None:
        oy = int(round(c[1] - B / 2))
    # sink: a screen-space push down (px), so the jump's dip and the recoil
    # read at every latitude (low on the dome the surface normal points at
    # the camera, and a 3D drop alone barely moves the picture)
    sink = pose.get('sink', 0)
    xs = ((px[:, 0] - ox) * SS).astype(int); ys = ((px[:, 1] + sink - oy) * SS).astype(int)
    z = np.linalg.norm(world - pos, axis=1)
    lam = np.clip(Nw @ LIGHT, 0, 1)
    h = LIGHT + view; h /= np.linalg.norm(h, axis=1, keepdims=True)
    spec = np.clip((Nw * h).sum(1), 0, 1) ** 16
    shade = np.clip(0.25 + 0.75 * lam + 0.8 * spec, 0, 1.2)
    idxs = np.zeros(len(Kk), np.uint8)
    for k, ramp in RAMP.items():
        m = Kk == k
        idxs[m] = np.array(ramp)[np.clip((shade[m] * len(ramp)).astype(int), 0, len(ramp) - 1)]
    keep = face | np.isin(Kk, [4, 5])
    order = np.argsort(-z[keep])                # far to near: the nearest point wins
    xs, ys, ii = xs[keep][order], ys[keep][order], idxs[keep][order]
    grid = np.zeros((B * SS, B * SS), np.uint8)
    for dx in range(SS // 2 + 1):
        for dy in range(SS // 2 + 1):
            X, Y = xs + dx - 1, ys + dy - 1
            ok = (X >= 0) & (X < B * SS) & (Y >= 0) & (Y < B * SS)
            grid[Y[ok], X[ok]] = ii[ok]
    b = grid.reshape(B, SS, B, SS).transpose(0, 2, 1, 3).reshape(B, B, SS * SS)
    counts = np.stack([(b == i).sum(-1) for i in range(16)], -1)
    out = (counts[..., 1:].argmax(-1) + 1).astype(np.uint8)
    out[(SS * SS - counts[..., 0]) < SS * SS * 0.34] = 0
    m = out > 0; pad = np.pad(m, 1)               # the outline
    out[(pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]) & ~m] = 1
    return out, (ox, oy)


# ---------------------------------------------------------------- the poses
POSE_REST = dict(ride=RIDE)
HOVER = [dict(ride=RIDE * (1 + 0.25 * math.sin(2 * math.pi * k / 4)), pitch=0.04 * math.cos(2 * math.pi * k / 4))
         for k in range(4)]
JUMP = [dict(ride=RIDE * 0.15, sink=2),            # dips to the ground
        dict(ride=RIDE * 1.4, pitch=0.18, sink=-1),  # launches nose-up
        dict(ride=RIDE * 1.8, pitch=0.05),         # airborne
        dict(ride=RIDE * 0.6, pitch=-0.05)]        # lands
RECOIL = [dict(ride=RIDE * 0.55, recoil=1.0, flash=1.0, pitch=-0.06, sink=2),   # the shot pushes it down
          dict(ride=RIDE * 0.65, recoil=0.6, flash=0.5, sink=1),
          dict(ride=RIDE * 0.85, recoil=0.25),
          dict(ride=RIDE, recoil=0.0)]


def pose_of(f):
    if f == F_REST:
        return POSE_REST
    if f < F_JUMP:
        return HOVER[f - F_WALK]
    if f < F_HEAVE:
        return JUMP[f - F_JUMP]
    return RECOIL[f - F_HEAVE]


# ---------------------------------------------------------------- the bolt
BOLT_HALF = [(5.5 + 0.6 * k) * 2 / 3 for k in range(BOLT_FRAMES)]   # px: 2/3 of round 4's (round 5)
BOLT_RADII = ((2.1, 13), (1.4, 14), (0.75, 15))                       # edge red, orange, core


def bolt(a, k, n=16):
    """(16 x 16 indices, head pixel): the streak at picture angle a (0 =
    pointing right, increasing clockwise on screen), shimmer frame k."""
    t = 2 * math.pi * a / BOLT_ANGLES
    yy, xx = np.mgrid[0:n * SS, 0:n * SS] / SS - n / 2 + 0.5 / SS
    u = xx * math.cos(t) + yy * math.sin(t)
    v = -xx * math.sin(t) + yy * math.cos(t)
    d = np.sqrt(np.maximum(0, np.abs(u) - BOLT_HALF[k]) ** 2 + v ** 2)
    big = np.zeros((n * SS, n * SS), np.uint8)
    for rad, idx in BOLT_RADII:
        big[d < rad] = idx
    b = big.reshape(n, SS, n, SS).transpose(0, 2, 1, 3).reshape(n, n, SS * SS)
    cov = (b > 0).mean(-1)
    out = np.where(cov > 0.3, b.max(-1), 0).astype(np.uint8)
    hx = n / 2 - 0.5 + math.cos(t) * BOLT_HALF[0]
    hy = n / 2 - 0.5 + math.sin(t) * BOLT_HALF[0]
    return out, (int(round(hx)), int(round(hy)))


def bolt_angles():
    """[ring][q48] -> the picture whose angle is nearest the bullet line's
    direction on screen (outward), taken between 1.2 and 1.6 radii."""
    th = gm.tables()["th"]
    out = []
    for t in th:
        row = []
        for q in range(48):
            j = q * 5
            a = gm.project(gm.world(1.2, t, j), FIT)
            b = gm.project(gm.world(1.6, t, j), FIT)
            if a is None or b is None:
                row.append(0)
                continue
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            row.append(int(round(ang / (2 * math.pi) * BOLT_ANGLES)) % BOLT_ANGLES)
        out.append(row)
    return out


def bolt_len_r():
    """the bolt's length on screen at the ship's start latitude, in R units
    (along the cell's outward line there)."""
    th = math.radians(g.SHIP_MAX_DEG) * 0.5
    p = frame(th)[0]
    a = g.to_px(g.project(np.array([p * 1.0, p * 1.1]), 0)[0], FIT)
    px_per_radius = np.linalg.norm(a[1] - a[0]) / 0.1
    length_px = 2 * (BOLT_HALF[0] + BOLT_RADII[0][0])
    return int(round(length_px / px_per_radius * R_UNIT))


# ---------------------------------------------------------------- the sheet
def views(yaw):
    """[(theta, sprite y)] per latitude view at one heading's yaw, each
    view's 13 pictures centred vertically in the 32-px sprite (measured in
    a 64-px box)."""
    out = []
    for i in range(g.SHIP_STEPS):
        theta = math.radians(g.SHIP_MAX_DEG) * i / (g.SHIP_STEPS - 1)
        top, bot = 999, -1
        for f in range(FRAMES):
            idx, (_, oy64) = render(pose_of(f), theta, box=64, yaw=yaw)
            ys = np.nonzero(idx.any(1))[0]
            top, bot = min(top, oy64 + ys[0]), max(bot, oy64 + ys[-1])
        assert bot - top + 1 <= SIZE - 2, (i, top, bot)
        out.append((theta, (top + bot + 1) // 2 - SIZE // 2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("header")
    ap.add_argument("--preview")
    args = ap.parse_args()

    vss = [views(heading_yaw(hd)) for hd in range(HEADINGS)]
    nb = g.SHIP_STEPS * FRAMES
    nbolt = BOLT_ANGLES * BOLT_FRAMES
    WIDE = HEADINGS * SIZE                      # 8 headings side by side
    per_row = WIDE // 16                        # bolt tiles per 16-px row
    sheet = np.zeros((SIZE * nb + 16 * ((nbolt + per_row - 1) // per_row), WIDE), np.uint8)
    for hd, vs in enumerate(vss):
        for v, (theta, oy) in enumerate(vs):
            for f in range(FRAMES):
                idx, (ox, _) = render(pose_of(f), theta, oy=oy, yaw=heading_yaw(hd))
                assert ox == OX, (hd, v, ox, OX)
                assert not (idx[0].any() or idx[-1].any() or idx[:, 0].any() or idx[:, -1].any()), (hd, v, f)
                b = v * FRAMES + f
                sheet[b * SIZE:(b + 1) * SIZE, hd * SIZE:(hd + 1) * SIZE] = idx
    heads = []
    y0 = SIZE * nb
    for a in range(BOLT_ANGLES):
        for k in range(BOLT_FRAMES):
            pic, head = bolt(a, k)
            i = a * BOLT_FRAMES + k
            sheet[y0 + (i // per_row) * 16:y0 + (i // per_row) * 16 + 16,
                  (i % per_row) * 16:(i % per_row) * 16 + 16] = pic
            if k == 0:
                heads.append(head)
    im = Image.fromarray(sheet, "P")
    flat = [int(c) for rgb in PALETTE for c in rgb]
    im.putpalette(flat)
    im.save(args.sheet)
    if args.preview:
        strip = np.vstack([np.hstack([sheet[(v * FRAMES + f) * SIZE:(v * FRAMES + f + 1) * SIZE]
                                      for f in range(FRAMES)]) for v in (0, 24, 47)])
        pv = Image.fromarray(strip, "P")
        pv.putpalette(flat)
        pv.convert("RGB").resize((strip.shape[1] * 3, strip.shape[0] * 3), Image.NEAREST).save(args.preview)

    def tile(hd, b, c, r):
        return TILE_BASE + (b * ROWS + r) * (WIDE // 16) + hd * COLS + c

    ang = bolt_angles()
    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/render_hovercraft.py: do not edit */\n"
          f"#define SHIP_HEADINGS {HEADINGS}   /* h = ship_dir / 4: 0 right, 2 up, 4 left, 6 down */\n"
          f"#define SHIP_VIEWS {g.SHIP_STEPS}\n#define SHIP_FRAMES {FRAMES}\n"
          f"#define SHIP_COLS {COLS}\n#define SHIP_ROWS {ROWS}\n#define SHIP_TILE_BASE {TILE_BASE}\n"
          f"#define SHIP_OX {OX}      /* sprite x in the dome box */\n"
          f"#define SHIP_F_REST {F_REST}\n#define SHIP_F_WALK {F_WALK}   /* 4: the hover bob */\n"
          f"#define SHIP_F_JUMP {F_JUMP}   /* 4: dip, launch, airborne, land */\n"
          f"#define SHIP_F_HEAVE {F_HEAVE}  /* 4: the recoil (flash, down, rising, rest) */\n"
          f"#define SHIP_BOLT_TILE {TILE_BASE + HEADINGS * nb * 4}\n"
          f"#define BOLT_ANGLES {BOLT_ANGLES}\n#define BOLT_FRAMES {BOLT_FRAMES}\n"
          f"#define SHIP_MUZZLE_R {int(round((1 + MUZZLE_H) * R_UNIT))}   /* the muzzle, from the sphere's centre */\n"
          f"#define BOLT_LEN_R {bolt_len_r()}\n"
          "/* tile number of heading h, latitude view v's REST picture, column c, row r */\n"
          "static const u16 ship_tile[SHIP_HEADINGS][SHIP_VIEWS][SHIP_COLS][SHIP_ROWS] = {\n")
        for hd in range(HEADINGS):
            w(" {\n")
            for v in range(g.SHIP_STEPS):
                b = v * FRAMES + F_REST
                w("  {" + ",".join("{" + ",".join(str(tile(hd, b, c, r)) for r in range(ROWS)) + "}" for c in range(COLS)) + "},\n")
            w(" },\n")
        w("};\n/* every picture: [heading][view][frame][column][row] */\n"
          "static const u16 ship_anim_tile[SHIP_HEADINGS][SHIP_VIEWS][SHIP_FRAMES][SHIP_COLS][SHIP_ROWS] = {\n")
        for hd in range(HEADINGS):
            w(" {\n")
            for v in range(g.SHIP_STEPS):
                w("  {" + ",".join("{" + ",".join("{" + ",".join(str(tile(hd, v * FRAMES + f, c, r)) for r in range(ROWS)) + "}"
                                              for c in range(COLS)) + "}" for f in range(FRAMES)) + "},\n")
            w(" },\n")
        w("};\n/* sprite y in the dome box, per heading and latitude view */\n"
          "static const s16 ship_oy[SHIP_HEADINGS][SHIP_VIEWS] = {\n" +
          ",\n".join("  {" + ", ".join(str(oy) for _, oy in vs) + "}" for vs in vss) + "\n};\n")
        w("/* the bolt's head pixel (x, y) in its tile, per picture angle */\n"
          f"static const u8 bolt_head[BOLT_ANGLES][2] = {{" + ", ".join("{%d,%d}" % hd for hd in heads) + "};\n")
        w(f"/* the bolt picture for a bullet on ring k at screen azimuth step q48 */\n"
          f"static const u8 bolt_angle[{len(ang)}][48] = {{\n" + ",\n".join("  {" + ",".join(map(str, row)) + "}" for row in ang) + "\n};\n")


if __name__ == "__main__":
    main()
