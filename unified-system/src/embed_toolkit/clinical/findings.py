"""Clinical finding objects independent of source-code adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from embed_toolkit.clinical.procedures import PathologyEvent, Procedure, _to_plain
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
    assessment: Optional[str] = None
    anatomical_position: Optional[AnatomicalPosition] = None
    raw_source_fields: Dict[str, Any] = field(default_factory=dict)
    source_location_codes: Dict[str, Any] = field(default_factory=dict)
    source_depth_codes: Dict[str, Any] = field(default_factory=dict)
    descriptors: Dict[str, Any] = field(default_factory=dict)
    normalization_warnings: List[str] = field(default_factory=list)
    validation_issues: List[Dict[str, Any]] = field(default_factory=list)
    procedures: List[Procedure] = field(default_factory=list)
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

        for attribute in ("laterality", "finding_type", "assessment"):
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

    @property
    def pathology_events(self) -> Tuple[PathologyEvent, ...]:
        """Pathology aggregated from all procedures attached to this finding."""

        return tuple(
            event
            for procedure in self.procedures
            for event in procedure.pathology_events
        )

    def add_procedure(self, procedure: Procedure) -> Procedure:
        """Attach a duplicate-capable procedure row to this finding."""

        procedure.accession_number = procedure.accession_number or self.accession_number
        procedure.laterality = Laterality.coerce(procedure.laterality)
        procedure.finding_number = procedure.finding_number or self.finding_number
        procedure.finding_number = str(procedure.finding_number)
        procedure.add_finding_reference(self.accession_number, self.finding_number)
        if not any(existing is procedure for existing in self.procedures):
            self.procedures.append(procedure)
        return procedure

    def to_dict(self) -> Dict[str, Any]:
        return _to_plain(self)
