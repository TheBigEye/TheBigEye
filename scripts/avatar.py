#!/usr/bin/env python3
"""
avatar.py — turns the profile picture into ANSI art with a living gaze.

The picture is downsampled to a character grid (one CP437 block glyph per cell),
colour-quantised per cell and rounded off with a circular mask, so the result
reads as an eye instead of a photo shrunk into letters.

Five cell maps are generated from the same image: the iris disk is rolled left,
right, up and down, and the colours are re-sampled each time. The SVG swaps
between them on a timeline, which gives a real gaze instead of a fake one.

Nothing is drawn on top of the portrait: a blink is the terminal clearing its
own rows, in the card, with the panel colour.

Output: assets/readme/data/avatar.json
"""

from __future__ import annotations

import base64
import json
import os

import colorsys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get("AVATAR_SRC", "/home/user/uploads/63316583.jpg")
OUT = os.path.join(ROOT, "assets/readme/data/avatar.json")

COLS, ROWS = 40, 20      # 8x16 cells -> a square 320x320 block
COLOURS = 10
SUPERSAMPLE = 4


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
    im = _square(Image.open(src).convert("RGB"))
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
    iris = dist <= 0.62                     # the part that moves when looking

    palette = _kmeans(big[mask].reshape(-1, 3), COLOURS)
    # The picture sits on a dark plate, so every swatch has to carry itself:
    # no near-blacks, and enough saturation that the iris still reads as green.
    lifted = []
    for r, g, b in palette:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        h = 0.28 + (h - 0.28) * 0.55          # pull the olive toward iris green
        lifted.append(np.array([h % 1.0, min(1.0, s * 1.9), 0.14 + 0.88 * v]))
    palette = np.array([np.array(colorsys.hsv_to_rgb(*c)) * 255 for c in lifted])
    hexes = ["#%02x%02x%02x" % tuple(int(v) for v in np.clip(c, 0, 255))
             for c in palette]

    def cells_for(shift: tuple[int, int]) -> list:
        """`shift` is (dy, dx): the iris is rolled that many cells."""
        img = big.copy()
        dy, dx = shift
        if dy or dx:
            rolled = np.roll(np.roll(img, dy, axis=0), dx, axis=1)
            img = np.where(iris[:, :, None], rolled, img)      # only the iris moves
        d = ((img[:, :, None, :] - palette[None, None]) ** 2).sum(axis=3)
        idx = d.argmin(axis=2)

        # Glyph density by rank, not by linear brightness: a photo has most of
        # its cells in the dark end, so equal bands are what keeps the texture.
        lum = img.mean(axis=2)
        vals = lum[mask]
        order = vals.argsort().argsort() / max(1, len(vals) - 1)
        norm = np.zeros_like(lum)
        norm[mask] = order

        rows = []
        for y in range(ROWS):
            row = []
            for x in range(COLS):
                # Dark cells near the rim are the sclera shadow and the lid:
                # on a terminal they read as a plate around the eye, so they
                # are dropped and the panel shows through. The pupil is dark
                # too but sits in the middle, so it stays.
                if not mask[y, x] or (norm[y, x] < 0.22 and dist[y, x] > 0.70):
                    row.append(None)
                    continue
                v = norm[y, x]
                glyph = min(4, int(v * 4.999))      # density, not a character
                if edge[y, x]:
                    glyph = 1
                row.append([int(idx[y, x]), glyph])
            rows.append(row)
        return rows

    LEVELS = 5

    # Which cells belong to the iris. The SVG draws the fixed part once and
    # swaps only this patch, otherwise three full maps triple the file size.
    iris_mask = base64.b64encode(bytes(
        1 if iris[y, x] else 0 for y in range(ROWS) for x in range(COLS))).decode()

    def encode(rows: list) -> str:
        raw = bytearray()
        for row in rows:
            for cell in row:
                if cell is None:
                    raw.append(0xEE)
                else:
                    raw.append((cell[0] << 4) | cell[1])
        return base64.b64encode(bytes(raw)).decode()

    return {
        "src": os.path.basename(src),
        "cols": COLS, "rows": ROWS,
        "palette": hexes,
        "levels": LEVELS,
        # Poses, cheapest first: the fixed part is drawn once and only the iris
        # patch is swapped, so each extra direction is a small file on its own.
        "look": {
            "l1": encode(cells_for((0, -2))),
            "l2": encode(cells_for((0, -3))),
            "r1": encode(cells_for((0, 2))),
            "r2": encode(cells_for((0, 3))),
            "u1": encode(cells_for((-2, 0))),
            "d1": encode(cells_for((2, 0))),
            "g1": encode(cells_for((-2, 2))),    # up and to the right
            "g2": encode(cells_for((-2, -2))),   # up and to the left
        },
        "centre": encode(cells_for((0, 0))),
        "iris": iris_mask,
        "iris_r": 0.62,
    }


def main() -> None:
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    filled = sum(1 for r in data["centre"] for c in r if c)
    print(f"✓ avatar.json · {data['cols']}×{data['rows']} "
          f"({filled} cells inside the mask) · {len(data['palette'])} colours · "
          f"{os.path.getsize(OUT)/1024:.1f} kB")
    if os.environ.get("AVATAR_DEBUG") == "1":
        shapes = ".,:-#"
        raw = base64.b64decode(data["centre"])
        for y in range(data["rows"]):
            line = ""
            for x in range(data["cols"]):
                b = raw[y * data["cols"] + x]
                line += " " if b == 0xEE else shapes[b & 0x0F]
            print(line)


if __name__ == "__main__":
    main()
