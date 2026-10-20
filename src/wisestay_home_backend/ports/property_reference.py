"""Resvanta property-reference port (plan X.7, RSV-01/02).

Consumers never derive bookability from this port (Q14): ``bookable`` is
always ``False``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class PropertyReferenceFact:
    status: Literal["current", "not_found", "unavailable"]
    property_id: str
    property_type: Literal["REAL", "VIRTUAL"] | None   # None unless current
    record_version: int | None
    observed_at: str | None
    bookable: Literal[False] = False

    def __post_init__(self) -> None:
        if self.bookable is not False:
            raise ValueError("the property-reference port never carries bookability (Q14)")
        if self.status != "current" and self.property_type is not None:
            raise ValueError("property_type is None unless the fact is current")


class PropertyReferencePort(Protocol):
    def resolve(self, property_id: str) -> PropertyReferenceFact: ...


class CredentialSource(Protocol):
    def get(self) -> str: ...


class UnconfiguredPropertyReference:
    """Used when no Resvanta API root is configured: always ``unavailable``."""

    def resolve(self, property_id: str) -> PropertyReferenceFact:
        return PropertyReferenceFact("unavailable", property_id, None, None, None)
