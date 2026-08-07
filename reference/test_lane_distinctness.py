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

    real = [(c.stem.removesuffix(".cell"), independence_of(payload(c))) for c in cells]

    print("── positive: the live cells are pairwise distinct")
    for i in range(len(real)):
        for j in range(i + 1, len(real)):
            ok, _ = pair_basis(real[i], real[j])
            chk(f"{real[i][0]} x {real[j][0]}", ok)

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
    base = real[0]
    other = real[1]

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
    derived = copy.deepcopy(other[1])
    derived["derived_from"] = base[1]["repo"]
    b3 = copy.deepcopy(base[1])
    b3["derived_from"] = None
    ok, basis = pair_basis(("origin", b3), ("fork", derived))
    chk("declared derived_from is NOT an independent lane", not ok)

    # 6. Both independent is the only shape that clears it outright.
    i1, i2 = copy.deepcopy(base[1]), copy.deepcopy(other[1])
    i1["derived_from"] = i2["derived_from"] = None
    ok, basis = pair_basis(("a", i1), ("b", i2))
    chk("both derived_from=null clears the sufficient condition", ok)
    chk("  and is reported GREEN, not merely not-contradicted",
        any("GREEN derived_from" in b for b in basis))

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
