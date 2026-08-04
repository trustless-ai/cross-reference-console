# Cell — the signed cross-verification (v0)

A `Cell` is one node's **independently recomputed** verdict on one `Claim` (see [`CLAIM.md`](CLAIM.md)), signed so anyone can recover the signer and re-derive every field. A row of Cells across nodes is the Matrix. **Never a bare green** — a Cell without a recomputable evidence body is not a Cell.

```
proof_payload (crc.cell.v0)
├── schema         "crc.cell.v0"
├── claim_id       the Claim being verified (== sha256:df1a6bfe… for #236)
├── result         GREEN | RED | AMBER   (derived from evidence, never asserted)
├── verifier       the node's identity: an ERC-8004 token id (node 1) or the on-chain agent/attestor address (node 2)
├── boundary       the ERC-8274 verifier lane this node used (recompute/* | attestation/* | tee/* | zk/*)
├── recomputed_at  RFC3339 UTC
└── evidence       { claim_preimage, recomputed{…}, recipe, note, source_ledger_entry, cross_check, … }
```

## Two signature envelopes, one payload

The `proof_payload` is identical across nodes; only the **signature layer** differs by node infrastructure. Both are recomputable, neither is privileged.

- **Node 1 (Fede, `/verify-proof`, verifier `54848`)** — schnorr over the payload, wrapped as a **Nostr** event (NIP-01 `id = sha256([0,pubkey,created_at,kind,tags,content])`). Lane: `attestation/invinoveritas`.
- **Node 2 (Vértice recompute-lens)** — **EIP-712** over the Cell struct below, signed by the gateway **attestor** key (the same key that signs L4 execution attestations). Lane: `recompute/cross-reference-console`.

That the same `claim_id` (`df1a6bfe…`) carries across an **attestation** lane and a **recompute** lane, each independently reproduced, is the point of the 2×1 matrix.

## EIP-712 (node 2)

```jsonc
domain = { "name": "cross-reference-console", "version": "0", "chainId": 1 }

types.Cell = [
  { "name": "schema",        "type": "string"  },
  { "name": "claim_id",      "type": "string"  },
  { "name": "result",        "type": "string"  },
  { "name": "verifier",      "type": "address" },   // node 2's on-chain agent/attestor address
  { "name": "recomputed_at", "type": "string"  },
  { "name": "evidence_hash", "type": "bytes32" }   // keccak256( utf8( JCS(evidence) ) )
]
```

`evidence_hash` binds the full evidence body into the signed struct while keeping the wallet-legible fields (`claim_id`, `result`, `verifier`) in the clear. For #236: `evidence_hash = 0xe4a98e481700cd62ae8dd6c85341c28e042ade7375a0024a5501a358afa4f76a`.

### Recompute a node-2 Cell (anyone)
1. `keccak256(utf8(JCS(evidence))) == evidence_hash` → the evidence is intact.
2. `recoverTypedDataAddress(domain, {Cell}, cellStruct, sig) == ` the gateway attestor address → the signer is the Vértice node.
3. Re-run the evidence yourself: `claim_id(claim_preimage) == claim_id` and `decision_ref` re-derives from `/ledger #236` → `result` is earned, not asserted.

## v0 first edge — **LANDED (2026-08-04)**

`#236` now has **two independently-signed Cells on two lanes** = the first live 2×1 matrix:

| Node | Verifier | Lane | Signature | Cell |
|---|---|---|---|---|
| 1 (Fede, `/verify-proof`) | `54848` | `attestation/invinoveritas` | schnorr / Nostr | `api.babyblueviper.com/verdict-proofs/5f6b6d7c…` |
| 2 (Vértice recompute-lens) | `0x85Fa…Bf1A` | `recompute/cross-reference-console` | EIP-712 | [`reference/vectors/236-node2-cell.signed.json`](reference/vectors/236-node2-cell.signed.json) |

Both carry `claim_id sha256:df1a6bfe…`, each independently reproduced (node 2 re-derived both `claim_id` **and** `decision_ref` from the `/ledger #236` source, not from node 1's Cell). Node 2's signature was produced **inside the gateway container** — the attestor key never left the box — and recovers to `0x85Fa…Bf1A` off-box (`eth_account`, `ethers`). Any change to the struct mints `crc.cell.v1` — v0 is append-only.
