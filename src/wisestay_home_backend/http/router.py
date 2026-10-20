"""Route table H01-H16 (plan X.2.2).  Paths are relative to ``/api/v1``.

There is no ``/home-scenes/{id}/jobs`` route: HSB-04.2-04.4 cloud jobs are
DISABLED by Q02 and the path answers 404 like any unknown route.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

API_PREFIX = "/api/v1"


@dataclass(frozen=True, slots=True)
class Route:
    route_id: str
    method: str
    path: str
    idempotent: bool
    handler: str
    status: int
    pattern: re.Pattern

    def match(self, method: str, path: str) -> dict | None:
        if method != self.method:
            return None
        found = self.pattern.match(path)
        return found.groupdict() if found else None


def _route(route_id: str, method: str, path: str, idempotent: bool, handler: str,
           status: int) -> Route:
    regex = "^" + re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[A-Za-z0-9_-]{1,128})", re.escape(path)) + "$"
    return Route(route_id, method, path, idempotent, handler, status, re.compile(regex))


ROUTES: tuple[Route, ...] = (
    _route("H01", "POST", "/home-captures", True, "create_capture", 201),
    _route("H02", "POST", "/home-captures/{capture_id}/uploads", True, "create_upload", 201),
    _route("H03", "GET", "/uploads/{upload_id}", False, "get_upload", 200),
    _route("H04", "POST", "/uploads/{upload_id}/component-urls", True, "component_urls", 200),
    _route("H05", "POST", "/uploads/{upload_id}/cancel", True, "cancel_upload", 200),
    _route("H06", "POST", "/uploads/{upload_id}/finalize", True, "finalize_upload", 201),
    _route("H07", "GET", "/home-scenes", False, "list_scenes", 200),
    _route("H08", "GET", "/home-scenes/{scene_id}", False, "get_scene", 200),
    _route("H09", "GET", "/home-scenes/{scene_id}/versions/{version}", False, "get_version", 200),
    _route("H10", "POST", "/home-scenes/{scene_id}/versions/{version}/review", True, "review", 200),
    _route("H11", "GET", "/home-scenes/{scene_id}/versions/{version}/audience-projection", False,
           "audience_projection", 200),
    _route("H12", "POST", "/home-scenes/{scene_id}/publication", True, "publish", 200),
    _route("H13", "POST", "/home-scenes/{scene_id}/withdrawal", True, "withdraw", 200),
    _route("H14", "POST", "/home-scenes/{scene_id}/grants", True, "create_grant", 201),
    _route("H15", "DELETE", "/home-scenes/{scene_id}/grants/{grant_id}", False, "revoke_grant", 200),
    _route("H16", "POST", "/home-scenes/{scene_id}/view-grants", True, "create_view_grant", 201),
)


def match(method: str, full_path: str) -> tuple[Route, dict] | None:
    if not full_path.startswith(API_PREFIX + "/"):
        return None
    path = full_path[len(API_PREFIX):]
    for route in ROUTES:
        params = route.match(method, path)
        if params is not None:
            return route, params
    return None
