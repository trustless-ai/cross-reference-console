#!/usr/bin/env python3
"""VECTOR-MATRIX-v3-independence rows V-01…V-06, V-12…V-14 — executable.

CELL-v3.md §4 marks its normative prose `[PENDING-VECTOR]` until these run in
CI. That is the whole point of this file: the spec declines to be normative
about lineage until someone can demonstrate the algorithm doing what the prose
says, which is the same standard the rest of the repo holds itself to.

Synthetic graphs throughout. Real Cells cannot express V-02…V-05 yet — nobody
has published a v3 Cell — and waiting for one would mean the spec stayed
pending while the code went unexercised.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lineage_graph import (DERIVED, INDEPENDENT, NOT_PROVEN,  # noqa: E402
                           ancestors, build_graph, pair_state)
import lineage_graph as _lg  # noqa: E402

fails = 0


def chk(label, cond, detail=""):
    global fails
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails += 1


H = {n: "sha256:" + c * 64 for n, c in
     (("A", "a"), ("B", "b"), ("C", "c"), ("X", "1"), ("D", "d"))}
REF = "crc.lineage.v0:impl/"


def cell(name, derived_from, schema="crc.cell.v3", result="GREEN", impl_hash=None):
    return (name, {"schema": schema, "result": result, "evidence": {"independence": {
        "implementation": {"repo": f"https://github.com/{name}/impl", "commit": "c" * 40,
                           "path": "x.py", "impl_hash": impl_hash or H[name]},
        "derived_from": derived_from}}})


def g(*cells):
    return build_graph(list(cells))


def state(graph, a, b):
    return pair_state(graph, H[a], H[b])


# The lineage rows below test LINEAGE. INDEPENDENT is currently UNREACHABLE — it
# is gated behind binding affiliation at signing time (Pavlo's audit) — so these
# rows assert that the LINEAGE conclusion was reached, via the basis, rather than
# asserting a terminal state the gate now withholds. Changing them to expect
# NOT_PROVEN outright would have deleted their meaning: every row would pass for
# the gate's reason and none would still be testing ancestry.
LINEAGE_CLEAR = "no shared ancestry"
_lg._AFFIL.update({n: f"org-{n.lower()}" for n in ("A", "B", "C", "X", "D")})

print("VECTOR-MATRIX-v3-independence — lineage rows\n")

# V-01 · both declared, no ancestry -> INDEPENDENT
st, basis = state(g(cell("A", []), cell("B", [])), "A", "B")
chk("V-01 independent baseline -> lineage clear (terminal state gated)",
    any(LINEAGE_CLEAR in b for b in basis) and st != DERIVED, st)

# V-02 · B derives directly from A
st, basis = state(g(cell("A", []), cell("B", [REF + H["A"]])), "A", "B")
chk("V-02 direct derivation -> DERIVED", st == DERIVED, st)
chk("  and the basis names the direction", any("derives from" in b for b in basis))

# V-03 · multi-parent: X from both A and B
gr = g(cell("A", []), cell("B", []), cell("X", [REF + H["A"], REF + H["B"]]))
chk("V-03 multi-parent X×A -> DERIVED", state(gr, "X", "A")[0] == DERIVED)
chk("V-03 multi-parent X×B -> DERIVED", state(gr, "X", "B")[0] == DERIVED)
chk("V-03 the two parents remain lineage-clear of each other",
    any(LINEAGE_CLEAR in b for b in state(gr, "A", "B")[1])
    and state(gr, "A", "B")[0] != DERIVED)

# V-04 · two hops: X -> A -> C. The pair X×C is the whole point of transitivity.
gr = g(cell("C", []), cell("A", [REF + H["C"]]), cell("X", [REF + H["A"]]))
st, basis = state(gr, "X", "C")
chk("V-04 two-hop transitivity X×C -> DERIVED", st == DERIVED, st)
chk("  and C is genuinely in Ancestors(X)", H["C"] in ancestors(gr, H["X"]))

# V-05 · cycle A<->B
st, basis = state(g(cell("A", [REF + H["B"]]), cell("B", [REF + H["A"]])), "A", "B")
chk("V-05 cycle -> INDEPENDENCE_NOT_PROVEN", st == NOT_PROVEN, st)
chk("  and the basis says cycle", any("cycle" in b for b in basis))

# V-06 · cited ancestor resolves to nothing
st, basis = state(g(cell("A", []), cell("X", [REF + "sha256:" + "e" * 64])), "A", "X")
chk("V-06 unresolved target -> INDEPENDENCE_NOT_PROVEN", st == NOT_PROVEN, st)
chk("  and it is NOT silently treated as no-ancestor",
    any("unresolved" in b for b in basis))

# V-12 · any pre-v3 cell in the pair
st, basis = state(g(cell("A", []), cell("B", None, schema="crc.cell.v2")), "A", "B")
chk("V-12 mixed v3×v2 -> INDEPENDENCE_NOT_PROVEN", st == NOT_PROVEN, st)
chk("  and the basis names the pre-v3 side", any("pre-v3" in b for b in basis))

# V-13 · fork laundering: different hash and repo, but declared derivation.
# The attack this exists for — cosmetic distinctness with real shared lineage.
st, basis = state(g(cell("A", []), cell("B", [REF + H["A"]])), "A", "B")
chk("V-13 fork laundering (distinct hashes, declared parent) -> DERIVED", st == DERIVED, st)

# V-14 · honest [] on both, genuinely unrelated
st, basis = state(g(cell("A", []), cell("D", [])), "A", "D")
chk("V-14 honest [] both sides -> lineage clear (terminal state gated)",
    any(LINEAGE_CLEAR in b for b in basis) and st != DERIVED, st)

print("\n── affiliation: [] is a declaration, and declarations from one group are not adverse")

# Damon, 2026-08-10: "reserve INDEPENDENT for a lane nobody in this group runs."
# `[]` is signed provenance from the lane OPERATOR. Two lanes run inside one
# working group had no interest in contradicting each other, and no amount of
# signing manufactures adversity. The result still catches implementation
# divergence — it is simply not the strongest word in the system.
_saved = dict(_lg._AFFIL)
try:
    _lg._AFFIL.update({"A": "wg", "B": "wg", "D": "outsider"})
    st, basis = state(g(cell("A", []), cell("B", [])), "A", "B")
    chk("same affiliation -> NOT_PROVEN, not INDEPENDENT", st == NOT_PROVEN, st)
    chk("  and the basis names BOTH unresolved relations, not a conflated label",
        any("shared_operator" in b and "shared_design_context" in b for b in basis))

    # Was: "different affiliation -> INDEPENDENT". Pavlo's audit closed that
    # branch — affiliation is read from live nodes.json and bound by no signed
    # Cell, so an unsigned edit could manufacture the strongest verdict in the
    # system. Demonstrated on real data before gating it.
    st, basis = state(g(cell("A", []), cell("D", [])), "A", "D")
    chk("different affiliation is NOT ENOUGH while affiliation is unbound",
        st == NOT_PROVEN, st)
    chk("  and the basis says why, rather than reading as ordinary not-proven",
        any("is not inferred from" in b for b in basis))

    _lg._AFFIL.update({"C": None})
    st, basis = state(g(cell("A", []), cell("C", [])), "A", "C")
    chk("unrecorded affiliation -> NOT_PROVEN (absence is not the strong case)",
        st == NOT_PROVEN, st)

    # Affiliation must never RESCUE a pair. It can only demote — and note that is
    # a claim about THIS FUNCTION, not about the system: the input it reads is
    # unsigned, which is exactly what the gate above exists for.
    st, _ = state(g(cell("A", []), cell("D", ["crc.lineage.v0:impl/" + H["A"]])), "A", "D")
    chk("unaffiliated + declared derivation is still DERIVED (affiliation cannot rescue)",
        st == DERIVED, st)

    # The gate must not be reachable around: no affiliation arrangement produces
    # INDEPENDENT while the field is unbound.
    for aff in (("wg", "wg"), ("one", "two"), (None, "two")):
        _lg._AFFIL.update({"A": aff[0], "D": aff[1]})
        st, _ = state(g(cell("A", []), cell("D", [])), "A", "D")
        chk(f"no affiliation pair reaches INDEPENDENT while unbound {aff}",
            st != INDEPENDENT, st)
finally:
    _lg._AFFIL.clear(); _lg._AFFIL.update(_saved)

print("\n── properties that must hold regardless of row")

gr = g(cell("A", []), cell("B", [REF + H["A"]]))
chk("pair state is order-independent",
    state(gr, "A", "B")[0] == state(gr, "B", "A")[0])

# A cycle must not hang the closure — the reason ancestors() is iterative.
gr = g(cell("A", [REF + H["B"]]), cell("B", [REF + H["C"]]), cell("C", [REF + H["A"]]))
chk("3-node cycle terminates rather than looping", ancestors(gr, H["A"]) >= {H["B"], H["C"]})
chk("3-node cycle -> NOT_PROVEN", state(gr, "A", "B")[0] == NOT_PROVEN)

# Self-reference is rejected at the gate (§1.1), so it must never reach here as
# an edge — but if it did, it must not make a node its own ancestor.
gr = g(cell("A", [REF + H["A"]]))
chk("self-reference does not become a self-edge", H["A"] not in ancestors(gr, H["A"]))

# Lineage may only DEMOTE. Declaring [] cannot rescue a pair that shares an
# implementation — the necessary conditions live in check_lane_distinctness and
# this module never overrides them.
gr = g(cell("A", []), cell("B", [], impl_hash=H["A"]))
chk("identical impl_hash collapses to ONE node (cannot be laundered by declaring [])",
    len(gr) == 1)

print()
print("all green — lineage graph vectors" if not fails else f"{fails} failure(s)")
raise SystemExit(1 if fails else 0)
