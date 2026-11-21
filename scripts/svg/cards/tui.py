"""
tui.py — the profile is one terminal session.

A single CP437 window holds everything, the way a full-screen console program
does: amber prompts, green values, and the profile picture drawn as ANSI block
art that sits on the panel's own background — the picture is part of the screen,
not a rectangle pasted over it.

The gaze and the blink are CSS inside the same SVG, both on one 20 s clock so
the eye never guesses when to close.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from string import Template

from svg import ascii as A
from svg.common import ROOT, card_close, card_dots, card_open
from svg.kit import style

W = A.CW * 106                      # 848 px = 106 columns
INNER = 104                         # columns between the two side borders
OX, OY = 6, 6                       # frame inset inside the rounded card
PX, PY = 2, 26                      # where the picture starts, in px
SIDE = 43                           # column where the text beside the eye starts

AVATAR_FILE = os.path.join(ROOT, "assets/readme/data/avatar.json")
BRANDS_FILE = os.path.join(ROOT, "assets/readme/icons/brands.json")

# The colours GitHub itself uses for a language dot, so the little boxes read as
# the same thing a repo page shows.
LANG_COLOR = {
    "Python": "#3572A5", "C": "#555555", "C++": "#f34b7d", "Java": "#b07219",
    "Rust": "#dea584", "Shell": "#89e051", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "Assembly": "#6E4C13", "HTML": "#e34c26",
    "Makefile": "#427819", "COBOL": "#8f8f8f", "C#": "#178600", "Go": "#00ADD8",
}

# `$ which` — the languages first, then the tools they are built with. Every
# icon is a real brand path from assets/readme/icons/brands.json.
TOOLS = [("python", "Python"), ("openjdk", "Java"), ("c", "C"),
         ("cplusplus", "C++"), ("rust", "Rust"), ("gnubash", "Bash"),
         ("lua", "Lua"), ("zig", "Zig"), ("vim", "Vim"), ("make", "Make"),
         ("docker", "Docker"), ("sqlite", "SQLite")]

# Languages named by the README itself (it is the user's own prose: "I love
# Python, Java and C", "learning Rust and COBOL", "I love Assembly").
README_LANGS = [("Rust", "learning"), ("Assembly", "in use"), ("COBOL", "learning")]

# ── the clock ────────────────────────────────────────────────────────────────
# One 16 s cycle drives everything the eye does, and every event below is a
# percentage of that cycle, so the gaze and the blink can never drift apart.
CYCLE = 16.0

# (start, pose) — the eye changes where it looks about every second and a half
# and comes back to the viewer often, which is what reads as "alive" rather
# than as a robot sweeping left and right on a timer.
GAZE = [
    (0.0,  "c"), (1.4,  "r1"), (2.5,  "r2"), (3.6,  "c"), (4.4,  "u1"),
    (5.3,  "g1"), (6.2,  "c"), (7.0,  "l1"), (7.9,  "l2"), (8.8,  "c"),
    (9.6,  "d1"), (10.5, "c"), (11.3, "r1"), (12.1, "l1"), (13.0, "c"),
    (13.9, "g2"), (14.8, "c"),
]

# (t, close, hold, reopen) — a slow single blink, a double one, and a longer
# stare at the end. Nothing here is faster than 6 frames at 60 Hz per row, so
# the lid never teleports.
BLINKS = [(2.0, 0.34, 0.10, 0.40),
          (9.0, 0.30, 0.06, 0.30),
          (9.45, 0.30, 0.10, 0.34),
          (15.0, 0.40, 0.22, 0.50)]

ROWS_HIDDEN = 9    # the lid erases nine character rows from each side


def _pct(t: float) -> str:
    return f"{t / CYCLE * 100:.3f}%"


def _keyframes(name: str, spans: list[tuple[float, float]]) -> str:
    """A hard-edged visibility track from the seconds a thing is *on*."""
    steps = ["0%{opacity:0}"]
    for a, b in spans:
        steps.append(f"{_pct(a)}{{opacity:1}}")
        steps.append(f"{_pct(b)}{{opacity:0}}")
    return (f"  @keyframes {name} {{ {' '.join(steps)} }}")


def _spans(script: list[tuple[float, str]], want: str) -> list[tuple[float, float]]:
    out = []
    for i, (t, pose) in enumerate(script):
        if pose != want:
            continue
        end = script[i + 1][0] if i + 1 < len(script) else CYCLE
        out.append((t, end))
    return out


def _lid_tracks() -> tuple[dict[int, list], dict[int, list]]:
    """
    One blink, row by row.

    The lid is not a rectangle sliding over a picture: each row of the
    character grid is erased in turn, in the panel colour, the way a terminal
    would clear it. So a blink removes characters — it does not cover them.
    """
    top: dict[int, list] = {r: [] for r in range(ROWS_HIDDEN)}
    bottom: dict[int, list] = {r: [] for r in range(ROWS_HIDDEN)}
    for start, close, hold, reopen in BLINKS:
        for row in range(ROWS_HIDDEN):
            frac = row / ROWS_HIDDEN
            a = start + close * frac              # sweeps down from the top
            b = start + close + hold + reopen * (1 - frac)
            top[row].append((a, b))
            bottom[row].append((a, b))
    return top, bottom


def _eye_css() -> str:
    poses = ["l1", "l2", "r1", "r2", "u1", "d1", "g1", "g2"]
    rules = ["  .look, .shut { opacity: 0; }"]
    for pose in poses:
        spans = _spans(GAZE, pose)
        if not spans:
            continue
        rules.append(_keyframes(f"g-{pose}", spans))
        rules.append(f"  .g-{pose} {{ animation: g-{pose} {CYCLE}s steps(1,end) "
                     f"infinite; }}")
    top, bottom = _lid_tracks()
    for row, spans in top.items():
        rules.append(_keyframes(f"lid-t{row}", spans))
        rules.append(f"  .lid-t{row} {{ animation: lid-t{row} {CYCLE}s "
                     f"steps(1,end) infinite; }}")
    for row, spans in bottom.items():
        rules.append(_keyframes(f"lid-b{row}", spans))
        rules.append(f"  .lid-b{row} {{ animation: lid-b{row} {CYCLE}s "
                     f"steps(1,end) infinite; }}")
    lash = [(st + cl * .86, st + cl + ho + re * .18)
            for st, cl, ho, re in BLINKS]
    rules.append(_keyframes("lash", lash))
    rules.append(f"  .lash {{ animation: lash {CYCLE}s steps(1,end) infinite; }}")
    rules.append("  .ball { animation: breathe 7.5s ease-in-out infinite; "
                 "transform-box: fill-box; transform-origin: center; }")
    rules.append("  @keyframes breathe { 0%,100% { transform: scale(1) } "
                 "50% { transform: scale(.985) } }")
    rules.append("  @media (prefers-reduced-motion: reduce) "
                 "{ * { animation: none !important } }")
    return "\n".join(rules) + "\n"


def _css(h: int) -> str:
    return Template("""
  .blink { animation: blink 1.1s steps(1,end) infinite; }
  @keyframes blink { 0%,55% { opacity:1 } 56%,100% { opacity:0 } }
  .wipe { animation: wipe 1.1s cubic-bezier(.6,0,.35,1) both;
          transform-box: fill-box; transform-origin: top center; }
  @keyframes wipe { from { transform: scaleY(1) } to { transform: scaleY(0) } }
  .scan { animation: scan 16s linear 3s infinite; }
  @keyframes scan { 0% { transform: translateY(0); opacity:0 }
                    3% { opacity:.2 } 97% { opacity:.07 }
                    100% { transform: translateY($h px); opacity:0 } }
