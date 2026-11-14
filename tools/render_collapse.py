"""render_collapse.py: the art and the tables of the dome's collapse (the
redo of 10-25, from the approved mockup ~/Downloads/dome-collapse.html).

    python3 tools/render_collapse.py HEADER C1 C2 [--preview PNG] [--over PNG]

The collapse, in frames g = collapse_frac - COLLAPSE_SHAKE (g 0 is the
burst; the shake before it is f 0..40, as today):

  - the PUFFS (f 0..40, during the shake): small bursts on the dome, a
    2x2-tile picture in 4 frames at full size (no shrink: 2 sprites each;
    at most 3 at once). A puff that starts late runs on past f 40 only in
    the tables' arithmetic: the runtime drops every puff at the burst;
  - the RUIN (from g 0 until the new dome): one 8x6-tile picture in the
    dome's own box, drawn in place of the dome's columns. It is built from
    the dome's 3D mesh relative to the camera (tall stumps on the far
    diagonals, a low rim in front, a rubble floor with embers), so ONE
    picture serves every dome angle;
  - the FIREBALL (g 0..FIRE_T-1): 6 frames of 12x10 tiles drawn at full
    size; the hardware shrink grows it from 30% to 100% over the dome.
    Its 12 columns are independent sprites (never sticky: a shrunk sticky
    chain leaves gaps), column c at x + c * (hz + 1). A column that is
    empty in a frame is hidden (it would only cost sprites on its lines);
  - the FRAGMENTS (g 0..FRAG_T-1): pieces of the dome's own glass, one
    sprite column each (16 px wide, 1..3 tiles), flying out under gravity
    and tumbling by H/V flips. A fragment is hidden before its launch and
    whenever it is off the screen. Their launch delays are chosen here so
    that no screen line goes over the sprite budget (below);
  - the SMOKE (from g SMOKE_G0): 3 plumes rising from the stumps, each its
    own 8-frame loop of 3x7 tiles, swapped by the CPU (each plume has its
    own phase, which the LSPC's one global auto-animation counter could not
    give). A plume grows by vertical shrink anchored at its base, and
    drifts sideways. From g SMOKE_LOOP the tables repeat every SMOKE_PERIOD
    frames (a GAME OVER keeps the ruin smoking for ever).

Every picture's fully transparent tiles are tile number 0 (relative), the
part's own blank tile, so the runtime writes a tile number for every row
and never special-cases one.

THE SPRITE BUDGET. The LSPC draws at most 96 sprites on a line; past that
the HIGHEST slots are dropped (the console, the radar). BASELINE below is
the most sprites any line had over the props leg's whole spin on trunk
e6dd693 WITHOUT the dome's columns and the broken overlays (both gone
during the collapse), measured from VRAM with the tear probe (sticky
followers added: ground 19, mountains 20, band 20, ship 1). Every frame of
the collapse is held to BASELINE + its own sprites <= 96 - MARGIN on every
line; the generator fails if not. The real total is measured in MAME by the
collapse task's census leg; this table only steers the design.

All pictures and tables are exact to the hardware's shrink: horizontal
through ZOOM_X_COLS, vertical through the BIOS zoom table (_ZOOM_Y), both
from tools/render_radar.py (see docs/superpowers/lessons.md, "The Neo Geo
vertical zoom table").
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tests"))
import geometry as g                                    # noqa: E402
import render_dome as rd                                # noqa: E402
import render_broken as rb                              # noqa: E402
import render_radar as rr                               # noqa: E402
import render_scenery as rs                             # noqa: E402
from layout import d as lay                             # noqa: E402

TILE = 16
SCREEN_W, SCREEN_H = 320, 224
DX, DY = lay.DOME_X, lay.DOME_Y
COLLAPSE_SHAKE = 41          # src/rules.h: the shake's frames (f 0..40)
DEAD_FRAMES = 118            # src/rules.h: the new dome at f 118
G_END = DEAD_FRAMES - COLLAPSE_SHAKE      # 77: g 0..76 before a new dome
MARGIN = 4
LINE_LIMIT = 96 - MARGIN
# the measured baseline (see the docstring), per screen line 0..223,
# run-length coded as (count, value) pairs
_BASELINE_RLE = (
    (24, 6), (28, 3), (16, 24), (13, 45), (1, 47), (1, 51), (3, 53), (1, 56),
    (1, 57), (1, 59), (1, 62), (1, 64), (1, 66), (3, 68), (2, 71), (3, 72),
    (1, 50), (1, 52), (2, 58), (1, 60), (1, 61), (2, 63), (1, 65), (5, 64),
    (1, 62), (1, 60), (3, 58), (4, 57), (1, 60), (2, 57), (2, 54), (4, 53),
    (1, 50), (3, 49), (4, 46), (1, 45), (3, 46), (1, 51), (1, 49), (2, 50),
    (1, 51), (1, 52), (2, 58), (2, 61), (2, 58), (1, 59), (1, 56), (2, 51),
    (9, 49), (3, 46), (4, 43), (2, 56), (11, 53), (1, 54), (2, 59), (1, 66),
    (1, 65), (2, 64), (1, 65), (1, 66), (1, 65), (6, 64), (1, 63), (16, 62),
    (2, 58),)
BASELINE = np.concatenate([np.full(n, v, int) for n, v in _BASELINE_RLE])
assert BASELINE.shape == (SCREEN_H,), BASELINE.shape

DOME_PTS, DOME_EDGES, DOME_FACES = g.build_mesh()
FIT = g.fit()
DOME = rd.quantize(rd.render_view(0, DOME_PTS, DOME_EDGES, DOME_FACES, FIT))
DH, DW = DOME.shape                         # 96 x 128: the dome's box
assert DH % TILE == 0 and DW % TILE == 0


# ------------------------------------------------------------------ helpers
def noise(shape, scale, seed):
    """smooth value noise in 0..1: random cells of `scale` px, bicubic."""
    r = np.random.default_rng(seed)
    small = r.random((shape[0] // scale + 2, shape[1] // scale + 2))
    im = Image.fromarray((small * 255).astype(np.uint8)).resize(
        (shape[1] + 2 * scale, shape[0] + 2 * scale), Image.BICUBIC)
    return np.asarray(im)[scale:scale + shape[0], scale:scale + shape[1]] / 255.0


def to_neo(pal_rgb):
    """16 RGB triples -> 16 palette words; entry 0 transparent (0x8000)."""
    out = [0x8000]
    for c in pal_rgb[1:]:
        out.append(rs.rgb_to_neo15(tuple(int(v) for v in c)))
    while len(out) < 16:
        out.append(0x8000)
    return out


def zoom_lines(rows, v, height=None):
    """[(screen line offset, SCB1 row, art row)] that a column of `rows`
    picture tiles draws at vertical zoom v with SCB3 height `height`
    (default rows), keeping only the lines that hit a picture row."""
    height = rows if height is None else height
    out = []
    for line in range(height * TILE):
        b = rr._ZOOM_Y[(v << 8) | (line & 0xff)]
        row, artrow = b >> 4, b & 0x0f
        if row < rows:
            out.append((line, row, artrow))
    return out


def fit_height(rows, v):
    """the smallest SCB3 height that still draws every picture line the
    full height draws (so a shrunk picture costs fewer lines)."""
    full = [(r, a) for _l, r, a in zoom_lines(rows, v)]
    for h in range(1, rows + 1):
        if [(r, a) for _l, r, a in zoom_lines(rows, v, h)] == full:
            return h
    return rows


def blit(frame, pic, pal, left, top, hz=15, v=255, height=None,
         hflip=False, vflip=False):
    """draw a picture of whole tiles as the hardware does: independent
    columns at left + c * (hz + 1), the zoom tables for both axes. A flip
    flips the WHOLE picture: the runtime sets the tiles' H/V bits AND
    reverses the tile order (a V-flipped fragment's SCB1 rows are written
    bottom tile first), so this flips the picture before drawing."""
    if hflip:
        pic = pic[:, ::-1]
    if vflip:
        pic = pic[::-1]
    rows, cols = pic.shape[0] // TILE, pic.shape[1] // TILE
    for line, row, artrow in zoom_lines(rows, v, height):
        sy = top + line
        if not 0 <= sy < SCREEN_H:
            continue
        for c in range(cols):
            for j, artcol in enumerate(rr.ZOOM_X_COLS[hz]):
                idx = int(pic[row * TILE + artrow, c * TILE + artcol])
                sx = left + c * (hz + 1) + j
                if idx and 0 <= sx < SCREEN_W:
                    frame[sy, sx] = pal[idx]


# ------------------------------------------------------------------ the ruin
# The ruin's top tile row is empty in every view (its rim starts 18..20 px
# down the box), so the runtime draws the ruin's columns RUIN_TOP px lower
# and one tile row shorter: 8 sprites off lines DY..DY+15 (the halo ring's
# full turn over the ruin measured 97..99 there with the whole box, 10-30).
RUIN_TOP = 16
SECTOR = 2 * math.pi / 5      # the dome mesh's symmetry (g.VIEWS = g.STEPS / 5)
# per 72-degree sector of the rim (radians from the sector's start, width,
# height): a main stump, a lesser one and a notch-filling shoulder; the same
# in every sector, so the ruin repeats every 72 degrees like the dome and
# view v serves every dome angle a with a % VIEWS == v (the halo ring turns
# the scene over the ruin, 10-30)
STUMPS = ((0.30, 0.17, 0.17), (0.86, 0.12, 0.09), (1.10, 0.20, 0.05))


def ruin_indices(view):
    """(full-colour indices DH x DW, palette) of the ruin at dome step
    `view`: the dome's own mesh turned like the dome's view, a low jagged
    rim with short stumps repeating every 72 degrees, and a rubble floor
    generated on the ground disc in 3D (so it turns with the walls)."""
    pts, edges, faces = DOME_PTS, DOME_EDGES, DOME_FACES
    raw, world = g.project(pts, view)
    px = g.to_px(raw, FIT)
    y0 = math.cos(math.radians(g.CAP_DEG))
    hgt = pts[:, 1] - y0
    phi = np.arctan2(pts[:, 2], pts[:, 0])
    cpos = g.camera()[0]

    def sect(p):
        return np.mod(p, SECTOR)

    def hlim(p, extra):
        q = sect(p)
        side = 0
        for c, w, hh in STUMPS:
            d = np.mod(q - c + SECTOR / 2, SECTOR) - SECTOR / 2
            side = side + np.exp(-(d / w) ** 2) * hh
        jag = 0.05 * np.sin(5 * p + 1.3) + 0.04 * np.sin(10 * p + 0.4)
        return 0.10 + side + jag + extra

    def face_extra(f):
        # a face's own ragged height, the same for the face's 72-degree
        # copies (a hash of its sector position and height, not a random
        # draw per face index)
        q = float(sect(np.arctan2(pts[list(f), 2].mean(), pts[list(f), 0].mean())))
        h = float(hgt[list(f)].mean())
        return 0.065 * math.sin(37 * q + 11 * h) - 0.015

    def clip(f, lim):
        P = [pts[i] for i in f]
        out = []
        for a, b in zip(P, P[1:] + P[:1]):
            ha, hb = a[1] - y0, b[1] - y0
            if ha <= lim:
                out.append(a)
            if (ha <= lim) != (hb <= lim):
                t = (lim - ha) / (hb - ha)
                out.append(a + t * (b - a))
        return out

    polys = []
    for k, f in enumerate(faces):
        P = clip(list(f), hlim(np.arctan2(pts[list(f), 2].mean(), pts[list(f), 0].mean()),
                               face_extra(f)))
        if len(P) >= 3:
            polys.append((k, np.array(P)))
    edge_ok = [(i, j) for i, j in edges
               if max(hgt[i], hgt[j]) < hlim(math.atan2(pts[i, 2] + pts[j, 2], pts[i, 0] + pts[j, 0]), 0.09)]
    front = set(g.front_faces(faces, world))
    img = rd.layer()
    d = ImageDraw.Draw(img)

    def proj(P):
        return g.to_px(g.project(P, view)[0], FIT)

    # far to near; ties (a face and its mirror image) by screen position, so
    # a view and its 72-degree copies draw in the same order
    def depth_key(q):
        wc = g.project(q[1], view)[1].mean(0)
        sc = proj(q[1]).mean(0)
        return (-round(float(np.linalg.norm(wc - cpos)), 9), round(float(sc[0]), 6), round(float(sc[1]), 6))

    for k, P in sorted(polys, key=depth_key):
        f = faces[k]
        if k in front:
            shade = round(5 * (rd.FILL + (1 - rd.FILL) * max(
                0.0, float(g.face_normal(world, f) @ rd.LIGHT))))
            col = rd.GLASS[shade]
        else:
            col = rd.GLASS[1]
        d.polygon([tuple(p * rd.SS) for p in proj(P)], fill=col + (255,))
    def by_screen(segs):
        """edges in screen order (a view's 72-degree copies list them alike)"""
        return sorted(segs, key=lambda e: tuple(np.round(np.concatenate(sorted(
            [e[0], e[1]], key=lambda p: (round(float(p[0]), 6), round(float(p[1]), 6)))), 6)))
    rd.lines(img, by_screen([(px[i], px[j]) for i, j in edge_ok]), rd.BACK_EDGE, rd.BACK_W, 1.0)
    vis = set(g.visible_edges(edges, faces, world))
    fr_e = by_screen([(px[i], px[j]) for i, j in edge_ok if (i, j) in vis])
    rd.lines(img, fr_e, rd.EDGE_GLOW, rd.GLOW_W - 1, 1.0)
    rd.lines(img, fr_e, (130, 205, 235), rd.CORE_W - 1, 1.0)
    out = rd.quantize(img.resize((g.DOME_W, g.DOME_H), Image.BOX)).astype(int)

    # the scorch: glass darkened, struts dulled; 4 extra colours: an ember
    # (16) and three rubble tones (17..19)
    pal = np.array(rd.PALETTE, float)
    pal[1:7] = pal[1:7] * 0.6 + np.array((40, 34, 30)) * 0.4
    pal[7:] = pal[7:] * 0.75 + np.array((90, 72, 56)) * 0.25
    pal = np.vstack([pal.clip(0, 255),
                     [(255, 150, 40), (46, 40, 36), (70, 62, 54), (98, 88, 76)]])

    th = np.linspace(0, 2 * math.pi, 400)
    s0 = math.sin(math.radians(g.CAP_DEG))
    ring = g.to_px(g.project(np.stack(
        [s0 * np.cos(th), np.full_like(th, y0), s0 * np.sin(th)], 1), 0)[0], FIT)
    mimg = Image.new('L', (DW, DH), 0)
    ImageDraw.Draw(mimg).polygon([tuple(p) for p in ring], fill=255)
    floor = np.asarray(mimg) > 0
    fy = np.nonzero(floor.any(1))[0]
    cxm = ring[:, 0].mean()
    nn = noise((DH, DW), 3, 61)
    nn2 = noise((DH, DW), 1, 62)
    fl = floor_texture(view)
    for y in range(fy[0], fy[-1] + 1):
        for x in np.nonzero(floor[y])[0]:
            if out[y, x] >= 7:
                continue
            out[y, x] = fl[y, x]
    for x in range(DW):
        dx = abs(x - cxm) / (DW * 0.42)
        col = np.nonzero(floor[:, x])[0]
        if dx >= 1 or not len(col):
            continue
        mid = (col[0] + col[-1]) // 2
        for k in range(int((1 - dx * dx) * (6 + 4 * nn[mid, x]))):
            y = mid - k
            if 0 <= y < DH and out[y, x] < 7:
                out[y, x] = (17, 18, 19)[int(nn2[y, x] * 2.99)]
    filled = DOME != 0
    bottom = np.where(filled.any(0), DH - 1 - np.argmax(filled[::-1], 0), 0)
    n = noise((DH, DW), 2, 23)
    hn = noise((1, DW), 4, 24)[0]
    for x in range(DW):
        if bottom[x] <= 0:
            continue
        for k in range(int(2 + 5 * hn[x])):
            y = bottom[x] - k
            if 0 <= y < DH and n[y, x] < 0.85:
                out[y, x] = 17 + int(n[y, x] * 3)
                if k < 3 and n[y, x] > 0.78:
                    out[y, x] = 16
    return out, pal


def floor_texture(view):
    """the rubble floor's colours (16 ember, 17..19 rubble) at dome step
    `view`, DH x DW: points on the ground disc in 3D, coloured from 2D noise
    made the same in every 72-degree sector (sym below), projected like the
    mesh and splatted; the most common colour wins each pixel."""
    y0 = math.cos(math.radians(g.CAP_DEG))
    s0 = math.sin(math.radians(g.CAP_DEG))
    nr, nphi = 70, 900
    r = (np.arange(nr) + 0.5) / nr
    ph = 2 * math.pi * np.arange(nphi) / nphi
    R, PH = np.meshgrid(r, ph, indexing="ij")
    P = np.stack([s0 * R * np.cos(PH), np.full_like(R, y0), s0 * R * np.sin(PH)], -1).reshape(-1, 3)
    px = g.to_px(g.project(P, view)[0], FIT)
    N = 192
    big = noise((N, N), 7, 61)
    fine = noise((N, N), 2, 62)
    X, Z = (s0 * R * np.cos(PH)).ravel(), (s0 * R * np.sin(PH)).ravel()

    def sym(tex):
        """tex sampled at the point and its four 72-degree turns, averaged,
        then rank-normalised back to 0..1: isotropic, the same in every
        sector"""
        acc = np.zeros_like(X)
        for k in range(5):
            c, sn = math.cos(k * SECTOR), math.sin(k * SECTOR)
            xr, zr = c * X - sn * Z, sn * X + c * Z
            u = ((xr / s0 + 1) / 2 * (N - 1)).astype(int)
            w = ((zr / s0 + 1) / 2 * (N - 1)).astype(int)
            acc += tex[np.clip(w, 0, N - 1), np.clip(u, 0, N - 1)]
        order = acc.argsort().argsort()
        return order / max(1, len(order) - 1)
    a, b = sym(big), sym(fine)
    col = np.array((17, 18, 19, 18))[np.minimum(3, (a * 3.2).astype(int))]
    col = np.where((b > 0.93) & (a < 0.5), 16, col)
    votes = np.zeros((DH, DW, 20), int)
    xs, ys = np.round(px[:, 0]).astype(int), np.round(px[:, 1]).astype(int)
    ok = (xs >= 0) & (xs < DW) & (ys >= 0) & (ys < DH)
    np.add.at(votes, (ys[ok], xs[ok], col[ok]), 1)
    out = votes.argmax(-1)
    out[votes.sum(-1) == 0] = 18
    return out


def ruin_pictures():
    """(48 x [indices DH x DW], 16 RGB): the ruin at every dome view, folded
    to ONE palette together (the runtime keeps one ruin bank)."""
    views = [ruin_indices(v) for v in range(g.VIEWS)]
    pal = views[0][1]
    stack = np.concatenate([v[0] for v in views], 0)
    idx, pal16 = fold(stack, pal, keep=(16,))
    return [idx[v * DH:(v + 1) * DH] for v in range(g.VIEWS)], pal16


def ruin_picture():
    """the ruin at view 0 (kept for the preview and the tests)."""
    pics, pal = ruin_pictures()
    return pics[0], pal


def fold(idx, pal, keep=()):
    """fold a picture's colours into 15 (+ transparent 0): while more than
    15 are used, merge the least-used colour (never one in `keep`) into its
    nearest used colour in RGB. Returns (indices 0..15, 16 RGB)."""
    idx = idx.copy()
    used = [c for c in sorted(set(idx.ravel().tolist())) if c]
    while len(used) > 15:
        counts = {c: int((idx == c).sum()) for c in used}
        victim = min((c for c in used if c not in keep), key=lambda c: counts[c])
        target = min((c for c in used if c != victim),
                     key=lambda c: float(((pal[c] - pal[victim]) ** 2).sum()))
        idx[idx == victim] = target
        used.remove(victim)
    lut = np.zeros(int(idx.max()) + 1, int)
    newpal = [(255, 0, 255)]
    for k, c in enumerate(used):
        lut[c] = k + 1
        newpal.append(tuple(int(v) for v in pal[c]))
    while len(newpal) < 16:
        newpal.append((0, 0, 0))
    return lut[idx].astype(np.uint8), np.array(newpal, np.uint8)


# ------------------------------------------------------------------ the fireball and the puffs
FIRE_PAL = np.array([(255, 0, 255), (255, 255, 236), (255, 244, 160), (255, 214, 80),
                     (255, 170, 40), (246, 120, 24), (220, 74, 18), (170, 40, 16),
                     (110, 26, 14), (70, 22, 16), (96, 88, 84), (72, 66, 64),
                     (52, 48, 48), (36, 34, 34), (130, 122, 116), (0, 0, 0)], np.uint8)
FIRE_COLS, FIRE_ROWS = 12, 10
FW, FH = FIRE_COLS * TILE, FIRE_ROWS * TILE
FIRE_FRAMES = 6
FIRE_STEP = 7                # g frames per fireball picture
FIRE_T = 45                  # g 0..44
FIRE_CX, FIRE_CY = DX + DW / 2, DY + DH * 0.78     # the burst's centre
PUFF = 32                    # a puff: 2 x 2 tiles
PUFF_FRAMES = 4
PUFF_STEP = 3
# (f of its first frame, its centre as a fraction of the dome's box)
PUFFS = ((14, .30, .45), (22, .68, .35), (29, .45, .20), (34, .78, .60), (37, .22, .70))


def _blob(out, cx, cy, r, n, col_of):
    h, w = out.shape
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy) / max(r, 1)
    m = d < 1 + 0.35 * (n - 0.5)
    out[m] = col_of(d, n)[m]


