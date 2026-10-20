"""HSB-06.1, 06.2, 06.4 grants and view grants; Q10 CommercialGate.

HSB-06.3 (opening on a second device) is covered here only through a second
synthetic account against the fakes; no device or browser is exercised.
Status: component-tested (synthetic data, in-memory fakes only).
"""
from __future__ import annotations

import json
import unittest
from urllib.parse import parse_qs, urlparse

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tests import scenario_wave2 as s
from tests.fakes_wave2 import Harness
from wisestay_home_backend.domain.asset_reference import ActorContext
from wisestay_home_backend.ports.commercial_gate import ConfigurationError, NotConfiguredCommercialGate


class ViewingTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.ids = s.published_scene(self.h, with_grant=True)
        self.scene_id = self.ids["scene_id"]
        self.path = f"/home-scenes/{self.scene_id}/view-grants"

    def test_HSB_06_1_owner_grants_named_viewer(self):
        h = Harness()
        ids = s.published_scene(h)
        before = h.call("GET", f"/home-scenes/{ids['scene_id']}", token="token-B")
        self.assertEqual(before.status, 404)
        response = s.grant(h, ids["scene_id"])
        self.assertEqual(response.status, 201, response.body)
        self.assertEqual(response.body, {"grant_id": "grt_01HZYSYNTH0000000000000001",
                                         "grantee_user_id": "USER-B",
                                         "expires_at": "2026-11-19T00:00:00Z", "state": "active"})
        after = h.call("GET", f"/home-scenes/{ids['scene_id']}", token="token-B")
        self.assertEqual((after.status, after.body["role"]), (200, "grantee"))
        listed = h.call("GET", "/home-scenes", token="token-B").body["items"]
        self.assertEqual([i["scene_id"] for i in listed], [ids["scene_id"]])
        self.assertEqual(h.call("GET", "/home-scenes", token="token-C").body,
                         {"items": [], "next_cursor": None})
        too_long = s.grant(h, ids["scene_id"], expires_at="2027-01-19T00:00:01Z")
        self.assertEqual((too_long.status, too_long.body["code"]), (422, "validation_failed"))
        by_grantee = s.grant(h, ids["scene_id"], grantee="USER-C", token="token-B")
        self.assertEqual((by_grantee.status, by_grantee.body["code"]), (403, "action_denied"))

    def test_HSB_06_2_view_grant_urls_projection_only_300s(self):
        response = self.h.call("POST", self.path, {"version": "1"}, token="token-B")
        self.assertEqual(response.status, 201, response.body)
        body = response.body
        self.assertEqual(body["commercial_outcome"], "allowed_no_commercial_policy")
        self.assertEqual(body["expires_at"], "2026-10-20T00:05:00Z")
        urls = [body["envelope_url"]] + [c["get_url"] for c in body["components"]]
        now = int(self.h.clock().timestamp())
        for url in urls:
            self.assertEqual(int(parse_qs(urlparse(url).query)["exp"][0]) - now, 300)
            key = urlparse(url).path.lstrip("/")
            self.assertTrue(key.startswith("versions/"), key)
            self.assertFalse(key.startswith(("staging/", "rejected/")))
        self.assertEqual([c["component_id"] for c in body["components"]], ["main"])
        defaulted = self.h.call("POST", self.path, {}, token="token-B")
        self.assertEqual((defaulted.status, defaulted.body["version"]), (201, "1"))

    def test_HSB_06_4_expired_grant_403_grant_expired(self):
        """Negative: an expired audience grant cannot open the scene."""
        self.h.clock.advance(31 * 24 * 3600)
        response = self.h.call("POST", self.path, {}, token="token-B")
        self.assertEqual((response.status, response.body["code"]), (403, "grant_expired"))
        self.assertEqual(self.h.call("GET", f"/home-scenes/{self.scene_id}", token="token-B").status, 404)

    def test_HSB_06_4_revoked_grant_403(self):
        grant_path = f"/home-scenes/{self.scene_id}/grants/{self.ids['grant_id']}"
        stale = self.h.call("DELETE", grant_path, query={"expected_version": 5})
        self.assertEqual((stale.status, stale.body["code"]), (409, "version_conflict"))
        by_grantee = self.h.call("DELETE", grant_path, token="token-B", query={"expected_version": 1})
        self.assertEqual(by_grantee.status, 403)
        revoked = self.h.call("DELETE", grant_path, query={"expected_version": 1})
        self.assertEqual((revoked.status, revoked.body), (200, {"grant_id": self.ids["grant_id"],
                                                                "state": "revoked"}))
        response = self.h.call("POST", self.path, {}, token="token-B")
        self.assertEqual((response.status, response.body["code"]), (403, "grant_revoked"))
        missing = self.h.call("DELETE", f"/home-scenes/{self.scene_id}/grants/grt_01HZYSYNTH9999999999999999",
                              query={"expected_version": 1})
        self.assertEqual(missing.status, 404)

    def test_HSB_06_4_withdrawn_scene_410(self):
        """Negative: a withdrawn scene issues no view grant and its version reads 410."""
        self.h.call("POST", f"/home-scenes/{self.scene_id}/withdrawal",
                    {"expected_version": 3, "reason": "synthetic withdrawal"})
        response = self.h.call("POST", self.path, {}, token="token-B")
        self.assertEqual((response.status, response.body["code"]), (410, "resource_withdrawn"))
        version = self.h.call("GET", f"/home-scenes/{self.scene_id}/versions/1", token="token-B")
        self.assertEqual((version.status, version.body["code"]), (410, "resource_withdrawn"))
        grant = s.grant(self.h, self.scene_id, grantee="USER-C")
        self.assertEqual((grant.status, grant.body["code"]), (410, "resource_withdrawn"))

    def test_HSB_06_4_wrong_account_view_grant_404(self):
        """Negative: an account with no grant learns nothing about the scene."""
        for method, path, body in (("POST", self.path, {}),
                                   ("GET", f"/home-scenes/{self.scene_id}", None),
                                   ("GET", f"/home-scenes/{self.scene_id}/versions/1", None),
                                   ("POST", "/home-scenes/scn_01HZYSYNTH9999999999999999/view-grants", {})):
            with self.subTest(path=path, method=method):
                response = self.h.call(method, path, body, token="token-C")
                self.assertEqual((response.status, response.body["code"]), (404, "not_found"))

    def test_HSB_06_4_cached_view_grant_id_never_renews(self):
        first = self.h.call("POST", self.path, {}, token="token-B", key="idem-view-0001")
        self.h.clock.advance(301)
        replay = self.h.call("POST", self.path, {}, token="token-B", key="idem-view-0001")
        self.assertEqual(replay.body, first.body)  # same id, same (now expired) URLs
        self.assertEqual(replay.body["expires_at"], "2026-10-20T00:05:00Z")
        fresh = self.h.call("POST", self.path, {}, token="token-B", key="idem-view-0002")
        self.assertNotEqual(fresh.body["view_grant_id"], first.body["view_grant_id"])
        self.assertEqual(fresh.body["expires_at"], "2026-10-20T00:10:01Z")
        stored = self.h.repository.raw(f"SCENE#{self.scene_id}", f"VIEWGRANT#{first.body['view_grant_id']}")
        self.assertEqual((stored.version, stored.data["expires_at"]), (1, "2026-10-20T00:05:00Z"))

    def test_HSB_06_grantee_needs_published_version(self):
        h = Harness()
        ids = s.finalized_scene(h)
        s.review(h, ids["scene_id"], "1")
        s.grant(h, ids["scene_id"])
        path = f"/home-scenes/{ids['scene_id']}/view-grants"
        grantee = h.call("POST", path, {}, token="token-B")
        self.assertEqual((grantee.status, grantee.body["code"]), (409, "invalid_state"))
        owner = h.call("POST", path, {"version": "1"})
        self.assertEqual(owner.status, 201, owner.body)

    def test_Q10_commercial_gate_view_allowed_no_commercial_policy_logged(self):
        with self.assertLogs("wisestay_home_backend.commercial_gate", level="INFO") as logs:
            response = self.h.call("POST", self.path, {}, token="token-B")
        self.assertEqual(response.status, 201)
        event = json.loads(logs.records[0].getMessage())
        self.assertEqual(event, {"event": "commercial_gate", "action": "view",
                                 "outcome": "allowed_no_commercial_policy", "reason": None,
                                 "resource_ref": f"home-scene:{self.scene_id}:1"})
        self.assertNotIn("token", logs.output[0])
        gate = NotConfiguredCommercialGate("dev")
        actor = ActorContext("USER-A", "home-scanner")
        self.assertEqual(gate.check("place", actor, "r").outcome, "allowed_no_commercial_policy")
        export = gate.check("export", actor, "r")
        self.assertEqual((export.outcome, export.reason), ("denied", "export_not_available"))

    def test_Q10_gate_refuses_production_environment(self):
        with self.assertRaises(ConfigurationError):
            NotConfiguredCommercialGate("production")
        with self.assertRaises(ConfigurationError):
            Harness(environment="production")


if __name__ == "__main__":
    unittest.main()
