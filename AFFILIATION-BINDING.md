# Binding affiliation — the agreed shape, not yet built

**Status:** design agreed 2026-08-10, unimplemented. `INDEPENDENT` is gated off
until it exists (`reference/lineage_graph.py`).

## The gap

`affiliation` is read from an advisory file at evaluation time. No signed Cell
binds it. Demonstrated rather than argued (@pipavlo82's audit):

```
before:  invinoveritas × vertice-recompute-lens: INDEPENDENCE_NOT_PROVEN
edit one line of an unsigned file — no Cell touched, no signature touched
after :  invinoveritas × vertice-recompute-lens: INDEPENDENT
and both Cells still validate
```

A historical pair could be upgraded to the strongest verdict in the system by
editing a file nobody signed, with nothing detecting it.

## The interim behaviour

`INDEPENDENT` is unreachable. Affiliation can only **demote** a pair to
`INDEPENDENCE_NOT_PROVEN`. That asymmetry is what makes it safe to read an
unsigned file at all: an edit cannot manufacture a stronger claim, only a weaker
one. The basis text says the gate is the reason, so it is never mistaken for an
ordinary absence of evidence.

## The agreed permanent fix

**@babyblueviper1, 2026-08-10:**

> have the next Cell version sign a `nodes_snapshot_hash` — a canonical hash of
> the relevant node entries (`affiliation`, `lane`, `key_ref`) **as they read at
> signing time** — inside the signed content, same as `claim_id`/`registry_id`
> already are. Independence evaluation then reads affiliation from the Cell's
> **own committed snapshot**, not from live `nodes.json` — a later edit to
> `nodes.json` can't retroactively reinterpret a Cell that already pinned what it
> believed at the time.

**@pipavlo82, 2026-08-10** — versioned, never widening what is frozen:

> `crc.nodes.v1` plus a signed registry-snapshot commitment in the next Cell
> version. Until then, the fail-closed gate is the correct behavior.

Both land on the same place: **the commitment belongs on the Cell side, where the
interpretation happens.** `crc.nodes.v0` stays frozen — append-only genesis
unchanged — and the new field lives on the Cell.

It is the house rule applied to our own registry: *don't trust the live mutable
file; commit what you actually saw.* A Cell already does this for its claim and
its inputs. Affiliation was the one input still read live at evaluation time.

## What must be true before the gate lifts

- a Cell version carrying `nodes_snapshot_hash` over a canonical projection of
  the relevant node entries
- `pair_state` reading affiliation from **the Cell's committed snapshot**, never
  from the live file
- a vector proving a post-signing edit to the live file **cannot** change a
  historical pair's verdict — the exact mutation demonstrated above, expected to
  fail
- the gate removed only once that vector passes, so lifting it is itself
  evidenced rather than asserted
