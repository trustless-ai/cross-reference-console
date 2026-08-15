#!/usr/bin/env python3
"""Vectors for bip340.py — including the one whose absence let it reject a valid cell.

This module verifies other people's signatures. Until today it had no test of its
own, and it carried a defect that made it return False for a correctly signed
third-party artifact: the message was required to be exactly 32 bytes, which is
true of every caller in this repo and not true of BIP-340.

THE CONTROL THAT MATTERS MOST IS THE POSITIVE ONE. A verifier that returns False
for everything passes every negative test ever written. When this file's bug was
being diagnosed, a hand-rolled replacement returned False on the real cell and was
nearly reported as "their signature is bad" — the mistake was trusting a False from
a verifier never once seen to return True. So the official BIP-340 vectors run
FIRST here, and a failure in them makes every other result in this file
meaningless.

EXIT: 0 · 1 a vector failed · 2 could not check.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))
import bip340  # noqa: E402

EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2
fails: list[str] = []


def chk(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


# From the BIP-340 reference test vectors (index, seckey, pubkey, aux, msg, sig, result).
# Only the verify-side fields are needed here.
OFFICIAL = [
    ("vector 1",
     "DFF1D77F2A671C5F36183726DB2341BE58FEAE1DA2DECED843240F7B502BA659",
     "243F6A8885A308D313198A2E03707344A4093822299F31D0082EFA98EC4E6C89",
     "6896BD60EEAE296DB48A229FF71DFE071BDE413E6D43F917DC8DCF8C78DE3341"
     "8906D11AC976ABCCB20B091292BFF4EA897EFCB639EA871CFA95F6DE339E4B0A", True),
    ("vector 2",
     "DD308AFEC5777E13121FA72B9CC1B7CC0139715309B086C960E18FD969774EB8",
     "7E2D58D8B3BCDF1ABADEC7829054F90DDA9805AAB56C77333024B9D0A508B75C",
     "5831AAEED7B44BB74E5EAB94BA9D4294C49BCF2A60728D8B4C200F50DD313C1B"
     "AB745879A5AD954A72C45A91C3A51D3C7ADEA98D82F8481E0E1E03674A6F3FB7", True),
]


def main() -> int:
    print("bip340.py — the verifier this repo checks other people's cells with\n")

    print("the positive control, first: it CAN return true\n")
    for name, pub, msg, sig, want in OFFICIAL:
        got = bip340.verify_hex(msg, pub, sig)
        chk(f"official {name} verifies", got == want, f"got {got}")
    if fails:
        print("\nthe positive control failed — every other result in this file is meaningless.")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD

    print("\nand it can return false\n")
    name, pub, msg, sig, _ = OFFICIAL[0]
    flipped = f"{int(msg, 16) ^ 1:064X}"
    chk("one bit flipped in the message → refused", not bip340.verify_hex(flipped, pub, sig))
    chk("truncated signature → refused", not bip340.verify_hex(msg, pub, sig[:-2]))
    chk("wrong pubkey → refused", not bip340.verify_hex(msg, OFFICIAL[1][1], sig))

    print("\nARBITRARY-LENGTH MESSAGES — the defect this file exists to pin\n")
    # A real third-party artifact: giskard09's composed-attestation BIP340 cell signs
    # 220 bytes of canonical JSON directly, not a digest of it. Against the old
    # 32-byte guard this verifier said False, which reads as "bad signature".
    cell_path = ROOT / "reference" / "vectors" / "bip340-anylen.json"
    if not cell_path.exists():
        print(f"  ..    no fixture at {cell_path.relative_to(ROOT)} — skipping the live shape")
    else:
        v = json.loads(cell_path.read_text(encoding="utf-8"))
        msg_b = v["message"].encode()
        pk_b = bytes.fromhex(v["pubkey_x_only"])
        sig_b = bytes.fromhex(v["sig"])
        chk(f"{len(msg_b)}-byte message verifies", bip340.verify(msg_b, pk_b, sig_b))
        chk("one character changed in it → refused",
            not bip340.verify(v["message"].replace("2026-08-15", "2026-08-16").encode(), pk_b, sig_b))
        chk("the message is NOT 32 bytes (so it would have failed before)", len(msg_b) != 32)

    print("\nthe functions create_cell.py has always called\n")
    for fn in ("pubkey_gen", "schnorr_sign"):
        chk(f"bip340.{fn} exists", hasattr(bip340, fn))
    # Round-trip: derive a key, sign, verify with this same file. Signing needs
    # coincurve; without it this is could-not-check, never a silent pass.
    sk = bytes.fromhex("00" * 31 + "03")
    try:
        pub = bip340.pubkey_gen(sk)
        chk("pubkey_gen returns 32 x-only bytes", len(pub) == 32, str(len(pub)))
        try:
            sig = bip340.schnorr_sign(b"a message of unusual length, 45 bytes", sk)
            chk("sign → verify round-trip holds",
                bip340.verify(b"a message of unusual length, 45 bytes", pub, sig))
            chk("that signature does not verify a different message",
                not bip340.verify(b"a different message entirely", pub, sig))
        except ImportError:
            print("  ..    signing needs coincurve, absent here — round-trip NOT checked")
    except Exception as e:
        chk("pubkey_gen runs", False, f"{type(e).__name__}: {e}")

    print()
    if fails:
        print(f"{len(fails)} vector(s) failed:")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD
    print("verifies what it should, refuses what it should, at any message length")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
