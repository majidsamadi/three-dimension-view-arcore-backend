"""RFC 4226 HOTP and RFC 6238 TOTP (stdlib only).

Cognito software-token MFA uses the RFC 6238 defaults: HMAC-SHA1, 30 s steps, 6 digits.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import struct

_DIGESTS = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}


class TotpSecretError(ValueError):
    """The TOTP secret is not valid base32.  The message never contains the secret."""


def decode_base32_secret(secret: str) -> bytes:
    """Decode an authenticator-app base32 secret (spaces, lower case and missing padding allowed)."""
    cleaned = "".join(secret.split()).upper().rstrip("=")
    if not cleaned:
        raise TotpSecretError("TOTP secret is empty")
    try:
        key = base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except (binascii.Error, ValueError):
        raise TotpSecretError("TOTP secret is not base32") from None
    if not key:
        raise TotpSecretError("TOTP secret is empty")
    return key


def hotp(key: bytes, counter: int, *, digits: int = 6, digest: str = "sha1") -> str:
    if counter < 0:
        raise ValueError("counter must be non-negative")
    mac = hmac.new(key, struct.pack(">Q", counter), _DIGESTS[digest]).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def totp(key: bytes, unix_time: float, *, step: int = 30, digits: int = 6, digest: str = "sha1",
         t0: int = 0) -> str:
    return hotp(key, int((unix_time - t0) // step), digits=digits, digest=digest)


def seconds_left_in_step(unix_time: float, step: int = 30) -> float:
    return step - (unix_time % step)
