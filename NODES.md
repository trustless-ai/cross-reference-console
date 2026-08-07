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
  "cell_url_template": "<url|null>",   // where this node serves a Cell for a claim: {claim_id_hex} placeholder
                                       //   ({claim_id_hex} = the 64-hex digest, no "sha256:" prefix — ":" breaks Windows paths).
                                       //   null ⇒ the node delivers by PR into cells/ (see below)
  "since":    "<rfc3339-utc>",         // when the lane opened
  "retired":  "<rfc3339-utc|null>"     // tombstone — a retired node's past Cells remain valid history
}
```

## Cell delivery contract

For each new claim in `claims/`, a node produces a signed **crc.cell.v1** Cell and delivers it one of two ways:

1. **In-repo (default):** PR (or bot commit) to `cells/{claim_id_hex}/{node_id}.cell.json` (hex digest only — no `sha256:` prefix in paths). The repo is the registry; CI (the same public watcher) validates envelope + gate before merge.
2. **Self-hosted:** serve it at `cell_url_template` with `{claim_id_hex}` substituted. The console fetches it live; unreachable ⇒ **pending-abstain** (AMBER discipline — never treated as failure). The endpoint contract is below.

Either way the Cell must verify under its envelope's recipe: `nostr-nip01` → NIP-01 id + BIP-340 schnorr vs `key_ref.pubkey`; `eip712` → triple equality vs `key_ref.address` (CELL-v1.md §2). A Cell that fails its envelope check is recorded in `cells/rejected/` with the error — non-suppression, same as claims.

## The self-hosted endpoint contract

What `cell_url_template` must actually do. Derived from the consumer rather than
invented: the console is a static page that fetches your URL from the browser,
strict-parses the body, and verifies the Cell client-side.

| requirement | detail |
|---|---|
| **Method / auth** | plain `GET`, no auth, no cookies. The URL is the whole request |
| **Status** | any non-2xx is treated as **unreachable**, not as a bad Cell |
| **CORS** | `Access-Control-Allow-Origin` **MUST** permit the console's origin. See the trap below |
| **Body** | the Cell JSON exactly as signed, byte-for-byte |
| **Duplicate keys** | rejected — the console strict-parses, same rule as the pre-hash gate |
| **Content-Type** | **not constrained.** The reference endpoint serves `text/plain` and works fine; the body is read as text and parsed |
| **Caching** | the console sends `cache: no-store`. Serve current bytes; a stale cache silently publishes a superseded Cell |

### The CORS trap, stated plainly

The console runs in a browser, on a different origin from your node. **An endpoint
with no CORS header is unreachable to it while being completely healthy** — you
will `curl` it successfully, see 200, and still show as pending-abstain.

That failure presents as downtime and is a header. If your column is AMBER and
your service is up, check this first:

```bash
curl -sI "https://your.node/cells/<64-hex>.json" | grep -i access-control-allow-origin
```

The reference endpoint (`raw.githubusercontent.com`) returns
`access-control-allow-origin: *`, which is why node 2's self-hosted lane works.

### What unreachable means

Nothing bad. Unreachable ⇒ **pending-abstain**: the edge waits, it does not break,
and no verdict is recorded against you. Could-not-fetch is never a RED, in the same
way could-not-check is never a pass. Downtime is not a judgement.

### Bytes, not equivalents

Serve the Cell you signed, unchanged. Re-serialising it — reordering keys,
re-indenting, dropping a null — changes `evidence_hash` and the signature no longer
recovers. The console will report a real mismatch, and it will be right.

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

## crc.cell.v2 (in force)

As of the activation commit (`git log --diff-filter=A -- CELL-v2.md`), **newly submitted Cells MUST be `crc.cell.v2`** — see [CELL-v2.md](CELL-v2.md). Cells that existed at activation stand as frozen history and are never re-judged; CI enforces the rule against *newly added* files only.

A v2 Cell carries `registry_id` inside its signed payload, and it MUST equal this registry's identity:

```
sha256:9b871ba9cf05e9da7df78e0b15d44fc04059e6af4bda8037d6f456984598d157
```

Don't take that constant on faith — derive it: `python3 reference/registry_id.py` (JCS of the genesis `nodes.json`, whose commit is itself derived via `git log --diff-filter=A -- nodes.json`).

## Versioning

`crc.nodes.v0`. Field changes mint `crc.nodes.v1`; instances are validated with the same strictness as ClaimPreimages (exact field set, no duplicates, unknown fields reject).
