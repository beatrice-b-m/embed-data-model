"""Mutable finding entities and source-neutral finding normalizers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    Union,
)

from embed_data_model.clinical.interpretations import ImagingInterpretation
from embed_data_model.clinical.procedures import _to_plain
from embed_data_model.core.anatomy import AnatomicalPosition
from embed_data_model.core.entity import (
    MutableEntity,
    readonly_mapping,
    serialize_entity,
)
from embed_data_model.core.primitives import Laterality
from embed_data_model.core.provenance import SourceLocator
from embed_data_model.core.source import SourceRef

if TYPE_CHECKING:
    from embed_data_model.clinical.pathology import Pathology
    from embed_data_model.clinical.procedures import Procedure


SourceValue = Union[SourceLocator, SourceRef]


class FindingRecordType(str, Enum):
    """Explicit semantic kind of a finding record."""

    FINDING = "finding"
    SYNTHETIC_CONTRALATERAL_NEGATIVE = "synthetic_contralateral_negative"


@dataclass(frozen=True)
class FindingNormalizationEvidence:
    """Source-scoped evidence supporting one normalized finding attribute."""

    source: SourceValue
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

    source: SourceValue
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


class Finding(MutableEntity):
    """A mutable clinical finding at accession/finding-number grain."""

    __key_fields__ = ("accession_number", "finding_number")

    def __init__(
        self,
        accession_number: str,
        laterality: Laterality,
        finding_number: str,
        finding_type: Optional[str] = None,
        interpretation: Optional[ImagingInterpretation] = None,
        anatomical_position: Optional[AnatomicalPosition] = None,
        source_location_codes: Optional[Dict[str, Any]] = None,
        source_depth_codes: Optional[Dict[str, Any]] = None,
        source_distance_codes: Optional[Dict[str, Any]] = None,
        normalization_evidence: Optional[Iterable[FindingNormalizationEvidence]] = None,
        descriptors: Optional[Mapping[str, Any]] = None,
        normalization_warnings: Optional[Iterable[FindingNormalizationWarning]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        record_type: FindingRecordType = FindingRecordType.FINDING,
        procedures: Optional[Iterable["Procedure"]] = None,
        source: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.accession_number = _required_text(accession_number, "accession_number")
        self.laterality = Laterality.coerce(laterality)
        self.finding_number = _identifier_text(finding_number, "finding_number")
        self.finding_type = finding_type
        self.interpretation = interpretation
        if interpretation is not None and interpretation.identity != self.identity:
            raise ValueError("Finding interpretation identity must match Finding")
        self.anatomical_position = anatomical_position
        self._source_location_codes = dict(source_location_codes or {})
        self._source_depth_codes = dict(source_depth_codes or {})
        self._source_distance_codes = dict(source_distance_codes or {})
        self._normalization_evidence = list(normalization_evidence or ())
        self._descriptors = dict(descriptors or {})
        self._normalization_warnings = list(normalization_warnings or ())
        self._metadata = dict(metadata or {})
        self.record_type = FindingRecordType(record_type)
        self.source = source
        self._procedures: List["Procedure"] = []
        for procedure in procedures or ():
            self._attach_local(procedure)
        self._finish_initialization()

    @property
    def identity(self) -> Tuple[str, str]:
        """Source-stable identity: accession and finding number."""

        return self.accession_number, self.finding_number

    @property
    def finding_id(self) -> str:
        return ":".join((self.accession_number, self.finding_number))

    @property
    def source_location_codes(self) -> Dict[str, Any]:
        return readonly_mapping(self._source_location_codes)  # type: ignore[return-value]

    @property
    def source_depth_codes(self) -> Dict[str, Any]:
        return readonly_mapping(self._source_depth_codes)  # type: ignore[return-value]

    @property
    def source_distance_codes(self) -> Dict[str, Any]:
        return readonly_mapping(self._source_distance_codes)  # type: ignore[return-value]

    @property
    def normalization_evidence(self) -> Tuple[FindingNormalizationEvidence, ...]:
        return tuple(self._normalization_evidence)

    @property
    def descriptors(self) -> Dict[str, Any]:
        return self._descriptors

    @descriptors.setter
    def descriptors(self, values: Mapping[str, Any]) -> None:
        self._descriptors = dict(values)

    @property
    def normalization_warnings(self) -> Tuple[FindingNormalizationWarning, ...]:
        return tuple(self._normalization_warnings)

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    @metadata.setter
    def metadata(self, values: Dict[str, Any]) -> None:
        self._metadata = dict(values)

    @property
    def procedures(self) -> Tuple["Procedure", ...]:
        return tuple(self._procedures)

    @property
    def pathologies(self) -> Tuple["Pathology", ...]:
        result: List["Pathology"] = []
        seen = set()
        for procedure in self._procedures:
            for pathology in procedure.pathologies:
                if id(pathology) not in seen:
                    seen.add(id(pathology))
                    result.append(pathology)
        return tuple(result)

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        return self.pathologies

    def merge_observation(self, observation: "Finding") -> None:
        """Merge a compatible repeated observation in place."""

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
        if self.finding_type is None:
            self.finding_type = observation.finding_type
        self._metadata["source_row_count"] = int(
            self._metadata.get("source_row_count", 1)
        ) + 1

    def add_procedure(self, procedure: "Procedure") -> "Procedure":
        if self.graph is not None:
            result = self.graph.attach(self, procedure)
            return procedure if result is None else result
        return self._attach_local(procedure)

    def _children(self) -> Tuple[MutableEntity, ...]:
        return tuple(self._procedures)

    def _attach_local(self, child: MutableEntity) -> "Procedure":
        from embed_data_model.clinical.procedures import Procedure

        if not isinstance(child, Procedure):
            raise TypeError("Finding children must be Procedure entities")
        for existing in self._procedures:
            if existing.identity == child.identity:
                if existing is child:
                    return existing
                raise ValueError(
                    "Distinct Procedure objects cannot share an identity in a Finding"
                )
        self._procedures.append(child)
        return child

    def _detach_local(self, child: MutableEntity) -> MutableEntity:
        for index, existing in enumerate(self._procedures):
            if existing is child:
                return self._procedures.pop(index)
        return child  # idempotent graph recomposition

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "accession_number": self.accession_number,
            "laterality": self.laterality,
            "finding_number": self.finding_number,
            "finding_type": self.finding_type,
            "interpretation": self.interpretation,
            "anatomical_position": self.anatomical_position,
            "source_location_codes": self._source_location_codes,
            "source_depth_codes": self._source_depth_codes,
            "source_distance_codes": self._source_distance_codes,
            "normalization_evidence": self.normalization_evidence,
            "descriptors": self._descriptors,
            "normalization_warnings": self.normalization_warnings,
            "metadata": self._metadata,
            "record_type": self.record_type,
            "source": self.source,
            "procedures": self.procedures,
            "pathology": self.pathology,
        }

    def to_dict(self) -> Dict[str, Any]:
        return serialize_entity(self)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _identifier_text(value: Any, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} must be populated")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be populated")
    return normalized
