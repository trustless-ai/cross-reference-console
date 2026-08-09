#!/usr/bin/env python3
"""Stable source projection — the cross-node comparison value for a mutable source.

## The problem this closes

`evidence.independence.inputs[].content_hash` hashes the whole fetched response.
For a live endpoint that is provenance of ONE fetch and nothing more, but it
*reads* like "we all verified the same bytes". On claim df1a6bfe, four honest
nodes recorded four different values for one URL:

    6cb8dc90…  vertice-recompute-lens   2026-08-05T18:20Z
    6cb8dc90…  receiptos-recompute      2026-08-05T21:26Z
    bc3afa72…  mycelium-anchorregistry  2026-08-06T13:41Z
    aac7fcc7…  invinoveritas            2026-08-08T20:01Z

Nothing was wrong: the source carries `relay_anchor.checked_at`, refreshed
server-side on a slow cadence. But the divergence is invisible in the field's
own terms, so a later auditor reads four values as disagreement — or worse,
someone "reconciles" it by copying another node's hash, signing a claim about
bytes they never fetched.

## Why INCLUSION, not exclusion

The obvious fix is to hash everything except the fields known to move. It does
not survive contact: a field that did not exist when the rule was written
silently defeats it. Verified against the live source —

    exclusion projection, source gains one new volatile field  -> BROKEN
    inclusion projection, same change                          -> STABLE

An exclusion list has to be right about everything the source will ever add. An
inclusion list has to be right about what the claim rests on, which is knowable
and already written down. So a projection NAMES the fields it pins, and anything
outside them — anchors, freshness probes, whatever the operator adds next — is
outside by construction rather than by having been anticipated.

## What it does NOT replace

`content_hash` stays. The two answer different questions and collapsing them is
the mistake this exists to fix:

    content_hash     what I actually fetched   — provenance, per-fetch, mine alone
    projection_hash  what the claim rests on   — comparable, stable, everyone's

Keeping both is the state-provenance rule: never let a collapsed value hide which
state produced it.

    python3 reference/projection.py <url-or-file> [--rule PROFILE]
"""

import copy
import hashlib
import json
import sys
import urllib.request

RULE = "crc.projection.v0"

# Named profiles, so a Cell cites a profile rather than restating a path list
# that can drift between nodes. A source with a different shape gets a new
# profile; profiles are append-only for the same reason Cell schemas are.
PROFILES = {
    # The invinoveritas ledger: the fields a Cell's claim and evidence rest on.
    # Deliberately omits relay_anchor/ots_anchor/commitment_proof timing — those
    # are freshness probes about the anchor, not statements about the verdict.
    "invinoveritas.ledger.v0": [
        "record.verdict.artifact_hash",
        "record.verdict.artifact_type",
        "record.verdict.policy_version",
        "record.verdict.decision_ref",
        "record.verdict.source_class",
        "record.verdict.verdict",
        "record.verdict.decision",
        "record.verdict.verifier_pubkey",
        "record.verdict.schema",
    ],
}


class ProjectionError(ValueError):
    pass