def _fire_col(t):
    def f(d, nn):
        heat = (1 - d) * (1.2 - 0.9 * t) + 0.35 * (nn - 0.5)
        return (8 - np.clip(heat * 9, 0, 8).astype(int)).clip(0, 8) + 1
    return f


def _smoke_col(d, nn):
    return np.where(nn > 0.62, 14, np.where(nn > 0.48, 10, np.where(nn > 0.35, 11, 12)))


def fire_picture(t):
    """t 0..1: the hot core, then billowing fire, then smoke balls."""
    n = 0.6 * noise((FH, FW), 12, 3) + 0.4 * noise((FH, FW), 5, 4)
    out = np.zeros((FH, FW), np.uint8)
    cx, cy = FW / 2, FH * 0.62
    r_rng = np.random.default_rng(77)
    balls = [(r_rng.uniform(-1, 1), r_rng.uniform(-1, 0.4), r_rng.uniform(0.55, 1.0))
             for _ in range(9)]
    spread = 12 + 24 * t
    if t > 0.2:
        for bx, by, br in balls:
            _blob(out, cx + bx * spread * 1.3, cy + by * spread - 18 * t * t,
                  (16 + 22 * t) * br * (1.25 - 0.55 * t * t), n, _smoke_col)
    core_r = (60 + 40 * t) * (1 - max(0, t - 0.4) * 1.6)
    if core_r > 4:
        _blob(out, cx, cy, core_r, n, _fire_col(t))
    for bx, by, br in balls[:5]:
        rr_ = (22 + 10 * t) * br * (1 - t) * 1.2
        if rr_ > 3:
            _blob(out, cx + bx * spread, cy + by * spread * 0.8, rr_, n, _fire_col(t))
    return out


