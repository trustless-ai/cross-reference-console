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

## The semantics, settled by the group 2026-08-10

Before the binding could be built, the field turned out to be measuring the wrong
thing. **giskard**, whose lane the label had been applied to without asking:

> Chat membership and shared operatorship aren't the same fact, and right now
> `affiliations.json` treats them as one.

**Damon Zwicker** took it further, and this is the part that kills lane-global
labelling even with two fields:

> shared design context isn't a property of a lane — it's a **relation between a
> lane and a rule**. Fede's panel was independent for some specs and failed the
> bar for the one co-designed in real-time. So the question for #68 was never
> "is giskard inside trustless-ai" — it's "was argentum-core in the design
> context of the claim_id derivation rule specifically."

So there are two facts with different shapes:

```
shared_operator        lane x lane   same person or entity runs both
shared_design_context  lane x RULE   was in the room when THIS rule was set
```

**Pavlo Tvardovskyi** on how to get there, and the constraint that set the pace:

> I would not carry affiliation forward as one signed field — signing the
> ambiguity would only make the ambiguity immutable.
>
> lane declaration → signed binding → relation evaluation → verdict basis
> rather than: affiliation label → verdict.
>
> If either relation cannot be established, I'd rather leave that relation
> unresolved than infer independence from absence of evidence.

**Who declares:** the operator, bound in a signed Cell — with Pavlo's framing that
the signature establishes **who made the declaration, not that it is true**.
Absence never upgrades.

**Interim state, shipped 2026-08-10.** `pair_state` no longer consults affiliation
at all. Every pair past the ancestry checks returns `INDEPENDENCE_NOT_PROVEN`
with a basis naming **both** unresolved relations, so a reader can see which fact
is missing rather than a conflated label asserting something about someone else's
lane. `affiliations.json` remains published as advisory disclosure and informs no
verdict.

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
