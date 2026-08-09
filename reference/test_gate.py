#!/usr/bin/env python3
"""Pre-hash gate conformance: one negative vector at every predicate the gate
enforces (a rule without a failing vector is a rule nobody has watched fire),
plus the #236 golden vector staying byte-for-byte green. Stdlib only.

    python3 test_gate.py
"""
import json, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claim_id import claim_id, loads_strict

GOLDEN_VECTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "vectors", "236-review-verdict.claim.json")
GOLDEN_ID = "sha256:df1a6bfe3063186f8a8327b75a5bfddae12d3518f2cc16f8fddbc6c311de9512"

base = json.load(open(GOLDEN_VECTOR))
failures = []


def expect_reject(label, fn):
    try:
        fn()
    except ValueError:
        print(f"  reject ok · {label}")
        return
    failures.append(label)
    print(f"  FAIL — accepted: {label}")


def mutated(**changes):
    d = dict(base)
    d.update(changes)
    return d


print("negative vectors (one per gate predicate):")
# field set
expect_reject("missing field", lambda: claim_id({k: v for k, v in base.items() if k != "as_of"}))
expect_reject("extra field", lambda: claim_id(mutated(extra="x")))
# duplicate members (raw text — the parsed object hides them)
expect_reject("duplicate member", lambda: loads_strict('{"a":1,"a":2}'))
expect_reject("nested duplicate member", lambda: loads_strict('{"x":{"a":1,"a":2}}'))
# types
expect_reject("schema mismatch", lambda: claim_id(mutated(schema="crc.claim.v1")))
expect_reject("empty string field", lambda: claim_id(mutated(profile_id="")))
expect_reject("claim_body wrong type", lambda: claim_id(mutated(claim_body=7)))
expect_reject("claimant bool", lambda: claim_id(mutated(claimant=True)))
expect_reject("claimant string", lambda: claim_id(mutated(claimant="54848")))
# hash grammar
expect_reject("artifact_hash sha256: prefix", lambda: claim_id(mutated(artifact_hash="sha256:" + base["artifact_hash"])))
expect_reject("artifact_hash 0x prefix", lambda: claim_id(mutated(artifact_hash="0x" + base["artifact_hash"])))
expect_reject("artifact_hash uppercase", lambda: claim_id(mutated(artifact_hash=base["artifact_hash"].upper())))
expect_reject("artifact_hash short", lambda: claim_id(mutated(artifact_hash=base["artifact_hash"][:-1])))
# claimant range
expect_reject("claimant negative", lambda: claim_id(mutated(claimant=-1)))
expect_reject("claimant > uint256", lambda: claim_id(mutated(claimant=2**256)))
# as_of strictness
expect_reject("as_of with offset", lambda: claim_id(mutated(as_of="2026-08-04T00:11:24+00:00")))
expect_reject("as_of fractional seconds", lambda: claim_id(mutated(as_of="2026-08-04T00:11:24.000Z")))
expect_reject("as_of impossible instant", lambda: claim_id(mutated(as_of="2026-13-04T00:11:24Z")))

print("golden vector:")
got = claim_id(loads_strict(open(GOLDEN_VECTOR).read()))
if got == GOLDEN_ID:
    print(f"  green · {got}")
else:
    failures.append("golden vector drifted")
    print(f"  FAIL — golden vector drifted: {got}")

if failures:
    print(f"\n{len(failures)} failure(s): {failures}")
    sys.exit(1)
print("\nall green — gate conformant")


def _artifact_type_axes():
    """CLAIM.md — ClaimPreimage.artifact_type is fixed by the lift rule, never
    copied from the source's verdict.artifact_type.

    A node that "reconciles" the two changes claim_id and breaks every edge on
    that claim. The ruling is @babyblueviper1's, confirmed against the producing
    schema: the source value describes WHAT WAS REVIEWED, the claim value
    describes WHAT KIND OF CLAIM THIS IS. Two axes.

    This vector pins the consequence rather than the prose: reconciling them
    must move claim_id.
    """
    import glob, json, pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from claim_id import claim_id
    fails = 0
    for p in glob.glob(str(pathlib.Path(__file__).resolve().parent.parent / "claims" / "*.json")):
        if len(pathlib.Path(p).stem) != 64:
            continue
        d = json.load(open(p))
        pre = d["claim_preimage"]
        before = claim_id(pre)
        reconciled = dict(pre, artifact_type="onchain_action")   # the tempting "fix"
        if claim_id(reconciled) == before:
            print(f"  FAIL  reconciling artifact_type did NOT change claim_id ({pathlib.Path(p).stem[:12]}…)")
            fails += 1
    if not fails:
        print("  ok    reconciling artifact_type would change claim_id (so: do not)")
    return fails


if __name__ == "__main__" and "--axes" in __import__("sys").argv:
    raise SystemExit(1 if _artifact_type_axes() else 0)
