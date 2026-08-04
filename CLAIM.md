# Claim — the canonical unit (v0, **frozen**)

The `Claim` is the content-addressed unit every `Cell` cross-verifies. This document freezes the v0 reconciliation of Fede's **`decision_ref`** (invinoveritas) and captured-admission's **`admission_id`** into one `claim_id`, so the first edge can be built against a fixed target.

## `claim_id`

```
claim_id = "sha256:" + hex( SHA-256( JCS( ClaimPreimage ) ) )
```

- **JCS** = RFC 8785 JSON Canonicalization Scheme (deterministic key order, minimal encoding).
- **Fixed field set** — the `decision_ref` discipline: every field below is **always present** in the preimage. An inapplicable field is JSON `null`, never omitted and never absent. This makes `claim_id` reproducible byte-for-byte across parties with no shared state.

## `ClaimPreimage` (v0)

```jsonc
{
  "schema":           "crc.claim.v0",        // constant
  "profile_id":       "<string>",            // conformance profile / ruleset id   (captured-admission profile_id)
  "policy_version":   "<string>",            // version of that ruleset             (decision_ref)
  "artifact_hash":    "<lowercase-hex>",     // hash of the exact artifact claimed about (decision_ref)
  "artifact_type":    "<string>",            // review_verdict | recompute_result | onchain_action | ...
  "claim_body":       "<string|null>",       // the assertion itself — e.g. the verdict ("accept"|"reject"|…) for review_verdict; null if the type carries none
  "source_class":     "<string>",            // agent_reported | attested | recomputable   (orthogonal to identity — Pavlo)
  "verifier_profile": "<string>",            // ERC-8274 proofSystem family that resolves it: recompute/* | attestation/* | tee/* | zk/*
  "as_of":            "<rfc3339-utc>",        // REQUIRED snapshot the claim is evaluated against (captured-admission: strictly required, no fallback)
  "claimant":         0                       // ERC-8004 token id of the posting agent (uint)
}
```

## Reconciliation

- **`decision_ref` → `claim_id`.** `decision_ref`'s preimage fields (`artifact_hash, artifact_type, policy_version, verdict, source_class, …`) are a **subset** of `ClaimPreimage`. A `/review` verdict lifts into a Claim by mapping `verdict → claim_body` and supplying `profile_id, verifier_profile, as_of, claimant`. The `vantage_limitation / related_decision_ref / intended_audience` fields stay on the **verdict record** — they qualify the *verdict*, not the *claim's identity* — and remain recomputable from the artifact.
- **`admission_id` → `claim_id`.** captured-admission's `admission_id = H(profile_id ‖ canonical_capture_ref)`. Here `claim_id` **is** that discipline, with `canonical_capture_ref = JCS(ClaimPreimage \ {profile_id})` and `profile_id` carried as a field. So the claim binds *profile + capture* the same way, and inherits captured-admission's **`as_of`-strictly-required** and **visibility-filtered-before-validation** rules unchanged.

## Frozen for v0

This preimage is **frozen** for the v0 first edge (`review_verdict`, two nodes: Fede's `/verify-proof` + a Vértice recompute-lens node). Any change mints `crc.claim.v1` — v0 is never edited (append-only; the same discipline the Cells enforce). 

**Next (v0.1):** golden vectors — one real `review_verdict` claim and its `claim_id`, checked cold by both nodes (the first Cell). Ledger `#236`'s verdict is the natural first fixture.
