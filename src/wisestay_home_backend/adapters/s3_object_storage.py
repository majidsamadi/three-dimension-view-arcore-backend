"""Live S3 object-storage adapter (plan X.9.1).

``boto3`` is imported lazily, only when no client is injected.  The presigned
PUT binds ``ChecksumSHA256`` and ``ContentLength`` so S3 itself rejects a body
whose digest or size differs from the admitted component.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from wisestay_home_backend.ports.object_storage import (
    PresignedPut,
    StorageUnavailable,
    StoredObject,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    return code in ("404", "NoSuchKey", "NotFound")


class S3ObjectStorage:
    def __init__(self, bucket: str, client=None, *,
                 clock: Callable[[], datetime] = _utc_now) -> None:
        if client is None:
            import boto3  # noqa: PLC0415 - lazy: never imported by tests

            client = boto3.client("s3")
        self._bucket = bucket
        self._client = client
        self._clock = clock

    def presign_put(self, key: str, *, sha256_b64: str, content_length: int,
                    expires_s: int = 900) -> PresignedPut:
        try:
            url = self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": key, "ChecksumSHA256": sha256_b64,
                        "ContentLength": content_length},
                ExpiresIn=expires_s,
            )
        except Exception as exc:
            raise StorageUnavailable("presign_put failed") from exc
        return PresignedPut(
            url=url,
            headers={"x-amz-checksum-sha256": sha256_b64, "content-length": str(content_length)},
            expires_at=_iso(self._clock() + timedelta(seconds=expires_s)),
        )

    def presign_get(self, key: str, *, expires_s: int = 300) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_s)
        except Exception as exc:
            raise StorageUnavailable("presign_get failed") from exc

    def head(self, key: str) -> StoredObject | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key, ChecksumMode="ENABLED")
        except Exception as exc:
            if _not_found(exc):
                return None
            raise StorageUnavailable("head_object failed") from exc
        return StoredObject(key, int(response["ContentLength"]), response.get("ChecksumSHA256"))

    def read_range(self, key: str, start: int, end_inclusive: int) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key,
                                               Range=f"bytes={start}-{end_inclusive}")
            return response["Body"].read()
        except Exception as exc:
            raise StorageUnavailable("get_object failed") from exc

    def copy(self, source_key: str, dest_key: str) -> None:
        try:
            self._client.copy_object(Bucket=self._bucket, Key=dest_key,
                                     CopySource={"Bucket": self._bucket, "Key": source_key},
                                     ChecksumAlgorithm="SHA256")
        except Exception as exc:
            raise StorageUnavailable("copy_object failed") from exc

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data,
                                    ContentType=content_type, ChecksumAlgorithm="SHA256")
        except Exception as exc:
            raise StorageUnavailable("put_object failed") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise StorageUnavailable("delete_object failed") from exc
