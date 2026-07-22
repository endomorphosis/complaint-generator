"""Typed capability contracts for optional formal-logic operations.

Python callers use these immutable contracts to gate execution without parsing
display strings.  JSON consumers receive the same state through ``as_dict`` at
the serialization boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional


class LogicCapabilityState(str, Enum):
    """Implementation state of a formal-logic operation."""

    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    IMPLEMENTED = "implemented"

    @property
    def available(self) -> bool:
        """Whether the operation can return a useful result."""

        return self is not LogicCapabilityState.UNAVAILABLE

    @property
    def degraded(self) -> bool:
        """Whether only a partial or fallback contract is available."""

        return self is LogicCapabilityState.DEGRADED

    @property
    def implemented(self) -> bool:
        """Whether the operation fulfils its complete formal contract."""

        return self is LogicCapabilityState.IMPLEMENTED


# Descriptive alias for consumers that call the enum a status.
LogicCapabilityStatus = LogicCapabilityState


class FormalLogicOperation(str, Enum):
    """Stable identifiers for public formal-logic operations."""

    TEXT_TO_FOL = "text_to_fol"
    LEGAL_TEXT_TO_DEONTIC = "legal_text_to_deontic"
    PROVE_CLAIM_ELEMENTS = "prove_claim_elements"
    CHECK_CONTRADICTIONS = "check_contradictions"
    RUN_HYBRID_REASONING = "run_hybrid_reasoning"

    @classmethod
    def coerce(cls, value: "FormalLogicOperation | str") -> "FormalLogicOperation":
        """Normalize an API-boundary value or raise a useful validation error."""

        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError as exc:
            supported = ", ".join(operation.value for operation in cls)
            raise ValueError(
                f"Unknown formal-logic operation {value!r}; expected one of: {supported}"
            ) from exc


class FormalLogicCapabilityError(RuntimeError):
    """Base error raised when a capability cannot satisfy a requested gate."""

    def __init__(self, capability: "FormalLogicCapability", *, required: str) -> None:
        self.capability = capability
        self.operation = capability.operation
        self.state = capability.state
        self.required = required
        reason = capability.reason or "no diagnostic was provided"
        super().__init__(
            f"Formal logic operation '{capability.operation.value}' requires {required}; "
            f"state is '{capability.state.value}': {reason}"
        )


class FormalLogicUnavailableError(FormalLogicCapabilityError):
    """Raised when an operation has no executable provider or fallback."""


class FormalLogicDegradedError(FormalLogicCapabilityError):
    """Raised when full formal validation is requested from a fallback."""


@dataclass(frozen=True)
class FormalLogicCapability:
    """Immutable capability description used to gate one operation.

    ``available`` includes degraded operations because they can provide a
    useful structural result.  ``implemented`` remains false so authoritative
    validation can explicitly reject partial behavior.
    """

    operation: FormalLogicOperation
    state: LogicCapabilityState
    provider: str
    module_path: str
    reason: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", FormalLogicOperation.coerce(self.operation))
        if not isinstance(self.state, LogicCapabilityState):
            object.__setattr__(self, "state", LogicCapabilityState(str(self.state)))
        object.__setattr__(self, "provider", str(self.provider or "").strip())
        object.__setattr__(self, "module_path", str(self.module_path or "").strip())
        normalized_reason = str(self.reason or "").strip() or None
        object.__setattr__(self, "reason", normalized_reason)
        object.__setattr__(self, "details", MappingProxyType(dict(self.details or {})))

        if self.state is not LogicCapabilityState.IMPLEMENTED and not normalized_reason:
            raise ValueError("Unavailable and degraded capabilities require a reason")

    @property
    def available(self) -> bool:
        return self.state.available

    @property
    def degraded(self) -> bool:
        return self.state is LogicCapabilityState.DEGRADED

    @property
    def implemented(self) -> bool:
        return self.state.implemented

    def require_available(self) -> "FormalLogicCapability":
        """Return self when usable; otherwise raise a deterministic error."""

        if not self.available:
            raise FormalLogicUnavailableError(self, required="an available capability")
        return self

    def require_implemented(self) -> "FormalLogicCapability":
        """Require authoritative implementation rather than fallback behavior."""

        if self.state is LogicCapabilityState.UNAVAILABLE:
            raise FormalLogicUnavailableError(self, required="an implemented capability")
        if self.state is LogicCapabilityState.DEGRADED:
            raise FormalLogicDegradedError(self, required="an implemented capability")
        return self

    def as_dict(self) -> dict[str, Any]:
        """Serialize the contract for JSON consumers."""

        return {
            "operation": self.operation.value,
            "status": self.state.value,
            "available": self.available,
            "degraded": self.degraded,
            "implemented": self.implemented,
            "provider": self.provider,
            "module_path": self.module_path,
            "reason": self.reason,
            "details": dict(self.details),
        }


def capability_state_from_payload(
    payload: Mapping[str, Any] | None,
) -> Optional[LogicCapabilityState]:
    """Read a serialized capability state without leaking wire strings.

    New producers embed the complete capability contract.  The compatibility
    paths below keep persisted pre-contract review payloads readable while all
    branching remains centralized here instead of being repeated by callers.
    ``None`` means the payload contains no recognizable capability signal.
    """

    value: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
    nested = value.get("capability")
    if isinstance(nested, Mapping):
        value = nested

    if value.get("implemented") is True or value.get("capability_implemented") is True:
        return LogicCapabilityState.IMPLEMENTED
    if value.get("degraded") is True or value.get("capability_degraded") is True:
        return LogicCapabilityState.DEGRADED
    if value.get("available") is False or value.get("capability_available") is False:
        return LogicCapabilityState.UNAVAILABLE

    raw_state = value.get("status") or value.get("implementation_status")
    if not raw_state and value is not payload and isinstance(payload, Mapping):
        raw_state = payload.get("implementation_status") or payload.get("status")
    normalized = str(raw_state or "").strip().lower()
    if not normalized:
        if isinstance(payload, Mapping) and payload.get("backend_available") is False:
            return LogicCapabilityState.UNAVAILABLE
        return None
    try:
        return LogicCapabilityState(normalized)
    except ValueError:
        # Compatibility for stored payloads created before the v1 contract.
        if normalized == "not_implemented":
            return (
                LogicCapabilityState.DEGRADED
                if not isinstance(payload, Mapping) or payload.get("backend_available") is not False
                else LogicCapabilityState.UNAVAILABLE
            )
        if normalized == "error":
            return LogicCapabilityState.DEGRADED
        if normalized in {"available", "success"}:
            return LogicCapabilityState.IMPLEMENTED
        return None


__all__ = [
    "FormalLogicCapability",
    "FormalLogicCapabilityError",
    "FormalLogicDegradedError",
    "FormalLogicOperation",
    "FormalLogicUnavailableError",
    "LogicCapabilityState",
    "LogicCapabilityStatus",
    "capability_state_from_payload",
]
