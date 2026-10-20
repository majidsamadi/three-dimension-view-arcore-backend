"""Central WiseStay (Cognito) access-token verification (plan X.6, HSB-01.3+).

Known limits, documented rather than hidden: there is no online revocation
check, so a token is honoured until ``exp``; organisation membership is not in
the token.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import time
from typing import Callable

from wisestay_home_backend.adapters import rs256
from wisestay_home_backend.domain.asset_reference import IdentityRequired
from wisestay_home_backend.ports.identity import JwksSource, VerifiedIdentity

MAX_AUTHORIZATION_CHARS = 12_000
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


def _b64url_decode(segment: str) -> bytes:
    if not _SEGMENT.match(segment):
        raise IdentityRequired("token segment is not base64url")
    try:
        return base64.urlsafe_b64decode((segment + "=" * (-len(segment) % 4)).encode("ascii"))
    except (binascii.Error, ValueError) as exc:
        raise IdentityRequired("token segment is not base64url") from exc


def _json_segment(segment: str) -> dict:
    try:
        value = json.loads(_b64url_decode(segment).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise IdentityRequired("token segment is not JSON") from exc
    if not isinstance(value, dict):
        raise IdentityRequired("token segment is not a JSON object")
    return value


def _int_claim(claims: dict, name: str, *, required: bool) -> int | None:
    value = claims.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise IdentityRequired(f"claim {name} must be an integer")
    return value


class CentralJwtIdentityVerifier:
    def __init__(self, issuer: str, client_id: str, application_id: str, jwks: JwksSource,
                 clock: Callable[[], float] = time.time, leeway_s: int = 60) -> None:
        if not issuer or not client_id or not application_id:
            raise ValueError("issuer, client_id and application_id are required")
        self._issuer = issuer
        self._client_id = client_id
        self._application_id = application_id
        self._jwks = jwks
        self._clock = clock
        self._leeway_s = leeway_s

    def verify(self, authorization: str | None) -> VerifiedIdentity:
        # 1. "Bearer <ascii token>" with exactly three base64url segments.
        if not isinstance(authorization, str) or len(authorization) > MAX_AUTHORIZATION_CHARS:
            raise IdentityRequired("a bearer token is required")
        if not authorization.startswith("Bearer ") or not authorization.isascii():
            raise IdentityRequired("a bearer token is required")
        token = authorization[len("Bearer "):]
        segments = token.split(".")
        if len(segments) != 3 or not all(_SEGMENT.match(s) for s in segments):
            raise IdentityRequired("token must have three base64url segments")
        header_b64, payload_b64, signature_b64 = segments
        # 2. JOSE header.
        header = _json_segment(header_b64)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
            raise IdentityRequired("token must be RS256 with a kid")
        # 3. Key (may raise IdentityUnavailable when the JWKS cannot be loaded).
        key = self._jwks.key(kid)
        if key is None or not rs256.acceptable_key(key.n, key.e):
            raise IdentityRequired("token key is unknown or unacceptable")
        # 4. Signature.
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        if not rs256.verify(key.n, key.e, signing_input, _b64url_decode(signature_b64)):
            raise IdentityRequired("token signature is invalid")
        # 5. Claims.
        claims = _json_segment(payload_b64)
        now = self._clock()
        if claims.get("iss") != self._issuer:
            raise IdentityRequired("token issuer mismatch")
        if claims.get("token_use") != "access":
            raise IdentityRequired("token is not an access token")
        if claims.get("client_id") != self._client_id:
            raise IdentityRequired("token client mismatch")
        exp = _int_claim(claims, "exp", required=True)
        iat = _int_claim(claims, "iat", required=True)
        nbf = _int_claim(claims, "nbf", required=False)
        if not exp > now - self._leeway_s:
            raise IdentityRequired("token expired")
        if not iat <= now + self._leeway_s:
            raise IdentityRequired("token issued in the future")
        if nbf is not None and not nbf <= now + self._leeway_s:
            raise IdentityRequired("token not yet valid")
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            raise IdentityRequired("token subject missing")
        return VerifiedIdentity(sub, self._application_id, self._client_id, exp)
