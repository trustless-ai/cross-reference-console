#!/usr/bin/env python3
"""Rung 4 — the PURE semantic oracle. Attribution recomputed under an independently identified
semantic contract, with NO dependency on the gate.

This module deliberately imports nothing that can reach the gate (no check_served_bytes,
check_selects_authoritative, test_operational_gates, subprocess, or importlib). That is what makes the
gate-isolation proof a real call-graph fact rather than a substring guess: rung4_crosscheck.py parses
this file's imports and refuses any gate/subprocess reference, so an aliased `from check_served_bytes
import classify as g` could not hide here — it would be a module-level import and get flagged. The gate
is exercised only in the runner, and its observed attribution is COMPARED to Aᵢ*, never an input.

Contract (per @pipavlo82, cross-reference-console#89/#90):
- ternary relations SATISFIED | VIOLATED | NOT_APPLICABLE, each with an INDEPENDENTLY defined
  applicability predicate; N/A only when applicability is false; a present container with an
  absent/malformed child is VIOLATED, never N/A;
- bₖ(m) = [Rₖ(m(w)) for w in Wₖ] over the pinned basis; attribution counts only SATISFIED → VIOLATED
  flips (what the mutant BROKE) — VIOLATED→SATISFIED (a mutant satisfying a pre-broken witness) and any
  transition into/out of N/A (a child whose container moved) do not attribute;
- each invariant's basis must carry its REQUIRED witness classes (per-basis completeness proven before
  the global pairwise separation matrix);
- UNRESOLVED where applicability or separation cannot be established.

Run directly for the pure self-tests (no gate). The live gate-vs-oracle comparison lives in
rung4_crosscheck.py. EXIT: 0 ok · 1 a control failed.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins"
LIVE = "bafybeihim4cjh2uqxlctepgibzdhr77rag53mqu6vlces72eyyiqnjjipe"

SAT, VIO, NA = "SATISFIED", "VIOLATED", "NOT_APPLICABLE"


# ── schema helpers (pure structure) ──────────────────────────────────────────────────────────────
def _serving(rec):
    s = rec.get("availability", {}).get("serving")
    return s if isinstance(s, dict) else None


def _observations(serving):
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


# ── invariants: independent applicability predicate + satisfaction, composed into a ternary Rₖ ────
def ap_serving(rec):      return True
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
    return s is not None and bool(_observations(s))
def st_says_why(rec):
    return all(isinstance(o.get("detail"), str) and o["detail"]
               for o in _observations(_serving(rec)) if o.get("verdict") != "IDENTICAL")

def ap_pinned_bytes(rec):
    s = _serving(rec)
    return s is not None and isinstance(s.get("gateways"), dict) and len(s["gateways"]) > 0
def st_pinned_bytes(rec):
    obs = _observations(_serving(rec))
    return bool(obs) and any(o.get("verdict") == "IDENTICAL" for o in obs)


def make_relation(applies, satisfied):
    """A ternary relation as a first-class function. N/A is emitted ONLY when applies is false — the
    discipline a tampered relation (one returning N/A while applicable) must be caught violating."""
    def R(rec):
        if not applies(rec):
            return NA
        return SAT if satisfied(rec) else VIO
    return R


# inv → (applies_fn, relation_fn, label, required_witness_classes)
def _build():
    spec = {
        "serving":      (ap_serving,      st_serving,      "carries availability.serving",
                         {"accept", "reject"}),
        "object":       (ap_object,       st_object,       "names what the bytes were compared against",
                         {"accept", "reject", "boundary", "na"}),
        "observations": (ap_observations, st_observations, "carries observations",
                         {"accept", "reject", "na"}),
        "gateway":      (ap_gateway,      st_gateway,      "lists at least one gateway",
                         {"accept", "reject", "na"}),
        "says_why":     (ap_says_why,     st_says_why,     "non-identical says why",
                         {"accept", "reject", "boundary", "na"}),
        "pinned_bytes": (ap_pinned_bytes, st_pinned_bytes, "at least one client somewhere gets the "
                         "pinned bytes exactly", {"accept", "reject", "na"}),
    }
    return {inv: (ap, make_relation(ap, st), label, req) for inv, (ap, st, label, req) in spec.items()}


INVARIANTS = _build()


def relation(inv, rec, invariants=None):
    return (invariants or INVARIANTS)[inv][1](rec)


def label_of(inv):
    return INVARIANTS[inv][2]


# ── reference record + total-transform mutants ───────────────────────────────────────────────────
def load_reference():
    return json.loads((PINS / (LIVE + ".json")).read_text(encoding="utf-8"))


def _clone(rec):
    return json.loads(json.dumps(rec))


def m_identity(rec): return _clone(rec)

def m_drop_serving(rec):
    r = _clone(rec); r.get("availability", {}).pop("serving", None); return r

def m_drop_object(rec):
    r = _clone(rec); s = _serving(r)
    if s is not None: s.pop("object", None)
    return r

def m_empty_gateways(rec):
    r = _clone(rec); s = _serving(r)
    if s is not None: s["gateways"] = {}
    return r

def m_bare_verdict(rec):
    r = _clone(rec); s = _serving(r)
    if s is not None: s["gateways"] = {"https://x/y": {"verdict": "IDENTICAL"}}
    return r

def m_injection_no_detail(rec):
    r = _clone(rec); s = _serving(r)
    if s is not None:
        for gw in s.get("gateways", {}).values():
            if isinstance(gw, list):
                for o in gw:
                    if isinstance(o, dict):
                        o["verdict"] = "SERVE_TIME_INJECTION"; o.pop("detail", None)
    return r

def m_no_identical(rec):
    r = _clone(rec); s = _serving(r)
    if s is not None:
        for gw in s.get("gateways", {}).values():
            if isinstance(gw, list):
                for o in gw:
                    if isinstance(o, dict):
                        o["verdict"] = "SERVE_TIME_INJECTION"; o["detail"] = "stated cause"
    return r


MUTANTS = {
    "no serving comparison at all":    (m_drop_serving,        {"serving"}),
    "no stated authority":             (m_drop_object,         {"object"}),
    "no gateways listed at all":       (m_empty_gateways,      {"gateway"}),
    "gateway is a bare verdict":       (m_bare_verdict,        {"observations", "pinned_bytes"}),
    "injection with no detail":        (m_injection_no_detail, {"says_why", "pinned_bytes"}),
    "no client gets the pinned bytes": (m_no_identical,        {"pinned_bytes"}),
}


# ── witness bases: (class, record, expected ternary) ─────────────────────────────────────────────
_SEED = {"availability": {"serving": {
    "object": "cid/console/index.html",
    "gateways": {"https://g": [
        {"as": "curl", "verdict": "IDENTICAL"},
        {"as": "browser", "verdict": "SERVE_TIME_INJECTION", "detail": "beacon"},
    ]}}}}


def _w(fn):
    r = _clone(_SEED); fn(r); return r


def witness_bases():
    return {
        "serving": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"].pop("serving")), VIO),
        ],
        "object": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"].pop("object")), VIO),
            ("boundary", _w(lambda r: r["availability"]["serving"].update(object="")), VIO),
            ("na", _w(lambda r: r["availability"].pop("serving")), NA),
        ],
        "observations": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"].update(
                gateways={"u": {"verdict": "IDENTICAL"}})), VIO),
            ("na", _w(lambda r: r["availability"].pop("serving")), NA),
        ],
        "gateway": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"].update(gateways={})), VIO),
            ("na", _w(lambda r: r["availability"].pop("serving")), NA),
        ],
        "says_why": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"]["gateways"]["https://g"].__setitem__(
                1, {"as": "browser", "verdict": "SERVE_TIME_INJECTION"})), VIO),
            ("boundary", _w(lambda r: r["availability"]["serving"]["gateways"]["https://g"].__setitem__(
                1, {"as": "browser", "verdict": "IDENTICAL"})), SAT),
            ("na", _w(lambda r: r["availability"]["serving"].update(
                gateways={"u": {"verdict": "IDENTICAL"}})), NA),
        ],
        "pinned_bytes": [
            ("accept", _SEED, SAT),
            ("reject", _w(lambda r: r["availability"]["serving"]["gateways"].__setitem__(
                "https://g", [{"as": "curl", "verdict": "SERVE_TIME_INJECTION", "detail": "x"}])), VIO),
            ("na", _w(lambda r: r["availability"]["serving"].update(gateways={})), NA),
        ],
    }


def basis_completeness(W, invariants=None):
    """Per-invariant: the committed basis must carry every REQUIRED witness class. Proven before the
    global pairwise matrix, so a pool that happens to separate can't paper over a missing class."""
    inv = invariants or INVARIANTS
    missing = []
    for name, (_, _, _, required) in inv.items():
        have = {cls for cls, _, _ in W.get(name, [])}
        for cls in required - have:
            missing.append((name, cls))
    return missing


