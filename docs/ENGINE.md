# Engine notes

A GitHub Action collects telemetry, draws one animated SVG and rewrites
`README.md` every four hours. No stats service, no JavaScript, no image hosting.

The page is a single CP437 console window: text on an 8×16 grid with the Linux
kernel's VGA font (Default8x16), and the profile picture drawn as coloured
characters on that same grid.

## Layout

```
.github/workflows/readme.yml   cron 7 */4 * * *  -> collect -> render -> readme -> check -> commit
scripts/
  collect.py       GitHub data -> assets/readme/data/telemetry.json
  avatar.py        assets/readme/photo/eye.png -> assets/readme/data/avatar.json (44x24 cells)
  render.py        data -> assets/readme/live/profile-dark.svg
  readme.py        data -> README.md (the img tag and nothing else)
  check.py         guard rail: XML, dead glyph refs, animation present, data sane
  update_readme.py the whole pipeline, the command the workflow runs
  preview.py       docs/preview.html, everything inlined
  mock_readme.py   docs/readme-dark.png, the card inside a mock profile page
  qa.py            cards to PNG with headless Chromium (dev only)
  svg/kit.py       palette and small SVG helpers
  svg/ascii.py     the text layer: font, CP437 table, glyph paths, meters
  svg/common.py    card chrome, shared motion
  svg/cards/tui.py the session, top to bottom
```

```bash
python3 scripts/collect.py        # network; GITHUB_TOKEN optional
python3 scripts/avatar.py         # Pillow + numpy; only when the photo changes
python3 scripts/render.py --data assets/readme/data/telemetry.json
python3 scripts/readme.py --data assets/readme/data/telemetry.json
python3 scripts/check.py
python3 scripts/preview.py        # optional offline look
```

The routine build uses only the standard library. `avatar.py` needs Pillow and
numpy, and its output is committed, so CI never runs it.

## One theme, one file, one object

The card ships dark only. A light palette would need a second SVG, a second
round of PNG checks and a `<picture>` element that can show the wrong variant
after a cache miss, and the portrait sits on the panel colour: unpainted cells
are not drawn at all, so the picture is only seamless while that colour is the
dark one. `kit.THEMES` holds one palette, `render.py` writes one file, and the
console looks the same for every visitor.

GitHub sanitizes the HTML of a README but does not look inside an image, so the
card is a self-contained animated SVG loaded with `<img>`. Consequences:

- all CSS lives inside the SVG, out of the sanitizer's reach;
- the photo, the font and the icons are embedded (base64), because an SVG
  loaded through `<img>` cannot fetch anything external;
- links are impossible. Topics stay in `about.json` and are printed as labels.

`assets/readme/live/css/` also holds each card with its `<style>` extracted,
plus a deduplicated bundle, for inlining the SVG by hand.

## Data

| number | source |
| --- | --- |
| contributions per day | `github.com/users/<user>/contributions`, parsed from the calendar tooltips |
| commits, PRs, issues | Search API, one request each |
| stars, forks, repos, languages | REST API, per-repo `/languages`; forks and archived repos excluded |
| followers, profile | REST API |
| contributed to | GraphQL, only with a PAT, else 0 |
| fallback | `github.com/<user>` HTML: pinned repos, stars, forks, followers, bio |

Every source is wrapped. A failure is recorded in `meta.degraded` and the build
continues. If the calendar scrape fails, the data is marked `synthetic` and
`check.py` fails the build rather than publish invented numbers.

Anonymous REST allows 60 requests per hour, not enough for 40 repositories, so
`collect.py` fetches languages for the 40 largest and stops at the first 403.
It then degrades in order: reuse the last good values from the previous
`telemetry.json`; if the API is gone entirely, scrape the profile page; if both
fail, draw from the history snapshot. A `GH_STATS_TOKEN` secret raises the limit
to 5000 per hour and enables GraphQL.

## The portrait

