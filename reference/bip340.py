#!/usr/bin/env python3
"""Pure-stdlib BIP-340 schnorr verification (secp256k1), for nostr-nip01 Cell
envelopes in CI — no native dependency. Follows the BIP-340 reference verifier.

Verification is pure-stdlib deliberately -- CI needs to check any node's Cell
without assuming every possible native crypto lib is installed. Signing has no
such constraint (it only ever runs locally, by the one node that holds the key),
so sign_hex below uses coincurve (imported lazily, inside the function) rather
than reimplementing scalar/point signing math in pure Python -- the verify path
above stays exactly as dependency-free as before.

Found live 2026-08-09 (invinoveritas, confirming a real pin record): this file
had NO signing function at all, so sign_confirmation.py's `bip340.sign_hex(...)`
call for the nostr-nip01 envelope was unreachable dead code -- the only
registered nostr-nip01 node (this one) could never actually produce a signed
confirmation. Round-trip tested before use: sign_hex output verifies correctly
against this same file's own verify_hex() for the actual pubkey/key pair used."""
import hashlib


def sign_hex(msg_hex: str, privkey_hex: str) -> str:
    """BIP-340 schnorr sign msg_hex (32-byte digest, hex) with privkey_hex (32-byte
    raw private key, hex). Returns the 64-byte signature as hex, matching
    verify_hex's expected format exactly."""
    from coincurve import PrivateKey
    sk = PrivateKey(bytes.fromhex(privkey_hex))
    sig = sk.sign_schnorr(bytes.fromhex(msg_hex))
    return sig.hex()

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


def verify(msg32: bytes, pubkey32: bytes, sig64: bytes) -> bool:
    """BIP-340: verify sig64 over msg32 for x-only pubkey32."""
    if len(msg32) != 32 or len(pubkey32) != 32 or len(sig64) != 64:
        return False
    pk = _lift_x(int.from_bytes(pubkey32, "big"))
    if pk is None: return False
    r = int.from_bytes(sig64[:32], "big")
    s = int.from_bytes(sig64[32:], "big")
    if r >= P or s >= N: return False
    e = int.from_bytes(
        _tagged_hash(b"BIP0340/challenge", sig64[:32] + pubkey32 + msg32), "big") % N
    R = _point_add(_point_mul((GX, GY), s), _point_mul(pk, N - e))
    return R is not None and R[1] % 2 == 0 and R[0] == r


def verify_hex(msg_hex: str, pubkey_hex: str, sig_hex: str) -> bool:
    return verify(bytes.fromhex(msg_hex), bytes.fromhex(pubkey_hex), bytes.fromhex(sig_hex))
