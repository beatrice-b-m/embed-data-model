"""Clinical finding objects independent of source-code adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from embed_toolkit.clinical.interpretations import ImagingInterpretation
from embed_toolkit.clinical.procedures import _to_plain
from embed_toolkit.core.anatomy import AnatomicalPosition
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import SourceLocator
from embed_toolkit.core.source import SourceRef


class FindingRecordType(str, Enum):
    """Governed meaning of EMBED finding-number records."""

    FINDING = "finding"
    SYNTHETIC_CONTRALATERAL_NEGATIVE = "synthetic_contralateral_negative"


@dataclass(frozen=True)
class FindingNormalizationEvidence:
    """Source-scoped evidence supporting one normalized finding attribute."""

    source: object
    source_field: str
    raw_value: Any
    normalized_kind: str
    normalized_value: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, (SourceLocator, SourceRef)):
            raise TypeError("source must be a SourceRef or SourceLocator")
        for attribute in ("source_field", "normalized_kind"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "source_field": self.source_field,
            "raw_value": _to_plain(self.raw_value),
            "normalized_kind": self.normalized_kind,
            "normalized_value": _to_plain(self.normalized_value),
        }


@dataclass(frozen=True)
class FindingNormalizationWarning:
    """Source-scoped warning emitted while normalizing finding anatomy."""

    source: object
    code: str
    message: str
    source_field: Optional[str] = None
    raw_value: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, (SourceLocator, SourceRef)):
            raise TypeError("source must be a SourceRef or SourceLocator")
        for attribute in ("code", "message"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        if self.source_field is not None and (
            not isinstance(self.source_field, str) or not self.source_field.strip()
        ):
            raise ValueError("source_field must be a non-empty string when supplied")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "source_field": self.source_field,
            "raw_value": _to_plain(self.raw_value),
            "code": self.code,
            "message": self.message,
        }


@dataclass
class Finding:
    """A stable clinical finding at EMBED accession/finding-number grain."""

    accession_number: str
    laterality: Laterality
    finding_number: str
    finding_type: Optional[str] = None
    interpretation: Optional[ImagingInterpretation] = None
    anatomical_position: Optional[AnatomicalPosition] = None
    source_location_codes: Dict[str, Any] = field(default_factory=dict)
    source_depth_codes: Dict[str, Any] = field(default_factory=dict)
    source_distance_codes: Dict[str, Any] = field(default_factory=dict)
    normalization_evidence: List[FindingNormalizationEvidence] = field(
        default_factory=list
    )
    descriptors: Dict[str, Any] = field(default_factory=dict)
    normalization_warnings: List[FindingNormalizationWarning] = field(
        default_factory=list
    )
    metadata: Dict[str, Any] = field(default_factory=dict)
    record_type: FindingRecordType = field(init=False)

    def __post_init__(self) -> None:
        self.laterality = Laterality.coerce(self.laterality)
        self.finding_number = str(self.finding_number)
        self.record_type = (
            FindingRecordType.SYNTHETIC_CONTRALATERAL_NEGATIVE
            if self.finding_number == "-9"
            else FindingRecordType.FINDING
        )
        if (
            self.interpretation is not None
            and self.interpretation.identity != self.identity
        ):
            raise ValueError("Finding interpretation identity must match Finding")
        if any(
            not isinstance(item, FindingNormalizationEvidence)
            for item in self.normalization_evidence
        ):
            raise TypeError(
                "normalization_evidence must contain FindingNormalizationEvidence"
            )
        if any(
            not isinstance(item, FindingNormalizationWarning)
            for item in self.normalization_warnings
        ):
            raise TypeError(
                "normalization_warnings must contain FindingNormalizationWarning"
            )

    @property
    def identity(self) -> Tuple[str, str]:
        """Source-stable identity: accession and finding number."""

        return (self.accession_number, self.finding_number)

    @property
    def finding_id(self) -> str:
        """Compact string form suitable for logs, dict keys, and exports."""

        return ":".join((self.accession_number, self.finding_number))

    def merge_observation(self, observation: "Finding") -> None:
        """Merge a compatible repeated observation atomically."""

        if not isinstance(observation, Finding):
            raise TypeError("observation must be a Finding")
        if observation.identity != self.identity:
            raise ValueError("Finding observations must have matching identity")
        conflicts = tuple(
            attribute
            for attribute in ("laterality", "finding_type")
            if getattr(self, attribute) is not None
            and getattr(observation, attribute) is not None
            and getattr(self, attribute) != getattr(observation, attribute)
        )
        if conflicts:
            raise ValueError(
                "Finding observations conflict on populated attributes: "
                + ", ".join(conflicts)
            )
        for attribute in ("laterality", "finding_type"):
            current = getattr(self, attribute)
            observed = getattr(observation, attribute)
            if current is None and observed is not None:
                setattr(self, attribute, observed)
        self.metadata["source_row_count"] = int(
            self.metadata.get("source_row_count", 1)
        ) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accession_number": self.accession_number,
            "laterality": self.laterality.value,
            "finding_number": self.finding_number,
            "finding_type": self.finding_type,
            "interpretation_reference": (
                {
                    "accession_number": self.interpretation.accession_number,
                    "finding_number": self.interpretation.finding_number,
                }
                if self.interpretation is not None
                else None
            ),
            "anatomical_position": _to_plain(self.anatomical_position),
            "source_location_codes": _to_plain(self.source_location_codes),
            "source_depth_codes": _to_plain(self.source_depth_codes),
            "source_distance_codes": _to_plain(self.source_distance_codes),
            "normalization_evidence": [
                item.to_dict() for item in self.normalization_evidence
            ],
            "descriptors": _to_plain(self.descriptors),
            "normalization_warnings": [
                warning.to_dict() for warning in self.normalization_warnings
            ],
            "metadata": _to_plain(self.metadata),
            "record_type": self.record_type.value,
        }
