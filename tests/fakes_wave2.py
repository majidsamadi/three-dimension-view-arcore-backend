"""Synthetic in-memory fakes for the wave-2 service slice (no I/O, no AWS).

* ``InMemoryRepository`` enforces the same conditions as the DynamoDB adapter
  (absent / version / check; all-or-nothing; TTL-expired items are absent).
* ``InMemoryObjectStorage`` simulates S3 presigned PUTs: ``client_upload``
  refuses a body whose sha256 differs from the claimed (presigned) checksum,
  the way S3 would; ``tamper`` corrupts stored bytes behind the checksum.
* ``FakeIdentityVerifier``, ``FakePropertyReference``, ``FixedClock`` and
  ``SequentialIds`` produce the synthetic ids used by the v0.4 fixtures.
"""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from typing import Callable

from wisestay_home_backend.domain.asset_reference import IdentityRequired
from wisestay_home_backend.entrypoints.composition import Composition, build_for_tests
from wisestay_home_backend.http.handlers import Request, Response
from wisestay_home_backend.ports.identity import IdentityUnavailable, VerifiedIdentity
from wisestay_home_backend.ports.object_storage import PresignedPut, StorageUnavailable, StoredObject
from wisestay_home_backend.ports.property_reference import PropertyReferenceFact
from wisestay_home_backend.ports.repository import (
    MAX_TRANSACT_OPS,
    Check,
    ConditionFailed,
    Item,
    Put,
    RepositoryUnavailable,
)

T0 = datetime(2026, 10, 20, tzinfo=timezone.utc)
BUCKET = "synthetic-home-scanner-assets"
TOKENS = {"Bearer token-A": "USER-A", "Bearer token-B": "USER-B", "Bearer token-C": "USER-C"}


class FixedClock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


