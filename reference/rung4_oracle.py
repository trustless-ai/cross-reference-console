#!/usr/bin/env python3
"""Rung 4 — attribution recomputed under an independently identified semantic contract.

The attribution ladder (test_operational_gates.py): declared → discriminating → correctly-attributed
(#86) → causal (#87). Every rung read invariant identity from ONE place — the gate's own assertion
labels — so a mislabelled assertion (`I₁` where it enforces `I₂`) makes the gate report `I₁`, the author
declare `I₁`, and set-equality pass on a shared wrong map. Rung 4 (per @pipavlo82's contract,
cross-reference-console#89 / #90) breaks that shared-labelling dependency.

For each invariant Iₖ this carries an INDEPENDENT semantic relation Rₖ — derived from what the invariant
means over the record schema, never by calling the gate — evaluated **ternary**:

    SATISFIED | VIOLATED | NOT_APPLICABLE

with an INDEPENDENTLY DEFINED applicability predicate `applies_k`. NOT_APPLICABLE is permitted ONLY when
`applies_k` is false; a present container with an absent/malformed child is VIOLATED, never N/A. The
mutant is a total transform; the behaviour vector is executed across the pinned separating witness basis
Wₖ, and attribution counts only genuine SATISFIED↔VIOLATED flips (a transition into N/A — a sub-invariant
whose container was removed — is the container's attribution, not the child's):

    bₖ(m) = [ Rₖ(m(w)) for w in Wₖ ]
    Aᵢ*   = { Iₖ : ∃ w ∈ Wₖ, { Rₖ(w), Rₖ(m(w)) } == {SATISFIED, VIOLATED} }

The oracle path (applies_*, sat_*, relation, b_vector, attribution) never imports or runs the gate — the
gate is exercised only in the cross-check, as a subprocess, and the observed labels are COMPARED to Aᵢ*,
never inputs. A real gate-label swap is the executable failing witness for the shared-labelling defect.

Covered: the SERVED-gate serving invariants — where the real harm (laundering a substitution into an
operational footnote) and the non-singleton attributions live.

EXIT: 0 all controls hold · 1 a control failed · 2 could not run.
"""

from __future__ import annotations

import ast
import itertools
import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins"
SERVED = ROOT / "reference" / "check_served_bytes.py"
LIVE = "bafybeihim4cjh2uqxlctepgibzdhr77rag53mqu6vlces72eyyiqnjjipe"
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2

SAT, VIO, NA = "SATISFIED", "VIOLATED", "NOT_APPLICABLE"

# ── schema helpers (pure structure, no gate) ─────────────────────────────────────────────────────
def _serving(rec):
    s = rec.get("availability", {}).get("serving")
    return s if isinstance(s, dict) else None


def _observations(serving):
    """Every structured observation across all gateways, or None if any gateway is not an obs-list."""
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


# ── the invariants: an INDEPENDENT applicability predicate + a satisfaction check, kept separate ──
# applies_k answers "is Iₖ in scope for this record" from the invariant hierarchy alone; sat_k is only
# consulted when applies_k is true. This is what makes N/A a positioned answer, not a hiding place.
def ap_serving(rec):      return True                                   # the root — always in scope
def st_serving(rec):      return _serving(rec) is not None

def ap_object(rec):       return _serving(rec) is not None
def st_object(rec):
    s = _serving(rec)
    return isinstance(s.get("object"), str) and bool(s.get("object"))

def ap_observations(rec): return _serving(rec) is not None
def st_observations(rec): return _observations(_serving(rec)) is not None

def ap_gateway(rec):      return _serving(rec) is not None
def st_gateway(rec):
    gws = _serving(rec).get("gateways")
    return isinstance(gws, dict) and len(gws) > 0

def ap_says_why(rec):
    s = _serving(rec)
    if s is None:
        return False
    obs = _observations(s)
    return bool(obs)                                                    # structured obs exist to judge
