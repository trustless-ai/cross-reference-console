#!/usr/bin/env python3
"""crc.cell.v1 sunset enforcement (CELL-v2.md §4).

A Cell **added** after the activation commit MUST be `crc.cell.v2`. Cells that
already existed at activation are frozen history and are never re-judged.

The activation point is not recorded anywhere by hand — it is derived:

    git log --diff-filter=A --format=%H -- CELL-v2.md

Usage (CI):  python3 reference/check_sunset.py <base-ref> <head-ref>
             python3 reference/check_sunset.py            # defaults to origin/main...HEAD

Exit 0 = conformant, 1 = a new v1-shaped Cell was submitted after activation.
Stdlib only.
"""
import json
import os
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


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    head = sys.argv[2] if len(sys.argv) > 2 else "HEAD"

    act = activation_commit()
    if not act:
        print("[SKIP] CELL-v2.md not present on this branch — sunset not in force yet")
        return 0  # not a pass of the rule; the rule simply does not apply yet
    print(f"activation commit (derived): {act[:12]}  [git log --diff-filter=A -- CELL-v2.md]")

    new = added_cells(base, head)
    if not new:
        print("no newly added Cells in this diff — nothing to judge")
        return 0

    bad = []
    for path in new:
        schema = schema_of(path)
        ok = schema == "crc.cell.v2"
        print(f"  {'ok  ' if ok else 'FAIL'} {path} -> {schema}")
        if not ok:
            bad.append((path, schema))

    if bad:
        print(
            f"\n{len(bad)} newly submitted Cell(s) are not crc.cell.v2.\n"
            f"CELL-v2.md §4: Cells added after the activation commit MUST be v2.\n"
            f"Existing Cells are untouched — this rule judges NEW submissions only."
        )
        return 1
    print("\nall newly added Cells are crc.cell.v2 — sunset respected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
