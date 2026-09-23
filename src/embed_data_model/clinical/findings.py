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
)

from embed_data_model.clinical.interpretations import ImagingInterpretation
from embed_data_model.core.anatomy import AnatomicalPosition
from embed_data_model.core.entity import (
    MutableEntity,
    plain_value,
    readonly_mapping,
    serialize_entity,
)
from embed_data_model.core.primitives import Laterality
from embed_data_model.core.source import SourceRef

if TYPE_CHECKING:
    from embed_data_model.clinical.pathology import Pathology
    from embed_data_model.clinical.procedures import Procedure




class FindingRecordType(str, Enum):
    """Explicit semantic kind of a finding record.

    Members
    -------
    FINDING='finding',
    SYNTHETIC_CONTRALATERAL_NEGATIVE='synthetic_contralateral_negative'.
    """

    FINDING = "finding"
    SYNTHETIC_CONTRALATERAL_NEGATIVE = "synthetic_contralateral_negative"


@dataclass(frozen=True)
class FindingNormalizationEvidence:
    """Source-scoped evidence supporting one normalized finding attribute.

    Attributes
    ----------
    source : SourceRef or None
        Physical row provenance when the load supplied source keys, else None.
        It identifies evidence, not a clinical event.
    source_field : str
        Source column/slot that supplied the normalized evidence.
    raw_value : Any
        Original unnormalized value retained as source evidence; not a semantic
        identity.
    normalized_kind : str
        Non-empty label describing the normalized concept.
    normalized_value : Any
        Normalized value retained alongside source evidence. Default: None.
    """

    source: Optional[SourceRef]
    """Physical row provenance when the load supplied source keys, else None."""
    source_field: str
    """Source column/slot that supplied the normalized evidence."""
    raw_value: Any
    """Original unnormalized value retained as source evidence; not a semantic identity."""
    normalized_kind: str
    """Non-empty label describing the normalized concept."""
    normalized_value: Any = None
    """Normalized value retained alongside source evidence. Default: None."""

    def __post_init__(self) -> None:
        if self.source is not None and not isinstance(self.source, SourceRef):
            raise TypeError("source must be a SourceRef or None")
        for attribute in ("source_field", "normalized_kind"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "source": None if self.source is None else self.source.to_dict(),
            "source_field": self.source_field,
            "raw_value": plain_value(self.raw_value),
            "normalized_kind": self.normalized_kind,
            "normalized_value": plain_value(self.normalized_value),
        }


@dataclass(frozen=True)
class FindingNormalizationWarning:
    """Source-scoped warning emitted while normalizing finding anatomy.

    Attributes
    ----------
    source : SourceRef or None
        Physical row provenance when the load supplied source keys, else None.
        It identifies evidence, not a clinical event.
    code : str
        Non-empty machine-readable diagnostic code.
    message : str
        Non-empty human-readable diagnostic explanation.
    source_field : Optional[str]
        Source column/slot that supplied the normalized evidence. Default: None.
    raw_value : Any
        Original unnormalized value retained as source evidence; not a semantic
        identity. Default: None.
    """

    source: Optional[SourceRef]
    """Physical row provenance when the load supplied source keys, else None."""
    code: str
    """Non-empty machine-readable diagnostic code."""
    message: str
    """Non-empty human-readable diagnostic explanation."""
    source_field: Optional[str] = None
    """Source column/slot that supplied the normalized evidence. Default: None."""
    raw_value: Any = None
    """Original unnormalized value retained as source evidence; not a semantic
    identity. Default: None.
    """

    def __post_init__(self) -> None:
        if self.source is not None and not isinstance(self.source, SourceRef):
            raise TypeError("source must be a SourceRef or None")
        for attribute in ("code", "message"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        if self.source_field is not None and (
            not isinstance(self.source_field, str) or not self.source_field.strip()
        ):
            raise ValueError("source_field must be a non-empty string when supplied")

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "source": None if self.source is None else self.source.to_dict(),
            "source_field": self.source_field,
            "raw_value": plain_value(self.raw_value),
            "code": self.code,
            "message": self.message,
        }


