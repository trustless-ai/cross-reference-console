#!/usr/bin/env python3
"""Sign a pin confirmation — the tool that makes the two-party rule usable.

A confirmation says: *I rebuilt this commit myself and got these bytes.* Since
Pavlo's review it must be signed by the confirming node's registered key, because
an unsigned entry is a claim by whoever wrote the file, not by the node it names
— and a rule whose whole purpose is "no unilateral pin" cannot rest on that.

Usage:

    export CRC_KEY=0x<your key>          # env, never a flag: flags land in history
    python3 reference/sign_confirmation.py --record pins/<cid>.json --node yournode

It rebuilds the record's commit ITSELF, so you cannot accidentally confirm bytes
you never produced: if your rebuild disagrees with the record it refuses to sign
and tells you what differed. That refusal is the point of the whole exercise —
the disagreement is the finding.

The signature covers the CID, the commit, the artifact, your bytes, your node_id
and your timestamp, so it cannot be lifted onto a different pin record.
"""

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))

from verify_pin import (ALLOWED_SITE_REPOS, confirmation_preimage,  # noqa: E402
                        ipfs_cid, sha256_file)


def _sign_msg(msg, node, key):
    """Sign the preimage in the node's registered envelope. Shared by both kinds."""
    env = node.get("envelope")
    if env == "eip712":
        from eth_account import Account
        from eth_account.messages import encode_typed_data
        full = {"types": {"EIP712Domain": [{"name": "name", "type": "string"},
                                           {"name": "version", "type": "string"},
                                           {"name": "chainId", "type": "uint256"}],
                          "PinConfirmation": [{"name": "preimage", "type": "string"}]},
                "primaryType": "PinConfirmation",
                "domain": {"name": "cross-reference-console", "version": "1", "chainId": 1},
                "message": {"preimage": msg}}
        acct = Account.from_key(key)
        want = (node.get("key_ref") or {}).get("address") or ""
        if acct.address.lower() != want.lower():
            raise SystemExit(f"CRC_KEY derives {acct.address}, but this node is registered as {want}")
        sig = Account.sign_message(encode_typed_data(full_message=full),
                                   private_key=key).signature.hex()
        return sig if sig.startswith("0x") else "0x" + sig
    if env == "nostr-nip01":
        import bip340
        return bip340.sign_hex(hashlib.sha256(msg.encode()).hexdigest(), key)
    raise SystemExit(f"unknown envelope {env!r}")