""" + _eye_css()).substitute({"h": h})


def meter(frac: float, width: int) -> str:
    """A half-block gauge: ▄▄▄▄▄"""
    filled = int(round(max(0.0, min(1.0, frac)) * width))
    return "▄" * filled + " " * (width - filled)


def _top(path: str, clock: str) -> dict:
    """
    The frame's top rule, cut into the runs that carry their own colour:
    `┌──┤ ~/github/Green_Eye ├───────┤ 03:07 UTC ─┐`, always INNER+2 columns.
    """
    lead = "┌──┤ "
    mid_at = len(lead) + len(path)
    tail = f"┤ {clock} ─┐"
    tail_at = INNER + 2 - len(tail)
    return {"lead": lead, "path": path, "mid_at": mid_at,
            "dash": "├" + "─" * (tail_at - mid_at - 1),
            "tail_at": tail_at, "clock": clock, "tail": tail}


# ── the picture ──────────────────────────────────────────────────────────────

def _avatar() -> dict:
    with open(AVATAR_FILE, encoding="utf-8") as f:
        return json.load(f)


def _cells(raw: bytes, cols: int, rows: int) -> dict:
    return {(y, x): raw[y * cols + x] for y in range(rows) for x in range(cols)}


def _emit(cells: dict, palette: list[str], klass: str = "") -> str:
    """One <g> per colour, every cell a positioned <use>."""
    by_colour: dict[str, list[str]] = {}
    for (y, x), b in cells.items():
        if b == 0xEE:
            continue
        glyph = A.BLOCKS["full" if (b & 0x0F) >= 3 else "shade1"]
        by_colour.setdefault(palette[b >> 4], []).append(
            f'<use href="#v{glyph}" x="{x * A.CW:.0f}" y="{y * A.CH:.0f}"/>')
    cls = f' class="{klass}"' if klass else ""
    return "".join(f'<g{cls} fill="{col}">{"".join(v)}</g>'
                   for col, v in by_colour.items())


def _eye(c: dict) -> tuple[str, int]:
    """
    The picture with no plate behind it: the panel *is* the background.

    The base cells are drawn once. Every pose (looking left, right, up, down,
    or up and to a corner) swaps only the iris patch. The lids are the rows of
    the grid themselves: erasing a row with the panel colour is a blink that
    the terminal itself would understand.
    """
    av = _avatar()
    cols, rows = av["cols"], av["rows"]
    iris = _cells(base64.b64decode(av["iris"]), cols, rows)
    centre = _cells(base64.b64decode(av["centre"]), cols, rows)
    pal = av["palette"]

    pic = _emit(centre, pal)
    for pose, raw in av["look"].items():
        shifted = _cells(base64.b64decode(raw), cols, rows)
        pic += _emit({k: v for k, v in shifted.items()
                      if iris.get(k) and v != 0xEE}, pal, f"look g-{pose}")

    pw, ph = cols * A.CW, rows * A.CH
    out = [f'<g transform="translate({PX},{PY})">',
           f'<clipPath id="cut"><rect width="{pw}" height="{ph}" rx="4"/></clipPath>',
           '<g clip-path="url(#cut)">',
           f'<g class="ball">{pic}</g>']
    # One rect per character row, so the lid covers exactly whole characters.
    for side, fn in (("t", lambda r: r), ("b", lambda r: rows - 1 - r)):
        for r in range(ROWS_HIDDEN):
            y = fn(r) * A.CH
            out.append(f'<g class="lid-{side}{r}"><rect x="0" y="{y}" '
                       f'width="{pw}" height="{A.CH}" fill="{c["panel"]}"/>'
                       f'</g>')
    out.append("</g>")
    # The lash: while the lids are down, one row of ▄ marks where the picture
    # was. It is a character row like everything else, not a drawn line.
    out.append(f'<g class="lash">{A.text(0, (A.CH * (rows // 2)) - 8, "▄" * cols, c["accent"], opacity=.55)}</g>')
    out.append("</g>")
    return "".join(out), rows


# ── the session ──────────────────────────────────────────────────────────────

def session(d: dict, c: dict) -> str:
    """
    The whole screen: the eye and its column, then the blocks underneath.

    The body is drawn into a list while its last row is tracked, and the frame
    is sized from that — a card can then never clip its own contents.
    """
    u, t, con = d["user"], d["totals"], d["contributions"]
    av = _avatar()
    eye, eye_rows = _eye(c)
    brands = _brands()
    keys = [(k, lbl) for k, lbl in TOOLS if k in brands][:12]
    wd, days = con["weekday"], con["days"]
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    peak = max([p["n"] for p in days] + [1])
    wmax = max([x["n"] for x in wd] + [1])
    stamp = d["generated_at"][:16].replace("T", " ")

    body: list[str] = []

    # ── the eye, and the column beside it ───────────────────────────────
    body.append(eye)
    side: list[tuple[str, str]] = [
        (f"{u.get('login', '')}@github", c["accent"]),
        (u.get("location") or "the internet", c["dim"]),
        ("", c["dim"]),
        (f"{u.get('name') or ''}".upper(), c["text"]),
        (u.get("bio") or "", c["muted"]),
        ("", c["muted"]),
        (f"since {u.get('created_at', '')[:4]} · {t['followers']} followers · "
         f"{t['following']} following", c["dim"]),
        ("", c["dim"]),
        ("$ uptime", c["accent3"]),
    ]
    stats = [("contributions", t["contributions"], 1200),
             ("commits", t["commits"], 2400),
             ("stars", t["stars"], 160),
             ("repos", t["repos"], 48)]
    stats_at = len(side)
    side += [(f"{lbl:<13}{val:>5}", c["muted"]) for lbl, val, _ in stats]
    side += [("", c["muted"]),
             (f"streak {con['streak']['current']}d · best "
              f"{con['streak']['longest']}d · rank {t['rank']['grade']}",
              c["muted"]),
             ("", c["muted"]),
             ("$ account", c["accent3"]),
             (f"{t['repos']} repos · {t['prs']} pull requests · "
              f"{t['issues']} issues", c["muted"])]
    for i, (txt, col) in enumerate(side):
        body.append(A.text(A.CW * SIDE, PY + i * A.CH, txt, col))
    for i, (_, val, ceiling) in enumerate(stats):
        body.append(A.text(A.CW * (SIDE + 20), PY + (stats_at + i) * A.CH,
                           meter(val / ceiling, 14), c["accent"]))

    # ── stack ───────────────────────────────────────────────────────────
    y = PY + eye_rows * A.CH + A.CH
    known = [l for l in d["languages"] if l["name"] in LANG_COLOR]
    for name, note in README_LANGS:       # named in the README, no repo yet
        if name not in [l["name"] for l in known] and name in LANG_COLOR:
            known.append({"name": name, "pct": None, "note": note})
    body.append(A.text(A.CW, y, "$ cat ~/stack", c["accent3"]))
    body.append(A.text(A.CW * (INNER - 18), y, "by bytes written", c["dim"]))
    y += A.CH
    for l in known:
        pct = l["pct"]
        body.append(A.text(A.CW * 2, y, f"{l['name'][:10]:<11}", c["muted"]))
        if pct is None:
            body.append(A.text(A.CW * 13, y, f"{l['note']:>9}", c["dim"]))
            body.append(A.text(A.CW * 46, y, "no repo yet", c["dim"]))
        else:
            body.append(A.text(A.CW * 13, y, f"{pct:5.1f}%   ", c["muted"]))
            body.append(A.text(A.CW * 22, y, meter(pct / 100, 24), c["accent"],
                               opacity=.9))
            body.append(A.text(A.CW * 48, y, f"{l['repos']} repos", c["dim"]))
        y += A.CH
    y += A.CH
    # the little colour boxes GitHub draws next to a repo name
    for i, l in enumerate(known):
        x = A.CW * (2 + (i % 3) * 30)
        yy = y + (i // 3) * A.CH
        body.append(f'<rect x="{x}" y="{yy + 3}" width="10" height="10" rx="2" '
                    f'fill="{LANG_COLOR[l["name"]]}"/>')
        pct = l["pct"]
        body.append(A.text(x + 14, yy, f"{l['name']} "
                           + (f"{pct:.1f}%" if pct else l["note"]), c["muted"]))
    y += A.CH * ((len(known) + 2) // 3) + A.CH

    # ── repos ───────────────────────────────────────────────────────────
    repos = d["projects"][:6]
    body.append(A.text(A.CW, y, "$ ls -1 ~/repos | head -6", c["accent3"]))
    body.append(A.text(A.CW * (INNER - 22), y, f"{len(repos)} of {t['repos']} repos",
                       c["dim"]))
    y += A.CH
    for r in repos:
        desc = (r["desc"] or "").replace("\n", " ").strip().lstrip("💾 ")
        body.append(A.text(A.CW * 2, y, f"{r['name'][:16]:<17}{desc[:54]}",
                           c["muted"]))
        body.append(A.text(A.CW * 74, y, f"{r['forks']:>3} forks", c["dim"]))
        body.append(A.text(A.CW * 88, y, f"{r['stars']:>3}★", c["dim"]))
        y += A.CH
    y += A.CH

    # ── the year ────────────────────────────────────────────────────────
    right = f"{con['total']} in a year"
    body.append(A.text(A.CW, y, "$ contribution-graph --year", c["accent3"]))
    body.append(A.text(A.CW * (INNER - len(right)), y, right, c["dim"]))
    y += A.CH
    body.append(A.text(A.CW * 2, y, "less", c["dim"]))
    for i in range(4):
        body.append(A.text(A.CW * (7 + i * 2), y, "▄", c["accent"],
                           opacity=.24 + .19 * i))
    body.append(A.text(A.CW * 15, y, "more", c["dim"]))
    y += A.CH
    for wd_i in range(7):
        for w, wk in enumerate(weeks):
            n = wk[wd_i]["n"] if wd_i < len(wk) else 0
            if not n:
                body.append(f'<use href="#v{A.BLOCKS["lower"]}" '
                            f'x="{A.CW * (2 + w)}" y="{y}" fill="{c["line"]}" '
                            f'opacity=".6"/>')
                continue
            lvl = min(4, 1 + int(3.999 * (n / peak) ** 0.5))
            body.append(f'<use href="#v{A.BLOCKS["lower"]}" x="{A.CW * (2 + w)}" '
                        f'y="{y}" fill="{c["accent"]}" '
                        f'opacity="{0.24 + 0.19 * (lvl - 1):.2f}"/>')
        x = wd[wd_i]
        body.append(A.text(A.CW * 58, y, f"{x['day'][:3]:<4}", c["dim"]))
        body.append(A.text(A.CW * 62, y, meter(x["n"] / wmax, 16), c["accent"],
                           opacity=.8))
        body.append(A.text(A.CW * 81, y, f"{x['n']:>4}", c["muted"]))
        y += A.CH
    body.append(A.text(A.CW * 2, y, f"streak {con['streak']['current']}d · "
                      f"longest {con['streak']['longest']}d · peak "
                      f"{con['best_day']['n']} on {con['best_day']['d']}",
                      c["muted"]))
    body.append(A.text(A.CW * (INNER - 16), y,
                       f"{sum(1 for x in days if x['n'])} active days",
                       c["dim"]))
    y += A.CH * 2

    # ── when in the day ─────────────────────────────────────────────────
    hours = con.get("hours") or [0] * 24
    hmax = max(hours + [1])
    body.append(A.text(A.CW, y, "$ history | awk '{print $2}' | cut -d: -f1 | "
                                 "sort | uniq -c", c["accent3"]))
    body.append(A.text(A.CW * (INNER - 9), y, "by hour", c["dim"]))
    y += A.CH
    baseline = y + 4 * A.CH                    # bars grow up from the tick row
    for h in range(24):
        cells = int(round(hours[h] / hmax * 6))    # six half-blocks = three rows
        for k in range(cells):
            body.append(f'<use href="#v{A.BLOCKS["lower"]}" '
                        f'x="{A.CW * (2 + h * 3)}" '
                        f'y="{baseline - A.CH // 2 - (k + 1) * 8}" '
                        f'fill="{c["accent"]}" opacity=".9"/>')
    labels = "".join(f"{h:02d}".ljust(3) if h % 3 == 0 else "   "
                     for h in range(24))
    body.append(A.text(A.CW * 2, baseline, labels.rstrip(), c["dim"]))
    y = baseline + A.CH
    body.append(A.text(A.CW * 2, y, f"peak {hours.index(hmax):02d}:00 UTC · "
                       f"hour by hour, from the daily counts", c["muted"]))
    y += A.CH * 2

    # ── the build, the way make would say it ────────────────────────────
    body.append(A.text(A.CW, y, "$ make -j4 all && sha1sum ~/profile",
                       c["accent3"]))
    y += A.CH
    glyphs = len(_all_text(d, av, keys, wd))
    checks = [f"mypy.py {len(d['languages'])} langs",
              f"tui.py {glyphs} chars",
              "blink.c 20s clock"]
    for i, txt in enumerate(checks):
        x = A.CW * (2 + i * 28)
        body.append(A.text(x, y, "■", c["accent"]))
        body.append(A.text(x + A.CW * 2, y, txt, c["muted"]))
    body.append(A.text(A.CW * (INNER - 6), y, "all ok", c["accent3"]))
    y += A.CH
    seed = hashlib.sha1(
        f"{t['commits']}{t['contributions']}{t['stars']}{t['repos']}"
        f"{u.get('login')}".encode()).hexdigest()[:12]
    body.append(A.text(A.CW * 2, y, seed, c["accent"]))
    body.append(A.text(A.CW * (2 + len(seed)), y, "  ~/profile", c["dim"]))
    y += A.CH * 2

    # ── toolbox ─────────────────────────────────────────────────────────
    # Six per row: two rows fit the twelve tools the laptop can actually run,
    # and `which` is the honest verb for "can I compile with it".
    for row_i in range(0, len(keys), 6):
        chunk = keys[row_i:row_i + 6]
        names = " ".join(lbl.lower() for _, lbl in chunk)
        body.append(A.text(A.CW, y, f"$ which {names}" if row_i == 0
                           else f"$ command -v {names}", c["accent3"]))
        y += A.CH
        for i, (key, lbl) in enumerate(chunk):
            x = A.CW * (2 + i * 16)
            body.append(A.text(x, y, "[", c["line"]))
            body.append(f'<g transform="translate({x + A.CW * 1.25:.1f},{y + 1:.1f}) '
                        f'scale({16 / 24:.4f})"><path d="{brands[key]["d"]}" '
                        f'fill="{c["accent"]}" opacity=".9"/></g>')
            body.append(A.text(x + A.CW * 3, y, "]", c["line"]))
            body.append(A.text(x + A.CW * 5, y, lbl[:10], c["muted"]))
        y += A.CH
    y += A.CH

    # ── footer ──────────────────────────────────────────────────────────
    prompt = "[eye@github ~]$ exit 0"
    body.append(A.text(A.CW * 2, y, prompt, c["accent3"]))
    body.append(A.text(A.CW * (3 + len(prompt)), y, "█", c["accent3"],
                       cls="blink"))
    y += A.CH
    body.append(A.text(A.CW * 2, y, "generated by "
                       f".github/workflows/readme.yml · {stamp} UTC", c["dim"]))
    y += A.CH * 2

    # ── frame, sized from the body ──────────────────────────────────────
    h = y + OY * 2 + 4
    top = _top("~/github/Green_Eye", f"{stamp[11:]} UTC")
    bottom = "└" + "─" * INNER + "┘"
    side_rule = (f'<rect x="3" y="{A.CH // 2}" width="2" '
                 f'height="{h - OY * 2 - A.CH}" fill="{c["line"]}"/>'
                 f'<rect x="{W - 5}" y="{A.CH // 2}" width="2" '
                 f'height="{h - OY * 2 - A.CH}" fill="{c["line"]}"/>')
    svg = (card_open(h, c, uid="tty", radius=10, gradient=False, solid=True,
                     dots_on_top=True)
           + style(_css(h)) + A.defs(_all_text(d, av, keys, wd))
           + f'<g transform="translate({OX},{OY})">' + side_rule
           + A.text(0, 0, top["lead"], c["line"])
           + A.text(A.CW * len(top["lead"]), 0, top["path"], c["accent"])
           + A.text(A.CW * top["mid_at"], 0, top["dash"], c["line"])
           + A.text(A.CW * (top["tail_at"] + 2), 0, top["clock"], c["dim"])
           + A.text(A.CW * top["tail_at"], 0, top["tail"][:2], c["line"])
           + A.text(A.CW * (top["tail_at"] + 2 + len(top["clock"])), 0,
                    top["tail"][2 + len(top["clock"]):], c["line"])
           + "".join(body)
           + A.text(0, h - OY * 2 - A.CH, bottom, c["line"])
           + "</g>")
    svg += card_dots(h, c, uid="tty", radius=10)
    svg += (f'<rect class="scan" x="0" y="0" width="{W}" height="8" '
            f'fill="{c["accent"]}" opacity=".05"/>')
    return svg + card_close()


def _all_text(d: dict, av: dict, keys, wd) -> str:
    """Everything the card prints, so ascii.defs() can size its <defs>."""
    u = d["user"]
    parts = [
        "session tty1", "GREEN EYE", u.get("login", ""), u.get("location") or "",
        u.get("bio") or "", "$ uptime", "$ cat ~/stack", "$ ls -1 ~/repos | head -3",
        "$ contribution-graph --year", "less more", "streak longest peak active days",
        "$ history | awk '{print $2}' | cut -d: -f1 | sort | uniq -c", "by hour",
        "peak UTC · hour by hour, from the daily counts",
        "$ make -j4 all && sha1sum ~/profile", "all ok",
        "$ ls -1 ~/repos | head -6", "of repos forks for all ok",
        "mypy.py langs tui.py chars blink.c 20s clock ~/profile UTC",
        "by bytes written", "no repo yet", "learning in use",
        "".join(n for n, _ in README_LANGS),
        "".join(lbl for _, lbl in TOOLS),
        "[eye@github ~]$ exit 0", "generated by .github/workflows/readme.yml ·",
        "since followers following", "contributions commits stars repos rank best",
        d["generated_at"][:16].replace("T", " "),
        "".join(l["name"] for l in d["languages"]),
        "".join((r["name"] or "") + (r["desc"] or "") for r in d["projects"]),
        "".join(lbl for _, lbl in keys), "$ which ",
        "".join(x["day"] for x in wd),
        "".join(f"{h:02d}" for h in range(24)) + "0123456789:",
        "".join(f"{l['name']} {l['pct']:.1f}%" for l in d["languages"]),
    ]
    return "".join(parts)


def _brands() -> dict:
    try:
        with open(BRANDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}
