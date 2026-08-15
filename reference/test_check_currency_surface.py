#!/usr/bin/env python3
"""Prove check_currency_surface.py can fail, once per claim it makes.

House rule, and the one that has caught the most this month: before reporting a check as
passing, prove it can fail. A surface check is exactly the kind that passes forever — it
renders, it compares, it is green, and nobody has ever seen it disagree with anything.

Each mutation below reintroduces a defect that would ship a real falsehood, applied to the
INLINED region of a COPY of ui/index.html — never the working tree. Every one must exit 1, and
must do so on the assertion that names the defect rather than on a golden diff, because "some
byte moved" is not the same finding as "the page renders a verdict it never established".

EXIT: 0 all mutations caught · 1 one survived · 2 could not run.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECK = ROOT / "reference" / "check_currency_surface.py"
INDEX = ROOT / "ui" / "index.html"
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2

# (name, what it breaks, from, to, an assertion label that MUST appear in the failure list)
MUTATIONS = [
    ("surface writes its own sentence",
     "the marker's text stops reaching the DOM — a second mapping, silently",
     "    var text = wellFormed ? marker.text : DEFECT_TEXT;",
     "    var text = 'everything looks fine';",
     "rendered text, tone, state and reason are the marker's own"),

    ("surface picks its own colour from the state",
     "a second mapping in the one file that must not have one",
     "    var tone = wellFormed ? marker.tone : 'amber';",
     "    var tone = (marker && marker.state === 'CHECKED') ? 'green' : 'amber';",
     'CODE does not contain "CHECKED"'),

    ("the qualified guard is dropped",
     "an unqualified marker renders as a bare green claim",
     "      && typeof marker.tone === 'string' && marker.tone !== ''\n"
     "      && marker.qualified === true;",
     "      && typeof marker.tone === 'string' && marker.tone !== '';",
     "unqualified: refuses it"),

    ("the initial NOT_RUN render is skipped",
     "the page shows nothing until the network answers — absence reads as a pass",
     "    renderCurrency(currencyMarker('NOT_RUN'), el);",
     "    void currencyMarker;",
     "opens on NOT_RUN"),

    ("PENDING never reaches the DOM",
     "'not asked' and 'asked, waiting' collapse into one another",
     "      onState: function (m) { renderCurrency(m, el); }",
     "      onState: function (m) { if (m.state !== 'PENDING') { renderCurrency(m, el); } }",
     "renders PENDING before the wait"),

    ("a reason loses its wording upstream",
     "three distinct next actions collapse into one indistinguishable amber",
     "    lock_unreadable:\n      'could not tell which commit is selected",
     "    lock_unreadable:\n      'could not read what is published",
     "record_missing"),
]


def run(index: pathlib.Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(CHECK), "--index", str(index)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    if not CHECK.exists() or not INDEX.exists():
        print("UNVERIFIABLE — check or page missing", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    if shutil.which("node") is None:
        print("UNVERIFIABLE — node is required to drive the page", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    original = INDEX.read_text(encoding="utf-8")
    bad = 0

    print("does check_currency_surface.py go red when the page starts lying?\n")

    # Baseline. A suite that is red before the mutation proves nothing about the mutation.
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "index.html"
        p.write_text(original, encoding="utf-8")
        rc, _ = run(p)
    print(f"  {'ok  ' if rc == 0 else 'FAIL'}  baseline: the unmutated page passes (exit {rc})")
    bad += rc != 0

    for name, why, frm, to, expect in MUTATIONS:
        if frm not in original:
            print(f"  FAIL  {name}: anchor not found — the mutation patched NOTHING, so a "
                  f"green here would mean nothing")
            bad += 1
            continue
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "index.html"
            mutated = original.replace(frm, to, 1)
            if mutated == original:
                print(f"  FAIL  {name}: replacement was a no-op")
                bad += 1
                continue
            p.write_text(mutated, encoding="utf-8")
            rc, out = run(p)
        if rc != 1:
            print(f"  FAIL  {name}: expected exit 1, got {rc} — {why}")
            bad += 1
            continue
        # Red is not enough. It has to be red on the assertion that names the defect.
        failures = out.split("assertion(s) failed:")[-1]
        if expect not in failures:
            print(f"  FAIL  {name}: red, but not on \"{expect}\" — a golden diff is not a finding")
            bad += 1
            continue
        print(f"  ok    {name} → caught ({why})")

    # Could-not-check must be 2, never 0. A check that reports success when it could not run
    # at all is the failure mode this repo exists to refuse.
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "index.html"
        stripped = re.sub(r"(/\* BEGIN currency-surface\.js[\s\S]*?\*/\n)[\s\S]*?"
                          r"(/\* END currency-surface\.js \*/)", r"\1\2", original, count=1)
        p.write_text(stripped, encoding="utf-8")
        rc, _ = run(p)
    print(f"  {'ok  ' if rc == 2 else 'FAIL'}  a page with no surface region is UNVERIFIABLE, "
          f"not a pass (exit {rc})")
    bad += rc != 2

    print()
    if bad:
        print(f"{bad} case(s) failed — the check does not catch what it claims to")
        return EXIT_BAD
    print("every mutation was caught, on the assertion that names it")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
