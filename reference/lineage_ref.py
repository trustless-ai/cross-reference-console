#!/usr/bin/env python3
"""
LineageRef grammar — LINEAGE-REF.md §2, normative.

Every element of `evidence.independence.derived_from` MUST match exactly one of:

    crc.lineage.v0:impl/sha256:<64-lowercase-hex>                    (§2.1, preferred)
    crc.lineage.v0:repo/<url>#commit/<40-hex>#path/<url-encoded-path> (§2.2)

Rejected (§2.3): a bare URL with no prefix, null, the empty string, duplicate
elements in the array, and any ref resolving to the signer's own `impl_hash`.

`derived_from: []` is NOT a LineageRef (§4) — it is a signed declaration of no
known derivation, and it is emphatically not proof of independence. That
distinction is the whole point of the field, so it lives in the type system
here: this module validates ELEMENTS, and the empty array never reaches it.
"""

import re

PREFIX = "crc.lineage.v0:"

# §2.1 — sha256 lowercase, exactly 64. Uppercase is rejected rather than
# normalised: the ref is inside a signed structure, so two spellings of the same
# hash would be two different signed bytes claiming to be one fact.
_IMPL_RE = re.compile(r"^crc\.lineage\.v0:impl/sha256:[0-9a-f]{64}$")

# §2.2 — repo/<url>#commit/<40-hex>#path/<percent-encoded>
_REPO_RE = re.compile(
    r"^crc\.lineage\.v0:repo/(?P<url>[^#]+)"
    r"#commit/(?P<commit>[0-9a-f]{40})"
    r"#path/(?P<path>[^#]+)$"
)


class LineageRefError(ValueError):
    """Raised with a reason a human can act on, not just 'invalid'."""


def parse(ref) -> dict:
    """Validate one element. Returns its parsed parts, or raises LineageRefError."""
    if ref is None:
        raise LineageRefError("null element — use [] on the array, never a null element (§2.3)")
    if not isinstance(ref, str):
        raise LineageRefError(f"element must be a string, got {type(ref).__name__} (§1.1 Type)")
    if ref == "":
        raise LineageRefError("empty string element — use [] on the array (§2.3)")

    if not ref.startswith(PREFIX):
        # The most likely mistake, and worth naming precisely rather than
        # reporting a generic grammar failure.
        hint = " — a bare URL is not a LineageRef (§2.3)" if "://" in ref else ""
        raise LineageRefError(f"missing '{PREFIX}' prefix{hint}")

    m = _IMPL_RE.match(ref)
    if m:
        return {"kind": "impl", "impl_hash": "sha256:" + ref.rsplit(":", 1)[1]}

    m = _REPO_RE.match(ref)
    if m:
        return {"kind": "repo", **m.groupdict()}

    body = ref[len(PREFIX):]
    if body.startswith("impl/"):
        raise LineageRefError(
            "impl ref must be exactly 'impl/sha256:<64 lowercase hex>' (§2.1)")
    if body.startswith("repo/"):
        raise LineageRefError(
            "repo ref must be 'repo/<url>#commit/<40 lowercase hex>#path/<url-encoded>' (§2.2)")
    raise LineageRefError("matches neither the impl (§2.1) nor the repo (§2.2) form")


def validate_derived_from(derived_from, own_impl_hash=None) -> None:
    """Apply CELL-v3.md §1.1 to the whole field. Raises LineageRefError.

    `own_impl_hash` enables the self-reference check. It is optional so this can
    be used on a bare field, but validate_cell.py always passes it — a Cell that
    cites itself as its own ancestor would otherwise read as declared lineage.
    """
    # Type: string[] ONLY. Not null, not a string, not an object (§1.1).
    if derived_from is None:
        raise LineageRefError(
            "derived_from is null — v3 requires an array. Use [] to declare no known "
            "derivation; null is not the same statement (§1.1 Type)")
    if isinstance(derived_from, str):
        raise LineageRefError("derived_from is a string — it must be an array (§1.1 Type)")
    if not isinstance(derived_from, list):
        raise LineageRefError(
            f"derived_from must be string[], got {type(derived_from).__name__} (§1.1 Type)")

    # [] is valid and is NOT a LineageRef (§4) — no element checks run on it.
    seen = set()
    for i, ref in enumerate(derived_from):
        try:
            parsed = parse(ref)
        except LineageRefError as e:
            raise LineageRefError(f"derived_from[{i}]: {e}") from None

        if ref in seen:
            raise LineageRefError(f"derived_from[{i}]: duplicate element (§1.1 Duplicates)")
        seen.add(ref)

        if own_impl_hash and parsed["kind"] == "impl" and parsed["impl_hash"] == own_impl_hash:
            raise LineageRefError(
                f"derived_from[{i}]: self-reference — resolves to this Cell's own "
                f"implementation.impl_hash (§1.1 Self-reference)")


if __name__ == "__main__":
    # Vectors for every rule in §1.1 and §2.3. A grammar with no negative
    # vectors is a grammar nobody has tested.
    OWN = "sha256:" + "a" * 64
    GOOD = [
        [],
        ["crc.lineage.v0:impl/sha256:" + "b" * 64],
        ["crc.lineage.v0:repo/https://github.com/x/y#commit/" + "c" * 40 + "#path/ref%2Fclaim_id.py"],
        ["crc.lineage.v0:impl/sha256:" + "b" * 64, "crc.lineage.v0:impl/sha256:" + "d" * 64],
    ]
    BAD = [
        (None, "null field"),
        ("crc.lineage.v0:impl/sha256:" + "b" * 64, "field is a string not an array"),
        ({}, "field is an object"),
        ([None], "null element"),
        ([""], "empty string element"),
        (["https://github.com/x/y"], "bare URL, no prefix"),
        (["crc.lineage.v0:impl/sha256:" + "B" * 64], "uppercase hex"),
        (["crc.lineage.v0:impl/sha256:" + "b" * 63], "63 hex, not 64"),
        (["crc.lineage.v0:repo/https://x/y#commit/" + "c" * 39 + "#path/a"], "39-hex commit"),
        (["crc.lineage.v0:impl/sha256:" + "b" * 64] * 2, "duplicate elements"),
        (["crc.lineage.v0:impl/" + "a" * 64], "impl ref missing sha256: label"),
        (["crc.lineage.v0:impl/sha256:" + "a" * 64], "self-reference"),
    ]
    fails = 0
    for g in GOOD:
        try:
            validate_derived_from(g, OWN)
            print(f"  ok    accepts: {str(g)[:64]}")
        except LineageRefError as e:
            print(f"  FAIL  rejected a valid field: {e}"); fails += 1
    for b, why in BAD:
        try:
            validate_derived_from(b, OWN)
            print(f"  FAIL  accepted: {why}"); fails += 1
        except LineageRefError:
            print(f"  ok    rejects: {why}")
    print()
    print("all green — LineageRef grammar" if not fails else f"{fails} failure(s)")
    raise SystemExit(1 if fails else 0)
