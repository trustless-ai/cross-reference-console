#!/usr/bin/env python3
"""Controls for the currency mapping check.

The two that matter are @boardyai's, because they are the assertions the check exists for
rather than incidental coverage:

  * a reason manufacturing a verdict
  * a failure disappearing into a generic amber

Both are driven by mutating the SHIPPED mapping and requiring an exact exit 1. Exit codes are
asserted exactly, never "non-zero": this repo separates 1 (determinate) from 2 (could not
check), and a control accepting either would pass while the check collapsed the two — the same
defect one level up from what is under test.

Anchor drift is reported as a FAILURE, never a skip. The sibling suite shipped once with an
anchor that patched zero bytes and therefore tested an unmodified file; a control that can
silently run against unmutated code is worse than no control, because it manufactures
confidence.

Run: python3 reference/test_check_currency_marker.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECK = ROOT / "reference" / "check_currency_marker.py"
MARKER = ROOT / "ui" / "currency-marker.js"
GOLDEN = ROOT / "reference" / "vectors" / "currency-markers.golden.json"

EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if not ok and detail else ""))
    if not ok:
        failures.append(label)


def run_mutated(find: str, replace: str):
    src = MARKER.read_text(encoding="utf-8")
    if find not in src:
        return {"anchored": False, "code": -1, "out": ""}
    td = tempfile.mkdtemp()
    p = pathlib.Path(td) / "currency-marker.js"
    p.write_text(src.replace(find, replace, 1), encoding="utf-8")
    r = subprocess.run([sys.executable, str(CHECK), "--marker", str(p), "--golden", str(GOLDEN)],
                       capture_output=True, text=True, timeout=180)
    shutil.rmtree(td, ignore_errors=True)
    return {"anchored": True, "code": r.returncode, "out": (r.stdout or "") + (r.stderr or "")}


print("controls for check_currency_marker\n")

print("HIS ASSERTION 1 — a reason manufactures a verdict (must be CAUGHT):")
r = run_mutated(
    "        verdict: null,                     /* rule 1: a reason never becomes a verdict */",
    "        verdict: 'CURRENT',                /* mutated: reason manufactures a verdict */")
check("mutation anchor still present", r["anchored"], "anchor drifted — the control did not run")
if r["anchored"]:
    check("exit is exactly 1", r["code"] == EXIT_BAD, f"got {r['code']}")
    check("caught as a layering violation, not just a golden diff",
          "no COULD_NOT_CHECK surface carries a verdict" in r["out"], r["out"][-260:])

print("\nHIS ASSERTION 2 — the three reasons collapse into one generic amber (must be CAUGHT):")
# Valid JS that genuinely collapses the three reasons to one text. An earlier version of this
# control produced a SYNTAX error instead, so the module would not load and the check returned
# 2 (could not check) rather than 1 — correct behaviour from the check, useless as a control.
r = run_mutated(
    "        text: 'could not check — ' + (known\n          ? REASON_TEXT[reason]",
    "        text: 'could not check — ' + (known\n          ? 'something went wrong'")
check("mutation anchor still present", r["anchored"])
if r["anchored"]:
    check("exit is exactly 1", r["code"] == EXIT_BAD, f"got {r['code']}")
    check("caught as a collapse, naming the distinctness assertion",
          "three distinct texts" in r["out"], r["out"][-260:])

print("\nGREEN IS NOT REACHABLE FROM A FAILURE (must be CAUGHT):")
r = run_mutated(
    "state: COULD_NOT_CHECK, verdict: null, reason: known ? reason : 'unspecified', tone: 'amber',",
    "state: COULD_NOT_CHECK, verdict: null, reason: known ? reason : 'unspecified', tone: 'green',")
if not r["anchored"]:
    # the field is written across lines in the source; fall back to the tone token in that branch
    r = run_mutated("        tone: 'amber',\n        text: 'could not check — '",
                    "        tone: 'green',\n        text: 'could not check — '")
check("mutation anchor still present", r["anchored"])
if r["anchored"]:
    check("exit is exactly 1", r["code"] == EXIT_BAD, f"got {r['code']}")
    check("caught by the green-only-from-CURRENT assertion",
          "green" in r["out"].lower(), r["out"][-200:])

print("\nRULE 3 — UNDETERMINED allowed to survive the boundary (must be CAUGHT):")
r = run_mutated(
    "      return currencyMarker(COULD_NOT_CHECK, LEGACY_REASON[reason] || 'unspecified');",
    "      return unqualifiedGuard({ state: 'UNDETERMINED', verdict: null, reason: reason || null, tone: 'amber', text: 'undetermined' });")
check("mutation anchor still present", r["anchored"])
if r["anchored"]:
    check("exit is exactly 1", r["code"] == EXIT_BAD, f"got {r['code']}")
    check("caught as a second canonical state",
          "no surface anywhere reports UNDETERMINED" in r["out"], r["out"][-240:])

print("\nUNVERIFIABLE — mapping missing (must be exactly 2, never 0):")
r = subprocess.run([sys.executable, str(CHECK), "--marker", "/nonexistent/currency-marker.js"],
                   capture_output=True, text=True, timeout=120)
check("exit is exactly 2", r.returncode == EXIT_UNVERIFIABLE, f"got {r.returncode}")
check("could-not-check never reports as a pass", r.returncode != EXIT_OK)

print("\nPOSITIVE CONTROL — the mapping as shipped:")
r = subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True, timeout=180)
check("exit is exactly 0", r.returncode == EXIT_OK, f"got {r.returncode}: {(r.stdout or '')[-240:]}")
check("and says the console still makes no network call",
      "still makes no network call" in (r.stdout or ""))

print()
if failures:
    print(f"{len(failures)} control(s) failed:")
    for f in failures:
        print(f"    - {f}")
    sys.exit(EXIT_BAD)
print("all controls passed — the check can fail for each assertion it claims to make")
