"""Bridge a verified request identity onto the existing ``IdentityFacts`` port (X.6)."""
from __future__ import annotations

from wisestay_home_backend.domain.asset_reference import (
    ActorContext,
    IdentityFact,
    IdentityFactStatus,
)
from wisestay_home_backend.ports.identity import VerifiedIdentity


class RequestIdentityFacts:
    def __init__(self, verified: VerifiedIdentity) -> None:
        self._verified = verified

    @property
    def actor(self) -> ActorContext:
        return ActorContext(self._verified.user_id, self._verified.application_id)

    def current_identity(self) -> IdentityFact:
        return IdentityFact(IdentityFactStatus.CURRENT, self.actor)
