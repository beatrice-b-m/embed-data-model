"""Pathology observations, diagnosis states, and attributed edges."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from embed_toolkit.clinical.associations import (
    AttributionStatus,
    ClinicalObjectReference,
)
from embed_toolkit.clinical.procedures import PathologySeverity
from embed_toolkit.core.provenance import BuildIssue, SourceLocator


class PathologyRecordKind(str, Enum):
    """Addressable pathology grains represented by attribution links."""

    OBSERVATION = "observation"
    DIAGNOSIS = "diagnosis"


@dataclass(frozen=True)
class PathologyObservation:
    """One descriptor occurrence in an ordered source slot."""

    descriptor: str
    source_slot: str
    source_ordinal: int
    source: SourceLocator

    def __post_init__(self) -> None:
        for attribute in ("descriptor", "source_slot"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        if (
            isinstance(self.source_ordinal, bool)
            or not isinstance(self.source_ordinal, int)
            or self.source_ordinal < 1
        ):
            raise ValueError("source_ordinal must be a positive integer")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "descriptor": self.descriptor,
            "source_slot": self.source_slot,
            "source_ordinal": self.source_ordinal,
            "source": self.source.to_dict(),
        }


@dataclass(frozen=True)
class PathologyDiagnosis:
    """One row-level diagnosis state with explicitly named documentation time."""

    source: SourceLocator
    diagnosis: Optional[str] = None
    result_category: Optional[str] = None
    malignant: Optional[bool] = None
    severity: Optional[PathologySeverity] = None
    raw_severity: Any = None
    report_documented_date: Optional[str] = None
    validation_issues: Tuple[BuildIssue, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.severity is not None:
            object.__setattr__(self, "severity", PathologySeverity(self.severity))
        object.__setattr__(self, "validation_issues", tuple(self.validation_issues))
        if any(issue.source != self.source for issue in self.validation_issues):
            raise ValueError("Pathology diagnosis issues must reference its source")
        represented_values = (
            self.diagnosis,
            self.result_category,
            self.malignant,
            self.severity,
            self.raw_severity,
            self.report_documented_date,
        )
        if all(value is None for value in represented_values):
            raise ValueError("PathologyDiagnosis requires represented diagnosis evidence")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "diagnosis": self.diagnosis,
            "result_category": self.result_category,
            "malignant": self.malignant,
            "severity": int(self.severity) if self.severity is not None else None,
            "raw_severity": _json_value(self.raw_severity),
            "report_documented_date": self.report_documented_date,
            "validation_issues": [
                issue.to_dict() for issue in self.validation_issues
            ],
        }


@dataclass(frozen=True)
class PathologyReference:
    """Non-recursive reference to one pathology diagnosis or observation."""

    kind: PathologyRecordKind
    source: SourceLocator
    source_slot: Optional[str] = None

    def __post_init__(self) -> None:
        kind = PathologyRecordKind(self.kind)
        object.__setattr__(self, "kind", kind)
        if kind is PathologyRecordKind.OBSERVATION:
            if (
                not isinstance(self.source_slot, str)
                or not self.source_slot.strip()
            ):
                raise ValueError("Observation references require source_slot")
        elif self.source_slot is not None:
            raise ValueError("Diagnosis references do not use source_slot")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "source": self.source.to_dict(),
            "source_slot": self.source_slot,
        }


@dataclass(frozen=True)
class PathologyAttributionLink:
    """Attributed edge from pathology evidence to a clinical object."""

    pathology: PathologyReference
    target: ClinicalObjectReference
    status: AttributionStatus
    source: SourceLocator

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", AttributionStatus(self.status))
        if self.source != self.pathology.source:
            raise ValueError("Pathology link provenance must match pathology source")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pathology": self.pathology.to_dict(),
            "target": self.target.to_dict(),
            "status": self.status.value,
            "source": self.source.to_dict(),
        }


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