def puff_picture(i):
    """a small burst, frame i of 4: a hot ball that turns to smoke."""
    t = i / (PUFF_FRAMES - 1)
    n = 0.6 * noise((PUFF, PUFF), 5, 90 + i) + 0.4 * noise((PUFF, PUFF), 2, 95 + i)
    out = np.zeros((PUFF, PUFF), np.uint8)
    r = 7 + 7 * t
    if t > 0.3:
        _blob(out, PUFF / 2, PUFF / 2 - 2 * t, r + 1, n, _smoke_col)
    core = r * (1 - 0.8 * t)
    if core > 2:
        _blob(out, PUFF / 2, PUFF / 2, core, n, _fire_col(t))
    return out


def fire_shrink(gf):
    """the fireball at frame g: (picture, k, hz, v)."""
    k = min(1.0, 0.3 + 0.7 * (gf / 14) ** 0.7)
    hz = max(0, int(round(16 * k)) - 1)
    v = max(0, min(255, int(round(256 * k)) - 1))
    return min(FIRE_FRAMES - 1, gf // FIRE_STEP), k, hz, v


# ------------------------------------------------------------------ the smoke
SMOKE_PAL = np.array([(255, 0, 255), (150, 144, 140), (120, 114, 112), (92, 88, 88),
                      (66, 62, 64)] + [(0, 0, 0)] * 11, np.uint8)
SMOKE_COLS, SMOKE_ROWS = 2, 7    # 2 columns since the ring of plumes (10-30; was 3)
SW, SH = SMOKE_COLS * TILE, SMOKE_ROWS * TILE
SMOKE_FRAMES = 8
SMOKE_ANIM = 3               # g frames per smoke picture
SMOKE_PERIOD = 144           # the drift's period; a multiple of 8 * 3
# The plumes stand in a ring inside the ruin (the user's pick, 10-30: six
# plumes, two sprites wide, at 0.6 of the floor's radius), so they turn with
# the ruin when the halo ring turns the scene: plume p's foot is the ground
# point at world angle PLUME_ANGLE0 + p * 60 degrees, SMOKE_R of the cap's
# radius out, projected at the dome step (smoke_foot_x/y[step][p]). The
# three nearest the camera are drawn in front of the ruin, the other three
# behind it (smoke_front[step], a bit per plume).
SMOKE_R = 0.6
PLUME_ANGLE0 = math.radians(15)
# (seed, first g, phase, mirrored)
PLUMES = ((31, 17, 0, False), (52, 26, 3, True), (73, 35, 5, False),
          (94, 44, 1, True), (115, 53, 6, False), (136, 62, 2, True))
SMOKE_GROW = 33              # g frames from 15% to full height


def smoke_pictures(seed, mirror):
    """one plume's 8-frame loop (SH x SW each): the texture scrolls up 6 px
    a frame through a fixed envelope with a rounded cap."""
    PER = 48
    yy_, xx_ = np.mgrid[0:SH, 0:SW]
    tex = 0.55 * noise((PER * 2 + SH, SW), 7, seed) + 0.45 * noise((PER * 2 + SH, SW), 3, seed + 1)
    t2 = np.concatenate([tex[:PER]] * ((SH + PER) // PER + 2), 0)
    env_n = noise((SH, SW), 9, seed + 2)
    k = SW / 48                       # the envelope was drawn for 3 columns
    width = (7 + 15 * (1 - yy_ / SH) ** 0.7 + 4 * (env_n - 0.5)) * k
    lean = 4 * k * (1 - yy_ / SH) ** 1.6 * (1 if seed % 2 else -1)
    d = np.abs(xx_ - SW / 2 - lean) / width
    CAP = 26
    cy = (CAP - yy_) / CAP
    capw = np.sqrt(np.clip(1 - np.clip(cy, 0, 1) ** 2, 0, 1))
    frames = []
    for f in range(SMOKE_FRAMES):
        off = f * PER // SMOKE_FRAMES
        n = t2[off:off + SH]
        dens = (1 - d) * (0.5 + 0.5 * yy_ / SH) + 0.55 * (n - 0.5) + 0.25 * (env_n - 0.5)
        dth = noise((SH, SW), 1, seed + 10 + f)
        inside_cap = (np.abs(xx_ - SW / 2 - lean) / (width + 2)) < capw * (0.9 + 0.25 * (n - 0.5))
        dens = np.where(yy_ < CAP, np.where(inside_cap, dens, -1), dens)
        on = (dens > 0.18) & (dens > dth * 0.5)
        out = np.zeros((SH, SW), np.uint8)
        out[on] = np.clip(1 + ((0.6 * n[on] + 0.4 * env_n[on]) * 4).astype(int), 1, 4)
        frames.append(out[:, ::-1].copy() if mirror else out)
    return frames


SMOKE_LOOP = max(p[1] for p in PLUMES) + SMOKE_GROW + 1    # every plume full-grown


def smoke_foot(step, p):
    """plume p's foot on screen at dome step `step`: (x, y, distance to the
    camera)."""
    y0 = math.cos(math.radians(g.CAP_DEG))
    s0 = math.sin(math.radians(g.CAP_DEG))
    a = PLUME_ANGLE0 + p * 2 * math.pi / len(PLUMES)
    P = np.array([[SMOKE_R * s0 * math.cos(a), y0, SMOKE_R * s0 * math.sin(a)]])
    raw, world = g.project(P, step)
    px = g.to_px(raw, FIT)[0]
    return (int(round(DX + px[0])), int(round(DY + px[1])),
            float(np.linalg.norm(world[0] - g.camera()[0])))


def smoke_feet():
    """([step][p] x, [step][p] y, [step] front bitmask): the three plumes
    nearest the camera are the front ones."""
    xs, ys, front = [], [], []
    for step in range(g.STEPS):
        f = [smoke_foot(step, p) for p in range(len(PLUMES))]
        xs.append([q[0] for q in f])
        ys.append([q[1] for q in f])
        near = sorted(range(len(PLUMES)), key=lambda p: f[p][2])[:len(PLUMES) // 2]
        front.append(sum(1 << p for p in near))
    return xs, ys, front


def smoke_at(p, gf):
    """plume p at frame g: None (not yet) or (picture, dx, lines, v,
    height): the picture's left is the foot's x + dx - SW / 2 and its top
    the foot's y - lines."""
    seed, g0, phase, _m = PLUMES[p]
    if gf < g0:
        return None
    if gf >= SMOKE_LOOP + SMOKE_PERIOD:
        gf = SMOKE_LOOP + (gf - SMOKE_LOOP) % SMOKE_PERIOD
    kv = min(1.0, 0.15 + 0.85 * (gf - g0) / SMOKE_GROW)
    v = max(0, min(255, int(round(256 * kv)) - 1))
    h = fit_height(SMOKE_ROWS, v)
    lines = len(zoom_lines(SMOKE_ROWS, v, h))
    pic = ((gf + COLLAPSE_SHAKE) // SMOKE_ANIM + phase) % SMOKE_FRAMES
    drift = int(round(2.5 * math.sin(2 * math.pi * gf / SMOKE_PERIOD + p * 2.1)))
    return pic, drift, lines, v, h


# ------------------------------------------------------------------ the fragments
GRAVITY = 0.16
FRAG_T = G_END               # a fragment is drawn on g 0..76 at most
MAX_DELAY = 10


def fragment_pieces():
    """the dome's visible cells (view 0) as one-column pictures, with their
    flight: [(picture rows*16 x 16, x, y, vx, vy, spin)]."""
    rng = np.random.default_rng(11)
    out = []
    for cell in range(76):
        poly = rb._cell_poly_px_at(cell, 0)
        img = Image.new('L', (DW, DH), 0)
        ImageDraw.Draw(img).polygon([tuple(p) for p in poly], fill=255)
        m = (np.asarray(img) > 0) & (DOME != 0)
        if m.sum() < 30:
            continue
        ys, xs = np.nonzero(m)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        if x1 - x0 > TILE:
            c = (x0 + x1) // 2
            x0, x1 = c - 8, c + 8
        rows = -(-(y1 - y0) // TILE)
        pic = np.zeros((rows * TILE, TILE), np.uint8)
        pic[:y1 - y0, :x1 - x0] = np.where(m[y0:y1, x0:x1], DOME[y0:y1, x0:x1], 0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ang = math.atan2(cy - DH * 0.95, cx - DW / 2)
        sp = rng.uniform(2.2, 4.8)
        out.append((pic, DX + x0, DY + y0, sp * math.cos(ang) * 1.3,
                    sp * math.sin(ang) - rng.uniform(1.0, 3.0), int(rng.integers(3, 7))))
    return out


def fragment_track(piece, delay):
    """[(x, y, flips) or None per g 0..FRAG_T-1]: None = hidden."""
    pic, x0, y0, vx, vy, spin = piece
    h = pic.shape[0]
    out = []
    for gf in range(FRAG_T):
        s = gf - delay
        if s < 0:
            out.append(None)
            continue
        x = int(round(x0 + vx * s))
        y = int(round(y0 + vy * s + GRAVITY * s * s))
        if x + TILE <= 0 or x >= SCREEN_W or y + h <= 0 or y >= SCREEN_H:
            out.append(None)
            continue
        q = (s // spin) % 4
        out.append((x, y, (1 if q in (1, 2) else 0) | (2 if q in (2, 3) else 0)))
    return out


# ------------------------------------------------------------------ the census
def lines_of(top, height):
    """the screen lines a sprite of SCB3 `height` at `top` covers."""
    a, b = max(0, top), min(SCREEN_H, top + height * TILE)
    return (a, b) if b > a else None


def build():
    ruins, ruin_pal = ruin_pictures()
    ruin = ruins[0]
    fire = [fire_picture(t) for t in np.linspace(0, 1, FIRE_FRAMES)]
    puffs = [puff_picture(i) for i in range(PUFF_FRAMES)]
    smoke = [smoke_pictures(seed, m) for seed, _g, _p, m in PLUMES]
    feet_x, feet_y, feet_front = smoke_feet()
    pieces = fragment_pieces()

    # the fireball's per-frame words: a column empty in its picture is hidden
    fire_tab = []
    for gf in range(FIRE_T):
        i, k, hz, v = fire_shrink(gf)
        h = fit_height(FIRE_ROWS, v)
        nl = len(zoom_lines(FIRE_ROWS, v, h))
        w = FIRE_COLS * (hz + 1)
        left = int(round(FIRE_CX - w / 2))
        top = int(round(FIRE_CY - nl * 0.62))
        mask = sum(1 << c for c in range(FIRE_COLS)
                   if fire[i][:, c * TILE:(c + 1) * TILE].any())
        fire_tab.append((i, hz, v, h, left, top, mask))

    # the census of everything but the fragments, per g
    count = np.zeros((G_END, SCREEN_H), int)
    for gf in range(G_END):
        count[gf, DY + RUIN_TOP:DY + DH] += DW // TILE      # the ruin (below its empty top row)
        if gf < FIRE_T:
            i, hz, v, h, left, top, mask = fire_tab[gf]
            span = lines_of(top, h)
            if span:
                count[gf, span[0]:span[1]] += bin(mask).count("1")
        # the plumes: the most sprites any dome step puts on each line (the
        # scene's angle is the GAME OVER's, and the halo ring turns it)
        worst = np.zeros(SCREEN_H, int)
        for step in range(g.STEPS):
            add = np.zeros(SCREEN_H, int)
            for p in range(len(PLUMES)):
                s = smoke_at(p, gf)
                if s:
                    span = lines_of(feet_y[step][p] - s[2], s[4])
                    if span:
                        add[span[0]:span[1]] += SMOKE_COLS
            worst = np.maximum(worst, add)
        count[gf] += worst
    # the shake (f 0..40): the dome's columns (shaken up to 21 px either
    # way; the broken overlays are hidden for the whole collapse, as
    # today, src/cracks.c) and the puffs, 2 sprites each
    shake = np.zeros((COLLAPSE_SHAKE, SCREEN_H), int)
    for fr in range(COLLAPSE_SHAKE):
        shake[fr, max(0, DY - 21):DY + DH + 21] += DW // TILE
        for f0, _px, py in PUFFS:
            if 0 <= (fr - f0) // PUFF_STEP < PUFF_FRAMES:
                top = int(round(DY + DH * py)) - 16
                shake[fr, max(0, top):top + PUFF] += 2
    assert (BASELINE[None, :] + shake <= LINE_LIMIT).all()

    # the fragments: each takes the smallest delay that keeps every line
    # within the budget; one that fits no delay up to MAX_DELAY is dropped
    order = sorted(range(len(pieces)), key=lambda j: (pieces[j][2], pieces[j][1]))
    frags = []
    for j in order:
        pic = pieces[j][0]
        rows = pic.shape[0] // TILE
        for delay in range(MAX_DELAY + 1):
            tr = fragment_track(pieces[j], delay)
            add = np.zeros_like(count)
            for gf, st in enumerate(tr):
                if st:
                    span = lines_of(st[1], rows)
                    if span:
                        add[gf, span[0]:span[1]] += 1
            if (BASELINE[None, :] + count + add <= LINE_LIMIT).all():
                count += add
                frags.append((pic, tr))
                break
    assert (BASELINE[None, :] + count <= LINE_LIMIT).all()
    return dict(ruin=ruin, ruins=ruins, ruin_pal=ruin_pal, fire=fire, puffs=puffs, smoke=smoke,
                pieces=pieces, frags=frags, fire_tab=fire_tab, count=count,
                feet_x=feet_x, feet_y=feet_y, feet_front=feet_front)


# ------------------------------------------------------------------ output
class Tiles:
    """the part's tiles: tile 0 is blank; identical tiles are stored once."""

    def __init__(self):
        self.tiles = [np.zeros((TILE, TILE), np.uint8)]
        self.index = {self.tiles[0].tobytes(): 0}

    def add(self, t):
        key = t.tobytes()
        if key not in self.index:
            self.index[key] = len(self.tiles)
            self.tiles.append(t.copy())
        return self.index[key]

    def picture(self, pic):
        """tile numbers [col][row] of a picture."""
        rows, cols = pic.shape[0] // TILE, pic.shape[1] // TILE
        return [[self.add(pic[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE])
                 for r in range(rows)] for c in range(cols)]


def c_array(name, typ, arr):
    a = np.asarray(arr)
    dims = "".join(f"[{n}]" for n in a.shape)

    def rec(x):
        if x.ndim == 1:
            return "{" + ",".join(str(int(v)) for v in x) + "}"
        return "{" + ",\n ".join(rec(y) for y in x) + "}"
    return f"static const {typ} {name}{dims} = {rec(a)};\n"


def write(out, header, c1, c2):
    T = Tiles()
    for r in out["ruins"]:
        assert not r[:RUIN_TOP].any(), "the ruin's top tile row is not empty"
    ruin_t = [T.picture(r[RUIN_TOP:]) for r in out["ruins"]]
    fire_t = [T.picture(p) for p in out["fire"]]
    puff_t = [T.picture(p) for p in out["puffs"]]
    smoke_t = [[T.picture(p) for p in plume] for plume in out["smoke"]]
    frag_t = [T.picture(pic)[0] for pic, _tr in out["frags"]]
    nfr = len(out["frags"])
    max_rows = max(len(t) for t in frag_t)

    c1b, c2b = bytearray(), bytearray()
    for t in T.tiles:
        a, b = rs.encode_tile(t)
        c1b += a
        c2b += b
    open(c1, "wb").write(bytes(c1b))
    open(c2, "wb").write(bytes(c2b))

    HIDE = -32768
    fx = np.full((nfr, FRAG_T), HIDE)
    fy = np.full((nfr, FRAG_T), HIDE)
    ff = np.zeros((nfr, FRAG_T), int)
    for n, (_pic, tr) in enumerate(out["frags"]):
        for gf, st in enumerate(tr):
            if st:
                fx[n, gf], fy[n, gf], ff[n, gf] = st
    ft = np.zeros((nfr, max_rows), int)
    fr_rows = []
    for n, t in enumerate(frag_t):
        ft[n, :len(t)] = t
        fr_rows.append(len(t))

    nsg = SMOKE_LOOP + SMOKE_PERIOD
    sm = np.zeros((len(PLUMES), nsg, 5), int)
    for p in range(len(PLUMES)):
        for gf in range(nsg):
            s = smoke_at(p, gf)
            sm[p, gf] = (0xff, 0, 0, 0, 0) if s is None else s

    ft_tab = np.array(out["fire_tab"])
    with open(header, "w") as h:
        w = h.write
        w("/* generated by tools/render_collapse.py: do not edit */\n")
        w("#ifndef COLLAPSE_MAP_H\n#define COLLAPSE_MAP_H\n")
        w("/* tile numbers are relative to the collapse part (0 = blank); a\n"
          " * picture's tiles are [col][row]. g = collapse_frac - COLLAPSE_SHAKE. */\n")
        w(f"#define COLLAPSE_TILES {len(T.tiles)}\n")
        w(f"#define COLLAPSE_HIDE ({HIDE})      /* an x/y that means: not drawn */\n")
        w(f"#define RUIN_COLS {DW // TILE}\n#define RUIN_ROWS {(DH - RUIN_TOP) // TILE}\n"
          f"#define RUIN_TOP {RUIN_TOP}   /* the ruin's columns start RUIN_TOP px below the dome box's top */\n"
          f"#define RUIN_VIEWS {g.VIEWS}   /* ruin_tile[dome_angle % RUIN_VIEWS]: the ruin turns like the dome */\n")
        w(f"#define FIRE_COLS {FIRE_COLS}\n#define FIRE_ROWS {FIRE_ROWS}\n"
          f"#define FIRE_FRAMES {FIRE_FRAMES}\n#define FIRE_T {FIRE_T}\n")
        w(f"#define PUFF_COLS 2\n#define PUFF_ROWS 2\n#define PUFF_FRAMES {PUFF_FRAMES}\n"
          f"#define PUFF_STEP {PUFF_STEP}\n#define NPUFFS {len(PUFFS)}\n")
        w(f"#define SMOKE_COLS {SMOKE_COLS}\n#define SMOKE_ROWS {SMOKE_ROWS}\n"
          f"#define SMOKE_FRAMES {SMOKE_FRAMES}\n#define NPLUMES {len(PLUMES)}\n"
          f"#define SMOKE_LOOP {SMOKE_LOOP}\n#define SMOKE_PERIOD {SMOKE_PERIOD}\n"
          f"#define SMOKE_T {nsg}      /* g >= SMOKE_T: g = SMOKE_LOOP + (g - SMOKE_LOOP) % SMOKE_PERIOD */\n")
        w(f"#define NFRAGS {nfr}\n#define FRAG_T {FRAG_T}\n#define FRAG_MAX_ROWS {max_rows}\n")
        w(f"#define COLLAPSE_SPRITES ({DW // TILE} + {FIRE_COLS} + {len(PLUMES)} * {SMOKE_COLS} + {nfr})"
          "   /* ruin + fireball + smoke + fragments */\n")
        w(f"#define COLLAPSE_WORST_LINE {int((BASELINE[None, :] + out['count']).max())}"
          "   /* measured baseline + the collapse's own, <= 92 */\n")
        for name, pal in (("ruin_pal", out["ruin_pal"]), ("fire_pal", FIRE_PAL),
                          ("smoke_pal", SMOKE_PAL)):
            w(f"static const u16 {name}[16] = {{" + ", ".join(f"0x{x:04x}" for x in to_neo(pal)) + "};\n")
        w("/* the fragments are the dome's own glass: they use the dome's bank */\n")
        w(c_array("ruin_tile", "u16", ruin_t))
        w(c_array("fire_tile", "u16", fire_t))
        w(c_array("puff_tile", "u16", puff_t))
        w(c_array("smoke_tile", "u16", smoke_t))
        w("/* the fireball per g: picture, SCB2 (hz << 8 | v), SCB3 height,\n"
          " * left, top (column c at left + c * (hz + 1)), shown-column mask */\n")
        w(c_array("fire_pic", "u8", ft_tab[:, 0]))
        w(c_array("fire_scb2", "u16", (ft_tab[:, 1] << 8) | ft_tab[:, 2]))
        w(c_array("fire_h", "u8", ft_tab[:, 3]))
        w(c_array("fire_x", "s16", ft_tab[:, 4]))
        w(c_array("fire_y", "s16", ft_tab[:, 5]))
        w(c_array("fire_mask", "u16", ft_tab[:, 6]))
        w("/* the puffs: f of the first frame, centre (screen px); frame i of\n"
          " * PUFF_FRAMES shows f0 + i*PUFF_STEP .. +PUFF_STEP-1, full size */\n")
        w(c_array("puff_f0", "u8", [p[0] for p in PUFFS]))
        w(c_array("puff_x", "s16", [int(round(DX + DW * p[1])) - 16 for p in PUFFS]))
        w(c_array("puff_y", "s16", [int(round(DY + DH * p[2])) - 16 for p in PUFFS]))
        w("/* the plumes per g (wrapped as SMOKE_T says): picture (0xff = not\n"
          " * yet), dx, lines, SCB2 v (hz is 15), SCB3 height. At dome step a,\n"
          " * plume p's left is smoke_foot_x[a][p] + dx - SMOKE_COLS * 8 and its\n"
          " * top smoke_foot_y[a][p] - lines; it is drawn in front of the ruin\n"
          " * when bit p of smoke_front[a] is set, else behind it. */\n")
        w(c_array("smoke_pic", "u8", sm[:, :, 0]))
        w(c_array("smoke_dx", "s8", sm[:, :, 1]))
        w(c_array("smoke_lines", "u8", sm[:, :, 2]))
        w(c_array("smoke_v", "u8", sm[:, :, 3]))
        w(c_array("smoke_h", "u8", sm[:, :, 4]))
        w(c_array("smoke_foot_x", "s16", out["feet_x"]))
        w(c_array("smoke_foot_y", "s16", out["feet_y"]))
        w(c_array("smoke_front", "u8", out["feet_front"]))
        w("/* the fragments: tiles (one column), rows, and per g the top-left\n"
          " * (COLLAPSE_HIDE = hidden) and the flips (bit 0 H, bit 1 V: the\n"
          " * SCB1 attribute's low bits) */\n")
        w(c_array("frag_tile", "u16", ft))
        w(c_array("frag_rows", "u8", fr_rows))
        w(c_array("frag_x", "s16", fx))
        w(c_array("frag_y", "s16", fy))
        w(c_array("frag_flip", "u8", ff))
        w("#endif\n")
    return T


def preview(out, path, over=None, fr_list=(10, 30, 41, 44, 50, 60, 80, 100, 117)):
    """exact-hardware stills of the collapse (pieces only) over a snapshot."""
    dpal = np.array(rd.PALETTE, np.uint8)
    bg = (np.array(Image.open(over).convert("RGB")) if over else
          np.full((SCREEN_H, SCREEN_W, 3), (117, 182, 233), np.uint8))
    stills = []
    for fr in fr_list:
        f = bg.copy()
        gf = fr - COLLAPSE_SHAKE
        if gf < 0:
            blit(f, DOME, dpal, DX, DY)
            for n, (f0, px, py) in enumerate(PUFFS):
                i = (fr - f0) // PUFF_STEP
                if 0 <= i < PUFF_FRAMES:
                    blit(f, out["puffs"][i], FIRE_PAL, int(round(DX + DW * px)) - 16,
                         int(round(DY + DH * py)) - 16)
        else:
            blit(f, out["ruin"], out["ruin_pal"], DX, DY)
            for p in range(len(PLUMES)):
                s = smoke_at(p, gf)
                if s:
                    pic, dx, lines, v, h = s
                    blit(f, out["smoke"][p][pic], SMOKE_PAL,
                         out["feet_x"][0][p] + dx - SW // 2, out["feet_y"][0][p] - lines, v=v, height=h)
            for pic, tr in out["frags"]:
                st = tr[gf] if gf < FRAG_T else None
                if st:
                    blit(f, pic, dpal, st[0], st[1], hflip=st[2] & 1, vflip=st[2] & 2)
            if gf < FIRE_T:
                i, hz, v, h, left, top, mask = out["fire_tab"][gf]
                pic = out["fire"][i].copy()
                for c in range(FIRE_COLS):
                    if not mask >> c & 1:
                        pic[:, c * TILE:(c + 1) * TILE] = 0
                blit(f, pic, FIRE_PAL, left, top, hz=hz, v=v, height=h)
        stills.append(f)
    row1 = np.concatenate(stills[:len(stills) // 2 + 1], 1)
    row2 = np.concatenate(stills[len(stills) // 2 + 1:] + [bg] * (2 * (len(stills) // 2 + 1) - len(stills) - 1)
                          if len(stills) % 2 == 0 else stills[len(stills) // 2 + 1:] + [bg], 1)
    Image.fromarray(np.concatenate([row1, row2], 0)).save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("header")
    ap.add_argument("c1")
    ap.add_argument("c2")
    ap.add_argument("--preview")
    ap.add_argument("--over", help="a 320x224 game snapshot under the preview")
    args = ap.parse_args()
    out = build()
    T = write(out, args.header, args.c1, args.c2)
    if args.preview:
        preview(out, args.preview, args.over)
    worst = (BASELINE[None, :] + out["count"]).max(1)
    print(f"tiles {len(T.tiles)}, fragments {len(out['frags'])} of {len(out['pieces'])}, "
          f"worst line {worst.max()} (g {int(worst.argmax())}), ruin colours "
          f"{len(set(out['ruin'].ravel().tolist())) - 1}")


if __name__ == "__main__":
    main()
