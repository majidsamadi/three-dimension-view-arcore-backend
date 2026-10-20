"""Explicit synthetic test adapters.  They contain no I/O and no defaults."""
from dataclasses import dataclass

from wisestay_home_backend.domain.asset_reference import (
    ActorContext,
    CurrentActionFact,
    HomeAssetReference,
    HomeResourceFact,
    IdentityFact,
    ReferenceAction,
)


@dataclass(slots=True)
class StaticIdentityFacts:
    fact: IdentityFact

    def current_identity(self) -> IdentityFact:
        return self.fact


@dataclass(slots=True)
class StaticHomeResourceFacts:
    fact: HomeResourceFact

    def lookup_home(self, reference: HomeAssetReference) -> HomeResourceFact:
        return self.fact


@dataclass(slots=True)
class StaticCurrentActionFacts:
    fact: CurrentActionFact

    def current_home_action(
        self,
        actor: ActorContext,
        reference: HomeAssetReference,
        action: ReferenceAction,
    ) -> CurrentActionFact:
        return self.fact
