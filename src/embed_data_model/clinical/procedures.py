"""Mutable performed procedures and immutable procedure identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Union,
)

from embed_data_model.core.entity import (
    MutableEntity,
    serialize_entity,
)
from embed_data_model.core.primitives import Laterality
from embed_data_model.core.provenance import SourceLocator
from embed_data_model.core.source import SourceRef

if TYPE_CHECKING:
    from embed_data_model.clinical.pathology import Pathology


SourceValue = Union[SourceLocator, SourceRef]


@dataclass(frozen=True)
class ProcedureIdentity:
    """Complete immutable identity for one resolved procedure.

    Attributes
    ----------
    patient_id : str
        Patient identifier. Non-empty text; source patient claims and assigned
        exam ownership are separate facts.
    performed_date : str
        Non-empty reported procedure date, conventionally ISO YYYY-MM-DD.
        Construction checks text, validate checks dates.
    procedure_type : str
        Non-empty reported procedure kind; part of semantic identity.
    laterality : Laterality
        Known LEFT, RIGHT or BILATERAL side. UNKNOWN raises ValueError.
    """

    patient_id: str
    """Patient identifier. Non-empty text; source patient claims and assigned exam
    ownership are separate facts.
    """
    performed_date: str
    """Non-empty reported procedure date, conventionally ISO YYYY-MM-DD.
    Construction checks text, validate checks dates.
    """
    procedure_type: str
    """Non-empty reported procedure kind; part of semantic identity."""
    laterality: Laterality
    """Known LEFT, RIGHT or BILATERAL side. UNKNOWN raises ValueError."""

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
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "patient_id": self.patient_id,
            "performed_date": self.performed_date,
            "procedure_type": self.procedure_type,
            "laterality": self.laterality.value,
        }


class Procedure(MutableEntity):
    """One mutable performed procedure that can own pathology bundles.

    Parameters
    ----------
    identity : ProcedureIdentity
        Semantic identity used for graph membership; use rekey for a registered
        entity.
    sources : Optional[Iterable[object]], optional
        Source evidence in supplied order. None starts an empty collection;
        source adds one item. Default: None.
    metadata : Optional[Dict[str, Any]], optional
        Consumer metadata, shallow-copied into a mutable dict. Nested values
        remain shared. Default: None.
    pathologies : Optional[Iterable[Pathology]], optional
        Initial pathology bundles, retained by reference in supplied order.
        Default: None.
    source : Optional[object], optional
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.
    """

    __key_fields__ = ("identity",)

    def __init__(
        self,
        identity: ProcedureIdentity,
        sources: Optional[Iterable[object]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        pathologies: Optional[Iterable["Pathology"]] = None,
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
        """Tuple of retained source evidence in insertion order."""

        return tuple(self._sources)

    @property
    def metadata(self) -> Dict[str, Any]:
        """Mutable consumer metadata dictionary. Assignment shallow-copies the mapping;
        nested values remain shared.
        """

        return self._metadata

    @metadata.setter
    def metadata(self, values: Dict[str, Any]) -> None:
        """Mutable consumer metadata dictionary. Assignment shallow-copies the mapping;
        nested values remain shared.
        """

        self._metadata = dict(values)

    @property
    def pathologies(self) -> Tuple["Pathology", ...]:
        """Alias for pathology, preserving live objects and collection order."""

        return tuple(self._pathologies)

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        """Tuple of live pathology bundles in stored traversal order, deduplicated by
        Python identity where aggregated.
        """

        return self.pathologies

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
        from embed_data_model.clinical.pathology import Pathology

        if not isinstance(child, Pathology):
            raise TypeError("Procedure children must be Pathology entities")
        for existing in self._pathologies:
            if existing.identity == child.identity:
                if existing is child:
                    return existing
                raise ValueError(
                    "Distinct Pathology objects cannot share an identity in a Procedure"
                )
        self._pathologies.append(child)
        return child

    def _detach_local(self, child: MutableEntity) -> MutableEntity:
        for index, existing in enumerate(self._pathologies):
            if existing is child:
                return self._pathologies.pop(index)
        return child  # idempotent graph recomposition

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "sources": self.sources,
            "pathology": self.pathology,
            "metadata": self._metadata,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)
