"""Synthetic end-to-end steps built from the v0.4 fixture request examples.

Each step drives the composed API (in-memory fakes only) exactly as the HSA
fake client would, so tests and the router contract replay share one path.
"""
from __future__ import annotations

import copy
from pathlib import Path

import tests  # noqa: F401  -- puts src/ on sys.path for plain `unittest discover -s tests`
from tests.fakes_wave2 import Harness
from tools.check_contract_fixtures_v0_4 import FIXTURE_DIR, load_fixture

ROOT = Path(__file__).resolve().parents[1]
API = load_fixture("api/home-scanner.v0.4.json")
EXAMPLES = load_fixture("assets/asset-envelope.v1.examples.json")
GLB = (ROOT / FIXTURE_DIR / "fixtures/assets/synthetic-unit-box.glb").read_bytes()
ROUTES = {r["id"]: r for r in API["routes"]}


def example_body(route_id: str) -> dict:
    return copy.deepcopy(ROUTES[route_id]["request_example"]["body"])


def capture(h: Harness, **overrides):
    body = {**example_body("H01"), **overrides}
    return h.call("POST", "/home-captures", body)


def upload_body(**envelope_overrides) -> dict:
    body = example_body("H02")
    body["envelope"].update(envelope_overrides)
    return body


def upload(h: Harness, capture_id: str, body: dict | None = None, token: str = "token-A"):
    return h.call("POST", f"/home-captures/{capture_id}/uploads", body or upload_body(), token=token)


def put_components(h: Harness, upload_id: str, data: bytes = GLB, component_ids=("main",)) -> None:
    for cid in component_ids:
        h.storage.client_upload(f"staging/{upload_id}/{cid}", data)


def finalize(h: Harness, upload_id: str, expected_version: int = 1, *, key: str = "auto",
             token: str = "token-A"):
    return h.call("POST", f"/uploads/{upload_id}/finalize", {"expected_version": expected_version},
                  key=key, token=token)


def finalized_scene(h: Harness) -> dict:
    cap = capture(h)
    assert cap.status == 201, cap.body
    up = upload(h, cap.body["capture_id"])
    assert up.status == 201, up.body
    put_components(h, up.body["upload_id"])
    fin = finalize(h, up.body["upload_id"])
    assert fin.status == 201, fin.body
    return {"capture_id": cap.body["capture_id"], "upload_id": up.body["upload_id"],
            "scene_id": fin.body["scene_id"], "version": fin.body["version"], "finalize": fin.body}


def scene_record_version(h: Harness, scene_id: str) -> int:
    return h.repository.raw(f"SCENE#{scene_id}", "META").version


def review(h: Harness, scene_id: str, version: str, decision: str = "approved",
           expected_version: int | None = None, token: str = "token-A"):
    body = example_body("H10")
    body["decision"] = decision
    body["expected_version"] = (scene_record_version(h, scene_id)
                                if expected_version is None else expected_version)
    return h.call("POST", f"/home-scenes/{scene_id}/versions/{version}/review", body, token=token)


def projection_id(h: Harness, scene_id: str, version: str) -> str:
    response = h.call("GET", f"/home-scenes/{scene_id}/versions/{version}/audience-projection")
    assert response.status == 200, response.body
    return response.body["projection_id"]


def publish(h: Harness, scene_id: str, version: str, *, expected_version: int | None = None,
            projection: str | None = None, token: str = "token-A", key: str = "auto"):
    body = {"version": version,
            "projection_id": projection or projection_id(h, scene_id, version),
            "expected_version": (scene_record_version(h, scene_id)
                                 if expected_version is None else expected_version)}
    return h.call("POST", f"/home-scenes/{scene_id}/publication", body, token=token, key=key)


def grant(h: Harness, scene_id: str, grantee: str = "USER-B",
          expires_at: str = "2026-11-19T00:00:00Z", token: str = "token-A"):
    return h.call("POST", f"/home-scenes/{scene_id}/grants",
                  {"grantee_user_id": grantee, "expires_at": expires_at}, token=token)


def published_scene(h: Harness, *, with_grant: bool = False) -> dict:
    ids = finalized_scene(h)
    response = review(h, ids["scene_id"], ids["version"])
    assert response.status == 200, response.body
    response = publish(h, ids["scene_id"], ids["version"])
    assert response.status == 200, response.body
    if with_grant:
        response = grant(h, ids["scene_id"])
        assert response.status == 201, response.body
        ids["grant_id"] = response.body["grant_id"]
    return ids