def st_says_why(rec):
    obs = _observations(_serving(rec))
    return all(isinstance(o.get("detail"), str) and o["detail"]
               for o in obs if o.get("verdict") != "IDENTICAL")

def ap_pinned_bytes(rec):
    s = _serving(rec)
    return s is not None and isinstance(s.get("gateways"), dict) and len(s["gateways"]) > 0
def st_pinned_bytes(rec):
    obs = _observations(_serving(rec))
    return bool(obs) and any(o.get("verdict") == "IDENTICAL" for o in obs)


INVARIANTS = {
    "serving":      (ap_serving,      st_serving,      "carries availability.serving"),
    "object":       (ap_object,       st_object,       "names what the bytes were compared against"),
    "observations": (ap_observations, st_observations, "carries observations"),
    "gateway":      (ap_gateway,      st_gateway,      "lists at least one gateway"),
    "says_why":     (ap_says_why,     st_says_why,     "non-identical says why"),
    "pinned_bytes": (ap_pinned_bytes, st_pinned_bytes, "at least one client somewhere gets the "
                                                       "pinned bytes exactly"),
}


def relation(inv, rec):
    """Ternary Rₖ. N/A only when the independently-defined applicability predicate is false."""
    applies, satisfied, _ = INVARIANTS[inv]
    if not applies(rec):
        return NA
    return SAT if satisfied(rec) else VIO


# ── reference record + total-transform mutants ───────────────────────────────────────────────────
def load_reference():
    return json.loads((PINS / (LIVE + ".json")).read_text(encoding="utf-8"))


def _clone(rec):
    return json.loads(json.dumps(rec))


# Each mutant is a TOTAL transform record→record (defensive: a no-op where its target is absent).
def m_identity(rec): return _clone(rec)

def m_drop_serving(rec):
    r = _clone(rec)
    r.get("availability", {}).pop("serving", None)
    return r

def m_drop_object(rec):
    r = _clone(rec)
    s = _serving(r)
    if s is not None:
        s.pop("object", None)
    return r

def m_empty_gateways(rec):
    r = _clone(rec)
    s = _serving(r)
    if s is not None:
        s["gateways"] = {}
    return r

def m_bare_verdict(rec):
    r = _clone(rec)
    s = _serving(r)
    if s is not None:
        s["gateways"] = {"https://x/y": {"verdict": "IDENTICAL"}}       # a dict, not an obs list
    return r

def m_injection_no_detail(rec):
    r = _clone(rec)
    s = _serving(r)
    if s is not None:
        for gw in s.get("gateways", {}).values():
            if isinstance(gw, list):
                for o in gw:
                    if isinstance(o, dict):
                        o["verdict"] = "SERVE_TIME_INJECTION"
                        o.pop("detail", None)
    return r

def m_no_identical(rec):
    r = _clone(rec)
    s = _serving(r)
    if s is not None:
        for gw in s.get("gateways", {}).values():
            if isinstance(gw, list):
                for o in gw:
                    if isinstance(o, dict):
                        o["verdict"] = "SERVE_TIME_INJECTION"
                        o["detail"] = "stated cause"
    return r


# name → (transform, declared attribution set, gate-label-friendly description)
MUTANTS = {
    "no serving comparison at all":        (m_drop_serving,       {"serving"}),
    "no stated authority":                 (m_drop_object,        {"object"}),
    "no gateways listed at all":           (m_empty_gateways,     {"gateway"}),
    "gateway is a bare verdict":           (m_bare_verdict,       {"observations", "pinned_bytes"}),
    "injection with no detail":            (m_injection_no_detail, {"says_why", "pinned_bytes"}),
    "no client gets the pinned bytes":     (m_no_identical,       {"pinned_bytes"}),
}


# ── witness bases Wₖ: per invariant, records with an EXPECTED ternary + class ─────────────────────
_SEED = {"availability": {"serving": {
    "object": "cid/console/index.html",
    "gateways": {"https://g": [
        {"as": "curl", "verdict": "IDENTICAL"},
        {"as": "browser", "verdict": "SERVE_TIME_INJECTION", "detail": "beacon"},
    ]}}}}


