"""PROVISIONAL policy limits used by the Home Scanner service slice (HSB-02-06).

Values transcribe ``contracts/draft/v0.4/fixtures/common/policy-limits.v0.4.json``
(Q03/Q08/Q09/Q15, DELEGATED-PROVISIONAL).  A test pins them against the
fixture so they cannot drift silently.  The fixture itself is not shipped in
the Lambda package, so the values are constants here.
"""
from __future__ import annotations

APPLICATION_ID = "home-scanner"

COMPONENTS_PER_UPLOAD = 10
BYTES_PER_COMPONENT = 209_715_200
ENVELOPE_JSON_BYTES = 65_536
GLB_JSON_CHUNK_BYTES = 4 * 1024 * 1024
GLB_NODES = 10_000
GLB_MESHES = 2_000
GLB_ACCESSORS = 20_000
GLB_POSITION_VERTICES_TOTAL = 5_000_000
GLB_POSITION_TOLERANCE_M = 0.01
BOUNDS_EXTENT_M = {"home": 200.0, "shop": 500.0, "object": 20.0}

PRESIGNED_PUT_LIFETIME_S = 900
PRESIGNED_GET_LIFETIME_S = 300
VIEW_GRANT_LIFETIME_S = 300
UPLOAD_SESSION_EXPIRY_S = 7 * 24 * 3600
UPLOAD_RECORD_RETENTION_AFTER_EXPIRY_S = 30 * 24 * 3600
AUDIENCE_GRANT_MAX_LIFETIME_S = 90 * 24 * 3600
IDEMPOTENCY_RETENTION_S = 24 * 3600

MAX_REQUEST_BODY_BYTES = 2_000_000
LIST_LIMIT_DEFAULT = 20
LIST_LIMIT_MAX = 50
