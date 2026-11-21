"""
common.py — the card chrome: rounded panel, dot grid, one-pixel frame.

No motion lives here: each card carries its own, so a card is a single file that
animates on its own.
"""

from __future__ import annotations

import os
from string import Template

from svg.kit import dot_grid, linear_gradient, svg_open

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W = 860

BASE_CSS = Template("""
  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; opacity: 1 !important; }
  }
""")


def card_open(h: int, c: dict, *, uid: str, radius: int = 16, w: int = W,
              gradient: bool = True, solid: bool = False,
              dots_on_top: bool = False) -> str:
    """
    `solid` paints the panel at full opacity, so a card can predict the exact
    colour of its own background (the lids of the eye must be the panel colour).
    `dots_on_top` moves the dot grid above the contents, which is what makes a
    lid filled with that colour disappear completely.
    """
    return (
        svg_open(w, h)
        + "<defs>"
        + linear_gradient(f"bgline{uid}", [(0, c["line"], .9), (50, c["accent"], .45),
                                           (100, c["line"], .9)])
        + dot_grid(f"dots{uid}", c["dim"], .16 if c["mode"] == "dark" else .22)
        + f'<clipPath id="card{uid}"><rect x="0" y="0" width="{w}" height="{h}" '
          f'rx="{radius}"/></clipPath>'
        + "</defs>"
        + f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{radius}" '
          f'fill="{c["panel"]}" '
          f'fill-opacity="{1 if solid else (0.72 if c["mode"] == "dark" else 0.55)}" '
          f'stroke="{f"url(#bgline{uid})" if gradient else c["line"]}" '
          f'stroke-width="1"/>'
        + ("" if dots_on_top else
           f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{radius}" '
           f'fill="url(#dots{uid})"/>')
        + f'<g clip-path="url(#card{uid})">'
    )


def card_dots(h: int, c: dict, *, uid: str, radius: int = 16, w: int = W) -> str:
    """The dot grid, above the contents (see card_open(dots_on_top=True))."""
    return (f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{radius}" '
            f'fill="url(#dots{uid})"/>')


def card_close() -> str:
    return "</g></svg>"
