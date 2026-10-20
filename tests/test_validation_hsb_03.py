"""HSB-03.1-03.4: envelope and GLB validation, private vs viewable material,
immutable content-addressed versions and capability metadata.

Status: component-tested (synthetic data, in-memory fakes only).
"""
from __future__ import annotations

import copy
import hashlib
import json
import struct
import unittest

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tests import scenario_wave2 as s
from tests.fakes_wave2 import Harness
from tools.check_contract_fixtures_v0_4 import load_fixture
from wisestay_home_backend.domain import policy
from wisestay_home_backend.domain.envelope import (
    capabilities,
    validate_envelope,
    validate_glb_structure,
)
from wisestay_home_backend.ports.repository import ConditionFailed, Item, Put

BOX_BOUNDS = {"min": [-0.5, 0.0, -0.5], "max": [0.5, 1.0, 0.5]}
GLB_REASON_CODES = load_fixture("assets/asset-envelope.v1.schema.json")[
    "x-wisestay-admission"]["glb_reason_codes"]


def _split(glb: bytes) -> tuple[dict, bytes]:
    json_len = struct.unpack_from("<I", glb, 12)[0]
    return json.loads(glb[20:20 + json_len]), glb[20 + json_len:]


def _build(gltf: dict, rest: bytes, *, magic: int = 0x46546C67, version: int = 2,
           chunk_type: int = 0x4E4F534A, declared_delta: int = 0, chunk_len: int | None = None) -> bytes:
    raw = json.dumps(gltf, separators=(",", ":")).encode()
    raw += b" " * (-len(raw) % 4)
    total = 20 + len(raw) + len(rest)
    return (struct.pack("<III", magic, version, total + declared_delta)
            + struct.pack("<II", len(raw) if chunk_len is None else chunk_len, chunk_type) + raw + rest)


def _variant(code: str) -> bytes:
    """Derive a GLB from the fixture box that fails exactly one X.2.1 check."""
    gltf, rest = _split(s.GLB)
    g = copy.deepcopy(gltf)
    if code == "glb_bad_magic":
        return _build(g, rest, magic=0x12345678)
    if code == "glb_bad_version":
        return _build(g, rest, version=1)
    if code == "glb_length_mismatch":
        return _build(g, rest, declared_delta=4)
    if code == "glb_first_chunk_not_json":
        return _build(g, rest, chunk_type=0x004E4942)
    if code == "glb_json_too_large":
        return _build(g, rest, chunk_len=policy.GLB_JSON_CHUNK_BYTES + 4)
    if code == "gltf_bad_asset_version":
        g["asset"]["version"] = "1.0"
    elif code == "gltf_extension_required":
        g["extensionsRequired"] = ["KHR_draco_mesh_compression"]
    elif code == "gltf_external_uri":
        g["buffers"][0]["uri"] = "data:application/octet-stream;base64,AAAA"
    elif code == "gltf_count_limit":
        g["nodes"] = g["nodes"] * (policy.GLB_NODES + 1)
    elif code == "gltf_vertex_limit":
        g["accessors"][0]["count"] = policy.GLB_POSITION_VERTICES_TOTAL + 1
    elif code == "gltf_position_bounds_missing":
        del g["accessors"][0]["min"]
    elif code == "bounds_outside_envelope":
        g["accessors"][0]["max"] = [0.6, 1.0, 0.5]
    else:
        raise AssertionError(f"no variant for {code}")
    return _build(g, rest)


def _validate(data: bytes, bounds=BOX_BOUNDS, kind="home") -> list[str]:
    return validate_glb_structure(lambda a, b: data[a:b + 1], len(data),
                                  envelope_bounds=bounds, kind=kind)


