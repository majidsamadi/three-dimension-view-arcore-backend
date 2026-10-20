"""HSB-04.1 and HSB-05.1-05.4: review inputs, review states, audience
projection, conflict-safe publish / replace and withdrawal.

HSB-04.2-04.4 (cloud jobs) are DISABLED by Q02.
Status: component-tested (synthetic data, in-memory fakes only).
"""
from __future__ import annotations

import unittest

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tests import scenario_wave2 as s
from tests.fakes_wave2 import Harness


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.ids = s.finalized_scene(self.h)
        self.scene_id = self.ids["scene_id"]

    def test_HSB_04_1_review_inputs_recorded(self):
        body = {"decision": "review_ready", "expected_version": 1,
                "review_inputs": {"quality_note": "synthetic sharp edges",
                                  "completeness_note": "one corner not observed",
                                  "dimension_evidence_note": None}}
        response = self.h.call("POST", f"/home-scenes/{self.scene_id}/versions/1/review", body)
        self.assertEqual((response.status, response.body), (200, {"version": "1", "review_state": "review_ready"}))
        history = self.h.repository.raw(f"SCENE#{self.scene_id}", "META").data["reviews"]["1"]["history"]
        self.assertEqual(history[0]["review_inputs"], body["review_inputs"])
        self.assertEqual((history[0]["by"], history[0]["decision"]), ("USER-A", "review_ready"))
        bad = self.h.call("POST", f"/home-scenes/{self.scene_id}/versions/1/review",
                          {**body, "expected_version": 2, "review_inputs": {"photo": "x"}})
        self.assertEqual(bad.status, 400)

    def test_HSB_04_jobs_route_absent_404(self):
        absent = s.API["absent_routes"][0]
        path = absent["path"].replace("{scene_id}", self.scene_id)
        for method in ("POST", "GET"):
            response = self.h.call(method, path, {"kind": "refine"} if method == "POST" else None)
            self.assertEqual((response.status, response.body["code"]),
                             (absent["expected_status"], "not_found"))

    def test_HSB_05_1_review_state_transitions(self):
        steps = [("rejected", 200, "rejected"), ("approved", 409, None),
                 ("review_ready", 200, "review_ready"), ("approved", 200, "approved"),
                 ("rejected", 409, None), ("review_ready", 409, None)]
        for decision, status, state in steps:
            with self.subTest(decision=decision):
                response = s.review(self.h, self.scene_id, "1", decision)
                self.assertEqual(response.status, status, response.body)
                if state:
                    self.assertEqual(response.body["review_state"], state)
                else:
                    self.assertEqual(response.body["code"], "invalid_state")
        stale = s.review(self.h, self.scene_id, "1", "approved", expected_version=1)
        self.assertEqual(stale.status, 409)
        grantee = Harness()
        ids = s.finalized_scene(grantee)
        s.grant(grantee, ids["scene_id"])
        denied = s.review(grantee, ids["scene_id"], "1", token="token-B")
        self.assertEqual((denied.status, denied.body["code"]), (403, "action_denied"))
        hidden = s.review(grantee, ids["scene_id"], "1", token="token-C")
        self.assertEqual((hidden.status, hidden.body["code"]), (404, "not_found"))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.ids = s.finalized_scene(self.h)
        self.scene_id = self.ids["scene_id"]

    def test_HSB_05_2_projection_requires_approved(self):
        path = f"/home-scenes/{self.scene_id}/versions/1/audience-projection"
        response = self.h.call("GET", path)
        self.assertEqual((response.status, response.body["code"]), (409, "invalid_state"))
        s.review(self.h, self.scene_id, "1", "review_ready")
        self.assertEqual(self.h.call("GET", path).status, 409)
        s.review(self.h, self.scene_id, "1", "approved")
        response = self.h.call("GET", path)
        self.assertEqual(response.status, 200, response.body)
        self.assertEqual(response.body["audience"], "explicit_grantees")
        s.grant(self.h, self.scene_id)
        grantee = self.h.call("GET", path, token="token-B")
        self.assertEqual((grantee.status, grantee.body["code"]), (403, "action_denied"))

    def test_HSB_05_3_unauthorized_publish_by_grantee_403(self):
        """Negative: a named grantee may view but never publish."""
        s.review(self.h, self.scene_id, "1")
        projection = s.projection_id(self.h, self.scene_id, "1")
        s.grant(self.h, self.scene_id)
        before = s.scene_record_version(self.h, self.scene_id)
        response = s.publish(self.h, self.scene_id, "1", projection=projection, token="token-B")
        self.assertEqual((response.status, response.body["code"]), (403, "action_denied"))
        stranger = s.publish(self.h, self.scene_id, "1", projection=projection, token="token-C")
        self.assertEqual((stranger.status, stranger.body["code"]), (404, "not_found"))
        self.assertEqual(s.scene_record_version(self.h, self.scene_id), before)
        scene = self.h.call("GET", f"/home-scenes/{self.scene_id}").body
        self.assertEqual(scene["publication"]["state"], "unpublished")

    def test_HSB_05_3_publish_requires_approved_and_matching_projection(self):
        unapproved = s.publish(self.h, self.scene_id, "1", projection="prj_01HZYSYNTH0000000000000001")
        self.assertEqual((unapproved.status, unapproved.body["code"]), (409, "invalid_state"))
        s.review(self.h, self.scene_id, "1")
        wrong = s.publish(self.h, self.scene_id, "1", projection="prj_01HZYSYNTH9999999999999999")
        self.assertEqual((wrong.status, wrong.body["code"]), (409, "invalid_state"))
        ok = s.publish(self.h, self.scene_id, "1")
        self.assertEqual(ok.status, 200, ok.body)
        self.assertEqual(ok.body, {"state": "published", "published_version": "1",
                                   "superseded_version": None, "record_version": 3})

    def test_HSB_05_3_stale_expected_version_conflict(self):
        s.review(self.h, self.scene_id, "1")
        response = s.publish(self.h, self.scene_id, "1", expected_version=1)
        self.assertEqual((response.status, response.body["code"], response.body["current_version"]),
                         (409, "version_conflict", 2))

    def test_HSB_05_3_concurrent_publish_one_wins(self):
        s.review(self.h, self.scene_id, "1")
        projection = s.projection_id(self.h, self.scene_id, "1")
        results = []

        def race(_writes):  # a competing publish lands between the read and the conditional write
            results.append(s.publish(self.h, self.scene_id, "1", projection=projection,
                                     expected_version=2))

        self.h.repository.before_transact = race
        loser = s.publish(self.h, self.scene_id, "1", projection=projection, expected_version=2)
        self.assertEqual(results[0].status, 200, results[0].body)
        self.assertEqual((loser.status, loser.body["code"], loser.body["current_version"]),
                         (409, "version_conflict", 3))
        self.assertEqual(s.scene_record_version(self.h, self.scene_id), 3)

    def test_HSB_05_4_replacement_supersedes_previous(self):
        s.review(self.h, self.scene_id, "1")
        s.publish(self.h, self.scene_id, "1")
        up = s.upload(self.h, self.ids["capture_id"], s.upload_body(asset_id=self.scene_id)).body
        s.put_components(self.h, up["upload_id"])
        self.assertEqual(s.finalize(self.h, up["upload_id"]).body["version"], "2")
        s.review(self.h, self.scene_id, "2")
        response = s.publish(self.h, self.scene_id, "2")
        self.assertEqual(response.status, 200, response.body)
        self.assertEqual((response.body["published_version"], response.body["superseded_version"]),
                         ("2", "1"))
        scene = self.h.call("GET", f"/home-scenes/{self.scene_id}").body
        self.assertEqual(scene["publication"], {"state": "published", "published_version": "2",
                                                "superseded_versions": ["1"]})
        s.grant(self.h, self.scene_id)
        old = self.h.call("GET", f"/home-scenes/{self.scene_id}/versions/1", token="token-B")
        self.assertEqual(old.status, 404)
        new = self.h.call("GET", f"/home-scenes/{self.scene_id}/versions/2", token="token-B")
        self.assertEqual(new.status, 200)

    def test_HSB_05_4_withdrawal_blocks_new_view_grants(self):
        s.review(self.h, self.scene_id, "1")
        s.publish(self.h, self.scene_id, "1")
        s.grant(self.h, self.scene_id)
        path = f"/home-scenes/{self.scene_id}/view-grants"
        self.assertEqual(self.h.call("POST", path, {}, token="token-B").status, 201)
        denied = self.h.call("POST", f"/home-scenes/{self.scene_id}/withdrawal",
                             {"expected_version": 3, "reason": "x"}, token="token-B")
        self.assertEqual(denied.status, 403)
        response = self.h.call("POST", f"/home-scenes/{self.scene_id}/withdrawal",
                               {"expected_version": 3, "reason": "synthetic withdrawal"})
        self.assertEqual(response.body, {"state": "withdrawn",
                                         "new_access_blocked_at": "2026-10-20T00:00:00Z",
                                         "outstanding_view_grants_expire_by": "2026-10-20T00:05:00Z"})
        for token in ("token-A", "token-B"):
            blocked = self.h.call("POST", path, {}, token=token)
            self.assertEqual((blocked.status, blocked.body["code"]), (410, "resource_withdrawn"))
        again = self.h.call("POST", f"/home-scenes/{self.scene_id}/withdrawal",
                            {"expected_version": 4, "reason": "again"})
        self.assertEqual((again.status, again.body["code"]), (409, "invalid_state"))
        republish = s.publish(self.h, self.scene_id, "1")
        self.assertEqual((republish.status, republish.body["code"]), (409, "invalid_state"))
        owner_view = self.h.call("GET", f"/home-scenes/{self.scene_id}")
        self.assertEqual(owner_view.body["publication"]["state"], "withdrawn")
        self.assertEqual(self.h.call("GET", f"/home-scenes/{self.scene_id}", token="token-B").status, 404)


if __name__ == "__main__":
    unittest.main()
