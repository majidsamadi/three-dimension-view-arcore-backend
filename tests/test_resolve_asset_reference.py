from __future__ import annotations

import unittest

from wisestay_home_backend.application.resolve_asset_reference import HomeReferenceResolver
from wisestay_home_backend.domain.asset_reference import (
    ActionDecision,
    ActionDenied,
    ActorContext,
    AuthorityFactStatus,
    CurrentActionFact,
    DependencyUnavailable,
    HomeAssetReference,
    HomeResourceFact,
    IdentityFact,
    IdentityFactStatus,
    IdentityRequired,
    ReferenceAction,
    ReferenceMismatch,
    ResourceFactStatus,
    ResourceNotFound,
    ResourceWithdrawn,
    StaleAuthorityFact,
    WrongAccount,
)
from tests.fakes import StaticCurrentActionFacts, StaticHomeResourceFacts, StaticIdentityFacts


ACTOR = ActorContext("USER-A", "home-scanner-web")
REF = HomeAssetReference("HOME-A", "7", "PROPERTY-A")


def action_fact(
    *,
    status: AuthorityFactStatus = AuthorityFactStatus.CURRENT,
    decision: ActionDecision | None = ActionDecision.ALLOW,
    user_id: str | None = ACTOR.user_id,
    application_id: str | None = ACTOR.application_id,
    scene_id: str | None = REF.scene_id,
    scene_revision: str | None = REF.scene_revision,
    property_id: str | None = REF.property_id,
    action: ReferenceAction | None = ReferenceAction.READ_METADATA,
) -> CurrentActionFact:
    return CurrentActionFact(
        status=status,
        decision=decision,
        user_id=user_id,
        application_id=application_id,
        scene_id=scene_id,
        scene_revision=scene_revision,
        property_id=property_id,
        action=action,
    )


def resolver(
    *,
    identity: IdentityFact | None = None,
    resource: HomeResourceFact | None = None,
    authority: CurrentActionFact | None = None,
) -> HomeReferenceResolver:
    return HomeReferenceResolver(
        StaticIdentityFacts(identity or IdentityFact(IdentityFactStatus.CURRENT, ACTOR)),
        StaticHomeResourceFacts(resource or HomeResourceFact(ResourceFactStatus.CURRENT, REF)),
        StaticCurrentActionFacts(authority or action_fact()),
    )


class HomeReferenceResolverTests(unittest.TestCase):
    def test_resolves_only_the_exact_caller_supplied_reference(self):
        resolved = resolver().resolve(REF, ReferenceAction.READ_METADATA)
        self.assertEqual(resolved.reference, REF)
        self.assertEqual(resolved.actor, ACTOR)
        self.assertEqual(resolved.action, ReferenceAction.READ_METADATA)

    def test_signed_out_identity_fails_without_creating_a_user(self):
        with self.assertRaises(IdentityRequired):
            resolver(identity=IdentityFact(IdentityFactStatus.SIGNED_OUT)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_identity_unavailable_is_not_treated_as_signed_out_or_allowed(self):
        with self.assertRaises(DependencyUnavailable):
            resolver(identity=IdentityFact(IdentityFactStatus.UNAVAILABLE)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_wrong_account_fails_closed(self):
        with self.assertRaises(WrongAccount):
            resolver(identity=IdentityFact(IdentityFactStatus.WRONG_ACCOUNT, ACTOR)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_missing_resource_does_not_create_a_property_or_scene(self):
        with self.assertRaises(ResourceNotFound):
            resolver(resource=HomeResourceFact(ResourceFactStatus.NOT_FOUND)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_resource_unavailable_does_not_become_not_found_or_allowed(self):
        with self.assertRaises(DependencyUnavailable):
            resolver(resource=HomeResourceFact(ResourceFactStatus.UNAVAILABLE)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_withdrawn_exact_reference_fails(self):
        with self.assertRaises(ResourceWithdrawn):
            resolver(resource=HomeResourceFact(ResourceFactStatus.WITHDRAWN, REF)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_later_scene_revision_cannot_replace_requested_revision(self):
        later = HomeAssetReference("HOME-A", "8", "PROPERTY-A")
        with self.assertRaises(ReferenceMismatch):
            resolver(resource=HomeResourceFact(ResourceFactStatus.CURRENT, later)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_different_property_cannot_replace_requested_property(self):
        wrong_property = HomeAssetReference("HOME-A", "7", "PROPERTY-B")
        with self.assertRaises(ReferenceMismatch):
            resolver(resource=HomeResourceFact(ResourceFactStatus.CURRENT, wrong_property)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_action_unavailable_does_not_become_denied_or_allowed(self):
        fact = action_fact(status=AuthorityFactStatus.UNAVAILABLE, decision=None)
        with self.assertRaises(DependencyUnavailable):
            resolver(authority=fact).resolve(REF, ReferenceAction.READ_METADATA)

    def test_absent_current_action_decision_is_unavailable_not_allowed(self):
        with self.assertRaises(DependencyUnavailable):
            resolver(authority=action_fact(decision=None)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_action_denial_fails_closed(self):
        with self.assertRaises(ActionDenied):
            resolver(authority=action_fact(decision=ActionDecision.DENY)).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_stale_authority_for_other_revision_cannot_authorize_request(self):
        with self.assertRaises(StaleAuthorityFact):
            resolver(authority=action_fact(scene_revision="8")).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_stale_authority_for_other_account_cannot_authorize_request(self):
        with self.assertRaises(StaleAuthorityFact):
            resolver(authority=action_fact(user_id="USER-B")).resolve(
                REF, ReferenceAction.READ_METADATA
            )

    def test_view_reference_requires_its_own_exact_action_fact(self):
        with self.assertRaises(StaleAuthorityFact):
            resolver(authority=action_fact(action=ReferenceAction.READ_METADATA)).resolve(
                REF, ReferenceAction.VIEW_REFERENCE
            )


if __name__ == "__main__":
    unittest.main()
