#!/usr/bin/env python3
"""geometry.py: E-SRG's dome (a Goldberg GP(5,0) cap, pentagon at the top) and
camera, copied from the Vectrex game's tools/gen_dome.py (v1.0.0), plus the
fit to the Neo Geo's dome box (DOME_W x DOME_H pixels)."""
import math
from collections import defaultdict

import numpy as np

FREQ = 5             # pentagon to pentagon = FREQ cell steps
# Dome-scenery Task 3: the dome's picture has a flat base. RIM_DEG is None
# and the sphere is cut by the plane y = cos(CAP_DEG); 69.59 deg is the
# lowest corner of the 76 whole cells (69.585), so the walkable cells do
# not change and the cut only adds partial picture pieces.
RIM_DEG = None       # if set: keep whole polygons whose centre is within RIM_DEG of the peak
CAP_DEG = 69.59      # only if RIM_DEG is None: polar angle of a flat cut
# The radar's roof is drawn to the Vectrex camera-facing rim, a separate
# constant from the dome's picture: Task 3's flat cut does not move the
# radar (render_radar.py reads this; its pictures stay byte-identical).
RADAR_RIM_DEG = 63.5
CAM_ELEV_DEG = 38.0  # camera elevation, seen from the sphere centre
CAM_DIST = 2.6       # camera distance from the sphere centre (radius 1)
LOOK_Y = 0.55        # the camera looks at (0, LOOK_Y, 0)
STEPS = 240          # rotation steps per turn
VIEWS = STEPS // 5   # distinct views (5-fold symmetry)

# ---- the dome's one size knob (the dome-scenery plan's Task 1) ----
# The box the dome's sprites are laid out in: DOME_COLS 16-px sprite
# columns by DOME_ROWS 16-px tiles. The rendered dome is DOME_SCALE times
# the size of the scale that fills a full 11x8 = 176x128 box, so shrinking
# the box alone does NOT shrink the dome (the render stays the same size,
# with more margin round it); DOME_SCALE alone does. Every picture and
# table that depends on the dome's size reads fit(); the C side reads the
# box from build/dome_map.h (DOME_COLS/DOME_ROWS), generated here.
DOME_COLS = 8        # sprite columns (16 px each): 2/3 of the reference 11
DOME_ROWS = 6        # tiles tall (16 px each): 2/3 of the reference 8
DOME_SCALE = 2 / 3   # the dome's render size, x the full box's fit
DOME_W = 16 * DOME_COLS   # the dome box on the Neo Geo ...
DOME_H = 16 * DOME_ROWS   # ... in pixels
MARGIN = 2.0         # px kept clear inside the box (room for the edge glow)

# Legacy light for the ship and missiles (they keep the old upper-behind
# light, so their pictures do not change). The DOME's light is
# render_dome.LIGHT: the upper left, slightly behind, chosen with the user
# from a mockup (Dome-scenery Task 3).
LIGHT = np.array([0.0, 1.0, 0.6])
LIGHT = LIGHT / np.linalg.norm(LIGHT)

# ---- copied verbatim from vectrex-e-srg tools/gen_dome.py ----
# rot_to, build_mesh, camera, project, visible_edges


def rot_to(a, b):
    """rotation matrix taking unit vector a onto unit vector b."""
    v, c = np.cross(a, b), a @ b
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)


