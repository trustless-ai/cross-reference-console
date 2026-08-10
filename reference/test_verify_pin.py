#!/usr/bin/env python3
"""Negative matrix for the pin rule — a vector per predicate, run in CI.

Pavlo's review asked for this directly, and he was right to: the first version of
these vectors lived in my terminal, which is the same defect as a conformance
claim nobody can re-run. A check that exists only where it was written is not a
check.

The vector that matters most is `unsigned_pair`: two confirmations naming two
registered nodes, both self-consistent, both correct about the bytes — authored
by one writer. That reached GREEN before signatures were bound, which meant the
"no unilateral pin" rule was policy rather than mechanism.

Signature vectors use freshly generated throwaway keys against a synthetic node
registry, so the crypto is exercised without depending on any real node's key.
"""

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))

import verify_pin  # noqa: E402

verify_confirmation_sig_or_skip = verify_pin.verify_confirmation_signature

fails = 0


def check(label: str, cond: bool, detail: str = ""):
    global fails
    if cond:
        print(f"  ok    {label}")
    else:
        fails += 1
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------- signatures
def signature_vectors():
    print("\nsignature binding (throwaway keys, synthetic registry):")
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
    except ImportError:
        print("  amber eth-account not installed — signature vectors SKIPPED")
        print("        (this line is the finding: the suite could not check them)")
        return

    acct = Account.create()
    other = Account.create()
    node = {"node_id": "testnode", "envelope": "eip712",
            "key_ref": {"address": acct.address, "pubkey": None}}
    rec = {"cid": "bafkreitest", "commit": "a" * 40, "artifact": "ui/index.html",
           "file_sha256": "sha256:" + "b" * 64}
    conf = {"node_id": "testnode", "rebuilt_at": "2026-08-09T00:00:00Z",
            "file_sha256": "sha256:" + "b" * 64, "cid": "bafkreitest"}

    def sign(with_key, r=rec, c=conf):
        msg = verify_pin.confirmation_preimage(r, c)
        full = {"types": {"EIP712Domain": [{"name": "name", "type": "string"},
                                           {"name": "version", "type": "string"},
                                           {"name": "chainId", "type": "uint256"}],
                          "PinConfirmation": [{"name": "preimage", "type": "string"}]},
                "primaryType": "PinConfirmation",
                "domain": {"name": "cross-reference-console", "version": "1", "chainId": 1},
                "message": {"preimage": msg}}
        s = Account.sign_message(encode_typed_data(full_message=full),
                                 private_key=with_key.key).signature.hex()
        return s if s.startswith("0x") else "0x" + s

    good = dict(conf, signature=sign(acct))
    ok, d = verify_pin.verify_confirmation_signature(rec, good, node)
    check("a correctly signed confirmation verifies", ok is True, str(d))

    ok, d = verify_pin.verify_confirmation_signature(rec, dict(conf), node)
    check("an unsigned confirmation is AMBER, not a pass", ok is None, str(d))

    ok, d = verify_pin.verify_confirmation_signature(rec, dict(conf, signature=sign(other)), node)
    check("a signature from another key is rejected", ok is False, str(d))

    # Replay: a signature lifted onto a DIFFERENT pin record must not verify.
    other_rec = dict(rec, cid="bafkreiOTHER", commit="c" * 40)
    ok, d = verify_pin.verify_confirmation_signature(other_rec, good, node)
    check("a signature cannot be replayed onto another pin record", ok is False, str(d))

    # Tampering the confirmed bytes after signing must break it.
    ok, d = verify_pin.verify_confirmation_signature(
        rec, dict(good, file_sha256="sha256:" + "f" * 64), node)
    check("editing file_sha256 after signing breaks the signature", ok is False, str(d))

    # The gap @pipavlo82 found: conf["cid"] was outside the signed preimage, so
    # the CID attributed to a confirmer could be rewritten after signing. Since
    # verify_pin compares it to decide AMBER-vs-counted, editing it promoted a
    # parameter disagreement into a counted confirmation.
    ok, d = verify_pin.verify_confirmation_signature(
        rec, dict(good, cid="bafkreiSOMETHING-ELSE"), node)
    check("editing the confirmer's OWN cid after signing breaks the signature",
          ok is False, str(d))

    # A null CID is an honest abstention and must be signed as such — it must not
    # be interchangeable with a real one under the same signature.
    null_cid = dict(conf, cid=None)
    signed_null = dict(null_cid, signature=sign(acct, c=null_cid))
    ok, d = verify_pin.verify_confirmation_signature(rec, signed_null, node)
    check("a null-cid confirmation can be signed honestly", ok is True, str(d))
    ok, d = verify_pin.verify_confirmation_signature(
        rec, dict(signed_null, cid=rec["cid"]), node)
    check("backfilling a null cid from the record breaks the signature",
          ok is False, str(d))

    # ---- which BYTE of a signature you tamper with decides what the test proves.
    #
    # An eip712 signature is r||s||v. `v` is the recovery id, and v=0 recovers the
    # same address as v=27 (likewise 1/28) — malleable by construction. So the
    # obvious adversarial test, "flip the last byte and watch it break", flips the
    # one byte that CANNOT break, and reports GREEN while proving nothing.
    #
    # This was not hypothetical: that exact test was run against node 2's leg on the
    # bafybeiadnq… record and passed vacuously, after the same mutation had been
    # posted as real evidence on #49 — where it WAS sound, because invinoveritas
    # signs schnorr, which has no recovery byte. One mutation, meaningful on one
    # lane and worthless on the other.
    #
    # Both facts are asserted here so the next person reads them instead of
    # rediscovering them. Neither is a vulnerability: forging still needs the key.
    def flip(sig, i):
        return sig[:i] + ("0" if sig[i] != "0" else "1") + sig[i + 1:]

    body = good["signature"][2:] if good["signature"].startswith("0x") else good["signature"]
    pre = "0x" if good["signature"].startswith("0x") else ""

    v_int = int(body[128:130], 16)
    alt_v = {27: 0, 28: 1, 0: 27, 1: 28}.get(v_int)
    if alt_v is not None:
        malleable = pre + body[:128] + f"{alt_v:02x}"
        ok, d = verify_pin.verify_confirmation_signature(
            rec, dict(good, signature=malleable), node)
        check("eip712 v-byte is MALLEABLE — v=27/0 recover the same signer "
              "(so a last-byte flip proves nothing)", ok is True, str(d))

    ok, d = verify_pin.verify_confirmation_signature(
        rec, dict(good, signature=pre + flip(body, 8)), node)
    check("tampering a byte of r IS detected", ok is False, str(d))

    ok, d = verify_pin.verify_confirmation_signature(
        rec, dict(good, signature=pre + flip(body, 80)), node)
    check("tampering a byte of s IS detected", ok is False, str(d))

    # @pipavlo82, round 2: v1 bound conf["cid"] by NAME, and the same commit
    # added conf["tree_sha256"] — unbound, and the field site-tree counting acts
    # on. v2 signs every confirmation field by construction, so this holds for
    # fields that do not exist yet.
    tree_conf = dict(conf, tree_sha256="sha256:" + "c" * 64)
    signed_tree = dict(tree_conf, signature=sign(acct, c=tree_conf))
    ok, d = verify_confirmation_sig_or_skip(rec, signed_tree, node)
    check("a site-tree confirmation verifies", ok is True, str(d))
    ok, d = verify_confirmation_sig_or_skip(
        rec, dict(signed_tree, tree_sha256="sha256:" + "d" * 64), node)
    check("editing tree_sha256 after signing breaks the signature", ok is False, str(d))

    # The class, not the instance: a field nobody has written yet must be covered
    # the moment it exists, or we are back to maintaining a list by hand.
    future = dict(conf, some_future_field="original")
    signed_future = dict(future, signature=sign(acct, c=future))
    ok, d = verify_confirmation_sig_or_skip(
        rec, dict(signed_future, some_future_field="tampered"), node)
    check("editing an ARBITRARY new field breaks the signature (class, not instance)",
          ok is False, str(d))

    # cid_params live in the signed record context, so a record cannot be
    # re-verified under parameters nobody confirmed.
    ok, d = verify_confirmation_sig_or_skip(
        dict(rec, cid_params={"cid_version": 0}), good, node)
    check("changing the record's cid_params breaks the signature", ok is False, str(d))

    bad_grammar = dict(conf, signature="0xdeadbeef")
    ok, d = verify_pin.verify_confirmation_signature(rec, bad_grammar, node)
    check("malformed signature grammar is rejected", ok is False, str(d))


