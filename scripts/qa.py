"""qa.py — render every card to a PNG so the layout can be eyeballed."""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, "assets/readme/live")
ORDER = ["profile"]

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body {{ margin:0; padding:24px; background:{bg};
      font-family: -apple-system, sans-serif; }}
.wrap {{ max-width: 880px; margin: 0 auto; }}
img {{ display:block; width:100%; margin-bottom:8px; }}
h4 {{ color:{fg}; font-size:11px; letter-spacing:1px; text-transform:uppercase;
      opacity:.4; margin:14px 0 4px; }}
</style></head><body><div class="wrap">{body}</div></body></html>"""


async def shot(mode: str, wait: float, out: str):
    bg = "#0d1117" if mode == "dark" else "#ffffff"
    fg = "#f0f6fc" if mode == "dark" else "#1f2328"
    body = ""
    for name in ORDER:
        path = os.path.join(LIVE, f"{name}-{mode}.svg")
        if not os.path.exists(path):
            continue
        body += f'<h4>{name}</h4><img src="file://{path}">'
    html = HTML.format(bg=bg, fg=fg, body=body)
    tmp = os.path.join(ROOT, f".qa-{mode}.html")
    with open(tmp, "w") as f:
        f.write(html)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 940, "height": 5600},
                              device_scale_factor=1)
        await pg.goto(f"file://{tmp}")
        await pg.wait_for_timeout(int(wait * 1000))
        await pg.screenshot(path=out, full_page=False, clip={"x":0,"y":0,"width":940,"height":min(5600, await pg.evaluate("document.body.scrollHeight"))})
        await b.close()
    print("→", out)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "dark"
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 3.6
    out = sys.argv[3] if len(sys.argv) > 3 else f"/home/user/qa-{mode}.png"
    asyncio.run(shot(mode, wait, out))
