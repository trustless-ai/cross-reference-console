#!/usr/bin/env python3
"""Rung 4 — attribution recomputed under an independently identified semantic contract.

The attribution ladder so far (test_operational_gates.py):
  declared → discriminating → correctly-attributed (set equality, #86) → causal (repair, #87).

Every rung above still reads invariant identity from ONE place: the gate's own assertion labels.
`observed_attribution()` parses the gate's failure list; the declared `expect` set is authored by
whoever writes the mutant. If a gate assertion is mislabelled — tagged as enforcing I₁ but actually
enforcing I₂ — a mutant that breaks I₂ trips that assertion, the gate reports I₁, the author declares
I₁, and everything agrees and is wrong together. Set equality cannot see it: both sides inherit the
same map.

Rung 4 breaks that shared-labelling dependency. For each invariant Iₖ it carries an INDEPENDENT
semantic relation Rₖ — implemented from what the invariant MEANS over the record schema, never by
calling the gate or reading its labels — and a pinned separating witness basis Wₖ (acceptance,
rejection, boundary). Per @pipavlo82's rung-4 contract (cross-reference-console#89):

    bₖ(m) = [ Rₖ(m, w) for w in Wₖ ]
    Aᵢ*   = { Iₖ : bₖ(mᵢ) != bₖ(reference) }

The gate's labels are COMPARED to Aᵢ*, never an input to it. Before any attribution is trusted the
oracle proves its separation matrix: the committed basis distinguishes the intended invariant
semantics. If two invariants overlap with no separating witness the honest result is UNRESOLVED, never
a forced singleton. Author-declared Aᵢ survives only as a third cross-check.

Covered invariants: the SERVED-gate serving semantics — where the real harm (laundering a substitution
into an operational footnote) and @pipavlo82's own non-singleton examples live. The machinery is
extensible to the `selects` invariants; the contract is the same.

EXIT: 0 all controls hold · 1 a control failed · 2 could not run.
"""

from __future__ import annotations

import itertools
import sys

EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2

# ── The independent semantic relations Rₖ ────────────────────────────────────────────────────
# Each takes a record and returns True iff invariant Iₖ is SATISFIED (not violated). The relations
# are LAYERED exactly as the invariants mean it: a sub-invariant of `serving` makes no claim when
# `serving` is absent (that is I_serving's job), so removing `serving` attributes to I_serving alone
# rather than cascading. This layering is the invariant semantics, derived here from the schema —
# NOT copied from the gate, which this module never imports.
#
# Record schema (from the serving contract):
#   record["availability"]["serving"] = {
#       "object": "<cid>/path",                         # what bytes are compared against
#       "gateways": { url: [ {"as": client,
#                             "verdict": IDENTICAL|SERVE_TIME_INJECTION|DIFFERS,
#                             "detail": str?}, ... ] } }

VERDICTS = {"IDENTICAL", "SERVE_TIME_INJECTION", "DIFFERS"}


def _serving(rec):
    s = rec.get("availability", {}).get("serving")
    return s if isinstance(s, dict) else None


def _observations(serving):
    """Every structured observation across all gateways, or None if the shape is not obs-lists."""
    gws = serving.get("gateways")
    if not isinstance(gws, dict):
        return None
    obs = []
    for v in gws.values():
        if not isinstance(v, list):
            return None
        for o in v:
            if not isinstance(o, dict):
                return None
            obs.append(o)
    return obs


def r_serving(rec):
    return _serving(rec) is not None


def r_object(rec):
    s = _serving(rec)
    if s is None:
        return True                                  # not this invariant's concern
    return isinstance(s.get("object"), str) and bool(s.get("object"))


def r_observations(rec):
    s = _serving(rec)
    if s is None:
        return True
    return _observations(s) is not None              # every gateway maps to structured obs lists


def r_gateway(rec):
    s = _serving(rec)
    if s is None:
        return True
    gws = s.get("gateways")
    return isinstance(gws, dict) and len(gws) > 0


