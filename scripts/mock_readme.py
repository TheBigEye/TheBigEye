#!/usr/bin/env python3
"""
mock_readme.py — how the README looks on the GitHub profile page.

Builds a throwaway page with GitHub's own profile layout (header, tabs, README
box) and drops the generated SVG into it, then screenshots it with headless
Chromium, once per theme.

    python3 scripts/mock_readme.py            -> docs/readme-dark.png
"""

from __future__ import annotations

import asyncio
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, "assets/readme/live")
OUT = os.path.join(ROOT, "docs")
PHOTO = os.environ.get("AVATAR_SRC", "/home/user/uploads/63316583.jpg")

BULLETS = [
    ("🔭 I’m currently working on <b>Monarch OS</b> and <b>Aircraft</b>."),
    ("❤️ I love <b>Python</b>, <b>Java</b> and <b>C</b>."),
    ("👀 I am focused on the development of <b>Games</b>, "
     "<b>Operating Systems</b>, and <b>IA</b>."),
    ("🌱 I’m currently learning <b>Rust</b> and <b>COBOL</b> for fun."),
    ("👯 I’m currently collaborating on <b>Minicraft+</b>."),
    ("⚡ Fun fact, I love <b>Assembly</b>, is faster and sometimes easy to learn."),
    ("🎨 <b>Green</b> is my favorite color."),
]

THEMES = {
    # Only the dark GitHub page is mocked: the card itself is always dark, so
    # that is the pairing worth checking.
    "dark": dict(
        bg="#0d1117", panel="#0d1117", box="#161b22", text="#e6edf3",
        muted="#9198a1", border="#30363d", link="#4493f8", btn="#21262d",
        tab="#f0f6fc", underline="#f78166", chip="#3d444d",
    ),
}


def html(mode: str, data: dict) -> str:
    t = THEMES[mode]
    u = data["user"]
    login, name = u.get("login", ""), u.get("name", "")
    bio = u.get("bio", "")
    followers, following = data["totals"]["followers"], data["totals"]["following"]
    bullets = "\n".join(f"<li>{b}</li>" for b in BULLETS)
    img = "../assets/readme/live/profile-dark.svg"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:{t['bg']}; color:{t['text']};
          font: 14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,
                Arial,sans-serif; }}
  .page {{ max-width: 1012px; margin: 0 auto; padding: 24px 16px 40px; }}
  .head {{ display:flex; gap:24px; align-items:center; padding-bottom:16px;
           border-bottom:1px solid {t['border']}; }}
  .avatar {{ width:96px; height:96px; border-radius:50%; object-fit:cover;
             border:1px solid {t['border']}; }}
  .who {{ flex:1; }}
  .name {{ font-size:24px; font-weight:600; line-height:1.25; }}
  .login {{ color:{t['muted']}; font-size:20px; font-weight:300; }}
  .bio {{ margin-top:4px; color:{t['text']}; }}
  .social {{ color:{t['muted']}; font-size:12px; margin-top:6px; }}
  .social b {{ color:{t['text']}; font-weight:600; }}
  .follow {{ background:{t['btn']}; color:{t['text']};
             border:1px solid {t['border']}; border-radius:6px;
             padding:5px 16px; font-size:14px; font-weight:500; }}
  .tabs {{ display:flex; gap:8px; margin:16px 0 20px; color:{t['muted']};
           font-size:14px; }}
  .tab {{ padding:6px 8px; display:flex; align-items:center; gap:6px; }}
  .tab.on {{ color:{t['tab']}; font-weight:600;
             border-bottom:2px solid {t['underline']}; }}
  .readme {{ border:1px solid {t['border']}; border-radius:6px;
             background:{t['box']}; }}
  .readme header {{ display:flex; align-items:center; gap:8px; padding:8px 16px;
                    border-bottom:1px solid {t['border']}; color:{t['muted']};
                    font-size:12px; }}
  .dot {{ width:8px; height:8px; border-radius:50%; background:{t['chip']}; }}
  .body {{ padding:24px 32px 40px; }}
  .body ul {{ margin:0; padding-left:26px; }}
  .body li {{ margin:0 0 6px; }}
  .body b {{ font-weight:600; }}
  .card {{ margin-top:18px; text-align:center; }}
  .card img {{ width:100%; height:auto; display:block; }}
  .details {{ margin-top:22px; border:1px solid {t['border']}; border-radius:6px;
              padding:8px 12px; color:{t['muted']}; font-size:13px; }}
  .details b {{ color:{t['text']}; }}
</style></head><body><div class="page">
  <div class="head">
    <img class="avatar" src="file://{PHOTO}">
    <div class="who">
      <div><span class="name">{name}</span> <span class="login">{login}</span></div>
      <div class="bio">{bio}</div>
      <div class="social"><b>{followers}</b> followers · <b>{following}</b> following
        · <span>127.0.0.1</span></div>
    </div>
    <div class="follow">Follow</div>
  </div>
  <div class="tabs">
    <div class="tab on">◧ Overview</div>
    <div class="tab">Repositories<span style="background:{t['chip']};
      border-radius:20px; padding:0 6px; font-size:12px">40</span></div>
    <div class="tab">Projects</div><div class="tab">Packages</div>
    <div class="tab">Stars</div>
  </div>
  <div class="readme">
    <header><span class="dot"></span> README.md</header>
    <div class="body">
      <div class="card"><img src="{img}"></div>
      <ul>{bullets}</ul>
      <div class="details"><b>▲ how this README is built</b></div>
    </div>
  </div>
</div></body></html>"""


async def shot(mode: str, data: dict) -> str:
    from playwright.async_api import async_playwright

    tmp = os.path.join(OUT, f".mock-{mode}.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html(mode, data))
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1044, "height": 900},
                              device_scale_factor=2)
        await pg.goto(f"file://{tmp}")
        await pg.wait_for_timeout(1200)
        # Freeze the clock at a frame where the eye is open and looking at the
        # viewer: a screenshot of an animation should not depend on timing.
        await pg.evaluate(
            "document.getAnimations().forEach("
            "a => { a.currentTime = 300; a.pause(); })")
        height = await pg.evaluate("document.body.scrollHeight")
        await pg.screenshot(path=os.path.join(OUT, f"readme-{mode}.png"),
                            clip={"x": 0, "y": 0, "width": 1044, "height": height})
        await b.close()
    os.remove(tmp)
    return os.path.join(OUT, f"readme-{mode}.png")


def main() -> None:
    with open(os.path.join(ROOT, "assets/readme/data/telemetry.json"),
              encoding="utf-8") as f:
        data = json.load(f)
    path = asyncio.run(shot("dark", data))
    size = os.path.getsize(path) / 1024
    print(f"✓ {os.path.relpath(path, ROOT)} ({size:.0f} kB)")


if __name__ == "__main__":
    main()
