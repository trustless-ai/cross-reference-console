#!/usr/bin/env python3
"""Every record in pins/ must reproduce its own CID and tree hash.

`test_verify_pin.py` proves the *verifier* is correct against synthetic vectors.
Nothing proved the *records* were. A pin record whose CID did not recompute
could merge to main and sit there looking authoritative until somebody happened
to run `verify_pin.py` by hand — and the record is the artifact people sign
against, so a wrong one collects real signatures over a false statement.

## Why this cannot simply be `verify_pin.py` in CI

`verify_pin.py` answers *"may this be pinned?"* and its answer is RED until two
independent confirmations exist. That is correct there and useless here: a record
is *supposed* to land unsigned and collect signatures afterwards. Running it
as-is would make CI red for every new record, and a check that is red by design
is a check people learn to ignore.

So this splits the question the way the record itself is split:

    structural   the CID recomputes, the tree hash reproduces, cid_params
                 match the site commit, the console page is the build of its
                 locked commit                                    -> MUST be true now
    social       two authenticated confirmations                  -> NOT checked here

The structural half is the half that must never land wrong, because every
signature added later is a signature over it.

## Reading the tri-state

`verify_pin.py` reports RED for a failed rebuild and RED for missing signatures,
which are the same colour for very different reasons. This reads its lines rather
than its exit code, and treats **only** the confirmation-count line as expected.
Anything else RED fails. If verify_pin cannot run at all — no network, no git —
that is a COULD-NOT-CHECK and fails too: a pin record silently unverified is the
exact state this file exists to prevent.
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins"
VERIFY = ROOT / "reference" / "verify_pin.py"

# The one RED that is expected on a record that has not collected signatures yet.
CONFIRMATION_RED = re.compile(r"confirmation\(s\) are both authenticated and correct"
                              r"|only \d+ confirmation")

fails = []


def check(rec: pathlib.Path) -> None:
    print(f"\n── {rec.name}")
    try:
        r = subprocess.run([sys.executable, str(VERIFY), str(rec)],
                           capture_output=True, text=True, timeout=600)
    except Exception as e:                      # noqa: BLE001 — any failure is could-not-check
        print(f"   FAIL  verify_pin could not run: {e}")
        fails.append(f"{rec.name}: could not run")
        return

    out = r.stdout + r.stderr
    if not out.strip():
        print("   FAIL  verify_pin produced no output — nothing was actually checked")
        fails.append(f"{rec.name}: no output")
        return

    # verify_pin prints per-check lines as "RED   · <what failed>" and ends with a
    # bare verdict line "RED — do NOT pin". Counting the verdict as a check would
    # fail every unsigned record — which is the normal state of a new one.
    def lines(prefix):
        return [ln.strip() for ln in out.splitlines()
                if ln.strip().startswith(prefix) and "·" in ln]

    reds = lines("RED")
    structural = [ln for ln in reds if not CONFIRMATION_RED.search(ln)]
    pending = [ln for ln in reds if CONFIRMATION_RED.search(ln)]

    # A record that reports no structural check at all is not passing, it is silent.
    oks = lines("ok")
    if len(oks) < 4:
        print(f"   FAIL  only {len(oks)} check(s) reported — expected the full structural set")
        fails.append(f"{rec.name}: too few checks ran")
        return

    for ln in structural:
        print(f"   FAIL  {ln}")
    if structural:
        fails.append(f"{rec.name}: {len(structural)} structural failure(s)")
    else:
        print(f"   ok    structural: {len(oks)} checks reproduce")
        if pending:
            # Not a failure. Stated out loud so 'green' never silently means 'signed'.
            print("   ..    awaiting signatures — the two-party rule is NOT asserted here")


def main() -> int:
    if not PINS.is_dir():
        print("no pins/ — nothing to check")
        return 0
    records = sorted(PINS.glob("*.json"))
    if not records:
        print("pins/ is empty — nothing to check")
        return 0
    print(f"checking {len(records)} pin record(s) — structural only, signatures NOT asserted")
    for rec in records:
        check(rec)
    print()
    if fails:
        print(f"{len(fails)} pin record(s) do not reproduce:")
        for f in fails:
            print(f"  {f}")
        return 1
    print("all pin records reproduce their own CID and tree hash")
    return 0


if __name__ == "__main__":
    sys.exit(main())
