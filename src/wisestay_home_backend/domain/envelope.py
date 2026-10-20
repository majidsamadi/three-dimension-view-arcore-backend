"""``wisestay.asset-envelope.v1`` and GLB structure validation (HSB-03.1, Q05).

Both validators return reason codes, never raise for bad input:

* envelope codes are the S0 draft codes listed in
  ``asset-envelope.v1.schema.json`` (``x-wisestay-admission``);
* GLB codes are the X.2.1 table.  The GLB validator reads only the 12-byte
  header, the 8-byte chunk header and the JSON chunk through an injected
  ``read_range(start, end_inclusive)`` callable.

Any failure puts a version in ``quarantined`` (never a success state).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from typing import Callable, Iterable

from wisestay_home_backend.domain import policy

SCHEMA = "wisestay.asset-envelope.v1"
TOP_LEVEL_KEYS = frozenset({
    "schema", "asset_id", "kind", "version", "producer", "components", "frame", "bounds_m",
    "scale_claim", "unobserved_regions", "provenance", "audience_projection_id",
})
KINDS = frozenset({"home", "object", "shop"})
ROLES = frozenset({"geometry", "review_model", "diagnostics"})
SCALE_CLAIMS = frozenset({
    "unknown", "estimated", "seller-declared", "reference-supported", "independently-verified",
})
CONTENT_CLASSES = frozenset({"synthetic", "permitted-unoccupied-reference"})
PRODUCER_APPS = frozenset({"home-scanner", "object-scanner"})
FRAME = {"handedness": "right", "up": "+Y", "units": "metre"}
MEDIA_TYPE = "model/gltf-binary"

_COMPONENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ASSET_ID = re.compile(r"^(scn|obj)_[0-9A-HJKMNP-TV-Z]{26}$")
_VERSION = re.compile(r"^[1-9][0-9]*$")

_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A


def canonical_json(value) -> bytes:
    """Deterministic UTF-8 JSON used for service-written envelopes and digests."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _bounds_ok(bounds) -> bool:
    if not isinstance(bounds, dict) or set(bounds) != {"min", "max"}:
        return False
    lo, hi = bounds["min"], bounds["max"]
    if not (isinstance(lo, list) and isinstance(hi, list) and len(lo) == 3 and len(hi) == 3):
        return False
    if not all(_is_number(v) for v in lo + hi):
        return False
    return all(a <= b for a, b in zip(lo, hi))


def bounds_extent(bounds: dict) -> float:
    return max(b - a for a, b in zip(bounds["min"], bounds["max"]))


def _add(reasons: list[str], code: str) -> None:
    if code not in reasons:
        reasons.append(code)


