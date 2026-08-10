# Vector matrix — v3 independence semantics

**Status:** SPEC — executable implementation **not yet in CI**. Each row defines a scenario that MUST become a named test in `reference/test_independence.py` (future PR).  
**Normative pair rules:** [CELL-v3.md](../CELL-v3.md). **LineageRef grammar:** [LINEAGE-REF.md](../LINEAGE-REF.md).

**Legend**

- **Pair state:** INDEPENDENT | DERIVED | NOT_DISTINCT | INDEPENDENCE_NOT_PROVEN
- **Claim validity:** separate axis — see [CELL-v3.md §3](../CELL-v3.md)
- **Exec:** ❌ = not yet executable in repo CI

---

## Pair vectors (V-01 – V-16)

| ID | Scenario | Setup summary | Expected pair state | Expected basis highlight | Exec |
|---|---|---|---|---|---|
| **V-01** | Independent baseline | v3 A,B both GREEN; `derived_from: []`; distinct impl_hash/repo; same claim_id | **INDEPENDENT** | `derived_from []/[]`; no lineage path |✅ `test_lineage_graph.py` |
| **V-02** | Direct derivation | B `derived_from: [ref→A.impl_hash]`; distinct hashes | **DERIVED** | `direct`; B→A |✅ `test_lineage_graph.py` |
| **V-03** | Multi-parent | X `derived_from: [ref→A, ref→B]` | X×A **DERIVED**, X×B **DERIVED** | `direct` per parent |✅ `test_lineage_graph.py` |
| **V-04** | Two-hop transitivity | X→A, A→C (all v3, declared) | X×C **DERIVED** | `transitive`; path X→A→C |✅ `test_lineage_graph.py` |
| **V-05** | Cycle | A→B, B→A (declared, multi-node) | A×B **INDEPENDENCE_NOT_PROVEN** | `lineage cycle: …` |✅ `test_lineage_graph.py` |
| **V-06** | Missing target | X `derived_from: [crc.lineage.v0:impl/sha256:dead…]` (no match) | any pair with X **INDEPENDENCE_NOT_PROVEN** | `unresolved LineageRef` |✅ `test_lineage_graph.py` |
| **V-07** | Identical impl_hash | copycat independence block (PR #8 vector) | **NOT_DISTINCT** | `impl_hash IDENTICAL` | ✅ PR #8 |
| **V-08** | Identical repo | same repo URL, different impl_hash | **NOT_DISTINCT** if repo rule fires | `repo IDENTICAL` | ✅ PR #8 |
| **V-09** | Shared runtime | same `runtime_image`, distinct code | **NOT_DISTINCT** | `runtime_image identical` | ✅ PR #8 |
| **V-10** | Shared dependency_lock | same lock hash disclosed both sides | **NOT_DISTINCT** | `dependency_lock identical` | ✅ PR #8 |
| **V-11** | Pre-v3 pair | v1 × v1 (live #236 cells) | **INDEPENDENCE_NOT_PROVEN** | `derived_from ABSENT (pre-v3)` | ✅ PR #8 (AMBER basis) |
| **V-12** | Mixed v3×v2 | v3 `[]` vs v2 | **INDEPENDENCE_NOT_PROVEN** | `pre-v3 / mixed-version cell in pair` |✅ `test_lineage_graph.py` |
| **V-13** | Fork laundering | distinct impl_hash/repo; B `derived_from: [ref→A]` | **DERIVED** | hash inequality **insufficient** |✅ `test_lineage_graph.py` |
| **V-14** | Honest `[]` | distinct impl_hash; both `[]`; no shared ancestry | **INDEPENDENT** (candidate) | signed `[]`, not proven |✅ `test_lineage_graph.py` |
| **V-15** | Rename-lane attack | identical independence block, different lane labels | **NOT_DISTINCT** | PR #8 rename attack | ✅ PR #8 |
| **V-16** | Stem suffix regression | cell file `mycelium.cellstore.cell.json` → node id `mycelium.cellstore` | checker id extraction correct | `removesuffix(".cell")` (Pavlo, PR #8) | ✅ PR #8 |

---

## Claim-level vectors (derive from pairs)

| ID | Scenario | GREEN cells | Pair facts | Validity axis | Independence axis |
|---|---|---|---|---|---|
| **C-01** | Validity holds + independence confirmed | A,B GREEN INDEPENDENT | V-01 | **VALIDITY_HOLDS** | **INDEPENDENCE_CONFIRMED** |
| **C-02** | Validity holds + derived corroboration only | A,B GREEN; V-13 | B DERIVED from A | **VALIDITY_HOLDS** | **INDEPENDENCE_NOT_CONFIRMED** |
| **C-03** | Validity disputed, informational independence | A,B GREEN INDEPENDENT; C RED | V-01 among A,B | **VALIDITY_DISPUTED** | **INDEPENDENCE_UNAVAILABLE** (claim) + A×B basis **informational only** |
| **C-04** | Pre-v3 validity only | v1 GREEN pair, byte-equal claim_id | V-11 | **VALIDITY_HOLDS** (v1 rules) | **INDEPENDENCE_NOT_CONFIRMED** |

---

## Transitivity vectors (block normative prose until executable)

These rows **must pass** before [CELL-v3.md §4](../CELL-v3.md) transitivity prose is marked final:

- V-04 (two-hop)
- V-05 (cycle)
- V-06 (unresolved)
- V-03 (multi-parent + shared ancestor interaction) `[PENDING-VECTOR]`

---

## Shared-ancestor vectors

| ID | Scenario | Expected |
|---|---|---|
| **S-01** | A→C, B→C; both `[]` at declaration level but shared C | A×B **DERIVED · shared_ancestor C** |
| **S-02** | A→C, B→D; C≠D; no cross path | Evaluate per full closure `[PENDING-VECTOR]` |

---

## Gate vectors (Cell publish — REJECT)

| ID | Scenario | Expected |
|---|---|---|
| **G-01** | `derived_from` absent | **REJECT** |
| **G-02** | `derived_from: null` | **REJECT** |
| **G-03** | `derived_from: [""]` | **REJECT** |
| **G-04** | duplicate refs in array | **REJECT** |
| **G-05** | self-reference ref | **REJECT** |
| **G-06** | malformed ref (bare URL) | **REJECT** |
| **G-07** | unresolved well-formed ref | **ACCEPT** Cell; pair **INDEPENDENCE_NOT_PROVEN** |

---

## Implementation checklist (future PR — not this scope)

- [ ] `reference/test_independence.py` — one named test per V-01–V-16, S-*, G-* row
- [ ] `reference/check_independence.py` — pair state enum + transitivity + claim-axis summaries
- [ ] CI step replaces lane-only stdout with edge-state report
- [ ] UI contract per [CELL-v3.md §3.3](../CELL-v3.md) (separate PR)
