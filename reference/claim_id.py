#!/usr/bin/env python3
"""Reference claim_id for the Cross-Reference Console (see ../CLAIM.md, v0).

Stdlib only.  claim_id = "sha256:" + hex(sha256(JCS(ClaimPreimage))).

JCS = RFC 8785 (sorted keys, minimal separators, UTF-8). ClaimPreimage v0 uses
only string / int leaf values, for which
    json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False)
is a conformant JCS serialization. Every field is ALWAYS present; an
inapplicable field is JSON null, never omitted (the decision_ref discipline).
"""
import json, hashlib, sys

FIELDS = ["schema", "profile_id", "policy_version", "artifact_hash",
          "artifact_type", "claim_body", "source_class", "verifier_profile",
          "as_of", "claimant"]

def canonical(preimage: dict) -> bytes:
    obj = {k: preimage.get(k, None) for k in FIELDS}   # missing -> explicit null
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")

def claim_id(preimage: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(preimage)).hexdigest()

if __name__ == "__main__":
    p = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else json.load(sys.stdin)
    print(claim_id(p))