44 × 24 cells, one colour and one ink level per cell.

- **Colour** is an index in the xterm-256 table (`xterm256()`: 16 system
  colours, a 6×6×6 cube, a 24-step grey ramp). The portrait uses 74 of the 256,
  which is what keeps the iris's olive-to-yellow falloff and the blue highlight
  instead of four flat tones.
- **Dither.** A 6×6×6 cube has six levels per channel, so the colour is chosen
  with an ordered Bayer dither, the same trick a 256-colour terminal uses.
  `DITHER` and `LIFT` are the knobs.
- **Character** comes from the ramp `" .:-=+*#%@"` and encodes ink: brightness
  blended with local detail. Short on purpose, because colour carries the tone;
  a 68-character ramp turned the portrait into noise.
- **Pupil** is left empty. On a terminal, black is the absence of ink.

`avatar.json` stores two bytes per cell (xterm index, ink level) plus a one-byte
iris mask, base64, about 40 kB for the centre and twelve poses.

## Motion

One cycle (`CYCLE` in `svg/cards/tui.py`) drives everything, and every event is
a percentage of it, so the poses cannot drift apart.

- **Gaze.** Thirty keyframes over twelve poses baked into `avatar.json`
  (`l1 l2 l3 r1 r2 r3 u1 u2 d1 d2` and two diagonals), with pauses of one to
  three seconds between movements. Each pose is one cell from the previous one,
  so a change of direction is a short run of small steps, not a jump.
- **The body moves too.** Past one cell of look, the whole picture rolls with it
  by one cell (`poses` in `avatar.py`), and the iris rolls on top. An earlier
  version did this with CSS `translate`/`rotate`, which moves glyphs off the
  character grid: the text blurs and the console stops looking like a console.
  Every frame is now a grid drawn with the same font, cell for cell.
- **Tempo.** `SCRIPT` is the duration the keyframe table was written for,
  `CYCLE` the duration it plays at (16 s), `FADE` the dissolve between poses
  (0.18 s). Change `CYCLE` for a faster or slower performance; no keyframe
  needs editing.
- **Scan line.** A slow band moving down the card, 20 s.

`prefers-reduced-motion: reduce` turns all of it off. The only blinking element
in the session is the caret at the prompt (`1.1 s`).

## Changing things

- **Username**: `README_USER` in the workflow, or the env var locally.
- **Pinned repos**: `PINS` for `collect.py`.
- **Palette**: `THEMES` in `scripts/svg/kit.py`.
- **Photo**: replace `assets/readme/photo/eye.png` and rerun `avatar.py`
  (`AVATAR_SRC` overrides the path). Knobs: `COLS`/`ROWS`, `RAMP`, `DITHER`,
  `LIFT`, the blur radius and the detail weight.
- **Font**: `assets/readme/fonts/vga8x16.json`, the kernel's
  `lib/fonts/font_8x16.c` as base64. Each glyph becomes a path of horizontal
  runs, emitted once in `<defs>` and reused with `<use>`.
- **Icons**: Simple Icons paths (CC0) in `assets/readme/icons/brands.json`.
- **Cards**: each is a function `render(data, theme) -> svg`. Remove a line from
  `CARDS` in `render.py`, and the matching `<img>` from `readme.py`.
- **Copy**: the seven hand-written lines are in
  `assets/readme/data/about.json`. They are never collected, the terminal prints
  them, and `check.py` fails if the file stops holding seven complete entries.
  `README.md` itself carries no prose.
- **Pixel art**: a separate 53×7 grid in
  `.github/workflows/ghost-activity.yml`.

## README.md is one image

`README.md` is an `<img>` between two comments. The old `<details>` block and
its bullet list were removed because they introduced a second visual language on
the page. Anything worth stating is printed by the terminal or written in
`about.json`.

## Credits

The links, the projects and the green belong to the original author. The engine
in `scripts/` is original code.
