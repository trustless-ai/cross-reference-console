# reference — `claim_id` + golden vectors

Reference implementation of [`../CLAIM.md`](../CLAIM.md) and the golden vectors both nodes check against. Stdlib only, no deps. **The reference implementation is the conformance boundary.**

## Compute a `claim_id`
```
python3 reference/claim_id.py reference/vectors/236-review-verdict.claim.json
# -> sha256:df1a6bfe3063186f8a8327b75a5bfddae12d3518f2cc16f8fddbc6c311de9512
```

## Validation — the pre-hash gate  *(Pavlo, 2026-08-04)*
`claim_id()` **validates before it hashes**: exact `crc.claim.v0` key set (no missing, no unknown fields), required types, and strict `as_of` = RFC3339 UTC `YYYY-MM-DDTHH:MM:SSZ`. A structurally incomplete or extended input is **rejected** (`ValueError`) — it never receives a `claim_id`. So the reference impl serves as the conformance boundary, not just a hasher.

## Status of the first edge
- ✅ **Fixture shipped** — `vectors/236-review-verdict.*`, `claim_id sha256:df1a6bfe…`, from real `/ledger #236`.
- ✅ **Node 1 Cell landed + cross-verified** — Fede's `/verify-proof` (agentId `54848`) published a signed **GREEN** Cell; we recomputed his `claim_id` and the Nostr event-id cold — both match. (`api.babyblueviper.com/verdict-proofs/5f6b6d7c…`)
- ⏳ **Node 2 Cell pending** — a Vértice recompute-lens node publishes the second signed Cell → the first live **2×1 matrix**.

## Composability: authority ⟂ assertion  *(Pavlo)*
Two proofs, kept composable, never collapsed:
- **Authority** — *which agent key was valid* → `pq-agent-binding` / ERC-8323 (the PQ binding lifecycle).
- **Assertion + recompute** — *what the authorized agent asserted, and what independent nodes recomputed* → Claim / Cell.

`claimant` names the agent; whether its key was in-force is resolved by the **authority leg**, not folded into `claim_id`.

## The first Cell flow
1. Both nodes compute `claim_id` from the ClaimPreimage → must equal `sha256:df1a6bfe…` byte-for-byte.
2. Each node recomputes the verdict itself (schnorr sig vs the published key, `decision_ref` recomputes) and publishes a signed **Cell** (GREEN + evidence).
3. A reader pulls both cells → the first **2×1 matrix**, every cell independently recomputable. Never a bare green.

## Mapping choices (v0 — open for Fede to confirm)
`artifact_hash` = the verdict's `decision_ref` (the verdict *is* the artifact cross-verified). To split it, mint `crc.claim.v0.1` — v0 stays frozen (append-only).
