"""Home Scanner reference and authority facts.

This module is intentionally internal and transport-free.  It models only the
facts required to validate an exact Home asset reference at the service
boundary.  It does not create users, properties, grants, publications, storage
records, or deployment resources.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


class IdentityFactStatus(str, Enum):
    CURRENT = "current"
    SIGNED_OUT = "signed_out"
    WRONG_ACCOUNT = "wrong_account"
    UNAVAILABLE = "unavailable"


class ResourceFactStatus(str, Enum):
    CURRENT = "current"
    NOT_FOUND = "not_found"
    WITHDRAWN = "withdrawn"
    UNAVAILABLE = "unavailable"


class AuthorityFactStatus(str, Enum):
    CURRENT = "current"
    UNAVAILABLE = "unavailable"


class ActionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class ReferenceAction(str, Enum):
    """Bounded non-commercial actions supported by this preparation slice."""

    READ_METADATA = "read_metadata"
    VIEW_REFERENCE = "view_reference"


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: str
    application_id: str
    organization_id: str | None = None
    relationship_id: str | None = None

    def __post_init__(self) -> None:
        _required(self.user_id, "user_id")
        _required(self.application_id, "application_id")
        if self.organization_id is not None:
            _required(self.organization_id, "organization_id")
        if self.relationship_id is not None:
            _required(self.relationship_id, "relationship_id")


@dataclass(frozen=True, slots=True)
class HomeAssetReference:
    """Exact Home scene reference plus canonical Resvanta property reference."""

    scene_id: str
    scene_revision: str
    property_id: str

    def __post_init__(self) -> None:
        _required(self.scene_id, "scene_id")
        _required(self.scene_revision, "scene_revision")
        _required(self.property_id, "property_id")


@dataclass(frozen=True, slots=True)
class IdentityFact:
    status: IdentityFactStatus
    context: ActorContext | None = None


@dataclass(frozen=True, slots=True)
class HomeResourceFact:
    status: ResourceFactStatus
    reference: HomeAssetReference | None = None


@dataclass(frozen=True, slots=True)
class CurrentActionFact:
    """A fact received from the owning/current-authority adapter.

    The boundary never creates this fact.  Exact actor, application, resource,
    revision, property and action are carried so stale/cross-context facts fail
    closed.
    """

    status: AuthorityFactStatus
    decision: ActionDecision | None
    user_id: str | None
    application_id: str | None
    # Required constructor fields: None is explicitly attested personal/no-relationship
    # scope; omission or unavailable scope must never silently use None.
    organization_id: str | None
    relationship_id: str | None
    scene_id: str | None
    scene_revision: str | None
    property_id: str | None
    action: ReferenceAction | None

    def __post_init__(self) -> None:
        if self.organization_id is not None:
            _required(self.organization_id, "organization_id")
        if self.relationship_id is not None:
            _required(self.relationship_id, "relationship_id")


@dataclass(frozen=True, slots=True)
class ResolvedHomeReference:
    """Exact reference validated against injected current facts.

    This is not a grant, publication receipt, storage record, or content key.
    """

    reference: HomeAssetReference
    actor: ActorContext
    action: ReferenceAction


class BoundaryError(RuntimeError):
    code = "boundary_error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)


class IdentityRequired(BoundaryError):
    code = "identity_required"


class WrongAccount(BoundaryError):
    code = "wrong_account"


class DependencyUnavailable(BoundaryError):
    code = "dependency_unavailable"


class ResourceNotFound(BoundaryError):
    code = "resource_not_found"


class ResourceWithdrawn(BoundaryError):
    code = "resource_withdrawn"


class ReferenceMismatch(BoundaryError):
    code = "reference_mismatch"


class ActionDenied(BoundaryError):
    code = "action_denied"


class StaleAuthorityFact(BoundaryError):
    code = "stale_authority_fact"
