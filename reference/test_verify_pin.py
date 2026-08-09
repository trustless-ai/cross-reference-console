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


if __name__ == "__main__":
    print("pin rule — negative matrix")
    signature_vectors()
    record_vectors()
    print()
    print("all green — pin rule vectors" if not fails else f"{fails} FAILURE(S)")
    raise SystemExit(1 if fails else 0)
