"""Resolved procedures and source-located incomplete procedure evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import SourceLocator
from embed_toolkit.core.source import SourceRef


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

    source: object
    missing_identity_fields: Tuple[str, ...]
    patient_id: Optional[str] = None
    performed_date: Optional[str] = None
    procedure_type: Optional[str] = None
    laterality: Laterality = Laterality.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.source, (SourceLocator, SourceRef)):
            raise TypeError("source must be a SourceRef or SourceLocator")
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
            "source": self.source.to_dict(),
            "missing_identity_fields": list(self.missing_identity_fields),
            "patient_id": self.patient_id,
            "performed_date": self.performed_date,
            "procedure_type": self.procedure_type,
            "laterality": self.laterality.value,
        }


@dataclass
class Procedure:
    """One resolved procedure shared independently of finding attribution."""

    identity: ProcedureIdentity
    sources: List[object] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ProcedureIdentity):
            raise TypeError("identity must be a ProcedureIdentity")
        sources = list(self.sources)
        if any(
            not isinstance(source, (SourceLocator, SourceRef)) for source in sources
        ):
            raise TypeError("sources must contain SourceRef or SourceLocator values")
        if len(set(sources)) != len(sources):
            raise ValueError("sources must contain unique SourceLocator values")
        self.sources = sources

    def add_source(
        self,
        source: object,
    ) -> object:
        """Attach a source reference without changing clinical identity."""

        if not isinstance(source, (SourceLocator, SourceRef)):
            raise TypeError("source must be a SourceRef or SourceLocator")
        if source not in self.sources:
            self.sources.append(source)
        return source

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
            "metadata": _to_plain(self.metadata),
        }
