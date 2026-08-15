#!/usr/bin/env python3
"""Pure-stdlib BIP-340 schnorr verification (secp256k1), for nostr-nip01 Cell
envelopes in CI — no native dependency. Follows the BIP-340 reference verifier.

Pure stdlib on BOTH sides now. Verification always was: CI has to check any node's
Cell without assuming every native crypto lib is installed. Signing used to
delegate to coincurve on the reasoning that it "only ever runs locally" -- which
made create_cell.py need a native package to produce a Cell, and left the signing
path unexercised by CI. That is how the defect below survived a second time.

Found live 2026-08-09 (invinoveritas, confirming a real pin record): this file
had NO signing function at all, so sign_confirmation.py's `bip340.sign_hex(...)`
call for the nostr-nip01 envelope was unreachable dead code -- the only
registered nostr-nip01 node (this one) could never actually produce a signed
confirmation. Round-trip tested before use: sign_hex output verifies correctly
against this same file's own verify_hex() for the actual pubkey/key pair used."""
import hashlib


def sign_hex(msg_hex: str, privkey_hex: str) -> str:
    """BIP-340 schnorr sign msg_hex with privkey_hex (both hex). Returns hex.

    Was a coincurve wrapper. Now pure stdlib like the rest of the file, so
    sign_confirmation.py and create_cell.py need no native package — see
    schnorr_sign_raw for why that mattered.
    """
    return schnorr_sign_raw(bytes.fromhex(msg_hex), bytes.fromhex(privkey_hex)).hex()


P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8


def _tagged_hash(tag: bytes, msg: bytes) -> bytes:
    t = hashlib.sha256(tag).digest()
    return hashlib.sha256(t + t + msg).digest()


def _point_add(a, b):
    if a is None: return b
    if b is None: return a
    ax, ay = a; bx, by = b
    if ax == bx and (ay + by) % P == 0: return None
    if a == b:
        lam = (3 * ax * ax * pow(2 * ay, P - 2, P)) % P
    else:
        lam = ((by - ay) * pow(bx - ax, P - 2, P)) % P
    x = (lam * lam - ax - bx) % P
    return (x, (lam * (ax - x) - ay) % P)


def _point_mul(pt, k):
    r = None
    while k:
        if k & 1: r = _point_add(r, pt)
        pt = _point_add(pt, pt)
        k >>= 1
    return r


def _lift_x(x: int):
    if x >= P: return None
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if pow(y, 2, P) != y_sq: return None
    return (x, y if y % 2 == 0 else P - y)


def verify(msg: bytes, pubkey32: bytes, sig64: bytes) -> bool:
    """BIP-340: verify sig64 over msg (ANY length) for x-only pubkey32.

    The message used to be required to be exactly 32 bytes. That was correct for
    every caller in this repo -- validate_cell passes a NIP-01 event id,
    verify_pin and sign_confirmation pass a sha256 digest -- so the constraint
    never fired and was never noticed.

    It is not what BIP-340 says. The challenge is
    tagged_hash("BIP0340/challenge", r || P || m) over an m of arbitrary length,
    and a producer may legitimately sign canonical bytes directly rather than a
    digest of them. giskard09's composed-attestation BIP340 cell (argentum-core,
    examples/conformance/composed-attestation-bip340-cell) does exactly that: it
    signs 220 bytes of JCS. Against the old guard this verifier returned False --
    reporting someone else's correct artifact as a bad signature, which is worse
    than not checking it, because a length constraint is indistinguishable on the
    surface from a forgery.

    Fixed-length callers are unaffected: a 32-byte msg verifies exactly as before.
    """
    if len(pubkey32) != 32 or len(sig64) != 64:
        return False
    pk = _lift_x(int.from_bytes(pubkey32, "big"))
    if pk is None: return False
    r = int.from_bytes(sig64[:32], "big")
    s = int.from_bytes(sig64[32:], "big")
    if r >= P or s >= N: return False
    e = int.from_bytes(
        _tagged_hash(b"BIP0340/challenge", sig64[:32] + pubkey32 + msg), "big") % N
    R = _point_add(_point_mul((GX, GY), s), _point_mul(pk, N - e))
    return R is not None and R[1] % 2 == 0 and R[0] == r