# ------------------------------------------------------------ record vectors
def record_vectors():
    print("\nrecord-level vectors (verify_pin.py end to end):")
    nodes = list(verify_pin.registered_nodes())
    if len(nodes) < 2:
        print("  amber fewer than 2 registered nodes — record vectors SKIPPED")
        return
    a, b = nodes[0], nodes[1]
    sha = "sha256:" + "b" * 64
    base = {"schema": "crc.pin-record.v0", "cid": "bafkreitest", "commit": "a" * 40,
            "artifact": "ui/index.html", "file_sha256": sha,
            "cid_params": {"cid_version": 1, "wrap_with_directory": False},
            "confirmations": [], "pinned_at": None, "tx": None}
    mk = lambda **kw: {**base, **kw}
    conf = lambda n: {"node_id": n, "rebuilt_at": "2026-08-09T00:00:00Z",
                      "file_sha256": sha, "cid": "bafkreitest"}

    cases = [
        ("THE ONE THAT MATTERED: two unsigned entries, one writer",
         mk(confirmations=[conf(a), conf(b)])),
        ("a single confirmation", mk(confirmations=[conf(a)])),
        ("the same node twice", mk(confirmations=[conf(a), conf(a)])),
        ("an unregistered node", mk(confirmations=[conf(a), conf("nobody-here")])),
        ("cid_params absent", mk(cid_params={}, confirmations=[conf(a), conf(b)])),
        ("wrong schema", mk(schema="crc.pin-record.v9", confirmations=[conf(a), conf(b)])),
        ("commit is not a sha", mk(commit="not-a-sha", confirmations=[conf(a), conf(b)])),
        ("no confirmations at all", mk(confirmations=[])),
        ("both confirmers computed no CID (null) — bytes only",
         mk(confirmations=[dict(conf(a), cid=None), dict(conf(b), cid=None)])),
    ]
    with tempfile.TemporaryDirectory() as td:
        for label, rec in cases:
            p = pathlib.Path(td) / "r.json"
            p.write_text(json.dumps(rec))
            r = subprocess.run([sys.executable, str(ROOT / "reference" / "verify_pin.py"), str(p)],
                               capture_output=True, text=True)
            green = r.stdout.strip().splitlines()[-1].startswith("GREEN") if r.stdout.strip() else False
            check(f"not GREEN: {label}", not green)


