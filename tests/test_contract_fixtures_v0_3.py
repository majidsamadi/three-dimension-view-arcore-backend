"""Home backend consumer tests for the DRAFT / SYNTHETIC B-RFX v0.3 fixtures (P03).

HSB-01.1-HSB-01.2.  Fixture examples are mapped onto the existing
`HomeReferenceResolver` with synthetic fakes; the resolver is not modified.
Status: component-tested only.  Passing here does not freeze or accept any
fixture (freeze needs owner Q01/Q03/Q04/Q05/Q06).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import unittest

from tests.contract_fixtures import (
    DRAFT_STATUS,
    FIXTURE_IDS,
    DraftContractFixtures,
    IncompatibleFixtureVersion,
    select_effective,
    split_label,
)
from wisestay_home_backend.application.resolve_asset_reference import HomeReferenceResolver
from wisestay_home_backend.domain.asset_reference import (
    ActionDecision,
    ActionDenied,
    ActorContext,
    AuthorityFactStatus,
    CurrentActionFact,
    HomeAssetReference,
    HomeResourceFact,
    IdentityFact,
    IdentityFactStatus,
    IdentityRequired,
    ReferenceAction,
    ReferenceMismatch,
    ResourceFactStatus,
    ResourceWithdrawn,
    StaleAuthorityFact,
    WrongAccount,
)
from tests.fakes import StaticCurrentActionFacts, StaticHomeResourceFacts, StaticIdentityFacts

FIXTURES = DraftContractFixtures()
APP = "home-scanner-web"
PROPERTY = "PROPERTY-A"
ACTOR = ActorContext("ACCOUNT-A", APP)

# Examples with a Home backend consumer in this slice.  Every other effective
# example is listed as an explicit skip so new examples cannot go unnoticed.
MAPPED = {
    ("B-RFX-01", "local project name is not canonical association"),
    ("B-RFX-03", "foreign revision"),
    ("B-RFX-03", "incomplete candidate V2 while accepted complete V1 remains unchanged"),
    ("B-RFX-04", "local versus remote cancellation"),
    ("B-RFX-04", "old scope receipt"),
    ("B-RFX-06", "restored metadata after withdrawal"),
    ("B-RFX-06", "wrong resource"),
    ("B-RFX-07", "capturing phone offline versus second viewer"),
}


def home_ref(label: str, property_id: str = PROPERTY) -> HomeAssetReference:
    scene_id, revision = split_label(label)
    return HomeAssetReference(scene_id, revision, property_id)


def allow(actor: ActorContext, ref: HomeAssetReference, action: ReferenceAction,
          decision: ActionDecision = ActionDecision.ALLOW) -> CurrentActionFact:
    return CurrentActionFact(
        status=AuthorityFactStatus.CURRENT,
        decision=decision,
        user_id=actor.user_id,
        application_id=actor.application_id,
        organization_id=actor.organization_id,
        relationship_id=actor.relationship_id,
        scene_id=ref.scene_id,
        scene_revision=ref.scene_revision,
        property_id=ref.property_id,
        action=action,
    )


def resolver(identity: IdentityFact, resource: HomeResourceFact,
             authority: CurrentActionFact) -> HomeReferenceResolver:
    return HomeReferenceResolver(
        StaticIdentityFacts(identity),
        StaticHomeResourceFacts(resource),
        StaticCurrentActionFacts(authority),
    )


@dataclass(slots=True)
class RecordingFacts:
    """Mutable synthetic facts that log every lookup the resolver makes."""
    identity: IdentityFact
    resource: HomeResourceFact
    authority: CurrentActionFact
    calls: list[str] = field(default_factory=list)

    def current_identity(self) -> IdentityFact:
        self.calls.append("identity")
        return self.identity

    def lookup_home(self, reference: HomeAssetReference) -> HomeResourceFact:
        self.calls.append("resource")
        return self.resource

    def current_home_action(self, actor, reference, action) -> CurrentActionFact:
        self.calls.append("authority")
        return self.authority


class DraftFixtureStructureTests(unittest.TestCase):
    def test_draft_all_eight_effective_fixtures_load_with_matching_ids(self):
        self.assertEqual(tuple(sorted(FIXTURES.effective)), FIXTURE_IDS)
        for fixture_id, (fixture, _, filename) in FIXTURES.originals.items():
            self.assertTrue(filename.startswith(f"{fixture_id}_"), filename)
            self.assertEqual(fixture["fixture_id"], fixture_id)

    def test_draft_status_and_unselected_fields_stay_null(self):
        for fixture_id, fixture in FIXTURES.effective.items():
            with self.subTest(fixture_id=fixture_id):
                self.assertEqual(fixture["status"], DRAFT_STATUS)
                self.assertIsNone(fixture["codec"])
                self.assertIsNone(fixture["protection_scheme"])
                self.assertIsNone(fixture["coordinate_convention"])
                self.assertEqual(fixture["physical_measurement_receipts"], [])
                for item in fixture["examples"]:
                    self.assertTrue(item["draft_expected"].strip(), item["example"])

    def test_draft_b_rfx_03_revision_0_2_supersedes_original(self):
        effective = FIXTURES.fixture("B-RFX-03")
        original = FIXTURES.originals["B-RFX-03"][0]
        self.assertEqual(effective["fixture_revision"], "0.2")
        self.assertEqual(effective["revises"]["correction_id"], "BC03-COR-01")
        self.assertIsNot(effective, original)
        self.assertEqual(original["status"], DRAFT_STATUS)
        self.assertNotIn("fixture_revision", original)
        self.assertNotEqual(effective["examples"][0]["draft_expected"],
                            original["examples"][0]["draft_expected"])
        self.assertIsNone(effective["receipt_scope"]["whole_fixture_contract_acceptance"])
        self.assertFalse(effective["receipt_scope"]["runtime_execution"])

    def test_draft_delta_records_are_all_proposed_not_frozen(self):
        records = FIXTURES.delta_records
        self.assertEqual({r["status"] for r in records}, {"PROPOSED_NOT_FROZEN"})
        ids = {r["id"] for r in records}
        for n in range(17, 22):
            self.assertIn(f"DELTA-{n}", ids)

    def test_draft_incompatible_fixture_revision_is_refused(self):
        """Negative: incompatible version.  A revision this consumer does not know fails closed."""
        original, digest = FIXTURES.originals["B-RFX-03"][:2]
        revised = dict(FIXTURES.fixture("B-RFX-03"))
        self.assertEqual(select_effective({"B-RFX-03": (original, digest)}, [revised])["B-RFX-03"],
                         revised)
        for bad in (
            {**revised, "fixture_revision": "0.3"},
            {**revised, "revises": {**revised["revises"], "predecessor_sha256": "0" * 64}},
            {**revised, "fixture_id": "B-RFX-09"},
        ):
            with self.subTest(bad=bad["fixture_id"] + "/" + str(bad["fixture_revision"])):
                with self.assertRaises(IncompatibleFixtureVersion):
                    select_effective({"B-RFX-03": (original, digest)}, [bad])

    def test_draft_every_example_is_mapped_or_explicitly_skipped(self):
        keys = FIXTURES.example_keys()
        self.assertTrue(MAPPED <= keys, MAPPED - keys)
        for fixture_id, example in sorted(keys - MAPPED):
            with self.subTest(fixture=fixture_id, example=example):
                self.skipTest(f"no HSB consumer for {fixture_id}/{example} in this slice")


class DraftHomeConsumerTests(unittest.TestCase):
    def test_draft_local_project_label_is_not_a_canonical_property(self):
        """B-RFX-01 "local project name is not canonical association"."""
        ex = FIXTURES.example("B-RFX-01", "local project name is not canonical association")
        self.assertIsNone(ex["canonical_property"])
        with self.assertRaises(ValueError):
            HomeAssetReference("H-A", "7", ex["canonical_property"])
        # A label used in place of the canonical property never resolves to it.
        canonical = home_ref("H-A@7")
        by_label = home_ref("H-A@7", ex["local_project_label"])
        with self.assertRaises(ReferenceMismatch):
            resolver(
                IdentityFact(IdentityFactStatus.CURRENT, ACTOR),
                HomeResourceFact(ResourceFactStatus.CURRENT, canonical),
                allow(ACTOR, by_label, ReferenceAction.READ_METADATA),
            ).resolve(by_label, ReferenceAction.READ_METADATA)

    def test_draft_foreign_revision_is_not_substituted(self):
        """B-RFX-03 "foreign revision" (negative: incompatible version)."""
        ex = FIXTURES.example("B-RFX-03", "foreign revision")
        expected, received = home_ref(ex["expected"]), home_ref(ex["received_component_context"])
        identity = IdentityFact(IdentityFactStatus.CURRENT, ACTOR)
        with self.assertRaises(ReferenceMismatch):
            resolver(identity, HomeResourceFact(ResourceFactStatus.CURRENT, received),
                     allow(ACTOR, expected, ReferenceAction.VIEW_REFERENCE),
                     ).resolve(expected, ReferenceAction.VIEW_REFERENCE)
        with self.assertRaises(StaleAuthorityFact):
            resolver(identity, HomeResourceFact(ResourceFactStatus.CURRENT, expected),
                     allow(ACTOR, received, ReferenceAction.VIEW_REFERENCE),
                     ).resolve(expected, ReferenceAction.VIEW_REFERENCE)
        resolved = resolver(identity, HomeResourceFact(ResourceFactStatus.CURRENT, expected),
                            allow(ACTOR, expected, ReferenceAction.VIEW_REFERENCE),
                            ).resolve(expected, ReferenceAction.VIEW_REFERENCE)
        self.assertEqual(resolved.reference.scene_revision, "7")

    def test_draft_incomplete_candidate_v2_leaves_accepted_v1_resolvable(self):
        """B-RFX-03 v0.2 "incomplete candidate V2 while accepted complete V1 remains unchanged"."""
        ex = FIXTURES.example(
            "B-RFX-03", "incomplete candidate V2 while accepted complete V1 remains unchanged")
        v1 = HomeAssetReference("H-A", ex["accepted_source"]["fixture_set"], PROPERTY)
        v2 = HomeAssetReference("H-A", ex["candidate"]["fixture_set"], PROPERTY)
        identity = IdentityFact(IdentityFactStatus.CURRENT, ACTOR)
        with self.assertRaises(ReferenceMismatch):
            resolver(identity, HomeResourceFact(ResourceFactStatus.CURRENT, v2),
                     allow(ACTOR, v1, ReferenceAction.READ_METADATA),
                     ).resolve(v1, ReferenceAction.READ_METADATA)
        resolved = resolver(identity, HomeResourceFact(ResourceFactStatus.CURRENT, v1),
                            allow(ACTOR, v1, ReferenceAction.READ_METADATA),
                            ).resolve(v1, ReferenceAction.READ_METADATA)
        self.assertEqual(resolved.reference, v1)

    def test_draft_old_scope_receipt_does_not_attach_to_new_workspace(self):
        """B-RFX-04 "old scope receipt"."""
        ex = FIXTURES.example("B-RFX-04", "old scope receipt")
        old_account, old_workspace = ex["old_scope"].split("/")
        new_account, new_workspace = ex["new_scope"].split("/")
        old_actor = ActorContext(old_account, APP, old_workspace)
        new_actor = ActorContext(new_account, APP, new_workspace)
        ref = home_ref("H-A@7")
        with self.assertRaises(StaleAuthorityFact):
            resolver(IdentityFact(IdentityFactStatus.CURRENT, new_actor),
                     HomeResourceFact(ResourceFactStatus.CURRENT, ref),
                     allow(old_actor, ref, ReferenceAction.READ_METADATA),
                     ).resolve(ref, ReferenceAction.READ_METADATA)

    def test_draft_cancellation_does_not_reuse_an_earlier_resolution(self):
        """B-RFX-04 "local versus remote cancellation" (negative: cancellation).

        After a local sign-out cancels the session, the next resolve fails
        before any resource/authority lookup, and the earlier result is not
        reused.  Remote termination is not modelled here and is not asserted.
        """
        ex = FIXTURES.example("B-RFX-04", "local versus remote cancellation")
        self.assertEqual(ex["remote_state"], "not supplied")
        ref = home_ref("H-A@7")
        facts = RecordingFacts(
            IdentityFact(IdentityFactStatus.CURRENT, ACTOR),
            HomeResourceFact(ResourceFactStatus.CURRENT, ref),
            allow(ACTOR, ref, ReferenceAction.VIEW_REFERENCE),
        )
        home = HomeReferenceResolver(facts, facts, facts)
        home.resolve(ref, ReferenceAction.VIEW_REFERENCE)
        self.assertEqual(facts.calls, ["identity", "resource", "authority"])
        facts.calls.clear()
        facts.identity = IdentityFact(IdentityFactStatus.SIGNED_OUT)
        with self.assertRaises(IdentityRequired):
            home.resolve(ref, ReferenceAction.VIEW_REFERENCE)
        self.assertEqual(facts.calls, ["identity"])
        # A withdrawn (cancelled) current grant is not revived by the prior ALLOW.
        facts.identity = IdentityFact(IdentityFactStatus.CURRENT, ACTOR)
        facts.authority = allow(ACTOR, ref, ReferenceAction.VIEW_REFERENCE, ActionDecision.DENY)
        with self.assertRaises(ActionDenied):
            home.resolve(ref, ReferenceAction.VIEW_REFERENCE)

    def test_draft_restored_metadata_after_withdrawal_stays_withdrawn(self):
        """B-RFX-06 "restored metadata after withdrawal"."""
        ex = FIXTURES.example("B-RFX-06", "restored metadata after withdrawal")
        self.assertTrue(ex["current_authority"].startswith("withdrawn"))
        ref = home_ref("H-A@7")
        restored_t1_allow = allow(ACTOR, ref, ReferenceAction.VIEW_REFERENCE)
        with self.assertRaises(ResourceWithdrawn):
            resolver(IdentityFact(IdentityFactStatus.CURRENT, ACTOR),
                     HomeResourceFact(ResourceFactStatus.WITHDRAWN, ref),
                     restored_t1_allow,
                     ).resolve(ref, ReferenceAction.VIEW_REFERENCE)

    def test_draft_wrong_resource_grant_is_denied_without_leaking_existence(self):
        """B-RFX-06 "wrong resource" (negative: wrong resource)."""
        ex = FIXTURES.example("B-RFX-06", "wrong resource")
        granted = home_ref(ex["grant_scope"].split()[0])
        requested = home_ref(ex["requested"].split()[0])
        self.assertEqual(ex["requested"].split()[1], "view")
        with self.assertRaises(StaleAuthorityFact) as caught:
            resolver(IdentityFact(IdentityFactStatus.CURRENT, ACTOR),
                     HomeResourceFact(ResourceFactStatus.CURRENT, requested),
                     allow(ACTOR, granted, ReferenceAction.VIEW_REFERENCE),
                     ).resolve(requested, ReferenceAction.VIEW_REFERENCE)
        self.assertEqual(caught.exception.code, "stale_authority_fact")
        self.assertNotIn(requested.scene_id, str(caught.exception))
        self.assertNotIn(granted.scene_id, str(caught.exception))

    def test_draft_second_account_cannot_use_capturing_account_authority(self):
        """B-RFX-07 "capturing phone offline versus second viewer" (negative: wrong account)."""
        ex = FIXTURES.example("B-RFX-07", "capturing phone offline versus second viewer")
        self.assertEqual(ex["capturing_phone_network"], "offline")
        ref = home_ref("H-A@7")
        second = ActorContext("ACCOUNT-B", APP)
        with self.assertRaises(WrongAccount):
            resolver(IdentityFact(IdentityFactStatus.WRONG_ACCOUNT),
                     HomeResourceFact(ResourceFactStatus.CURRENT, ref),
                     allow(ACTOR, ref, ReferenceAction.VIEW_REFERENCE),
                     ).resolve(ref, ReferenceAction.VIEW_REFERENCE)
        with self.assertRaises(StaleAuthorityFact):
            resolver(IdentityFact(IdentityFactStatus.CURRENT, second),
                     HomeResourceFact(ResourceFactStatus.CURRENT, ref),
                     allow(ACTOR, ref, ReferenceAction.VIEW_REFERENCE),
                     ).resolve(ref, ReferenceAction.VIEW_REFERENCE)


if __name__ == "__main__":
    unittest.main()
