"""Transport-neutral request dispatch for the Home Scanner API (H01-H16).

Order for every request: route match (unknown -> 404) -> body cap (2 MB ->
413) -> central identity (401 / 503) -> JSON body -> Idempotency-Key (idem
routes) -> idempotent replay or 409 reuse -> service call -> problem mapping.
Only successful (2xx) results are stored for replay, for 24 hours.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import hashlib
import json
import logging
import re

from wisestay_home_backend.application.capture_service import CaptureService
from wisestay_home_backend.application.common import ServiceDeps, epoch, idempotency_key
from wisestay_home_backend.application.publication_service import PublicationService
from wisestay_home_backend.application.scene_query_service import SceneQueryService
from wisestay_home_backend.application.upload_service import UploadService
from wisestay_home_backend.application.viewing_service import ViewingService
from wisestay_home_backend.domain import policy
from wisestay_home_backend.domain.asset_reference import ActorContext, IdentityRequired
from wisestay_home_backend.domain.envelope import canonical_json
from wisestay_home_backend.domain.scene import ApiError
from wisestay_home_backend.http import router
from wisestay_home_backend.http.problem import PROBLEM_CONTENT_TYPE, problem_body
from wisestay_home_backend.ports.commercial_gate import CommercialGate
from wisestay_home_backend.ports.identity import IdentityUnavailable, IdentityVerifier, VerifiedIdentity
from wisestay_home_backend.ports.object_storage import StorageUnavailable
from wisestay_home_backend.ports.property_reference import PropertyReferencePort
from wisestay_home_backend.ports.repository import ConditionFailed, Item, Put, RepositoryUnavailable

LOGGER = logging.getLogger("wisestay_home_backend.http")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
JSON_CONTENT_TYPE = "application/json"


def _reject_constant(name: str):
    raise ValueError(f"{name} is not valid JSON")


@dataclass(frozen=True, slots=True)
class Request:
    method: str
    path: str
    headers: dict = field(default_factory=dict)  # any case; looked up case-insensitively
    query: dict = field(default_factory=dict)
    body: bytes | None = None
    request_id: str = "local"

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    body: dict
    headers: dict

    def encoded(self) -> bytes:
        return json.dumps(self.body, sort_keys=True, separators=(",", ":")).encode("utf-8")


class HomeScannerApi:
    def __init__(self, *, deps: ServiceDeps, identity: IdentityVerifier,
                 properties: PropertyReferencePort, gate: CommercialGate) -> None:
        self._deps = deps
        self._identity = identity
        self.captures = CaptureService(deps, properties)
        self.uploads = UploadService(deps)
        self.scenes = SceneQueryService(deps)
        self.publication = PublicationService(deps)
        self.viewing = ViewingService(deps, gate)

    # --- responses -----------------------------------------------------------------------

    @staticmethod
    def _problem(code: str, request: Request, extras: dict | None = None) -> Response:
        body = problem_body(code, request.request_id, extras)
        return Response(body["status"], body, {"Content-Type": PROBLEM_CONTENT_TYPE,
                                               "X-Request-Id": request.request_id})

    @staticmethod
    def _ok(status: int, body: dict, request: Request) -> Response:
        headers = {"Content-Type": JSON_CONTENT_TYPE, "X-Request-Id": request.request_id}
        if request.method == "GET" and isinstance(body.get("record_version"), int):
            headers["ETag"] = f'"{body["record_version"]}"'
        return Response(status, body, headers)

    # --- dispatch ------------------------------------------------------------------------

    def dispatch(self, request: Request) -> Response:
        try:
            return self._dispatch(request)
        except ApiError as exc:
            return self._problem(exc.code, request, exc.extras)
        except IdentityRequired:
            return self._problem("identity_required", request)
        except IdentityUnavailable:
            return self._problem("identity_unavailable", request)
        except (RepositoryUnavailable, StorageUnavailable):
            return self._problem("dependency_unavailable", request)
        except Exception as exc:  # never leak a stack trace; the table has no 500 code
            LOGGER.error(json.dumps({"event": "unhandled_error", "type": type(exc).__name__,
                                     "request_id": request.request_id}))
            return self._problem("dependency_unavailable", request)

    def _dispatch(self, request: Request) -> Response:
        found = router.match(request.method, request.path)
        if found is None:
            raise ApiError("not_found")
        route, params = found
        if request.body is not None and len(request.body) > policy.MAX_REQUEST_BODY_BYTES:
            raise ApiError("limit_exceeded")
        identity = self._identity.verify(request.header("Authorization"))
        body = self._json_body(request)
        if not route.idempotent:
            return self._ok(route.status, self._call(route, identity, params, request.query, body),
                            request)

        key = request.header("Idempotency-Key")
        if not isinstance(key, str) or not IDEMPOTENCY_KEY.match(key):
            raise ApiError("idempotency_key_required")
        digest = hashlib.sha256(canonical_json(
            {"params": params, "query": request.query, "body": body})).hexdigest()
        pk, sk = idempotency_key(identity.user_id, route.route_id, key)
        stored = self._deps.repository.get(pk, sk)
        if stored is not None:
            return self._replay(stored, digest, request)
        result = self._call(route, identity, params, request.query, body)
        expires = self._deps.clock() + timedelta(seconds=policy.IDEMPOTENCY_RETENTION_S)
        record = {"digest": digest, "status": route.status, "body": result}
        try:
            self._deps.repository.transact([Put(Item(pk, sk, 1, record, ttl_epoch=epoch(expires)),
                                                "absent")])
        except ConditionFailed:
            current = self._deps.repository.get(pk, sk)
            if current is not None:
                return self._replay(current, digest, request)
        return self._ok(route.status, result, request)

    def _replay(self, stored: Item, digest: str, request: Request) -> Response:
        if stored.data.get("digest") != digest:
            raise ApiError("idempotency_key_reuse")
        return self._ok(int(stored.data["status"]), stored.data["body"], request)

    @staticmethod
    def _json_body(request: Request):
        if request.method in ("GET", "DELETE"):
            return None
        if not request.body:
            return {}
        try:
            value = json.loads(request.body.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ApiError("invalid_request", "body must be JSON") from exc
        if not isinstance(value, dict):
            raise ApiError("invalid_request", "body must be a JSON object")
        return value

    def _call(self, route: router.Route, identity: VerifiedIdentity, params: dict, query: dict,
              body) -> dict:
        actor = ActorContext(identity.user_id, identity.application_id)
        handler = route.handler
        if handler == "create_capture":
            return self.captures.create(actor, body)
        if handler == "create_upload":
            return self.uploads.create(actor, params["capture_id"], body)
        if handler == "get_upload":
            return self.uploads.get(actor, params["upload_id"])
        if handler == "component_urls":
            return self.uploads.component_urls(actor, params["upload_id"], body)
        if handler == "cancel_upload":
            return self.uploads.cancel(actor, params["upload_id"], body)
        if handler == "finalize_upload":
            return self.uploads.finalize(actor, params["upload_id"], body)
        if handler == "list_scenes":
            return self.scenes.list(identity, query)
        if handler == "get_scene":
            return self.scenes.get(identity, params["scene_id"])
        if handler == "get_version":
            return self.scenes.get_version(identity, params["scene_id"], params["version"])
        if handler == "review":
            return self.publication.review(identity, params["scene_id"], params["version"], body)
        if handler == "audience_projection":
            return self.scenes.audience_projection(identity, params["scene_id"], params["version"])
        if handler == "publish":
            return self.publication.publish(identity, params["scene_id"], body)
        if handler == "withdraw":
            return self.publication.withdraw(identity, params["scene_id"], body)
        if handler == "create_grant":
            return self.viewing.grant(identity, params["scene_id"], body)
        if handler == "revoke_grant":
            return self.viewing.revoke(identity, params["scene_id"], params["grant_id"], query)
        if handler == "create_view_grant":
            return self.viewing.view_grant(identity, params["scene_id"], body)
        raise ApiError("not_found")
