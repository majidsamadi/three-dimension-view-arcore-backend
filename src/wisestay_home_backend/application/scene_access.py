"""Read-path access through the existing ``HomeReferenceResolver`` (X.6 mapping).

Every scene read (H08, H09, H16) builds the exact ``HomeAssetReference``
(scene id, version, Resvanta property id) and resolves it with:

* ``RequestIdentityFacts`` - the verified central identity;
* ``SceneResourceFacts`` - the scene record (withdrawn / not found / current);
* ``SceneActionFacts`` - owner, or an active grant on the published version.

The resolver is reused unchanged.  Its failures map to 404 (never disclosing
existence), 410 for withdrawn scenes, or 503.
"""
from __future__ import annotations

from dataclasses import dataclass

from wisestay_home_backend.application.common import (
    ServiceDeps,
    active_grant,
    grants_for,
    load_scene,
    load_version,
    not_found,
)
from wisestay_home_backend.application.resolve_asset_reference import HomeReferenceResolver
from wisestay_home_backend.adapters.request_identity_facts import RequestIdentityFacts
from wisestay_home_backend.domain.asset_reference import (
    ActionDecision,
    ActionDenied,
    ActorContext,
    AuthorityFactStatus,
    BoundaryError,
    CurrentActionFact,
    DependencyUnavailable,
    HomeAssetReference,
    HomeResourceFact,
    ReferenceAction,
    ResourceFactStatus,
    ResourceNotFound,
    ResourceWithdrawn,
)
from wisestay_home_backend.domain.scene import ApiError, PublicationState, Scene
from wisestay_home_backend.ports.identity import VerifiedIdentity


class SceneResourceFacts:
    def __init__(self, deps: ServiceDeps, *, withdrawn_is_current: bool = False) -> None:
        self._deps = deps
        self._withdrawn_is_current = withdrawn_is_current

    def lookup_home(self, reference: HomeAssetReference) -> HomeResourceFact:
        loaded = load_scene(self._deps.repository, reference.scene_id)
        if loaded is None:
            return HomeResourceFact(ResourceFactStatus.NOT_FOUND)
        scene = loaded[0]
        if scene.withdrawn and not self._withdrawn_is_current:
            return HomeResourceFact(ResourceFactStatus.WITHDRAWN)
        if load_version(self._deps.repository, scene.scene_id, reference.scene_revision) is None:
            return HomeResourceFact(ResourceFactStatus.NOT_FOUND)
        return HomeResourceFact(ResourceFactStatus.CURRENT, HomeAssetReference(
            scene.scene_id, reference.scene_revision, scene.property_id))


class SceneActionFacts:
    def __init__(self, deps: ServiceDeps) -> None:
        self._deps = deps

    def current_home_action(self, actor: ActorContext, reference: HomeAssetReference,
                            action: ReferenceAction) -> CurrentActionFact:
        loaded = load_scene(self._deps.repository, reference.scene_id)
        decision = ActionDecision.DENY
        if loaded is not None:
            scene = loaded[0]
            if scene.owner_user_id == actor.user_id:
                decision = ActionDecision.ALLOW
            elif (scene.publication.state is PublicationState.PUBLISHED
                  and scene.publication.published_version == reference.scene_revision
                  and active_grant(grants_for(self._deps.repository, actor.user_id, scene.scene_id),
                                   self._deps.clock()) is not None):
                decision = ActionDecision.ALLOW
        return CurrentActionFact(
            status=AuthorityFactStatus.CURRENT, decision=decision, user_id=actor.user_id,
            application_id=actor.application_id, organization_id=actor.organization_id,
            relationship_id=actor.relationship_id, scene_id=reference.scene_id,
            scene_revision=reference.scene_revision, property_id=reference.property_id,
            action=action)


@dataclass(frozen=True, slots=True)
class SceneAccess:
    scene: Scene
    role: str  # "owner" | "grantee"


def resolve_scene(deps: ServiceDeps, identity: VerifiedIdentity, scene_id: str, version: str | None,
                  action: ReferenceAction, *, withdrawn_status: str = "resource_withdrawn") -> SceneAccess:
    """Resolve the exact reference or raise an ``ApiError``."""
    loaded = load_scene(deps.repository, scene_id)
    if loaded is None:
        raise not_found()
    scene = loaded[0]
    facts = RequestIdentityFacts(identity)
    is_owner = scene.owner_user_id == identity.user_id
    revision = version or scene.publication.published_version or str(scene.latest_version)
    resolver = HomeReferenceResolver(
        facts, SceneResourceFacts(deps, withdrawn_is_current=is_owner and withdrawn_status == "owner_visible"),
        SceneActionFacts(deps))
    try:
        resolver.resolve(HomeAssetReference(scene.scene_id, revision, scene.property_id), action)
    except ResourceWithdrawn as exc:
        if withdrawn_status == "owner_visible":
            raise not_found() from exc
        raise ApiError("resource_withdrawn") from exc
    except (ResourceNotFound, ActionDenied) as exc:
        raise not_found() from exc
    except DependencyUnavailable as exc:
        raise ApiError("dependency_unavailable") from exc
    except BoundaryError as exc:  # mismatch / stale fact: fail closed without disclosure
        raise not_found() from exc
    return SceneAccess(scene, "owner" if is_owner else "grantee")