def _confirm_site_tree(rec, node, args, key):
    """Confirm a whole published site, which is what the contenthash covers.

    Clones the landing repo at the stated commit, checks the console page is the
    build of ITS locked commit (otherwise the tree contains a hand-copied file and
    only reproduces by luck), then derives the tree hash and directory CID.
    """
    repo = rec.get("repo") or "https://github.com/trustless-ai/trustless-ai-landing"
    # Same boundary as verify_pin, and it needed saying twice: confirming a
    # site-tree record also EXECUTES build code from the cloned repo. Fixing the
    # verifier and not the signer would have left the hole open for exactly the
    # people doing the most careful work — the ones who bother to confirm.
    if repo.rstrip("/").removesuffix(".git") not in ALLOWED_SITE_REPOS:
        print(f"REFUSING TO SIGN — repo {repo!r} is not in the allowlist.\n"
              "Confirming would execute build code from a record-selected repository.")
        return 1
    with tempfile.TemporaryDirectory() as td:
        site = pathlib.Path(td) / "site"
        r = subprocess.run(["git", "clone", "--quiet", "--no-checkout", repo + ".git", str(site)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"REFUSING TO SIGN — cannot clone {repo}")
            return 1
        r = subprocess.run(["git", "checkout", "--quiet", rec["commit"]],
                           capture_output=True, text=True, cwd=site)
        if r.returncode != 0:
            print(f"REFUSING TO SIGN — commit {rec['commit'][:12]} not found in {repo}")
            return 1
        c = subprocess.run([sys.executable, "build/sync_console.py", "--check"],
                           capture_output=True, text=True, cwd=site)
        if c.returncode != 0:
            print("REFUSING TO SIGN — the site's console page is not the build of its\n"
                  "locked commit. The tree has drifted from its sources:\n"
                  + "  " + (c.stdout.strip().splitlines() or ["(no output)"])[0][:160])
            return 1
        s = subprocess.run([sys.executable, "build/site_cid.py", "--json"],
                           capture_output=True, text=True, cwd=site)
        if s.returncode != 0:
            print("REFUSING TO SIGN — could not derive the site CID from that commit")
            return 1
        got = json.loads(s.stdout)

    if got["tree_sha256"] != rec.get("tree_sha256"):
        print("REFUSING TO SIGN — your rebuild does not match the record.\n"
              f"  record:  {rec.get('tree_sha256')}\n"
              f"  you got: {got['tree_sha256']}\n"
              "That disagreement is a finding. Report it rather than working around it.")
        return 1
    print(f"  tree hash matches the record: {got['tree_sha256'][:26]}…  "
          f"({got['file_count']} files)")

    my_cid = got.get("cid")
    if my_cid is None:
        print("  no usable `ipfs` — recording cid: null (NOT copying the record's).\n"
              "  This confirmation will be AMBER and will not count toward the two.")
    elif my_cid != rec.get("cid"):
        print(f"  note: your CID differs ({my_cid[:20]}… vs {str(rec.get('cid'))[:20]}…).\n"
              "  Same tree, so this is a PARAMETER difference, not a bad site. Recording yours.")

    conf = {"node_id": args.node, "rebuilt_at": now(),
            "tree_sha256": got["tree_sha256"], "file_sha256": got["tree_sha256"],
            "cid": my_cid}
    conf["signature"] = _sign_msg(confirmation_preimage(rec, conf), node, key)

    rec.setdefault("confirmations", [])
    rec["confirmations"] = [c for c in rec["confirmations"] if c.get("node_id") != args.node]
    rec["confirmations"].append(conf)
    pathlib.Path(args.record).write_text(json.dumps(rec, indent=2) + "\n")
    print(f"  signed and added confirmation for {args.node}")
    print(f"\nNow run:  python3 reference/verify_pin.py {args.record}")
    return 0


def now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sign a pin confirmation.")
    ap.add_argument("--record", required=True, help="path to pins/<cid>.json")
    ap.add_argument("--node", required=True, help="your node_id, as registered")
    args = ap.parse_args()

    key = os.environ.get("CRC_KEY", "")
    if not key:
        print("CRC_KEY is not set. Export it — it is never accepted as a flag.")
        return 2

    rec = json.loads(pathlib.Path(args.record).read_text())
    nodes = {n["node_id"]: n for n in json.loads((ROOT / "nodes.json").read_text())["nodes"]}
    node = nodes.get(args.node)
    if not node:
        print(f"node {args.node!r} is not in nodes.json — register it first")
        return 1

    # Rebuild it yourself. Confirming bytes you did not produce is the one thing
    # this tool must not make easy.
    commit = rec["commit"]
    artifact = rec.get("artifact", "ui/index.html")

    if rec.get("artifact_kind") == "site-tree":
        return _confirm_site_tree(rec, node, args, key)
    with tempfile.TemporaryDirectory() as td:
        wt = pathlib.Path(td) / "wt"
        r = subprocess.run(["git", "worktree", "add", "--detach", "-q", str(wt), commit],
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            print(f"cannot check out {commit[:8]} — fetch it first, then re-run.")
            return 1
        try:
            b = subprocess.run([sys.executable, "ui/embed_snapshot.py"],
                               capture_output=True, text=True, cwd=wt)
            # The build MUST be checked. The artifact is committed in the repo, so
            # a failed build leaves a plausible file sitting there — and since CI
            # enforces committed == build, hashing it would look like success.
            # That is signing a rebuild that never ran. Found in review by @pipavlo82.
            if b.returncode != 0:
                print("REFUSING TO SIGN — the rebuild command failed:\n"
                      f"  {(b.stderr.strip().splitlines() or ['(no stderr)'])[-1][:200]}\n"
                      "Signing now would attest to bytes that were checked out, not rebuilt.")
                return 1
            target = wt / artifact
            if not target.exists():
                print(f"REFUSING TO SIGN — rebuild produced no {artifact}")
                return 1
            my_sha = sha256_file(target)
            my_cid = ipfs_cid(target, rec.get("cid_params") or {})
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                           capture_output=True, cwd=ROOT)

    if my_sha != rec.get("file_sha256"):
        print("REFUSING TO SIGN — your rebuild does not match the record.\n"
              f"  record:  {rec.get('file_sha256')}\n"
              f"  you got: {my_sha}\n"
              "That disagreement is a finding. Report it rather than working around it.")
        return 1
    print(f"  rebuild matches the record: {my_sha[:26]}…")
    if my_cid is None:
        # Record null, never the record's value. Copying it would sign a CID this
        # node never computed — fabricated provenance, and precisely the defect we
        # keep catching elsewhere. verify_pin reads null as AMBER, which is right:
        # the confirmer established the bytes and not the CID.
        print("  no usable `ipfs` — recording cid: null (NOT copying the record's).\n"
              "  This confirmation will be AMBER and will not count toward the two.\n"
              "  Install ipfs and re-run to produce a counting confirmation.")
    elif my_cid != rec.get("cid"):
        print(f"  note: your CID differs ({my_cid[:20]}… vs {str(rec.get('cid'))[:20]}…).\n"
              "  Same bytes, so this is a PARAMETER difference, not a bad page. Recording yours.")

    conf = {"node_id": args.node, "rebuilt_at": now(),
            "file_sha256": my_sha, "cid": my_cid}
    msg = confirmation_preimage(rec, conf)

    env = node.get("envelope")
    if env == "eip712":
        from eth_account import Account
        from eth_account.messages import encode_typed_data
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
        acct = Account.from_key(key)
        want = (node.get("key_ref") or {}).get("address") or ""
        if acct.address.lower() != want.lower():
            print(f"CRC_KEY derives {acct.address}, but {args.node} is registered as {want}")
            return 1
        conf["signature"] = Account.sign_message(encode_typed_data(full_message=full),
                                                 private_key=key).signature.hex()
        if not conf["signature"].startswith("0x"):
            conf["signature"] = "0x" + conf["signature"]
    elif env == "nostr-nip01":
        import bip340
        digest = hashlib.sha256(msg.encode()).hexdigest()
        conf["signature"] = bip340.sign_hex(digest, key)
    else:
        print(f"unknown envelope {env!r} for {args.node}")
        return 1

    rec.setdefault("confirmations", [])
    rec["confirmations"] = [c for c in rec["confirmations"] if c.get("node_id") != args.node]
    rec["confirmations"].append(conf)
    pathlib.Path(args.record).write_text(json.dumps(rec, indent=2) + "\n")
    print(f"  signed and added confirmation for {args.node}")
    print(f"\nNow run:  python3 reference/verify_pin.py {args.record}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
