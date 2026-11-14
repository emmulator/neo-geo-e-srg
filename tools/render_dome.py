#!/usr/bin/env python3
"""render_dome.py SHEET.gif HEADER.h [--preview PNG --view N]

Renders E-SRG's 48 distinct dome views as "glass" pictures (filled front
faces shaded by a fixed light, faint back edges seen through them, glowing
front edges) into one indexed 16-colour sprite sheet, and writes the C
header mapping each view's 11 columns x 8 rows to C ROM tile numbers."""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402

SS = 4                                # supersampling
COLS, ROWS = g.DOME_W // 16, g.DOME_H // 16
TILE_BASE = 256

PALETTE = [
    (255, 0, 255),                                           # 0 transparent (key colour)
    (6, 14, 34), (10, 24, 52), (14, 36, 72), (20, 52, 96),   # 1-6 glass, dark to light
    (30, 70, 120), (44, 92, 144),
    (24, 60, 84),                                            # 7 back edge seen through glass
    (30, 90, 130), (40, 120, 165), (60, 150, 195),           # 8-10 glow ramp
    (90, 180, 220), (130, 205, 235), (175, 228, 245),        # 11-13
    (215, 242, 252), (250, 255, 255),                        # 14-15 core
]
GLASS = [PALETTE[i] for i in range(1, 7)]
BACK_EDGE = PALETTE[7]
EDGE_GLOW = PALETTE[9]
EDGE_CORE = PALETTE[15]
GLASS_ALPHA = 0.8


def layer():
    return Image.new("RGBA", (g.DOME_W * SS, g.DOME_H * SS), (0, 0, 0, 0))


def lines(img, segs, colour, width, alpha):
    d = ImageDraw.Draw(img)
    a = round(255 * alpha)
    for p, q in segs:
        d.line([tuple(p * SS), tuple(q * SS)], fill=colour + (a,), width=width)
        for c in (p, q):                    # round caps so joints don't notch
            r = width / 2
            d.ellipse([c[0] * SS - r, c[1] * SS - r, c[0] * SS + r, c[1] * SS + r],
                      fill=colour + (a,))


def render_view(v, pts, edges, faces, f):
    raw, world = g.project(pts, v)
    px = g.to_px(raw, f)
    vis = set(g.visible_edges(edges, faces, world))
    back = [(px[i], px[j]) for i, j in edges if (i, j) not in vis]
    front = [(px[i], px[j]) for i, j in vis]

    img = layer()
    lines(img, back, BACK_EDGE, 6, 1.0)
    glass = layer()
    d = ImageDraw.Draw(glass)
    for k in g.front_faces(faces, world):
        shade = round(5 * max(0.0, float(g.face_normal(world, faces[k]) @ g.LIGHT)))
        d.polygon([tuple(px[i] * SS) for i in faces[k]],
                  fill=GLASS[shade] + (round(255 * GLASS_ALPHA),))
    img = Image.alpha_composite(img, glass)
    glow = layer()
    lines(glow, front, EDGE_GLOW, 10, 0.6)
    img = Image.alpha_composite(img, glow)
    core = layer()
    lines(core, front, EDGE_CORE, 4, 1.0)
    img = Image.alpha_composite(img, core)
    return img.resize((g.DOME_W, g.DOME_H), Image.BOX)


def quantize(img):
    a = np.asarray(img).astype(float)
    rgb, alpha = a[..., :3], a[..., 3] / 255.0
    pal = np.array(PALETTE[1:], float)
    unpre = rgb.copy()                      # PIL's RGBA resize is premultiplied-correct
    dist = ((unpre[..., None, :] - pal[None, None]) ** 2).sum(-1)
    idx = dist.argmin(-1) + 1
    idx[alpha < 0.5] = 0
    return idx.astype(np.uint8)


def views():
    """the 48 quantized dome views (DOME_H x DOME_W palette-index arrays),
    exactly as the sheet stores them. render_broken.py builds its overlays
    from these pixels, so an overlay only ever paints what the dome draws as
    the cell's own glass."""
    pts, edges, faces = g.build_mesh()
    f = g.fit()
    out = []
    # PIL rasterises lines and polygons with a fixed tie rule at half-integer
    # pixel centres, so a view and its geometric mirror can differ by a few
    # anti-aliased edge pixels. Each view v is a true mirror pair with view
    # 48-v (the light sits in the mirror plane), so average the pair's renders
    # (v and the mirrored partner): the pairs become exactly mirror-symmetric
    # in the sheet, with the rasterisation noise halved. Quantize (pointwise)
    # commutes with the flip, so the equalities survive to the sheet.
    rendered = [render_view(v, pts, edges, faces, f) for v in range(g.VIEWS)]
    for v in range(g.VIEWS):
        img = rendered[v]
        mir = rendered[(g.VIEWS - v) % g.VIEWS].transpose(Image.FLIP_LEFT_RIGHT)
        sym = Image.blend(img.convert("RGBA"), mir.convert("RGBA"), 0.5)
        out.append(quantize(sym))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("header")
    ap.add_argument("--preview")
    ap.add_argument("--view", type=int, default=0)
    args = ap.parse_args()

    sheet = np.concatenate(views())
    im = Image.fromarray(sheet, "P")
    flat = [c for rgb in PALETTE for c in rgb]
    im.putpalette(flat)
    im.save(args.sheet)
    if args.preview:
        v = args.view
        pv = Image.fromarray(sheet[v * g.DOME_H:(v + 1) * g.DOME_H], "P")
        pv.putpalette(flat)
        pv.convert("RGB").resize((g.DOME_W * 3, g.DOME_H * 3), Image.NEAREST).save(args.preview)

    with open(args.header, "w") as h:
        h.write("/* generated by tools/render_dome.py: do not edit */\n")
        h.write(f"#define DOME_VIEWS {g.VIEWS}\n#define DOME_COLS {COLS}\n"
                f"#define DOME_ROWS {ROWS}\n#define DOME_TILE_BASE {TILE_BASE}\n")
        h.write("/* tile number of view v, column c, row r (top to bottom) */\n")
        h.write("static const u16 dome_tile[DOME_VIEWS][DOME_COLS][DOME_ROWS] = {\n")
        for v in range(g.VIEWS):
            h.write("  {")
            for c in range(COLS):
                t = [TILE_BASE + (v * ROWS + r) * COLS + c for r in range(ROWS)]
                h.write("{" + ",".join(map(str, t)) + "},")
            h.write("},\n")
        h.write("};\n")


if __name__ == "__main__":
    main()
