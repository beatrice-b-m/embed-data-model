"""Serializable evidence and warning containers for workflow audit trails."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional


JsonValue = Any
JsonMapping = Mapping[str, JsonValue]


class WarningSeverity(str, Enum):
    """Severity levels for non-fatal audit warnings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def serialize_value(value: Any) -> JsonValue:
    """Return a JSON-compatible value made from mappings, lists, and primitives."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, tuple):
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

    def to_dict(self) -> Dict[str, JsonValue]:
        return {
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