class Finding(MutableEntity):
    """A mutable clinical finding at accession/finding-number grain.

    Parameters
    ----------
    accession_number : str
        Non-empty exam accession identifying the clinical examination.
    laterality : Laterality
        Breast side. Coercible values are normalized; unknown values become
        UNKNOWN where coercion is supported.
    finding_number : str
        Non-empty finding identifier scoped to its accession; not a row ordinal.
    finding_type : Optional[str], optional
        Reported finding category; None means not supplied. Default: None.
    interpretation : Optional[ImagingInterpretation], optional
        Finding-level assessment/recommendation object, retained by reference;
        None means absent. Default: None.
    anatomical_position : Optional[AnatomicalPosition], optional
        Reported anatomy, independent of image coordinates; None means unknown.
        Default: None.
    source_location_codes : Optional[Dict[str, Any]], optional
        Source location codes copied into a dict, retaining raw evidence.
        Default: None.
    source_depth_codes : Optional[Dict[str, Any]], optional
        Source depth codes copied into a dict, retaining raw evidence. Default:
        None.
    source_distance_codes : Optional[Dict[str, Any]], optional
        Source distance codes copied into a dict, retaining raw evidence.
        Default: None.
    normalization_evidence : Optional[Iterable[FindingNormalizationEvidence]], optional
        Ordered source-code evidence retained for normalized finding anatomy.
        Default: None.
    descriptors : Optional[Mapping[str, Any]], optional
        Reported descriptor payload; no diagnosis is inferred from these values.
        Default: None.
    normalization_warnings : Optional[Iterable[FindingNormalizationWarning]], optional
        Ordered warnings for unknown or conflicting source codes. Default: None.
    metadata : Optional[Mapping[str, Any]], optional
        Consumer metadata, shallow-copied into a mutable dict. Nested values
        remain shared. Default: None.
    record_type : FindingRecordType, optional
        Semantic kind; FINDING is the default. Synthetic contralateral negatives
        must be explicit. Default: FindingRecordType.FINDING.
    procedures : Optional[Iterable[Procedure]], optional
        Initial performed procedures; objects are attached by reference and may
        be shared. Default: None.
    source : Optional[object], optional
        Optional SourceRef locating the source row; evidence, not a
        clinical event. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.

    Raises
    ------
    ValueError
        Blank accession/finding ID or incompatible interpretation/procedure context.
    TypeError
        Invalid interpretation, anatomy, evidence or warning type."""

    __key_fields__ = ("accession_number", "finding_number")

    finding_type: Optional[str]
    """Reported finding category; None means not supplied."""
    interpretation: Optional[ImagingInterpretation]
    """Finding-level assessment/recommendation object, retained by reference; None
    means absent.
    """
    anatomical_position: Optional[AnatomicalPosition]
    """Reported anatomy, independent of image coordinates; None means unknown."""
    source: Optional[object]
    """Optional SourceRef locating the source row; evidence, not a clinical event."""

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
        """Alias for finding_number; unique only within an accession."""

        return ":".join((self.accession_number, self.finding_number))

    @property
    def source_location_codes(self) -> Dict[str, Any]:
        """Live dictionary of raw source location evidence."""

        return readonly_mapping(self._source_location_codes)  # type: ignore[return-value]

    @property
    def source_depth_codes(self) -> Dict[str, Any]:
        """Live dictionary of raw source depth evidence."""

        return readonly_mapping(self._source_depth_codes)  # type: ignore[return-value]

    @property
    def source_distance_codes(self) -> Dict[str, Any]:
        """Live dictionary of raw source distance evidence."""

        return readonly_mapping(self._source_distance_codes)  # type: ignore[return-value]

    @property
    def normalization_evidence(self) -> Tuple[FindingNormalizationEvidence, ...]:
        """Immutable tuple of source normalization evidence in supplied order."""

        return tuple(self._normalization_evidence)

    @property
    def descriptors(self) -> Dict[str, Any]:
        """Reported descriptors in stored order; container behavior follows the return
        type and values are not deep-copied.
        """

        return self._descriptors

    @descriptors.setter
    def descriptors(self, values: Mapping[str, Any]) -> None:
        """Reported descriptors in stored order; container behavior follows the return
        type and values are not deep-copied.
        """

        self._descriptors = dict(values)

    @property
    def normalization_warnings(self) -> Tuple[FindingNormalizationWarning, ...]:
        """Immutable tuple of normalization warnings in supplied order."""

        return tuple(self._normalization_warnings)

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
    def procedures(self) -> Tuple["Procedure", ...]:
        """Tuple of live performed procedures in stored traversal order, deduplicated
        by Python identity where aggregated.
        """

        return tuple(self._procedures)

    @property
    def pathologies(self) -> Tuple["Pathology", ...]:
        """Alias for pathology, preserving live objects and collection order."""

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
        """Tuple of live pathology bundles in stored traversal order, deduplicated by
        Python identity where aggregated.
        """

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
        """Attach procedure and return the retained live object.

        Parameters
        ----------
        procedure : Procedure
            Compatible object with matching parent context. Retained by reference.

        Returns
        -------
        Procedure
            Attached object. Graph-backed containment delegates membership to the
            graph; embedded observations remain local values.

        Raises
        ------
        TypeError, ValueError
            Wrong object kind, incompatible parent context, or conflicting identity.
        """

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
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

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
