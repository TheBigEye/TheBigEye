"""
ascii.py — the VGA text layer.

Renders text with the *real* Linux console font (VGA 8x16, the one cpi2fnt
produces for the kernel, extracted from lib/fonts/font_8x16.c). Every glyph is
turned into a path of horizontal runs once, emitted in <defs>, and then reused
with <use>, which keeps the payload small even with thousands of characters.

Cell grid: 8 x 16 px, integer scaling only — anything else would blur the
bitmap, and blurring a VGA font defeats the point.
"""

from __future__ import annotations

import base64
import json
import os
import re

FONT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "assets/readme/fonts/vga8x16.json")

CW, CH = 8, 16          # cell size in font pixels


# Unicode -> CP437, so the cards can be written with box-drawing characters and
# still come out as real VGA glyphs.
CP437 = {
    "☺": 0x01, "☻": 0x02, "♥": 0x03, "♦": 0x04, "♣": 0x05, "♠": 0x06, "•": 0x07,
    "◘": 0x08, "○": 0x09, "◙": 0x0A, "♂": 0x0B, "♀": 0x0C, "♪": 0x0D, "♫": 0x0E,
    "☼": 0x0F, "►": 0x10, "◄": 0x11, "↕": 0x12, "‼": 0x13, "¶": 0x14, "§": 0x15,
    "▬": 0x16, "↨": 0x17, "↑": 0x18, "↓": 0x19, "→": 0x1A, "←": 0x1B, "∟": 0x1C,
    "↔": 0x1D, "▲": 0x1E, "▼": 0x1F, "⌂": 0x7F,
    "Ç": 0x80, "ü": 0x81, "é": 0x82, "â": 0x83, "ä": 0x84, "à": 0x85, "å": 0x86,
    "ç": 0x87, "ê": 0x88, "ë": 0x89, "è": 0x8A, "ï": 0x8B, "î": 0x8C, "ì": 0x8D,
    "Ä": 0x8E, "Å": 0x8F, "É": 0x90, "æ": 0x91, "Æ": 0x92, "ô": 0x93, "ö": 0x94,
    "ò": 0x95, "û": 0x96, "ù": 0x97, "ÿ": 0x98, "Ö": 0x99, "Ü": 0x9A, "¢": 0x9B,
    "£": 0x9C, "¥": 0x9D, "₧": 0x9E, "ƒ": 0x9F, "á": 0xA0, "í": 0xA1, "ó": 0xA2,
    "ú": 0xA3, "ñ": 0xA4, "Ñ": 0xA5, "ª": 0xA6, "º": 0xA7, "¿": 0xA8, "⌐": 0xA9,
    "¬": 0xAA, "½": 0xAB, "¼": 0xAC, "¡": 0xAD, "«": 0xAE, "»": 0xAF,
    "░": 0xB0, "▒": 0xB1, "▓": 0xB2, "│": 0xB3, "┤": 0xB4, "Á": 0xB5, "Â": 0xB6,
    "À": 0xB7, "©": 0xB8, "╣": 0xB9, "║": 0xBA, "╗": 0xBB, "╝": 0xBC,
    "┐": 0xBF, "└": 0xC0, "┴": 0xC1, "┬": 0xC2, "├": 0xC3, "─": 0xC4,
    "┼": 0xC5, "ã": 0xC6, "Ã": 0xC7, "╚": 0xC8, "╔": 0xC9, "╩": 0xCA, "╦": 0xCB,
    "╠": 0xCC, "═": 0xCD, "╬": 0xCE, "¤": 0xCF, "ð": 0xD0, "Ð": 0xD1, "Ê": 0xD2,
    "Ë": 0xD3, "È": 0xD4, "ı": 0xD5, "Í": 0xD6, "Î": 0xD7, "Ï": 0xD8, "┘": 0xD9,
    "┌": 0xDA, "█": 0xDB, "▄": 0xDC, "▌": 0xDD, "▐": 0xDE, "▀": 0xDF, "Ó": 0xE0,
    "ß": 0xE1, "Ô": 0xE2, "Ò": 0xE3, "õ": 0xE4, "Õ": 0xE5, "µ": 0xE6, "þ": 0xE7,
    "Þ": 0xE8, "Ú": 0xE9, "Û": 0xEA, "Ù": 0xEB, "ý": 0xEC, "Ý": 0xED, "¯": 0xEE,
    "´": 0xEF, "≡": 0xF0, "±": 0xF1, "‗": 0xF2, "¾": 0xF3,
    "÷": 0xF6, "¸": 0xF7, "°": 0xF8, "¨": 0xF9, "·": 0xFA, "¹": 0xFB, "³": 0xFC,
    "²": 0xFD, "■": 0xFE, "\xa0": 0xFF,
}

EXTRA = {
    "●": 0x07,          # U+25CF, a build light: the bullet dot, drawn round
    "★": 0x2A,          # U+2605 has no glyph in the VGA font (0x07 is blank),
                        # so a star is printed as an asterisk: what a terminal
                        # would actually do.
    "▸": 0x10, "▶": 0x10, "►": 0x10, "◂": 0x11, "☕": 0x07, "•": 0x07,
    "│": 0xB3, "|": 0xB3, "—": 0xC4, "–": 0xC4, "·": 0xFA, "▬": 0x16,
    "✓": 0xFB, "×": 0x78, "°": 0xF8, "█": 0xDB, "▄": 0xDC, "▀": 0xDF,
}