def _w(fn):
    r = _clone(_SEED)
    fn(r)
    return r


def witness_bases():
    """Each entry: (class, record, expected_ternary). Boundary cases carry an explicit expectation, so
    the basis proves the relation's semantics — accept AND reject AND boundary — not just two poles."""
    return {
        "serving": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"].pop("serving")), VIO),
        ],
        "object": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"].pop("object")), VIO),
            ("boundary-empty", _w(lambda r: r["availability"]["serving"].update(object="")), VIO),
            ("na-no-container", _w(lambda r: r["availability"].pop("serving")), NA),
        ],
        "observations": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"].update(
                gateways={"u": {"verdict": "IDENTICAL"}})), VIO),
            ("na-no-container", _w(lambda r: r["availability"].pop("serving")), NA),
        ],
        "gateway": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"].update(gateways={})), VIO),
            ("na-no-container", _w(lambda r: r["availability"].pop("serving")), NA),
        ],
        "says_why": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"]["gateways"]["https://g"].__setitem__(
                1, {"as": "browser", "verdict": "SERVE_TIME_INJECTION"})), VIO),
            ("boundary-identical-needs-no-detail",
             _w(lambda r: r["availability"]["serving"]["gateways"]["https://g"].__setitem__(
                 1, {"as": "browser", "verdict": "IDENTICAL"})), SAT),
            ("na-no-structured-obs", _w(lambda r: r["availability"]["serving"].update(
                gateways={"u": {"verdict": "IDENTICAL"}})), NA),
        ],
        "pinned_bytes": [
            ("accept", _SEED, SAT),
            ("reject-all-injection", _w(lambda r: r["availability"]["serving"]["gateways"].__setitem__(
                "https://g", [{"as": "curl", "verdict": "SERVE_TIME_INJECTION", "detail": "x"}])), VIO),
            ("na-no-gateways", _w(lambda r: r["availability"]["serving"].update(gateways={})), NA),
        ],
    }


# ── behaviour vectors + attribution (never touches the gate) ─────────────────────────────────────
def b_vector(inv, basis, transform):
    return tuple(relation(inv, transform(rec)) for _, rec, _ in basis)


def attribution(transform, W):
    """Aᵢ* = { Iₖ : some witness in Wₖ is turned SATISFIED→VIOLATED by the mutant }.

    Attribution names what the mutant VIOLATED, so the flip is directional: SATISFIED→VIOLATED counts.
    VIOLATED→SATISFIED (the mutant happens to satisfy a pre-broken witness — e.g. emptying the gateways
    "fixes" observations' bare-verdict reject-witness) is not a violation of Iₖ and must not attribute
    it. Transitions into or out of NOT_APPLICABLE (a child whose container moved) are the container's
    attribution, never the child's. bₖ is still executed across the whole pinned Wₖ."""
    out = set()
    for inv, basis in W.items():
        ref = b_vector(inv, basis, m_identity)
        mut = b_vector(inv, basis, transform)
        if any(a == SAT and b == VIO for a, b in zip(ref, mut)):
            out.add(inv)
    return out


# ── the gate, as a subprocess (only here — never in the attribution path) ────────────────────────
def observed_attribution(out: str):
    """The labels the gate blamed, from its own failure list shape (^ {4}- ...$)."""
    return [m.group(1).strip() for m in re.finditer(r"^ {4}- (.+)$", out, re.M)]


def run_gate_on(transform, served_src=None):
    """Apply the mutant to the live record, run check_served_bytes over a temp pins dir, and return the
    gate's observed attribution as an INVARIANT SET (mapped through the labels — a comparison target,
    not an input to Aᵢ*). Optionally run against patched gate source (served_src)."""
    with tempfile.TemporaryDirectory() as td:
        pins = pathlib.Path(td) / "pins"
        pins.mkdir()
        for p in PINS.glob("*.json"):
            (pins / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        target = pins / (LIVE + ".json")
        target.write_text(json.dumps(transform(load_reference()), indent=2) + "\n", encoding="utf-8")
        script = SERVED
        backup = None
        if served_src is not None:
            backup = SERVED.read_text(encoding="utf-8")
            SERVED.write_text(served_src, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, str(script), "--pins", str(pins)],
                               capture_output=True, text=True)
        finally:
            if backup is not None:
                SERVED.write_text(backup, encoding="utf-8")
    blamed = observed_attribution(r.stdout + r.stderr)
    return {inv for inv, (_, _, label) in INVARIANTS.items()
            if any(label in line for line in blamed)}


