# nodes.json — the node & intake registry (crc.nodes.v0)

The registry the console renders columns from, and the contract a node accepts by registering. Same disciplines as everything else here: **fixed field set, null-not-absent, append-only** (removing a node is a tombstone flag, never a deletion — a departed node is a derivable fact).

**To register: one PR adding one object to `nodes` in [`nodes.json`](nodes.json).** If the PR parses, conforms, and the key reference is checkable, it merges. No other approval step.

## Node object

```jsonc
{
  "node_id":  "<short-slug>",          // stable id; also the cell filename component
  "display":  "<string>",              // human label for the column header
  "verifier": <int | "0x…">,           // EXACTLY as it appears in the node's Cell proof_payload.verifier
                                       //   (ERC-8004 token id as integer, or on-chain attestor address)
  "lane":     "<erc8274-family/instance>",  // e.g. attestation/invinoveritas · recompute/cross-reference-console
  "envelope": "nostr-nip01" | "eip712",     // signature envelope; verification recipe per CELL.md / CELL-v1.md
  "key_ref": {                         // how anyone checks this node's signatures — must be checkable, not asserted
    "pubkey":   "<hex|null>",          //   nostr-nip01: BIP-340 pubkey
    "address":  "<0x…|null>",          //   eip712: attestor address
    "keys_url": "<url|null>"           //   published key document, if any
  },
  "cell_url_template": "<url|null>",   // where this node serves a Cell for a claim: {claim_id} placeholder.
                                       //   null ⇒ the node delivers by PR into cells/ (see below)
  "since":    "<rfc3339-utc>",         // when the lane opened
  "retired":  "<rfc3339-utc|null>"     // tombstone — a retired node's past Cells remain valid history
}
```

## Cell delivery contract

For each new claim in `claims/`, a node produces a signed **crc.cell.v1** Cell and delivers it one of two ways:

1. **In-repo (default):** PR (or bot commit) to `cells/{claim_id}/{node_id}.cell.json`. The repo is the registry; CI (the same public watcher) validates envelope + gate before merge.
2. **Self-hosted:** serve it at `cell_url_template` with `{claim_id}` substituted. The console fetches it live; unreachable ⇒ **pending-abstain** (AMBER discipline — never treated as failure).

Either way the Cell must verify under its envelope's recipe: `nostr-nip01` → NIP-01 id + BIP-340 schnorr vs `key_ref.pubkey`; `eip712` → triple equality vs `key_ref.address` (CELL-v1.md §2). A Cell that fails its envelope check is recorded in `cells/rejected/` with the error — non-suppression, same as claims.

## Intake object (`claim_sources`)

```jsonc
{
  "source_id": "<short-slug>",
  "url":       "<url>",                // where submissions enter
  "admission": "<string>",             // the anti-spam economics, stated plainly (e.g. "sats per entry")
  "lifts":     ["review_verdict"],     // claim types this intake can lift into a ClaimPreimage
  "since":     "<rfc3339-utc>",
  "retired":   "<rfc3339-utc|null>"
}
```

v0.2 is **ledger-only** by group decision (2026-08-05): one admission mechanism first, so a `claims/` mismatch is unambiguously a gate bug. Adding an intake later is a PR to this file, not a rework. Admission never decides validity — the gate does.

## Versioning

`crc.nodes.v0`. Field changes mint `crc.nodes.v1`; instances are validated with the same strictness as ClaimPreimages (exact field set, no duplicates, unknown fields reject).
