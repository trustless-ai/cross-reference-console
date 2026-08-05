#!/usr/bin/env python3
"""Reference claim_id for the Cross-Reference Console (see ../CLAIM.md, v0).

Stdlib only.  claim_id = "sha256:" + hex(sha256(JCS(ClaimPreimage))).

The reference implementation IS the conformance boundary, so it is strict: a
ClaimPreimage is VALIDATED before hashing (exact key set, required types, and
`as_of` format). A structurally incomplete or extended input is rejected — it
never receives a claim_id (Pavlo, 2026-08-04).

JCS = RFC 8785 (sorted keys, minimal separators, UTF-8). ClaimPreimage v0 uses
only string / int leaf values, for which
    json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False)
is a conformant JCS serialization.
"""
import json, hashlib, re, datetime, sys

# The exact, ordered key set for crc.claim.v0. Every field is required and present.
FIELDS = ["schema", "profile_id", "policy_version", "artifact_hash",
          "artifact_type", "claim_body", "source_class", "verifier_profile",
          "as_of", "claimant"]

_STR_FIELDS = ["schema", "profile_id", "policy_version", "artifact_hash",
               "artifact_type", "source_class", "verifier_profile", "as_of"]
_AS_OF_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")  # RFC3339 UTC, second precision
_HASH_RE = re.compile(r"[0-9a-f]{64}")  # lowercase hex, exactly 64 — no sha256:/0x prefix here
_UINT256_MAX = 2**256 - 1  # claimant is an ERC-8004 token id


def _reject_duplicate_pairs(pairs):
    """object_pairs_hook: JCS is only defined over unique members, and a parser
    that silently keeps the last member lets two different byte-streams
    canonicalize identically. Detected here, at parse time — on the parsed
    object the evidence is already gone."""
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError(f"duplicate JSON member: {k!r}")
        obj[k] = v
    return obj


def loads_strict(text: str):
    """Parse JSON text rejecting duplicate members at any depth."""
    return json.loads(text, object_pairs_hook=_reject_duplicate_pairs)


def validate(preimage: dict) -> None:
    """Raise ValueError unless `preimage` is an exact, well-typed crc.claim.v0.
    Runs BEFORE canonicalization/hashing — the pre-hash gate."""
    if not isinstance(preimage, dict):
        raise ValueError("ClaimPreimage must be a JSON object")
    keys = set(preimage)
    required = set(FIELDS)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    if extra:
        raise ValueError(f"unknown fields (not in crc.claim.v0): {extra}")

    if preimage["schema"] != "crc.claim.v0":
        raise ValueError("schema must be exactly 'crc.claim.v0'")
    for k in _STR_FIELDS:
        if not isinstance(preimage[k], str) or preimage[k] == "":
            raise ValueError(f"{k} must be a non-empty string")
    # claim_body: string or explicit null (the type may carry no assertion)
    if not (preimage["claim_body"] is None or isinstance(preimage["claim_body"], str)):
        raise ValueError("claim_body must be a string or null")
    # artifact_hash: strict grammar — bare lowercase hex-64 (sha256:/0x prefixes reject)
    if not _HASH_RE.fullmatch(preimage["artifact_hash"]):
        raise ValueError("artifact_hash must match ^[0-9a-f]{64}$ (bare lowercase hex)")
    # claimant: an ERC-8004 token id (integer; bool is not an int here) in uint256 range
    if isinstance(preimage["claimant"], bool) or not isinstance(preimage["claimant"], int):
        raise ValueError("claimant must be an integer (ERC-8004 token id)")
    if not (0 <= preimage["claimant"] <= _UINT256_MAX):
        raise ValueError("claimant must be in uint256 range [0, 2^256)")
    # as_of: strict RFC3339 UTC 'YYYY-MM-DDTHH:MM:SSZ', and a real instant
    if not _AS_OF_RE.fullmatch(preimage["as_of"]):
        raise ValueError("as_of must be RFC3339 UTC 'YYYY-MM-DDTHH:MM:SSZ'")
    datetime.datetime.strptime(preimage["as_of"], "%Y-%m-%dT%H:%M:%SZ")  # rejects e.g. month 13


def canonical(preimage: dict) -> bytes:
    validate(preimage)
    obj = {k: preimage[k] for k in FIELDS}  # exact set; validation guarantees presence
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def claim_id(preimage: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(preimage)).hexdigest()


if __name__ == "__main__":
    text = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    print(claim_id(loads_strict(text)))