def jcs(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def extract(doc: dict, paths):
    """Pull the named paths into a flat, canonical map.

    A path that is ABSENT is recorded as absent rather than skipped: two nodes
    must not agree merely because a field vanished for one of them. Omission and
    null are different facts and are kept different.
    """
    out = {}
    for p in paths:
        cur, found = doc, True
        for k in p.split("."):
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                found = False
                break
        out[p] = cur if found else {"__absent__": True}
    return out


def projection_hash(doc: dict, profile: str) -> str:
    if profile not in PROFILES:
        raise ProjectionError(
            f"unknown projection profile {profile!r} — a Cell must cite a profile "
            f"this verifier knows, not an ad-hoc path list. Known: {sorted(PROFILES)}")
    picked = extract(doc, PROFILES[profile])
    if all(isinstance(v, dict) and v.get("__absent__") for v in picked.values()):
        # Every pinned field missing means the profile does not match this source.
        # Hashing that would produce a confident-looking value for nothing.
        raise ProjectionError(
            f"profile {profile!r} matched NO fields in this document — wrong profile "
            f"for this source. Refusing to hash an empty projection.")

    # Domain-bind the rule and profile into the digest (@pipavlo82). The profile
    # IS the semantic context: it decides which fields the value speaks for. A
    # digest over the selected map alone can be compared against one produced
    # under a different profile as though the two meant the same thing, and two
    # profiles that happen to select the same values collide outright.
    #
    # This module's own docstring says never let a collapsed value hide which
    # state produced it — and the digest was doing exactly that. Binding them
    # means a projection_hash cannot outlive, or be compared independently of,
    # the profile that gave it meaning.
    return "sha256:" + hashlib.sha256(
        jcs({"rule": RULE, "profile": profile, "projection": picked}).encode()).hexdigest()


def _fetch(src: str) -> dict:
    if src.startswith("http://") or src.startswith("https://"):
        with urllib.request.urlopen(src, timeout=30) as r:
            return json.loads(r.read())
    with open(src) as f:
        return json.load(f)


def _selftest() -> int:
    """Vectors. The first two are the point; the third is what stops the point
    from being achieved by hashing nothing."""
    print("projection — vectors\n")
    fails = 0

    def chk(label, cond):
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'}  {label}")
        fails += not cond

    base = {"record": {"verdict": {
        "artifact_hash": "a" * 64, "artifact_type": "review_verdict",
        "policy_version": "p.v1", "decision_ref": "sha256:" + "b" * 64,
        "source_class": "agent_reported", "verdict": "reject",
        "verifier_pubkey": "c" * 64, "schema": "x.v1"}},
        "relay_anchor": {"checked_at": 1786263616}}
    P = "invinoveritas.ledger.v0"
    h0 = projection_hash(base, P)

    moved = copy.deepcopy(base); moved["relay_anchor"]["checked_at"] = 1799999999
    chk("stable when the refreshed anchor timestamp moves", projection_hash(moved, P) == h0)

    grew = copy.deepcopy(base); grew["relay_anchor"]["last_seen_peers"] = 41
    grew["brand_new_top_level"] = {"t": 1}
    chk("stable when the source GAINS fields (what exclusion cannot do)",
        projection_hash(grew, P) == h0)

    flipped = copy.deepcopy(base); flipped["record"]["verdict"]["verdict"] = "approve"
    chk("changes when a claim-bearing field changes", projection_hash(flipped, P) != h0)

    dref = copy.deepcopy(base); dref["record"]["verdict"]["decision_ref"] = "sha256:" + "d" * 64
    chk("changes when decision_ref changes", projection_hash(dref, P) != h0)

    gone = copy.deepcopy(base); del gone["record"]["verdict"]["source_class"]
    chk("a REMOVED pinned field changes the hash (absence is a fact, not a skip)",
        projection_hash(gone, P) != h0)

    try:
        projection_hash({"totally": "different"}, P); chk("refuses a non-matching source", False)
    except ProjectionError:
        chk("refuses a source where the profile matches nothing", True)

    try:
        projection_hash(base, "no.such.profile.v9"); chk("refuses an unknown profile", False)
    except ProjectionError:
        chk("refuses an unknown profile", True)

    # @pipavlo82: the profile is semantic context, so it belongs INSIDE the digest.
    # Two profiles selecting identical values must not produce identical hashes —
    # otherwise the value can be compared independently of what gave it meaning.
    PROFILES["_vec.a.v0"] = ["record.verdict.verdict"]
    PROFILES["_vec.b.v0"] = ["record.verdict.verdict"]
    try:
        doc = {"record": {"verdict": {"verdict": "reject"}}}
        chk("identical selections under DIFFERENT profiles do not collide",
            projection_hash(doc, "_vec.a.v0") != projection_hash(doc, "_vec.b.v0"))
        # And the same profile must still be stable — binding must not add entropy.
        chk("the same profile is still deterministic",
            projection_hash(doc, "_vec.a.v0") == projection_hash(doc, "_vec.a.v0"))
    finally:
        PROFILES.pop("_vec.a.v0", None); PROFILES.pop("_vec.b.v0", None)

    print()
    print("all green — projection" if not fails else f"{fails} failure(s)")
    return fails


def main(argv) -> int:
    if "--selftest" in argv:
        return 1 if _selftest() else 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    profile = argv[argv.index("--rule") + 1] if "--rule" in argv else "invinoveritas.ledger.v0"
    doc = _fetch(argv[1])
    full = "sha256:" + hashlib.sha256(jcs(doc).encode()).hexdigest()
    print(f"  source          : {argv[1]}")
    print(f"  profile         : {RULE} / {profile}")
    print(f"  content_hash    : {full}      (this fetch — provenance)")
    print(f"  projection_hash : {projection_hash(doc, profile)}      (comparable across nodes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