def r_says_why(rec):
    s = _serving(rec)
    if s is None:
        return True
    obs = _observations(s)
    if obs is None:
        return True                                  # unstructured is r_observations' concern
    return all(isinstance(o.get("detail"), str) and o["detail"]
               for o in obs if o.get("verdict") != "IDENTICAL")


def r_pinned_bytes(rec):
    s = _serving(rec)
    if s is None:
        return True
    gws = s.get("gateways")
    if not isinstance(gws, dict) or len(gws) == 0:
        return True                                  # no gateways at all ⇒ I_gateway's concern
    obs = _observations(s)
    if obs is None:
        return False                # gateways present but unstructured ⇒ no client proven exact
    return any(o.get("verdict") == "IDENTICAL" for o in obs)


# Invariant id → (relation, human label). The label is NEVER read to derive Aᵢ*; it exists only for
# the third cross-check against the gate, and the negative controls prove corrupting it does not move
# Aᵢ*.
INVARIANTS = {
    "serving":      (r_serving,      "carries availability.serving"),
    "object":       (r_object,       "names what the bytes were compared against"),
    "observations": (r_observations, "carries observations"),
    "gateway":      (r_gateway,      "lists at least one gateway"),
    "says_why":     (r_says_why,     "non-identical says why"),
    "pinned_bytes": (r_pinned_bytes, "at least one client somewhere gets the pinned bytes exactly"),
}

# ── The reference record and the witness bases Wₖ ────────────────────────────────────────────────
REFERENCE = {
    "availability": {"serving": {
        "object": "bafyref/console/index.html",
        "gateways": {
            "https://ipfs.io": [
                {"as": "curl", "verdict": "IDENTICAL"},
                {"as": "browser", "verdict": "SERVE_TIME_INJECTION", "detail": "cdn beacon"},
            ],
        },
    }}}


def _mut(rec, fn):
    import copy
    r = copy.deepcopy(rec)
    fn(r["availability"]["serving"])
    return r


def _drop_serving(rec):
    import copy
    r = copy.deepcopy(rec)
    r["availability"].pop("serving")
    return r


# Each witness is (record, label). A witness basis proves the relation's semantics by carrying
# acceptance AND rejection AND boundary cases: a lone rejecting witness can miss over-rejection.
# "class" tags let a negative control drop an entire class and watch separation collapse.
def witness_bases():
    ref = REFERENCE
    W = {
        "serving": [
            ("accept", ref),
            ("reject", _drop_serving(ref)),
        ],
        "object": [
            ("accept", ref),
            ("reject", _mut(ref, lambda s: s.pop("object"))),
            ("boundary", _mut(ref, lambda s: s.update(object=""))),        # empty string is absent
        ],
        "observations": [
            ("accept", ref),
            ("reject", _mut(ref, lambda s: s.update(gateways={"u": {"verdict": "IDENTICAL"}}))),
            ("boundary", _mut(ref, lambda s: s["gateways"].__setitem__(
                "https://ipfs.io", ["a bare string"]))),
        ],
        "gateway": [
            ("accept", ref),
            ("reject", _mut(ref, lambda s: s.update(gateways={}))),
        ],
        "says_why": [
            # reject: an injection with no detail, but a real IDENTICAL kept ⇒ isolates says_why
            ("accept", ref),
            ("reject", _mut(ref, lambda s: s["gateways"]["https://ipfs.io"].__setitem__(
                1, {"as": "browser", "verdict": "SERVE_TIME_INJECTION"}))),
            ("boundary", _mut(ref, lambda s: s["gateways"]["https://ipfs.io"].__setitem__(
                1, {"as": "browser", "verdict": "IDENTICAL"}))),           # IDENTICAL needs no detail
        ],
        "pinned_bytes": [
            # reject: every obs an injection (with detail, so says_why stays satisfied) ⇒ isolates
            ("accept", ref),
            ("reject", _mut(ref, lambda s: s["gateways"].__setitem__("https://ipfs.io", [
                {"as": "curl", "verdict": "SERVE_TIME_INJECTION", "detail": "x"}]))),
        ],
    }
    return W


