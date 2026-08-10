#!/usr/bin/env python3
"""
Negative vectors for lane distinctness.

The checker exists to catch one thing: a cell that copies another node's
implementation and registers it under a different lane name. A checker that
has never been shown failing is a checker nobody has tested — so every
predicate it enforces gets a vector that trips it.

Run:  python3 reference/test_lane_distinctness.py
"""

import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from check_lane_distinctness import independence_of, pair_basis  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

PASS, FAIL = "  ok  ", "  FAIL"
failures = 0


def chk(label, cond):
    global failures
    print(f"{PASS if cond else FAIL}  {label}")
    if not cond:
        failures += 1


def payload(path):
    d = json.loads(path.read_text())
    pp = d.get("proof_payload")
    if pp is None and "event" in d:
        pp = json.loads(d["event"].get("content", "{}"))
    return pp or {}


def main():
    cells = sorted(ROOT.glob("cells/*/*.cell.json"))
    if len(cells) < 2:
        print("ERROR: need >= 2 cells to test pairing", file=sys.stderr)
        return 1

    # Carry claim_id. An edge exists between two nodes ON THE SAME CLAIM, so
    # those are the only pairs distinctness is defined over — which is exactly
    # what check_lane_distinctness.py does (`if ca != cb: continue`).
    #
    # This harness dropped it and paired every Cell with every other. It passed
    # for an accidental reason: until node 2 verified a second claim, no node
    # held two Cells, so a same-node pair could never arise. The moment one did,
    # it demanded that a node's Cell on claim A be "distinct" from its own Cell
    # on claim B — same node, same implementation, no edge between them, and no
    # such requirement anywhere in the spec.
    #
    # The test asserted a property the checker deliberately does not: adjacent
    # to distinctness, not distinctness. Real data surfaced it; nothing else
    # would have.
    real = [(c.stem.removesuffix(".cell"), independence_of(payload(c)),
             payload(c).get("claim_id")) for c in cells]

    print("── positive: cells on the same claim are pairwise distinct")
    pairs = 0
    for i in range(len(real)):
        for j in range(i + 1, len(real)):
            if real[i][2] != real[j][2]:
                continue                      # different claims: no edge, nothing to check
            ok, _ = pair_basis(real[i][:2], real[j][:2])
            chk(f"{real[i][0]} x {real[j][0]}  (claim {str(real[i][2])[7:19]}…)", ok)
            pairs += 1
    # A positive section that silently checks nothing is worse than no section.
    chk("at least one same-claim pair existed to check", pairs > 0)

    print("\n── regression: cell-name derivation (Pavlo, 2026-08-07)")
    # `.replace(".cell", "")` corrupts any node whose name CONTAINS ".cell",
    # not just one that ends with it, because replace() is not anchored.
    # Found by Pavlo running this file; fixed with removesuffix in both places.
    for fn, want in [
        ("invinoveritas.cell.json", "invinoveritas"),
        ("mycelium-anchorregistry.cell.json", "mycelium-anchorregistry"),
        ("mycelium.cellstore.cell.json", "mycelium.cellstore"),
        ("x.cellular-node.cell.json", "x.cellular-node"),
    ]:
        got = pathlib.Path(fn).stem.removesuffix(".cell")
        chk(f"{fn} -> {want}", got == want)

    print("\n── negative: each predicate, tripped on purpose")
    # The synthetic vectors below mutate one field at a time and assert what that
    # does to distinctness, so the two fixtures must be from DIFFERENT nodes —
    # otherwise every vector is drowned out by identical impl_hash and tests
    # nothing about the field it names.
    #
    # `real[0], real[1]` was fine only while each node held exactly one Cell.
    # As soon as node 2 verified a second claim, index 0 and 1 became two of ITS
    # OWN Cells and the vectors started measuring the fixture instead of the
    # predicate. Pick by distinct node id rather than by position.
    _by_node = {}
    for r in real:
        _by_node.setdefault(r[0], r)
    if len(_by_node) < 2:
        print("ERROR: need cells from >= 2 distinct nodes for the synthetic vectors",
              file=sys.stderr)
        return 1
    base, other = list(_by_node.values())[:2]
    chk(f"fixtures are from distinct nodes ({base[0]} / {other[0]})", base[0] != other[0])

    # 1. The attack the checker exists for: same implementation, new label.
    copycat = ("copycat", copy.deepcopy(base[1]))
    ok, basis = pair_basis(base, copycat)
    chk("identical impl_hash + repo is NOT distinct", not ok)
    chk("  and says why (impl_hash IDENTICAL)",
        any("impl_hash" in b and "IDENTICAL" in b for b in basis))

    # 2. Null impl_hash cannot establish distinctness.
    nulled = ("nulled", {**copy.deepcopy(other[1]), "impl_hash": None})
    ok, basis = pair_basis(base, nulled)
    chk("null impl_hash is NOT distinct (absence is not a pass)", not ok)

    # 3. Null repo, same.
    nullrepo = ("nullrepo", {**copy.deepcopy(other[1]), "repo": None})
    ok, _ = pair_basis(base, nullrepo)
    chk("null repo is NOT distinct", not ok)

    # 4. A shared runtime image is a real correlation, even when code differs.
    shared_env = copy.deepcopy(other[1])
    shared_env["runtime_image"] = "sha256:" + "a" * 64
    b2 = copy.deepcopy(base[1])
    b2["runtime_image"] = "sha256:" + "a" * 64
    ok, _ = pair_basis(("a", b2), ("b", shared_env))
    chk("identical runtime_image is NOT distinct even with distinct code", not ok)

    # 5. Declared derivation defeats distinctness however different the files are.
    #
    # These two vectors used to encode the DRAFT shape — derived_from=None meaning
    # "independent" and a bare repo URL meaning "derived" — because they were
    # written before crc.cell.v3 shipped. The spec landed on `[]` for no-known-
    # derivation and LINEAGE-REF.md §2 REJECTS null. So the tests asserted the
    # inverse of the rule and passed against a checker that shared their mistake:
    # two wrongs agreeing, which is what a test and its subject are supposed to
    # make impossible. The first pair of real v3 Cells read
    # `[] / [] — one derives from the other`, and only then did it show.
    derived = copy.deepcopy(other[1])
    derived["derived_from"] = ["crc.lineage.v0:impl/" + base[1]["impl_hash"]]
    b3 = copy.deepcopy(base[1])
    b3["derived_from"] = []
    ok, basis = pair_basis(("origin", b3), ("fork", derived))
    chk("declared derivation (real LineageRef) is NOT an independent lane", not ok)
    chk("  and the basis names the derivation",
        any("derives from" in b or "DERIVED" in b for b in basis))

    # 6. Both declaring [] — no known derivation — is what clears it outright.
    i1, i2 = copy.deepcopy(base[1]), copy.deepcopy(other[1])
    i1["derived_from"] = i2["derived_from"] = []
    ok, basis = pair_basis(("a", i1), ("b", i2))
    chk("both derived_from=[] clears the sufficient condition", ok)
    # Not GREEN by default. These two lanes have no recorded affiliation, and an
    # unstated affiliation is exactly what a reader cannot weigh — so `[]` on both
    # reads as declared-not-adverse, never as demonstrated independence.
    chk("  and reads not-adverse, NOT independence, when affiliation is unrecorded",
        any("derived_from" in b and b.startswith("AMBER") for b in basis))

    import lineage_graph as _lg
    _saved = dict(_lg._AFFIL)
    try:
        _lg._AFFIL.update({"a": "org-one", "b": "org-two"})
        ok, basis = pair_basis(("a", i1), ("b", i2))
        chk("  and IS GREEN once the lanes are unaffiliated", ok and
            any("GREEN derived_from" in b for b in basis))
    finally:
        _lg._AFFIL.clear(); _lg._AFFIL.update(_saved)

    # 6b. null is NOT the honest value and must not read as independence.
    n1, n2 = copy.deepcopy(base[1]), copy.deepcopy(other[1])
    n1["derived_from"] = n2["derived_from"] = None
    ok, basis = pair_basis(("a", n1), ("b", n2))
    chk("derived_from=null does NOT clear it (LINEAGE-REF.md rejects null)",
        not any("GREEN derived_from" in b for b in basis))

    # 7. The absent field must read AMBER — never as satisfied.
    ok, basis = pair_basis(base, other)
    chk("absent derived_from reads AMBER, not GREEN",
        any("AMBER derived_from" in b for b in basis))

    print()
    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("all green — lane distinctness catches what it exists for")
    return 0


if __name__ == "__main__":
    sys.exit(main())
