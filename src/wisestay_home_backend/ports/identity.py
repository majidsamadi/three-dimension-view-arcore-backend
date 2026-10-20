"""Central identity verification port (plan X.6, HSB-01.3+).

Every route requires a verified central WiseStay access token.  The verifier
raises ``IdentityRequired`` (401 ``identity_required``) or
``IdentityUnavailable`` (503 ``identity_unavailable``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from wisestay_home_backend.domain.asset_reference import BoundaryError, IdentityRequired


class IdentityUnavailable(BoundaryError):
    code = "identity_unavailable"


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    user_id: str            # token "sub"
    application_id: str     # constant for this backend: "home-scanner"
    client_id: str          # token "client_id" (UM app client)
    expires_at: int         # token "exp"


@dataclass(frozen=True, slots=True)
class RsaPublicKey:
    n: int
    e: int


class IdentityVerifier(Protocol):
    def verify(self, authorization: str | None) -> VerifiedIdentity: ...


class JwksSource(Protocol):
    def key(self, kid: str) -> RsaPublicKey | None: ...


__all__ = ["IdentityRequired", "IdentityUnavailable", "IdentityVerifier", "JwksSource",
           "RsaPublicKey", "VerifiedIdentity"]
