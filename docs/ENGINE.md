# The animated profile engine

The README is generated: a GitHub Action collects telemetry, draws one animated
SVG and rewrites `README.md` every four hours. No third-party stats service, no
JavaScript, no image hosting.

The look is a single Linux console session: the card is one CP437 window drawn
with the kernel's VGA font (Default8x16) on an 8x16 character grid, and the
profile picture is ANSI block art sitting on the window's own background.

```
.github/workflows/readme.yml     cron 7 */4 * * *  →  collect → render → readme → check → commit
scripts/
  collect.py     real data → assets/readme/data/telemetry.json (+ daily history)
  render.py      data → assets/readme/live/profile-dark.svg   (one theme, dark)
  readme.py      data → README.md                          (keeps the hand-written list)
  check.py       guard rail: XML validity, dead refs, animation present
  preview.py     docs/preview.html — everything inlined, for offline review
  qa.py          renders the cards to PNG with headless Chromium (dev only)
  update_readme.py  the whole pipeline, the same command the workflow runs
  mock_readme.py    docs/readme-dark.png — the README inside a mock
                    GitHub profile page, to check it in context
  avatar.py      the photo → assets/readme/data/avatar.json (40×20 ANSI cells)
  svg/kit.py     palette and the few SVG primitives still in use
  svg/ascii.py   the VGA text layer: font, CP437 table, glyph paths, meters
  svg/common.py  card chrome + the shared motion language
  svg/cards/tui.py  the whole session, top to bottom: eye + account column ·
                 stack · repos · contribution year · hours histogram ·
                 build status + sha1sum · toolbox · footer
```

Run it locally:

```bash
python3 scripts/collect.py        # needs network; GITHUB_TOKEN optional
python3 scripts/avatar.py         # needs Pillow + numpy; rerun when the photo changes
python3 scripts/render.py --data assets/readme/data/telemetry.json
python3 scripts/readme.py --data assets/readme/data/telemetry.json
python3 scripts/check.py
python3 scripts/preview.py        # optional offline look
```

Only the standard library is used for the routine build, so nothing to install
in CI. `avatar.py` is the single exception (Pillow + numpy) and its output is
committed, so the workflow never runs it.

---

## Why it is dark only

A terminal with a white background is a contradiction, and the ANSI portrait
depends on the panel colour: the lids that hide the eye at the blink are filled
with `panel`, so the picture merges with the screen. Shipping two palettes meant
two animations, two PNG checks and a `<picture>` element that could show the
wrong one after a cache miss. Now `kit.THEMES` holds a single palette, `render`
writes one SVG, and GitHub — light or dark mode — shows the same console.

## Why the card is an `<img>` and not inline SVG

GitHub runs a strict sanitizer over the HTML of a README, but it never looks
inside an image. So:

* each card is a **self-contained animated SVG** loaded with a plain `<img>`;
* all the CSS (`@keyframes`, animations, `prefers-reduced-motion`) lives **inside**
  that SVG, where the sanitizer can't reach;
* the CRT photo is embedded as a base64 data URI, because an SVG loaded through
  `<img>` is firewalled from every external resource (it cannot fetch `../x.png`);
* there is **one** file and no `<picture>`: the card is a console, so it is dark
  for everyone. A white terminal would also break the portrait — the eyelids are
  painted in the panel's exact colour, and the eye is only seamless while that
  colour is the dark one.

There is also a `assets/readme/live/css/*.src.svg` copy of every card with its
`<style>` extracted (plus a deduplicated bundle). Those are the files to use if
you ever want to inline the SVG in the README yourself — GitHub does keep a
`<style>` block that lives *inside* an inline `<svg>` element.

## How the data stays honest

