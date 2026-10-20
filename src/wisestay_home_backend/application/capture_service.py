"""H01 capture session admission (HSB-02.1; Q07 first-slice content, Q14).

A capture is admitted only for a ``current`` Resvanta property reference.  A
REAL property also needs a ``permission_record_id``.  Occupied-home content is
refused (Q07: synthetic data plus permitted unoccupied references only).
"""
from __future__ import annotations

from wisestay_home_backend.application.common import ServiceDeps, capture_key, iso, require_fields
from wisestay_home_backend.domain.asset_reference import ActorContext
from wisestay_home_backend.domain.scene import (
    ApiError,
    CaptureKind,
    CapturePurpose,
    CaptureSession,
    ContentClass,
)
from wisestay_home_backend.ports.property_reference import PropertyReferencePort
from wisestay_home_backend.ports.repository import Item, Put

_REQUIRED = frozenset({"property_id", "kind", "purpose", "capture_mode", "content_class", "consent"})
_OPTIONAL = frozenset({"permission_record_id", "local_draft_ref"})


def _optional_text(value, field: str, max_len: int = 128) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ApiError("invalid_request", f"{field} must be a non-empty string")
    return value


class CaptureService:
    def __init__(self, deps: ServiceDeps, properties: PropertyReferencePort) -> None:
        self._deps = deps
        self._properties = properties

    def create(self, actor: ActorContext, body) -> dict:
        body = require_fields(body, required=_REQUIRED, optional=_OPTIONAL)
        if body["content_class"] == "occupied":
            raise ApiError("occupied_home_publication_disabled")
        property_id = body["property_id"]
        if not isinstance(property_id, str) or not property_id.strip() or len(property_id) > 128:
            raise ApiError("invalid_request", "property_id is required")
        try:
            kind = CaptureKind(body["kind"])
            purpose = CapturePurpose(body["purpose"])
            content_class = ContentClass(body["content_class"])
        except ValueError as exc:
            raise ApiError("invalid_request", "kind, purpose or content_class is invalid") from exc
        if body["capture_mode"] != "local":
            raise ApiError("invalid_request", "capture_mode must be local (Q02)")
        consent = body["consent"]
        if not (isinstance(consent, dict) and set(consent) == {"upload_processed_representation"}
                and consent["upload_processed_representation"] is True):
            raise ApiError("invalid_request", "consent to upload the processed representation is required")
        permission = _optional_text(body.get("permission_record_id"), "permission_record_id")
        draft_ref = _optional_text(body.get("local_draft_ref"), "local_draft_ref")

        fact = self._properties.resolve(property_id)
        if fact.status == "unavailable":
            raise ApiError("dependency_unavailable")
        if fact.status != "current" or fact.property_type not in ("REAL", "VIRTUAL"):
            raise ApiError("property_not_usable")
        if fact.property_type == "REAL" and permission is None:
            raise ApiError("property_not_usable", "a REAL property needs a permission record")

        now = iso(self._deps.clock())
        capture = CaptureSession(
            capture_id=self._deps.ids.new("cap"), owner_user_id=actor.user_id,
            property_id=property_id, property_type=fact.property_type,
            property_record_version=fact.record_version, kind=kind.value, purpose=purpose.value,
            content_class=content_class.value, permission_record_id=permission,
            local_draft_ref=draft_ref, created_at=now,
        )
        pk, sk = capture_key(capture.capture_id)
        self._deps.repository.transact([Put(Item(pk, sk, 1, capture.to_data()), "absent")])
        return {"capture_id": capture.capture_id, "property_id": property_id,
                "property_type": fact.property_type, "kind": capture.kind, "state": "open",
                "record_version": 1, "created_at": now}