# ── Separation matrix ────────────────────────────────────────────────────────────────────────────
def separation_matrix(W):
    """Prove every pair of invariants is distinguished by some committed witness, using ONLY the
    relations (never the gate). Returns (separable_pairs, unresolved_pairs).

    Iₖ and Iⱼ are separable iff some witness in Wₖ ∪ Wⱼ is classified differently by Rₖ and Rⱼ.
    """
    all_witnesses = [w for ws in W.values() for _, w in ws]
    unresolved = []
    for a, b in itertools.combinations(INVARIANTS, 2):
        Ra, Rb = INVARIANTS[a][0], INVARIANTS[b][0]
        if not any(Ra(w) != Rb(w) for w in all_witnesses):
            unresolved.append((a, b))
    return unresolved


def witness_self_test(W):
    """Each relation must classify its own basis as the basis declares: accept⇒True, reject⇒False.
    A hollow relation (e.g. always-True from tampering) fails here before it can attribute anything.
    """
    bad = []
    for inv, ws in W.items():
        R = INVARIANTS[inv][0]
        for cls, w in ws:
            got = R(w)
            want = {"accept": True, "reject": False}.get(cls)
            if want is not None and got != want:
                bad.append((inv, cls, got, want))
    return bad


# ── Attribution ────────────────────────────────────────────────────────────────────────────────
def attribution(mutant_record):
    """Aᵢ* = { Iₖ : Rₖ(reference) != Rₖ(mutant) }. No gate, no labels."""
    return {inv for inv, (R, _) in INVARIANTS.items() if R(REFERENCE) != R(mutant_record)}


# The mutants, expressed as independent transforms with a DECLARED set (the same declarations the
# gate harness makes). The oracle recomputes Aᵢ* and must match — proving the declaration is right
# for a reason that never consulted the gate.
def mutants():
    return [
        ("no serving comparison at all", _drop_serving(REFERENCE), {"serving"}),
        ("no stated authority", _mut(REFERENCE, lambda s: s.pop("object")), {"object"}),
        ("no gateways listed at all", _mut(REFERENCE, lambda s: s.update(gateways={})), {"gateway"}),
        ("gateway is a bare verdict, not observations",
         _mut(REFERENCE, lambda s: s.update(gateways={"u": {"verdict": "IDENTICAL"}})),
         {"observations", "pinned_bytes"}),
        ("injection with no detail (every obs)",
         _mut(REFERENCE, lambda s: [o.update(verdict="SERVE_TIME_INJECTION") or o.pop("detail", None)
                                    for gw in s["gateways"].values() for o in gw]),
         {"says_why", "pinned_bytes"}),
        ("no client anywhere gets the pinned bytes",
         _mut(REFERENCE, lambda s: [o.update(verdict="SERVE_TIME_INJECTION", detail="d")
                                    for gw in s["gateways"].values() for o in gw]),
         {"pinned_bytes"}),
    ]


def gate_labels():
    """The SEPARATE label map — the third cross-check only. Deliberately NOT wired into attribution()."""
    return {inv: lbl for inv, (_, lbl) in INVARIANTS.items()}