| number | source | notes |
| --- | --- | --- |
| contributions / day | `github.com/users/<user>/contributions` HTML | exact counts, parsed from the calendar tooltips |
| commits, PRs, issues | Search API | one request each |
| stars, forks, repos, languages | REST API + per-repo `/languages` | forks and archived repos excluded |
| followers, profile | REST API | |
| contributed-to | GraphQL (only with a PAT) | falls back to 0 |
| repo fallback | `github.com/<user>` HTML | pinned repos, stars, followers when the API is down |

Every source is wrapped: if one fails, `collect.py` records it under
`meta.degraded`, keeps going, and the README still renders. If the calendar
scrape fails entirely the data is marked `synthetic` and `check.py` fails the
build instead of publishing a lie.

Rate limit? Anonymous REST gives 60 requests/h — not enough for 40 repos, so
`collect.py` fetches languages for the 40 largest repos only, **stops touching the
API as soon as it sees a 403**, and then degrades in this order:

1. reuse the last known good values from the previous `telemetry.json`;
2. if the API is entirely unavailable, scrape the public profile page
   (pinned repos, stars, forks, followers, bio) — the cards keep their numbers;
3. only if *both* fail, the card is drawn from the history snapshot. Add a `GH_STATS_TOKEN` secret
(a PAT with `read:user`) and the workflow gets 5000 requests/h plus GraphQL.

## The motion language

Everything the eye does hangs off **one 16 s clock** (`CYCLE` in
`svg/cards/tui.py`), and every event is expressed as a percentage of it, so the
gaze and the blink can never drift apart.

* **the gaze** — the portrait ships nine cell maps: the centre, eight poses
  (left and right at two widths, up, down, and two corners). Only the iris patch
  is swapped, in `steps(1, end)` so the eye *lands* on a pose instead of sliding
  through pixels. The script changes pose about every 1.5 s and returns to the
  viewer often — the eye looks at you, glances at the repos, comes back.
* **the blink** — not a rectangle: nine character rows vanish from the top and
  nine from the bottom, one row at a time, in the panel colour. The lid is the
  terminal clearing its own rows, so a blink removes characters instead of
  covering a picture. While the lids are down a single row of `▄` (the lash)
  keeps the shape readable. Two slow blinks and a double one per cycle; the
  fastest row takes 60 ms, which is four frames at 60 Hz.
* **the breath** — the whole ball scales by 1.5 % over 7.5 s, unrelated to the
  clock on purpose, so the two motions never synchronise into a loop the eye can
  predict.
* **the scan line** — a slow band travelling down the card, 16 s.

`@media (prefers-reduced-motion: reduce)` turns all of it off.

There is exactly **one cursor** in the session — the block at the prompt. A
blinking block beside the portrait was removed: two of them looked like two
shells waiting.

## Make it yours

* **Username** — `README_USER` in the workflow (or the env var locally).
* **Pinned repos** — `PINS=python-os,monarch-os,...` feeds the projects card.
* **Palette** — one place: `THEMES` in `scripts/svg/kit.py`.
* **The portrait** — `scripts/avatar.py` quantises the photo to 10 colours and
  40×20 cells, emits nine maps (centre plus eight poses) and the iris mask; the
  card only ever swaps the masked patch.
* **The font** — `assets/readme/fonts/vga8x16.json` is the kernel's
  `lib/fonts/font_8x16.c` as base64; every glyph becomes a path of horizontal
  runs, emitted once in `<defs>` and reused with `<use>`.
* **Toolbox** — the brand marks are Simple Icons paths (CC0) in
  `assets/readme/icons/brands.json`, so the build never touches the network.
* **Layout** — each card is a pure function `render(data, theme) -> svg`; delete
  a line in `CARDS` of `render.py` and the corresponding `<img>` in `readme.py`.
* **Copy** — the bullet list in the README is never generated; edit it by hand
  and the build preserves it verbatim.
* **Pixel art** — the canvas lives in `.github/workflows/ghost-activity.yml`
  (53 × 7, `0` empty / `1` painted), independent of the cards.

## Credits

The list of links, the projects and the green are the original author's.
The engine (collector, renderer, cards, motion) is original code in `scripts/`.
