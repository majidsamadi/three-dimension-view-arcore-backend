"""CommercialGate port and its not-configured implementation (plan X.9.3, Q10).

Q10 is DELEGATED-PROVISIONAL: no commercial policy exists in wave 2.  View and
place are allowed with the explicit outcome ``allowed_no_commercial_policy``;
export is always denied.  The gate refuses to run in production so the no-op
can never silently become a production policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Literal, Protocol

from wisestay_home_backend.domain.asset_reference import ActorContext

LOGGER = logging.getLogger("wisestay_home_backend.commercial_gate")


class ConfigurationError(RuntimeError):
    """The service composition is not allowed in this environment."""


@dataclass(frozen=True, slots=True)
class GateOutcome:
    outcome: Literal["allowed_no_commercial_policy", "denied"]
    reason: str | None


class CommercialGate(Protocol):
    def check(self, action: Literal["view", "place", "export"], actor: ActorContext,
              resource_ref: str) -> GateOutcome: ...


class NotConfiguredCommercialGate:
    def __init__(self, environment: str) -> None:
        if environment == "production":
            raise ConfigurationError("NotConfiguredCommercialGate must not run in production (Q10)")
        self._environment = environment

    def check(self, action: str, actor: ActorContext, resource_ref: str) -> GateOutcome:
        if action in ("view", "place"):
            outcome = GateOutcome("allowed_no_commercial_policy", None)
        else:
            outcome = GateOutcome("denied", "export_not_available")
        # No imagery, coordinates or tokens are ever logged.
        LOGGER.info(json.dumps({"event": "commercial_gate", "action": action,
                                "outcome": outcome.outcome, "reason": outcome.reason,
                                "resource_ref": resource_ref}, sort_keys=True))
        return outcome
