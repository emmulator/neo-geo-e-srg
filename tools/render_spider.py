#!/usr/bin/env python3
"""render_spider.py SHEET.gif HEADER.h [--preview PNG]

The player: a metallic-black, mechanical six-legged spider whose body is an
upside-down bottle stopper's shape (a ribbed cap, a hollow banded stalk that
leans up the dome like a mortar, a furnace glowing inside it), and its
molten fireball shot (design: docs/superpowers/specs/
2026-10-26-stopper-spider-design.md; approved mockup 10-26). It replaces the
Vectrex's pyramid at the same place and scale: a 32 x 32 sprite (2 x 2
tiles) on the dome's front meridian, one view per latitude (the ship only
ever changes latitude: the dome turns under it).

Each latitude view has SHIP_FRAMES pictures: REST, 4 WALK (a tripod gait),
4 JUMP (scrunch, launch, airborne, land), 4 HEAVE (the stalk squeezes,
lurches and spits as the furnace flares, then settles). The fireball is 4
churning 16 x 16 pictures (one tile each) in the same 16-colour palette.

The pictures are rendered in 3D on the game's own camera and light
(geometry.py), point-splatted at 4x and box-filtered, quantized to PALETTE.

HEADER (build/ship_map.h):
  SHIP_VIEWS, SHIP_FRAMES, SHIP_COLS, SHIP_ROWS, SHIP_TILE_BASE, SHIP_OX
  SHIP_F_REST, SHIP_F_WALK, SHIP_F_JUMP, SHIP_F_HEAVE (first frame of each)
  ship_tile[SHIP_VIEWS][SHIP_COLS][SHIP_ROWS]     the REST pictures (the
                                                   runtime's table until the
                                                   animation lands)
  ship_anim_tile[SHIP_VIEWS][SHIP_FRAMES][SHIP_COLS][SHIP_ROWS]
  ship_oy[SHIP_VIEWS]                              sprite y in the dome box
  SHIP_FIREBALL_TILE, SHIP_FIREBALL_FRAMES        the fireball's 4 tiles
TILES (this module) is the part's tile count, for the parts after it."""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402
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
FIREBALL_FRAMES = 4
TILES = g.SHIP_STEPS * FRAMES * COLS * ROWS + FIREBALL_FRAMES
REST_GLOW = 0.1

# the palette: 1..8 gun-metal, black to highlight (cool), 9..15 the furnace
PALETTE = np.array([(255, 0, 255),
                (8, 9, 12), (18, 20, 26), (30, 33, 42), (46, 50, 62), (68, 74, 90),
                (100, 108, 128), (150, 160, 182), (215, 225, 240),
                (70, 12, 6), (130, 26, 8), (196, 58, 10), (240, 110, 20),
                (255, 170, 50), (255, 222, 120), (255, 252, 220)], float)
METAL = list(range(1, 9)); GLOW = list(range(9, 16))


# ---------------------------------------------------------------- geometry (local frame: n up, f toward the peak, s side)
def frame(theta):
    p = np.array([0.0, math.cos(theta), math.sin(theta)])
    f = np.array([0.0, math.sin(theta), -math.cos(theta)])
    s = np.cross(p, f)
    return p, f, s


def cyl(r0, r1, h0, h1, ribs=0, n_a=96, n_h=14, inward=False):
    """points/normals of a (tapered) cylinder wall around n, in local
    coords (x side, y fwd, z up)."""
    a = np.linspace(0, 2 * math.pi, n_a, endpoint=False)
    t = np.linspace(0, 1, n_h)
    A, T = np.meshgrid(a, t)
    r = r0 + (r1 - r0) * T
    if ribs:
        r = r * (1 + 0.06 * np.maximum(0, np.cos(ribs * A)) ** 3)
    x, y, z = r * np.cos(A), r * np.sin(A), h0 + (h1 - h0) * T
    nx, ny = np.cos(A), np.sin(A)
    if ribs:
        k = -0.35 * np.sin(ribs * A)
        nx, ny = nx - k * np.sin(A), ny + k * np.cos(A)
    nz = np.full_like(x, (r0 - r1) / max(1e-6, abs(h1 - h0)) * 0.6)
    N = np.stack([nx, ny, nz], -1); N /= np.linalg.norm(N, axis=-1, keepdims=True)
    if inward:
        N = -N
    return np.stack([x, y, z], -1).reshape(-1, 3), N.reshape(-1, 3)


