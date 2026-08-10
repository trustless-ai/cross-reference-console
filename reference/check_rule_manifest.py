#!/usr/bin/env python3
"""Enforce the mechanical half of one-decision-site-per-rule.

Damon Zwicker's amendment to the proposal, 2026-08-10:

    "name the module that decides rule X" is a human audit unless recorded. So
    record it — a manifest per repo mapping rule -> deciding module -> sanctioned
    duplicates -> their comparator. CI then enforces the mechanical half: every
    listed duplicate has a comparator that runs, and the comparator fails on
    deliberate mutation.

What this enforces, per `rules.json`:

  1. the spec, deciding module and vector file all exist
  2. **the vectors cite the spec** — because the `[] / []` inversion survived
     review by having its own vectors encode the same guess the checker did. A
     cross-check cannot catch two implementations that inherit one wrong
     assumption through shared vectors, so a vector file that never names the
     document it is testing against is testing the implementation, not the rule
  3. every registered duplicate names a comparator, and that comparator EXISTS
  4. **the comparator actually fails when the duplicate is mutated** — applied
     for real, in a scratch copy, not asserted. A comparator that has never
     disagreed with anything is unverified in exactly the way the broken checker
     was: it passes because nothing has ever made it speak.

What it deliberately does NOT enforce: unregistered duplicates. Nothing here can
find a copy nobody declared. Those stay a review finding — the manifest does not
make the question enforceable, it makes it answerable.
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "rules.json"

fails = []


def chk(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


def mutation_makes_comparator_fail(dup: dict, comparator: pathlib.Path) -> tuple:
    """Copy the tree, apply the declared mutation, run the comparator, expect failure."""
    mut = dup.get("mutation") or {}
    for k in ("file", "find", "replace"):
        if not mut.get(k):
            return False, f"mutation.{k} missing — the comparator is unproven"

    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td) / "repo"
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        target = work / mut["file"]
        if not target.exists():
            return False, f"{mut['file']} not found in the copied tree"
        text = target.read_text()
        if mut["find"] not in text:
            # A mutation that no longer applies is not a passing test. The code it
            # was written against has moved and nobody re-proved the comparator.
            return False, (f"mutation no longer applies to {mut['file']} — the code moved "
                           f"and the comparator has not been re-proven against it")
        target.write_text(text.replace(mut["find"], mut["replace"], 1))

        rel = comparator.relative_to(ROOT)
        r = subprocess.run([sys.executable, str(work / rel)],
                           capture_output=True, text=True, timeout=600, cwd=work)
        if r.returncode == 0:
            return False, ("comparator PASSED on the mutated duplicate — it does not "
                           "actually compare the thing it claims to")
        return True, ""


def main() -> int:
    if not MANIFEST.exists():
        print(f"FAIL  no rules.json — the deciding module for each rule is unrecorded",
              file=sys.stderr)
        return 1
    m = json.loads(MANIFEST.read_text())
    chk("schema is crc.rules.v0", m.get("schema") == "crc.rules.v0", str(m.get("schema")))
    rules = m.get("rules") or []
    chk("manifest lists at least one rule", bool(rules))
    if fails:
        return 1

    for r in rules:
        name = r.get("rule", "?")
        print(f"\n── {name}")
        spec = ROOT / r.get("spec", "")
        decides = ROOT / r.get("decides", "")
        vectors = ROOT / r.get("vectors", "")
        chk(f"spec exists ({r.get('spec')})", spec.is_file())
        chk(f"deciding module exists ({r.get('decides')})", decides.is_file())
        chk(f"vectors exist ({r.get('vectors')})", vectors.is_file())

        # Clause 3: vectors derive from the spec, not the implementation.
        if vectors.is_file():
            body = vectors.read_text()
            cites = r.get("spec", "") in body
            chk("vectors cite the spec, not just the implementation", cites,
                f"{r.get('vectors')} never names {r.get('spec')} — vectors written "
                f"against the implementation cannot catch the implementation being wrong")

        dups = r.get("duplicates") or []
        if not dups:
            print("     ..    no sanctioned duplicates — one decision site")
            continue

        for d in dups:
            comp = ROOT / d.get("comparator", "")
            chk(f"duplicate {d.get('impl')} names an existing comparator "
                f"({d.get('comparator')})", comp.is_file())
            if not comp.is_file():
                continue
            ok, why = mutation_makes_comparator_fail(d, comp)
            chk(f"comparator FAILS when {d.get('impl')} is mutated "
                f"({(d.get('mutation') or {}).get('why', 'declared mutation')})", ok, why)

    print()
    if fails:
        print(f"{len(fails)} manifest failure(s)")
        return 1
    print("all green — every registered duplicate has a comparator that demonstrably bites")
    print("(unregistered duplicates are NOT covered here — that stays a review finding)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
