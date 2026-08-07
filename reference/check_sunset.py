#!/usr/bin/env python3
"""Cell schema sunset enforcement (CELL-v2.md §4, CELL-v3.md §5).

A Cell **added** after the activation commit MUST carry the in-force schema.
Cells that already existed at activation are frozen history, never re-judged.

Neither the in-force schema NOR its activation point is recorded by hand.
Both are DERIVED (see registry_id.in_force_schema):

    v2 in force until BOTH CELL-v3.md (minted) AND v3 enforcement (marker) land
    v3 in force only when minted AND enforced — neither alone activates admission

Usage (CI):  python3 reference/check_sunset.py <base-ref> <head-ref>
             python3 reference/check_sunset.py            # defaults to origin/main...HEAD

Exit 0 = conformant, 1 = a newly submitted Cell uses a superseded schema.
Stdlib only.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from registry_id import in_force_schema, schema_activation_commit, V3_ENFORCEMENT_MARKER  # noqa: E402


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

    want = in_force_schema()
    act = schema_activation_commit(want)
    if not act:
        print("[SKIP] no activation point derived — sunset not in force yet")
        return 0

    if want == "crc.cell.v3":
        act_note = f"git log --diff-filter=A -- {V3_ENFORCEMENT_MARKER}"
        spec_ref = "CELL-v3.md §5.1"
    else:
        act_note = "git log --diff-filter=A -- CELL-v2.md"
        spec_ref = "CELL-v2.md §4"

    print(f"in-force schema (derived): {want}")
    print(f"activation commit (derived): {act[:12]}  [{act_note}]")

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
            f"{spec_ref}: Cells added after the activation commit MUST be {want}.\n"
            f"Existing Cells are untouched — this rule judges NEW submissions only."
        )
        return 1
    print(f"\nall newly added Cells are {want} — sunset respected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
