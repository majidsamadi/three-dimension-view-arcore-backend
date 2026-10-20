"""Home Scanner capture, upload, scene version, publication and grant records.

HSB-02 to HSB-06 (wave 2).  Frozen slotted dataclasses, ``str`` enums and the
closed problem-code table of plan section X.1.  The module is transport-free:
records convert to and from plain JSON-compatible dicts for the repository
port, and nothing here performs I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from wisestay_home_backend.domain.asset_reference import BoundaryError


# --- closed problem-code table (X.1) -------------------------------------------------

ERROR_STATUS: dict[str, int] = {
    "invalid_request": 400,
    "idempotency_key_required": 400,
    "identity_required": 401,
    "action_denied": 403,
    "grant_expired": 403,
    "grant_revoked": 403,
    "export_not_available": 403,
    "seller_membership_unverified": 403,
    "not_found": 404,
    "version_conflict": 409,
    "idempotency_key_reuse": 409,
    "already_finalized": 409,
    "upload_incomplete": 409,
    "invalid_state": 409,
    "resource_withdrawn": 410,
    "upload_expired": 410,
    "query_expired": 410,
    "limit_exceeded": 413,
    "validation_failed": 422,
    "component_digest_mismatch": 422,
    "component_size_mismatch": 422,
    "occupied_home_publication_disabled": 422,
    "property_not_usable": 422,
    "unsupported_input": 422,
    "unsupported_scale": 422,
    "identity_unavailable": 503,
    "dependency_unavailable": 503,
}


class ApiError(BoundaryError):
    """A service failure that maps onto exactly one X.1 problem code.

    ``extras`` carries only the optional problem members allowed by X.1
    (``current_version``, ``reasons``, ``components``) plus the H06
    ``already_finalized`` members ``scene_id`` / ``version``.
    """

    _ALLOWED_EXTRAS = frozenset(
        {"current_version", "current_revision", "reasons", "components", "scene_id", "version"}
    )

    def __init__(self, code: str, message: str = "", **extras: Any) -> None:
        if code not in ERROR_STATUS:
            raise ValueError(f"{code!r} is not in the closed X.1 problem-code table")
        unknown = set(extras) - self._ALLOWED_EXTRAS
        if unknown:
            raise ValueError(f"problem extras not allowed: {sorted(unknown)}")
        self.code = code
        self.status = ERROR_STATUS[code]
        self.extras = extras
        super().__init__(message or code)


# --- enums -----------------------------------------------------------------------------

class CaptureKind(str, Enum):
    HOME = "home"
    SHOP = "shop"


class CapturePurpose(str, Enum):
    LISTING_TOUR = "listing_tour"
    PLANNING = "planning"
    SHOP_MAP = "shop_map"


class ContentClass(str, Enum):
    SYNTHETIC = "synthetic"
    PERMITTED_UNOCCUPIED_REFERENCE = "permitted-unoccupied-reference"


class ComponentState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class UploadState(str, Enum):
    OPEN = "open"
    FINALIZING = "finalizing"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class VersionState(str, Enum):
    VALIDATED = "validated"
    QUARANTINED = "quarantined"


class ReviewState(str, Enum):
    DRAFT = "draft"
    REVIEW_READY = "review_ready"
    APPROVED = "approved"
    REJECTED = "rejected"


REVIEW_TRANSITIONS: dict[ReviewState, frozenset[ReviewState]] = {
    ReviewState.DRAFT: frozenset({ReviewState.REVIEW_READY, ReviewState.APPROVED, ReviewState.REJECTED}),
    ReviewState.REVIEW_READY: frozenset({ReviewState.APPROVED, ReviewState.REJECTED}),
    ReviewState.REJECTED: frozenset({ReviewState.REVIEW_READY}),
    ReviewState.APPROVED: frozenset(),
}


class PublicationState(str, Enum):
    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class GrantState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


# Roles that never leave the owner's private material (HSB-03.2).
PROJECTION_ROLES = frozenset({"geometry"})
EXCLUDED_CATEGORIES = ("raw_capture", "diagnostics", "review_model", "source_photos", "notes")


# --- records ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CaptureSession:
    capture_id: str
    owner_user_id: str
    property_id: str
    property_type: str
    property_record_version: int | None
    kind: str
    purpose: str
    content_class: str
    permission_record_id: str | None
    local_draft_ref: str | None
    created_at: str
    state: str = "open"
    scene_id: str | None = None

    def to_data(self) -> dict:
        return {name: getattr(self, name) for name in self.__slots__}

    @classmethod
    def from_data(cls, data: dict) -> "CaptureSession":
        return cls(**{name: data.get(name) for name in cls.__slots__})


@dataclass(frozen=True, slots=True)
class ComponentSlot:
    component_id: str
    role: str
    media_type: str
    sha256: str
    bytes: int
    state: ComponentState = ComponentState.PENDING
    reason: str | None = None

    def to_data(self) -> dict:
        return {"component_id": self.component_id, "role": self.role,
                "media_type": self.media_type, "sha256": self.sha256, "bytes": self.bytes,
                "state": self.state.value, "reason": self.reason}

    @classmethod
    def from_data(cls, data: dict) -> "ComponentSlot":
        return cls(data["component_id"], data["role"], data["media_type"], data["sha256"],
                   int(data["bytes"]), ComponentState(data["state"]), data.get("reason"))


@dataclass(frozen=True, slots=True)
class UploadSession:
    upload_id: str
    capture_id: str
    owner_user_id: str
    state: UploadState
    created_at: str
    expires_at: str
    envelope: dict
    components: tuple[ComponentSlot, ...]
    scene_id: str | None = None
    version: str | None = None
    finalize_result: dict | None = None

    def to_data(self) -> dict:
        return {"upload_id": self.upload_id, "capture_id": self.capture_id,
                "owner_user_id": self.owner_user_id, "state": self.state.value,
                "created_at": self.created_at, "expires_at": self.expires_at,
                "envelope": self.envelope,
                "components": [c.to_data() for c in self.components],
                "scene_id": self.scene_id, "version": self.version,
                "finalize_result": self.finalize_result}

    @classmethod
    def from_data(cls, data: dict) -> "UploadSession":
        return cls(data["upload_id"], data["capture_id"], data["owner_user_id"],
                   UploadState(data["state"]), data["created_at"], data["expires_at"],
                   data["envelope"], tuple(ComponentSlot.from_data(c) for c in data["components"]),
                   data.get("scene_id"), data.get("version"), data.get("finalize_result"))

    def with_components(self, components: tuple[ComponentSlot, ...]) -> "UploadSession":
        return replace(self, components=components)


@dataclass(frozen=True, slots=True)
class SceneVersion:
    """Immutable once written (repository ``expect="absent"`` only).

    Review state is not stored here: it lives on the scene record so the
    version item, its envelope digest and its content-addressed components are
    never rewritten (HSB-03.3).
    """

    scene_id: str
    version: str
    upload_id: str
    state: VersionState
    reasons: tuple[str, ...]
    envelope: dict
    envelope_sha256: str
    components: tuple[dict, ...]
    created_at: str

    def to_data(self) -> dict:
        return {"scene_id": self.scene_id, "version": self.version, "upload_id": self.upload_id,
                "state": self.state.value, "reasons": list(self.reasons),
                "envelope": self.envelope, "envelope_sha256": self.envelope_sha256,
                "components": [dict(c) for c in self.components], "created_at": self.created_at}

    @classmethod
    def from_data(cls, data: dict) -> "SceneVersion":
        return cls(data["scene_id"], data["version"], data["upload_id"],
                   VersionState(data["state"]), tuple(data["reasons"]), data["envelope"],
                   data["envelope_sha256"], tuple(data["components"]), data["created_at"])


@dataclass(frozen=True, slots=True)
class Publication:
    state: PublicationState = PublicationState.UNPUBLISHED
    published_version: str | None = None
    superseded_versions: tuple[str, ...] = ()
    withdrawn_at: str | None = None
    withdrawal_reason: str | None = None

    def to_data(self) -> dict:
        return {"state": self.state.value, "published_version": self.published_version,
                "superseded_versions": list(self.superseded_versions),
                "withdrawn_at": self.withdrawn_at, "withdrawal_reason": self.withdrawal_reason}

    @classmethod
    def from_data(cls, data: dict) -> "Publication":
        return cls(PublicationState(data["state"]), data.get("published_version"),
                   tuple(data.get("superseded_versions", ())), data.get("withdrawn_at"),
                   data.get("withdrawal_reason"))


@dataclass(frozen=True, slots=True)
class VersionReview:
    review_state: ReviewState = ReviewState.DRAFT
    projection_id: str | None = None
    history: tuple[dict, ...] = ()

    def to_data(self) -> dict:
        return {"review_state": self.review_state.value, "projection_id": self.projection_id,
                "history": [dict(h) for h in self.history]}

    @classmethod
    def from_data(cls, data: dict) -> "VersionReview":
        return cls(ReviewState(data["review_state"]), data.get("projection_id"),
                   tuple(data.get("history", ())))


@dataclass(frozen=True, slots=True)
class Scene:
    scene_id: str
    owner_user_id: str
    capture_id: str
    property_id: str
    property_type: str
    kind: str
    content_class: str
    created_at: str
    latest_version: int
    version_summaries: dict = field(default_factory=dict)  # version -> {state, scale_claim, ...}
    reviews: dict = field(default_factory=dict)            # version -> VersionReview
    publication: Publication = Publication()

    def to_data(self) -> dict:
        return {"scene_id": self.scene_id, "owner_user_id": self.owner_user_id,
                "capture_id": self.capture_id, "property_id": self.property_id,
                "property_type": self.property_type, "kind": self.kind,
                "content_class": self.content_class, "created_at": self.created_at,
                "latest_version": self.latest_version,
                "version_summaries": {k: dict(v) for k, v in self.version_summaries.items()},
                "reviews": {k: v.to_data() for k, v in self.reviews.items()},
                "publication": self.publication.to_data()}

    @classmethod
    def from_data(cls, data: dict) -> "Scene":
        return cls(data["scene_id"], data["owner_user_id"], data["capture_id"],
                   data["property_id"], data["property_type"], data["kind"],
                   data["content_class"], data["created_at"], int(data["latest_version"]),
                   dict(data["version_summaries"]),
                   {k: VersionReview.from_data(v) for k, v in data["reviews"].items()},
                   Publication.from_data(data["publication"]))

    def review(self, version: str) -> VersionReview:
        return self.reviews.get(version, VersionReview())

    @property
    def withdrawn(self) -> bool:
        return self.publication.state is PublicationState.WITHDRAWN


@dataclass(frozen=True, slots=True)
class AudienceProjection:
    projection_id: str
    scene_id: str
    version: str
    components: tuple[str, ...]
    component_digests: dict
    envelope_sha256: str
    envelope_key: str
    created_at: str
    audience: str = "explicit_grantees"

    def to_data(self) -> dict:
        return {"projection_id": self.projection_id, "scene_id": self.scene_id,
                "version": self.version, "components": list(self.components),
                "component_digests": dict(self.component_digests),
                "envelope_sha256": self.envelope_sha256, "envelope_key": self.envelope_key,
                "created_at": self.created_at, "audience": self.audience}

    @classmethod
    def from_data(cls, data: dict) -> "AudienceProjection":
        return cls(data["projection_id"], data["scene_id"], data["version"],
                   tuple(data["components"]), dict(data["component_digests"]),
                   data["envelope_sha256"], data["envelope_key"], data["created_at"],
                   data.get("audience", "explicit_grantees"))


@dataclass(frozen=True, slots=True)
class ViewingGrant:
    grant_id: str
    scene_id: str
    grantee_user_id: str
    granted_by: str
    expires_at: str
    created_at: str
    state: GrantState = GrantState.ACTIVE
    revoked_at: str | None = None

    def to_data(self) -> dict:
        return {"grant_id": self.grant_id, "scene_id": self.scene_id,
                "grantee_user_id": self.grantee_user_id, "granted_by": self.granted_by,
                "expires_at": self.expires_at, "created_at": self.created_at,
                "state": self.state.value, "revoked_at": self.revoked_at}

    @classmethod
    def from_data(cls, data: dict) -> "ViewingGrant":
        return cls(data["grant_id"], data["scene_id"], data["grantee_user_id"],
                   data["granted_by"], data["expires_at"], data["created_at"],
                   GrantState(data["state"]), data.get("revoked_at"))


@dataclass(frozen=True, slots=True)
class ViewGrant:
    """A short-lived (300 s) set of presigned GET URLs.  Never renewed."""

    view_grant_id: str
    scene_id: str
    version: str
    user_id: str
    expires_at: str
    projection_id: str
    created_at: str

    def to_data(self) -> dict:
        return {name: getattr(self, name) for name in self.__slots__}
