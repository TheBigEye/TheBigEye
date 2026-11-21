"""
readme.py — writes README.md around the generated SVGs, preserving the original
content and structure.

Why images instead of inline SVG:

  GitHub sanitises the HTML of a README, but it never inspects the *contents* of
  an image. So each card is a self-contained animated SVG loaded through an
  <img>, and every animation lives inside that file. That is also why the CRT
  photo is embedded as a data URI: an SVG loaded as an image is firewalled from
  every external resource, but it can still run its own CSS.

Usage:
    python3 readme.py --data data.json [--out README.md]
"""

from __future__ import annotations

import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")
BEGIN = "<!-- ═══════════════ ANIMATED README · generated ═══════════════ -->"
END = "<!-- ═════════════════════════════ END GENERATED ═════════════════════════════ -->"
LIVE = "assets/readme/live"

# cards whose aspect ratio we let the README decide (they are full width)
CARDS = [
    ("profile", "The whole profile as one terminal session — the picture is ANSI art"),
]


BUST = os.environ.get("README_CACHE_BUST", "1") != "0"


def picture(name: str, alt: str, width: str = "100%", v: str = "") -> str:
    """
    The one animated SVG.

    Dark only: a terminal on a white page would need a second palette and would
    stop being the same object, so the card carries its own background and
    everybody sees the same screen. The `?v=` suffix changes on every build,
    because GitHub proxies images through a cache keyed by URL.
    """
    q = f"?v={v}" if (v and BUST) else ""
    return (f'<img src="{LIVE}/{name}-dark.svg{q}" alt="{alt}" '
            f'width="{width}">')


def generated(d: dict) -> str:
    """
    The README is the terminal and nothing else.

    The seven lines that used to be a markdown bullet list are written in
    `assets/readme/data/about.json` and printed *inside* the console, links
    included, so the page has a single object to look at.
    """
    u = d["user"].get("login", "")
    v = re.sub(r"\D", "", d["generated_at"])[:12]
    name, alt = CARDS[0]
    bits = [BEGIN, ""]
    bits += ['<p align="center">',
             f'  <a href="https://github.com/{u}">{picture(name, alt, v=v)}</a>',
             "</p>", ""]
    bits += [END]
    return "\n".join(bits)


CREDITS = """<!-- ─────────────────────────────── credits ───────────────────────────────
  Cards and animation: scripts/ (stdlib only)
  Typeface: Linux console font Default8x16 (CP437) — assets/readme/fonts/
  Brand marks: Simple Icons (CC0) — assets/readme/icons/brands.json
  Rebuilt every 4 h by .github/workflows/readme.yml
──────────────────────────────────────────────────────────────────────────── -->"""


CREDITS_RE = re.compile(r"<!-- ─+ credits ─+.*?-->\s*", re.S)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data.json"))
    ap.add_argument("--out", default=README)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        d = json.load(f)

    original = open(args.out, encoding="utf-8").read() if os.path.exists(args.out) else ""
    body = generated(d)

    head, tail = "", ""
    if BEGIN in original:
        head = original.split(BEGIN)[0].strip()
        if END in original:
            tail = original.split(END, 1)[1].strip()

    parts = [re.sub(CREDITS_RE, "", p).strip() for p in (head, body, tail)]
    new = "\n\n".join([p for p in parts if p] + [CREDITS]) + "\n"

    if args.dry_run:
        print(new)
        return
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"✓ {os.path.basename(args.out)} written "
          f"({len(new)/1024:.1f} kB, {len(new.splitlines())} lines)")


if __name__ == "__main__":
    main()
