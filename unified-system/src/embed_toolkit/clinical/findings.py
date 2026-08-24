"""Clinical finding objects independent of source-code adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from embed_toolkit.clinical.interpretations import ImagingInterpretation
from embed_toolkit.clinical.procedures import _to_plain
from embed_toolkit.core.anatomy import AnatomicalPosition
from embed_toolkit.core.primitives import Laterality


class FindingRecordType(str, Enum):
    """Governed meaning of EMBED finding-number records."""

    FINDING = "finding"
    NO_FINDING_SENTINEL = "no_finding_sentinel"


@dataclass
class Finding:
    """A stable clinical finding at EMBED accession/finding-number grain."""

    accession_number: str
    laterality: Laterality
    finding_number: str
    finding_type: Optional[str] = None
    interpretation: Optional[ImagingInterpretation] = None
    anatomical_position: Optional[AnatomicalPosition] = None
    raw_source_fields: Dict[str, Any] = field(default_factory=dict)
    source_location_codes: Dict[str, Any] = field(default_factory=dict)
    source_depth_codes: Dict[str, Any] = field(default_factory=dict)
    descriptors: Dict[str, Any] = field(default_factory=dict)
    normalization_warnings: List[str] = field(default_factory=list)
    validation_issues: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    record_type: FindingRecordType = field(init=False)

    def __post_init__(self) -> None:
        self.laterality = Laterality.coerce(self.laterality)
        self.finding_number = str(self.finding_number)
        self.record_type = (
            FindingRecordType.NO_FINDING_SENTINEL
            if self.finding_number == "-9"
            else FindingRecordType.FINDING
        )
        if (
            self.interpretation is not None
            and self.interpretation.identity != self.identity
        ):
            raise ValueError("Finding interpretation identity must match Finding")

    @property
    def identity(self) -> Tuple[str, str]:
        """Source-stable identity: accession and finding number."""

        return (self.accession_number, self.finding_number)

    @property
    def finding_id(self) -> str:
        """Compact string form suitable for logs, dict keys, and exports."""

        return ":".join((self.accession_number, self.finding_number))

    def merge_observation(self, observation: "Finding") -> None:
        """Merge a repeated wide row while surfacing invariant conflicts."""

        for attribute in ("laterality", "finding_type"):
            current = getattr(self, attribute)
            observed = getattr(observation, attribute)
            if current is None and observed is not None:
                setattr(self, attribute, observed)
                continue
            if observed is None or current == observed:
                continue
            self.validation_issues.append(
                {
                    "code": "conflicting_finding_attribute",
                    "attribute": attribute,
                    "retained": current.value if isinstance(current, Laterality) else current,
                    "observed": observed.value
                    if isinstance(observed, Laterality)
                    else observed,
                }
            )
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
            "raw_source_fields": _to_plain(self.raw_source_fields),
            "source_location_codes": _to_plain(self.source_location_codes),
            "source_depth_codes": _to_plain(self.source_depth_codes),
            "descriptors": _to_plain(self.descriptors),
            "normalization_warnings": _to_plain(self.normalization_warnings),
            "validation_issues": _to_plain(self.validation_issues),
            "metadata": _to_plain(self.metadata),
            "record_type": self.record_type.value,
        }
