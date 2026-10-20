"""Fail-closed exact Home reference resolver."""
from __future__ import annotations

from wisestay_home_backend.domain.asset_reference import (
    ActionDecision,
    ActionDenied,
    AuthorityFactStatus,
    DependencyUnavailable,
    HomeAssetReference,
    IdentityFactStatus,
    IdentityRequired,
    ReferenceAction,
    ReferenceMismatch,
    ResolvedHomeReference,
    ResourceFactStatus,
    ResourceNotFound,
    ResourceWithdrawn,
    StaleAuthorityFact,
    WrongAccount,
)
from wisestay_home_backend.ports.reference_authority import (
    CurrentActionFacts,
    HomeResourceFacts,
    IdentityFacts,
)


class HomeReferenceResolver:
    """Validate an exact caller-supplied Home reference using injected facts.

    The resolver intentionally has no fallback from a property label, local
    project name, later scene revision, cached authority or another account.
    """

    def __init__(
        self,
        identity_facts: IdentityFacts,
        resource_facts: HomeResourceFacts,
        action_facts: CurrentActionFacts,
    ) -> None:
        self._identity_facts = identity_facts
        self._resource_facts = resource_facts
        self._action_facts = action_facts

    def resolve(
        self,
        reference: HomeAssetReference,
        action: ReferenceAction,
    ) -> ResolvedHomeReference:
        identity = self._identity_facts.current_identity()
        if identity.status is IdentityFactStatus.UNAVAILABLE:
            raise DependencyUnavailable("canonical identity is unavailable")
        if identity.status is IdentityFactStatus.WRONG_ACCOUNT:
            raise WrongAccount("current canonical account does not match the request context")
        if identity.status is not IdentityFactStatus.CURRENT:
            raise IdentityRequired("a current canonical identity is required")
        if identity.context is None:
            raise DependencyUnavailable("current canonical actor context is incomplete")

        resource = self._resource_facts.lookup_home(reference)
        if resource.status is ResourceFactStatus.UNAVAILABLE:
            raise DependencyUnavailable("home resource authority is unavailable")
        if resource.status is ResourceFactStatus.WITHDRAWN:
            raise ResourceWithdrawn("the exact Home reference is withdrawn")
        if resource.status is ResourceFactStatus.NOT_FOUND:
            raise ResourceNotFound("the exact Home reference was not found")
        if resource.status is not ResourceFactStatus.CURRENT or resource.reference is None:
            raise DependencyUnavailable("home resource fact is incomplete")
        if resource.reference != reference:
            raise ReferenceMismatch(
                "resource fact does not match the caller-supplied scene/property revision"
            )

        authority = self._action_facts.current_home_action(identity.context, reference, action)
        if authority.status is AuthorityFactStatus.UNAVAILABLE:
            raise DependencyUnavailable("current Home action authority is unavailable")
        if authority.status is not AuthorityFactStatus.CURRENT:
            raise DependencyUnavailable("current Home action authority is incomplete")

        # An outdated adapter with no organization/relationship binding must
        # fail unavailable, not be treated as a personal-scope ALLOW fact.
        try:
            action_org = authority.organization_id
            action_relationship = authority.relationship_id
        except AttributeError as exc:
            raise DependencyUnavailable("current action actor-scope fact is incomplete") from exc
        expected = (
            identity.context.user_id,
            identity.context.application_id,
            identity.context.organization_id,
            identity.context.relationship_id,
            reference.scene_id,
            reference.scene_revision,
            reference.property_id,
            action,
        )
        observed = (
            authority.user_id,
            authority.application_id,
            action_org,
            action_relationship,
            authority.scene_id,
            authority.scene_revision,
            authority.property_id,
            authority.action,
        )
        if (
            any(item is None for item in (authority.user_id, authority.application_id,
                authority.scene_id, authority.scene_revision, authority.property_id,
                authority.action))
            or authority.decision is None
            or any(value is not None and (not isinstance(value, str) or not value.strip())
                   for value in (action_org, action_relationship))
        ):
            raise DependencyUnavailable("current action authority fact is incomplete")
        if observed != expected:
            raise StaleAuthorityFact("authority fact is for a different actor/resource/version/action")
        if authority.decision is not ActionDecision.ALLOW:
            raise ActionDenied("current authority does not allow the requested Home action")

        return ResolvedHomeReference(reference=reference, actor=identity.context, action=action)