def disc(r_in, r_out, h, up=True, n_a=96, n_r=8):
    a = np.linspace(0, 2 * math.pi, n_a, endpoint=False)
    rr = np.linspace(r_in, r_out, n_r)
    A, RR = np.meshgrid(a, rr)
    P = np.stack([RR * np.cos(A), RR * np.sin(A), np.full_like(A, h)], -1).reshape(-1, 3)
    N = np.tile([0, 0, 1.0 if up else -1.0], (len(P), 1))
    return P, N


def tube(a, b, r, n=40, n_a=10):
    """a thin limb from a to b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a; L = np.linalg.norm(d); d /= L
    u = np.cross(d, [0, 0, 1.0]);
    if np.linalg.norm(u) < 1e-3: u = np.cross(d, [1.0, 0, 0])
    u /= np.linalg.norm(u); v = np.cross(d, u)
    t = np.linspace(0, 1, n); ang = np.linspace(0, 2 * math.pi, n_a, endpoint=False)
    T, AN = np.meshgrid(t, ang)
    N = np.cos(AN)[..., None] * u + np.sin(AN)[..., None] * v
    P = a + T[..., None] * (b - a) + r * N
    return P.reshape(-1, 3), N.reshape(-1, 3)


# the body, in sphere radii (the old ship was 0.15 long, 0.09 tall)
K_ = 1.28                         # the whole creature, to fill the 32-px box
CAP_R, CAP_H = 0.050 * K_, 0.026 * K_   # the flared, ribbed cap (the spider's body)
STALK_R, STALK_H = 0.030 * K_, 0.046 * K_   # the hollow stalk
RIDE = 0.022 * K_                 # the body's underside above the dome
HIP_R, KNEE_R, FOOT_R = 0.046 * K_, 0.085 * K_, 0.105 * K_
TILT = math.radians(50)           # the stalk leans up the dome, like a mortar


def spider(pose):
    """pose: dict(ride, legs=[(knee_up, foot_r, foot_lift, swing)]*6,
    stalk=(squash, widen), glow=0..1). Returns (P, N, kind) local points."""
    ride = pose['ride']
    sq, wd = pose['stalk']
    parts = []
    # the cap: a ribbed flared wall, its top ring, its underside
    P, N = cyl(CAP_R * 1.12, CAP_R, ride, ride + CAP_H, ribs=18); parts.append((P, N, 0))
    P, N = disc(STALK_R * wd * 1.1, CAP_R, ride + CAP_H); parts.append((P, N, 0))
    P, N = disc(0, CAP_R * 1.12, ride, up=False); parts.append((P, N, 0))
    # the stalk: banded, slightly tapered, hollow; built upright from 0,
    # then leaned TILT toward the peak and set on the cap's top
    st = []
    h1 = STALK_H * sq
    P, N = cyl(STALK_R * wd, STALK_R * wd * 0.92, 0, h1, n_h=18); st.append((P, N, 0))
    heat = pose.get('heat', 0)
    for k in (0.3, 0.6):
        P, N = cyl(STALK_R * wd * 1.07, STALK_R * wd * 1.07, h1 * k, h1 * k + 0.005, n_h=3)
        st.append((P, N, 1 if heat else 0))                 # the bands glow when heated
    spit = pose.get('spit', 0.0)
    if spit:                                                # a molten blob bulging from the muzzle
        u = np.random.default_rng(3).normal(size=(600, 3)); u /= np.linalg.norm(u, axis=1, keepdims=True)
        u = np.concatenate([u, u * np.array([-1, 1, 1])])        # mirrored: a symmetric silhouette
        st.append((u * spit + np.array([0, 0, h1 + spit * 1.1]), u, 3))
    P, N = disc(STALK_R * wd * 0.70, STALK_R * wd * 0.92, h1); st.append((P, N, 0))       # the lip
    P, N = disc(0, STALK_R * wd * 0.70, h1 - 0.014); st.append((P, N, 2))               # the furnace
    P, N = cyl(STALK_R * wd * 0.70, STALK_R * wd * 0.70, h1 - 0.014, h1, inward=True, n_h=5); st.append((P, N, 1))
    ct, stn = math.cos(TILT), math.sin(TILT)
    Rm = np.array([[1, 0, 0], [0, ct, -stn], [0, stn, ct]])     # z -> (0, sin, cos): toward the peak
    base = np.array([0, -CAP_R * 0.15, ride + CAP_H * 0.85])
    for P, N, k in st:
        parts.append((P @ Rm + base, N @ Rm, k))
    P, N = disc(0, STALK_R * wd * 1.1, ride + CAP_H); parts.append((P, N, 0))           # the cap's top
    # six legs: hip on the cap's rim, knee up and out, foot on the dome
    for i, (kup, fr, lift, swing) in enumerate(pose['legs']):
        a = math.radians(30 + 60 * i) + swing
        ca, sa = math.cos(a), math.sin(a)
        hip = (HIP_R * ca, HIP_R * sa, ride + CAP_H * 0.45)
        knee_r = (HIP_R + fr) / 2 * 1.05
        knee = (knee_r * ca, knee_r * sa, ride + CAP_H * 0.45 + kup)
        foot = (fr * ca, fr * sa, lift)
        for (q0, q1, rad) in ((hip, knee, 0.0065), (knee, foot, 0.0045)):
            P, N = tube(q0, q1, rad); parts.append((P, N, 0))
    P = np.concatenate([p for p, _, _ in parts]); N = np.concatenate([n for _, n, _ in parts])
    K = np.concatenate([np.full(len(p), k) for p, _, k in parts])
    return P, N, K


def to_world(P, theta):
    p, f, s = frame(theta)
    return p + P[:, 0:1] * s + P[:, 1:2] * f + P[:, 2:3] * p


def render(pose, theta, glow=0.0, oy=None, box=None):
    """(32x32 indices, sprite top-left in the dome box, z-sorted) at latitude theta."""
    P, N, K = spider(pose)
    p, f, s = frame(theta)
    W = to_world(P, theta)
    Nw = N[:, 0:1] * s + N[:, 1:2] * f + N[:, 2:3] * p
    raw, world = g.project(W, 0)
    px = g.to_px(raw, FIT)
    pos = g.camera()[0]
    view = pos - world; view /= np.linalg.norm(view, axis=1, keepdims=True)
    face = (Nw * view).sum(1) > -0.05
    # the sprite's box: centred on the foot point like the old ship
    c = g.to_px(g.project(p[None], 0)[0], FIT)[0]
    B = SIZE if box is None else box
    ox = int(round(c[0] - SIZE / 2)) - (B - SIZE) // 2
    if oy is None:
        oy = int(round(c[1] - B / 2))
    buf = np.full((B * SS, B * SS), 1e9); col = np.zeros((B * SS, B * SS, 3)); hit = np.zeros((B * SS, B * SS), bool)
    xs = ((px[:, 0] - ox) * SS).astype(int); ys = ((px[:, 1] - oy) * SS).astype(int)
    z = np.linalg.norm(world - pos, axis=1)
    # shading: metal = dark base + sharp specular + a cool rim; glow = emissive
    lam = np.clip((Nw @ LIGHT), 0, 1)
    h = LIGHT + view; h /= np.linalg.norm(h, axis=1, keepdims=True)
    spec = np.clip((Nw * h).sum(1), 0, 1) ** 14
    rim = np.clip(1 - (Nw * view).sum(1), 0, 1) ** 2
    # a sprite key light from the camera's upper left (the hardware has
    # no lights: this is the art's own sheen, like the dome's edge glow)
    key = np.array(g.camera()[3]) * 0.7 - np.array(g.camera()[2]) * 0.5 + view * 0.6
    key /= np.linalg.norm(key, axis=1, keepdims=True)
    hk = key + view; hk /= np.linalg.norm(hk, axis=1, keepdims=True)
    spec2 = np.clip((Nw * hk).sum(1), 0, 1) ** 20
    metal = 0.05 + 0.20 * lam + 0.75 * spec + 0.9 * spec2 + 0.45 * rim
    # far to near: numpy's fancy assignment keeps the LAST write for a
    # repeated index, so the nearest point wins every sample
    keep = face | (K != 0)
    order = np.argsort(-z[keep])
    xs, ys, Kk = xs[keep][order], ys[keep][order], K[keep][order]
    mcol = (np.array([0.82, 0.88, 1.0]) * metal[keep][order][:, None] * 255)
    c1 = np.tile(PALETTE[10] * (0.6 + 0.5 * glow), (len(Kk), 1))
    c2 = np.tile(PALETTE[12] * (0.55 + 0.45 * glow) + PALETTE[15] * 0.4 * glow, (len(Kk), 1))
    c3 = np.tile(PALETTE[14] * 0.7 + PALETTE[15] * 0.3, (len(Kk), 1))
    cc = np.where((Kk == 0)[:, None], mcol, np.where((Kk == 1)[:, None], c1, np.where((Kk == 2)[:, None], c2, c3)))
    for dx in range(SS // 2 + 1):
        for dy in range(SS // 2 + 1):
            X, Y = xs + dx - 1, ys + dy - 1
            ok = (X >= 0) & (X < B * SS) & (Y >= 0) & (Y < B * SS)
            col[Y[ok], X[ok]] = cc[ok]
            hit[Y[ok], X[ok]] = True
    cov = hit.reshape(B, SS, B, SS).mean((1, 3))
    rgb = col.reshape(B, SS, B, SS, 3).sum((1, 3)) / np.maximum(1, hit.reshape(B, SS, B, SS).sum((1, 3)))[..., None]
    out = np.zeros((B, B), np.uint8)
    on = cov >= 0.34
    d = ((rgb[on][:, None, :] - PALETTE[None, 1:]) ** 2).sum(-1)
    out[on] = 1 + d.argmin(1)
    return out, (ox, oy)


# ---------------------------------------------------------------- the poses
def rest_legs(fr=FOOT_R, kup=0.030):
    return [(kup, fr, 0.0, 0.0)] * 6


def walk(k):
    """the tripod gait, 4 frames: legs 0,2,4 then 1,3,5 lift and swing."""
    legs = []
    for i in range(6):
        grp = i % 2
        ph = (k + 2 * grp) % 4               # 0 lift, 1 swing, 2 plant, 3 push
        lift = (0.020, 0.012, 0.0, 0.0)[ph]
        swing = math.radians((-10, 6, 12, -2)[ph])
        legs.append((0.030 + lift * 0.9, FOOT_R, lift, swing))
    return dict(ride=RIDE + (0.002 if k % 2 else 0.0), legs=legs, stalk=(1.0, 1.0))


JUMP = [dict(ride=RIDE * 0.35, legs=rest_legs(FOOT_R * 0.86, 0.042), stalk=(0.92, 1.05)),     # scrunch
        dict(ride=RIDE * 2.6, legs=[(0.004, FOOT_R * 0.78, RIDE * 1.1, 0.0)] * 6, stalk=(1.08, 0.97)),   # launch: legs long, trailing
        dict(ride=RIDE * 3.2, legs=[(0.012, FOOT_R * 1.10, RIDE * 2.0, 0.0)] * 6, stalk=(1.0, 1.0)),    # airborne: legs flung out
        dict(ride=RIDE * 0.5, legs=rest_legs(FOOT_R * 1.05, 0.040), stalk=(0.9, 1.06))]      # land, flexed
HEAVE = [dict(ride=RIDE, legs=rest_legs(), stalk=(1.0, 1.0)),
         dict(ride=RIDE * 0.75, legs=rest_legs(FOOT_R, 0.036), stalk=(0.72, 1.16), heat=1),    # squeeze down, the bands heat
         dict(ride=RIDE * 1.15, legs=rest_legs(FOOT_R, 0.026), stalk=(1.28, 0.9), heat=1,
              spit=0.020 * K_),                                                                # lurch up: spit
         dict(ride=RIDE, legs=rest_legs(), stalk=(1.06, 0.97))]
HEAVE_GLOW = [0.2, 0.6, 1.0, 0.45]


# ---------------------------------------------------------------- the fireball
def fireball(k, n=16):
    """a molten blob with a dark crust, frame k of 4 (it churns)."""
    rng = np.random.default_rng(40 + k)
    yy, xx = np.mgrid[0:n, 0:n]
    cx = cy = (n - 1) / 2
    d = np.hypot(xx - cx, yy - cy) / (n * 0.44)
    noise = rng.random((n, n))
    out = np.zeros((n, n), np.uint8)
    heat = 1 - d + 0.18 * (noise - 0.5)
    out[heat > 0.0] = 9
    out[heat > 0.18] = 10
    out[heat > 0.36] = 11
    out[heat > 0.52] = 12
    out[heat > 0.66] = 13
    out[heat > 0.78] = 14
    out[heat > 0.88] = 15
    crust = (noise > 0.80) & (heat > 0.05) & (heat < 0.45)
    out[crust] = 2
    return out




def pose_of(f):
    """frame f's (pose, furnace glow)."""
    if f == F_REST:
        return dict(ride=RIDE, legs=rest_legs(), stalk=(1.0, 1.0)), REST_GLOW
    if f < F_JUMP:
        return walk(f - F_WALK), REST_GLOW
    if f < F_HEAVE:
        return JUMP[f - F_JUMP], REST_GLOW
    return HEAVE[f - F_HEAVE], HEAVE_GLOW[f - F_HEAVE]