def validate_envelope(envelope, *, draft: bool = False, expected_kind: str | None = None,
                      expected_asset_id: str | None = None) -> list[str]:
    """Return the envelope reason codes (empty list when valid).

    ``draft=True`` is the H02 admission form: ``version`` and
    ``audience_projection_id`` must be null and ``asset_id`` may be null or the
    existing asset id.  Otherwise the stored form is checked: ``asset_id`` and
    ``version`` are required.
    """
    reasons: list[str] = []
    if not isinstance(envelope, dict):
        return ["envelope_field_invalid"]
    try:
        if len(canonical_json(envelope)) > policy.ENVELOPE_JSON_BYTES:
            _add(reasons, "envelope_too_large")
    except (TypeError, ValueError):
        return ["envelope_field_invalid"]
    if set(envelope) - TOP_LEVEL_KEYS:
        _add(reasons, "envelope_unknown_key")
    if envelope.get("schema") != SCHEMA:
        _add(reasons, "envelope_schema_unsupported")
    missing = TOP_LEVEL_KEYS - set(envelope)
    if missing:
        _add(reasons, "envelope_field_invalid")

    kind = envelope.get("kind")
    if kind not in KINDS:
        _add(reasons, "envelope_field_invalid")
    elif expected_kind is not None and kind != expected_kind:
        _add(reasons, "envelope_kind_mismatch")

    asset_id = envelope.get("asset_id")
    if draft:
        if asset_id is not None and asset_id != expected_asset_id:
            _add(reasons, "envelope_asset_mismatch")
        if envelope.get("version") is not None or envelope.get("audience_projection_id") is not None:
            _add(reasons, "envelope_field_invalid")
    else:
        if not isinstance(asset_id, str) or not _ASSET_ID.match(asset_id):
            _add(reasons, "envelope_field_invalid")
        elif expected_asset_id is not None and asset_id != expected_asset_id:
            _add(reasons, "envelope_asset_mismatch")
        version = envelope.get("version")
        if not isinstance(version, str) or not _VERSION.match(version):
            _add(reasons, "envelope_field_invalid")
        projection = envelope.get("audience_projection_id")
        if projection is not None and not isinstance(projection, str):
            _add(reasons, "envelope_field_invalid")

    producer = envelope.get("producer")
    if not (isinstance(producer, dict)
            and set(producer) == {"engine", "engine_version", "app"}
            and producer.get("engine") == "three-dimension-view-arcore"
            and isinstance(producer.get("engine_version"), str)
            and producer.get("app") in PRODUCER_APPS):
        _add(reasons, "envelope_field_invalid")

    for code in component_reasons(envelope.get("components")):
        _add(reasons, code)

    if envelope.get("frame") != FRAME:
        _add(reasons, "envelope_frame_invalid")

    bounds = envelope.get("bounds_m")
    if not _bounds_ok(bounds):
        _add(reasons, "envelope_bounds_invalid")
    elif kind in policy.BOUNDS_EXTENT_M and bounds_extent(bounds) > policy.BOUNDS_EXTENT_M[kind]:
        _add(reasons, "bounds_extent_limit")

    if envelope.get("scale_claim") not in SCALE_CLAIMS:
        _add(reasons, "envelope_field_invalid")

    regions = envelope.get("unobserved_regions")
    if not isinstance(regions, list):
        _add(reasons, "envelope_field_invalid")
    else:
        for region in regions:
            if not (isinstance(region, dict) and set(region) == {"region_id", "bounds_m", "label"}
                    and isinstance(region.get("region_id"), str)
                    and isinstance(region.get("label"), str)):
                _add(reasons, "envelope_field_invalid")
            elif not _bounds_ok(region["bounds_m"]):
                _add(reasons, "envelope_bounds_invalid")

    provenance = envelope.get("provenance")
    if not (isinstance(provenance, dict) and set(provenance) == {
            "capture_mode", "cloud_refinement", "content_class", "permission_record_id"}):
        _add(reasons, "envelope_field_invalid")
    else:
        if provenance["capture_mode"] != "local":
            _add(reasons, "envelope_capture_not_local")
        if provenance["cloud_refinement"] is not False:
            _add(reasons, "envelope_cloud_refinement_enabled")
        if provenance["content_class"] not in CONTENT_CLASSES:
            _add(reasons, "envelope_field_invalid")
        permission = provenance["permission_record_id"]
        if permission is not None and (not isinstance(permission, str) or not permission.strip()):
            _add(reasons, "envelope_field_invalid")
    return reasons


def component_reasons(components) -> list[str]:
    reasons: list[str] = []
    if not isinstance(components, list) or not 1 <= len(components) <= policy.COMPONENTS_PER_UPLOAD:
        return ["envelope_component_invalid"]
    seen: set[str] = set()
    for item in components:
        if not isinstance(item, dict) or set(item) != {"component_id", "role", "media_type", "sha256", "bytes"}:
            _add(reasons, "envelope_component_invalid")
            continue
        if item["role"] == "raw_capture":
            _add(reasons, "raw_capture_not_accepted")
        elif item["role"] not in ROLES:
            _add(reasons, "envelope_component_invalid")
        cid = item["component_id"]
        size = item["bytes"]
        if (not isinstance(cid, str) or not _COMPONENT_ID.match(cid) or cid in seen
                or item["media_type"] != MEDIA_TYPE
                or not isinstance(item["sha256"], str) or not _SHA256.match(item["sha256"])
                or not isinstance(size, int) or isinstance(size, bool)
                or not 1 <= size <= policy.BYTES_PER_COMPONENT):
            _add(reasons, "envelope_component_invalid")
        if isinstance(cid, str):
            seen.add(cid)
    return reasons


# --- GLB -------------------------------------------------------------------------------

def _walk_uris(value) -> Iterable[bool]:
    for item in value if isinstance(value, list) else ():
        yield isinstance(item, dict) and "uri" in item