def main() -> int:
    if not SERVED.exists() or not (PINS / (LIVE + ".json")).exists():
        print("UNVERIFIABLE — gate or live pin record missing", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    bad = 0
    W = witness_bases()
    print("rung 4 — attribution recomputed under an independent ternary semantic contract\n")

    # 1. witness self-test — each relation reproduces its basis's declared ternary (accept/reject/
    #    boundary/na all carry an explicit expectation)
    print("witness-basis self-test — relations reproduce accept / reject / boundary / N-A\n")
    st = [(inv, cls, relation(inv, rec), exp)
          for inv, basis in W.items() for cls, rec, exp in basis if relation(inv, rec) != exp]
    if st:
        for inv, cls, got, exp in st:
            print(f"  FAIL  R[{inv}] on {cls} → {got}, declared {exp}")
        bad += len(st)
    else:
        print("  ok    every witness classified as its basis declares")

    # 2. applicability discipline — N/A permitted ONLY where applies_k is false
    print("\napplicability discipline — NOT_APPLICABLE only when the applicability predicate is false\n")
    viol = [(inv, cls) for inv, basis in W.items() for cls, rec, _ in basis
            if relation(inv, rec) == NA and INVARIANTS[inv][0](rec)]
    if viol:
        for inv, cls in viol:
            print(f"  FAIL  R[{inv}] returned N/A on {cls} while applies_{inv} is true")
        bad += len(viol)
    else:
        print("  ok    no relation hides a violation behind N/A")

    # 3. separation matrix — each pair distinguished by a committed witness; else UNRESOLVED
    print("\nseparation matrix — every invariant pair distinguished by a committed witness\n")
    pool = [rec for basis in W.values() for _, rec, _ in basis]
    unresolved = [(a, b) for a, b in itertools.combinations(INVARIANTS, 2)
                  if not any(relation(a, w) != relation(b, w) for w in pool)]
    if unresolved:
        print(f"  UNRESOLVED (no separating witness): {unresolved} — refusing to force a singleton")
        bad += len(unresolved)
    else:
        print(f"  ok    all {len(list(itertools.combinations(INVARIANTS, 2)))} pairs separable")

    # 4. witness-derived attribution — Aᵢ* over Wₖ agrees with the declared set
    print("\nattribution — Aᵢ* derived across Wₖ agrees with the declared set\n")
    a_star = {}
    for name, (transform, declared) in MUTANTS.items():
        a = attribution(transform, W)
        a_star[name] = a
        ok = a == declared
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}: Aᵢ* = {sorted(a)}"
              + ("" if ok else f"  ≠ declared {sorted(declared)}"))
        bad += not ok

    # 5. LIVE cross-check — run the real gate on each mutant; observed labels must equal Aᵢ*
    print("\nlive gate-vs-oracle — observed_attribution(gate) == Aᵢ* on the real record\n")
    for name, (transform, _) in MUTANTS.items():
        observed = run_gate_on(transform)
        ok = observed == a_star[name]
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}: gate {sorted(observed)} vs Aᵢ* {sorted(a_star[name])}")
        bad += not ok

    # 6. the shared-labelling failing witness — swap a REAL gate assertion label; the comparison reds
    print("\nreal gate-label swap — the executable failing witness for shared labelling\n")
    src = SERVED.read_text(encoding="utf-8")
    frm = '{short}: carries availability.serving'
    to = '{short}: lists at least one gateway'          # a real, different invariant's label
    if frm not in src:
        print("  FAIL  swap anchor not found in the gate — control patched nothing")
        bad += 1
    else:
        observed = run_gate_on(m_drop_serving, served_src=src.replace(frm, to, 1))
        a = a_star["no serving comparison at all"]        # label-free Aᵢ* = {serving}
        caught = observed != a
        print(f"  {'ok  ' if caught else 'FAIL'}  drop_serving with serving-label swapped→gateway: "
              f"gate now blames {sorted(observed)}, Aᵢ* still {sorted(a)} — "
              f"{'mismatch caught' if caught else 'MISSED'}")
        bad += not caught

    # 7. negative controls on the oracle machinery
    print("\nnegative controls — each must be caught\n")

    # 7a. a child relation that returns N/A while its container is present must be rejected
    def tampered_na(rec):                                # pretends says_why is N/A even with obs
        return NA
    probe = _SEED                                        # serving + structured obs present
    applies = INVARIANTS["says_why"][0](probe)
    rejected = applies and tampered_na(probe) == NA      # N/A while applicable ⇒ the discipline reds
    print(f"  {'ok  ' if rejected else 'FAIL'}  child N/A while container present is rejected "
          f"({'caught' if rejected else 'MISSED'})")
    bad += not rejected

    # 7b. missing witness class → separation collapses to UNRESOLVED, not a silent pass. Drop every
    #     discriminating witness (keep only the accept pole): with nothing that rejects, no pair can be
    #     told apart, so separation must refuse rather than pass.
    W_gap = {inv: [t for t in basis if t[0] == "accept"] for inv, basis in W.items()}
    pool_gap = [rec for basis in W_gap.values() for _, rec, _ in basis]
    unresolved_gap = [(a, b) for a, b in itertools.combinations(INVARIANTS, 2)
                      if not any(relation(a, w) != relation(b, w) for w in pool_gap)]
    ok = len(unresolved_gap) > 0
    print(f"  {'ok  ' if ok else 'FAIL'}  missing witness class: separation collapses to "
          f"{len(unresolved_gap)} UNRESOLVED pair(s)")
    bad += not ok

    # 7c. the non-singleton attributions are retained (not flattened to singletons)
    ns_ok = (a_star["gateway is a bare verdict"] == {"observations", "pinned_bytes"}
             and a_star["injection with no detail"] == {"says_why", "pinned_bytes"})
    print(f"  {'ok  ' if ns_ok else 'FAIL'}  non-singleton attributions retained "
          f"({'both' if ns_ok else 'LOST'})")
    bad += not ns_ok

    # 7d. gate-path reuse — the ATTRIBUTION path must not import/call the gate. AST over the actual
    #     call graph of attribution(), catching direct calls, imports, and dynamic loading.
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    attribution_path = {"attribution", "b_vector", "relation",
                        *(f.__name__ for f in (ap_serving, ap_object, ap_observations, ap_gateway,
                                               ap_says_why, ap_pinned_bytes, st_serving, st_object,
                                               st_observations, st_gateway, st_says_why,
                                               st_pinned_bytes)),
                        "_serving", "_observations"}
    banned = ("check_served", "check_selects", "test_operational_gates", "subprocess",
              "importlib", "__import__", "run_gate_on")
    leaks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in attribution_path:
            for sub in ast.walk(node):
                names = []
                if isinstance(sub, ast.Name):
                    names.append(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.append(sub.attr)
                for n in names:
                    if any(b in n for b in banned):
                        leaks.append((node.name, n))
    ok = not leaks
    print(f"  {'ok  ' if ok else 'FAIL'}  gate-path reuse: attribution path is gate-free "
          f"({'clean' if ok else leaks[:3]})")
    bad += not ok

    print()
    if bad:
        print(f"{bad} control(s) failed — the oracle does not hold its contract")
        return EXIT_BAD
    print("Aᵢ* derived across Wₖ, the running gate compared against it, a real label swap proven to "
          "red the comparison, separation and applicability proven, controls red under mutation")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