def cp437(ch: str) -> int:
    """Unicode character -> CP437 code point (0x3F = '?' when unmapped)."""
    if ch in EXTRA:
        return EXTRA[ch]
    if ch in CP437:
        return CP437[ch]
    code = ord(ch)
    return code if 0 <= code < 256 else 0x3F


# CP437 points we actually draw with
BLOCKS = {
    "shade1": 0xB0,     # ░
    "shade2": 0xB1,     # ▒
    "shade3": 0xB2,     # ▓
    "full": 0xDB,       # █
    "lower": 0xDC,      # ▄
    "left": 0xDD,       # ▌
    "right": 0xDE,      # ▐
    "upper": 0xDF,      # ▀
}

_FONT: dict | None = None
_GLYPHS: list[list[int]] = []


def load() -> list[list[int]]:
    """Decode the font payload into 256 glyphs of 16 rows."""
    global _FONT, _GLYPHS
    if _GLYPHS:
        return _GLYPHS
    with open(FONT_FILE, encoding="utf-8") as f:
        _FONT = json.load(f)
    raw = base64.b64decode(_FONT["glyphs"])
    _GLYPHS = [[raw[n * CH + r] for r in range(CH)] for n in range(256)]
    return _GLYPHS


def _runs(glyph: list[int]) -> str:
    """Horizontal runs of a glyph as a compact path."""
    parts = []
    for r, bits in enumerate(glyph):
        c = 0
        while c < CW:
            if bits & (0x80 >> c):
                start = c
                while c < CW and bits & (0x80 >> c):
                    c += 1
                parts.append(f"M{start} {r}h{c-start}v1h-{c-start}z")
            else:
                c += 1
    return "".join(parts)


def defs(text: str = "") -> str:
    """
    <defs> with every glyph a card can draw.

    render.py prunes this down to the ids the file actually references, so a
    card never pays for a character it does not print and never loses one it
    does: forgetting a letter in a caller stops being a possible bug.
    """
    glyphs = load()
    codes = {cp437(ch) for ch in text} | set(BLOCKS.values())
    codes |= set(range(0x20, 0x80)) | set(range(0xB0, 0x100))
    out = []
    for code in sorted(codes):
        d = _runs(glyphs[code])
        if d:
            out.append(f'<path id="v{code}" d="{d}"/>')
    return "<defs>" + "".join(out) + "</defs>"


def prune(svg: str) -> str:
    """Drop every <path id="vNNN"> no <use> in this file points at."""
    used = {int(n) for n in re.findall(r'href="#v(\d+)"', svg)}

    def keep(m: re.Match) -> str:
        return m.group(0) if int(m.group(1)) in used else ""

    return re.sub(r'<path id="v(\d+)" d="[^"]*"/>', keep, svg)


def _esc(ch: str) -> int:
    return cp437(ch)


def text(x: float, y: float, s: str, color: str, scale: int = 1,
         opacity: float | None = None, cls: str = "") -> str:
    """One line of text; (x, y) is the top-left of the first cell."""
    if not s:
        return ""
    uses = []
    for i, ch in enumerate(s):
        if ch == " ":
            continue
        uses.append(f'<use href="#v{_esc(ch)}" x="{i*CW}"/>')
    op = f' opacity="{opacity}"' if opacity is not None else ""
    klass = f' class="{cls}"' if cls else ""
    return (f'<g transform="translate({x:.1f},{y:.1f})'
            f'{f" scale({scale})" if scale != 1 else ""}" fill="{color}"{op}{klass}>'
            f'{"".join(uses)}</g>')


def cols(px: float, scale: int = 1) -> int:
    return int(px // (CW * scale))


def block(x: float, y: float, name: str, color: str, scale: int = 1,
          opacity: float | None = None) -> str:
    """A single CP437 block glyph (shades, halves)."""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<g transform="translate({x:.1f},{y:.1f})'
            f'{f" scale({scale})" if scale != 1 else ""}" fill="{color}"{op}>'
            f'<use href="#v{BLOCKS[name]}"/></g>')


def hline(x: float, y: float, n: int, color: str, ch: str = "─",
          scale: int = 1, opacity: float | None = None) -> str:
    return text(x, y, ch * n, color, scale, opacity)


def bar(x: float, y: float, width: int, value: float, color: str,
        dim: str, style: str = "block") -> str:
    """
    A meter, the way a terminal draws one: filled cells, empty cells.

    style="block" -> ████░░░░    style="htop" -> |||||
    """
    value = max(0.0, min(1.0, value))
    filled = int(round(width * value))
    if style == "htop":
        return text(x, y, "|" * filled + " " * (width - filled), color)
    out = [block(x + i * CW, y, "full", color) for i in range(filled)]
    out += [block(x + i * CW, y, "shade1", dim, opacity=0.55)
            for i in range(filled, width)]
    return "".join(out)


def label(text_str: str, width: int) -> str:
    """Left/right pad, as terminals do."""
    return (text_str[:width]).ljust(width)
