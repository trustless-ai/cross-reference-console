#!/usr/bin/env python3
"""Controls for the Boardy rule check.

The point of this suite is the FAIL path. A rendered-surface check that has only ever been
run against a correct mapping has not been shown to work — it has been shown to be silent,
which is what a broken one also looks like, and silence about the surface a reader trusts is
the exact defect the check exists to prevent.

Each control mutates the SHIPPED mapping in a temp copy and requires the check to go red for
that specific reason. Exit codes are asserted exactly, never "non-zero": this repo separates
1 (determinate mismatch) from 2 (could not check), and a control that accepted either would
pass while the check collapsed those two states — the same defect one level up.

Run: python3 reference/test_check_boardy_rule.py
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECK = ROOT / "reference" / "check_boardy_rule.py"
MARKER = ROOT / "ui" / "lineage-marker.js"
GOLDEN = ROOT / "reference" / "vectors" / "rendered-markers.golden.json"

EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if not ok and detail else ""))
    if not ok:
        failures.append(label)


def run(marker: pathlib.Path | None = None, golden: pathlib.Path | None = None):
    argv = [sys.executable, str(CHECK)]
    if marker is not None:
        argv += ["--marker", str(marker)]
    if golden is not None:
        argv += ["--golden", str(golden)]
    return subprocess.run(argv, capture_output=True, text=True, timeout=300)


def with_mutation(find: str, replace: str):
    """A temp copy of the shipped mapping with one substitution applied."""
    src = MARKER.read_text(encoding="utf-8")
    if find not in src:
        return None, f"anchor not present in mapping: {find[:60]}"
    td = tempfile.mkdtemp()
    p = pathlib.Path(td) / "lineage-marker.js"
    p.write_text(src.replace(find, replace, 1), encoding="utf-8")
    return p, None


def control_unqualified_green() -> None:
    """The original defect: a state that should carry a caveat rendering without one."""
    print("\nNEGATIVE CONTROL — NOT PROVEN rendered without its qualifier (must be CAUGHT):")
    # Targets the unproven() branch specifically: the one whose whole job is to carry a
    # caveat. Anchored on the tail immediately above it so the mutation cannot land on
    # INDEPENDENT's flag by accident.
    p, err = with_mutation(
        "tail: ' · independence NOT PROVEN — ' + why + NOT_PROVEN_SUFFIX,\n      qualified: true",
        "tail: ' · independence NOT PROVEN — ' + why + NOT_PROVEN_SUFFIX,\n      qualified: false")
    if p is None:
        # Anchor drifted. Reported, never skipped — an unrun control is not a passing one.
        check("mutation anchor still present in the mapping", False, err or "")
        return
    r = run(marker=p)
    check("exit is exactly 1 (determinate), not merely non-zero", r.returncode == EXIT_BAD,
          f"got {r.returncode}")
    check("names the unqualified case", "qualified" in r.stdout.lower())
    shutil.rmtree(p.parent, ignore_errors=True)


def control_qualifier_dropped_from_text() -> None:
    """A `qualified: true` flag beside a bare sentence: the letter kept, the point lost."""
    print("\nNEGATIVE CONTROL — flag stays true but the words 'NOT PROVEN' are removed:")
    p, err = with_mutation("' · independence NOT PROVEN — '", "' · independence — '")
    if p is None:
        check("mutation anchor still present in the mapping", False, err or "")
        return
    r = run(marker=p)
    check("exit is exactly 1", r.returncode == EXIT_BAD, f"got {r.returncode}")
    check("catches it in the rendered text, not just the flag",
          "tail names it NOT PROVEN" in r.stdout, r.stdout[-300:])
    shutil.rmtree(p.parent, ignore_errors=True)


def control_wording_drift() -> None:
    """Any change to what a reader sees must be deliberate — i.e. must update the golden."""
    print("\nNEGATIVE CONTROL — rendered wording changed without updating the golden:")
    p, err = with_mutation("'. Distinctness is necessary, not sufficient.'",
                           "'. Distinctness is sufficient.'")
    if p is None:
        check("mutation anchor still present in the mapping", False, err or "")
        return
    r = run(marker=p)
    check("exit is exactly 1", r.returncode == EXIT_BAD, f"got {r.returncode}")
    check("reports it as a golden mismatch", "renders as recorded" in r.stdout)
    shutil.rmtree(p.parent, ignore_errors=True)


def control_could_not_check_is_not_a_pass() -> None:
    print("\nUNVERIFIABLE — the mapping is missing (must be 2, never 0):")
    r = run(marker=pathlib.Path("/nonexistent/lineage-marker.js"))
    check("exit is exactly 2", r.returncode == EXIT_UNVERIFIABLE, f"got {r.returncode}")
    check("could-not-check never reports as a pass", r.returncode != EXIT_OK)

    print("\nUNVERIFIABLE — the golden is missing (must be 2, never 0):")
    r2 = run(golden=pathlib.Path("/nonexistent/golden.json"))
    check("exit is exactly 2", r2.returncode == EXIT_UNVERIFIABLE, f"got {r2.returncode}")


def positive_control_the_shipped_mapping_passes() -> None:
    print("\nPOSITIVE CONTROL — the mapping as shipped (must PASS):")
    r = run()
    check("exit is exactly 0", r.returncode == EXIT_OK, f"got {r.returncode}: {r.stdout[-300:]}")
    check("says the surface matches the asserted state",
          "the rendered surface matches the asserted state" in r.stdout)


def main() -> int:
    if not CHECK.exists() or not MARKER.exists() or not GOLDEN.exists():
        print("check, mapping or golden missing — cannot run controls", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    print("controls for check_boardy_rule.py")
    control_unqualified_green()
    control_qualifier_dropped_from_text()
    control_wording_drift()
    control_could_not_check_is_not_a_pass()
    positive_control_the_shipped_mapping_passes()
    print()
    if failures:
        print(f"{len(failures)} control(s) failed:")
        for f in failures:
            print(f"    - {f}")
        return EXIT_BAD
    print("all controls passed — the check can fail for each reason it claims to check")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
