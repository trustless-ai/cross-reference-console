#!/usr/bin/env python3
"""
Lane distinctness — the predicate the edge rule rests on.

CELL-v1.md §5: "An edge holds when >= 2 Cells are GREEN with byte-equal
claim_id on DISTINCT lanes/implementations."

Nothing defined "distinct" and nothing checked it. `validate_nodes.py` only
asserts the lane string is non-empty and contains "/", so two nodes running one
implementation under the names `recompute/a` and `recompute/b` would produce a
green edge carrying zero independence. The core predicate of the mesh was a
label.

This derives distinctness from `evidence.independence` instead of the name.

WHAT IS MACHINE-CHECKABLE (enforced here)
  - impl_hash present and pairwise distinct
  - repo present and pairwise distinct

WHAT IS NOT (reported, never asserted)
  Hash inequality proves the FILES differ, not that the implementations are
  INDEPENDENT. Fork `reference/claim_id.py`, change a comment, and you get a
  fresh impl_hash with no independence whatsoever. Whether an implementation
  was written from the spec or derived from another node's code is a
  provenance claim that cannot be derived from any hash we collect.

  So this tool reports an independence BASIS per pair and refuses to collapse
  it into a boolean. Necessary conditions are enforced; the sufficient one is
  disclosed or it is absent, and absent is not a pass.

Run:  python3 reference/check_lane_distinctness.py
"""

import json
import pathlib
import sys
from itertools import combinations

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_payload(path):
    """Both envelopes: EIP-712 carries proof_payload, Nostr signs content."""
    d = json.loads(path.read_text())
    pp = d.get("proof_payload")
    if pp is None and "event" in d:
        pp = json.loads(d["event"].get("content", "{}"))
    return pp or {}


def independence_of(pp):
    ind = (pp.get("evidence") or {}).get("independence") or {}
    impl = ind.get("implementation") or {}
    return {
        "impl_hash": impl.get("impl_hash"),
        "repo": impl.get("repo"),
        "path": impl.get("path"),
        "commit": impl.get("commit"),
        "dependency_lock": ind.get("dependency_lock"),
        "runtime_image": ind.get("runtime_image"),
        # Not in the schema yet. Pavlo declared exactly this in prose inside
        # his boundary string ("from-scratch ... NOT reference/claim_id.py ...
        # reasoned from CLAIM.md"). Promoting it to a field is the crc.cell.v3
        # proposal; until then it reads as absent, never as satisfied.
        "derived_from": ind.get("derived_from", "ABSENT"),
    }


def pair_basis(a, b):
    """Return (necessary_ok, basis_lines) for one pair. Never a bare bool."""
    basis = []
    ok = True

    for field in ("impl_hash", "repo"):
        av, bv = a[1][field], b[1][field]
        if av is None or bv is None:
            basis.append(f"RED   {field}: null on one side — cannot establish distinctness")
            ok = False
        elif av == bv:
            basis.append(f"RED   {field}: IDENTICAL — same implementation, not two lanes")
            ok = False
        else:
            basis.append(f"GREEN {field}: distinct")

    # Strengthening evidence: present or not, never required.
    for field in ("dependency_lock", "runtime_image"):
        av, bv = a[1][field], b[1][field]
        if av is None or bv is None:
            basis.append(f"amber {field}: not disclosed by both — no strengthening")
        elif av == bv:
            basis.append(f"RED   {field}: identical — same environment")
            ok = False
        else:
            basis.append(f"GREEN {field}: distinct — strengthens")

    # The sufficient condition, which no hash can supply.
    av, bv = a[1]["derived_from"], b[1]["derived_from"]
    if av == "ABSENT" or bv == "ABSENT":
        basis.append(
            "AMBER derived_from: field does not exist yet (crc.cell.v3 proposal) — "
            "independence is NOT established, only not-contradicted"
        )
    elif av is None and bv is None:
        basis.append("GREEN derived_from: both declare independent derivation")
    else:
        basis.append(f"RED   derived_from: {av!r} / {bv!r} — one derives from the other")
        ok = False

    return ok, basis


def main():
    cells = sorted(ROOT.glob("cells/*/*.cell.json"))
    if not cells:
        print("ERROR: no cells found — discovery broken, refusing to report a pass",
              file=sys.stderr)
        return 1

    nodes = []
    for c in cells:
        pp = load_payload(c)
        nodes.append((c.stem.replace(".cell", ""), independence_of(pp), pp.get("claim_id")))

    print(f"Lane distinctness over {len(nodes)} cell(s)\n")

    failures = 0
    for (na, ia, ca), (nb, ib, cb) in combinations(nodes, 2):
        if ca != cb:
            continue  # only cells on the same claim can form an edge
        ok, basis = pair_basis((na, ia), (nb, ib))
        head = "DISTINCT (necessary conditions met)" if ok else "NOT DISTINCT"
        print(f"── {na}  ×  {nb}\n   {head}")
        for line in basis:
            print(f"     {line}")
        print()
        if not ok:
            failures += 1

    print("─" * 68)
    if failures:
        print(f"{failures} pair(s) fail the necessary conditions.")
        return 1

    print("All pairs meet the NECESSARY conditions for distinctness.")
    print()
    print("Not a claim of independence. `derived_from` does not exist in the")
    print("signed struct yet, so no pair can do better than 'not contradicted'.")
    print("Promoting it is the crc.cell.v3 proposal — see PROPOSAL-lane-distinctness.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
