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


def badge(src_img: str, href: str, alt: str) -> str:
    return f'<a href="{href}"><img src="{src_img}" alt="{alt}" height="20"></a>'


def details_block(d: dict) -> str:
    t = d["totals"]
    con = d["contributions"]
    return "\n".join([
        "<details>",
        "<summary><b>▲ how this README is built</b></summary>",
        "",
        "```mermaid",
        "flowchart LR",
        '  A["⏱️ every 4 h · push · manual"] --> B["python 3.13 · stdlib only"]',
        '  B --> C["collect.py<br/>REST · search · calendar"]',
        '  B --> D["avatar.py<br/>photo → 40×20 ANSI cells"]',
        '  C --> E[("data.json")]',
        '  D --> E',
        '  E --> F["render.py<br/>one animated SVG"]',
        '  F --> G["git commit"] --> A',
        "```",
        "",
        "| what | how | why it is not a screenshot |",
        "| --- | --- | --- |",
        "| **telemetry** | REST + search API, contribution calendar per day | re-collected on every run |",
        "| **portrait** | the photo quantised to 40×20 cells of CP437 blocks | the gaze and the blink are CSS |",
        "| **terminal** | one SVG window in the VGA console font, CSS keyframes | animation ships inside the file |",
        "",
        f"**Last build** `{d['generated_at'][:19].replace('T', ' ')} UTC` · "
        f"**contributions** `{t['contributions']}` · "
        f"**streak** `{con['streak']['current']}d` / best `{con['streak']['longest']}d` · "
        f"**rank** `{t['rank']['grade']}` · "
        f"**degraded sources** `{len(d['meta']['degraded'])}`",
        "",
        "<sub>Rendered by `scripts/` from the GitHub API and the contribution "
        "calendar. Sources that fail are noted above; the rest of the README "
        "still renders.</sub>",
        "",
        "</details>",
    ])


def generated(d: dict) -> str:
    u = d["user"].get("login", "")
    v = re.sub(r"\D", "", d["generated_at"])[:12]
    name, alt = CARDS[0]
    bits = [BEGIN, ""]
    bits += ['<p align="center">',
             f'  <a href="https://github.com/{u}">{picture(name, alt, v=v)}</a>',
             "</p>", ""]
    bits += ["@@LIST@@", ""]
    bits += [details_block(d), "", END]
    return "\n".join(bits)


LIST_FALLBACK = """- 🔭 I’m currently working on **[Monarch OS](https://github.com/TheBigEye/Monarch-OS)** and **[Aircraft](https://github.com/TheBigEye/Aircraft)**.
- ❤️ I love **[Python](https://github.com/topics/python)**, **[Java](https://github.com/topics/java)** and **[C](https://github.com/topics/c)**.
- 👀 I am focused on the development of **[Games](https://github.com/topics/game-engine)**, **[Operating Systems](https://github.com/topics/osdev)**, and **[IA](https://github.com/topics/ai)**.
- 🌱 I’m currently learning **[Rust](https://github.com/topics/rust)** and **[COBOL](https://github.com/topics/cobol)** for fun.
- 👯 I’m currently collaborating on **[Minicraft+](https://github.com/MinicraftPlus/minicraft-plus-revived)**.
- ⚡ Fun fact, I love **[Assembly](https://github.com/topics/assembly-language)**, is faster and sometimes easy to learn.
- 🎨 **Green** is my favorite color."""

CREDITS = """<!-- ─────────────────────────────── credits ───────────────────────────────
  Cards and animation: scripts/ (stdlib only)
  Typeface: Linux console font Default8x16 (CP437) — assets/readme/fonts/
  Brand marks: Simple Icons (CC0) — assets/readme/icons/brands.json
  Regenerated by .github/workflows/readme.yml
──────────────────────────────────────────────────────────────────────────── -->"""


CREDITS_RE = re.compile(r"<!-- ─+ credits ─+.*?-->\s*", re.S)


def extract_list(readme: str) -> str:
    """Keep the human-written bullet list exactly as it is."""
    if "@@LIST@@" not in readme and "I’m currently working on" not in readme:
        return ""
    lines = []
    for line in readme.splitlines():
        if line.startswith("- "):
            lines.append(line)
        elif lines and not line.strip():
            break
    return "\n".join(lines)


def unescape(text: str) -> str:
    """Put the HTML entities back (authors write ’ and & freely in markdown)."""
    for a, b in (("&rsquo;", "’"), ("&amp;", "&"), ("&quot;", '"'), ("&lt;", "<"),
                 ("&gt;", ">")):
        text = text.replace(a, b)
    return text


def migrate(original: str) -> str:
    """Strip the old static blocks, keep everything a human wrote."""
    out, skip = [], False
    for line in original.splitlines():
        if line.strip() == BEGIN:
            skip = True
            continue
        if line.strip() == END:
            skip = False
            continue
        if skip:
            continue
        dropped = (
            "assets/readme/header/" in line
            or "assets/readme/image/pc-" in line
            or "assets/readme/stats/" in line
            or "komarev.com/ghpvc" in line
            or line.strip() in {"<!-- ------ README --------->", "<!-- Header -->",
                                "<!-- Views -->", "<!-- User stats -->",
                                "<!-- Top langs used -->", "<!-- Contributions -->",
                                "<p align=\"left\">", "<p align=\"right\">",
                                "<p align=\"center\">", "</p>"}
            or (line.strip().startswith("<!-- ---") and line.strip().endswith("-->"))
            or (line.strip().startswith("<!-- Credit") )
        )
        if not dropped:
            out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return unescape(text)


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

    # where does the list go? Before the stats row, exactly like the original.
    listing = ""
    if BEGIN not in original:
        listing = extract_list(migrate(original)) or LIST_FALLBACK
        body = body.replace("@@LIST@@", listing)
    else:
        listing = extract_list(original) or LIST_FALLBACK
        body = body.replace("@@LIST@@", listing)

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