def site_tree_vectors():
    """End-to-end site-tree records — @pipavlo82 noted the matrix only covered
    the signature layer and the file lane."""
    print("\nsite-tree lane (end to end through verify_pin.py):")
    nodes = list(verify_pin.registered_nodes())
    if len(nodes) < 2:
        print("  amber fewer than 2 registered nodes — SKIPPED")
        return
    a, b = nodes[0], nodes[1]
    tree = "sha256:" + "e" * 64
    base = {"schema": "crc.pin-record.v0", "artifact_kind": "site-tree",
            "repo": "https://github.com/trustless-ai/trustless-ai-landing",
            "cid": "bafybeitest", "commit": "a" * 40, "tree_sha256": tree,
            "cid_params": {"cid_version": 1, "wrap_with_directory": False},
            "confirmations": [], "pinned_at": None, "tx": None}
    mk = lambda **kw: {**base, **kw}
    conf = lambda n: {"node_id": n, "rebuilt_at": "2026-08-09T00:00:00Z",
                      "tree_sha256": tree, "file_sha256": tree, "cid": "bafybeitest"}

    cases = [
        # THE SECURITY BOUNDARY: a record must not be able to choose what code runs.
        ("a record naming an arbitrary repo (arbitrary code execution)",
         mk(repo="https://github.com/attacker/evil", confirmations=[conf(a), conf(b)])),
        ("a repo that merely looks like ours",
         mk(repo="https://github.com/trustless-ai-evil/trustless-ai-landing",
            confirmations=[conf(a), conf(b)])),
        ("unsigned site-tree confirmations", mk(confirmations=[conf(a), conf(b)])),
        ("a site-tree record with one confirmation", mk(confirmations=[conf(a)])),
    ]
    with tempfile.TemporaryDirectory() as td:
        for label, rec in cases:
            p = pathlib.Path(td) / "r.json"
            p.write_text(json.dumps(rec))
            r = subprocess.run([sys.executable, str(ROOT / "reference" / "verify_pin.py"), str(p)],
                               capture_output=True, text=True)
            out = r.stdout.strip().splitlines()
            green = out[-1].startswith("GREEN") if out else False
            check(f"not GREEN: {label}", not green)
            if "arbitrary repo" in label or "looks like ours" in label:
                refused = any("allowlist" in ln for ln in out)
                check(f"  ...and refuses to execute its code", refused)


