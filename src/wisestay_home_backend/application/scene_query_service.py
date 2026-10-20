"""H07-H09 and H11 scene reads (HSB-03.2-03.4, HSB-05.2).

Owners see every version; grantees see only the published version of a
published, non-withdrawn scene.  Anything else is 404 so existence is never
disclosed.  No read returns a URL; content is reachable only through H16.
"""
from __future__ import annotations

import base64
import json

from wisestay_home_backend.application.common import (
    ServiceDeps,
    active_grant,
    grants_for,
    load_projection,
    load_scene,
    load_version,
    not_found,
    owned_scene,
)
from wisestay_home_backend.application.scene_access import resolve_scene
from wisestay_home_backend.domain import policy
from wisestay_home_backend.domain.asset_reference import ReferenceAction
from wisestay_home_backend.domain.envelope import capabilities
from wisestay_home_backend.domain.scene import (
    EXCLUDED_CATEGORIES,
    PROJECTION_ROLES,
    ApiError,
    PublicationState,
    ReviewState,
    Scene,
    VersionState,
)
from wisestay_home_backend.ports.identity import VerifiedIdentity


def parse_limit(value) -> int:
    if value is None:
        return policy.LIST_LIMIT_DEFAULT
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid_request", "limit must be an integer") from exc
    if not 1 <= limit <= policy.LIST_LIMIT_MAX:
        raise ApiError("invalid_request", "limit must be 1..50")
    return limit


def _encode_cursor(phase: str, inner: str | None) -> str:
    return base64.urlsafe_b64encode(json.dumps([phase, inner]).encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[str, str | None]:
    if cursor is None:
        return "owner", None
    try:
        phase, inner = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ApiError("invalid_request", "invalid cursor") from exc
    if phase not in ("owner", "grantee") or not (inner is None or isinstance(inner, str)):
        raise ApiError("invalid_request", "invalid cursor")
    return phase, inner


class SceneQueryService:
    def __init__(self, deps: ServiceDeps) -> None:
        self._deps = deps

    @staticmethod
    def _summary(scene: Scene, role: str) -> dict:
        return {"scene_id": scene.scene_id, "property_id": scene.property_id, "kind": scene.kind,
                "role": role, "publication_state": scene.publication.state.value,
                "published_version": scene.publication.published_version}

    # --- H07 ---------------------------------------------------------------------------

    def list(self, identity: VerifiedIdentity, query: dict) -> dict:
        limit = parse_limit(query.get("limit"))
        phase, inner = _decode_cursor(query.get("cursor"))
        repo = self._deps.repository
        items: list[dict] = []
        seen: set[str] = set()
        while len(items) < limit:
            if phase == "owner":
                rows, inner = repo.query_gsi1(f"OWNER#{identity.user_id}", "SCENE#",
                                              limit=limit - len(items), cursor=inner)
                for row in rows:
                    scene = Scene.from_data(row.data)
                    items.append(self._summary(scene, "owner"))
            else:
                rows, inner = repo.query_gsi1(f"GRANTEE#{identity.user_id}", "SCENE#",
                                              limit=limit - len(items), cursor=inner)
                for row in rows:
                    scene_id = row.data.get("scene_id")
                    if scene_id in seen:
                        continue
                    loaded = load_scene(repo, scene_id)
                    if loaded is None:
                        continue
                    scene = loaded[0]
                    if (scene.publication.state is not PublicationState.PUBLISHED
                            or active_grant(grants_for(repo, identity.user_id, scene_id),
                                            self._deps.clock()) is None):
                        continue
                    seen.add(scene_id)
                    items.append(self._summary(scene, "grantee"))
            if inner is None:
                if phase == "owner":
                    phase = "grantee"
                    continue
                return {"items": items, "next_cursor": None}
        return {"items": items, "next_cursor": _encode_cursor(phase, inner)}

    # --- H08 ---------------------------------------------------------------------------

    def get(self, identity: VerifiedIdentity, scene_id: str) -> dict:
        access = resolve_scene(self._deps, identity, scene_id, None, ReferenceAction.READ_METADATA,
                               withdrawn_status="owner_visible")
        scene = access.scene
        versions = sorted(scene.version_summaries, key=int)
        if access.role == "grantee":
            versions = [v for v in versions if v == scene.publication.published_version]
        loaded = load_scene(self._deps.repository, scene_id)
        record_version = loaded[1].version if loaded else 0
        return {
            "scene_id": scene.scene_id, "property_id": scene.property_id, "kind": scene.kind,
            "role": access.role,
            "versions": [{"version": v, **{k: scene.version_summaries[v][k] for k in (
                "state", "scale_claim", "bounds_m", "capabilities", "missing_regions")},
                "review_state": scene.review(v).review_state.value} for v in versions],
            "publication": {"state": scene.publication.state.value,
                            "published_version": scene.publication.published_version,
                            "superseded_versions": list(scene.publication.superseded_versions)},
            "record_version": record_version,
        }

    # --- H09 ---------------------------------------------------------------------------

    def get_version(self, identity: VerifiedIdentity, scene_id: str, version: str) -> dict:
        access = resolve_scene(self._deps, identity, scene_id, version, ReferenceAction.READ_METADATA)
        scene = access.scene
        stored = load_version(self._deps.repository, scene_id, version)
        if stored is None:
            raise not_found()
        review = scene.review(version)
        projection = load_projection(self._deps.repository, scene_id, review.projection_id)
        envelope = projection_envelope(stored.envelope, projection.projection_id) if projection \
            else stored.envelope
        return {"scene_id": scene_id, "version": version, "kind": scene.kind,
                "state": stored.state.value, "review_state": review.review_state.value,
                "envelope": envelope,
                "capabilities": capabilities(stored.envelope,
                                             validated=stored.state is VersionState.VALIDATED),
                "publication_state": scene.publication.state.value}

    # --- H11 ---------------------------------------------------------------------------

    def audience_projection(self, identity: VerifiedIdentity, scene_id: str, version: str) -> dict:
        scene, _ = owned_scene(self._deps, identity.user_id, scene_id)
        if load_version(self._deps.repository, scene_id, version) is None:
            raise not_found()
        review = scene.review(version)
        projection = load_projection(self._deps.repository, scene_id, review.projection_id)
        if review.review_state is not ReviewState.APPROVED or projection is None:
            raise ApiError("invalid_state")
        return {"projection_id": projection.projection_id, "scene_id": scene_id,
                "version": version, "components": list(projection.components),
                "excluded_categories": list(EXCLUDED_CATEGORIES),
                "envelope_sha256": projection.envelope_sha256, "audience": projection.audience}


def projection_envelope(envelope: dict, projection_id: str) -> dict:
    """The audience-facing envelope: geometry components only (HSB-03.2)."""
    return {**envelope, "audience_projection_id": projection_id,
            "components": [c for c in envelope["components"] if c["role"] in PROJECTION_ROLES]}
