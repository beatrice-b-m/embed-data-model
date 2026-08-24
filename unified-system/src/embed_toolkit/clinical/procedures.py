"""Finding-owned procedures and pathology events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from embed_toolkit.core.primitives import Laterality


def _to_plain(value: Any) -> Any:
    """Convert nested domain objects to JSON-ready Python primitives."""

    if is_dataclass(value):
        return _to_plain(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value


@dataclass
class PathologyEvent:
    """Pathology information linked through a clinical procedure."""

    pathology_id: Optional[str] = None
    diagnosis: Optional[str] = None
    result_category: Optional[str] = None
    event_date: Optional[str] = None
    malignant: Optional[bool] = None
    raw_source_fields: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _to_plain(self)

    @property
    def evidence_identity(self) -> Tuple[Any, ...]:
        if self.pathology_id is not None:
            return ("pathology_id", self.pathology_id)
        return (
            "source_values",
            self.diagnosis,
            self.result_category,
            self.event_date,
            self.malignant,
        )


@dataclass
class Procedure:
    """Clinical procedure row associated with a finding."""

    procedure_id: Optional[str] = None
    procedure_type: Optional[str] = None
    patient_id: Optional[str] = None
    accession_number: Optional[str] = None
    laterality: Laterality = Laterality.UNKNOWN
    finding_number: Optional[str] = None
    performed_date: Optional[str] = None
    pathology_events: List[PathologyEvent] = field(default_factory=list)
    raw_source_fields: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    finding_references: List[Tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.laterality = Laterality.coerce(self.laterality)
        if self.finding_number is not None:
            self.finding_number = str(self.finding_number)

    def add_pathology_event(self, event: PathologyEvent) -> PathologyEvent:
        """Attach pathology to this procedure and return it for chaining."""

        for existing in self.pathology_events:
            if existing.evidence_identity == event.evidence_identity:
                return existing
        self.pathology_events.append(event)
        return event

    @property
    def release_scoped_identity(
        self,
    ) -> Optional[Tuple[str, str, str, Laterality]]:
        """Return the complete EMBED procedure identity, or no identity."""

        if (
            self.patient_id is None
            or self.performed_date is None
            or self.procedure_type is None
            or self.laterality is Laterality.UNKNOWN
        ):
            return None
        return (
            self.patient_id,
            self.performed_date,
            self.procedure_type,
            self.laterality,
        )

    def add_finding_reference(self, accession: str, finding_number: str) -> None:
        reference = (accession, str(finding_number))
        if reference not in self.finding_references:
            self.finding_references.append(reference)

    def to_dict(self) -> Dict[str, Any]:
        return _to_plain(self)
