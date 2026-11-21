#!/usr/bin/env python3
"""
avatar.py — turns the profile picture into ANSI art with a living gaze.

The picture is downsampled to a character grid (one *ordinary* ASCII character
per cell — no shade blocks: the density comes from the glyph itself), colour-
quantised per cell and rounded off with a circular mask, so the result reads as
an eye instead of a photo shrunk into letters.

Five cell maps are generated from the same image: the iris disk is rolled left,
right, up and down, and the colours are re-sampled each time. The SVG swaps
between them on a timeline, which gives a real gaze instead of a fake one.

Nothing is ever drawn on top of the portrait: the animation is the iris moving,
and the cells that carry no ink are simply absent.

Output: assets/readme/data/avatar.json
"""

from __future__ import annotations

import base64
import json
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get("AVATAR_SRC",
                    os.path.join(ROOT, "assets/readme/photo/eye.png"))
OUT = os.path.join(ROOT, "assets/readme/data/avatar.json")

COLS, ROWS = 44, 24      # 8x16 cells -> 352x384, a rounder portrait
SUPERSAMPLE = 4
DITHER = 52.0   # how hard the cube is pushed
LIFT = 1.16     # screen light vs paper light

# ── the xterm-256 palette ────────────────────────────────────────────────────
# A terminal with 256 colours is not "any RGB": it is this table. Cells 0-15 are
# the system colours, 16-231 a 6x6x6 cube (steps of 0x33, offset 0x37) and
# 232-255 a 24-step grey ramp. Building the same table means the portrait draws
# itself with SGR codes, and a real terminal could print it.
_SYS = ["#000000", "#800000", "#008000", "#808000", "#000080", "#800080",
        "#008080", "#c0c0c0", "#808080", "#ff0000", "#00ff00", "#ffff00",
        "#0000ff", "#ff00ff", "#00ffff", "#ffffff"]
_STEPS = [0, 0x5f, 0x87, 0xaf, 0xd7, 0xff]


def xterm256() -> list[str]:
    out = list(_SYS)
    for r in _STEPS:
        for g in _STEPS:
            for b in _STEPS:
                out.append(f"#{r:02x}{g:02x}{b:02x}")
    for i in range(24):
        v = 8 + i * 10
        out.append(f"#{v:02x}{v:02x}{v:02x}")
    return out

# Ordered by ink: a bright cell is a dense character, a dark one is faint.
# Deliberately short — with 256 colours the *colour* carries the tone, and a
# long ramp turns the portrait into a page of random text instead of a picture.
RAMP = " .:-=+*#%@"
LADDER = len(RAMP)


