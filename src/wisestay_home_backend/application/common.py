"""Shared application helpers: clock, identifiers, record keys and loaders.

Application services are pure: every side effect goes through an injected
port (repository, object storage, property reference, commercial gate), the
clock is ``Callable[[], datetime]`` and identifiers come from ``IdGenerator``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import secrets
import threading
import time
from typing import Callable, Protocol

from wisestay_home_backend.domain.scene import (
    ApiError,
    AudienceProjection,
    CaptureSession,
    Scene,
    SceneVersion,
    UploadSession,
    ViewingGrant,
)
from wisestay_home_backend.ports.object_storage import ObjectStorage
from wisestay_home_backend.ports.repository import Item, Repository

Clock = Callable[[], datetime]

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_RFC3339_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value) -> datetime:
    """Parse an RFC 3339 UTC ``...Z`` timestamp (seconds precision) or raise ValueError."""
    if not isinstance(value, str) or not _RFC3339_Z.match(value):
        raise ValueError("timestamp must be RFC 3339 UTC with a Z suffix")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def epoch(value: datetime) -> int:
    return int(value.timestamp())


class IdGenerator(Protocol):
    def new(self, prefix: str) -> str: ...


class SecretsIdGenerator:
    """``<prefix>_<26 Crockford base32>``: 48-bit ms time + 80-bit ``secrets`` randomness.

    Monotonic within one process: a second id in the same millisecond
    increments the random part instead of drawing a new one.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._last_ms = -1
        self._last_rand = 0

    def new(self, prefix: str) -> str:
        with self._lock:
            ms = int(self._clock() * 1000)
            if ms <= self._last_ms:
                ms = self._last_ms
                rand = (self._last_rand + 1) & ((1 << 80) - 1)
            else:
                rand = secrets.randbits(80)
            self._last_ms, self._last_rand = ms, rand
        value = (ms << 80) | rand
        chars = []
        for _ in range(26):
            chars.append(_CROCKFORD[value & 31])
            value >>= 5
        return f"{prefix}_{''.join(reversed(chars))}"


# --- keys (DynamoDB table wisestay-dev-home-scanner) -------------------------------------

def capture_key(capture_id: str) -> tuple[str, str]:
    return f"CAPTURE#{capture_id}", "META"


def upload_key(upload_id: str) -> tuple[str, str]:
    return f"UPLOAD#{upload_id}", "META"


def scene_key(scene_id: str) -> tuple[str, str]:
    return f"SCENE#{scene_id}", "META"


def version_sk(version: str) -> str:
    return f"VERSION#{int(version):06d}"


def projection_sk(projection_id: str) -> str:
    return f"PROJECTION#{projection_id}"


def grant_sk(grant_id: str) -> str:
    return f"GRANT#{grant_id}"


def view_grant_sk(view_grant_id: str) -> str:
    return f"VIEWGRANT#{view_grant_id}"


def idempotency_key(user_id: str, route_id: str, key: str) -> tuple[str, str]:
    return f"IDEMP#{user_id}#{route_id}#{key}", "META"


# --- dependencies and loaders ----------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ServiceDeps:
    repository: Repository
    storage: ObjectStorage
    clock: Clock
    ids: IdGenerator


def not_found() -> ApiError:
    return ApiError("not_found")


def load_capture(repo: Repository, capture_id: str) -> tuple[CaptureSession, Item] | None:
    item = repo.get(*capture_key(capture_id)) if isinstance(capture_id, str) else None
    return (CaptureSession.from_data(item.data), item) if item else None


def load_upload(repo: Repository, upload_id: str) -> tuple[UploadSession, Item] | None:
    item = repo.get(*upload_key(upload_id)) if isinstance(upload_id, str) else None
    return (UploadSession.from_data(item.data), item) if item else None


def load_scene(repo: Repository, scene_id: str) -> tuple[Scene, Item] | None:
    item = repo.get(*scene_key(scene_id)) if isinstance(scene_id, str) else None
    return (Scene.from_data(item.data), item) if item else None


def load_version(repo: Repository, scene_id: str, version: str) -> SceneVersion | None:
    if not isinstance(version, str) or not version.isdigit() or version.startswith("0"):
        return None
    item = repo.get(f"SCENE#{scene_id}", version_sk(version))
    return SceneVersion.from_data(item.data) if item else None


def load_projection(repo: Repository, scene_id: str,
                    projection_id: str | None) -> AudienceProjection | None:
    if not projection_id:
        return None
    item = repo.get(f"SCENE#{scene_id}", projection_sk(projection_id))
    return AudienceProjection.from_data(item.data) if item else None


def load_grant(repo: Repository, scene_id: str, grant_id: str) -> tuple[ViewingGrant, Item] | None:
    if not isinstance(grant_id, str):
        return None
    item = repo.get(f"SCENE#{scene_id}", grant_sk(grant_id))
    return (ViewingGrant.from_data(item.data), item) if item else None


def grants_for(repo: Repository, user_id: str, scene_id: str) -> list[ViewingGrant]:
    grants: list[ViewingGrant] = []
    cursor = None
    while True:
        items, cursor = repo.query_gsi1(f"GRANTEE#{user_id}", f"SCENE#{scene_id}",
                                        limit=50, cursor=cursor)
        grants.extend(ViewingGrant.from_data(i.data) for i in items
                      if i.data.get("scene_id") == scene_id)
        if cursor is None:
            return grants


def active_grant(grants: list[ViewingGrant], now: datetime) -> ViewingGrant | None:
    for grant in grants:
        if grant.state.value == "active" and parse_iso(grant.expires_at) > now:
            return grant
    return None


def owned_scene(deps: ServiceDeps, user_id: str, scene_id: str) -> tuple[Scene, Item]:
    """The scene and its item if ``user_id`` owns it; 403 for a grantee, else 404."""
    loaded = load_scene(deps.repository, scene_id)
    if loaded is None:
        raise not_found()
    scene, item = loaded
    if scene.owner_user_id == user_id:
        return scene, item
    if active_grant(grants_for(deps.repository, user_id, scene_id), deps.clock()):
        raise ApiError("action_denied")
    raise not_found()


def check_expected_version(body: dict, current: int, *, field: str = "expected_version") -> int:
    expected = body.get(field)
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
        raise ApiError("invalid_request", f"{field} must be a positive integer")
    if expected != current:
        raise ApiError("version_conflict", current_version=current)
    return expected


def require_fields(body, *, required: frozenset[str] | set[str],
                   optional: frozenset[str] | set[str] = frozenset()) -> dict:
    if not isinstance(body, dict):
        raise ApiError("invalid_request", "a JSON object body is required")
    keys = set(body)
    if not set(required) <= keys or keys - set(required) - set(optional):
        raise ApiError("invalid_request", "unexpected or missing body fields")
    return body
