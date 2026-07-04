"""Clinical finding objects independent of source-code adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from embed_toolkit.clinical.procedures import PathologyEvent, Procedure, _to_plain
from embed_toolkit.core.anatomy import AnatomicalPosition
from embed_toolkit.core.primitives import Laterality


@dataclass
class Finding:
    """A stable clinical finding within an accession and breast side."""

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
    procedures: List[Procedure] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.laterality = Laterality.coerce(self.laterality)
        self.finding_number = str(self.finding_number)

    @property
    def identity(self) -> Tuple[str, Laterality, str]:
        """Source-stable identity: accession, side, and finding number."""

        return (self.accession_number, self.laterality, self.finding_number)

    @property
    def finding_id(self) -> str:
        """Compact string form suitable for logs, dict keys, and exports."""

        return ":".join(
            (self.accession_number, self.laterality.value, self.finding_number)
        )

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
        if procedure.laterality is Laterality.UNKNOWN:
            procedure.laterality = self.laterality
        procedure.finding_number = procedure.finding_number or self.finding_number
        procedure.finding_number = str(procedure.finding_number)
        self.procedures.append(procedure)
        return procedure

    def to_dict(self) -> Dict[str, Any]:
        return _to_plain(self)