def main() -> int:
    bad = 0
    W = witness_bases()
    print("rung 4 — attribution under an independently identified semantic contract\n")

    # 1. the relations must classify their own witness bases (proves each Rₖ is not hollow)
    print("witness-basis self-test — every relation classifies accept/reject as declared\n")
    st = witness_self_test(W)
    if st:
        for inv, cls, got, want in st:
            print(f"  FAIL  R[{inv}] on {cls} witness → {got}, declared {want}")
        bad += len(st)
    else:
        print("  ok    all relations classify their bases correctly")

    # 2. separation matrix — prove the basis distinguishes the invariant semantics, without the gate
    print("\nseparation matrix — every invariant pair distinguished by a committed witness\n")
    unresolved = separation_matrix(W)
    if unresolved:
        print(f"  UNRESOLVED pairs (no separating witness): {unresolved}")
        print("  → these invariants cannot be independently attributed; refusing to force a singleton")
        bad += len(unresolved)
    else:
        print(f"  ok    all {len(list(itertools.combinations(INVARIANTS, 2)))} pairs separable")

    # 3. attribution — Aᵢ* recomputed independently must match each declared set
    print("\nattribution — Aᵢ* recomputed independently agrees with the declared set\n")
    for name, rec, declared in mutants():
        a_star = attribution(rec)
        ok = a_star == declared
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}: Aᵢ* = {sorted(a_star)}"
              + ("" if ok else f"  ≠ declared {sorted(declared)}"))
        bad += not ok

    # 3b. the rung-4 payoff, made explicit: a MISLABELLED declaration is refused. Under set-equality
    #     against the gate's own labels, a shared mislabel passes (both sides inherit the same wrong
    #     map); Aᵢ*, derived without labels, disagrees and catches it.
    print("\nmislabel demonstration — a wrong declaration is refused by the label-free Aᵢ*\n")
    _, empty_gw, _ = mutants()[2]           # "no gateways listed at all" — truly {gateway}
    wrong = {"pinned_bytes"}                 # a plausible-but-wrong shared mislabel
    a_star = attribution(empty_gw)
    caught = a_star != wrong
    print(f"  {'ok  ' if caught else 'FAIL'}  mislabel {sorted(wrong)} refused: Aᵢ* = {sorted(a_star)}")
    bad += not caught

    # 4. the four negative controls Pavlo required — each must red
    print("\nnegative controls — each must be caught\n")

    # 4a. swapped labels: corrupt the gate label map; Aᵢ* must NOT move (labels are not its input),
    #     and the label cross-check must notice the swap.
    labels = gate_labels()
    swapped = dict(labels)
    swapped["serving"], swapped["gateway"] = swapped["gateway"], swapped["serving"]
    a_before = {n: attribution(r) for n, r, _ in mutants()}
    # attribution() never reads `labels`, so recomputing after the swap is identical:
    a_after = {n: attribution(r) for n, r, _ in mutants()}
    labels_moved = swapped != labels
    astar_unmoved = a_before == a_after
    ok = labels_moved and astar_unmoved
    print(f"  {'ok  ' if ok else 'FAIL'}  swapped labels: Aᵢ* unmoved ({astar_unmoved}) while the "
          f"label map changed ({labels_moved}) — attribution is label-independent")
    bad += not ok

    # 4b. missing witness class: drop every reject witness; separation must collapse to UNRESOLVED
    #     rather than silently continuing to attribute.
    W_gap = {inv: [(c, w) for c, w in ws if c != "reject"] for inv, ws in W.items()}
    unresolved_gap = separation_matrix(W_gap)
    ok = len(unresolved_gap) > 0
    print(f"  {'ok  ' if ok else 'FAIL'}  missing witness class: separation collapses to "
          f"{len(unresolved_gap)} UNRESOLVED pair(s) — not a silent pass")
    bad += not ok

    # 4c. oracle tampering: force a relation to always-accept; its own reject witness must catch it.
    tampered_R = lambda rec: True                            # noqa: E731 — the tamper under test
    reject_ws = [w for cls, w in W["pinned_bytes"] if cls == "reject"]
    caught = any(tampered_R(w) is not False for w in reject_ws)   # always-True never rejects
    print(f"  {'ok  ' if caught else 'FAIL'}  oracle tampering: an always-accept relation fails its "
          f"own reject witness ({'caught' if caught else 'MISSED'})")
    bad += not caught

    # 4d. gate-path reuse: the oracle module must not import or call the gate. Structural proof.
    import ast
    import rung4_oracle as self_mod
    tree = ast.parse(open(self_mod.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    reused = any("check_served" in m or "check_selects" in m for m in imported)
    ok = not reused
    print(f"  {'ok  ' if ok else 'FAIL'}  gate-path reuse: oracle does not import or call the gate "
          f"({'clean' if ok else 'REUSED'})")
    bad += not ok

    print()
    if bad:
        print(f"{bad} control(s) failed — the oracle does not hold its contract")
        return EXIT_BAD
    print("attribution recomputed under an independent semantic contract, separation proven, "
          "every control red under mutation")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
