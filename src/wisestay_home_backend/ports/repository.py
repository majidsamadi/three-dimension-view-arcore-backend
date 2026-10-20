"""DynamoDB repository port (plan X.9.2).

``Put(expect="version")`` writes ``version = expected_version + 1`` and is
conditional on the stored version; ``Put(expect="absent")`` writes the item's
own version and requires that no live (non-expired) item exists.  ``transact``
is all-or-nothing for at most 25 operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

MAX_TRANSACT_OPS = 25


@dataclass(frozen=True, slots=True)
class Item:
    pk: str
    sk: str
    version: int
    data: dict
    gsi1pk: str | None = None
    gsi1sk: str | None = None
    ttl_epoch: int | None = None


class ConditionFailed(Exception):
    """A conditional write failed; mapped to version_conflict / already_* codes."""


class RepositoryUnavailable(Exception):
    """The table could not be reached; mapped to 503 dependency_unavailable."""


@dataclass(frozen=True, slots=True)
class Put:
    item: Item
    expect: Literal["absent", "version"]
    expected_version: int | None = None

    def __post_init__(self) -> None:
        if self.expect not in ("absent", "version"):
            raise ValueError("expect must be 'absent' or 'version'")
        if self.expect == "version" and not isinstance(self.expected_version, int):
            raise ValueError("expect='version' needs an integer expected_version")


@dataclass(frozen=True, slots=True)
class Check:
    pk: str
    sk: str
    expected_version: int


class Repository(Protocol):
    def get(self, pk: str, sk: str) -> Item | None: ...

    def transact(self, writes: list[Put | Check]) -> None: ...

    def query(self, pk: str, sk_prefix: str, *, limit: int,
              cursor: str | None) -> tuple[list[Item], str | None]: ...

    def query_gsi1(self, gsi1pk: str, sk_prefix: str, *, limit: int,
                   cursor: str | None) -> tuple[list[Item], str | None]: ...
