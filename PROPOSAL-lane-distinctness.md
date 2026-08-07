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

## 6 · Resolved by the group (2026-08-07)

All four were answered on the PR. Recorded here with attribution, because the answers changed the proposal.

**1 · `derived_from` is a LIST, not a single field.** *(Fede, giskard)* Real derivation is not always single-parent — a fork that later merges logic from a second implementation is a real shape, not a hypothetical. giskard tied it to existing practice: the same discipline as `action_ref`/`decision_binding_ref`, *never collapse multiple provenance facts into a field where the signer has to omit or pick one; a list costs nothing and doesn't pressure honesty.*

**2 + 3 · A derived pair is a DISTINCT, DISQUALIFYING state — not weaker corroboration.** *(Fede, giskard)* Fede's framing, and it settles both questions at once:

> *"shares lineage" and "independently derived" aren't two points on a trust gradient, they're different claims about what the edge proves. Folding a derived pair into GREEN-with-caveat is the same failure as folding `evidence_unavailable` into a fail — a real, distinct fact gets flattened into the nearest existing bucket instead of getting its own state.*

So the console renders a **third value** alongside present/absent that a reader can filter on, not a footnote on an edge that still reads GREEN at a glance. giskard: a boolean hides *which* check produced the AMBER/RED, and that is exactly the part a reader needs.

**4 · Ship v3 alone.** *(giskard)* Nothing pending on the mycelium leg that would need a second struct change, so no reason to batch and make nodes re-sign twice.

## 7 · Open, and deliberately not assumed into this PR

**Does exclusion transit?** If X declares `derived_from [A, B]` and A itself declares `derived_from C`, is X still non-independent of C? Both Fede and giskard reason it must transit, fail-closed — otherwise a two-hop fork launders itself back into independence for free. Both also said it should get its own vector once the field exists rather than be assumed now, and that is the right call: a transitivity rule with no implementation to test against is a guess written in normative language.

## 8 · Fixed in review

`.replace(".cell", "")` corrupted any node name *containing* `.cell` rather than ending with it — `mycelium.cellstore` became `myceliumstore`. Found and fixed by **Pavlo** (`removesuffix`, both checker and tests), who could not push to this repo directly. Applied here with a regression vector over four names so it cannot return.