class GlbValidationTests(unittest.TestCase):
    def test_HSB_03_1_valid_box_validates(self):
        self.assertEqual(_validate(s.GLB), [])
        facts = load_fixture("assets/synthetic-unit-box.facts.json")
        self.assertEqual(hashlib.sha256(s.GLB).hexdigest(), facts["sha256"])
        h = Harness()
        ids = s.finalized_scene(h)
        self.assertEqual(ids["finalize"]["state"], "validated")
        self.assertEqual(ids["finalize"]["validation"], {"reasons": []})

    def test_HSB_03_1_each_glb_reason_code_quarantines(self):
        self.assertEqual(len(GLB_REASON_CODES), 12)
        for code in GLB_REASON_CODES:
            with self.subTest(code=code):
                data = _variant(code)
                self.assertEqual(_validate(data), [code])
                h = Harness()
                capture_id = s.capture(h).body["capture_id"]
                body = s.upload_body()
                component = {**body["components"][0], "bytes": len(data),
                             "sha256": hashlib.sha256(data).hexdigest()}
                body["components"] = [component]
                body["envelope"]["components"] = [dict(component)]
                up = s.upload(h, capture_id, body)
                self.assertEqual(up.status, 201, up.body)
                s.put_components(h, up.body["upload_id"], data)
                fin = s.finalize(h, up.body["upload_id"])
                self.assertEqual(fin.status, 201, fin.body)
                self.assertEqual(fin.body["state"], "quarantined")
                self.assertEqual(fin.body["validation"]["reasons"], [code])
                # Quarantined bytes go to rejected/, never to the versions/ namespace.
                self.assertIn(f"rejected/{up.body['upload_id']}/main", h.storage.objects)
                self.assertFalse([k for k in h.storage.objects if k.startswith("versions/")])
                review = s.review(h, fin.body["scene_id"], "1")
                self.assertEqual((review.status, review.body["code"]), (409, "invalid_state"))

    def test_HSB_03_1_envelope_examples_from_v0_4(self):
        examples = load_fixture("assets/asset-envelope.v1.examples.json")
        for case in examples["valid"]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(validate_envelope(case["envelope"]), [])
        self.assertGreaterEqual(len(examples["invalid"]), 10)
        for case in examples["invalid"]:
            with self.subTest(case=case["case_id"]):
                envelope_reasons = validate_envelope(case["envelope"])
                if case["case_id"].startswith("INV-13"):
                    self.assertEqual(envelope_reasons, [])
                    self.assertEqual(_validate(s.GLB, case["envelope"]["bounds_m"]),
                                     case["expected_reasons"])
                else:
                    self.assertEqual(envelope_reasons, case["expected_reasons"])

    def test_HSB_03_1_envelope_size_limit(self):
        envelope = copy.deepcopy(s.EXAMPLES["valid"][0]["envelope"])
        envelope["unobserved_regions"] = [
            {"region_id": f"r{i}", "bounds_m": BOX_BOUNDS, "label": "Not observed " * 4}
            for i in range(800)]
        self.assertIn("envelope_too_large", validate_envelope(envelope))

    def test_HSB_03_2_projection_excludes_private_roles(self):
        h = Harness()
        capture_id = s.capture(h).body["capture_id"]
        body = s.upload_body()
        geometry = body["components"][0]
        diagnostics = {**geometry, "component_id": "diag", "role": "diagnostics"}
        review_model = {**geometry, "component_id": "review", "role": "review_model"}
        body["components"] = [geometry, diagnostics, review_model]
        body["envelope"]["components"] = [dict(c) for c in body["components"]]
        up = s.upload(h, capture_id, body).body
        s.put_components(h, up["upload_id"], component_ids=("main", "diag", "review"))
        fin = s.finalize(h, up["upload_id"]).body
        scene_id = fin["scene_id"]
        s.review(h, scene_id, "1")
        projection = h.call("GET", f"/home-scenes/{scene_id}/versions/1/audience-projection").body
        self.assertEqual(projection["components"], ["main"])
        self.assertEqual(projection["excluded_categories"],
                         ["raw_capture", "diagnostics", "review_model", "source_photos", "notes"])
        stored = h.storage.objects[f"versions/envelopes/{scene_id}/1.json"][0]
        self.assertEqual(hashlib.sha256(stored).hexdigest(), projection["envelope_sha256"])
        envelope = json.loads(stored)
        self.assertEqual([c["component_id"] for c in envelope["components"]], ["main"])
        self.assertEqual(envelope["audience_projection_id"], projection["projection_id"])
        version = h.call("GET", f"/home-scenes/{scene_id}/versions/1").body
        self.assertEqual([c["role"] for c in version["envelope"]["components"]], ["geometry"])

    def test_HSB_03_3_versions_immutable_and_content_addressed(self):
        h = Harness()
        ids = s.published_scene(h)
        scene_id = ids["scene_id"]
        digest = hashlib.sha256(s.GLB).hexdigest()
        self.assertEqual(h.storage.objects[f"versions/{digest}"][0], s.GLB)
        item = h.repository.raw(f"SCENE#{scene_id}", "VERSION#000001")
        self.assertEqual(item.version, 1)  # review and publish never rewrote the version item
        self.assertEqual(item.data["envelope_sha256"], ids["finalize"]["envelope_sha256"])
        self.assertEqual(item.data["components"][0]["key"], f"versions/{digest}")
        with self.assertRaises(ConditionFailed):
            h.repository.transact([Put(Item(item.pk, item.sk, 1, {"tampered": True}), "absent")])
        self.assertFalse([k for k in h.storage.objects if k.startswith("staging/")])

    def test_HSB_03_3_second_upload_creates_next_version(self):
        h = Harness()
        ids = s.finalized_scene(h)
        up = s.upload(h, ids["capture_id"], s.upload_body(asset_id=ids["scene_id"])).body
        s.put_components(h, up["upload_id"])
        fin = s.finalize(h, up["upload_id"]).body
        self.assertEqual((fin["scene_id"], fin["version"]), (ids["scene_id"], "2"))
        scene = h.call("GET", f"/home-scenes/{ids['scene_id']}").body
        self.assertEqual([v["version"] for v in scene["versions"]], ["1", "2"])

    def test_HSB_03_4_capabilities_follow_scale_claim(self):
        envelope = s.EXAMPLES["valid"][0]["envelope"]
        expected = {
            "unknown": (False, False), "estimated": (False, True), "seller-declared": (False, True),
            "reference-supported": (True, True), "independently-verified": (True, True),
        }
        for claim, (measurement, placement) in expected.items():
            with self.subTest(claim=claim):
                caps = capabilities({**envelope, "scale_claim": claim}, validated=True)
                self.assertEqual((caps["measurement"], caps["placement"]), (measurement, placement))
                self.assertTrue(caps["visual_tour"])
                self.assertEqual(caps["missing_regions"], envelope["unobserved_regions"])
        self.assertFalse(capabilities(envelope, validated=False)["visual_tour"])
        h = Harness()
        ids = s.finalized_scene(h)
        version = h.call("GET", f"/home-scenes/{ids['scene_id']}").body["versions"][0]
        self.assertEqual(version["capabilities"]["measurement"], True)
        self.assertEqual(version["missing_regions"], envelope["unobserved_regions"])

    def test_HSB_03_policy_limits_match_v0_4_fixture(self):
        limits = {k: v["value"] for k, v in load_fixture("common/policy-limits.v0.4.json")["limits"].items()}
        pinned = {
            "components_per_upload": policy.COMPONENTS_PER_UPLOAD,
            "bytes_per_component": policy.BYTES_PER_COMPONENT,
            "envelope_json_bytes": policy.ENVELOPE_JSON_BYTES,
            "glb_json_chunk_bytes": policy.GLB_JSON_CHUNK_BYTES,
            "glb_nodes": policy.GLB_NODES, "glb_meshes": policy.GLB_MESHES,
            "glb_accessors": policy.GLB_ACCESSORS,
            "glb_position_vertices_total": policy.GLB_POSITION_VERTICES_TOTAL,
            "bounds_extent_home_m": policy.BOUNDS_EXTENT_M["home"],
            "bounds_extent_shop_m": policy.BOUNDS_EXTENT_M["shop"],
            "bounds_extent_object_m": policy.BOUNDS_EXTENT_M["object"],
            "presigned_put_lifetime_s": policy.PRESIGNED_PUT_LIFETIME_S,
            "presigned_get_lifetime_s": policy.PRESIGNED_GET_LIFETIME_S,
            "view_grant_lifetime_s": policy.VIEW_GRANT_LIFETIME_S,
            "upload_session_expiry_s": policy.UPLOAD_SESSION_EXPIRY_S,
            "audience_grant_max_lifetime_s": policy.AUDIENCE_GRANT_MAX_LIFETIME_S,
        }
        for name, value in pinned.items():
            with self.subTest(limit=name):
                self.assertEqual(limits[name], value)


if __name__ == "__main__":
    unittest.main()
