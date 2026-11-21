"""
render.py — data.json  ➜  animated SVGs.

Output layout (consumed by the README):

    assets/readme/live/<card>-dark.svg         self-contained, animated (dark only)
    assets/readme/live/css/<card>-dark.src.svg animated + shared <style>

The `.src.svg` copy is the GitHub trick: `<img>` cannot pull an external CSS
file, so `update_readme.py` inlines those styles inside a `<style>` block of the
README. GitHub does not inject cached stylesheets into `<style>` blocks, so the
CSS — and therefore the animation — runs fresh on every page load.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from svg import ascii as A  # noqa: E402
from svg.cards import tui  # noqa: E402
from svg.kit import theme  # noqa: E402

CARDS = [
    ("profile", tui.session),
]
STATICS = []


def _split_style(svg: str) -> tuple[str, list[str]]:
    """Pull every <style>…</style> out of the SVG, keeping the markup intact."""
    blocks = re.findall(r"<style>(.*?)</style>", svg, flags=re.S)
    naked = re.sub(r"<style>.*?</style>", "", svg, flags=re.S)
    return naked, blocks


def _scope(css: str, card: str, mode: str) -> str:
    css = re.sub(r"@keyframes\s+([\w-]+)", lambda m: f"@keyframes {m.group(1)}-{card}-{mode}", css)
    css = re.sub(r"animation(-name)?:\s*([\w-]+)", lambda m: (
        f"animation{m.group(1) or ''}: {m.group(2)}-{card}-{mode}"), css)
    css = css.replace("var(--off)", "var(--off)")     # keep custom props untouched
    css = re.sub(r"var\(--([\w-]+)\)", lambda m: f"var(--{m.group(1)}-{card}-{mode})", css)
    css = re.sub(r"--([\w-]+):", lambda m: f"--{m.group(1)}-{card}-{mode}:", css)
    return css


def render_all(data: dict, out_dir: str) -> dict:
    """
    Dark only, on purpose.

    The card is a terminal, and a terminal on a white page is a contradiction:
    the panel is painted solid so the picture and the lids can rely on its exact
    colour, and it looks the same for every viewer whatever their theme is.
    """
    report = {"cards": [], "src_css": []}
    css_dir = os.path.join(out_dir, "css")
    os.makedirs(css_dir, exist_ok=True)

    for mode in ("dark",):
        c = theme(mode)
        for name, fn in CARDS + STATICS:
            svg = A.prune(fn(data, c))
            plain = os.path.join(out_dir, f"{name}-{mode}.svg")
            with open(plain, "w", encoding="utf-8") as f:
                f.write(svg)
            naked, blocks = _split_style(svg)
            with open(os.path.join(css_dir, f"{name}-{mode}.src.svg"), "w",
                      encoding="utf-8") as f:
                f.write(naked)
            if blocks:
                css = "\n".join(blocks)
                report["src_css"].append((f"{name}-{mode}", _scope(css, name, mode)))
            report["cards"].append((f"{name}-{mode}", len(svg), len(naked)))
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "assets/readme/live"))
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(args.out, exist_ok=True)
    rep = render_all(data, args.out)

    print(f"✓ {len(rep['cards'])} SVGs → {os.path.relpath(args.out, ROOT)}")
    for name, size, naked in rep["cards"]:
        extra = f"  (css split: {naked/1024:.1f} kB)" if naked != size else ""
        print(f"   {name:22s} {size/1024:7.1f} kB{extra}")

    # CSS bundle for the README <style> block
    bundle = os.path.join(args.out, "css", "animation-bundle.css")
    with open(bundle, "w", encoding="utf-8") as f:
        for name, css in rep["src_css"]:
            f.write(f"/* ── {name} ───────────────────────────── */\n{css}\n")
    print(f"✓ css bundle → {os.path.relpath(bundle, ROOT)} "
          f"({os.path.getsize(bundle)/1024:.1f} kB)")


if __name__ == "__main__":
    main()