# ── behaviour vectors + directional attribution ──────────────────────────────────────────────────
def b_vector(inv, basis, transform, invariants=None):
    return tuple(relation(inv, transform(rec), invariants) for _, rec, _ in basis)


def attribution(transform, W, invariants=None):
    """Aᵢ* = { Iₖ : some witness in Wₖ is turned SATISFIED→VIOLATED by the mutant }. Directional: what
    the mutant BROKE. VIOLATED→SATISFIED and transitions into/out of NOT_APPLICABLE do not attribute."""
    out = set()
    for inv, basis in W.items():
        ref = b_vector(inv, basis, m_identity, invariants)
        mut = b_vector(inv, basis, transform, invariants)
        if any(a == SAT and b == VIO for a, b in zip(ref, mut)):
            out.add(inv)
    return out


def separation_matrix(W, invariants=None):
    inv = invariants or INVARIANTS
    pool = [rec for basis in W.values() for _, rec, _ in basis]
    return [(a, b) for a, b in itertools.combinations(inv, 2)
            if not any(relation(a, w, inv) != relation(b, w, inv) for w in pool)]


def validate_applicability(invariants, W):
    """N/A permitted ONLY where applies_k is false. Returns violations. Runs against ANY invariants
    map, so a tampered relation (returning N/A while applicable) can be injected and must be caught."""
    bad = []
    for inv, (applies, R, _, _) in invariants.items():
        for cls, rec, _ in W.get(inv, []):
            if applies(rec) and R(rec) == NA:
                bad.append((inv, cls))
    return bad


