# The watcher — intake → gate → registry (public CI)

The pipeline that makes the console self-serve: submissions enter at a registered intake, pass the **pre-hash gate**, and land in `claims/` — committed **from public GitHub Actions CI**, so the committer role lives in no member's box and every commit's audit trail is a public run log (group decision, 2026-08-05: *"a committer that only lives on one member's box is itself a single point of trust"*).

```
/ledger/submit (paid, signed, auto-accepted)      ← admission: the intake's economics
        │
        ▼  reference/watcher.py, every 30 min from CI
   pre-hash gate (reference/claim_id.py)          ← validity: the ONLY door to claims/
        │
        ├─ conforming    → claims/{claim_id_hex}.json     (crc.claimfile.v0)
        └─ nonconforming → claims/rejected/entry-{n}.json (crc.rejected.v0, WITH the gate error)
        ▼
   nodes produce signed v1 Cells → cells/{claim_id_hex}/{node_id}.cell.json
        ▼
   console renders rows from claims/, columns from nodes.json
```

## lift.v0 — deterministic, no special cases

A ledger entry whose `proof_event.content` parses as `invinoveritas.verdict_proof.v1` lifts to a `ClaimPreimage` as documented in [`reference/watcher.py`](reference/watcher.py) (profile from `platform`, `artifact_hash` from `decision_ref`, `as_of` = RFC3339 of the verdict's own `verified_at`, `claimant` = the issuing verifier's ERC-8004 id). Anyone re-running the lift derives the same `claim_id`.

**Proof it's the right rule:** lifting `/ledger #236` derives `sha256:df1a6bfe…` — **byte-for-byte the hand-minted claim** both v0 and v1 Cells already verify. The watermark therefore starts at 235 and #236 entered `claims/` through the same pipeline as everything after it. One rule, no grandfathering.

## Non-suppression

- Paid-but-nonconforming submissions are **public** in `claims/rejected/` with the exact gate error — *"the asymmetry IS the moat, a verifier that only shows you its wins isn't verifying anything"* (Fede). Payment never buys past the gate; failing the gate never refunds admission.
- A claim with no Cell yet renders **pending-abstain** (AMBER discipline), never failure.
- The watermark file (`claims/.watermark.json`) is committed — where the watcher has looked is itself derivable.

## PR validation ([validate-pr.yml](.github/workflows/validate-pr.yml))

Every PR touching `nodes.json`, `cells/`, `claims/`, or `reference/` runs, in public CI: the gate conformance suite (negative vector per predicate), the `crc.nodes.v0` validator, every Cell's envelope check against the registry (eip712 → quadruple equality incl. the registered address; nostr-nip01 → NIP-01 + BIP-340 vs the registered pubkey — pure-stdlib [`reference/bip340.py`](reference/bip340.py)), and every claim file's re-derivation. Green = merges; that is the whole review.
