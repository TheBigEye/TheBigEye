"""
tui.py — the profile is one terminal session.

A single CP437 window holds everything, the way a full-screen console program
does: amber prompts, green values, and the profile picture drawn as ANSI block
art that sits on the panel's own background — the picture is part of the screen,
not a rectangle pasted over it.

The gaze is CSS inside the same SVG, on one 26 s clock, so every pose knows
when it is on screen. There is no blink: the portrait is the eye.
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
PX, PY = 3, 26                      # picture origin: PX in columns, PY in px
SIDE = 50                           # column where the text beside the eye starts
                                    # (the portrait is 44 cells wide)

AVATAR_FILE = os.path.join(ROOT, "assets/readme/data/avatar.json")
ABOUT_FILE = os.path.join(ROOT, "assets/readme/data/about.json")
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
# One cycle drives everything the eye does, and every event is expressed as a
# percentage of it, so the poses can never drift apart.
#   SCRIPT  the duration the GAZE table below was written for
#   CYCLE   the duration it is actually played at — one number for the tempo
SCRIPT, CYCLE = 30.0, 16.0
FADE = 0.18        # seconds a gaze takes to dissolve into the next one

# (t, pose) — 25 keyframes across the cycle. Each pose is one cell further than
# the previous one, so a change of direction is a sequence of small movements
# instead of a jump: that is what reads as smooth rather than frame-like.
# The pose of each keyframe, and the pixel drift that pose means. The body of
# the eye copies that drift at a third of its size, so the whole picture follows
# the look instead of the iris moving inside a frozen frame.

GAZE = [
    # a quick glance right, then it holds still and stares at you
    (0.0, "c"), (1.2, "r1"), (2.0, "r2"), (2.8, "r3"), (3.8, "r2"),
    (5.0, "c"), (7.4, "c"),
    # up, and a pause to think
    (8.6, "u1"), (9.3, "u2"), (10.1, "u1"), (11.0, "c"), (12.8, "c"),
    # the diagonal, then a long blink-less stare
    (13.9, "g1"), (14.8, "r2"), (15.6, "c"), (18.2, "c"),
    # left, the widest look of the cycle
    (19.3, "l1"), (20.1, "l2"), (20.9, "l3"), (22.0, "l2"),
    (23.0, "c"), (24.6, "c"),
    # down, and the last pause before it starts again
    (25.6, "d1"), (26.4, "d2"), (27.2, "d1"), (28.0, "c"), (30.0, "c"),
]


def _pct(t: float) -> str:
    """A time from the script as a percentage of the played cycle."""
    return f"{t / SCRIPT * 100:.3f}%"


def _keyframes(name: str, spans: list[tuple[float, float]],
               fade: float = 0.0) -> str:
    """A visibility track from the seconds a thing is *on*; `fade` ramps the
    edges, so two consecutive poses dissolve into each other."""
    steps = ["0%{opacity:0}"]
    for a, b in spans:
        if fade:
            steps.append(f"{_pct(max(0.0, a - fade))}{{opacity:0}}")
            steps.append(f"{_pct(a)}{{opacity:1}}")
            steps.append(f"{_pct(max(a, b - fade))}{{opacity:1}}")
            steps.append(f"{_pct(b)}{{opacity:0}}")
        else:
            steps.append(f"{_pct(a)}{{opacity:1}}")
            steps.append(f"{_pct(b)}{{opacity:0}}")
    return f"  @keyframes {name} {{ {' '.join(steps)} }}"


def _spans(script: list[tuple[float, str]], want: str) -> list[tuple[float, float]]:
    out = []
    for i, (t, pose) in enumerate(script):
        if pose != want:
            continue
        end = script[i + 1][0] if i + 1 < len(script) else SCRIPT
        out.append((t, end))
    return out


def _eye_css() -> str:
    """
    The gaze: one fade per pose, all on the same clock.

    Every pose is a full map of the iris, so a change never leaves a ghost
    behind; the fades are short (0.34 s) so what you see is movement, not a
    cross-dissolve.
    """
    rules = ["  .look { opacity: 0; }"]
    for pose in sorted({p for _, p in GAZE} - {"c"}):
        spans = _spans(GAZE, pose)
        if not spans:
            continue
        rules.append(_keyframes(f"g-{pose}", spans, FADE))
        rules.append(f"  .g-{pose} {{ animation: g-{pose} {CYCLE}s "
                     f"ease-in-out infinite; }}")
    rules.append("  @media (prefers-reduced-motion: reduce) "
                 "{ * { animation: none !important } }")
    return "\n".join(rules) + "\n"


def _css(h: int) -> str:
    return Template("""
  /* the caret: the one thing in the session that blinks */
  .blink { animation: caret 1.1s steps(1,end) infinite; }
  @keyframes caret { 0%,55% { opacity:1 } 56%,100% { opacity:0 } }
  .wipe { animation: wipe 1.1s cubic-bezier(.6,0,.35,1) both;
          transform-box: fill-box; transform-origin: top center; }
  @keyframes wipe { from { transform: scaleY(1) } to { transform: scaleY(0) } }
  .scan { animation: scan 20s linear 3s infinite; }
  @keyframes scan { 0% { transform: translateY(0); opacity:0 }
                    3% { opacity:.2 } 97% { opacity:.07 }
                    100% { transform: translateY($h px); opacity:0 } }
