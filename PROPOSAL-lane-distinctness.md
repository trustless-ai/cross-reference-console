# Proposal — define and enforce lane distinctness

**Status:** PROPOSAL, for the group. Not adopted. Raised 2026-08-07 after an outsider onboarding walk ([PR #7](https://github.com/trustless-ai/cross-reference-console/pull/7), M Zidan Fatonie) surfaced the lane taxonomy as undocumented. It is worse than undocumented.

---

## 1 · The hole

`CELL-v1.md` §5, unchanged through v2:

> An edge holds when ≥ 2 Cells are GREEN with byte-equal `claim_id` on **distinct lanes/implementations**.

An edge is the console's entire output. Everything else — claims, cells, signatures, the gate — exists to produce it. And the predicate it turns on has never been defined.

The only enforcement that exists anywhere is in `validate_nodes.py`:

```python
chk(f"{nid}: lane non-empty family/instance", nonempty_str(n["lane"]) and "/" in n["lane"])
```

A non-empty string containing a slash. Nothing compares lanes across nodes. Nothing looks at what the lanes actually *did*.

**So two nodes running one implementation, registered as `recompute/a` and `recompute/b`, produce a green edge carrying zero independence.** The mesh's central claim — that two parties recomputed the same value separately — currently rests on them having typed different strings.

This is not hypothetical. `reference/check_lane_distinctness.py` includes the case: copy an existing cell's `independence` block, change the lane name and verifier, and the pair is indistinguishable from a real edge under today's rules.

## 2 · What can and cannot be derived

The evidence already collected in `evidence.independence` (v1 §4) is enough for the **necessary** conditions:

| condition | derivable today | why it matters |
|---|---|---|
| `impl_hash` present and distinct | yes | identical hash = literally the same file |
| `repo` present and distinct | yes | identical repo = the same codebase |
| `dependency_lock` distinct | when disclosed | different resolved dependency graph |
| `runtime_image` distinct | when disclosed | different execution environment |

It is **not** enough for the sufficient one.

Hash inequality proves the files differ. It says nothing about whether one implementation was *written from* the other. Fork `reference/claim_id.py`, change a comment, and you have a fresh `impl_hash`, a fresh `repo`, and no independence at all. Two implementations that share a lineage share their bugs — which is the only reason independence was ever worth having.

**Independence cannot be derived from any hash we collect.** It is a provenance claim, and provenance has to be declared.

## 3 · The declaration already exists — in prose

`receiptos-recompute`'s boundary string, on the live edge:

> *"...independently re-derived from the live `/ledger #236` source using a from-scratch `crc.claim.v0` gate + JCS canonicalizer (`tools/cross_reference_console/receiptos_crc_claim_id.py`, **not** `reference/claim_id.py`); ClaimPreimage field mapping **reasoned from** CLAIM.md, CELL-v1.md, and `reference/README.md`..."*

That is a precise, deliberate non-derivation claim. Pavlo made exactly the right disclosure, by hand, because the schema had nowhere to put it — so it went into a free-text field where nothing can check it, index it, or notice its absence.

This is the failure the group has now hit four times in one day: **a qualifying state travelling as prose beside the value instead of inside the structure.**

## 4 · Proposed change (mints `crc.cell.v3`)

Add one field to `evidence.independence`:

```jsonc
"independence": {
  "implementation": { "repo": …, "commit": …, "path": …, "impl_hash": … },
  "dependency_lock": …,
  "runtime_image": …,
  "derived_from": null,        // NEW — REQUIRED, null-not-absent
  "inputs": [ … ]
}
```

- `null` — written from the specification, not from another implementation.
- `"<url>"` — derived from that implementation. Honest, permitted, and it means an edge with that implementation is **not** an independent edge.

Per v1's existing rule, the field is always present; `null` means "independent", never "unstated". Absence fails the gate.

**Why this must be v3 and not a validator patch.** `evidence.independence` sits inside the signed struct. A required field changes it, and `CELL-v2.md` §6 is explicit: any change to the struct or these rules mints `crc.cell.v3`. Existing v1/v2 cells stay valid as v1/v2 — the append-only discipline holds, nothing is re-signed.

## 5 · Migration, and what happens to the live edge

`reference/check_lane_distinctness.py` runs today, against real cells, with no spec change:

```
All pairs meet the NECESSARY conditions for distinctness.

Not a claim of independence. `derived_from` does not exist in the signed
struct yet, so no pair can do better than 'not contradicted'.
```

All six pairs across the four current cells pass the necessary conditions — four distinct repos, four distinct `impl_hash` values. **No existing edge breaks.** The forged copycat case fails, as it must.

The checker reports an independence **basis** per pair rather than a boolean, and refuses to upgrade "not contradicted" into "independent". Until `derived_from` exists, AMBER is the strongest honest reading, and could-not-check is never a pass.

## 6 · Open questions for the group

1. **Is `derived_from` a single field or a list?** An implementation may draw on several. A list is more honest and more annoying to check.
2. **Does a `derived_from` edge count for anything?** Proposal: it is recorded, and it does not satisfy the ≥2-distinct-lanes rule. It is a corroboration, not an independent confirmation.
3. **Should the console display the basis?** Currently an edge renders as present or absent. It could render *why* — which would make the weak-independence case visible instead of merely recorded.
4. **Does this justify v3 on its own,** or should it be batched with other pending struct changes so nodes re-sign once rather than twice?

*Decision is the group's. This proposal ships the checker and the negative case so the decision is about something running rather than something described.*