def views():
    """[(theta, sprite y in the dome box)] per latitude view: each view's
    13 pictures, measured in a 64-px box, are centred vertically in the
    32-px sprite (the creature's height on screen changes with latitude:
    near the peak it is seen from the side and the stalk rises)."""
    out = []
    for i in range(g.SHIP_STEPS):
        theta = math.radians(g.SHIP_MAX_DEG) * i / (g.SHIP_STEPS - 1)
        top, bot = 999, -1
        for f in range(FRAMES):
            pose, glow = pose_of(f)
            idx, (ox64, oy64) = render(pose, theta, glow, box=64)
            ys = np.nonzero(idx.any(1))[0]
            top, bot = min(top, oy64 + ys[0]), max(bot, oy64 + ys[-1])
        assert bot - top + 1 <= SIZE - 2, (i, top, bot)
        oy = (top + bot + 1) // 2 - SIZE // 2
        out.append((theta, oy))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("header")
    ap.add_argument("--preview")
    args = ap.parse_args()

    vs = views()
    nb = g.SHIP_STEPS * FRAMES
    sheet = np.zeros((SIZE * nb + 32, SIZE), np.uint8)
    for v, (theta, oy) in enumerate(vs):
        for f in range(FRAMES):
            pose, glow = pose_of(f)
            idx, (ox, oy2) = render(pose, theta, glow, oy=oy)
            assert ox == OX, (v, ox, OX)
            # nothing may touch the box's edge: a clipped leg would show
            assert not (idx[0].any() or idx[-1].any() or idx[:, 0].any() or idx[:, -1].any()), (v, f)
            b = v * FRAMES + f
            sheet[b * SIZE:(b + 1) * SIZE] = idx
    fb = [fireball(k) for k in range(FIREBALL_FRAMES)]
    y0 = SIZE * nb
    sheet[y0:y0 + 16, 0:16], sheet[y0:y0 + 16, 16:32] = fb[0], fb[1]
    sheet[y0 + 16:y0 + 32, 0:16], sheet[y0 + 16:y0 + 32, 16:32] = fb[2], fb[3]

    im = Image.fromarray(sheet, "P")
    flat = [int(c) for rgb in PALETTE for c in rgb]
    im.putpalette(flat)
    im.save(args.sheet)
    if args.preview:
        strip = np.hstack([sheet[(v * FRAMES + f) * SIZE:(v * FRAMES + f + 1) * SIZE]
                           for v in (0, 24, 47) for f in range(FRAMES)])
        pv = Image.fromarray(strip, "P")
        pv.putpalette(flat)
        pv.convert("RGB").resize((strip.shape[1] * 4, SIZE * 4), Image.NEAREST).save(args.preview)

    def tile(b, c, r):
        return TILE_BASE + (b * ROWS + r) * COLS + c

    with open(args.header, "w") as h:
        w = h.write
        w("/* generated by tools/render_spider.py: do not edit */\n"
          f"#define SHIP_VIEWS {g.SHIP_STEPS}\n#define SHIP_FRAMES {FRAMES}\n"
          f"#define SHIP_COLS {COLS}\n#define SHIP_ROWS {ROWS}\n#define SHIP_TILE_BASE {TILE_BASE}\n"
          f"#define SHIP_OX {OX}      /* sprite x in the dome box */\n"
          f"#define SHIP_F_REST {F_REST}\n#define SHIP_F_WALK {F_WALK}   /* 4 frames */\n"
          f"#define SHIP_F_JUMP {F_JUMP}   /* 4: scrunch, launch, airborne, land */\n"
          f"#define SHIP_F_HEAVE {F_HEAVE}  /* 4: rest-glow, squeeze, spit, settle */\n"
          f"#define SHIP_FIREBALL_TILE {TILE_BASE + nb * 4}\n#define SHIP_FIREBALL_FRAMES {FIREBALL_FRAMES}\n"
          "/* tile number of latitude view v's REST picture, column c, row r */\n"
          "static const u16 ship_tile[SHIP_VIEWS][SHIP_COLS][SHIP_ROWS] = {\n")
        for v in range(g.SHIP_STEPS):
            b = v * FRAMES + F_REST
            w("  {" + ",".join("{" + ",".join(str(tile(b, c, r)) for r in range(ROWS)) + "}" for c in range(COLS)) + "},\n")
        w("};\n/* every picture: [view][frame][column][row] */\n"
          "static const u16 ship_anim_tile[SHIP_VIEWS][SHIP_FRAMES][SHIP_COLS][SHIP_ROWS] = {\n")
        for v in range(g.SHIP_STEPS):
            w("  {" + ",".join("{" + ",".join("{" + ",".join(str(tile(v * FRAMES + f, c, r)) for r in range(ROWS)) + "}"
                                          for c in range(COLS)) + "}" for f in range(FRAMES)) + "},\n")
        w("};\n/* sprite y in the dome box, per latitude view */\n"
          "static const s16 ship_oy[SHIP_VIEWS] = {\n  " + ", ".join(str(oy) for _, oy in vs) + "\n};\n")


if __name__ == "__main__":
    main()
