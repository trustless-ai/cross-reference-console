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

## Two verdicts, not one

@boardyai, 2026-08-13 — raised in public, with no commit access:

> The pin proves reproducibility of a commit, while contenthash proves what users
> resolve today. Those need separate verdicts, or a green repo can still ship
> yesterday's page.

The rule above governs the first claim. A CID earns a pin when two independent parties
rebuild the stated commit and reach the same bytes, and `reference/verify_pin.py` is what a
third party runs to check that without trusting whoever wrote the record.

None of it governs the second. Every pin record can be valid, CI green on `main`, and the
contenthash still resolving to an earlier build — all true at once, and none of it wrong,
because nothing here ever claimed currency. That is not a loophole; it is a claim we had not
written down, which is worse, because the first verdict reads like it covers both.

So currency is its own verdict, with its own three outcomes. The third is not optional, for
the same reason AMBER is not optional above:

| verdict | meaning |
|---|---|
| `CURRENT` | the resolved contenthash CID equals the CID of the deterministic build of `main` |
| `STALE` | both were computed and they differ — determinate. Reports **both CIDs and the commit range between them** |
| `UNDETERMINED` | it could not be computed, with a **required reason**: `resolver_unreachable` or `no_local_ipfs` |

Two refinements from @babyblueviper1, 2026-08-14, both of which change what the check has to
emit rather than how it is displayed.

**STALE reports the range, not only the difference.** Two CIDs prove they differ; the commit
range is what a human needs to judge whether this is one missed pin or a month of accumulated
drift, and those want different reactions.

**UNDETERMINED carries a reason, and stays one verdict.** "The resolver did not answer" and "I
have no `ipfs` binary" are the same display and different next actions, so the cause has to
survive into the output — but as a required field, not a fourth verdict. Splitting the
vocabulary gets you a fifth entry next month; a reason field does not. This is the same shape
as the third state itself, one level down: we separated true from false, and the separator
immediately needed separating.

The consumer rule, in his words, so nobody re-collapses it later:

> **CURRENT is the only pass. STALE is a determinate fail naming both CIDs. UNDETERMINED is
> don't-act rather than a silent not-current.**

A staleness check that cannot say "I could not look" fails in exactly the way this document
exists to prevent.

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

## What the record covers

The contenthash is a **directory** CID — every published file, not one page. The
first version of this record covered `ui/index.html` alone, which meant a
confirmation on it said nothing about the other twenty-eight files in the tree.

So a record declares its `artifact_kind`:

- **`site-tree`** — the real thing. Names the landing repo and commit, and carries
  a `tree_sha256` over every published file. Verifying it clones that commit,
  checks the console page **is the build of its own locked commit** (otherwise the
  tree holds a hand-copied file and reproduces only by luck), then derives the tree
  hash and the directory CID.
- **`file`** — a single artifact. Useful for testing the machinery; not what gets
  pinned.

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
  "confirmations": [              // >= 2 SIGNED, from distinct registered nodes
    {
      "node_id": "vertice-recompute-lens",
      "rebuilt_at": "2026-08-09T14:00:00Z",
      "file_sha256": "sha256:…",  // what THIS party got, independently
      "cid": "bafkrei…",
      "signature": "0x…"          // by the node's REGISTERED key; unsigned = AMBER
    }
  ],
  "pinned_at": null,              // set when the contenthash transaction lands
  "tx": null
}
```

A confirmation is a claim that **you personally ran the build and got these
values** — not that you read them in this file and agreed. If you did not run it,
do not add your node.

### What a signature covers (crc.pin-confirmation.v2)

**Everything the confirmer asserts, plus the record context — by construction,
not by a list.**

This took two rounds of review to get right, and the way it failed is the useful
part. v0 enumerated the signed fields and omitted `conf["cid"]`, which counting
acted on. v1 added `conf["cid"]` to the list — and the *same commit* introduced
`conf["tree_sha256"]`, also unenumerated, also the field counting acts on for a
site tree. The identical defect, reintroduced while fixing it.

A hand-maintained allowlist has to be updated every time a field is added, and
nothing fails when someone forgets. v2 signs the whole confirmation minus its own
signature, plus the record's identifying context including `cid_params`. A field
that does not exist yet is covered the moment someone adds it.

*Fixing the instance is not fixing the class, and the difference is invisible
until the second instance arrives.*

### Confirmations must be signed (revised 2026-08-09 after review)

They were briefly unsigned, on my argument that `verify_pin.py` rebuilds the
commit itself, so a forged confirmation could never make a *bad* CID verify.

That argument is true and it defends the wrong property. Pavlo's review named it:
the rule is **no unilateral pin**, and one writer authoring both entries defeats
exactly that. Two self-consistent confirmations naming two registered nodes would
have reached GREEN with a single author. Byte integrity was enforced; the
two-party property was left as policy while reading as mechanism — which is worse
than an obvious gap, because the tool said GREEN.

So a confirmation is now signed by the confirming node's **registered** key, in
its registered envelope, exactly as a Cell is. The signature covers the CID, the
commit, the artifact, the confirmed bytes, the node_id and the timestamp, so it
cannot be lifted onto a different pin record.

An **unsigned** confirmation is AMBER and does not count toward the two — never
silently ignored, and never a pass.

The general lesson, which is the one worth keeping: *checking integrity is not
the same as checking authorship, and a rule about who agreed cannot be satisfied
by a check about what the bytes are.*

## Confirming one

```bash
export CRC_KEY=0x<your key>      # env, never a flag
python3 reference/sign_confirmation.py --record pins/<cid>.json --node yournode
```

It rebuilds the record's commit **itself** and refuses to sign if your rebuild
disagrees, so you cannot confirm bytes you never produced. That refusal is the
point: the disagreement is the finding, and working around it defeats the rule.

## What a verifier will and will not run

Verifying a `site-tree` record **executes build code from the cloned repo.** So
the repo is not chosen by the record: `verify_pin.py` carries an allowlist, and a
record naming anything else is **RED** — not AMBER, because this is not something
that could-not-be-checked, it is something that must not be run.

A pin record is untrusted input. The people who run this tool are exactly the
people we ask to check work they did not author, and letting the artifact select
what code executes on their machine would turn every honest verifier into a
target.

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