def build_mesh():
    """Goldberg cap: points [n,3] at rotation 0, edges (index pairs), faces (index polygons)."""
    t = (1 + 5 ** 0.5) / 2
    ico = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t],
                    [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    ico /= np.linalg.norm(ico, axis=1, keepdims=True)
    ifaces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
              (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
              (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    # vertex 0 (a pentagon centre of the dual) onto +Y, then its neighbour 1
    # onto the x = 0 plane: that plane is then a mirror plane of the mesh
    ico = ico @ rot_to(ico[0], np.array([0.0, 1.0, 0.0])).T
    az = math.atan2(ico[1][0], ico[1][2])
    ry = np.array([[math.cos(az), 0, -math.sin(az)], [0, 1, 0], [math.sin(az), 0, math.cos(az)]])
    ico = ico @ ry.T
    assert abs(ico[1][0]) < 1e-9

    gpts, gid, tris = [], {}, []           # geodesic sphere (primal)

    def gp(p):
        p = p / np.linalg.norm(p)
        key = tuple(np.round(p, 6))
        if key not in gid:
            gid[key] = len(gpts)
            gpts.append(p)
        return gid[key]
    n = FREQ
    for ia, ib, ic in ifaces:
        A, B, C = ico[ia], ico[ib], ico[ic]
        P = {(i, j): gp(A + (B - A) * i / n + (C - A) * j / n)
             for i in range(n + 1) for j in range(n + 1 - i)}
        for i in range(n):
            for j in range(n - i):
                tris.append((P[i, j], P[i + 1, j], P[i, j + 1]))
                if i + j < n - 1:
                    tris.append((P[i + 1, j], P[i + 1, j + 1], P[i, j + 1]))
    gpts = np.array(gpts)

    # dual: a point per triangle (centroid pushed to the sphere), a face per primal vertex
    dpts = np.array([gpts[list(tr)].mean(axis=0) for tr in tris])
    dpts /= np.linalg.norm(dpts, axis=1, keepdims=True)
    around = defaultdict(list)
    for ti, tr in enumerate(tris):
        for v in tr:
            around[v].append(ti)
    y0 = math.cos(math.radians(CAP_DEG))
    pts, pid = [], {}

    def pt(p):
        key = tuple(np.round(p, 6))
        if key not in pid:
            pid[key] = len(pts)
            pts.append(p)
        return pid[key]
    faces = []
    for v, tlist in around.items():
        c = gpts[v]
        e1 = np.cross(c, [0.3, 0.5, 0.7])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(c, e1)
        poly = [dpts[ti] for ti in sorted(tlist, key=lambda ti: math.atan2(dpts[ti] @ e2, dpts[ti] @ e1))]
        if RIM_DEG is not None:             # whole polygons only
            m = np.mean(poly, axis=0)
            if math.degrees(math.acos(min(1.0, m[1] / np.linalg.norm(m)))) <= RIM_DEG + 0.01:
                faces.append([pt(p) for p in poly])
            continue
        out = []                            # clip to y >= y0 (Sutherland-Hodgman)
        for k in range(len(poly)):
            P, Q = poly[k], poly[(k + 1) % len(poly)]
            if P[1] >= y0:
                out.append(P)
            if (P[1] >= y0) != (Q[1] >= y0):
                lo, hi = (P, Q) if tuple(P) < tuple(Q) else (Q, P)   # same point for both faces
                out.append(lo + (hi - lo) * (y0 - lo[1]) / (hi[1] - lo[1]))
        if len(out) >= 3:
            ids = [pt(p) for p in out]
            faces.append([i for k, i in enumerate(ids) if i != ids[k - 1]])
    edges = set()
    for f in faces:
        for k in range(len(f)):
            u, w = f[k], f[(k + 1) % len(f)]
            edges.add((min(u, w), max(u, w)))
    return np.array(pts), sorted(edges), faces


def camera():
    e = math.radians(CAM_ELEV_DEG)
    pos = np.array([0.0, CAM_DIST * math.sin(e), CAM_DIST * math.cos(e)])
    fwd = np.array([0.0, LOOK_Y, 0.0]) - pos
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 1, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    return pos, fwd, right, up


def project(pts, step):
    """raw (unscaled) screen coords [n,2] and rotated world points [n,3]."""
    pos, fwd, right, up = camera()
    a = 2 * math.pi * step / STEPS
    rot = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    world = pts @ rot.T
    d = world - pos
    z = d @ fwd
    return np.column_stack([d @ right / z, d @ up / z]), world


def visible_edges(edges, faces, world):
    """Exact hidden-line removal for a convex polyhedron: an edge is visible
    iff at least one face using it faces the camera."""
    pos = camera()[0]
    front = set()
    for f in faces:
        P = world[list(f)]
        n = sum(np.cross(P[k], P[(k + 1) % len(P)]) for k in range(len(P)))   # Newell normal
        ctr = P.mean(axis=0)
        if n @ ctr < 0:                     # orient outward (the cap is convex around the origin)
            n = -n
        if n @ (pos - ctr) > 0:
            for k in range(len(f)):
                u, v = f[k], f[(k + 1) % len(f)]
                front.add((min(u, v), max(u, v)))
    return [e for e in edges if e in front]

# ---- end of copied geometry ----


def face_normal(world, face):
    """outward unit normal (Newell), oriented away from the sphere centre."""
    P = world[list(face)]
    n = sum(np.cross(P[k], P[(k + 1) % len(P)]) for k in range(len(P)))
    if n @ P.mean(axis=0) < 0:
        n = -n
    return n / np.linalg.norm(n)


def front_faces(faces, world):
    pos = camera()[0]
    return [k for k, f in enumerate(faces)
            if face_normal(world, f) @ (pos - world[list(f)].mean(axis=0)) > 0]


# the reference box: 11 x 8 tiles. The full-box fit below is the size the
# dome has always had; DOME_SCALE scales that render, not the box.
REF_W = 16 * 11
REF_H = 16 * 8


def whole_cells(pts, faces):
    """The walkable cells (the 76 whole polygons; with a flat cut, the
    whole ones whose centre is clear of the cut) as [(face, centre), ...]
    sorted peak first. The partial pieces cut by the flat base are NOT
    cells: they are only part of the dome's picture."""
    y0 = math.cos(math.radians(CAP_DEG))
    cells = []
    for f in faces:
        P = pts[list(f)]
        c = P.mean(axis=0)
        c /= np.linalg.norm(c)
        if RIM_DEG is None and (len(f) < 5 or np.any(np.abs(P[:, 1] - y0) < 1e-6)
                                or math.degrees(math.acos(min(1.0, c[1]))) > CAP_DEG - CELL_RIM_MARGIN_DEG):
            continue                                             # clipped by / too near the cut
        cells.append((f, c))
    cells.sort(key=lambda fc: -fc[1][1])                         # peak first
    return cells


def fit():
    """(scale, ox, oy): raw -> px = (raw.x * scale + ox, oy - raw.y * scale).

    The dome is rendered at DOME_SCALE times the scale that fills the
    reference 176x128 box (the widest view spans REF_W - 2*MARGIN, the
    lowest point sits MARGIN above the bottom), centred in the actual
    DOME_W x DOME_H box. The scaled dome must fit inside the box with
    MARGIN on each side; a box too small for DOME_SCALE fails here.

    The reference scale is computed from the 76-CELL mesh, not from the
    flat-based picture: the picture's partial pieces reach barely lower
    (their bottom is the cut plane), but the task keeps the size exactly
    as it was (Dome-scenery Task 3)."""
    pts, _, faces = build_mesh()
    used = sorted({i for f, _ in whole_cells(pts, faces) for i in f})
    cell_pts = pts[used]
    allraw = np.vstack([project(cell_pts, s)[0] for s in range(VIEWS)])
    ref = (REF_W / 2 - MARGIN) / np.abs(allraw[:, 0]).max()
    scale = DOME_SCALE * ref
    width = (allraw[:, 0].max() - allraw[:, 0].min()) * scale
    height = (allraw[:, 1].max() - allraw[:, 1].min()) * scale
    assert width <= DOME_W - 2 * MARGIN, \
        f"dome too wide for the box: {width:.1f} px in {DOME_W} (MARGIN {MARGIN})"
    assert height <= DOME_H - 2 * MARGIN, \
        f"dome too tall for the box: {height:.1f} px in {DOME_H} (MARGIN {MARGIN})"
    return scale, DOME_W / 2, DOME_H - MARGIN + allraw[:, 1].min() * scale


def to_px(raw, f):
    scale, ox, oy = f
    return np.column_stack([raw[:, 0] * scale + ox, oy - raw[:, 1] * scale])


# ---- the ship and the movement tables: copied verbatim from vectrex-e-srg
# tools/gen_dome.py (v1.0.0): the constants they read, then ship_model,
# ship_visible_edges and make_cells ----
SHIP_STEPS = 48               # latitude views; the lowest is the lowest cell centre
SHIP_MAX_DEG = None           # set from the cells (see make_cells)
CELL_RIM_MARGIN_DEG = 3.0     # flat cut only: a cell is walkable if whole and its centre this far above the cut
STICK_DIRS = 32               # stick directions (11.25 deg each), 0 = right, 8 = up
STICK_DEAD = 40               # analog stick dead zone (of 127)
SHIP_LEN = 0.15              # nose to tail, in sphere radii
SHIP_WIDTH = 0.12            # across the tail
SHIP_HEIGHT = 0.09           # apex above the surface


def ship_model(theta):
    """Pyramid on the front meridian at polar angle theta: points [4,3], faces."""
    p = np.array([0.0, math.cos(theta), math.sin(theta)])   # surface point; normal = p
    fwd = np.array([0.0, math.sin(theta), -math.cos(theta)])  # tangent toward the peak
    side = np.cross(p, fwd)
    nose = p + fwd * (SHIP_LEN * 0.6)
    tl = p - fwd * (SHIP_LEN * 0.4) + side * (SHIP_WIDTH / 2)
    tr = p - fwd * (SHIP_LEN * 0.4) - side * (SHIP_WIDTH / 2)
    apex = p - fwd * (SHIP_LEN * 0.1) + p * SHIP_HEIGHT
    pts = np.array([nose, tl, tr, apex])
    faces = [[0, 1, 2], [3, 0, 1], [3, 1, 2], [3, 2, 0]]      # base first
    return pts, faces


def ship_visible_edges(pts, faces):
    """Edges of the faces that face the camera (a pyramid is convex)."""
    pos = camera()[0]
    ctr = pts.mean(axis=0)
    out = set()
    for f in faces:
        P = pts[f]
        n = np.cross(P[1] - P[0], P[2] - P[0])
        fc = P.mean(axis=0)
        if n @ (fc - ctr) < 0:
            n = -n
        if n @ (pos - fc) > 0:
            for k in range(len(f)):
                u, v = f[k], f[(k + 1) % len(f)]
                out.add((min(u, v), max(u, v)))
    return sorted(out)


def make_cells(pts, faces):
    """Walkable cells (every polygon; with a flat cut, the whole ones whose
    centre is clear of the cut) and the
    movement tables. Cell 0 is the peak pentagon. A cell's centre is the
    normalised mean of its corners. Returns a dict of tables for dome_data."""
    global SHIP_MAX_DEG
    cells = whole_cells(pts, faces)
    assert len(cells[0][0]) == 5 and cells[0][1][1] > 0.999, "cell 0 must be the peak pentagon"
    centres = [c for _, c in cells]
    theta = [math.acos(min(1.0, c[1])) for c in centres]
    phi = [math.atan2(c[0], c[2]) for c in centres]
    SHIP_MAX_DEG = math.degrees(max(theta))
    lat = [round(t / max(theta) * (SHIP_STEPS - 1)) for t in theta]
    step = [round(-p * STEPS / (2 * math.pi)) % STEPS for p in phi]
    step[0] = 0
    # neighbours: cells sharing an edge
    edge_cells = defaultdict(list)
    for i, (f, _) in enumerate(cells):
        for k in range(len(f)):
            u, v = f[k], f[(k + 1) % len(f)]
            edge_cells[(min(u, v), max(u, v))].append(i)
    nbrs = defaultdict(set)
    for cs in edge_cells.values():
        if len(cs) == 2:
            nbrs[cs[0]].add(cs[1])
            nbrs[cs[1]].add(cs[0])
    pos, fwd, right, up = camera()

    def screen_dir(a, b, rot):
        """screen angle of the move a -> b with the dome turned by `rot` radians."""
        R = np.array([[math.cos(rot), 0, math.sin(rot)], [0, 1, 0], [-math.sin(rot), 0, math.cos(rot)]])
        q = []
        for c in (centres[a], centres[b]):
            d = R @ c - pos
            z = d @ fwd
            q.append(np.array([d @ right / z, d @ up / z]))
        v = q[1] - q[0]
        return math.atan2(v[1], v[0])
    # per cell, the best neighbour for each stick direction (within 45 deg)
    nbr_tab = []
    for i in range(len(cells)):
        row = []
        dirs = [(screen_dir(i, j, -phi[i]), j) for j in nbrs[i]] if i else []
        for d in range(STICK_DIRS):
            want = 2 * math.pi * d / STICK_DIRS
            best = min(dirs, key=lambda aj: abs((aj[0] - want + math.pi) % (2 * math.pi) - math.pi),
                       default=None)
            ok = best and abs((best[0] - want + math.pi) % (2 * math.pi) - math.pi) <= math.radians(45)
            row.append(best[1] if ok else 255)
        nbr_tab.append(row)
    # stored instead: per cell its neighbours and their screen directions (in
    # 1/256 turn); the game picks the nearest to the stick (cell_toward in
    # e-srg.c, modelled here) less than 45 degrees (32/256) off
    adj = []
    for i in range(len(cells)):
        dirs = [(round(screen_dir(i, j, -phi[i]) / (2 * math.pi) * 256) % 256, j)
                for j in sorted(nbrs[i])]          # (the peak's: for the collapse rule only)
        assert len(dirs) <= 6
        adj.append(dirs + [(0, 255)] * (6 - len(dirs)))
    differ = 0
    for i in range(1, len(cells)):
        for d in range(STICK_DIRS):
            best, bd = 255, 32
            for a, j in adj[i]:
                if j == 255:
                    break
                e = (a - d * 8) & 255
                e = 256 - e if e & 128 else e
                if e < bd:
                    best, bd = j, e
            differ += best != nbr_tab[i][d]
            nbr_tab[i][d] = best
    # the peak: "down" goes to the ring cell nearest the front for the current spin
    peak_down = []
    ring = sorted(nbrs[0])
    for st in range(STEPS // 5):
        rot = 2 * math.pi * st / STEPS
        peak_down.append(min(ring, key=lambda j: abs((phi[j] + rot + math.pi) % (2 * math.pi) - math.pi)))
    # analog stick (x, y) -> direction, on a 32x32 grid of the -128..127
    # range; stored for one quadrant (16x16, x, y > 0): the game mirrors it
    def sdir(x, y):
        if math.hypot(x, y) < STICK_DEAD:
            return 255
        return round(math.atan2(y, x) / (2 * math.pi) * STICK_DIRS) % STICK_DIRS
    stick = [sdir(4 + 8 * ax, 4 + 8 * ay) for ay in range(16) for ax in range(16)]
    for gy in range(32):                 # the mirroring must reproduce the full grid
        for gx in range(32):
            ax, ay = (gx - 16, gy - 16) if False else (gx - 16 if gx >= 16 else 15 - gx,
                                                     gy - 16 if gy >= 16 else 15 - gy)
            d = stick[ay * 16 + ax]
            if d != 255:
                if gx < 16:
                    d = (STICK_DIRS // 2 - d) % STICK_DIRS
                if gy < 16:
                    d = (STICK_DIRS - d) % STICK_DIRS
            want = sdir(gx * 8 - 124, gy * 8 - 124)
            assert d == want or (d - want) % STICK_DIRS in (1, STICK_DIRS - 1), (gx, gy, d, want)
    print(f"moves: runtime pick differs from exact angles in {differ} of {(len(cells) - 1) * STICK_DIRS} cases (ties, or right at 45 deg)")
    return dict(n=len(cells), step=step, lat=lat, nbr=nbr_tab, adj=adj, peak_down=peak_down, stick=stick,
                theta=theta, nbrs=nbrs)

# ---- end of copied ship and movement tables ----
