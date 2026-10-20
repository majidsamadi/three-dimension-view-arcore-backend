"""Stdlib RSASSA-PKCS1-v1_5 / SHA-256 signature verification (RFC 8017 §8.2.2).

Only verification is implemented: integer ``pow``, EMSA-PKCS1-v1_5 encoding
with the SHA-256 DigestInfo prefix, and a constant-time comparison.
"""
from __future__ import annotations

import hashlib
import hmac

# DER DigestInfo prefix for SHA-256 (RFC 8017 §9.2 note 1).
SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
MIN_MODULUS_BITS = 2048
REQUIRED_EXPONENT = 65537


def emsa_pkcs1_v1_5_sha256(message: bytes, em_len: int) -> bytes:
    t = SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
    if em_len < len(t) + 11:
        raise ValueError("intended encoded message length too short")
    return b"\x00\x01" + b"\xff" * (em_len - len(t) - 3) + b"\x00" + t


def acceptable_key(n: int, e: int) -> bool:
    return isinstance(n, int) and n.bit_length() >= MIN_MODULUS_BITS and e == REQUIRED_EXPONENT


def verify(n: int, e: int, message: bytes, signature: bytes) -> bool:
    """Return True only for a valid RS256 signature under an acceptable key."""
    if not acceptable_key(n, e):
        return False
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False
    em = pow(s, e, n).to_bytes(k, "big")
    return hmac.compare_digest(em, emsa_pkcs1_v1_5_sha256(message, k))
