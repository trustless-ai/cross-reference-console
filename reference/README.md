# reference — `claim_id` + golden vectors

Reference implementation of [`../CLAIM.md`](../CLAIM.md) and the golden vectors both nodes check against. Stdlib only, no deps.

## Compute a `claim_id`
```
python3 reference/claim_id.py reference/vectors/236-review-verdict.claim.json
# -> sha256:df1a6bfe3063186f8a8327b75a5bfddae12d3518f2cc16f8fddbc6c311de9512
```

## The first edge (v0)
`vectors/236-review-verdict.*` — the first golden vector: a `review_verdict` Claim lifted from invinoveritas **`/ledger #236`** (Fede's `/review` reject on the EthMagicians t/28083 composed-run action).

The **first Cell** — the first real edge of the mesh:
1. **Both nodes** compute `claim_id` from the ClaimPreimage → must equal `sha256:df1a6bfe…` byte-for-byte. This repo proves our side; Fede's `/verify-proof` (agentId `54848`) confirms his.
2. **Each node recomputes the verdict itself** — schnorr sig vs the published key `6786e18a…`, `decision_ref` recomputes — and publishes a signed **Cell** (GREEN + evidence) to `/ledger`.
3. A reader pulls both cells → the first **2×1 matrix**, every cell independently recomputable. Never a bare green.

## Mapping choices (v0 — open for Fede to confirm)
See `vectors/236-review-verdict.json → mapping_choices_v0`. The one worth a nod: **`artifact_hash` = the verdict's `decision_ref`** (i.e. the verdict *is* the artifact the console cross-verifies). If you'd rather `artifact_hash` = the *reviewed* artifact with the verdict as a separate field, we mint `crc.claim.v0.1` — v0 stays frozen (append-only, same discipline the Cells enforce).
