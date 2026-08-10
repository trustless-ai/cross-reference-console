#!/usr/bin/env python3
"""Lineage resolution and transitivity — CELL-v3.md §4, made executable.

§4 marks its own normative prose `[PENDING-VECTOR]` until the matching rows in
`docs/VECTOR-MATRIX-v3-independence.md` run in CI. This module is what closes
that: the graph, the transitive closure, and the pair states the spec names.

## What it answers, and what it deliberately does not

`check_lane_distinctness.py` answers the **necessary** question — are these two
Cells even capable of being distinct lanes (different implementation, different
repo, no shared runtime or lock). This module answers the **sufficient** one —
given declared lineage, are they *actually* independent, derived, or unproven.

It never upgrades a pair. A pair that fails the necessary conditions stays
NOT_DISTINCT no matter how clean its lineage looks; declaring `derived_from: []`
on a copy of someone else's implementation does not make it independent. Lineage
can only ever *demote* — which is the direction that matters, because the
attractive lie is "we are independent", never "we are derived".

## The states (§4.3, §4.4)

    INDEPENDENT              both v3, both declared, no shared ancestry
    DERIVED                  one reachable from the other, or shared ancestor
    INDEPENDENCE_NOT_PROVEN  cycle, unresolved ref, or any pre-v3 cell in the pair

`INDEPENDENCE_NOT_PROVEN` is not a failure and not a pass. It is the honest
answer when the graph cannot establish the thing being asked, and collapsing it
toward either neighbour is how this whole mechanism would quietly stop meaning
anything.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lineage_ref import LineageRefError, parse  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

INDEPENDENT = "INDEPENDENT"
DERIVED = "DERIVED"
NOT_PROVEN = "INDEPENDENCE_NOT_PROVEN"


def node_key(independence: dict) -> str:
    """§4.2 — impl_hash when present, else the (repo, commit, path) tuple."""
    impl = (independence or {}).get("implementation") or {}
    if impl.get("impl_hash"):
        return impl["impl_hash"]
    return "|".join(str(impl.get(k, "")) for k in ("repo", "commit", "path"))


def _resolve(ref: str, by_hash: dict, by_tuple: dict):
    """LineageRef -> node key present in the graph, or None if it resolves to nothing.

    Returning None is load-bearing: §4.2 says an unresolved ref marks the node
    `lineage_unresolved` and MUST NOT invent a target. A resolver that silently
    dropped unknown refs would turn "I cited an ancestor you cannot see" into
    "I cited nothing", which is the difference between unproven and independent.
    """
    try:
        p = parse(ref)
    except LineageRefError:
        return None
    if p["kind"] == "impl":
        return p["impl_hash"] if p["impl_hash"] in by_hash else None
    key = "|".join((p["url"], p["commit"], p["path"]))
    return key if key in by_tuple else None


def build_graph(cells: list) -> dict:
    """cells: [(node_id, payload)] on ONE claim. Returns the lineage graph."""
    nodes, by_hash, by_tuple = {}, {}, {}
    for node_id, pp in cells:
        ind = (pp.get("evidence") or {}).get("independence") or {}
        k = node_key(ind)
        nodes[k] = {"node_id": node_id, "schema": pp.get("schema"),
                    "result": pp.get("result"), "independence": ind,
                    "derived_from": ind.get("derived_from"), "edges": set(),
                    "unresolved": False}
        impl = ind.get("implementation") or {}
        if impl.get("impl_hash"):
            by_hash[impl["impl_hash"]] = k
        by_tuple["|".join(str(impl.get(x, "")) for x in ("repo", "commit", "path"))] = k

    for k, n in nodes.items():
        df = n["derived_from"]
        if df is None:          # pre-v3: field absent entirely
            continue
        for ref in df:
            t = _resolve(ref, by_hash, by_tuple)
            if t is None:
                n["unresolved"] = True   # §4.2 — do not invent targets
            elif t != k:
                n["edges"].add(t)
    return nodes


def ancestors(graph: dict, start: str) -> set:
    """§4.3 — transitive closure over derived_from edges. Cycle-safe by construction."""
    seen, stack = set(), list(graph.get(start, {}).get("edges", ()))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.get(cur, {}).get("edges", ()))
    return seen


def in_cycle(graph: dict, a: str, b: str) -> bool:
    """§4.4 — a multi-node cycle containing both, i.e. each reaches the other."""
    return b in ancestors(graph, a) and a in ancestors(graph, b)


def pair_state(graph: dict, a: str, b: str):
    """Returns (state, basis[]). Order-independent."""
    na, nb = graph.get(a), graph.get(b)
    basis = []
    if not na or not nb:
        return NOT_PROVEN, ["one or both implementations are not in the graph"]

    # Any pre-v3 cell in the pair: the field does not exist, so nothing is declared.
    for n, label in ((na, "A"), (nb, "B")):
        if n["derived_from"] is None:
            basis.append(f"{label} is {n['schema']}: derived_from ABSENT (pre-v3) — "
                         f"nothing is declared, so independence is not established")
            return NOT_PROVEN, basis

    if in_cycle(graph, a, b):
        basis.append(f"lineage cycle: {na['node_id']} ↔ {nb['node_id']}")
        return NOT_PROVEN, basis

    if na["unresolved"] or nb["unresolved"]:
        who = na["node_id"] if na["unresolved"] else nb["node_id"]
        basis.append(f"unresolved lineage ref on {who} — a cited ancestor resolves to "
                     f"nothing in this claim's graph; not treated as no-ancestor")
        return NOT_PROVEN, basis

    anc_a, anc_b = ancestors(graph, a), ancestors(graph, b)
    if b in anc_a:
        basis.append(f"transitive: {na['node_id']} derives from {nb['node_id']}")
        return DERIVED, basis
    if a in anc_b:
        basis.append(f"transitive: {nb['node_id']} derives from {na['node_id']}")
        return DERIVED, basis
    shared = anc_a & anc_b
    if shared:
        names = ", ".join(sorted(graph[s]["node_id"] for s in shared))
        basis.append(f"shared_ancestor: both derive from {names}")
        return DERIVED, basis

    basis.append("derived_from declared on both, no shared ancestry — independent")
    return INDEPENDENT, basis


def load_claim(claim_dir: pathlib.Path) -> list:
    out = []
    for p in sorted(claim_dir.glob("*.cell.json")):
        d = json.loads(p.read_text())
        pp = json.loads(d["event"]["content"]) if "event" in d else d.get("proof_payload", {})
        if pp.get("result") == "GREEN":          # §4.1 — graph is built from GREEN Cells
            out.append((p.stem.removesuffix(".cell"), pp))
    return out


def main() -> int:
    cells_root = ROOT / "cells"
    if not cells_root.is_dir():
        print("no cells/ — nothing to resolve", file=sys.stderr)
        return 1
    for claim_dir in sorted(cells_root.iterdir()):
        if not claim_dir.is_dir():
            continue
        cells = load_claim(claim_dir)
        if len(cells) < 2:
            continue
        g = build_graph(cells)
        keys = sorted(g)
        print(f"\n── claim {claim_dir.name[:12]}…  ({len(cells)} GREEN cells)")
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                st, basis = pair_state(g, keys[i], keys[j])
                print(f"   {g[keys[i]]['node_id']} × {g[keys[j]]['node_id']}: {st}")
                for b in basis:
                    print(f"      {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
