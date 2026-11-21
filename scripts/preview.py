#!/usr/bin/env python3
"""
preview.py — builds a single self-contained preview.html (every SVG inlined as
a data URI) so the result can be inspected offline, inside a dark page.

    python3 scripts/preview.py            ->  docs/preview.html
"""

from __future__ import annotations

import base64
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, "assets/readme/live")
OUT = os.path.join(ROOT, "docs/preview.html")

ORDER = ["profile"]
TITLES = {
    "profile": ("session · tty1",
                "one terminal: the eye in ANSI, the stack, the year, the toolbox"),
}


def uri(path: str) -> str:
    with open(path, "rb") as f:
        return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()


def main() -> None:
    d = json.load(open(os.path.join(ROOT, "assets/readme/data/telemetry.json"),
                       encoding="utf-8"))
    t = d["totals"]
    rows = []
    for name in ORDER:
        art = uri(os.path.join(LIVE, f"{name}-dark.svg"))
        title, why = TITLES[name]
        rows.append(f"""
    <section>
      <div class="meta"><span class="n">{title}</span><span class="w">{why}</span></div>
      <img src="{art}" alt="{name}">
    </section>""")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Animated profile — preview</title>
<style>
  :root {{ --bg:#0d1117; --fg:#f0f6fc; --muted:#9ba7b4; --line:#30363d;
           --accent:#3fb950; --card:#161b22; color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
          font: 14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 40px 20px 80px; }}
  header.top {{ display:flex; align-items:baseline; justify-content:space-between;
                gap:16px; border-bottom:1px solid var(--line); padding-bottom:14px;
                margin-bottom:8px; flex-wrap:wrap; }}
  h1 {{ font-size: 19px; margin:0; letter-spacing:-.2px; }}
  h1 b {{ color: var(--accent); }}
  .tag {{ font-family: ui-monospace,monospace; font-size:11px; color:var(--muted); }}
  .kpis {{ display:flex; gap:8px; flex-wrap:wrap; margin:18px 0 26px; }}
  .kpi {{ border:1px solid var(--line); background:var(--card); border-radius:10px;
          padding:8px 12px; font-family: ui-monospace,monospace; font-size:11px;
          color:var(--muted); }}
  .kpi b {{ display:block; font-size:16px; color:var(--fg); font-family:inherit; }}
  section {{ margin: 30px 0 6px; }}
  .meta {{ display:flex; gap:10px; align-items:baseline; margin-bottom:6px; }}
  .n {{ font-family: ui-monospace,monospace; font-size:10px; letter-spacing:1.4px;
        text-transform:uppercase; color:var(--accent); }}
  .w {{ font-size:11px; color:var(--muted); }}
  img {{ display:block; width:100%; height:auto; }}
  .note {{ margin-top:46px; border-top:1px solid var(--line); padding-top:16px;
           font-size:12px; color:var(--muted); }}
  code {{ font-family: ui-monospace,monospace; font-size:11.5px;
          background: var(--card); padding:1px 5px; border-radius:4px;
          border:1px solid var(--line); }}
</style></head>
<body><div class="wrap">
  <header class="top">
    <h1>github.com/<b>{d['user'].get('login','')}</b> — animated profile</h1>
    <span class="tag">offline preview · {d['generated_at'][:16].replace('T',' ')} UTC</span>
  </header>
  <div class="kpis">
    <div class="kpi"><b>{t['contributions']}</b>contributions</div>
    <div class="kpi"><b>{t['commits']}</b>commits</div>
    <div class="kpi"><b>{t['stars']}</b>stars</div>
    <div class="kpi"><b>{t['rank']['grade']}</b>rank</div>
    <div class="kpi"><b>{d['contributions']['streak']['longest']}d</b>best streak</div>
  </div>
  {''.join(rows)}
  <p class="note">
    Every image above is one self-contained SVG: CSS keyframes only, no JavaScript,
    no external request. Motion is skipped automatically when the viewer asks for
    <code>prefers-reduced-motion</code>. Toggle your OS theme to see the other palette.
  </p>
</div></body></html>"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ {os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT)/1024:.0f} kB)")


if __name__ == "__main__":
    main()