def _kmeans(pixels: np.ndarray, k: int, iters: int = 16) -> np.ndarray:
    rng = np.random.default_rng(7)
    centers = pixels[rng.choice(len(pixels), k, replace=False)].astype(float)
    for _ in range(iters):
        d = ((pixels[:, None, :] - centers[None]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        for i in range(k):
            sel = pixels[lab == i]
            if len(sel):
                centers[i] = sel.mean(axis=0)
    return centers


def _square(im: Image.Image) -> Image.Image:
    side = min(im.size)
    return im.crop(((im.width - side) // 2, (im.height - side) // 2,
                    (im.width + side) // 2, (im.height + side) // 2))


def _grid(im: Image.Image) -> np.ndarray:
    return np.asarray(im.resize((COLS, ROWS), Image.LANCZOS)).astype(float)


def build(src: str = SRC) -> dict:
    im = _square(Image.open(src).convert("RGB"))   # RGBA is fine: alpha dropped
    big = _grid(im)

    # A cell is 8x16, so a circle in pixels is an ellipse two cells wide per
    # cell of height. Masking in cell space with a plain radius would squash
    # the portrait into a tall egg.
    yy, xx = np.mgrid[0:ROWS, 0:COLS]
    cx, cy = (COLS - 1) / 2, (ROWS - 1) / 2
    rx, ry = cx + 0.5, cy + 0.5
    dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    mask = dist <= 1.0
    mask[:2, :] = False                    # the eyebrow arc reads as a halo
    mask[ROWS - 2:, :] = False             # and the lower lid as a smear

    edge = (dist > 0.92) & mask
    iris = dist <= 0.62                     # the iris: what visibly moves

    # The 256 colours of the terminal. Every cell keeps the colour the photo
    # actually has at that point, snapped to the nearest cell of the palette:
    # the iris stays olive where it is olive, the highlight stays blue-white,
    # and the falloff between them becomes a gradient instead of four steps.
    term = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in xterm256()],
                    dtype=float)
    hexes = xterm256()

    def cells_for(iris_shift: tuple[int, int],
                  body_shift: tuple[int, int] = (0, 0)) -> list:
        """
        `iris_shift` rolls the iris, `body_shift` rolls the whole picture.

        Both are in cells, and that is the point: the entire eye follows the
        look *inside the character grid*. Animating the portrait with CSS
        transforms moves the glyphs off the grid and the terminal stops looking
        like a terminal.
        """
        img = big.copy()
        by, bx = body_shift
        if by or bx:
            img = np.roll(np.roll(img, by, axis=0), bx, axis=1)
        dy, dx = iris_shift
        if dy or dx:
            rolled = np.roll(np.roll(big, dy, axis=0), dx, axis=1)
            img = np.where(iris[:, :, None], rolled, img)      # the iris, on top
        # A 6x6x6 cube only has six levels per channel, so a smooth photograph
        # would band. Ordered (Bayer) dithering pushes each cell toward one of
        # its two neighbouring cells of the cube, which is exactly what a
        # 256-colour terminal does to fake the tones it does not have.
        order = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                          [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 - 0.5
        tile = np.tile(order, (ROWS // 4 + 1, COLS // 4 + 1))[:ROWS, :COLS]
        # A terminal prints colour, not light: the photo's shadows would go
        # black on screen, so the value is lifted a little before snapping.
        lit = np.clip(img * LIFT + tile[:, :, None] * DITHER, 0, 255)
        d = ((lit[:, :, None, :] - term[None, None]) ** 2).sum(axis=3)
        idx = d.argmin(axis=2)

        # Glyph density from two maps, not one: the overall brightness (so the
        # picture keeps its shape) and the local detail (so the iris ring, the
        # pupil edge and the lashes survive the trip to 44 x 24 characters).
        # A photograph is mostly local contrast; without it the portrait reads
        # as one green smudge.
        lum = img.mean(axis=2)
        k = 2               # a 5x5 average: cells are coarse, keep the edges
        pad = np.pad(lum, k, mode="edge")
        soft = sum(pad[dy:dy + ROWS, dx:dx + COLS]
                   for dy in range(2 * k + 1)
                   for dx in range(2 * k + 1)) / (2 * k + 1) ** 2
        detail = lum - soft
        pad = np.pad(detail, 1, mode="edge")
        detail = sum(pad[dy:dy + ROWS, dx:dx + COLS]
                     for dy in range(3) for dx in range(3)) / 9

        def rank(a: np.ndarray) -> np.ndarray:
            vals = a[mask]
            order = vals.argsort().argsort() / max(1, len(vals) - 1)
            out = np.zeros_like(a)
            out[mask] = order
            return out

        w = 0.55            # how much of the local detail survives
        norm = (1 - w) * rank(lum) + w * rank(detail)

        rows = []
        for y in range(ROWS):
            row = []
            for x in range(COLS):
                # Dark cells near the rim are the sclera shadow and the lid:
                # on a terminal they read as a plate around the eye, so they
                # are dropped and the panel shows through. The pupil is dark
                # too but sits in the middle, so it stays.
                if not mask[y, x] or (norm[y, x] < 0.10 and dist[y, x] > 0.86):
                    row.append(None)
                    continue
                v = norm[y, x]
                glyph = min(LADDER - 1, int(v * LADDER))
                if edge[y, x]:
                    glyph = 1                       # a light rim: '.'
                row.append([int(idx[y, x]), glyph])
            rows.append(row)
        return rows

    # The ladder: ordinary characters ordered by how much ink they put on the
    # paper. The terminal draws the cells; the portrait is letters, not blocks.
    # (Density comes from `norm`, which mixes brightness with local detail.)
    LEVELS = LADDER

    # Which cells belong to the iris. The card draws the base once and swaps
    # only this patch; the rest of the portrait never changes.
    iris_mask = base64.b64encode(bytes(
        1 if iris[y, x] else 0 for y in range(ROWS) for x in range(COLS))).decode()

    def encode(rows: list) -> str:
        """Two bytes per cell: xterm colour index, then ink level."""
        raw = bytearray()
        for row in rows:
            for cell in row:
                if cell is None:
                    raw += b"\xee\xee"        # the panel shows through
                else:
                    raw += bytes((cell[0], cell[1]))
        return base64.b64encode(bytes(raw)).decode()

    # Twelve frames, one cell apart: this is what "more frames" means for a
    # portrait made of characters. Sliding glyphs between cells only produced a
    # translucent double image, so the gaze is baked at every step instead.
    # The second tuple is the *body*: past one cell of look, the whole eye leans
    # that way too, which is what makes the picture feel alive as a whole.
    poses = {"l1": ((0, -1), (0, 0)), "l2": ((0, -2), (0, -1)),
             "l3": ((0, -3), (0, -1)), "r1": ((0, 1), (0, 0)),
             "r2": ((0, 2), (0, 1)), "r3": ((0, 3), (0, 1)),
             "u1": ((-1, 0), (0, 0)), "u2": ((-2, 0), (-1, 0)),
             "d1": ((1, 0), (0, 0)), "d2": ((2, 0), (1, 0)),
             "g1": ((-1, 1), (0, 0)), "g2": ((-1, -1), (0, -1))}
    centre = cells_for((0, 0), (0, 0))
    maps = {name: cells_for(*shifts) for name, shifts in poses.items()}

    return {
        "src": os.path.basename(src),
        "cols": COLS, "rows": ROWS,
        "palette": hexes,
        "colours_used": len({c[0] for row in centre for c in row if c}),
        "levels": LEVELS,
        "ramp": RAMP,
        "centre": encode(centre),
        "look": {name: encode(rows) for name, rows in maps.items()},
        "iris": iris_mask,
        "iris_r": 0.62,
    }


def main() -> None:
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    raw = base64.b64decode(data["centre"])
    filled = sum(1 for i in range(0, len(raw), 2) if raw[i] != 0xEE)
    print(f"✓ avatar.json · {data['cols']}×{data['rows']} "
          f"({filled} cells painted) · {data['colours_used']} of 256 colours · "
          f"{os.path.getsize(OUT)/1024:.1f} kB")
    if os.environ.get("AVATAR_DEBUG") == "1":
        shapes = ".,:-#"
        for y in range(data["rows"]):
            line = ""
            for x in range(data["cols"]):
                i = 2 * (y * data["cols"] + x)
                col, ink = raw[i], raw[i + 1]
                line += " " if col == 0xEE else shapes[min(4, ink // 3)]
            print(line)


if __name__ == "__main__":
    main()
