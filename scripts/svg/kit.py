"""
kit.py — shared palette, helpers and micro-DSL for the animated README SVGs.

Everything here is pure stdlib: the whole renderer runs inside a GitHub Action
with zero third-party dependencies.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
#  PALETTE — "the green eye", one console palette, dark by definition
# ─────────────────────────────────────────────────────────────────────────────

THEMES = {
    # One theme on purpose: the card is a console, and a console is dark.
    # Everyone sees this, whatever their GitHub theme is.
    "dark": {
        "panel":     "#0d1117",
        "line":      "#30363d",
        "text":      "#f0f6fc",
        "muted":     "#9ba7b4",
        "dim":       "#6e7681",
        "accent":    "#3fb950",
        "accent3":   "#7ee787",
    },
}

FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif,"
        "'Apple Color Emoji','Segoe UI Emoji'")
MONO = ("ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',"
        "monospace")



def theme(name: str = "dark") -> dict:
    """The single palette. `mode` stays for the few places that branch on it."""
    t = dict(THEMES["dark"])
    t["mode"] = "dark"
    return t


def compact(n: float) -> str:
    n = float(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1_000:.1f}k".replace(".0k", "k")
    return str(int(n))


def svg_open(w: int, h: int, extra: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" fill="none" role="img" {extra}>')


def linear_gradient(gid: str, stops, x1="0%", y1="0%", x2="100%", y2="0%") -> str:
    body = "".join(
        f'<stop offset="{o}" stop-color="{c}"{f" stop-opacity={chr(34)}{a}{chr(34)}" if a is not None else ""}/>'
        for o, c, a in [(s if len(s) == 3 else (*s, None)) for s in stops]
    )
    return (f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
            f'{body}</linearGradient>')


def dot_grid(pid: str, color: str, opacity: float = 0.13, gap: int = 22) -> str:
    return (f'<pattern id="{pid}" width="{gap}" height="{gap}" patternUnits="userSpaceOnUse">'
            f'<circle cx="1.2" cy="1.2" r="1.2" fill="{color}" opacity="{opacity}"/></pattern>')


def style(css: str) -> str:
    return f"<style>{css}</style>"