def pubkey_gen(seckey: bytes) -> bytes:
    """x-only public key for a 32-byte secret key. Pure stdlib.

    Added because create_cell.py has called this since it was written and it did
    not exist -- see schnorr_sign below.
    """
    d = int.from_bytes(seckey, "big")
    if not (1 <= d <= N - 1):
        raise ValueError("secret key out of range")
    pt = _point_mul((GX, GY), d)
    if pt is None:
        raise ValueError("degenerate public key")
    return pt[0].to_bytes(32, "big")


def _has_even_y(pt) -> bool:
    return pt is not None and pt[1] % 2 == 0


def schnorr_sign_raw(msg: bytes, seckey: bytes, aux: bytes = b"\x00" * 32) -> bytes:
    """BIP-340 sign, pure stdlib, no native dependency.

    Signing used to delegate to coincurve, on the reasoning that it "only ever runs
    locally". That made create_cell.py -- the tool an outsider onboards with --
    require a native package to produce a Cell, and it made the signing path
    untestable in CI, which is how the missing-function defect below survived. All
    the scalar math was already here for verification; this reuses it.
    """
    d0 = int.from_bytes(seckey, "big")
    if not (1 <= d0 <= N - 1):
        raise ValueError("secret key out of range")
    Pt = _point_mul((GX, GY), d0)
    d = d0 if _has_even_y(Pt) else N - d0
    t = (d ^ int.from_bytes(_tagged_hash(b"BIP0340/aux", aux), "big")).to_bytes(32, "big")
    rand = _tagged_hash(b"BIP0340/nonce", t + Pt[0].to_bytes(32, "big") + msg)
    k0 = int.from_bytes(rand, "big") % N
    if k0 == 0:
        raise ValueError("nonce is zero")           # negligible, but never sign on it
    R = _point_mul((GX, GY), k0)
    k = k0 if _has_even_y(R) else N - k0
    e = int.from_bytes(_tagged_hash(
        b"BIP0340/challenge", R[0].to_bytes(32, "big") + Pt[0].to_bytes(32, "big") + msg), "big") % N
    sig = R[0].to_bytes(32, "big") + ((k + e * d) % N).to_bytes(32, "big")
    # Never hand back a signature this file's own verifier rejects.
    if not verify(msg, Pt[0].to_bytes(32, "big"), sig):
        raise ValueError("produced a signature that does not verify — refusing to return it")
    return sig


def schnorr_sign(msg: bytes, seckey: bytes) -> bytes:
    """BIP-340 sign, bytes in and bytes out.

    THE SECOND INSTANCE OF A DEFECT THIS FILE ALREADY DOCUMENTS. The docstring at
    the top records that sign_confirmation.py called a `sign_hex` that did not
    exist, making the only nostr-nip01 node unable to produce a signed
    confirmation. That was fixed by adding sign_hex -- and nobody checked whether
    any OTHER caller wanted a different name.

    create_cell.py:sign_nostr has always called bip340.pubkey_gen() and
    bip340.schnorr_sign(). Neither existed. The Nostr signing path of the tool CI
    describes as "the tool an outsider onboards with" raised AttributeError on
    first use, and CI only ever ran `create_cell.py --help`, which does not reach
    it. Found 2026-08-15 while investigating why this module rejected a valid
    third-party cell.
    """
    return schnorr_sign_raw(msg, seckey)


def verify_hex(msg_hex: str, pubkey_hex: str, sig_hex: str) -> bool:
    return verify(bytes.fromhex(msg_hex), bytes.fromhex(pubkey_hex), bytes.fromhex(sig_hex))
