"""Object storage / presign port (plan X.9.1).

Key layout:

* ``staging/<upload_id>/<component_id>`` - browser PUT target;
* ``versions/<sha256 hex>`` - content-addressed, immutable, copied from
  staging only after validation;
* ``versions/envelopes/<asset_id>/<version>.json`` - service-written envelope;
* ``rejected/<upload_id>/<component_id>`` - quarantined bytes (30-day expiry).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    bytes: int
    checksum_sha256_b64: str | None


@dataclass(frozen=True, slots=True)
class PresignedPut:
    url: str
    headers: dict[str, str]
    expires_at: str


class StorageUnavailable(Exception):
    """Object storage could not be reached; mapped to 503 dependency_unavailable."""


class ObjectStorage(Protocol):
    def presign_put(self, key: str, *, sha256_b64: str, content_length: int,
                    expires_s: int = 900) -> PresignedPut: ...

    def presign_get(self, key: str, *, expires_s: int = 300) -> str: ...

    def head(self, key: str) -> StoredObject | None: ...  # ChecksumMode=ENABLED

    def read_range(self, key: str, start: int, end_inclusive: int) -> bytes: ...

    def copy(self, source_key: str, dest_key: str) -> None: ...

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None: ...

    def delete(self, key: str) -> None: ...


def staging_key(upload_id: str, component_id: str) -> str:
    return f"staging/{upload_id}/{component_id}"


def version_key(sha256_hex: str) -> str:
    return f"versions/{sha256_hex}"


def envelope_key(asset_id: str, version: str) -> str:
    return f"versions/envelopes/{asset_id}/{version}.json"


def rejected_key(upload_id: str, component_id: str) -> str:
    return f"rejected/{upload_id}/{component_id}"
