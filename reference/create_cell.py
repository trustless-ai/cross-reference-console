#!/usr/bin/env python3
"""
Produce a signed crc.cell.v2 — the tool this repo was missing.

Until now `reference/` held ten scripts and every one of them CHECKED something.
Nothing PRODUCED anything, so an outsider could verify our cells and not make
their own: they had to read the EIP-712 type list out of the spec, implement
signing from scratch, and hope the signature grammar was the only trap. That
gap was found by someone actually trying it (M Zidan Fatonie, PR #7, gap 1).

    # EIP-712 lane
    export CRC_KEY=0x<64-hex private key>
    python3 reference/create_cell.py \\
        --claim  claims/<claim_id>.json \\
        --node   my-node-id \\
        --result GREEN \\
        --boundary "ERC-8274 recompute/mine -- claim_id re-derived from ..." \\
        --evidence my-evidence.json

    # Nostr lane: same, with CRC_KEY as a 32-byte schnorr secret key.

The key is read from the environment, never a flag, so it does not land in
shell history or `ps`.

The cell is written to cells/<claim-digest>/<node_id>.cell.json and then
VALIDATED with the same validator CI runs. If it does not pass, the file is
removed and this exits non-zero — a create tool that emits invalid cells is
worse than no create tool, because it moves the failure to someone else's
review.
"""

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from claim_id import loads_strict, validate as gate, claim_id as derive_claim_id  # noqa: E402
from registry_id import registry_id as this_registry_id  # noqa: E402

# The signed struct, in order. CELL-v2.md §2 — registry_id is inside it, which
# is what makes a v2 Cell bound to THIS registry instance rather than portable
# to any fork that reuses the schema name.
CELL_TYPE_V2 = [
    {"name": "schema", "type": "string"},
    {"name": "claim_id", "type": "string"},
    {"name": "registry_id", "type": "string"},
    {"name": "result", "type": "string"},
    {"name": "verifier", "type": "address"},
    {"name": "boundary", "type": "string"},
    {"name": "as_of", "type": "string"},
    {"name": "recomputed_at", "type": "string"},
    {"name": "evidence_hash", "type": "bytes32"},
]

DOMAIN_V2 = {"name": "cross-reference-console", "version": "2", "chainId": 1}
RESULTS = ("GREEN", "RED", "AMBER")


def in_force_schema() -> str:
    """The schema new Cells must carry: highest CELL-vN.md present. DERIVED, not
    hardcoded -- a hardcoded version here would emit Cells that CI rejects the
    moment a new spec lands, which is exactly the deadlock this repo just had
    between CELL-v3.md and check_sunset.py."""
    ns = [int(m.group(1)) for f in os.listdir(ROOT)
          if (m := re.fullmatch(r"CELL-v(\d+)\.md", f))]
    return f"crc.cell.v{max(ns)}" if ns else "crc.cell.v2"


def jcs(o) -> str:
    """RFC 8785 canonical JSON, matching validate_cell.py byte for byte."""
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def keccak256(data: bytes) -> bytes:
    from Crypto.Hash import keccak
    k = keccak.new(digest_bits=256)
    k.update(data)
    return k.digest()


def die(msg: str) -> "NoReturn":
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def rfc3339_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_node(node_id: str) -> dict:
    nodes = json.loads((ROOT / "nodes.json").read_text())["nodes"]
    for n in nodes:
        if n["node_id"] == node_id:
            if n.get("retired"):
                die(f"node '{node_id}' is retired — a retired node cannot sign new Cells")
            return n
    known = ", ".join(n["node_id"] for n in nodes)
    die(f"node '{node_id}' is not in nodes.json. Register it first (see NODES.md).\n"
        f"       Known nodes: {known}")


def check_evidence(evidence: dict, result: str) -> None:
    """CELL.md: 'Never a bare green — a Cell without a recomputable evidence
    body is not a Cell.' Enforced here rather than left to review, because a
    tool that will happily emit one guarantees somebody eventually does."""
    if not isinstance(evidence, dict) or not evidence:
        die("evidence is empty. A Cell without a recomputable evidence body is not a Cell.")

    if "claim_preimage" not in evidence:
        die("evidence.claim_preimage is required — it is what makes the verdict re-runnable.")

    if in_force_schema() == "crc.cell.v3":
        ind = evidence.get("independence") or {}
        if "derived_from" not in ind:
            die("crc.cell.v3 requires evidence.independence.derived_from (CELL-v3.md §1.1).\n"
                "       Use [] to declare no known derivation from another implementation.\n"
                "       [] is signed provenance, never proof of independence.")

    if result == "GREEN":
        missing = [k for k in ("recomputed", "independence") if k not in evidence]
        if missing:
            die("a GREEN Cell must carry " + " and ".join(f"evidence.{m}" for m in missing) +
                ".\n       GREEN asserts you recomputed the value independently; without those "
                "fields\n       a reader has to take your word for it, which is the one thing "
                "this repo does not do.")


def build_payload(claim: dict, node: dict, result: str, boundary: str, evidence: dict) -> dict:
    pre = claim["claim_preimage"]
    gate(pre)  # the universal pre-hash conformance gate; raises on any violation
    cid = derive_claim_id(pre)

    if evidence.get("claim_preimage") != pre:
        die("evidence.claim_preimage does not match the claim you passed.\n"
            "       The Cell must carry the exact preimage it verified, byte for byte.")

    return {
        "schema": in_force_schema(),
        "claim_id": cid,
        "registry_id": this_registry_id(),
        "result": result,
        "verifier": node["verifier"],
        "boundary": boundary,
        # as_of is the OBSERVATION snapshot and comes from the claim; it is never
        # "now". recomputed_at is when THIS node ran. CELL-v1.md §1 — a Cell
        # recomputed a year later carries the same as_of and a new recomputed_at.
        "as_of": pre["as_of"],
        "recomputed_at": rfc3339_now(),
        "evidence": evidence,
    }


