"""Finding-owned procedures and pathology events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum, IntEnum
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import ResolutionState, SourceOccurrence


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


class PathologySeverity(IntEnum):
    """Governed EMBED pathology severities without inferred clinical labels."""

    SEVERITY_0 = 0
    SEVERITY_1 = 1
    SEVERITY_2 = 2
    SEVERITY_3 = 3
    SEVERITY_4 = 4
    SEVERITY_5 = 5


@dataclass(frozen=True)
class ProcedureIdentity:
    """Complete governed identity for one resolved procedure association."""

    patient_id: str
    performed_date: str
    procedure_type: str
    laterality: Laterality

    def __post_init__(self) -> None:
        for attribute in ("patient_id", "performed_date", "procedure_type"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        side = Laterality.coerce(self.laterality)
        if side is Laterality.UNKNOWN:
            raise ValueError("Resolved procedure identity requires known laterality")
        object.__setattr__(self, "laterality", side)

    def to_dict(self) -> Dict[str, str]:
        return {
            "patient_id": self.patient_id,
            "performed_date": self.performed_date,
            "procedure_type": self.procedure_type,
            "laterality": self.laterality.value,
        }


@dataclass(frozen=True)
class UnresolvedProcedureOccurrence:
    """Normalized procedure evidence that cannot establish clinical identity."""

    IDENTITY_FIELDS: ClassVar[Tuple[str, ...]] = (
        "patient_id",
        "performed_date",
        "procedure_type",
        "laterality",
    )

    occurrence: SourceOccurrence
    missing_identity_fields: Tuple[str, ...]
    patient_id: Optional[str] = None
    performed_date: Optional[str] = None
    procedure_type: Optional[str] = None
    laterality: Laterality = Laterality.UNKNOWN

    def __post_init__(self) -> None:
        if self.occurrence.resolution_state is not ResolutionState.UNRESOLVED:
            raise ValueError("Procedure occurrence must have unresolved source state")
        missing = tuple(self.missing_identity_fields)
        if not missing or any(
            not isinstance(value, str) or not value.strip() for value in missing
        ):
            raise ValueError("missing_identity_fields must identify incomplete fields")
        if len(set(missing)) != len(missing):
            raise ValueError("missing_identity_fields must not contain duplicates")
        unknown = set(missing) - set(self.IDENTITY_FIELDS)
        if unknown:
            raise ValueError(
                f"Unknown procedure identity fields: {tuple(sorted(unknown))}"
            )
        object.__setattr__(self, "missing_identity_fields", missing)
        laterality = Laterality.coerce(self.laterality)
        object.__setattr__(self, "laterality", laterality)
        candidate_missing = {
            field_name
            for field_name, value in (
                ("patient_id", self.patient_id),
                ("performed_date", self.performed_date),
                ("procedure_type", self.procedure_type),
            )
            if value is None or not isinstance(value, str) or not value.strip()
        }
        if laterality is Laterality.UNKNOWN:
            candidate_missing.add("laterality")
        if set(missing) != candidate_missing:
            raise ValueError(
                "missing_identity_fields must match absent or unknown candidate values"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "occurrence": self.occurrence.to_dict(),
            "missing_identity_fields": list(self.missing_identity_fields),
            "patient_id": self.patient_id,
            "performed_date": self.performed_date,
            "procedure_type": self.procedure_type,
            "laterality": self.laterality.value,
        }


@dataclass
class PathologyEvent:
    """Pathology information linked through a clinical procedure."""

    pathology_id: Optional[str] = None
    diagnosis: Optional[str] = None
    result_category: Optional[str] = None
    event_date: Optional[str] = None
    malignant: Optional[bool] = None
    severity: Optional[PathologySeverity] = None
    raw_severity: Any = None
    descriptors: Tuple[str, ...] = ()
    validation_issues: List[Dict[str, Any]] = field(default_factory=list)
    raw_source_fields: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity is not None:
            self.severity = PathologySeverity(self.severity)
        self.descriptors = tuple(str(value) for value in self.descriptors)

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
            self.raw_severity,
            self.descriptors,
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
