# Cell — registry-instance binding (v2)

`crc.cell.v2` is the hardening layer over [`crc.cell.v1`](CELL-v1.md), minted per the append-only discipline (v1 and v0 are frozen, never edited). It resolves one vulnerability class, identified in Pavlo's read-only domain/compat audit (2026-08-06) and demonstrated in the wild the next day: **a valid Cell signature must not be replayable across two registry instances — even when both live on the same chain, and even when the lane has no domain concept at all.** (The live exhibit: two verifier stacks on Sepolia, both verifying the same composed-run proof, one day after the audit.)

## 1 · Registry identity

```
registry_id = "sha256:" + hex( SHA-256( JCS( genesis nodes.json ) ) )
```

For THIS registry:

```
registry_id = sha256:9b871ba9cf05e9da7df78e0b15d44fc04059e6af4bda8037d6f456984598d157
genesis     = nodes.json @ 72b8804c4e85e6ec1530a3470a9af7a5fe47f238  (the commit that ADDED the file:
              2 nodes — invinoveritas, vertice-recompute-lens — and 1 claim_source)
```

- **JCS canonical, not raw bytes, not git blob** — the identity derives from the *parsed content* under the same RFC 8785 convention as `claim_id` and `decision_ref`, so anyone re-deriving from parsed JSON gets the same value regardless of on-disk formatting. (All three candidate conventions were computed and cross-checked independently by two parties before this pick was frozen.)
- The genesis commit is mechanically derivable: `git log --diff-filter=A -- nodes.json`.
- **Frozen-genesis identity**: the registry_id never changes as the registry grows — membership evolves, identity doesn't. A registry migration mints a NEW registry_id and tombstones this one (out of scope for v2).
- This value is also the instance qualifier for the registry's CAIP-10 form when the genesis content-address is anchored on-chain.

## 2 · Payload-primary binding (the invariant, per lane)

**Normative check (all lanes): `proof_payload.registry_id == THIS_REGISTRY.registry_id`.** A Cell whose payload carries a different — or no — registry_id is not a Cell of this registry, regardless of any domain-level separation.

Payload-primary is the invariant because it generalizes: the Nostr lane has no domain or salt concept — the event id is sha256 of the NIP-01-serialized content, so **only** a field inside the signed content can bind the registry. The EIP-712 lane gets the same treatment, with domain separation retained as defense-in-depth, not as the mechanism.

### 2.1 · Claim neutrality (normative)

`registry_id` lives in the **Cell** layer only. It MUST NOT enter the `crc.claim.v0` ClaimPreimage or the `claim_id` derivation: Claims remain lane- and registry-neutral so every lane and every registry continues to cross-reference the same byte-identical `claim_id`. (Pavlo, 2026-08-07.)

### 2.2 · EIP-712 lane

```jsonc
domain = { "name": "cross-reference-console", "version": "2", "chainId": 1,
           "salt": "0x9b871ba9cf05e9da7df78e0b15d44fc04059e6af4bda8037d6f456984598d157" }  // RECOMMENDED

types.Cell = [
  { "name": "schema",        "type": "string"  },   // "crc.cell.v2"
  { "name": "claim_id",      "type": "string"  },
  { "name": "result",        "type": "string"  },
  { "name": "verifier",      "type": "address" },
  { "name": "registry_id",   "type": "string"  },   // v2: the registry instance, INSIDE the signed struct
  { "name": "boundary",      "type": "string"  },
  { "name": "as_of",         "type": "string"  },
  { "name": "recomputed_at", "type": "string"  },
  { "name": "evidence_hash", "type": "bytes32" }
]
```

- `registry_id` in the struct already changes the digest — that alone is cryptographically sufficient **when the verifier performs the normative payload check above**.
- `domain.salt`, derived from the same registry_id digest, is RECOMMENDED as defense-in-depth/domain separation. It MUST NOT be described or relied upon as the only digest-changing mechanism.
- `verifyingContract` MUST NOT be used unless an actual verifying contract exists.
- **Quadruple equality carries over from v1** and gains the registry predicate: recovered signer == `signature.signer` == `proof_payload.verifier` == the key REGISTERED in nodes.json for this node, **and** `proof_payload.registry_id` equals the verifier's own registry_id.

### 2.3 · Nostr lane

`registry_id` is a member of the signed content object (the `proof_payload` serialized into the event `content`). It is therefore covered by the NIP-01 event id and the BIP-340 signature — same payload-primary mechanism, no domain construct involved. The registered pubkey check from v1 carries over unchanged.

## 3 · Signature grammar (all hex material, normative)

Learned live (Node 4's first Cell, 2026-08-07): a bare-hex signature verified under eth_account and threw under ethers — the same Cell earning two different verdicts across implementations. v2 pins the grammar so divergence is a named CI failure, not a browser mystery:

- EIP-712 `signature.signature`: `^0x[0-9a-f]{130}$` (65 bytes, 0x-prefixed, lowercase)
- `signature.evidence_hash`: `^0x[0-9a-f]{64}$` · `signature.signer` / `proof_payload.verifier`: `^0x[0-9a-fA-F]{40}$` (0x-prefixed)
- Nostr `event.id` / `event.pubkey` / `event.sig`: bare lowercase hex (64/64/128) — NIP-01's own convention, unchanged
- `registry_id` / `claim_id`: `sha256:` + 64 lowercase hex

An implementation MUST reject nonconforming encodings at validation time; tolerant parsing is how the divergence class survives.

## 4 · Mechanical v1 sunset

**Activation point = the commit that lands this file on `main`**, mechanically derivable by anyone:

```
activation_commit = git log --diff-filter=A --format=%H -- CELL-v2.md
```

- Cells submitted (PR-merged or bot-committed) **after** the activation commit MUST be `crc.cell.v2`. CI rejects new v1-shaped Cells with a named rule.
- Every Cell that exists at activation — the v0 pair and the four v1 Cells on `#236` — **stands as frozen history**. Nothing is re-signed, nothing is invalidated; the v1 edge remains the first closed 3-way edge and its Cells remain verifiable exactly as minted.
- Same shape as the admission-ledger `deadline_policy_commitment` discipline: bind the rule to what was in force at the time; never let it shift retroactively.

## 5 · Everything else carries over

Result semantics (GREEN / RED / AMBER-abstains), the edge rule (≥2 GREEN byte-equal on distinct lanes), the pre-hash conformance gate, `as_of`/`recomputed_at` separation, boundary-in-payload, and derivable `evidence.independence` are unchanged from [CELL-v1.md](CELL-v1.md). Any change to this struct or these rules mints `crc.cell.v3`.
