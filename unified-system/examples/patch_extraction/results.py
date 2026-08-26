"""Result records owned by the patch-extraction recipe."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from embed_toolkit.imaging.roi_provenance import RoiLocator


JsonValue = Any
JsonMapping = Mapping[str, JsonValue]


class ResultStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class WarningSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _freeze(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return _freeze(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numeric values must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON mapping keys must be strings")
        return MappingProxyType({key: _freeze(value[key]) for key in sorted(value)})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError(f"Unsupported serializable value: {type(value).__name__}")


def _mapping(value: Optional[JsonMapping]) -> JsonMapping:
    frozen = _freeze(value or {})
    assert isinstance(frozen, Mapping)
    return frozen


def _serialize(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return _serialize(value.value)
    if isinstance(value, Mapping):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


@dataclass(frozen=True)
class Evidence:
    kind: str
    source: str
    payload: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.source.strip():
            raise ValueError("Evidence kind and source must be non-empty")
        object.__setattr__(self, "payload", _mapping(self.payload))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"kind": self.kind, "source": self.source, "payload": _serialize(self.payload)}


@dataclass(frozen=True)
class AuditWarning:
    code: str
    message: str
    severity: WarningSeverity = WarningSeverity.WARNING
    payload: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            raise ValueError("Warning code and message must be non-empty")
        object.__setattr__(self, "severity", WarningSeverity(self.severity))
        object.__setattr__(self, "payload", _mapping(self.payload))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "payload": _serialize(self.payload),
        }


@dataclass(frozen=True)
class PatchExtractionResult:
    status: ResultStatus
    image_id: str
    roi_locator: Optional[RoiLocator]
    roi_key: Optional[str]
    patch_id: str
    bbox: Sequence[float]
    shape: Sequence[int]
    patch_payload: JsonMapping
    evidence: Sequence[Evidence] = field(default_factory=tuple)
    warnings: Sequence[AuditWarning] = field(default_factory=tuple)
    metadata: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ResultStatus(self.status))
        if not self.image_id.strip() or not self.patch_id.strip():
            raise ValueError("Image and patch identities must be non-empty")
        if self.roi_locator is None and not self.roi_key:
            raise ValueError("A patch result requires roi_locator or roi_key")
        if self.roi_locator is not None and not isinstance(self.roi_locator, RoiLocator):
            raise TypeError("roi_locator must be a RoiLocator or None")
        bbox = tuple(self.bbox)
        shape = tuple(self.shape)
        if len(bbox) != 4 or any(not math.isfinite(float(value)) for value in bbox):
            raise ValueError("bbox must contain four finite values")
        if len(shape) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in shape
        ):
            raise ValueError("shape must contain two non-negative integers")
        object.__setattr__(self, "bbox", bbox)
        object.__setattr__(self, "shape", shape)
        object.__setattr__(self, "patch_payload", _mapping(self.patch_payload))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "metadata", _mapping(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "status": self.status.value,
            "image_id": self.image_id,
            "roi_locator": (
                self.roi_locator.to_dict() if self.roi_locator is not None else None
            ),
            "roi_key": self.roi_key,
            "patch_id": self.patch_id,
            "bbox": list(self.bbox),
            "shape": list(self.shape),
            "patch_payload": _serialize(self.patch_payload),
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": [item.to_dict() for item in self.warnings],
            "metadata": _serialize(self.metadata),
        }
