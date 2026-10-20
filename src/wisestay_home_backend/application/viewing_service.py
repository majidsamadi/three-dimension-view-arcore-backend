"""H14 grants, H15 revocation and H16 view grants (HSB-06.1-06.4, Q07, Q10, Q15).

Audience is explicit named grantees only (Q07).  A view grant is a fresh set of
300-second presigned GET URLs for the audience projection (geometry plus the
projection envelope); it is never renewed, and a withdrawn scene issues no new
view grant.  Every H16 call goes through the CommercialGate (Q10).
"""
from __future__ import annotations

from datetime import timedelta

from wisestay_home_backend.application.common import (
    ServiceDeps,
    epoch,
    grant_sk,
    grants_for,
    iso,
    load_grant,
    load_projection,
    load_scene,
    not_found,
    owned_scene,
    parse_iso,
    require_fields,
    view_grant_sk,
)
from wisestay_home_backend.application.scene_access import resolve_scene
from wisestay_home_backend.adapters.request_identity_facts import RequestIdentityFacts
from wisestay_home_backend.domain import policy
from wisestay_home_backend.domain.asset_reference import ReferenceAction
from wisestay_home_backend.domain.scene import (
    ApiError,
    GrantState,
    PublicationState,
    ReviewState,
    ViewGrant,
    ViewingGrant,
)
from wisestay_home_backend.ports.commercial_gate import CommercialGate
from wisestay_home_backend.ports.identity import VerifiedIdentity
from wisestay_home_backend.ports.object_storage import version_key
from wisestay_home_backend.ports.repository import ConditionFailed, Item, Put

VIEW_GRANT_RECORD_RETENTION_S = 24 * 3600


