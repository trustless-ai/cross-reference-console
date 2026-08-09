#!/usr/bin/env python3
"""Verify a pin record: rebuild the stated commit and check the confirmations.

The ENS contenthash is the one pointer in this stack that is not recomputable, so
the rule is that no one person can move it: a CID is pinned only when two
independent parties each rebuilt the stated commit and got the same bytes and the
same CID (PIN-RECORD.md).

This tool is what a third party runs to check that claim without trusting anyone
who made it — including whoever wrote the record.

Tri-state on purpose. AMBER is a real answer here and is used whenever something
could not be established: no `ipfs` binary to recompute the CID with, or a commit
that cannot be fetched. Could-not-check is never a pass.

    python3 reference/verify_pin.py pins/<cid>.json
"""

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

GREEN, AMBER, RED = "GREEN", "AMBER", "RED"
_SYM = {GREEN: "ok   ", AMBER: "amber", RED: "RED  "}


class Report:
    def __init__(self):
        self.rows = []

    def add(self, state, msg):
        self.rows.append((state, msg))
        print(f"  {_SYM[state]} · {msg}")

    def verdict(self):
        if any(s == RED for s, _ in self.rows):
            return RED
        if any(s == AMBER for s, _ in self.rows):
            return AMBER
        return GREEN


def sha256_file(p: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def ipfs_cid(path: pathlib.Path, params: dict):
    """Recompute the CID with the RECORDED parameters, or None if not possible.

    The parameters are not decoration. The same bytes produce a different CID
    under --cid-version=0 vs 1, and different again when wrapped with -w. Two
    honest people who rebuild the same commit will disagree on the CID if their
    flags differ, so the record fixes them and this reproduces them exactly.
    """
    if not shutil.which("ipfs"):
        return None
    args = ["ipfs", "add", "-Q", "-n"]
    args.append(f"--cid-version={params.get('cid_version', 1)}")
    if params.get("wrap_with_directory"):
        args.append("-w")
    if "chunker" in params:
        args.append(f"--chunker={params['chunker']}")
    if "hash" in params:
        args.append(f"--hash={params['hash']}")
    if params.get("raw_leaves") is False:
        args.append("--raw-leaves=false")
    args.append(str(path))
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    out = r.stdout.strip().splitlines()
    return out[-1].strip() if out else None


def registered_nodes() -> dict:
    try:
        return {n["node_id"]: n for n in json.loads((ROOT / "nodes.json").read_text())["nodes"]
                if not n.get("retired")}
    except Exception:
        return {}


def confirmation_preimage(rec: dict, conf: dict) -> str:
    """The exact bytes a confirming node signs — JCS over the fields that matter.

    Binds the confirmation to THIS record: the CID, the commit, the artifact and
    the bytes. A signature over "I agree" would be replayable onto a different
    pin; this one is not.
    """
    return json.dumps({
        "schema": "crc.pin-confirmation.v0",
        "cid": rec.get("cid"),
        "commit": rec.get("commit"),
        "artifact": rec.get("artifact", "ui/index.html"),
        "file_sha256": conf.get("file_sha256"),
        "node_id": conf.get("node_id"),
        "rebuilt_at": conf.get("rebuilt_at"),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def verify_confirmation_signature(rec: dict, conf: dict, node: dict):
    """(ok, detail). Uses the node's REGISTERED envelope and key — never the one
    the confirmation asserts, which is the same rule Cells follow.

    Returns ok=None when the signature is absent, so the caller can distinguish
    'unsigned' from 'signed and wrong' — very different findings.
    """
    sig = conf.get("signature")
    if not sig:
        return None, "no signature"

    env = node.get("envelope")
    msg = confirmation_preimage(rec, conf)

    if env == "eip712":
        try:
            from eth_account import Account
            from eth_account.messages import encode_typed_data
        except ImportError:
            return None, "eth-account not installed — cannot check"
        full = {
            "types": {
                "EIP712Domain": [{"name": "name", "type": "string"},
                                 {"name": "version", "type": "string"},
                                 {"name": "chainId", "type": "uint256"}],
                "PinConfirmation": [{"name": "preimage", "type": "string"}],
            },
            "primaryType": "PinConfirmation",
            "domain": {"name": "cross-reference-console", "version": "1", "chainId": 1},
            "message": {"preimage": msg},
        }
        if not re.fullmatch(r"0x[0-9a-f]{130}", str(sig)):
            return False, "signature grammar (expect 0x + 130 lowercase hex)"
        try:
            rec_addr = Account.recover_message(encode_typed_data(full_message=full), signature=sig)
        except Exception as e:
            return False, f"recover failed: {type(e).__name__}"
        want = (node.get("key_ref") or {}).get("address") or ""
        if rec_addr.lower() != want.lower():
            return False, f"recovered {rec_addr} != registered {want}"
        return True, rec_addr

    if env == "nostr-nip01":
        try:
            sys.path.insert(0, str(ROOT / "reference"))
            import bip340
        except ImportError:
            return None, "bip340 helper unavailable — cannot check"
        pub = (node.get("key_ref") or {}).get("pubkey") or ""
        digest = hashlib.sha256(msg.encode()).hexdigest()
        try:
            if not bip340.verify_hex(digest, pub, str(sig)):
                return False, "schnorr verify failed vs registered pubkey"
        except Exception as e:
            return False, f"schnorr check errored: {type(e).__name__}"
        return True, pub

    return None, f"unknown envelope {env!r} — cannot check"


def _finish(rep) -> int:
    v = rep.verdict()
    print()
    print({GREEN: "GREEN — safe to pin: rebuilt, reproduced, and independently confirmed",
           AMBER: "AMBER — not established. Something could not be checked; that is not a pass",
           RED:   "RED — do NOT pin"}[v])
    return 0 if v == GREEN else 1


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    rec_path = pathlib.Path(argv[1])
    if not rec_path.exists():
        print(f"RED   pin record not found: {rec_path}")
        return 1

    rec = json.loads(rec_path.read_text())
    rep = Report()

    print(f"\nverifying {rec_path}\n")

    # --- shape -------------------------------------------------------------
    if rec.get("schema") != "crc.pin-record.v0":
        rep.add(RED, f"schema is {rec.get('schema')!r}, expected 'crc.pin-record.v0'")
        return _finish(rep)
    rep.add(GREEN, "schema is crc.pin-record.v0")

    commit = rec.get("commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        rep.add(RED, "commit is not a 40-hex sha")
        return _finish(rep)

    artifact = rec.get("artifact", "ui/index.html")
    params = rec.get("cid_params") or {}
    if not params:
        # Without these the CID cannot be reproduced, so the record cannot be
        # checked at all — that is a defect in the record, not an abstention.
        rep.add(RED, "cid_params absent — the CID is not reproducible without them")
        return _finish(rep)
    rep.add(GREEN, f"cid_params recorded: {json.dumps(params, sort_keys=True)}")

    # --- rebuild the stated commit ----------------------------------------
    built = None
    with tempfile.TemporaryDirectory() as td:
        wt = pathlib.Path(td) / "wt"
        r = subprocess.run(["git", "worktree", "add", "--detach", "-q", str(wt), commit],
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            rep.add(AMBER, f"cannot check out {commit[:8]} — fetch it and re-run "
                           f"(git fetch origin {commit})")
        else:
            try:
                b = subprocess.run([sys.executable, "ui/embed_snapshot.py"],
                                   capture_output=True, text=True, cwd=wt)
                target = wt / artifact
                if b.returncode != 0 or not target.exists():
                    rep.add(RED, f"rebuild of {commit[:8]} failed")
                else:
                    got_sha = sha256_file(target)
                    want_sha = rec.get("file_sha256")
                    if got_sha == want_sha:
                        rep.add(GREEN, f"rebuild of {commit[:8]} reproduces file_sha256")
                    else:
                        rep.add(RED, f"rebuild MISMATCH\n           record: {want_sha}\n"
                                     f"           rebuilt: {got_sha}")
                    got_cid = ipfs_cid(target, params)
                    if got_cid is None:
                        rep.add(AMBER, "no usable `ipfs` binary — CID not recomputed "
                                       "(the bytes were still checked)")
                    elif got_cid == rec.get("cid"):
                        rep.add(GREEN, f"CID recomputes under the recorded params: {got_cid[:24]}…")
                    else:
                        rep.add(RED, f"CID MISMATCH\n           record:   {rec.get('cid')}\n"
                                     f"           recomputed: {got_cid}")
                    built = got_sha
            finally:
                subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                               capture_output=True, cwd=ROOT)

    # --- confirmations -----------------------------------------------------
    confs = rec.get("confirmations") or []
    known = registered_nodes()
    seen_nodes = set()
    # Only confirmations that are BOTH authentic and correct count toward the
    # rule. Merely appearing in the array is not confirming — that conflation is
    # what let a single writer satisfy a two-party rule.
    counted = set()

    for c in confs:
        nid = c.get("node_id")
        if nid not in known:
            rep.add(RED, f"confirmation from unregistered node {nid!r}")
            continue
        if nid in seen_nodes:
            rep.add(RED, f"duplicate confirmation from {nid} — one party, counted twice, "
                         f"is exactly what the two-party rule exists to prevent")
            continue
        seen_nodes.add(nid)

        # Authenticity first: without it, everything below is a claim by whoever
        # wrote the file, not by the node it names.
        ok, detail = verify_confirmation_signature(rec, c, known[nid])
        if ok is False:
            rep.add(RED, f"{nid}: signature does not verify — {detail}")
            continue
        if ok is None:
            rep.add(AMBER, f"{nid}: {detail} — authorship is NOT established, so this "
                           f"confirmation cannot count toward the two-party rule")
            continue

        if c.get("file_sha256") != rec.get("file_sha256"):
            rep.add(RED, f"{nid} confirms a different file_sha256 than the record")
        elif built and c.get("file_sha256") != built:
            rep.add(RED, f"{nid} confirms bytes that do not match the rebuild")
        elif c.get("cid") != rec.get("cid"):
            # Same bytes, different CID = a parameter disagreement, not tampering.
            rep.add(AMBER, f"{nid} agrees on the bytes but reports a different CID — "
                           f"parameter mismatch, not a bad page (see PIN-RECORD.md)")
        else:
            rep.add(GREEN, f"{nid} signed, independently rebuilt, agrees on bytes and CID")
            counted.add(nid)

    # Reports the COUNTED set, not the set of names present. The previous version
    # printed "N distinct nodes confirm — no unilateral pin" off the names alone,
    # so it asserted the rule was met while a confirmation next to it was RED.
    if len(counted) >= 2:
        rep.add(GREEN, f"{len(counted)} authenticated confirmations from distinct nodes "
                       f"— no unilateral pin")
    else:
        rep.add(RED, f"only {len(counted)} confirmation(s) are both authenticated and "
                     f"correct — the rule is two ({len(seen_nodes)} node(s) named)")

    return _finish(rep)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