def sign_eip712(pp: dict, key: str) -> dict:
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
    except ImportError:
        die("eip712 lane needs eth-account:  pip install eth-account")

    evidence_hash = "0x" + keccak256(jcs(pp["evidence"]).encode()).hex()
    value = {f["name"]: (evidence_hash if f["name"] == "evidence_hash" else pp[f["name"]])
             for f in CELL_TYPE_V2}
    full = {
        "types": {
            "EIP712Domain": [{"name": "name", "type": "string"},
                             {"name": "version", "type": "string"},
                             {"name": "chainId", "type": "uint256"}],
            "Cell": CELL_TYPE_V2,
        },
        "primaryType": "Cell",
        "domain": DOMAIN_V2,
        "message": value,
    }
    acct = Account.from_key(key)
    signed = acct.sign_message(encode_typed_data(full_message=full))

    # CELL-v2.md §3: lowercase hex, 0x-prefixed, exactly 130 hex chars. eth_account
    # is tolerant of bare hex on the way IN and ethers is not, so the grammar is
    # pinned on the way OUT. A real Cell was repaired over exactly this.
    sig = "0x" + signed.signature.hex().removeprefix("0x").lower()
    if not re.fullmatch(r"0x[0-9a-f]{130}", sig):
        die(f"produced a signature that does not match the pinned grammar: {sig[:16]}…")

    return {
        "scheme": "eip712",
        "domain": DOMAIN_V2,
        "primaryType": "Cell",
        "types": {"Cell": CELL_TYPE_V2},
        "evidence_hash": evidence_hash,
        "signer": acct.address,
        "signature": sig,
    }


def sign_nostr(pp: dict, key: str) -> dict:
    import bip340
    content = jcs(pp)
    sk = bytes.fromhex(key.removeprefix("0x"))
    pubkey = bip340.pubkey_gen(sk).hex()
    created_at = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    # NIP-01: id = sha256(JSON([0, pubkey, created_at, kind, tags, content])),
    # serialised with no whitespace.
    ser = json.dumps([0, pubkey, created_at, 1, [], content],
                     separators=(",", ":"), ensure_ascii=False)
    eid = hashlib.sha256(ser.encode()).hexdigest()
    sig = bip340.schnorr_sign(bytes.fromhex(eid), sk).hex()
    return {"content": content, "created_at": created_at, "id": eid,
            "kind": 1, "pubkey": pubkey, "sig": sig, "tags": []}


VERIFY_NOTE = (
    "gate the claim_preimage; recompute claim_id; recompute "
    "evidence_hash=keccak256(JCS(evidence)); recover the signer and check it equals "
    "signature.signer AND proof_payload.verifier AND the address registered in "
    "nodes.json (quadruple equality, CELL-v1.md §2); check registry_id equals this "
    "registry (CELL-v2.md §2); re-run the evidence yourself."
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create and sign a crc.cell.v2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="The signing key is read from $CRC_KEY, never a flag.")
    ap.add_argument("--claim", required=True, help="path to a claims/<id>.json file")
    ap.add_argument("--node", required=True, help="your node_id, as registered in nodes.json")
    ap.add_argument("--result", required=True, choices=RESULTS)
    ap.add_argument("--boundary", required=True,
                    help="what you actually checked, and what you did NOT — this is read by humans")
    ap.add_argument("--evidence", required=True, help="path to your evidence JSON")
    args = ap.parse_args()

    key = os.environ.get("CRC_KEY")
    if not key:
        die("set CRC_KEY to your signing key (env, not a flag — flags land in shell history)")

    claim_path = pathlib.Path(args.claim)
    if not claim_path.exists():
        die(f"no such claim file: {claim_path}")
    claim = loads_strict(claim_path.read_text())
    evidence = loads_strict(pathlib.Path(args.evidence).read_text())

    node = load_node(args.node)
    check_evidence(evidence, args.result)

    pp = build_payload(claim, node, args.result, args.boundary, evidence)
    digest = pp["claim_id"].removeprefix("sha256:")

    env = node["envelope"]
    if env == "eip712":
        cell = {"proof_payload": pp, "signature": sign_eip712(pp, key), "verify": VERIFY_NOTE}
    elif env == "nostr-nip01":
        cell = {"event": sign_nostr(pp, key), "source_relays": [], "verify": VERIFY_NOTE}
    else:
        die(f"unknown envelope '{env}' in your nodes.json entry")

    # The path is DERIVED, with no flag to override it. validate_cell.py requires
    # the directory to be the claim digest and the filename to be
    # <node_id>.cell.json, so an --out flag could only ever select between
    # "the correct path" and "a path that always fails validation".
    out = ROOT / "cells" / digest / f"{args.node}.cell.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cell, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")

    # Self-validation. A create tool that can emit an invalid Cell just moves the
    # failure into someone else's review, so this runs the same validator CI does
    # and deletes its own output if it does not pass.
    print("\nvalidating with the same checker CI runs:\n")
    r = subprocess.run([sys.executable, str(HERE / "validate_cell.py"), str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    print(r.stdout.rstrip() or r.stderr.rstrip())
    if r.returncode != 0:
        out.unlink(missing_ok=True)
        print("\nCell did NOT validate — removed. Nothing was written.", file=sys.stderr)
        return 1

    print(f"\nValid. Open a PR adding {out.name}; CI re-runs exactly this.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