class ViewingService:
    def __init__(self, deps: ServiceDeps, gate: CommercialGate) -> None:
        self._deps = deps
        self._gate = gate

    # --- H14 ---------------------------------------------------------------------------

    def grant(self, identity: VerifiedIdentity, scene_id: str, body) -> dict:
        scene, _ = owned_scene(self._deps, identity.user_id, scene_id)
        body = require_fields(body, required={"grantee_user_id", "expires_at"})
        if scene.withdrawn:
            raise ApiError("resource_withdrawn")
        grantee = body["grantee_user_id"]
        if (not isinstance(grantee, str) or not grantee.strip() or len(grantee) > 128
                or grantee == identity.user_id):
            raise ApiError("invalid_request", "grantee_user_id must name another account")
        try:
            expires = parse_iso(body["expires_at"])
        except ValueError as exc:
            raise ApiError("invalid_request", "expires_at must be RFC 3339 UTC") from exc
        now = self._deps.clock()
        if not now < expires <= now + timedelta(seconds=policy.AUDIENCE_GRANT_MAX_LIFETIME_S):
            raise ApiError("validation_failed", reasons=["grant_expiry_out_of_range"])
        grant = ViewingGrant(self._deps.ids.new("grt"), scene_id, grantee, identity.user_id,
                             iso(expires), iso(now))
        self._deps.repository.transact([Put(Item(
            f"SCENE#{scene_id}", grant_sk(grant.grant_id), 1, grant.to_data(),
            gsi1pk=f"GRANTEE#{grantee}", gsi1sk=f"SCENE#{scene_id}"), "absent")])
        return {"grant_id": grant.grant_id, "grantee_user_id": grantee,
                "expires_at": grant.expires_at, "state": "active"}

    # --- H15 ---------------------------------------------------------------------------

    def revoke(self, identity: VerifiedIdentity, scene_id: str, grant_id: str, query: dict) -> dict:
        owned_scene(self._deps, identity.user_id, scene_id)
        raw = query.get("expected_version")
        try:
            expected = int(raw)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid_request", "expected_version query parameter is required") from exc
        loaded = load_grant(self._deps.repository, scene_id, grant_id)
        if loaded is None:
            raise not_found()
        grant, item = loaded
        if expected != item.version:
            raise ApiError("version_conflict", current_version=item.version)
        if grant.state is GrantState.REVOKED:
            return {"grant_id": grant_id, "state": "revoked"}
        revoked = ViewingGrant(grant.grant_id, grant.scene_id, grant.grantee_user_id,
                               grant.granted_by, grant.expires_at, grant.created_at,
                               GrantState.REVOKED, iso(self._deps.clock()))
        try:
            self._deps.repository.transact([Put(Item(
                item.pk, item.sk, item.version + 1, revoked.to_data(), gsi1pk=item.gsi1pk,
                gsi1sk=item.gsi1sk), "version", item.version)])
        except ConditionFailed as exc:
            current = self._deps.repository.get(item.pk, item.sk)
            raise ApiError("version_conflict",
                           current_version=current.version if current else item.version) from exc
        return {"grant_id": grant_id, "state": "revoked"}

    # --- H16 ---------------------------------------------------------------------------

    def view_grant(self, identity: VerifiedIdentity, scene_id: str, body) -> dict:
        repo, storage = self._deps.repository, self._deps.storage
        body = require_fields(body or {}, required=set(), optional={"version"})
        loaded = load_scene(repo, scene_id)
        if loaded is None:
            raise not_found()
        scene = loaded[0]
        now = self._deps.clock()
        is_owner = scene.owner_user_id == identity.user_id
        if not is_owner:
            grants = grants_for(repo, identity.user_id, scene_id)
            if not grants:
                raise not_found()
            live = [g for g in grants if g.state is GrantState.ACTIVE and parse_iso(g.expires_at) > now]
            if not live:
                if any(g.state is GrantState.ACTIVE for g in grants):
                    raise ApiError("grant_expired")
                raise ApiError("grant_revoked")
        if scene.withdrawn:
            raise ApiError("resource_withdrawn")
        version = body.get("version")
        if version is not None and not isinstance(version, str):
            raise ApiError("invalid_request", "version must be a string")
        published = (scene.publication.published_version
                     if scene.publication.state is PublicationState.PUBLISHED else None)
        version = version or published
        if version is None or (not is_owner and version != published):
            raise ApiError("invalid_state")
        review = scene.review(version)
        projection = load_projection(repo, scene_id, review.projection_id)
        if review.review_state is not ReviewState.APPROVED or projection is None:
            raise ApiError("invalid_state")
        # Exact reference check through the existing resolver (VIEW_REFERENCE).
        resolve_scene(self._deps, identity, scene_id, version, ReferenceAction.VIEW_REFERENCE)

        actor = RequestIdentityFacts(identity).actor
        outcome = self._gate.check("view", actor, f"home-scene:{scene_id}:{version}")
        if outcome.outcome != "allowed_no_commercial_policy":
            raise ApiError("action_denied")

        expires = now + timedelta(seconds=policy.VIEW_GRANT_LIFETIME_S)
        view = ViewGrant(self._deps.ids.new("vgr"), scene_id, version, identity.user_id,
                         iso(expires), projection.projection_id, iso(now))
        repo.transact([Put(Item(f"SCENE#{scene_id}", view_grant_sk(view.view_grant_id), 1,
                                view.to_data(),
                                ttl_epoch=epoch(expires) + VIEW_GRANT_RECORD_RETENTION_S), "absent")])
        lifetime = policy.VIEW_GRANT_LIFETIME_S
        return {
            "view_grant_id": view.view_grant_id, "scene_id": scene_id, "version": version,
            "expires_at": view.expires_at, "commercial_outcome": outcome.outcome,
            "envelope_url": storage.presign_get(projection.envelope_key, expires_s=lifetime),
            "components": [{"component_id": cid,
                            "get_url": storage.presign_get(version_key(projection.component_digests[cid]),
                                                           expires_s=lifetime)}
                           for cid in projection.components],
        }
