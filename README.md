# Cross-Reference Console

*A multi-operator, mutual-recompute surface for the trustless-AI working group.*

> **Don't trust. Recompute — continuously, and about each other.**

*The recompute discipline is not ours. `recompute → compare → confirm inclusion` is the
Verification Invariant of [ERC-8281, the Observation Commitment Protocol](https://github.com/ethereum/ERCs/pull/1788) (Damon Zwicker). This project applies it
across multiple operators; it did not invent it.*

**Status:** first edge **LIVE** (2026-08-04): `/ledger #236` carries two independently-signed Cells on two lanes (attestation/invinoveritas · recompute/cross-reference-console), same `claim_id`, recomputable in-browser (`ui/`). Hardening pass landed 2026-08-05 ([`CELL-v1.md`](CELL-v1.md)) answering Pavlo's five conformance points: observation/evaluation time split, full boundary binding + triple signer equality, a universal pre-hash gate (duplicate members, hash grammar, claimant range — enforced in Python **and** the browser, negative vectors in [`reference/test_gate.py`](reference/test_gate.py)), recomputable independence evidence, and the operational AMBER/RED split (AMBER abstains, only a computed mismatch earns RED).

---

## What this is

Today the working group runs blind-diff **by hand**: someone posts a claim or a verdict, someone else independently *recomputes* it before trusting it — e.g. the ERC-8274 composed run (CAPV · `/review` · `recompute/wyriwe`), all three cross-verified on Fede's `/ledger #236`.

The Cross-Reference Console makes that habit a **standing protocol surface**. Each participant registers an agent; when anyone posts a claim, the others' agents **auto-recompute it** and publish a **signed cross-verification**. The result is a matrix — rows = claims, columns = participants — where **every cell is a signed, independently recomputable evidence record**, and green / red / amber is derived *only* from that evidence.

It is a **submission gate**: nothing is trusted because it was asserted; it is trusted because N independent nodes re-derived it. Pavlo's framing — it turns "never a bare green" from a habit four of us share into a **protocol property**.

## Not a new build — a convergence

Every part already exists in the family:

| Piece | Provided by |
|---|---|
| **Recompute discipline / verification invariant** | **ERC-8281 (Observation Commitment Protocol), Damon Zwicker** — `recompute → compare → confirm inclusion`. The name of this project and its tagline are that invariant; everything below is built on it |
| **Claim format** | Fede's `decision_ref` (content-addressed preimage tuple) reconciled with captured-admission's `admission_id` |
| **Verifier boundary** | ERC-8274 `IProofVerifier` — proven to carry confidential ⊕ attested ⊕ recomputable through one interface (t/28083 → `/ledger #236`) |
| **Node** | Fede's `/verify-proof` (free, no-auth, recompute-and-confirm, schnorr-checked) — the reference node; each participant runs one |
| **Cell record** | a signed recomputable verdict published to `/ledger` |
| **Tri-state** | recompute-lens (AMBER "could not check" is a first-class state) |
| **Bus / substrate** | Jimmy's group-as-bus + agents-as-first-class; append-only (a correction anchors; the original stays preserved-marked-disputed) |

## Core model

### `Claim` — the unit under verification
Content-addressed; the `decision_ref` / `admission_id` discipline.
```
Claim {
  claim_id,          // = H(profile_id ‖ canonical_preimage)  (reconciles decision_ref ↔ admission_id)
  artifact_hash,     // what is claimed (a verdict, a recompute result, an on-chain action, a conformance run…)
  claim_type,        // review_verdict | recompute_result | onchain_action | conformance_run | …
  policy_version,    // ruleset the claim was made under (immutable; a change mints a new version)
  source_class,      // agent_reported | attested | recomputable | …  (orthogonal to identity — Pavlo)
  verifier_profile,  // ERC-8274 proofSystem family that resolves it: recompute/* | attestation/* | tee/* | zk/*
  as_of,             // REQUIRED — the snapshot it is evaluated against (captured-admission)
  claimant           // ERC-8004 id of the posting agent
}
```

### `Cell` — one node's independent cross-verification
```
Cell {
  claim_id,
  verifier,          // ERC-8004 id of the recomputing node
  result,            // GREEN (recomputed, matches) | RED (recomputed, mismatch) | AMBER (could not check)
  evidence,          // the recomputable record: recipe + inputs + boundary result — never a bare status
  boundary,          // the ERC-8274 IProofVerifier result it resolved through
  recomputed_at,     // the verifier's as_of; visibility-filtered-before-validation
  sig                // schnorr over the cell, checkable against the verifier's published key
}
```
**Rule (Pavlo):** every cell is a *signed, independently recomputable evidence record* — never an opinion, never a bare green. `result` is **derived** from `evidence`, not asserted.

### Matrix
Rows = claims, columns = nodes. **The matrix is a view; the truth is the set of signed cells on `/ledger`.** Any reader re-derives any cell from its evidence — no trust in the console, the poster, or any node.

## Protocol (v0 — narrow, per Pavlo's four constraints)

1. **One canonical claim format** — the `Claim` above (`decision_ref` ↔ `admission_id`).
2. **One shared verifier boundary** — ERC-8274 `IProofVerifier`; `verifier_profile` names the proofSystem family.
3. **Explicit timing** — `as_of` required on claim *and* cell; visibility-filtered-before-validation (a later transition can't change an earlier snapshot); a late/overturned outcome is **preserved, never rewritten** (captured-admission: semantic ⟂ liveness).
4. **Evidence-only tri-state** — GREEN / RED / AMBER derived solely from the cell's evidence; AMBER is first-class, not failure.

Flow:
```
1. Agent A posts a Claim to the group bus (dual-encoded: human text + machine envelope).
2. Each other node sees the envelope, fetches the artifact, and recomputes the claim through
   its ERC-8274 boundary at its own as_of.
3. Each node publishes a signed Cell to /ledger.
4. The console renders the matrix from the cells; every cell links to its recomputable evidence.
5. Appeals/corrections APPEND, never rewrite: a correcting cell anchors, the original stays
   marked disputed. Non-suppression: a missing cell is itself a derivable, falsifiable fact.
```

## v0 scope — the first edge, buildable now

- **Claim schema** — freeze `Claim`; write the `decision_ref ↔ admission_id` reconciliation as a captured-admission conformance profile.
- **Two nodes** — Fede's `/verify-proof` (live) + a second (Vértice recompute-lens node). One real cross-verification edge.
- **One claim type** — `review_verdict` (Fede already issues these; simplest to recompute).
- **Ledger** — reuse `/ledger` for the signed cells.
- **UI** — a 2×1 matrix (one claim, two nodes) rendering the two cells. Prove the surface before scaling to N.

**Deliberately NOT in v0:** N-party fan-out, the full matrix UI, agent auto-posting, economic incentives, cross-domain claim types. Narrow first.

## Non-goals
- Not a chat app — the edges are **recompute**, not messages.
- Not a trusted aggregator — the console **renders**, it does not adjudicate.
- Not a new trust model — it makes "never a bare green" a *protocol property* over the existing recompute stack.

## Open questions
- `decision_ref ↔ admission_id` field reconciliation (the exact shared preimage).
- Node discovery / registration (ERC-8004 + AgentCard).
- AMBER taxonomy — distinguish *artifact unavailable* vs *boundary unreachable* vs *policy_version unknown*.
- Non-suppression mechanics for a **missing** cell (Pavlo's four legs, one layer up).

## Relation to the stack
`decision_ref` (invinoveritas) · captured-admission (recompute-kit) · ERC-8274 `IProofVerifier` (agent-ercs) · `/verify-proof` (invinoveritas) · recompute-lens (UI) · group-as-bus / substrate (Jimmy) · `/ledger`.

---
*CC0. A working-group artifact — intended home: the `trustless-ai` org.*
