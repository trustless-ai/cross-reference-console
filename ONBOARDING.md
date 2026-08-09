# Joining the mesh

How to go from nothing to a Cell that other nodes accept.

This document exists because someone tried it and couldn't. The four founding
nodes were built by people who wrote the spec together, so the path between
"read `CELL-v2.md`" and "produce a Cell" was never written down — it lived in
shared context. [PR #7](https://github.com/trustless-ai/cross-reference-console/pull/7)
walked that path from outside and reported where it broke. This is the answer to
gap 2; the tool in step 6 is the answer to gap 1.

Nothing here needs anyone's permission except step 3.

---

## 0 · What you are joining

A **Claim** is a statement someone made, content-addressed by its preimage.
A **Cell** is *one node's independently recomputed verdict* on one Claim, signed.
An **edge** holds when ≥ 2 Cells are GREEN with a byte-equal `claim_id` on
**distinct implementations** — distinct being derived from evidence, not from
the lane name ([`PROPOSAL-lane-distinctness.md`](PROPOSAL-lane-distinctness.md)).

The point is not that we agree. It is that a stranger can re-run every step and
get the same bytes. **Never a bare green** — a Cell without a recomputable
evidence body is not a Cell.

## 1 · Get a verifier identity

Whatever you sign with, and it must be checkable by a reader:

| envelope | identity | `key_ref` |
|---|---|---|
| `eip712` | an Ethereum address | `address` set, `pubkey` null |
| `nostr-nip01` | a BIP-340 x-only pubkey | `pubkey` set, `address` null, `keys_url` where you publish it |

An ERC-8004 token id also works as the `verifier` if your lane is attestation-based
(node 1 uses `54848`).

**If your contract isn't deployed yet, stop here and say so.** You cannot register
an identity you cannot sign with, and no part of this rewards pretending otherwise.

## 2 · Choose your lane

`family/instance`, e.g. `recompute/yourname` or `attestation/yourservice`.

The lane string is a **label, not a claim**. What makes your lane distinct from
another node's is your `evidence.independence` — a different `impl_hash` and a
different `repo`. Two nodes running one implementation under two names produce an
edge worth nothing, and `reference/check_lane_distinctness.py` now catches that.

So: write your own implementation of the derivation. Reading our spec is the
point; copying `reference/claim_id.py` is not.

## 3 · Register your node

One PR adding one object to `nodes` in `nodes.json`:

```jsonc
{
  "node_id":  "yournode",
  "display":  "Node N — Your Thing (You)",
  "verifier":  "0x…",            // address, or an ERC-8004 token id
  "lane":      "recompute/yournode",
  "envelope":  "eip712",          // or "nostr-nip01"
  "key_ref":   { "pubkey": null, "address": "0x…", "keys_url": null },
  "cell_url_template": null,      // or where you self-host, see step 8
  "since":     "2026-08-07T00:00:00Z",
  "retired":   null
}
```

Every field is present; `null` means "not applicable", never omitted. CI checks
the shape:

```bash
python3 reference/validate_nodes.py
```

This is the only step that needs anyone else. It is a mechanical review — if CI
is green it merges.

## 4 · Pick a Claim

Everything in `claims/` is fair game. Start with one that already has Cells: you
get an immediate answer about whether your implementation agrees with two
independent ones.

> **Open limitation, stated plainly.** Claim intake is currently ledger-only by
> group decision (2026-08-05), so you can verify existing Claims but cannot yet
> introduce your own. That is gap 5 from PR #7 and it is a live question for the
> group, not a settled design. If you need a Claim that isn't there, say so —
> that is useful pressure, not an inconvenience.

## 5 · Recompute it — the part that matters

Read the Claim's `source_url`, fetch the source **yourself**, and derive the
`claim_id` with **your own code**.

Do not import ours. Do not check our answer first. The value of your Cell is
that it was produced without reference to the value it is confirming, and you
are the only person who can know whether that was true.

Then check yourself against `reference/claim_id.py` — after you have your own
answer, not before.

> **This applies to your second Cell as much as your first, and that is where it
> actually goes wrong.** Onboarding gets read once, when you join. The mistake
> lands months later on a routine Cell, when you are not reading this page and
> you reach for whatever is closest — which is often this repo, already checked
> out because it is where Cells get submitted. `create_cell.py` now refuses a Cell
> citing this repo's implementation as your own lane, so the tool catches it
> rather than CI catching it after you have recomputed, signed and pushed.

## 6 · Create and sign the Cell

`create_cell.py` emits the **in-force** schema — derived from enforcement state,
not from whether a spec file exists on disk:

```bash
python3 reference/registry_id.py   # prints in-force schema + activation commits
```

Until v3 is **both minted and enforced** ([`CELL-v3.md`](CELL-v3.md) §5.1 — spec landed
**and** enforcement marker present), new Cells remain **`crc.cell.v2`**. Merging
`CELL-v3.md` alone does not activate v3 admission; landing enforcement alone does not either.

```bash
export CRC_KEY=0x<your key>      # env, never a flag: flags land in shell history

python3 reference/create_cell.py \
    --claim    claims/<claim_id>.json \
    --node     yournode \
    --result   GREEN \
    --boundary "ERC-8274 recompute/yournode — claim_id re-derived from the live
                source with my own implementation; envelope validity out of scope" \
    --evidence my-evidence.json
```

It builds the payload, binds `registry_id`, computes `evidence_hash`, signs in
your envelope, writes to `cells/<claim-digest>/<node_id>.cell.json`, **and then
validates its own output**. If it doesn't pass, the file is deleted.

Your evidence body needs at least:

```jsonc
{
  "claim_preimage": { … },        // byte-identical to the Claim you verified
  "recomputed":     { … },        // what you derived, and from what
  "independence": {
    "implementation": { "repo": "…", "commit": "…", "path": "…", "impl_hash": "sha256:…" },
    "dependency_lock": null,      // present, null if you have none
    "runtime_image":   null,
    "derived_from":    [],         // crc.cell.v3 only — [] declares no known derivation (signed, not proof)
    "inputs": [ { "url": "…", "content_hash": "sha256:…", "retrieved_at": "…" } ]
  }
}
```

**On `--boundary`:** it is prose, and it is read by humans. Say what you checked
*and what you did not*. Node 3's boundary explicitly records that it used a
from-scratch canonicalizer and **not** `reference/claim_id.py` — which is exactly
the kind of thing that makes an edge mean something.

**On `--result`:** `AMBER` is a real answer, not a failure. If you couldn't reach
the source, or couldn't establish something, AMBER abstains and the edge waits.
Could-not-check is never a pass, and it is never a fail either.

## 7 · Validate

`create_cell.py` already ran this, but run it again whenever you touch anything:

```bash
python3 reference/validate_cell.py cells/<digest>/<yournode>.cell.json
```

The check count varies by envelope and schema version, so it isn't quoted here —
run it and read the list. The one that matters most is the same everywhere: the
recovered signer must equal `signature.signer`, `proof_payload.verifier`, **and**
the address you registered. There is no way to sign a Cell as someone else, or as
nobody.

## 8 · Publish

Two options, and you may do both:

**PR into `cells/`** — the file lands in this repo and CI re-runs every check.

**Self-host** — serve it at your `cell_url_template` with `{claim_id_hex}`
substituted. The console fetches it live, from a browser, cross-origin.

**Read [`NODES.md` → the self-hosted endpoint contract](NODES.md) before you do.**
The one that catches people: **without a permissive `Access-Control-Allow-Origin`
header your endpoint is unreachable to the console while being completely
healthy** — you will `curl` it, get a 200, and still show pending-abstain. Serve
the same bytes the validator accepted, unchanged.

> If your endpoint is unreachable the console records **pending-abstain**, never
> a failure — the AMBER discipline again. Downtime is not a verdict against you.

---

## When it goes wrong

| what you see | what it means |
|---|---|
| `node 'x' is not in nodes.json` | do step 3 first |
| `claim_id recomputes` fails | your derivation differs from ours — **do not just copy ours.** That disagreement is a finding; report it |
| `quadruple equality` fails | `CRC_KEY` isn't the key for the address you registered |
| `pre-hash gate` fails | the Claim preimage is malformed — check `CLAIM.md`'s field rules |
| `v2 registry_id` fails | you built against a different registry instance, or a fork |
| a GREEN Cell is refused | you didn't supply `recomputed` + `independence`. That guard is deliberate |

## Where to read more

- [`CLAIM.md`](CLAIM.md) — the Claim preimage and its gate
- [`CELL.md`](CELL.md) → [`CELL-v1.md`](CELL-v1.md) → [`CELL-v2.md`](CELL-v2.md) (→ [`CELL-v3.md`](CELL-v3.md) when minted) — appended never rewritten. **Sign the in-force schema** (`registry_id.py`); earlier versions remain valid frozen history, never re-signed
- [`NODES.md`](NODES.md) — the registry and intake contract
- [`PROPOSAL-lane-distinctness.md`](PROPOSAL-lane-distinctness.md) — what makes two lanes actually distinct

*Something here wrong or missing? That is worth a PR on its own. This document
exists because someone reported it missing rather than working around it.*
