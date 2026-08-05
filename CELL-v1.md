# Cell — the signed cross-verification (v1)

`crc.cell.v1` is the hardening layer over [`crc.cell.v0`](CELL.md), minted per the append-only discipline (v0 is frozen, never edited). It incorporates the five conformance points raised on the first live 2×1 edge (Pavlo, 2026-08-05): observation/evaluation time separation, full verifier-boundary binding, a universal pre-hash gate, recomputable independence evidence, and the operational AMBER/RED split. **The v0 first edge remains valid as v0** — v1 is the strict conformance surface new Cells sign against.

```
proof_payload (crc.cell.v1)
├── schema         "crc.cell.v1"
├── claim_id       the Claim being verified
├── result         GREEN | RED | AMBER          (see Result semantics)
├── verifier       the node's identity (ERC-8004 token id, or on-chain attestor address)
├── boundary       the ERC-8274 verifier lane    (NOW INSIDE the signed struct)
├── as_of          observation snapshot evaluated — MUST equal evidence.claim_preimage.as_of
├── recomputed_at  evaluation time — when THIS node ran (RFC3339 UTC)
└── evidence       { claim_preimage, recomputed{…}, recipe, independence{…}, … }
```

## 1 · Observation time ≠ evaluation time

`as_of` (what state of the world the claim is about) and `recomputed_at` (when this node evaluated it) are **both first-class signed fields** in v1. A Cell recomputed a year later carries the same `as_of` and a new `recomputed_at` — the later evaluation can never collapse into, or overwrite, the observation state. Rule: `proof_payload.as_of == evidence.claim_preimage.as_of`, byte-equal; a Cell violating this fails the gate and receives no verdict.

## 2 · Full verifier boundary in the signed struct

```jsonc
domain = { "name": "cross-reference-console", "version": "1", "chainId": 1 }

types.Cell = [
  { "name": "schema",        "type": "string"  },
  { "name": "claim_id",      "type": "string"  },
  { "name": "result",        "type": "string"  },
  { "name": "verifier",      "type": "address" },
  { "name": "boundary",      "type": "string"  },   // v1: lane is now signed
  { "name": "as_of",         "type": "string"  },   // v1: observation snapshot is now signed
  { "name": "recomputed_at", "type": "string"  },
  { "name": "evidence_hash", "type": "bytes32" }    // keccak256( utf8( JCS(evidence) ) )
]
```

**Triple equality (normative).** A v1 Cell verifies only if:

```
recoverTypedDataAddress(domain, {Cell}, cellStruct, sig)
  == signature.signer
  == proof_payload.verifier        (case-insensitive on hex addresses)
```

Any two matching without the third is a FAIL. In v0 the recovered signer was only checked against `signature.signer`, leaving `proof_payload.verifier` asserted; v1 closes that seam. (Node-1-style Cells bind the same way on their lane: the schnorr pubkey that verifies MUST be the pubkey the node's published verifier-keys document maps to `proof_payload.verifier`.)

## 3 · Pre-hash conformance gate (universal)

The gate runs **before any hashing, in every implementation** — Python reference, browser, any node. Identical behavior everywhere; an input rejected by the gate never receives a `claim_id` or an `evidence_hash`.

1. **Exact field set** — missing or unknown fields reject (fixed-set / null-not-absent discipline).
2. **No duplicate JSON members** — at any depth. JCS is only defined over unique members; parsers that silently keep the last member make two different byte-streams canonicalize identically. Implementations MUST detect duplicates on the raw text (e.g. `object_pairs_hook` in Python, a raw-text scanner in JS) — not on the already-parsed object, where the evidence is gone.
3. **Types** — per CLAIM.md v0 (strings non-empty, `claim_body` string|null, `claimant` int, bool is not int).
4. **Hash grammar** — `artifact_hash` MUST match `^[0-9a-f]{64}$` (lowercase hex, exactly 64). Prefixed forms (`sha256:…`, `0x…`) reject in this field.
5. **Claimant range** — `0 <= claimant < 2^256` (an ERC-8004 token id; negative or overflowing values reject).
6. **`as_of` strict** — RFC3339 UTC `YYYY-MM-DDTHH:MM:SSZ`, a real instant (month 13 rejects), second precision, no offsets.

## 4 · Independence evidence is recomputable, not asserted

v0's `independent_reimplementation: true` is metadata — a reader must take the node's word. v1 replaces it with an `evidence.independence` object from which independence is **derivable**. Every field is present; `null` means "not available", never omitted:

```jsonc
"independence": {
  "implementation": {                       // the node's OWN implementation of the derivation
    "repo":      "<url|null>",              //   where it lives (null for closed source…)
    "commit":    "<hex|null>",              //   pinned ref
    "path":      "<string|null>",           //   file within the repo
    "impl_hash": "<sha256:…|null>"          //   …but the hash is expected even then
  },
  "dependency_lock": "<sha256:…|null>",     // hash of the lockfile / env freeze the run used
  "runtime_image":   "<digest|null>",       // container/image digest the run executed in
  "inputs": [                               // every external input the derivation consumed
    { "url": "<url>", "content_hash": "<sha256:…>", "retrieved_at": "<rfc3339-utc>" }
  ],
  "execution_witness": "<ref|null>"         // transcript hash, attestation, or log ref for the run itself
}
```

Two Cells are **demonstrably independent** when their `implementation` refs differ (different repo/commit/hash) and their `inputs` carry the same `content_hash` for the same source URL — same input, different machinery, same output. A reader derives this; nobody asserts it.

## 5 · AMBER is operationally separate from RED

| Result | Meaning | Class | Effect on an edge |
|---|---|---|---|
| **GREEN** | every derivation check passed | validity | counts toward the edge |
| **RED** | a derivation **mismatch** — recomputed value ≠ published value, or a signature fails against present material | validity | **breaks** the edge |
| **AMBER** | could not observe — source unavailable, policy/profile unknown to this node, boundary unreachable | observation / availability | **abstains** — never breaks, never counts |

RED is evidence of inconsistency. AMBER is absence of observation — a network failure is not a mismatch. Implementations MUST NOT emit RED for an unreachable source, and MUST NOT emit AMBER for a hash that was computed and differs.

**Edge rule (v1).** An edge holds when ≥ 2 Cells are GREEN with byte-equal `claim_id` on distinct lanes/implementations. AMBER Cells abstain. Any RED on the claim breaks the edge until reconciled.

## First v1 Cell — node 2 LANDED (2026-08-05)

[`reference/vectors/236-node2-cell.v1.signed.json`](reference/vectors/236-node2-cell.v1.signed.json) — the first `crc.cell.v1` Cell, signed inside the Vértice gateway container (attestor `0x85Fa…Bf1A`, key never left the box). `claim_id` and `decision_ref` re-derived live from `/ledger #236` through the gate; `evidence.independence` carries the real refs (implementation pinned at [`a82f8f1`](https://github.com/trustless-ai/cross-reference-console/commit/a82f8f10b3ae870195e0fd12d92ab45125e19fd8) + file hash, `bun.lock` hash, runtime image digest, content-hashed inputs, and an execution witness that recomputes from [the published run transcript](reference/vectors/236-node2-cell.v1.transcript.json)). Verified off-box on two independent stacks (`ethers`, `eth_account`) plus the Python reference.

**The v1 edge abstains** until node 1 publishes its v1 Cell — per §5 that is a pending observation, not a break. The v0 edge stands as frozen history either way.

## Versioning

`crc.cell.v0` remains frozen; the #236 v0 Cells stand as the first edge. New Cells SHOULD sign v1. Any change to this struct or these rules mints `crc.cell.v2`.
