#!/usr/bin/env python3
"""
update_readme.py — the single entry point used by .github/workflows/readme.yml.

    collect telemetry → render SVGs → rewrite README → sanity check → preview

Any step failing aborts before the commit, so a broken build never reaches the
profile and never erases a good one.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
DATA = os.path.join(ROOT, "assets/readme/data/telemetry.json")


def step(label, *cmd, env=None):
    print(f"\n▶ {label}", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})})
    if r.returncode:
        sys.exit(f"✗ {label} failed ({r.returncode})")


def main():
    py = sys.executable
    step("collect telemetry", py, f"{SCRIPTS}/collect.py",
         env={"DATA_OUT": "assets/readme/data/telemetry.json"})
    step("render animated svgs", py, f"{SCRIPTS}/render.py", "--data", DATA)
    step("rewrite README", py, f"{SCRIPTS}/readme.py", "--data", DATA)
    step("sanity check", py, f"{SCRIPTS}/check.py")
    step("preview", py, f"{SCRIPTS}/preview.py")
    print("\n✓ README is alive")


if __name__ == "__main__":
    main()
