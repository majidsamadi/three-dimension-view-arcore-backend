"""HSB-02.1-02.4: capture admission and the resumable upload state machine.

Status: component-tested (synthetic data, in-memory fakes only).
"""
from __future__ import annotations

import base64
import hashlib
import unittest

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tests import scenario_wave2 as s
from tests.fakes_wave2 import ChecksumRejected, FakePropertyReference, Harness


def _versions(h: Harness, scene_id: str) -> list:
    return [k for k in h.repository.keys() if k[0] == f"SCENE#{scene_id}" and k[1].startswith("VERSION#")]


class CaptureTests(unittest.TestCase):
    def test_HSB_02_1_capture_requires_current_property(self):
        h = Harness(properties=FakePropertyReference(unavailable=frozenset({"PROP-DOWN-1"})))
        ok = s.capture(h)
        self.assertEqual(ok.status, 201, ok.body)
        self.assertEqual(ok.body["property_type"], "VIRTUAL")
        self.assertEqual(ok.body["state"], "open")
        missing = s.capture(h, property_id="PROP-MISSING-1")
        self.assertEqual((missing.status, missing.body["code"]), (422, "property_not_usable"))
        down = s.capture(h, property_id="PROP-DOWN-1")
        self.assertEqual((down.status, down.body["code"]), (503, "dependency_unavailable"))
        self.assertEqual(h.properties.calls, ["PROP-VIRTUAL-1", "PROP-MISSING-1", "PROP-DOWN-1"])

    def test_HSB_02_1_real_property_requires_permission_record(self):
        h = Harness()
        refused = s.capture(h, property_id="PROP-REAL-UNLISTED-1", permission_record_id=None)
        self.assertEqual((refused.status, refused.body["code"]), (422, "property_not_usable"))
        ok = s.capture(h, property_id="PROP-REAL-UNLISTED-1", permission_record_id="PERM-SYNTHETIC-1",
                       content_class="permitted-unoccupied-reference")
        self.assertEqual(ok.status, 201, ok.body)
        self.assertEqual(ok.body["property_type"], "REAL")

    def test_HSB_02_1_occupied_content_refused(self):
        h = Harness()
        response = s.capture(h, content_class="occupied")
        self.assertEqual((response.status, response.body["code"]),
                         (422, "occupied_home_publication_disabled"))
        for bad in ({"capture_mode": "cloud"}, {"consent": {"upload_processed_representation": False}},
                    {"kind": "vehicle"}, {"surprise": 1}):
            with self.subTest(bad=bad):
                response = s.capture(h, **bad)
                self.assertEqual((response.status, response.body["code"]), (400, "invalid_request"))
        self.assertFalse([k for k in h.repository.keys() if k[0].startswith("CAPTURE#")])


class UploadAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.capture_id = s.capture(self.h).body["capture_id"]

    def _components(self, n: int, size: int = 812) -> list:
        return [{"bytes": size, "component_id": f"c{i}", "media_type": "model/gltf-binary",
                 "role": "geometry", "sha256": "ab" * 32} for i in range(n)]

    def test_HSB_02_2_admission_limits_10_components_200MiB(self):
        for components in (self._components(11), self._components(1, 209_715_201)):
            body = s.upload_body(components=components)
            body["components"] = components
            response = s.upload(self.h, self.capture_id, body)
            self.assertEqual((response.status, response.body["code"]), (413, "limit_exceeded"))
        ten = self._components(10, 209_715_200)
        body = s.upload_body(components=ten)
        body["components"] = ten
        response = s.upload(self.h, self.capture_id, body)
        self.assertEqual(response.status, 201, response.body)
        self.assertEqual(len(response.body["components"]), 10)

    def test_HSB_02_2_presigned_put_carries_checksum_and_length(self):
        response = s.upload(self.h, self.capture_id)
        self.assertEqual(response.status, 201, response.body)
        component = response.body["components"][0]
        expected_b64 = base64.b64encode(hashlib.sha256(s.GLB).digest()).decode()
        self.assertEqual(component["put_headers"], {"x-amz-checksum-sha256": expected_b64,
                                                    "content-length": "812"})
        self.assertEqual(component["url_expires_at"], "2026-10-20T00:15:00Z")
        self.assertEqual(response.body["expires_at"], "2026-10-27T00:00:00Z")
        upload_id = response.body["upload_id"]
        key = f"staging/{upload_id}/main"
        self.assertEqual(self.h.storage.presigned[key], (expected_b64, 812))
        with self.assertRaises(ChecksumRejected):  # storage refuses a different body
            self.h.storage.client_upload(key, s.GLB[:-1] + b"\x01")
        self.assertIsNone(self.h.storage.head(key))

    def test_HSB_02_2_raw_capture_role_rejected(self):
        raw = [{**s.example_body("H02")["components"][0], "role": "raw_capture"}]
        body = s.upload_body(components=raw)
        body["components"] = raw
        response = s.upload(self.h, self.capture_id, body)
        self.assertEqual((response.status, response.body["code"]), (422, "validation_failed"))
        self.assertEqual(response.body["reasons"], ["raw_capture_not_accepted"])

    def test_HSB_02_2_envelope_must_match_capture(self):
        cases = {"envelope_kind_mismatch": {"kind": "shop"},
                 "envelope_asset_mismatch": {"asset_id": "scn_01HZYSYNTH9999999999999999"}}
        for reason, override in cases.items():
            with self.subTest(reason=reason):
                response = s.upload(self.h, self.capture_id, s.upload_body(**override))
                self.assertEqual(response.status, 422, response.body)
                self.assertIn(reason, response.body["reasons"])


class UploadLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.capture_id = s.capture(self.h).body["capture_id"]
        self.upload = s.upload(self.h, self.capture_id).body
        self.upload_id = self.upload["upload_id"]

    def _get(self, token="token-A"):
        return self.h.call("GET", f"/uploads/{self.upload_id}", token=token)

    def test_HSB_02_3_lost_ack_reconciles_to_confirmed(self):
        self.assertEqual(self._get().body["components"][0]["state"], "pending")
        s.put_components(self.h, self.upload_id)  # the browser never reports success
        response = self._get()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["components"],
                         [{"component_id": "main", "state": "confirmed", "reason": None}])
        self.assertNotIn("put_url", response.body["components"][0])
        self.assertEqual(response.headers["ETag"], '"1"')

    def test_HSB_02_3_head_reports_size_and_digest_mismatch(self):
        key = f"staging/{self.upload_id}/main"
        self.h.storage.place(key, s.GLB[:-4], None)
        self.assertEqual(self._get().body["components"][0]["reason"], "size_mismatch")
        self.h.storage.place(key, s.GLB, "AAAA")
        self.assertEqual(self._get().body["components"][0]["reason"], "digest_mismatch")

    def test_HSB_02_3_reissue_only_for_unconfirmed(self):
        urls = self.h.call("POST", f"/uploads/{self.upload_id}/component-urls", {})
        self.assertEqual([c["component_id"] for c in urls.body["components"]], ["main"])
        s.put_components(self.h, self.upload_id)
        for body in ({}, {"component_ids": ["main"]}):
            urls = self.h.call("POST", f"/uploads/{self.upload_id}/component-urls", body)
            self.assertEqual((urls.status, urls.body), (200, {"components": []}))
        unknown = self.h.call("POST", f"/uploads/{self.upload_id}/component-urls",
                              {"component_ids": ["nope"]})
        self.assertEqual(unknown.status, 400)

    def test_HSB_02_3_cancel_is_idempotent(self):
        first = self.h.call("POST", f"/uploads/{self.upload_id}/cancel", {"expected_version": 1})
        self.assertEqual((first.status, first.body), (200, {"state": "cancelled"}))
        again = self.h.call("POST", f"/uploads/{self.upload_id}/cancel", {"expected_version": 1})
        self.assertEqual((again.status, again.body), (200, {"state": "cancelled"}))
        urls = self.h.call("POST", f"/uploads/{self.upload_id}/component-urls", {})
        self.assertEqual((urls.status, urls.body["code"]), (409, "invalid_state"))
        fin = s.finalize(self.h, self.upload_id, 2)
        self.assertEqual((fin.status, fin.body["code"]), (409, "invalid_state"))

    def test_HSB_02_3_cancel_stale_expected_version_conflict(self):
        response = self.h.call("POST", f"/uploads/{self.upload_id}/cancel", {"expected_version": 7})
        self.assertEqual((response.status, response.body["code"], response.body["current_version"]),
                         (409, "version_conflict", 1))

    def test_HSB_02_3_expired_upload_410(self):
        s.put_components(self.h, self.upload_id)
        self.h.clock.advance(7 * 24 * 3600)
        for response in (self._get(),
                         self.h.call("POST", f"/uploads/{self.upload_id}/component-urls", {}),
                         s.finalize(self.h, self.upload_id)):
            self.assertEqual((response.status, response.body["code"]), (410, "upload_expired"))

    def test_HSB_02_4_finalize_requires_all_components(self):
        response = s.finalize(self.h, self.upload_id)
        self.assertEqual((response.status, response.body["code"]), (409, "upload_incomplete"))
        self.assertEqual(response.body["components"],
                         [{"component_id": "main", "state": "pending", "reason": None}])
        self.assertFalse([k for k in self.h.repository.keys() if k[0].startswith("SCENE#")])

    def test_HSB_02_4_repeated_finalize_same_key_replays_same_version(self):
        """Negative: repeated finalize with the same Idempotency-Key replays, never re-runs."""
        s.put_components(self.h, self.upload_id)
        first = s.finalize(self.h, self.upload_id, key="idem-finalize-0001")
        again = s.finalize(self.h, self.upload_id, key="idem-finalize-0001")
        self.assertEqual(first.status, 201)
        self.assertEqual((again.status, again.body), (first.status, first.body))
        self.assertEqual(len(_versions(self.h, first.body["scene_id"])), 1)
        reuse = self.h.call("POST", f"/uploads/{self.upload_id}/finalize", {"expected_version": 2},
                            key="idem-finalize-0001")
        self.assertEqual((reuse.status, reuse.body["code"]), (409, "idempotency_key_reuse"))

    def test_HSB_02_4_repeated_finalize_new_key_already_finalized_no_second_version(self):
        """Negative: a new key after success gets already_finalized and no second version."""
        s.put_components(self.h, self.upload_id)
        first = s.finalize(self.h, self.upload_id)
        second = s.finalize(self.h, self.upload_id, 2)
        self.assertEqual((second.status, second.body["code"]), (409, "already_finalized"))
        self.assertEqual((second.body["scene_id"], second.body["version"]),
                         (first.body["scene_id"], first.body["version"]))
        self.assertEqual(len(_versions(self.h, first.body["scene_id"])), 1)

    def test_HSB_02_4_tampered_digest_rejected_no_version_created(self):
        """Negative: bytes changed behind the stored checksum are caught by the full read."""
        s.put_components(self.h, self.upload_id)
        key = f"staging/{self.upload_id}/main"
        self.h.storage.tamper(key, s.GLB[:-1] + b"\x01")
        self.assertEqual(self._get().body["components"][0]["state"], "confirmed")  # HEAD cannot tell
        response = s.finalize(self.h, self.upload_id)
        self.assertEqual((response.status, response.body["code"]), (422, "component_digest_mismatch"))
        self.assertEqual(response.body["components"],
                         [{"component_id": "main", "state": "failed", "reason": "digest_mismatch"}])
        self.assertFalse([k for k in self.h.repository.keys() if k[0].startswith("SCENE#")])
        self.assertFalse([k for k in self.h.storage.objects if k.startswith("versions/")])
        self.assertEqual(self._get().body["components"][0]["reason"], "digest_mismatch")
        # Recovery: reissue the failed component, upload the right bytes, finalize.
        urls = self.h.call("POST", f"/uploads/{self.upload_id}/component-urls", {})
        self.assertEqual([c["component_id"] for c in urls.body["components"]], ["main"])
        s.put_components(self.h, self.upload_id)
        ok = s.finalize(self.h, self.upload_id, 3)
        self.assertEqual((ok.status, ok.body["state"]), (201, "validated"), ok.body)

    def test_HSB_02_4_size_mismatch_rejected(self):
        self.h.storage.place(f"staging/{self.upload_id}/main", s.GLB + b"\x00\x00\x00\x00", None)
        response = s.finalize(self.h, self.upload_id)
        self.assertEqual((response.status, response.body["code"]), (422, "component_size_mismatch"))
        self.assertEqual(response.body["components"][0]["reason"], "size_mismatch")
        self.assertFalse([k for k in self.h.repository.keys() if k[0].startswith("SCENE#")])

    def test_HSB_02_wrong_account_cannot_read_or_resume_upload_404(self):
        """Negative: another account sees 404 for every upload route; nothing changes."""
        s.put_components(self.h, self.upload_id)
        calls = (
            ("GET", f"/uploads/{self.upload_id}", None),
            ("POST", f"/uploads/{self.upload_id}/component-urls", {}),
            ("POST", f"/uploads/{self.upload_id}/cancel", {"expected_version": 1}),
            ("POST", f"/uploads/{self.upload_id}/finalize", {"expected_version": 1}),
            ("POST", f"/home-captures/{self.capture_id}/uploads", s.upload_body()),
        )
        for method, path, body in calls:
            with self.subTest(path=path):
                response = self.h.call(method, path, body, token="token-B")
                self.assertEqual((response.status, response.body["code"]), (404, "not_found"))
        self.assertEqual(self._get().body["state"], "open")

    def test_HSB_02_storage_outage_is_503(self):
        s.put_components(self.h, self.upload_id)
        self.h.storage.fail_next("head")
        response = self._get()
        self.assertEqual((response.status, response.body["code"]), (503, "dependency_unavailable"))
        self.h.repository.fail_next()
        response = self._get()
        self.assertEqual((response.status, response.body["code"]), (503, "dependency_unavailable"))


if __name__ == "__main__":
    unittest.main()
