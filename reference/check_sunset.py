#!/usr/bin/env python3
"""Cell schema sunset enforcement (CELL-v2.md §4, CELL-v3.md §5).

A Cell **added** after the activation commit MUST carry the in-force schema.
Cells that already existed at activation are frozen history, never re-judged.

Neither the in-force version NOR its activation point is recorded by hand.
Both are DERIVED:

    in-force version = the highest CELL-vN.md present on this branch
    activation       = git log --diff-filter=A --format=%H -- CELL-v<N>.md

The version was hardcoded to v2 until 2026-08-07. That made adding CELL-v3.md a
silent deadlock: the spec self-activates on merge and requires v3, while this
file still demanded v2 — so no new Cell of ANY version could be submitted.
Deriving it means minting v4 needs no change here, and a spec can never
activate a rule its enforcement doesn't know about.

Usage (CI):  python3 reference/check_sunset.py <base-ref> <head-ref>
             python3 reference/check_sunset.py            # defaults to origin/main...HEAD

Exit 0 = conformant, 1 = a new v1-shaped Cell was submitted after activation.
Stdlib only.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from registry_id import activation_commit  # noqa: E402


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def added_cells(base: str, head: str):
    out = git("diff", "--diff-filter=A", "--name-only", f"{base}...{head}", "--", "cells/")
    return [p for p in out.split() if p.endswith(".cell.json") and "/rejected/" not in p]


def schema_of(path: str) -> str:
    full = os.path.join(ROOT, path)
    d = json.load(open(full, encoding="utf-8"))
    pp = d.get("proof_payload")
    if pp is None and "event" in d:  # nostr lane: the payload is the signed content
        pp = json.loads(d["event"]["content"])
    return (pp or {}).get("schema", "<none>")


def in_force_version() -> int:
    """Highest N for which CELL-vN.md exists on this branch. Discovered, not listed."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ns = [int(m.group(1)) for f in os.listdir(root)
          if (m := re.fullmatch(r"CELL-v(\d+)\.md", f))]
    return max(ns) if ns else 0


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    head = sys.argv[2] if len(sys.argv) > 2 else "HEAD"

    n = in_force_version()
    if n == 0:
        print("[SKIP] no CELL-vN.md on this branch — sunset not in force yet")
        return 0  # not a pass of the rule; the rule simply does not apply yet
    spec = f"CELL-v{n}.md"
    want = f"crc.cell.v{n}"

    act = activation_commit(spec)
    if not act:
        print(f"[SKIP] {spec} not present on this branch — sunset not in force yet")
        return 0
    print(f"in-force schema (derived): {want}   [highest CELL-vN.md on this branch]")
    print(f"activation commit (derived): {act[:12]}  [git log --diff-filter=A -- {spec}]")

    new = added_cells(base, head)
    if not new:
        print("no newly added Cells in this diff — nothing to judge")
        return 0

    bad = []
    for path in new:
        schema = schema_of(path)
        ok = schema == want
        print(f"  {'ok  ' if ok else 'FAIL'} {path} -> {schema}")
        if not ok:
            bad.append((path, schema))

    if bad:
        print(
            f"\n{len(bad)} newly submitted Cell(s) are not {want}.\n"
            f"{spec}: Cells added after the activation commit MUST be {want}.\n"
            f"Existing Cells are untouched — this rule judges NEW submissions only."
        )
        return 1
    print(f"\nall newly added Cells are {want} — sunset respected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
