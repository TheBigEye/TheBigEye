#!/usr/bin/env python3
"""
check.py — the guard rail that keeps the illusion alive.

Verifies, with zero dependencies:
  · every generated SVG is well-formed XML
  · every SVG keeps its own CSS (animation survives GitHub's sanitizer)
  · the README references only files that exist
  · the README keeps its hand-written content
  · nothing points at a service that can disappear

Exit code 1 fails the workflow, so a broken build never reaches the profile.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, "assets/readme/live")
README = os.path.join(ROOT, "README.md")

errors: list[str] = []
warns: list[str] = []


def check_svgs() -> None:
    files = sorted(glob.glob(os.path.join(LIVE, "**/*.svg"), recursive=True))
    if not files:
        errors.append("no SVGs generated in assets/readme/live")
        return
    for path in files:
        rel = os.path.relpath(path, ROOT)
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as e:
            errors.append(f"{rel}: malformed XML ({e})")
            continue
        text = open(path, encoding="utf-8").read()
        if ".src.svg" in rel:
            continue
        if 'class="' in text and "<style>" not in text:
            errors.append(f"{rel}: uses classes but carries no <style> block")
        if "<animate" in text:
            warns.append(f"{rel}: uses SMIL, prefer CSS keyframes")
        if not re.search(r"@keyframes", text) and root.get("width") not in ("0", "132",
                                                                          "860", "14"):
            warns.append(f"{rel}: no @keyframes (static)")
        if 'href="http' in text or "href='http" in text:
            errors.append(f"{rel}: references an external resource "
                          f"(SVG images cannot fetch those)")
    print(f"  ✓ {len(files)} SVGs parsed")


def check_readme() -> None:
    if not os.path.exists(README):
        errors.append("README.md missing")
        return
    text = open(README, encoding="utf-8").read()

    for ref in sorted(set(re.findall(r'(?:src|srcset)="([^"$]+)"', text))):
        if ref.startswith(("http://", "https://", "data:")):
            continue
        ref = ref.split("?", 1)[0]          # ignore the cache-busting query
        if not os.path.exists(os.path.join(ROOT, ref)):
            errors.append(f"README references a missing file: {ref}")

    if "assets/readme/live/" not in text:
        errors.append("README does not include any generated card")

    for must in ("I’m currently working on", "Green", "Monarch OS"):
        if must not in text:
            errors.append(f"hand-written content lost: {must!r}")

    dead = re.findall(r"assets/readme/(stats|header|image/pc-)[\w/.-]*", text)
    if dead:
        errors.append(f"README still points at old static assets: {sorted(set(dead))}")

    if "profile-dark.svg" not in text:
        errors.append("README lost its generated card")

    print(f"  ✓ README.md checked ({len(text)/1024:.1f} kB)")


def check_data() -> None:
    path = next((p for p in (os.path.join(ROOT, "assets/readme/data/telemetry.json"),
                             os.path.join(ROOT, "data.json"))
                 if os.path.exists(p)), None)
    if not path:
        errors.append("no telemetry file — run scripts/collect.py first")
        return
    d = json.load(open(path, encoding="utf-8"))
    if d.get("meta", {}).get("synthetic"):
        errors.append("data.json is synthetic — the calendar scrape failed")
    if not d.get("contributions", {}).get("days"):
        errors.append("data.json has no contribution days")
    deg = d.get("meta", {}).get("degraded") or []
    if deg:
        warns.append(f"{len(deg)} degraded source(s): {deg[:2]}")
    stale = d.get("meta", {}).get("stale") or []
    if stale:
        warns.append(f"reused last known good data for: {stale}")
    if not d.get("user", {}).get("login"):
        errors.append("data.json has no user — every card would be empty")
    if not d.get("projects"):
        errors.append("data.json has no projects")
    print(f"  ✓ data.json checked ({len(d['contributions']['days'])} days)")


def main() -> None:
    print("🔍 sanity check")
    check_data()
    check_svgs()
    check_readme()

    for w in warns:
        print(f"  ⚠️  {w}")
    if errors:
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        sys.exit(f"✗ {len(errors)} problem(s)")
    print("  ✓ all good — the README is alive")


if __name__ == "__main__":
    main()
