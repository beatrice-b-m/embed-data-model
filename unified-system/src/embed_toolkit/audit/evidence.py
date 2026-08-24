"""Serializable evidence and warning containers for workflow audit trails."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional


JsonValue = Any
JsonMapping = Mapping[str, JsonValue]


class WarningSeverity(str, Enum):
    """Severity levels for non-fatal audit warnings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def freeze_json_value(value: Any) -> JsonValue:
    """Validate and recursively freeze one strict JSON-compatible value."""

    if isinstance(value, Enum):
        return freeze_json_value(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numeric values must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON mapping keys must be strings")
        return MappingProxyType(
            {key: freeze_json_value(value[key]) for key in sorted(value)}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json_value(item) for item in value)
    raise TypeError(f"Unsupported serializable value: {type(value).__name__}")


def freeze_json_mapping(payload: Optional[JsonMapping]) -> JsonMapping:
    """Validate and recursively freeze a string-keyed JSON mapping."""

    if payload is None:
        return MappingProxyType({})
    if not isinstance(payload, Mapping):
        raise TypeError("JSON payload must be a mapping")
    frozen = freeze_json_value(payload)
    assert isinstance(frozen, Mapping)
    return frozen


def serialize_value(value: Any) -> JsonValue:
    """Return a fresh JSON-ready copy with deterministic mapping order."""

    if isinstance(value, Enum):
        return serialize_value(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numeric values must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON mapping keys must be strings")
        return {key: serialize_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    raise TypeError(f"Unsupported serializable value: {type(value).__name__}")


def serialize_mapping(payload: Optional[JsonMapping]) -> Dict[str, JsonValue]:
    """Serialize a payload mapping without attaching domain object semantics."""

    if payload is None:
        return {}
    return serialize_value(payload)


@dataclass(frozen=True)
class Evidence:
    """A source-neutral fact or measurement used by a workflow decision."""

    kind: str
    source: str
    payload: JsonMapping = field(default_factory=dict)
    confidence: Optional[float] = None
    note: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("kind", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(
                self.confidence, (int, float)
            ):
                raise TypeError("confidence must be numeric")
            confidence = float(self.confidence)
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence must be finite and in [0, 1]")
            object.__setattr__(self, "confidence", confidence)
        if self.note is not None and not isinstance(self.note, str):
            raise TypeError("note must be a string")
        object.__setattr__(self, "payload", freeze_json_mapping(self.payload))

    def to_dict(self) -> Dict[str, JsonValue]:
        data: Dict[str, JsonValue] = {
            "kind": self.kind,
            "source": self.source,
            "payload": serialize_mapping(self.payload),
        }
        if self.confidence is not None:
            data["confidence"] = self.confidence
        if self.note is not None:
            data["note"] = self.note
        return data


@dataclass(frozen=True)
class AuditWarning:
    """A structured warning that preserves machine-readable context."""

    code: str
    message: str
    severity: WarningSeverity = WarningSeverity.WARNING
    payload: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("code", "message"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        object.__setattr__(self, "severity", WarningSeverity(self.severity))
        object.__setattr__(self, "payload", freeze_json_mapping(self.payload))

    def to_dict(self) -> Dict[str, JsonValue]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "payload": serialize_mapping(self.payload),
        }


@dataclass(frozen=True)
class AuditTrail:
    """Reusable evidence and warning bundle shared by result records."""

    evidence: List[Evidence] = field(default_factory=list)
    warnings: List[AuditWarning] = field(default_factory=list)

    def __post_init__(self) -> None:
        evidence = tuple(self.evidence)
        warnings = tuple(self.warnings)
        if any(not isinstance(item, Evidence) for item in evidence):
            raise TypeError("evidence must contain only Evidence values")
        if any(not isinstance(item, AuditWarning) for item in warnings):
            raise TypeError("warnings must contain only AuditWarning values")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "warnings", warnings)

    def to_dict(self) -> Dict[str, JsonValue]:
        return {
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
