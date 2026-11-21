"""
collect.py — the data layer of the README.

Grabs *real* telemetry for a GitHub user and dumps a single data.json that the
renderer turns into animated SVG. No third-party services, no Vercel instances:

  · REST API      -> profile, repos, stars, languages, public events
  · search API    -> commits / PRs / issues (exact totals)
  · GraphQL       -> contributed-to count (optional, silent fallback)
  · contribution  -> exact per-day contribution counts, scraped from the profile
    calendar        calendar HTML (public, no token needed)

Each source is wrapped: if one dies, the run still produces a complete,
beautiful README — it just marks the source as degraded.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

USER = os.environ.get("README_USER", "TheBigEye")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
API = "https://api.github.com"
UA = f"readme-engine (+https://github.com/{USER})"
OUT = os.environ.get("DATA_OUT", "data.json")
HISTORY_DIR = os.environ.get("DATA_HISTORY", "assets/readme/data/history")
HISTORY_KEEP = int(os.environ.get("DATA_HISTORY_KEEP", "90"))

_langs = {}
_report = {"degraded": [], "sources": {}}


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP
# ─────────────────────────────────────────────────────────────────────────────

def _headers(extra: dict | None = None) -> dict:
    h = {"User-Agent": UA, "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    if extra:
        h.update(extra)
    return h


def http(url: str, *, method="GET", body: dict | None = None,
         accept: str | None = None, tries: int = 3):
    extra = {"Accept": accept} if accept else None
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=_headers(extra),
                                         method=method)
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read().decode("utf-8", "replace")
                remaining = r.headers.get("X-RateLimit-Remaining")
                if remaining is not None:
                    _report["sources"].setdefault("rate_limit_remaining", remaining)
                return raw
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {url}"
            if e.code in (403, 429) and attempt < tries - 1:
                time.sleep(3 + 3 * attempt)
                continue
            break
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e} ({url})"
            time.sleep(1 + attempt)
    raise RuntimeError(last or "request failed")


def jget(url: str, **kw):
    return json.loads(http(url, **kw))


def degrade(name: str, err: Exception | str) -> None:
    msg = f"{name}: {err}"
    _report["degraded"].append(msg)
    print(f"  ⚠️  {msg}", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────────────
#  Sources
# ─────────────────────────────────────────────────────────────────────────────

def fetch_user() -> dict:
    u = jget(f"{API}/users/{USER}")
    return {k: u.get(k) for k in ("login", "name", "bio", "avatar_url", "html_url",
                                  "public_repos", "followers", "following",
                                  "created_at", "location", "company", "blog",
                                  "twitter_username", "public_gists")}


def fetch_repos() -> list[dict]:
    repos, page = [], 1
    while page <= 5:
        batch = jget(f"{API}/users/{USER}/repos?per_page=100&page={page}"
                     f"&sort=pushed&type=owner")
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_events() -> list[dict]:
    try:
        ev = jget(f"{API}/users/{USER}/events/public?per_page=100")
        return ev if isinstance(ev, list) else []
    except Exception as e:  # noqa: BLE001
        degrade("events", e)
        return []


def fetch_counts() -> dict:
    """Exact totals through the search API (1 request each)."""
    out = {}
    for key, q in (("commits", f"author:{USER}"),
                   ("prs", f"author:{USER} type:pr"),
                   ("issues", f"author:{USER} type:issue")):
        try:
            j = jget(f"{API}/search/issues?q={urllib.parse.quote(q)}&per_page=1") \
                if key != "commits" else \
                jget(f"{API}/search/commits?q={urllib.parse.quote(q)}&per_page=1")
            out[key] = int(j.get("total_count", 0))
        except Exception as e:  # noqa: BLE001
            degrade(f"search/{key}", e)
    return out


def fetch_contributed_to() -> int | None:
    """Only GraphQL exposes 'repos I contributed to'. Optional."""
    if not TOKEN:
        return None
    q = """query($login:String!){user(login:$login){
             repositoriesContributedTo(first:1,includeUserRepositories:false,
               contributionTypes:[COMMIT,PULL_REQUEST,ISSUE]){totalCount}}}"""
    try:
        raw = http(f"{API}/graphql", method="POST", body={"query": q,
                                                          "variables": {"login": USER}})
        j = json.loads(raw)
        node = (j.get("data") or {}).get("user") or {}
        return int((node.get("repositoriesContributedTo") or {}).get("totalCount", 0)) \
            if node else None
    except Exception as e:  # noqa: BLE001
        degrade("graphql/contributedTo", e)
        return None


MONTHS = ("January February March April May June July August September "
          "October November December").split()


def fetch_calendar() -> dict:
    """
    Exact per-day contributions.

    GitHub renders the calendar server-side for anonymous requests and pairs
    every cell with a <tool-tip> holding the exact number, e.g.
    "7 contributions on November 20th."
    """
    html = http(f"https://github.com/users/{USER}/contributions",
                accept="text/html", tries=3)

    counts: dict[str, int] = {}
    for m in re.finditer(r'<tool-tip[^>]*for="(contribution-day-component-[\d-]+)"'
                         r'[^>]*>([^<]*)</tool-tip>', html):
        text = m.group(2)
        if "contribution" not in text:
            continue
        n = re.match(r"\s*(No|\d[\d,]*)", text)
        val = 0 if (n and n.group(1) == "No") else int(n.group(1).replace(",", "")) if n else 0
        counts[m.group(1)] = val

    levels: dict[str, int] = {}
    order: list[str] = []
    for m in re.finditer(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*?'
                         r'id="(contribution-day-component-[\d-]+)"[^>]*?'
                         r'data-level="(\d)"', html):
        counts.setdefault(m.group(2), 0)
        levels[m.group(2)] = int(m.group(3))
        order.append(m.group(2))

    days = []
    seen = set()
    for m in re.finditer(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*?'
                         r'id="(contribution-day-component-[\d-]+)"[^>]*?'
                         r'data-level="(\d)"', html):
        d, cid, lvl = m.group(1), m.group(2), int(m.group(3))
        if d in seen:
            continue
        seen.add(d)
        days.append({"d": d, "n": counts.get(cid, 0), "lvl": lvl})
    days.sort(key=lambda x: x["d"])

    total = 0
    m = re.search(r'([\d,]+)\s*</h2>', html)
    if m:
        total = int(m.group(1).replace(",", ""))
    if not days:
        raise RuntimeError("calendar parsed 0 days (layout changed?)")
    return {"days": days, "total": total or sum(x["n"] for x in days)}


def fetch_html_fallback() -> dict:
    """
    No token, no API quota? The public profile page is still there.

    One request (plus the calendar) yields the bio, the follower and repo
    counters and the pinned repositories with their language and star count.
    It is less precise than the REST API, but it keeps the profile honest
    instead of showing yesterday's numbers.
    """
    html = http(f"https://github.com/{USER}", accept="text/html", tries=2)
    out: dict = {"repos": [], "user": {}}

    bio = re.search(r'<div class="p-note user-profile-bio[^"]*"[^>]*>(.*?)</div>',
                    html, re.S)
    if bio:
        out["user"]["bio"] = re.sub(r"<[^>]+>", "", bio.group(1)).strip()

    nick = re.search(r'<span class="p-nickname[^"]*"[^>]*>\s*([^<\n]+)', html)
    if nick:
        out["user"]["login"] = nick.group(1).strip()
    name = re.search(r'<span class="p-name[^"]*"[^>]*>\s*([^<\n]+)', html)
    if name:
        out["user"]["name"] = name.group(1).strip()
    loc = re.search(r'itemprop="homeLocation"[^>]*>\s*([^<\n]+)', html)
    if loc:
        out["user"]["location"] = loc.group(1).strip()

    # counters live in the tab bar: Repositories 40 / Projects 0 / Stars 0
    tab = re.search(r'Repositories\s*<span title="([\d,]+)"', html)
    if tab:
        out["user"]["public_repos"] = int(tab.group(1).replace(",", ""))
    fol = re.search(r'class="text-bold color-fg-default"[^>]*>([\d,]+)</span>\s*followers',
                    html)
    if fol:
        out["user"]["followers"] = int(fol.group(1).replace(",", ""))
    fol2 = re.search(r'>([\d,]+)</span>\s*following', html)
    if fol2:
        out["user"]["following"] = int(fol2.group(1).replace(",", ""))

    chunk = ""
    i = html.find("js-pinned-items-reorder-list")
    if i > 0:
        chunk = html[i:html.find("</ol>", i)]
    names = re.findall(r'<span class="repo">([^<]+)</span>', chunk)
    descs = [re.sub(r"<[^>]+>", "", d).strip() for d in
             re.findall(r'pinned-item-desc[^>]*>(.*?)</p>', chunk, re.S)]
    langs = re.findall(r'itemprop="programmingLanguage">([^<]+)<', chunk)

    blocks = chunk.split("</li>")
    for idx, name in enumerate(names):
        body = next((b for b in blocks if f'<span class="repo">{name}</span>' in b), "")
        pairs = re.findall(r'/(stargazers|forks)"[^>]*>\s*<svg.*?</svg>\s*([\d,]+)',
                           body, re.S)
        counts = {kind: int(n.replace(",", "")) for kind, n in pairs}
        out["repos"].append({
            "name": name,
            "description": descs[idx] if idx < len(descs) else "",
            "language": langs[idx] if idx < len(langs) else None,
            "stargazers_count": counts.get("stargazers", 0),
            "forks_count": counts.get("forks", 0),
            "pushed_at": None, "html_url": f"https://github.com/{USER}/{name}",
            "fork": False, "archived": False, "topics": [],
        })
    return out


def fallback_calendar(days: int = 365) -> dict:
    """Synthetic calendar so the SVG keeps its shape when scraping fails."""
    today = date.today()
    out = []
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        out.append({"d": d.isoformat(), "n": 0, "lvl": 0})
    return {"days": out, "total": 0, "synthetic": True}


# ─────────────────────────────────────────────────────────────────────────────
#  Aggregation
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_languages(repos: list[dict]) -> list[dict]:
    sizes, per_repo = {}, {}
    for r in repos:
        if r.get("fork") or r.get("archived"):
            continue
        for lang, n in (r.get("languages") or {}).items():
            sizes[lang] = sizes.get(lang, 0) + n
            per_repo[lang] = per_repo.get(lang, 0) + 1
    total = sum(sizes.values()) or 1
    rows = [{"name": k, "bytes": v, "pct": 100 * v / total, "repos": per_repo[k]}
            for k, v in sizes.items()]
    rows.sort(key=lambda x: x["bytes"], reverse=True)
    return rows[:8]


def count_languages(repos: list[dict]) -> None:
    """Fill repos[].languages one call per repo, but stop on rate limits."""
    for r in repos:
        if r.get("fork"):
            continue
        if "languages" in r:
            continue
        try:
            r["languages"] = jget(r["languages_url"])
        except Exception as e:  # noqa: BLE001
            degrade(f"languages/{r['name']}", e)
            r["languages"] = {}
            if "rate" in str(e).lower() or "403" in str(e):
                break


def streaks(days: list[dict]) -> dict:
    active = [d for d in days if d["n"] > 0]
    best_cur = best_all = 0
    cur = prev = None
    for d in active:
        dt = date.fromisoformat(d["d"])
        if prev and (dt - prev).days == 1:
            cur += 1
        else:
            cur = 1
        prev = dt
        best_all = max(best_all, cur)
    # current streak: walk back from the last day that has contributions
    if active:
        last = date.fromisoformat(active[-1]["d"])
        today = date.today()
        cur, walk = 0, last if (today - last).days <= 1 else None
        active_set = {d["d"] for d in active}
        while walk and walk.isoformat() in active_set:
            cur += 1
            walk -= timedelta(days=1)
        best_cur = cur
    return {"current": best_cur, "longest": best_all}


def hour_from_days(days: list[dict]) -> list[int]:
    """
    Hour-of-day rhythm without the events API.

    Every day's commits are spread around 13:00 UTC with a fixed, seeded shape:
    the total per day is exact, only the distribution inside the day is a model.
    """
    import hashlib
    hours = [0] * 24
    for d in days:
        n = d.get("n", 0)
        if not n:
            continue
        seed = int(hashlib.sha256(d["d"].encode()).hexdigest()[:8], 16)
        for i in range(n):
            mix = (seed >> (i % 24)) ^ (i * 2654435761)
            hours[8 + mix % 14] += 1          # 08:00–21:00, the hours people push
    return hours


def weekday_profile(days: list[dict]) -> list[dict]:
    names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    sums = [0] * 7
    cnt = [0] * 7
    for d in days:
        wd = (date.fromisoformat(d["d"]).weekday() + 1) % 7
        sums[wd] += d["n"]
        cnt[wd] += 1
    return [{"day": names[i], "n": sums[i], "avg": sums[i] / max(1, cnt[i])}
            for i in range(7)]


def hour_profile(events: list[dict]) -> list[int]:
    hours = [0] * 24
    for e in events:
        try:
            ts = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
            hours[ts.hour] += 1
        except Exception:  # noqa: BLE001
            continue
    return hours


def build_activity(events: list[dict]) -> list[dict]:
    out = []
    for e in events[:60]:
        t = e.get("type", "")
        repo = (e.get("repo") or {}).get("name", "")
        p = e.get("payload") or {}
        row = {"type": t, "repo": repo, "at": e.get("created_at", "")}
        if t == "PushEvent":
            commits = p.get("commits") or []
            row["count"] = int(p.get("size") or len(commits) or 1)
            msgs = [c.get("message", "").split("\n")[0] for c in commits]
            row["messages"] = [m for m in msgs if m][:3]
            row["ref"] = (p.get("ref") or "").replace("refs/heads/", "")
        elif t in ("PullRequestEvent", "IssuesEvent"):
            row["count"] = 1
            row["messages"] = [(p.get("pull_request") or p.get("issue") or {})
                               .get("title", "")][:1]
            row["action"] = p.get("action", "")
        elif t == "CreateEvent":
            row["count"] = 1
            row["messages"] = [p.get("ref") or p.get("ref_type") or ""]
        else:
            row["count"] = 1
            row["messages"] = []
        if row.get("count"):
            out.append(row)
    return out


def top_repos(repos: list[dict], pinned_names: list[str]) -> list[dict]:
    pool = [r for r in repos if not r.get("fork") and not r.get("archived")]
    by_name = {r["name"].lower(): r for r in pool}
    picked, done = [], set()
    for n in pinned_names:                      # README-defined order first
        r = by_name.get(n.lower())
        if r and r["name"] not in done:
            picked.append(r)
            done.add(r["name"])
    for r in sorted(pool, key=lambda x: (x["stargazers_count"], x["pushed_at"]),
                    reverse=True):
        if r["name"] not in done:
            picked.append(r)
            done.add(r["name"])
        if len(picked) >= 6:
            break
    rows = []
    for r in picked[:6]:
        rows.append({
            "name": r["name"], "desc": r.get("description") or "No description yet.",
            "stars": r["stargazers_count"], "forks": r["forks_count"],
            "lang": r.get("language") or "—", "pushed": r.get("pushed_at"),
            "url": r["html_url"], "size": r.get("size", 0),
            "topics": (r.get("topics") or [])[:3],
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
#  Rank — github-readme-stats style grade, recomputed locally
# ─────────────────────────────────────────────────────────────────────────────

def rank_for(totals: dict) -> dict:
    c, pr, isu, st, fol, rep = (totals.get(k, 0) or 0 for k in
                                ("commits", "prs", "issues", "stars", "followers", "repos"))
    score = (c * 1.0 + pr * 3.0 + isu * 2.0 + st * 6.0 + fol * 8.0 + rep * 4.0)
    grade = "C"
    for g, need in (("S", 12000), ("A+", 7000), ("A", 4800), ("A-", 3400),
                    ("B+", 2400), ("B", 1600), ("B-", 1100), ("C+", 700), ("C", 350)):
        if score >= need:
            grade = g
            break
    pct = max(1, min(99, round(100 * pow(min(score / 12000, 1), 0.62))))
    return {"grade": grade, "score": round(score), "percentile": 100 - pct}


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def _archive(data: dict) -> None:
    """Keep a small time machine: one snapshot per day, pruned to HISTORY_KEEP."""
    try:
        from datetime import date
        today = date.today().isoformat()
        os.makedirs(HISTORY_DIR, exist_ok=True)
        slim = {k: data[k] for k in ("generated_at", "totals", "languages",
                                     "contributions", "projects", "activity")}
        slim["contributions"] = {k: v for k, v in slim["contributions"].items()
                                 if k in ("total", "streak", "best_day")}
        with open(os.path.join(HISTORY_DIR, f"{today}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(slim, f, ensure_ascii=False, separators=(",", ":"))
        files = sorted(os.listdir(HISTORY_DIR))
        for old in files[:-HISTORY_KEEP]:
            os.remove(os.path.join(HISTORY_DIR, old))
        print(f"  ✓ history snapshot → {HISTORY_DIR}/{today}.json "
              f"({len(files[-HISTORY_KEEP:])} kept)")
    except Exception as e:  # noqa: BLE001
        degrade("history", e)


def previous_snapshot() -> dict:
    """The last good build. Degraded sources are patched with it."""
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def main() -> None:
    t0 = time.time()
    now = datetime.now(timezone.utc)
    print(f"👁️  collecting telemetry for @{USER}  ({now:%Y-%m-%d %H:%M UTC})")
    prev = previous_snapshot()
    stale: list[str] = []

    try:
        user = fetch_user()
    except Exception as e:  # noqa: BLE001
        degrade("user", e)
        user = prev.get("user") or {}
        if user:
            stale.append("user")

    repos: list[dict] = []
    try:
        repos = fetch_repos()
    except Exception as e:  # noqa: BLE001
        degrade("repos", e)
        if prev.get("projects"):
            stale.append("repos")

    if not user or not repos:
        print("  ↩ API unavailable — falling back to the public profile page")
        try:
            alt = fetch_html_fallback()
            user = user or alt.get("user", {})
            if not repos and alt.get("repos"):
                repos = alt["repos"]
                stale.append("repos(html)")
                print(f"  ✓ html fallback: {len(repos)} pinned repos, "
                      f"{sum(r['stargazers_count'] for r in repos)} stars")
        except Exception as e:  # noqa: BLE001
            degrade("html-fallback", e)

    events = fetch_events()
    counts = fetch_counts()
    contributed = fetch_contributed_to()

    if not counts and prev.get("totals"):
        stale.append("counts")
        counts = {k: prev["totals"].get(k, 0) for k in ("commits", "prs", "issues")}

    try:
        cal = fetch_calendar()
        print(f"  ✓ calendar: {len(cal['days'])} days, {cal['total']} contributions")
    except Exception as e:  # noqa: BLE001
        degrade("calendar", e)
        old = prev.get("contributions") or {}
        if old.get("days"):
            cal = {"days": old["days"], "total": old.get("total", 0), "stale": True}
            stale.append("calendar")
            print("  ↩ reusing the previous calendar (last known good)")
        else:
            cal = fallback_calendar()

    # languages need one extra request per repo: only for the top ones
    repos_sorted = sorted(repos, key=lambda r: r.get("size", 0), reverse=True)
    count_languages(repos_sorted[:40])
    for r in repos_sorted:                     # HTML fallback already knows one
        if not r.get("languages") and r.get("language"):
            r["languages"] = {r["language"]: 1}

    stars = sum(r.get("stargazers_count", 0) for r in repos if not r.get("fork"))
    forks = sum(r.get("forks_count", 0) for r in repos if not r.get("fork"))
    langs = aggregate_languages(repos_sorted)

    # a rate-limited repo fetch must not erase the cards: keep the last good set
    if not repos and prev.get("projects"):
        stars = prev.get("totals", {}).get("stars", stars)
        forks = prev.get("totals", {}).get("forks", forks)
        langs = prev.get("languages") or langs
        print("  ↩ reusing the previous repos / stars / languages (last known good)")

    for row in langs:
        if not row.get("color"):
            from svg.cards.tui import LANG_COLOR  # noqa: WPS433
            row["color"] = LANG_COLOR.get(row["name"], "#8b949e")

    days = cal["days"]
    recent = days[-365:]
    best = max(recent, key=lambda d: d["n"], default={"d": "", "n": 0})
    active_days = sum(1 for d in recent if d["n"] > 0)

    totals = {
        "commits": counts.get("commits", 0),
        "prs": counts.get("prs", 0),
        "issues": counts.get("issues", 0),
        "stars": stars,
        "forks": forks,
        "followers": user.get("followers", 0),
        "following": user.get("following", 0),
        "repos": user.get("public_repos") or len([r for r in repos
                                                 if not r.get("fork")]),
        "contributions": cal["total"] or sum(d["n"] for d in recent),
        "contributed_to": contributed if contributed is not None else 0,
        "active_days": active_days,
    }
    totals["rank"] = rank_for(totals)

    pinned_names = [n for n in os.environ.get(
        "PINS", "python-os,monarch-os,aircraft,minicraft-sdl,guanaco-py,green-debian"
    ).split(",") if n]

    data = {
        "generated_at": now.isoformat(),
        "user": user,
        "totals": totals,
        "contributions": {
            "days": days,
            "total": totals["contributions"],
            "best_day": {"d": best["d"], "n": best["n"]},
            "streak": streaks(days),
            "weekday": weekday_profile(days),
            "hours": hour_profile(events) if events else hour_from_days(days),
            "first": days[0]["d"] if days else "",
            "last": days[-1]["d"] if days else "",
        },
        "languages": langs,
        "projects": top_repos(repos, pinned_names) or prev.get("projects", []),
        "activity": build_activity(events) or prev.get("activity", []),
        "meta": {
            "degraded": _report["degraded"],
            "stale": sorted(set(stale)),
            "rate_limit_remaining": _report["sources"].get("rate_limit_remaining"),
            "authenticated": bool(TOKEN),
            "synthetic": cal.get("synthetic", False),
            "elapsed": round(time.time() - t0, 2),
        },
    }

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"  ✓ data.json written ({os.path.getsize(OUT)/1024:.1f} kB) in "
          f"{data['meta']['elapsed']}s")
    _archive(data)
    if _report["degraded"]:
        print(f"  ⚠️  degraded sources: {len(_report['degraded'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
