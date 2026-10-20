"""H10 review, H12 publish / replace and H13 withdraw (HSB-04.1, HSB-05.1-05.4).

All scene mutations are conflict-safe: the client sends the scene
``record_version`` as ``expected_version`` and the repository write is
conditional on it, so of two concurrent publishes exactly one wins and the
other gets 409 ``version_conflict``.  Only the owner (the capturing account,
Q07) may review, publish or withdraw; a grantee gets 403 ``action_denied`` and
anyone else 404.

Approval creates the audience projection: the geometry-only envelope written
to ``versions/envelopes/<scene>/<version>.json``.  Cloud review jobs
(HSB-04.2-04.4) are DISABLED by Q02; review inputs are recorded only.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import hashlib

from wisestay_home_backend.application.common import (
    ServiceDeps,
    check_expected_version,
    iso,
    load_version,
    not_found,
    owned_scene,
    projection_sk,
    require_fields,
    scene_key,
)
from wisestay_home_backend.application.scene_query_service import projection_envelope
from wisestay_home_backend.domain import policy
from wisestay_home_backend.domain.envelope import canonical_json
from wisestay_home_backend.domain.scene import (
    REVIEW_TRANSITIONS,
    ApiError,
    AudienceProjection,
    Publication,
    PublicationState,
    ReviewState,
    Scene,
    VersionReview,
    VersionState,
)
from wisestay_home_backend.ports.identity import VerifiedIdentity
from wisestay_home_backend.ports.object_storage import envelope_key
from wisestay_home_backend.ports.repository import ConditionFailed, Item, Put

REVIEW_INPUT_FIELDS = frozenset({"quality_note", "completeness_note", "dimension_evidence_note"})
MAX_NOTE_CHARS = 2000


class PublicationService:
    def __init__(self, deps: ServiceDeps) -> None:
        self._deps = deps

    def _write_scene(self, scene: Scene, item: Item, extra: list | None = None) -> int:
        pk, sk = scene_key(scene.scene_id)
        writes = [Put(Item(pk, sk, item.version + 1, scene.to_data(), gsi1pk=item.gsi1pk,
                           gsi1sk=item.gsi1sk), "version", item.version)]
        try:
            self._deps.repository.transact(writes + (extra or []))
        except ConditionFailed as exc:
            current = self._deps.repository.get(pk, sk)
            raise ApiError("version_conflict",
                           current_version=current.version if current else item.version) from exc
        return item.version + 1

    # --- H10 ---------------------------------------------------------------------------

    def review(self, identity: VerifiedIdentity, scene_id: str, version: str, body) -> dict:
        scene, item = owned_scene(self._deps, identity.user_id, scene_id)
        body = require_fields(body, required={"decision", "expected_version"},
                              optional={"review_inputs"})
        try:
            decision = ReviewState(body["decision"])
        except ValueError as exc:
            raise ApiError("invalid_request", "decision is invalid") from exc
        if decision is ReviewState.DRAFT:
            raise ApiError("invalid_request", "decision is invalid")
        inputs = body.get("review_inputs") or {}
        if not isinstance(inputs, dict) or set(inputs) - REVIEW_INPUT_FIELDS or any(
                v is not None and (not isinstance(v, str) or len(v) > MAX_NOTE_CHARS)
                for v in inputs.values()):
            raise ApiError("invalid_request", "review_inputs is invalid")
        stored = load_version(self._deps.repository, scene_id, version)
        if stored is None:
            raise not_found()
        if stored.state is VersionState.QUARANTINED or scene.withdrawn:
            raise ApiError("invalid_state")
        current = scene.review(version)
        if decision not in REVIEW_TRANSITIONS[current.review_state]:
            raise ApiError("invalid_state")
        check_expected_version(body, item.version)

        now = iso(self._deps.clock())
        entry = {"decision": decision.value, "by": identity.user_id, "at": now,
                 "review_inputs": {k: inputs.get(k) for k in sorted(REVIEW_INPUT_FIELDS)}}
        projection_id = current.projection_id
        extra = []
        if decision is ReviewState.APPROVED:
            projection_id = self._deps.ids.new("prj")
            envelope = projection_envelope(stored.envelope, projection_id)
            raw = canonical_json(envelope)
            key = envelope_key(scene_id, version)
            # Written before the conditional scene write; a lost race leaves only
            # an unreferenced envelope object behind.
            self._deps.storage.put_bytes(key, raw, content_type="application/json")
            components = tuple(c["component_id"] for c in envelope["components"])
            digests = {c["component_id"]: c["sha256"] for c in envelope["components"]}
            projection = AudienceProjection(projection_id, scene_id, version, components, digests,
                                            hashlib.sha256(raw).hexdigest(), key, now)
            extra.append(Put(Item(f"SCENE#{scene_id}", projection_sk(projection_id), 1,
                                  projection.to_data()), "absent"))
        reviews = {**scene.reviews, version: VersionReview(decision, projection_id,
                                                           current.history + (entry,))}
        self._write_scene(replace(scene, reviews=reviews), item, extra)
        return {"version": version, "review_state": decision.value}

    # --- H12 ---------------------------------------------------------------------------

    def publish(self, identity: VerifiedIdentity, scene_id: str, body) -> dict:
        scene, item = owned_scene(self._deps, identity.user_id, scene_id)
        body = require_fields(body, required={"version", "projection_id", "expected_version"})
        if scene.content_class == "occupied":
            raise ApiError("occupied_home_publication_disabled")
        version = body["version"]
        if not isinstance(version, str) or load_version(self._deps.repository, scene_id, version) is None:
            raise ApiError("invalid_state", "version does not exist")
        review = scene.review(version)
        if (scene.withdrawn or review.review_state is not ReviewState.APPROVED
                or review.projection_id != body["projection_id"]
                or scene.publication.published_version == version):
            raise ApiError("invalid_state")
        check_expected_version(body, item.version)
        previous = scene.publication.published_version
        superseded = scene.publication.superseded_versions + ((previous,) if previous else ())
        publication = Publication(PublicationState.PUBLISHED, version, superseded)
        record_version = self._write_scene(replace(scene, publication=publication), item)
        return {"state": "published", "published_version": version,
                "superseded_version": previous, "record_version": record_version}

    # --- H13 ---------------------------------------------------------------------------

    def withdraw(self, identity: VerifiedIdentity, scene_id: str, body) -> dict:
        scene, item = owned_scene(self._deps, identity.user_id, scene_id)
        body = require_fields(body, required={"expected_version", "reason"})
        reason = body["reason"]
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ApiError("invalid_request", "reason is required")
        if scene.withdrawn:
            raise ApiError("invalid_state")
        check_expected_version(body, item.version)
        now = self._deps.clock()
        publication = replace(scene.publication, state=PublicationState.WITHDRAWN,
                              withdrawn_at=iso(now), withdrawal_reason=reason)
        self._write_scene(replace(scene, publication=publication), item)
        return {"state": "withdrawn", "new_access_blocked_at": iso(now),
                "outstanding_view_grants_expire_by":
                    iso(now + timedelta(seconds=policy.VIEW_GRANT_LIFETIME_S))}
