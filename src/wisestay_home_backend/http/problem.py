"""``application/problem+json`` responses for the closed X.1 code table."""
from __future__ import annotations

from wisestay_home_backend.domain.scene import ERROR_STATUS

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://wizestay.com/problems/"

TITLES: dict[str, str] = {
    "invalid_request": "The request is not valid",
    "idempotency_key_required": "An Idempotency-Key header is required",
    "identity_required": "Sign-in is required",
    "action_denied": "This action is not allowed",
    "grant_expired": "The viewing grant has expired",
    "grant_revoked": "The viewing grant was revoked",
    "export_not_available": "Export is not available",
    "seller_membership_unverified": "Seller membership is not verified",
    "not_found": "Not found",
    "version_conflict": "The record changed; reload and retry",
    "idempotency_key_reuse": "The Idempotency-Key was used with a different request",
    "already_finalized": "The upload is already finalized",
    "upload_incomplete": "Some components are not uploaded yet",
    "invalid_state": "The resource is not in a state that allows this action",
    "resource_withdrawn": "The resource was withdrawn",
    "upload_expired": "The upload session has expired",
    "query_expired": "The query has expired",
    "limit_exceeded": "A size or count limit was exceeded",
    "validation_failed": "Validation failed",
    "component_digest_mismatch": "A component digest does not match",
    "component_size_mismatch": "A component size does not match",
    "occupied_home_publication_disabled": "Occupied-home content is not supported",
    "property_not_usable": "The property cannot be used for a capture",
    "unsupported_input": "The input is not supported",
    "unsupported_scale": "The scale is not supported",
    "identity_unavailable": "Sign-in could not be checked right now",
    "dependency_unavailable": "A dependency is unavailable; retry later",
}

assert set(TITLES) == set(ERROR_STATUS), "every X.1 code needs a fixed title"


def problem_body(code: str, request_id: str, extras: dict | None = None) -> dict:
    status = ERROR_STATUS[code]
    body = {"type": PROBLEM_TYPE_BASE + code, "title": TITLES[code], "status": status,
            "code": code, "request_id": request_id}
    body.update(extras or {})
    return body