class SequentialIds:
    """``<prefix>_01HZYSYNTH<16 digits>``: valid Crockford ids matching the fixtures."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def new(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}_01HZYSYNTH{self._counters[prefix]:016d}"


class FakeIdentityVerifier:
    def __init__(self, tokens: dict[str, str] | None = None, *, unavailable: bool = False) -> None:
        self._tokens = dict(TOKENS if tokens is None else tokens)
        self.unavailable = unavailable

    def verify(self, authorization: str | None) -> VerifiedIdentity:
        if self.unavailable:
            raise IdentityUnavailable("synthetic identity outage")
        user = self._tokens.get(authorization or "")
        if user is None:
            raise IdentityRequired("unknown synthetic token")
        return VerifiedIdentity(user, "home-scanner", "synthetic-client", 1_900_000_000)


class FakePropertyReference:
    DEFAULT = {"PROP-VIRTUAL-1": ("VIRTUAL", 3), "PROP-REAL-UNLISTED-1": ("REAL", 2)}

    def __init__(self, properties: dict | None = None, *, unavailable: frozenset[str] = frozenset()) -> None:
        self._properties = dict(self.DEFAULT if properties is None else properties)
        self._unavailable = set(unavailable)
        self.calls: list[str] = []

    def resolve(self, property_id: str) -> PropertyReferenceFact:
        self.calls.append(property_id)
        if property_id in self._unavailable:
            return PropertyReferenceFact("unavailable", property_id, None, None, None)
        if property_id not in self._properties:
            return PropertyReferenceFact("not_found", property_id, None, None, None)
        kind, version = self._properties[property_id]
        return PropertyReferenceFact("current", property_id, kind, version, "2026-10-20T00:00:00Z")


class InMemoryRepository:
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self._items: dict[tuple[str, str], Item] = {}
        self._fail_next = False
        self.before_transact: Callable[[list], None] | None = None
        self.transactions: list[list] = []

    def fail_next(self) -> None:
        self._fail_next = True

    def _maybe_fail(self) -> None:
        if self._fail_next:
            self._fail_next = False
            raise RepositoryUnavailable("synthetic repository outage")

    def _live(self, key: tuple[str, str]) -> Item | None:
        item = self._items.get(key)
        if item is not None and item.ttl_epoch is not None and self._clock().timestamp() >= item.ttl_epoch:
            return None
        return item

    @staticmethod
    def _copy(item: Item) -> Item:
        return Item(item.pk, item.sk, item.version, copy.deepcopy(item.data), item.gsi1pk,
                    item.gsi1sk, item.ttl_epoch)

    def get(self, pk: str, sk: str) -> Item | None:
        self._maybe_fail()
        item = self._live((pk, sk))
        return self._copy(item) if item else None

    def transact(self, writes: list) -> None:
        self._maybe_fail()
        if self.before_transact is not None:
            hook, self.before_transact = self.before_transact, None
            hook(writes)
        if not 1 <= len(writes) <= MAX_TRANSACT_OPS:
            raise ValueError("transact takes 1-25 operations")
        keys = [(w.item.pk, w.item.sk) if isinstance(w, Put) else (w.pk, w.sk) for w in writes]
        if len(set(keys)) != len(keys):
            raise ValueError("one operation per item per transaction")
        for write, key in zip(writes, keys):
            current = self._live(key)
            if isinstance(write, Put) and write.expect == "absent":
                if current is not None:
                    raise ConditionFailed(f"{key} exists")
            else:
                expected = write.expected_version
                if current is None or current.version != expected:
                    raise ConditionFailed(f"{key} version is not {expected}")
        json.dumps([w.item.data for w in writes if isinstance(w, Put)])  # JSON-compatible only
        for write, key in zip(writes, keys):
            if isinstance(write, Check):
                continue
            version = write.item.version if write.expect == "absent" else write.expected_version + 1
            item = write.item
            self._items[key] = Item(item.pk, item.sk, version, copy.deepcopy(item.data),
                                    item.gsi1pk, item.gsi1sk, item.ttl_epoch)
        self.transactions.append(list(writes))

    def _page(self, items: list[Item], limit: int, cursor: str | None, sort_key) -> tuple[list[Item], str | None]:
        items = sorted(items, key=sort_key)
        start = 0
        if cursor is not None:
            marker = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            start = next((i + 1 for i, it in enumerate(items) if list(sort_key(it)) == marker), len(items))
        page = items[start:start + limit]
        more = start + limit < len(items)
        next_cursor = (base64.urlsafe_b64encode(json.dumps(list(sort_key(page[-1]))).encode()).decode()
                       if more and page else None)
        return [self._copy(i) for i in page], next_cursor

    def query(self, pk: str, sk_prefix: str, *, limit: int, cursor: str | None):
        self._maybe_fail()
        rows = [i for k, i in self._items.items() if k[0] == pk and k[1].startswith(sk_prefix)
                and self._live(k)]
        return self._page(rows, limit, cursor, lambda i: (i.sk,))

    def query_gsi1(self, gsi1pk: str, sk_prefix: str, *, limit: int, cursor: str | None):
        self._maybe_fail()
        rows = [i for k, i in self._items.items() if i.gsi1pk == gsi1pk
                and (i.gsi1sk or "").startswith(sk_prefix) and self._live(k)]
        return self._page(rows, limit, cursor, lambda i: (i.gsi1sk or "", i.pk, i.sk))

    def raw(self, pk: str, sk: str) -> Item | None:
        return self._items.get((pk, sk))

    def keys(self) -> list[tuple[str, str]]:
        return sorted(self._items)


class ChecksumRejected(Exception):
    """The simulated S3 PUT was refused (checksum or length differs from the presign)."""


class InMemoryObjectStorage:
    def __init__(self, clock: Callable[[], datetime], bucket: str = BUCKET) -> None:
        self._clock = clock
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str | None, str]] = {}  # key -> (data, checksum, type)
        self.presigned: dict[str, tuple[str, int]] = {}
        self._fail: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def fail_next(self, op: str) -> None:
        self._fail.add(op)

    def _op(self, op: str, key: str) -> None:
        self.calls.append((op, key))
        if op in self._fail:
            self._fail.discard(op)
            raise StorageUnavailable(f"synthetic {op} outage")

    def _url(self, key: str, expires_s: int) -> tuple[str, int]:
        exp = int(self._clock().timestamp()) + expires_s
        sig = hmac.new(b"synthetic", f"{key}:{exp}".encode(), hashlib.sha256).hexdigest()[:16]
        return f"fake-s3://{self.bucket}/{key}?exp={exp}&sig={sig}", exp

    def presign_put(self, key: str, *, sha256_b64: str, content_length: int,
                    expires_s: int = 900) -> PresignedPut:
        self._op("presign_put", key)
        url, exp = self._url(key, expires_s)
        self.presigned[key] = (sha256_b64, content_length)
        return PresignedPut(url, {"x-amz-checksum-sha256": sha256_b64,
                                  "content-length": str(content_length)},
                            datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def presign_get(self, key: str, *, expires_s: int = 300) -> str:
        self._op("presign_get", key)
        return self._url(key, expires_s)[0]

    def client_upload(self, key: str, data: bytes, claimed_sha256_b64: str | None = None) -> None:
        """Simulate the browser PUT against a presigned URL."""
        actual = base64.b64encode(hashlib.sha256(data).digest()).decode()
        signed = self.presigned.get(key)
        claimed = claimed_sha256_b64 if claimed_sha256_b64 is not None else (signed or (actual,))[0]
        if claimed != actual:
            raise ChecksumRejected("x-amz-checksum-sha256 does not match the body")
        if signed is not None and (signed[0] != claimed or signed[1] != len(data)):
            raise ChecksumRejected("body does not match the presigned checksum/length")
        self.objects[key] = (bytes(data), actual, "application/octet-stream")

    def place(self, key: str, data: bytes, checksum_b64: str | None) -> None:
        """Store bytes with an arbitrary recorded checksum (simulates out-of-band writes)."""
        self.objects[key] = (bytes(data), checksum_b64, "application/octet-stream")

    def tamper(self, key: str, data: bytes) -> None:
        _, checksum, content_type = self.objects[key]
        self.objects[key] = (bytes(data), checksum, content_type)

    def head(self, key: str) -> StoredObject | None:
        self._op("head", key)
        found = self.objects.get(key)
        return StoredObject(key, len(found[0]), found[1]) if found else None

    def read_range(self, key: str, start: int, end_inclusive: int) -> bytes:
        self._op("read_range", key)
        if key not in self.objects:
            raise StorageUnavailable("no such key")
        return self.objects[key][0][start:end_inclusive + 1]

    def copy(self, source_key: str, dest_key: str) -> None:
        self._op("copy", dest_key)
        self.objects[dest_key] = self.objects[source_key]

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        self._op("put_bytes", key)
        self.objects[key] = (bytes(data), base64.b64encode(hashlib.sha256(data).digest()).decode(),
                             content_type)

    def delete(self, key: str) -> None:
        self._op("delete", key)
        self.objects.pop(key, None)


class Harness:
    """A composed service plus its fakes and small request helpers."""

    def __init__(self, *, properties: FakePropertyReference | None = None,
                 environment: str = "test") -> None:
        self.clock = FixedClock()
        self.ids = SequentialIds()
        self.repository = InMemoryRepository(self.clock)
        self.storage = InMemoryObjectStorage(self.clock)
        self.identity = FakeIdentityVerifier()
        self.properties = properties or FakePropertyReference()
        self.composition: Composition = build_for_tests(
            repository=self.repository, storage=self.storage, identity=self.identity,
            properties=self.properties, clock=self.clock, ids=self.ids, environment=environment)
        self._key = 0

    def next_key(self) -> str:
        self._key += 1
        return f"idem-test-{self._key:06d}"

    def call(self, method: str, path: str, body=None, *, token: str = "token-A",
             key: str | None = "auto", query: dict | None = None,
             headers: dict | None = None) -> Response:
        hdrs = {"Content-Type": "application/json"}
        if token is not None:
            hdrs["Authorization"] = f"Bearer {token}"
        if key == "auto":
            key = self.next_key() if method == "POST" else None
        if key is not None:
            hdrs["Idempotency-Key"] = key
        hdrs.update(headers or {})
        raw = None if body is None else json.dumps(body).encode()
        return self.composition.api.dispatch(Request(method, "/api/v1" + path, hdrs,
                                                     {k: str(v) for k, v in (query or {}).items()},
                                                     raw, "req-test"))
