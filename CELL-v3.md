# Cell — structural implementation lineage (v3)

`crc.cell.v3` is the hardening layer over [`crc.cell.v2`](CELL-v2.md), minted per the append-only discipline (v0, v1, and v2 are frozen, never edited). It resolves one vulnerability class identified after [PR #8](https://github.com/trustless-ai/cross-reference-console/pull/8): **implementation lineage was travelling as prose beside the value instead of inside the signed structure**, so distinctness could not be evaluated without trusting lane labels.

v3 adds **`evidence.independence.derived_from`** — a required, signed declaration of whether the implementation was written from specification material or from other implementations. Pair **independence** becomes structurally evaluable. **Cell validity** (GREEN / RED / AMBER) remains orthogonal.

**Prerequisite enforcement (already on `main` @ `7cecd8f`):** [PR #8](https://github.com/trustless-ai/cross-reference-console/pull/8) — `reference/check_lane_distinctness.py` derives **necessary** distinctness from `evidence.independence` (not lane labels), with negative vectors including the rename-lane attack. v3 adds the **sufficient** lineage axis; it does not reopen PR #8 necessary-condition semantics.

Normative companion: [`LINEAGE-REF.md`](LINEAGE-REF.md). Executable scenarios: [`docs/VECTOR-MATRIX-v3-independence.md`](docs/VECTOR-MATRIX-v3-independence.md).

---

## 1 · `evidence.independence.derived_from`

v3 extends the `evidence.independence` object defined in [CELL-v1.md §4](CELL-v1.md). All v1 null-not-absent fields **except** `derived_from` carry over unchanged.

```jsonc
"independence": {
  "implementation": { "repo": …, "commit": …, "path": …, "impl_hash": … },
  "dependency_lock": …,
  "runtime_image":   …,
  "derived_from":    string[],          // v3: REQUIRED — see below
  "inputs":          [ … ],
  "execution_witness": …
}
```

### 1.1 · Field rules (normative)

| Rule | Requirement |
|---|---|
| Presence | **Required** on every v3 Cell. Omission → pre-hash gate **REJECT**. |
| Type | **`string[]` only.** Not `null`, not a string, not an object. |
| Empty list `[]` | Signer declares **no known derivation from another implementation**. Written from specification / independent source material. **Signed provenance — not proof of independence.** |
| Non-empty list | Signer declares **implementation lineage** from one or more sources. Each element is a [LineageRef](LINEAGE-REF.md). |
| Duplicates | Reject at gate (duplicate array entries). |
| Malformed element | Reject at gate (syntax fails LineageRef grammar). |
| Self-reference | Reject at gate if any LineageRef resolves to **this Cell's own** `implementation.impl_hash`. |

### 1.2 · What the gate does NOT reject

- **Unresolved well-formed LineageRef** — syntactically valid ref with no matching implementation in registry resolution scope. The Cell MAY still be **GREEN** if all derivation checks pass. Independence evaluation for pairs involving that Cell yields **INDEPENDENCE_NOT_PROVEN** (see §2.5).

### 1.3 · Payload shape (carry-over from v2)

v3 Cells inherit [CELL-v2.md](CELL-v2.md) in full except for `schema: "crc.cell.v3"` and the changed `evidence` body (therefore changed `evidence_hash` / Nostr digest). EIP-712 `types.Cell` field list is unchanged from v2; `registry_id` remains inside the signed struct.

---

## 2 · Pair independence states (normative)

Independence is evaluated on **ordered pairs of Cells** `(A, B)` that are both **`result: GREEN`** and carry the **same `claim_id`**. This is **orthogonal** to each Cell's own GREEN / RED / AMBER result.

Four pair states exist. **Do not add a fifth user-facing state** — `DERIVED` sub-kinds are **basis labels** only (§2.3).

### 2.1 · INDEPENDENT

Pair `(A, B)` is **INDEPENDENT** if and only if **all** of:

1. Both Cells are **`crc.cell.v3`** with structurally valid `derived_from`.
2. **Necessary distinctness** passes ([PR #8](https://github.com/trustless-ai/cross-reference-console/pull/8) checker): `implementation.impl_hash` and `implementation.repo` present and pairwise distinct; identical disclosed `dependency_lock` or `runtime_image` fails necessary conditions.
3. Both declare **`derived_from: []`** (no known derivation — signed, not proven).
4. **No direct lineage** between A and B (neither's `derived_from` resolves to the other's implementation).
5. **No transitive lineage** between A and B (§4 algorithm).
6. **No shared ancestor** — `Ancestors(A) ∩ Ancestors(B) ≠ ∅` after resolved closure → not INDEPENDENT (§4).
7. **No unresolved LineageRef** on either side that blocks closure (§4).
8. **No multi-node cycle** in the resolved lineage graph involving either endpoint (§4).

**INDEPENDENT counts** toward the ≥2 independent confirmations rule (§3.2).

**`[]` is never sufficient alone.** Distinct `impl_hash` / `repo` are **necessary, never sufficient**.

### 2.2 · DERIVED

Pair `(A, B)` is **DERIVED** if any of:

- **Direct lineage** — one side's `derived_from` resolves to the other's implementation.
- **Transitive lineage** — a resolved path of length ≥2 connects the two implementations (§4).
- **Shared ancestor** — both transitively derive from a common ancestor implementation C.

**DERIVED never counts** toward ≥2 independent confirmations. It MAY be displayed as visible corroboration (group decision, [PROPOSAL-lane-distinctness.md §6](PROPOSAL-lane-distinctness.md)) — not GREEN-with-caveat, not a weaker form of INDEPENDENT.

### 2.3 · DERIVED basis labels (display only — not separate states)

| Label | Meaning |
|---|---|
| `direct` | One Cell's `derived_from` resolves to the other's `impl_hash` / repo ref |
| `transitive` | Resolved path length ≥2 between implementations |
| `shared_ancestor` | `Ancestors(A) ∩ Ancestors(B)` non-empty |

Implementations MUST emit at least one basis label when state is DERIVED.

### 2.4 · NOT_DISTINCT

Pair `(A, B)` is **NOT_DISTINCT** when **necessary distinctness fails** ([PR #8](https://github.com/trustless-ai/cross-reference-console/pull/8)):

- Identical `implementation.impl_hash` and/or `implementation.repo` (copycat / same-implementation rename-lane attack).
- Identical disclosed `runtime_image` or `dependency_lock` when both sides disclosed the field.
- Null `impl_hash` or `repo` on either side (absence is not a pass).

**NOT_DISTINCT is separate from DERIVED** — same file ≠ declared fork lineage.

### 2.5 · INDEPENDENCE_NOT_PROVEN

Pair `(A, B)` is **INDEPENDENCE_NOT_PROVEN** when independence cannot be closed fail-closed:

- Either Cell is **pre-v3** (`derived_from` structurally absent) or **mixed-version** pair (v3 × v2/v1/v0).
- **Unresolved** well-formed LineageRef on either side (§1.2).
- **Multi-node cycle** discovered during resolution (§4) — basis MUST name the cycle.
- **Could-not-close lineage** — closure algorithm cannot complete without guessing.

**INDEPENDENCE_NOT_PROVEN never silently upgrades to INDEPENDENT.** Pre-v3 pairs are **always** INDEPENDENCE_NOT_PROVEN on the independence axis, never INDEPENDENT.

---

## 3 · Claim-level semantics — two axes (normative)

v3 **does not collapse** validity dispute and independence confirmation. Claim-level status is **two orthogonal summaries**.

### 3.1 · Validity axis (carry-over from CELL-v1 §5, CELL-v2 §5)

Re-states existing crc.cell edge semantics. **Do not weaken.**

| Status | Rule |
|---|---|
| **VALIDITY_HOLDS** | ≥2 Cells **GREEN** with byte-equal `claim_id` on distinct lanes/implementations (necessary distinctness per PR #8); **no RED** on the claim |
| **VALIDITY_DISPUTED** | ≥1 Cell **RED** on the claim — *"Any RED on the claim breaks the edge until reconciled"* ([CELL-v1.md §5](CELL-v1.md)) |
| **VALIDITY_PENDING** | Fewer than two GREEN Cells; only AMBER / absent otherwise |

AMBER Cells **abstain** — never break validity, never count ([CELL-v1.md §5](CELL-v1.md)).

### 3.2 · Independence axis (v3)

Evaluated among **GREEN** Cells on the claim.

| Status | Rule |
|---|---|
| **INDEPENDENCE_CONFIRMED** | ∃ set S of GREEN Cells, \|S\| ≥ 2, such that ∀ a ≠ b ∈ S: pair(a,b) = **INDEPENDENT** |
| **INDEPENDENCE_NOT_CONFIRMED** | ≥2 GREEN but no qualifying INDEPENDENT pair (includes DERIVED-only, NOT_DISTINCT, INDEPENDENCE_NOT_PROVEN mixes) |
| **INDEPENDENCE_UNAVAILABLE** | Validity disputed, or fewer than two GREEN Cells |

### 3.3 · Display under validity dispute

When **VALIDITY_DISPUTED**, independence pair basis among remaining GREEN Cells MAY still be rendered **informational only**. It MUST be labeled as not confirming the claim-level validity edge. **Do not collapse** validity dispute into independence basis.

---

## 4 · Lineage resolution and transitivity

**Normative algorithm:** specified here for implementers. **Final normative prose** for edge cases marked `[PENDING-VECTOR]` until matching rows in [`docs/VECTOR-MATRIX-v3-independence.md`](docs/VECTOR-MATRIX-v3-independence.md) are executable in CI.

### 4.1 · Resolution scope

- Build lineage graph **G** per **claim** from all **GREEN** Cells on that claim in the registry.
- **Primary node key:** `implementation.impl_hash` when present.
- **LineageRef resolution:** per [LINEAGE-REF.md](LINEAGE-REF.md). Default scope: **same claim** Cells first; cross-claim refs `[PENDING-VECTOR]`.

### 4.2 · Graph construction

- **Node:** each distinct implementation (by `impl_hash`, else `(repo, commit, path)` tuple).
- **Directed edge X → Y:** Y is resolved from an entry in X's `derived_from`.
- **Unresolved ref:** mark node `lineage_unresolved: true`; do not invent targets.

### 4.3 · Ancestors and shared ancestor

```
Ancestors(X) = transitive closure of nodes reachable from X via derived_from edges
```

- Pair **DERIVED · shared_ancestor** if `Ancestors(A) ∩ Ancestors(B) ≠ ∅`.
- Pair **DERIVED · transitive** if B ∈ Ancestors(A) or A ∈ Ancestors(B) without requiring shared root only.

### 4.4 · Cycles

| Case | Treatment |
|---|---|
| Self-reference at gate | **REJECT** Cell (§1.1) |
| Multi-node cycle in G | Pair **INDEPENDENCE_NOT_PROVEN**; basis `lineage cycle: <path>` |

Cycle does **not** automatically imply NOT_DISTINCT unless necessary conditions also fail.

### 4.5 · Fail-closed rule

**Could-not-check is never a pass.** Any ambiguity in closure → **INDEPENDENCE_NOT_PROVEN**, never INDEPENDENT.

---

## 5 · Mechanical v2 sunset

Mirrors [CELL-v2.md §4 · Mechanical v1 sunset](CELL-v2.md):

```
activation_commit = git log --diff-filter=A --format=%H -- CELL-v3.md
```

- Cells submitted (PR-merged or bot-committed) **after** the activation commit **MUST** be `crc.cell.v3`.
- Every Cell that exists at activation — v0, v1, and v2 history including the live `#236` edge — **stands as frozen history**. Nothing is re-signed; nothing is invalidated.
- Same discipline as v2 §4: bind the rule to what was in force at the time; never shift retroactively.

---

## 6 · Everything else carries over

Result semantics (GREEN / RED / AMBER), the validity edge rule ([CELL-v1.md §5](CELL-v1.md)), the pre-hash conformance gate, `as_of`/`recomputed_at` separation, boundary-in-payload, `registry_id` binding ([CELL-v2.md](CELL-v2.md)), derivable `evidence.independence` fields other than `derived_from`, and signature grammar are unchanged from v2 except where this file explicitly amends independence evaluation.

Per [CELL-v2.md §5 · Everything else carries over](CELL-v2.md): *"Any change to this struct or these rules mints `crc.cell.v3`."* This file is that mint.

---

## 7 · Versioning

| Version | Status |
|---|---|
| `crc.cell.v0` | Frozen ([CELL.md](CELL.md)) |
| `crc.cell.v1` | Frozen ([CELL-v1.md](CELL-v1.md)) |
| `crc.cell.v2` | Frozen at v3 activation; remains verifiable as v2 |
| `crc.cell.v3` | Strict conformance surface for new Cells after activation |

Append-only: never edit prior version files in place. Any further struct or rule change mints `crc.cell.v4`.

---

## 8 · Relationship to superseded proposal

[PROPOSAL-lane-distinctness.md](PROPOSAL-lane-distinctness.md) recorded the hole, PR #8 necessary-condition enforcement, and group decisions on list shape and DERIVED disqualification. **This file supersedes that proposal as normative spec.** Implementation PRs follow separately.
