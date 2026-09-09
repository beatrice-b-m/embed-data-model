"""Mutable performed procedures and immutable procedure identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from embed_toolkit.core.entity import (
    MutableEntity,
    plain_value,
    readonly_mapping,
    serialize_entity,
)
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import SourceLocator
from embed_toolkit.core.source import SourceRef


def _to_plain(value: Any) -> Any:
    """Convert nested domain values to JSON-ready Python primitives."""

    return plain_value(value)


@dataclass(frozen=True)
class ProcedureIdentity:
    """Complete immutable identity for one resolved procedure."""

    patient_id: str
    performed_date: str
    procedure_type: str
    laterality: Laterality

    def __post_init__(self) -> None:
        for attribute in ("patient_id", "performed_date", "procedure_type"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
            object.__setattr__(self, attribute, value.strip())
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


class Procedure(MutableEntity):
    """One mutable performed procedure that can own pathology bundles."""

    __key_fields__ = ("identity",)

    def __init__(
        self,
        identity: ProcedureIdentity,
        sources: Optional[List[object]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        pathologies: Optional[List["Pathology"]] = None,
        source: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.identity = self._coerce_identity(identity)
        self._sources: List[object] = []
        self._metadata: Dict[str, Any] = dict(metadata or {})
        self._pathologies: List["Pathology"] = []
        for candidate in sources or ():
            self.add_source(candidate)
        if source is not None:
            self.add_source(source)
        for pathology in pathologies or ():
            self._attach_local(pathology)
        self._finish_initialization()

    @staticmethod
    def _coerce_identity(identity: ProcedureIdentity) -> ProcedureIdentity:
        if not isinstance(identity, ProcedureIdentity):
            raise TypeError("identity must be a ProcedureIdentity")
        return identity

    @property
    def sources(self) -> Tuple[object, ...]:
        return tuple(self._sources)

    @property
    def metadata(self) -> Any:
        return readonly_mapping(self._metadata)

    @property
    def pathologies(self) -> Tuple["Pathology", ...]:
        return tuple(self._pathologies)

    def add_source(self, source: object) -> object:
        """Attach optional source evidence without changing identity."""

        if not isinstance(source, (SourceLocator, SourceRef)):
            raise TypeError("source must be a SourceRef or SourceLocator")
        if source not in self._sources:
            self._sources.append(source)
        return source

    def add_pathology(self, pathology: "Pathology") -> "Pathology":
        """Attach pathology through the graph when this procedure is owned."""

        if self.graph is not None:
            result = self.graph.attach(self, pathology)
            return pathology if result is None else result
        return self._attach_local(pathology)

    def _children(self) -> Tuple[MutableEntity, ...]:
        return tuple(self._pathologies)

    def _attach_local(self, child: MutableEntity) -> "Pathology":
        from embed_toolkit.clinical.pathology import Pathology

        if not isinstance(child, Pathology):
            raise TypeError("Procedure children must be Pathology entities")
        for existing in self._pathologies:
            if existing.identity == child.identity:
                return existing
        self._pathologies.append(child)
        return child

    def _detach_local(self, child: MutableEntity) -> "Pathology":
        for index, existing in enumerate(self._pathologies):
            if existing is child:
                return self._pathologies.pop(index)
        raise ValueError("Pathology is not attached to this Procedure")

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "sources": self.sources,
            "pathologies": self.pathologies,
            "metadata": self._metadata,
        }

    def to_dict(self) -> Dict[str, Any]:
        return serialize_entity(self)