def main() -> int:
    bad = 0
    W = witness_bases()
    print("rung 4 — PURE semantic oracle (no gate)\n")

    print("witness-basis self-test — relations reproduce accept / reject / boundary / N-A\n")
    st = [(inv, cls, relation(inv, rec), exp)
          for inv, basis in W.items() for cls, rec, exp in basis if relation(inv, rec) != exp]
    for inv, cls, got, exp in st:
        print(f"  FAIL  R[{inv}] on {cls} → {got}, declared {exp}")
    bad += len(st) or print("  ok    every witness classified as its basis declares") or 0

    print("\nper-invariant basis completeness — each basis carries its required witness classes\n")
    miss = basis_completeness(W)
    for inv, cls in miss:
        print(f"  FAIL  basis[{inv}] missing required class '{cls}'")
    bad += len(miss) or print("  ok    every basis complete") or 0

    print("\napplicability discipline — N/A only where the applicability predicate is false\n")
    viol = validate_applicability(INVARIANTS, W)
    for inv, cls in viol:
        print(f"  FAIL  R[{inv}] returned N/A on {cls} while applies_{inv} is true")
    bad += len(viol) or print("  ok    no relation hides a violation behind N/A") or 0

    print("\nseparation matrix — every invariant pair distinguished by a committed witness\n")
    unresolved = separation_matrix(W)
    if unresolved:
        print(f"  UNRESOLVED (no separating witness): {unresolved}"); bad += len(unresolved)
    else:
        print(f"  ok    all {len(list(itertools.combinations(INVARIANTS, 2)))} pairs separable")

    print("\nattribution — Aᵢ* derived across Wₖ agrees with the declared set\n")
    for name, (transform, declared) in MUTANTS.items():
        a = attribution(transform, W)
        ok = a == declared
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}: Aᵢ* = {sorted(a)}"
              + ("" if ok else f"  ≠ {sorted(declared)}"))
        bad += not ok

    print("\nnegative controls (pure) — each must be caught\n")

    # per-invariant missing class → completeness must flag it (one invariant at a time)
    caught_all = True
    for inv in INVARIANTS:
        for cls in list(INVARIANTS[inv][3]):
            W_gap = {k: ([t for t in v if t[0] != cls] if k == inv else v) for k, v in W.items()}
            if not any(m == (inv, cls) for m in basis_completeness(W_gap)):
                caught_all = False
                print(f"  FAIL  dropping {inv}/{cls} was NOT flagged by completeness")
    print("  ok    per-invariant: dropping any required class is flagged" if caught_all else "")
    bad += not caught_all

    # inject a tampered relation (N/A while applicable) into the REAL validator → must fail
    tampered = dict(INVARIANTS)
    ap = INVARIANTS["says_why"][0]
    tampered["says_why"] = (ap, lambda rec: NA, INVARIANTS["says_why"][2], INVARIANTS["says_why"][3])
    inj = validate_applicability(tampered, W)
    ok = any(inv == "says_why" for inv, _ in inj)
    print(f"  {'ok  ' if ok else 'FAIL'}  injected N/A-while-applicable relation is rejected by the "
          f"validator ({'caught' if ok else 'MISSED'})")
    bad += not ok

    # non-singletons retained
    ns = (attribution(m_bare_verdict, W) == {"observations", "pinned_bytes"}
          and attribution(m_injection_no_detail, W) == {"says_why", "pinned_bytes"})
    print(f"  {'ok  ' if ns else 'FAIL'}  non-singleton attributions retained ({'both' if ns else 'LOST'})")
    bad += not ns

    print()
    print("pure oracle holds its contract" if not bad else f"{bad} control(s) failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
