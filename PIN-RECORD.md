# Pin records — how the console gets published

The ENS contenthash is **the one pointer in this stack that is not recomputable.**
Every other value here — `claim_id`, `evidence_hash`, the signer, the edge — a
stranger can re-derive from primary sources. The pin is a transaction we send,
pointing at bytes we chose. And the console's embedded snapshot is the matrix's
*primary* data source, so bytes that were tampered with would render fabricated
nodes and fabricated GREEN cells under the org's own domain, looking exactly like
real ones.

So the pin gets the same treatment as everything else: **don't trust, recompute.**

## The rule

**No unilateral pin.** A CID is pinned only when **two independent parties have
each rebuilt the stated commit and got the same bytes and the same CID.**

Chosen over a multisig contract deliberately (Pavlo's framing, and Fede's): it
preserves the property we actually care about — no one person can point the
domain wherever they like — without a heavier governance mechanism than we need.
If it becomes operationally painful, multisig is still there.

## The trap: identical bytes do not mean identical CID

This is the part that will bite two honest people, so it is stated before the
format rather than after.

`ipfs add` derives a CID from the bytes **and from its own parameters.** The same
file gives:

| how it was added | CID |
|---|---|
| `--cid-version=1` | `bafkreiegd4sdqn3ocbwxij7fwgr7a4fh4ghmzadtnvlrzhakrlqfyamd4m` |
| `--cid-version=0` | `QmeUGvZWbBwvRaZouchPFUJtyZLoGBuLYWC3bsEaeu4ybZ` |
| `--cid-version=1 -w` (wrapped in a directory) | `bafybeigdabc3gddkpz6jwjtha4pos2bgb5sykfdnyrnjhvfmpvraggi45i` |

Same bytes every time — `sha256:861f2438…` in all three rows.

Two people can therefore both faithfully rebuild the same commit, produce
byte-identical files, report different CIDs, and each conclude the other made a
mistake. The chunker and hash function have the same effect.

**So a confirmation carries both**: the file's `sha256` (which depends only on the
bytes) *and* the CID (which depends on the bytes and the parameters). The sha256
is what proves two rebuilds agree; the CID is what gets pinned. If two
confirmations agree on sha256 but not CID, the disagreement is in the parameters
and nothing is wrong with the page.

## The record

One file per pin, `pins/<cid>.json`, append-only:

```jsonc
{
  "schema": "crc.pin-record.v0",
  "cid": "bafkrei…",              // what the contenthash will point at
  "commit": "<40-hex>",           // the commit that was built
  "artifact": "ui/index.html",
  "file_sha256": "sha256:…",      // depends on bytes alone
  "cid_params": {                 // without these the CID is not reproducible
    "cid_version": 1,
    "wrap_with_directory": false,
    "raw_leaves": true,
    "chunker": "size-262144",
    "hash": "sha2-256"
  },
  "confirmations": [              // >= 2, from distinct registered nodes
    {
      "node_id": "vertice-recompute-lens",
      "rebuilt_at": "2026-08-09T14:00:00Z",
      "file_sha256": "sha256:…",  // what THIS party got, independently
      "cid": "bafkrei…"
    }
  ],
  "pinned_at": null,              // set when the contenthash transaction lands
  "tx": null
}
```

A confirmation is a claim that **you personally ran the build and got these
values** — not that you read them in this file and agreed. If you did not run it,
do not add your node.

## Verifying one

```bash
python3 reference/verify_pin.py pins/<cid>.json
```

It checks out the stated commit into a scratch worktree, rebuilds, hashes, and —
if an `ipfs` binary is present — recomputes the CID with the recorded parameters.
Then it checks that at least two confirmations from **distinct registered nodes**
agree with what it just derived.

It reports **AMBER**, never a pass, when it cannot check something — no `ipfs`
binary, or a commit it cannot fetch. Could-not-check is never a pass, the same
discipline as everywhere else here.

## Why the build had to become deterministic first

None of this works unless building a commit twice gives the same bytes. Until
[#18](https://github.com/trustless-ai/cross-reference-console/pull/18) it did not:
the snapshot stamped wall-clock build time, so two rebuilds of one commit differed
and no confirmation could ever match another. `crc.console-snapshot.v1` derives
the timestamp from the newest observation in the data instead, and
`reference/check_console_reproducible.py` keeps it that way in CI.
