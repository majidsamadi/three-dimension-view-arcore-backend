"""Injected ports for released identity/resource/current-action contracts.

Live I/O implementations are deliberately not part of C-P03-ASSET-REFERENCE-CODE-01.
"""
from __future__ import annotations

from typing import Protocol

from wisestay_home_backend.domain.asset_reference import (
    ActorContext,
    CurrentActionFact,
    HomeAssetReference,
    HomeResourceFact,
    IdentityFact,
    ReferenceAction,
)


class IdentityFacts(Protocol):
    def current_identity(self) -> IdentityFact: ...


class HomeResourceFacts(Protocol):
    def lookup_home(self, reference: HomeAssetReference) -> HomeResourceFact: ...


class CurrentActionFacts(Protocol):
    def current_home_action(
        self,
        actor: ActorContext,
        reference: HomeAssetReference,
        action: ReferenceAction,
    ) -> CurrentActionFact: ...