""" + _eye_css()).substitute({"h": h})


def meter(frac: float, width: int) -> str:
    """A half-block gauge: ▄▄▄▄▄"""
    filled = int(round(max(0.0, min(1.0, frac)) * width))
    return "▄" * filled + " " * (width - filled)


def _top(path: str) -> dict:
    """
    The frame's top rule, cut into the runs that carry their own colour:
    `┌──┤ ~/github/Green_Eye ├────────────┐`, always INNER+2 columns.

    No clock up here: the time belongs to the session (`$ date`), and a window
    that says the same thing twice is exactly the clutter we are removing.
    """
    lead = "┌──┤ "
    mid_at = len(lead) + len(path)
    return {"lead": lead, "path": path, "mid_at": mid_at,
            "dash": "├" + "─" * (INNER - mid_at - 1), "end": "─┐"}


# ── the picture ──────────────────────────────────────────────────────────────

def _avatar() -> dict:
    with open(AVATAR_FILE, encoding="utf-8") as f:
        return json.load(f)


def _cells(raw: bytes, cols: int, rows: int) -> dict:
    """Decode the two-byte-per-cell payload into {(y, x): (colour, ink)}."""
    out = {}
    for y in range(rows):
        for x in range(cols):
            i = 2 * (y * cols + x)
            col, ink = raw[i], raw[i + 1]
            out[(y, x)] = None if col == 0xEE else (col, ink)
    return out


def _ink(ink: int, ramp: str) -> int:
    """Ink level -> the CP437 code of the character that draws it."""
    return A.cp437(ramp[max(1, min(len(ramp) - 1, ink))])


def _emit(cells: dict, palette: list[str], ramp: str, klass: str = "") -> str:
    """
    Group the cells by glyph *and* colour.

    A 256-colour portrait is 924 cells in ~200 colours: one <g> per colour would
    mean 200 groups and the same <use> copied 200 times. Instead the whole
    picture is one <g> whose children say `fill="..."` per cell — every element
    still carries its own colour, and the browser groups the fills itself.
    """
    cls = f' class="{klass}"' if klass else ""
    out = []
    for (y, x), cell in cells.items():
        if cell is None:
            continue
        col, ink = cell
        out.append(f'<use href="#v{_ink(ink, ramp)}" x="{x * A.CW:.0f}" '
                   f'y="{y * A.CH:.0f}" fill="{palette[col]}"/>')
    return f'<g{cls}>{"".join(out)}</g>'


def _eye(c: dict) -> tuple[str, int]:
    """
    One base and one group per pose.

    The base is every cell of the portrait, drawn once. Each pose is a full map
    of the iris *only*: swapping whole maps means the moving part never leaves a
    translucent copy of itself on screen, which is exactly what a sliding patch
    does.
    """
    av = _avatar()
    cols, rows = av["cols"], av["rows"]
    iris_raw = base64.b64decode(av["iris"])
    iris = {(y, x): bool(iris_raw[y * cols + x]) for y in range(rows)
            for x in range(cols)}
    centre = _cells(base64.b64decode(av["centre"]), cols, rows)
    pal, ramp = av["palette"], av["ramp"]

    pic = _emit(centre, pal, ramp)
    for pose, raw in av["look"].items():
        shifted = _cells(base64.b64decode(raw), cols, rows)
        pic += _emit({k: v for k, v in shifted.items()
                      if iris.get(k) and v is not None}, pal, ramp,
                     f"look g-{pose}")
    # No transform on the portrait: moving glyphs with CSS takes them off the
    # character grid and the illusion breaks. The whole-eye movement is baked
    # into the maps (the body roll in avatar.py), so every frame is still a
    # terminal printed with the same font, cell for cell.
    return (f'<g transform="translate({PX * A.CW},{PY})">'
            f'<g class="ball">{pic}</g></g>', rows)


# ── the session ──────────────────────────────────────────────────────────────

RULE = "─" * INNER          # one separator, used everywhere, never mixed


def _about() -> dict:
    """The hand-written part of the profile: the owner's own words."""
    with open(ABOUT_FILE, encoding="utf-8") as f:
        return json.load(f)


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def session(d: dict, c: dict) -> str:
    """
    The whole screen: the eye and its column, then the blocks underneath.

    The body is drawn into a list while its last row is tracked, and the frame
    is sized from that — a card can then never clip its own contents.

    Layout rule, everywhere: a block is a `$ command` row, its output, and one
    empty row. Nothing else separates two blocks, so the screen reads as one
    session and not as a pile of widgets.
    """
    u, t, con = d["user"], d["totals"], d["contributions"]
    about = _about()
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
              f"{t['issues']} issues", c["muted"]),
             ("", c["muted"]),
             ("$ date", c["accent3"]),
             (f"{stamp} UTC", c["muted"])]
    for i, (txt, col) in enumerate(side):
        body.append(A.text(A.CW * SIDE, PY + i * A.CH, txt, col))
    for i, (_, val, ceiling) in enumerate(stats):
        body.append(A.text(A.CW * (SIDE + 20), PY + (stats_at + i) * A.CH,
                           meter(val / ceiling, 14), c["accent"]))

    # ── about: the seven lines the owner wrote, in terminal clothing ────
    # Whatever is taller wins: the portrait grid or the column beside it.
    y = max(PY + eye_rows * A.CH, PY + len(side) * A.CH) + A.CH
    right = f"{len(about['lines'])} lines"
    body.append(A.text(A.CW, y, f"$ cat ~/{about['prompt']}", c["accent3"]))
    body.append(A.text(A.CW * (INNER - len(right)), y, right, c["dim"]))
    y += A.CH
    for item in about["lines"]:
        wrapped = _wrap(item["text"], INNER - 6)
        for chunk in wrapped:
            body.append(A.text(A.CW * 4, y, chunk, c["muted"]))
            y += A.CH
    # The same words again, as the reference list a man page prints at the
    # bottom. Labels, not links: GitHub draws this SVG through an <img>, and
    # nothing inside an <img> can be clicked.
    y += A.CH
    links = [l["label"] for item in about["lines"] for l in item["links"]]
    for i, label in enumerate(links):
        x = A.CW * (2 + (i % 4) * 25)
        row = y + (i // 4) * A.CH
        body.append(A.text(x, row, "▸ ", c["line"]))
        body.append(A.text(x + A.CW * 2, row, label[:21], c["accent3"]))
    y += ((len(links) + 3) // 4) * A.CH + A.CH

    # ── stack ───────────────────────────────────────────────────────────
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
    for i, l in enumerate(known):          # the dots GitHub draws by a repo
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
    body.append(A.text(A.CW, y, "$ history | cut -d: -f1 | uniq -c",
                       c["accent3"]))
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
    checks = [f"mypy.py {len(d['languages'])} langs",
              f"ascii {av['colours_used']}/256 cols",
              "gaze.c 20s clock"]
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

    # ── footer: the session ends on the prompt, nothing else ────────────
    prompt = "[eye@github ~]$ "
    body.append(A.text(A.CW * 2, y, prompt, c["accent3"]))
    body.append(A.text(A.CW * (2 + len(prompt)), y, "█", c["accent3"],
                       cls="blink"))
    y += A.CH * 2

    # ── frame, sized from the body ──────────────────────────────────────
    h = y + OY * 2 + 4
    top = _top("~/github/Green_Eye")
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
           + A.text(A.CW * (INNER + 2 - len(top["end"])), 0, top["end"],
                    c["line"])
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
    about = _about()
    parts = [
        "~/github/Green_Eye", "GREEN EYE", u.get("login", ""), u.get("location") or "",
        u.get("bio") or "", "$ uptime", "$ cat ~/stack", "$ ls -1 ~/repos | head -3",
        "$ contribution-graph --year", "less more", "streak longest peak active days",
        "$ history | cut -d: -f1 | uniq -c", "by hour", "lines",
        "peak UTC · hour by hour, from the daily counts",
        "$ make -j4 all && sha1sum ~/profile", "all ok",
        "$ ls -1 ~/repos | head -6", "of repos forks for all ok",
        "mypy.py langs ascii cols gaze.c 20s clock ~/profile UTC 256",
        "by bytes written", "no repo yet", "learning in use", "▸ · ", "$ date",
        f"$ cat ~/{about['prompt']}", av["ramp"], "- ", "$ date",
        "".join(i["text"] for i in about["lines"]),
        "".join(l["label"] for i in about["lines"] for l in i["links"]),
        "".join(n for n, _ in README_LANGS),
        "".join(lbl for _, lbl in TOOLS),
        "[eye@github ~]$ ",
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