def validate_glb_structure(read_range: Callable[[int, int], bytes], size: int, *,
                           envelope_bounds: dict | None, kind: str | None = None) -> list[str]:
    """Return GLB / glTF reason codes for one stored ``model/gltf-binary`` object."""
    reasons: list[str] = []
    if size < 20:
        return ["glb_length_mismatch"]
    header = read_range(0, 19)
    if len(header) != 20:
        return ["glb_length_mismatch"]
    magic, container_version, declared = struct.unpack_from("<III", header, 0)
    chunk_length, chunk_type = struct.unpack_from("<II", header, 12)
    if magic != _GLB_MAGIC:
        return ["glb_bad_magic"]
    if container_version != 2:
        return ["glb_bad_version"]
    if declared != size:
        return ["glb_length_mismatch"]
    if chunk_type != _CHUNK_JSON:
        return ["glb_first_chunk_not_json"]
    if chunk_length > policy.GLB_JSON_CHUNK_BYTES:
        return ["glb_json_too_large"]
    if chunk_length == 0 or 20 + chunk_length > size:
        return ["glb_length_mismatch"]
    raw = read_range(20, 20 + chunk_length - 1)
    try:
        gltf = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ["glb_first_chunk_not_json"]
    if not isinstance(gltf, dict):
        return ["glb_first_chunk_not_json"]

    asset = gltf.get("asset")
    if not isinstance(asset, dict) or asset.get("version") != "2.0":
        _add(reasons, "gltf_bad_asset_version")
    if gltf.get("extensionsRequired"):
        _add(reasons, "gltf_extension_required")
    if any(_walk_uris(gltf.get("buffers"))) or any(_walk_uris(gltf.get("images"))):
        _add(reasons, "gltf_external_uri")

    nodes, meshes, accessors = (gltf.get(k, []) for k in ("nodes", "meshes", "accessors"))
    if not all(isinstance(v, list) for v in (nodes, meshes, accessors)):
        _add(reasons, "gltf_count_limit")
        return reasons
    if (len(nodes) > policy.GLB_NODES or len(meshes) > policy.GLB_MESHES
            or len(accessors) > policy.GLB_ACCESSORS):
        _add(reasons, "gltf_count_limit")
        return reasons

    position_indices: set[int] = set()
    for mesh in meshes:
        for primitive in (mesh.get("primitives", []) if isinstance(mesh, dict) else []):
            attributes = primitive.get("attributes", {}) if isinstance(primitive, dict) else {}
            index = attributes.get("POSITION") if isinstance(attributes, dict) else None
            if isinstance(index, int) and not isinstance(index, bool):
                position_indices.add(index)

    vertices = 0
    lows: list[list[float]] = []
    highs: list[list[float]] = []
    for index in sorted(position_indices):
        accessor = accessors[index] if 0 <= index < len(accessors) else None
        if not isinstance(accessor, dict):
            _add(reasons, "gltf_position_bounds_missing")
            continue
        count = accessor.get("count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            vertices += count
        lo, hi = accessor.get("min"), accessor.get("max")
        if not (isinstance(lo, list) and isinstance(hi, list) and len(lo) == 3 and len(hi) == 3
                and all(_is_number(v) for v in lo + hi)):
            _add(reasons, "gltf_position_bounds_missing")
            continue
        lows.append(lo)
        highs.append(hi)
    if vertices > policy.GLB_POSITION_VERTICES_TOTAL:
        _add(reasons, "gltf_vertex_limit")

    if envelope_bounds is not None and _bounds_ok(envelope_bounds):
        tol = policy.GLB_POSITION_TOLERANCE_M
        for lo, hi in zip(lows, highs):
            if any(lo[a] < envelope_bounds["min"][a] - tol or hi[a] > envelope_bounds["max"][a] + tol
                   for a in range(3)):
                _add(reasons, "bounds_outside_envelope")
                break
        if kind in policy.BOUNDS_EXTENT_M and bounds_extent(envelope_bounds) > policy.BOUNDS_EXTENT_M[kind]:
            _add(reasons, "bounds_extent_limit")
    return reasons


# --- capabilities (HSB-03.4) -----------------------------------------------------------

MEASUREMENT_CLAIMS = frozenset({"reference-supported", "independently-verified"})


def capabilities(envelope: dict, *, validated: bool) -> dict:
    has_geometry = any(c.get("role") == "geometry" for c in envelope.get("components", []))
    claim = envelope.get("scale_claim")
    return {
        "visual_tour": bool(validated and has_geometry),
        "measurement": claim in MEASUREMENT_CLAIMS,
        "placement": claim in SCALE_CLAIMS and claim != "unknown",
        "missing_regions": list(envelope.get("unobserved_regions", [])),
    }
