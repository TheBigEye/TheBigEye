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
  readme.py      data → README.md                          (the img tag, nothing else)
  check.py       guard rail: XML validity, dead refs, animation present
  preview.py     docs/preview.html — everything inlined, for offline review
  qa.py          renders the cards to PNG with headless Chromium (dev only)
  update_readme.py  the whole pipeline, the same command the workflow runs
  mock_readme.py    docs/readme-dark.png — the README inside a mock
                    GitHub profile page, to check it in context
  avatar.py      the photo → assets/readme/data/avatar.json (44×24 characters)
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

A terminal with a white background is a contradiction, and the ASCII portrait
sits directly on the panel colour: the cells that carry no ink are simply not
drawn, so the picture merges with the screen. Shipping two palettes meant
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

Everything the eye does hangs off **one played cycle** (`CYCLE` in
`svg/cards/tui.py`), and every event is expressed as a percentage of it, so the
poses can never drift apart.

* **the portrait** — 44 × 24 cells of the same VGA grid. Each cell carries a
  **terminal colour** and an ink level:

  * the colour is an index into the real **xterm-256** table (`xterm256()` builds
    it: 16 system colours, a 6×6×6 cube, a 24-step grey ramp) — the portrait
    actually uses ~80 of them, so the iris keeps its olive→yellow falloff and the
    highlight keeps its blue instead of being crushed into four tones;
  * a 6×6×6 cube only has six levels per channel, so the colour is chosen with
    an **ordered (Bayer) dither**: the same trick a 256-colour terminal uses to
    fake the tones it does not have. `DITHER` and `LIFT` are the two knobs;
  * the character comes from the short ramp `" .:-=+*#%@"` and encodes ink
    (brightness blended with local detail). Deliberately short: with 256 colours
    the colour carries the tone, and a 68-character ramp turned the portrait into
    a page of random text.

  The pupil is left empty on purpose: on a terminal, black is the absence of ink.
* **the gaze** — 30 keyframes, *twelve* baked poses (`l1 l2 l3 r1 r2 r3 u1 u2 d1
  d2` plus two diagonals), and **pauses**: the script alternates movement with
  holds of one to three seconds where the eye just stares, which is what reads as
  natural. Each pose is one cell further than the previous one, so a change of
  direction is a short sequence of small movements instead of a jump.
* **the whole eye moves, in cells** — past one cell of look, the *body* of the
  portrait rolls with it (one cell, in `avatar.py`), so the picture is alive as a
  whole and not an iris sliding inside a frozen frame. This is baked into the
  maps on purpose: an earlier version animated the portrait with CSS
  `translate`/`rotate`, which takes the glyphs off the character grid, blurs the
  text and breaks the illusion. **Every frame is still a terminal printed in the
  same font, cell for cell** — no transform ever touches the portrait.
* **tempo** — `SCRIPT` is the duration the table was written for, `CYCLE` the one
  it plays at (16 s), and `FADE` how fast one pose dissolves into the next
  (0.18 s). Fast movement, long holds: change `CYCLE` to make the whole
  performance faster or slower without touching a keyframe.
* **the scan line** — a slow band travelling down the card, 20 s.

`@media (prefers-reduced-motion: reduce)` turns all of it off.

There is exactly **one** blinking thing in the session: the caret at the prompt
(`.blink`, 1.1 s, driven by the `caret` keyframes).

## Make it yours

* **Username** — `README_USER` in the workflow (or the env var locally).
* **Pinned repos** — `PINS=python-os,monarch-os,...` feeds the projects card.
* **Palette** — one place: `THEMES` in `scripts/svg/kit.py`.
* **The photo** — `assets/readme/photo/eye.png` is the source of the portrait;
  swap it and rerun `avatar.py`. (`AVATAR_SRC` overrides the path.)
* **The portrait** — `scripts/avatar.py` maps the photo onto 44×24 cells of the
  xterm-256 palette (`RAMP`, `COLS`/`ROWS`, `DITHER`, `LIFT`, the blur `k` and
  the detail weight `w` are the knobs), emits nine maps (centre plus eight poses) and the
  iris mask; the card draws the base once and swaps the masked patch per pose.
  The payload is two bytes per cell (xterm index + ink level), base64, ~40 kB for
  the thirteen maps.
* **The font** — `assets/readme/fonts/vga8x16.json` is the kernel's
  `lib/fonts/font_8x16.c` as base64; every glyph becomes a path of horizontal
  runs, emitted once in `<defs>` and reused with `<use>`.
* **Toolbox** — the brand marks are Simple Icons paths (CC0) in
  `assets/readme/icons/brands.json`, so the build never touches the network.
* **Layout** — each card is a pure function `render(data, theme) -> svg`; delete
  a line in `CARDS` of `render.py` and the corresponding `<img>` in `readme.py`.
* **Copy** — the seven hand-written lines live in
  `assets/readme/data/about.json` (key, text, links). They are never collected:
  the terminal prints them, and `check.py` fails if the file stops having seven
  complete entries. The README itself carries no copy at all.
* **Pixel art** — the canvas lives in `.github/workflows/ghost-activity.yml`
  (53 × 7, `0` empty / `1` painted), independent of the cards.

## One object on the page

`README.md` is now an `<img>` between two HTML comments and a credits comment —
there is no markdown beside the console. The old `<details>` block ("how this
README is built") and the bullet list were removed on purpose: they pushed the
page into a second, unrelated visual language. Everything that is worth saying
is printed by the terminal or written in `about.json`, and the "generated by"
footer inside the card is gone as well, so the session ends on a prompt.

A consequence worth knowing: an SVG drawn through `<img>` cannot contain a
clickable link. The topics (`https://github.com/topics/...`) are kept in
`about.json` as the reference list under the about block, but on GitHub they are
labels, not links. If the links matter more than the single-object look, add a
short markdown list after the image and `check.py` will not complain.

## Credits

The list of links, the projects and the green are the original author's.
The engine (collector, renderer, cards, motion) is original code in `scripts/`.