def signer_boundary_vector():
    """The signer must refuse a record-selected repo too.

    Found by auditing for the class after @pipavlo82 found it in verify_pin:
    the fix had been applied to the verifier and NOT to sign_confirmation, which
    clones and executes from the same field. Fixing one of two call sites is the
    same instance-not-class error, one layer up.
    """
    print("\nsigner boundary:")
    import os
    rec = {"schema": "crc.pin-record.v0", "artifact_kind": "site-tree",
           "repo": "https://github.com/attacker/evil", "cid": "bafybeitest",
           "commit": "a" * 40, "tree_sha256": "sha256:" + "e" * 64,
           "cid_params": {"cid_version": 1}, "confirmations": []}
    nodes = list(verify_pin.registered_nodes())
    if not nodes:
        print("  amber no registered nodes — SKIPPED")
        return
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "r.json"
        p.write_text(json.dumps(rec))
        env = dict(os.environ, CRC_KEY="0x" + "0" * 63 + "1")
        r = subprocess.run([sys.executable, str(ROOT / "reference" / "sign_confirmation.py"),
                            "--record", str(p), "--node", nodes[0]],
                           capture_output=True, text=True, env=env)
        refused = "not in the allowlist" in r.stdout
        check("sign_confirmation refuses a record-selected repo", refused)
        # And it must refuse BEFORE doing anything with the key.
        check("  ...and refuses before touching the key", "REFUSING TO SIGN" in r.stdout)


def real_record_vector():
    """Re-run every committed pin record. @pipavlo82 asked for a real one to
    rerun independently; this makes sure it never rots."""
    print("\ncommitted pin records:")
    pins = sorted((ROOT / "pins").glob("*.json")) if (ROOT / "pins").is_dir() else []
    if not pins:
        print("  amber no pins/*.json committed — nothing to re-run")
        return
    for p in pins:
        r = subprocess.run([sys.executable, str(ROOT / "reference" / "verify_pin.py"), str(p)],
                           capture_output=True, text=True)
        out = r.stdout.strip().splitlines()
        last = out[-1] if out else "(no output)"
        # Any verdict is acceptable; a CRASH is not. The record must remain
        # runnable by a third party, which is the entire point of committing it.
        check(f"{p.name[:26]}… runs and reports a verdict ({last.split(' ')[0]})",
              bool(out) and last.split(" ")[0] in ("GREEN", "AMBER", "RED"))


if __name__ == "__main__":
    print("pin rule — negative matrix")
    signature_vectors()
    record_vectors()
    site_tree_vectors()
    signer_boundary_vector()
    real_record_vector()
    print()
    print("all green — pin rule vectors" if not fails else f"{fails} FAILURE(S)")
    raise SystemExit(1 if fails else 0)
