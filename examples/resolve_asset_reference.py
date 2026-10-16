"""Runnable synthetic example for C-P03-ASSET-REFERENCE-CODE-01."""
from dataclasses import dataclass

from wisestay_home_backend.application.resolve_asset_reference import HomeReferenceResolver
from wisestay_home_backend.domain.asset_reference import (
    ActionDecision,
    ActorContext,
    AuthorityFactStatus,
    CurrentActionFact,
    HomeAssetReference,
    HomeResourceFact,
    IdentityFact,
    IdentityFactStatus,
    ReferenceAction,
    ResourceFactStatus,
)


@dataclass
class IdentityAdapter:
    def current_identity(self) -> IdentityFact:
        return IdentityFact(IdentityFactStatus.CURRENT, ActorContext("SYN-USER-A", "home-example"))


@dataclass
class ResourceAdapter:
    reference: HomeAssetReference

    def lookup_home(self, reference: HomeAssetReference) -> HomeResourceFact:
        return HomeResourceFact(ResourceFactStatus.CURRENT, self.reference)


@dataclass
class ActionAdapter:
    reference: HomeAssetReference

    def current_home_action(self, actor, reference, action) -> CurrentActionFact:
        return CurrentActionFact(
            status=AuthorityFactStatus.CURRENT,
            decision=ActionDecision.ALLOW,
            user_id=actor.user_id,
            application_id=actor.application_id,
            scene_id=self.reference.scene_id,
            scene_revision=self.reference.scene_revision,
            property_id=self.reference.property_id,
            action=action,
        )


reference = HomeAssetReference("SYN-HOME-1", "v1", "SYN-PROPERTY-1")
resolved = HomeReferenceResolver(
    IdentityAdapter(), ResourceAdapter(reference), ActionAdapter(reference)
).resolve(reference, ReferenceAction.READ_METADATA)
print(f"resolved {resolved.reference.scene_id}@{resolved.reference.scene_revision} for {resolved.actor.user_id}")
