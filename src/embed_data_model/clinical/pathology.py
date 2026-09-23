"""Mutable pathology bundles, registry entries, and value references."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any, Dict, Hashable, Iterable, Mapping, Optional, Tuple, Union

from embed_data_model.clinical.associations import (
    AttributionStatus,
    ClinicalObjectReference,
)
from embed_data_model.core.entity import (
    MutableEntity,
    plain_value,
    serialize_entity,
)
from embed_data_model.core.provenance import SourceLocator
from embed_data_model.core.source import SourceRef


SourceValue = Union[SourceLocator, SourceRef]


def _optional_source(source: Optional[object]) -> Optional[SourceValue]:
    if source is not None and not isinstance(source, (SourceLocator, SourceRef)):
        raise TypeError("source must be a SourceRef or SourceLocator")
    return source


class PathologySeverity(IntEnum):
    """Governed EMBED pathology severities without inferred labels.

    Members
    -------
    SEVERITY_0=0, SEVERITY_1=1, SEVERITY_2=2, SEVERITY_3=3, SEVERITY_4=4,
    SEVERITY_5=5.
    """

    SEVERITY_0 = 0
    SEVERITY_1 = 1
    SEVERITY_2 = 2
    SEVERITY_3 = 3
    SEVERITY_4 = 4
    SEVERITY_5 = 5


class PathologyRecordKind(str, Enum):
    """Addressable pathology grains represented by attribution links.

    Members
    -------
    OBSERVATION='observation', DIAGNOSIS='diagnosis'.
    """

    OBSERVATION = "observation"
    DIAGNOSIS = "diagnosis"


class PathologyObservation(MutableEntity):
    """One mutable descriptor occurrence in an ordered source slot.

    Parameters
    ----------
    descriptor : str
        One non-empty reported pathology descriptor.
    source_slot : str
        Non-empty source descriptor slot name; preserves ordered source
        evidence.
    source_ordinal : int
        One-based occurrence within a descriptor slot; must be a positive
        integer.
    source : Optional[SourceValue], optional
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.
    """

    source_ordinal: int
    """One-based occurrence within a descriptor slot; must be a positive integer."""

    def __init__(
        self,
        descriptor: str,
        source_slot: str,
        source_ordinal: int,
        source: Optional[SourceValue] = None,
    ) -> None:
        super().__init__()
        self.descriptor = _required_text(descriptor, "descriptor")
        self.source_slot = _required_text(source_slot, "source_slot")
        if (
            isinstance(source_ordinal, bool)
            or not isinstance(source_ordinal, int)
            or source_ordinal < 1
        ):
            raise ValueError("source_ordinal must be a positive integer")
        self.source_ordinal = source_ordinal
        self.source = _optional_source(source)
        self._finish_initialization()

    @property
    def identity(self) -> Tuple[str, int]:
        """Semantic identity used for equality of addresses, independent of Python object identity."""

        return self.source_slot, self.source_ordinal

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "descriptor": self.descriptor,
            "source_slot": self.source_slot,
            "source_ordinal": self.source_ordinal,
            "source": self.source,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


class PathologyDiagnosis(MutableEntity):
    """Mutable diagnosis evidence with an explicit documentation date.

    Parameters
    ----------
    source : Optional[SourceValue], optional
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events. Default: None.
    diagnosis : Optional[str], optional
        Reported diagnosis text; None means absent. No diagnosis is inferred.
        Default: None.
    result_category : Optional[str], optional
        Reported result category; None means absent. Default: None.
    malignant : Optional[bool], optional
        Reported malignancy flag; None means unknown, not False. Default: None.
    severity : Optional[PathologySeverity], optional
        Reported EMBED severity on the 0–5 scale; invalid numeric facts are
        retained for validate. Default: None.
    raw_severity : Any, optional
        Unnormalized source severity retained for comparison; None means absent.
        Default: None.
    report_documented_date : Optional[str], optional
        Date the report was documented, conventionally ISO YYYY-MM-DD; not a
        diagnosis/event date. Default: None.
    validation_issues : Tuple[object, ...], optional
        Supplied diagnostics retained in order; does not run validation.
        Default: ().

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.
    """

    diagnosis: Optional[str]
    """Reported diagnosis text; None means absent. No diagnosis is inferred."""
    result_category: Optional[str]
    """Reported result category; None means absent."""
    malignant: Optional[bool]
    """Reported malignancy flag; None means unknown, not False."""
    raw_severity: Any
    """Unnormalized source severity retained for comparison; None means absent."""
    report_documented_date: Optional[str]
    """Date the report was documented, conventionally ISO YYYY-MM-DD; not a
    diagnosis/event date.
    """

    def __init__(
        self,
        source: Optional[SourceValue] = None,
        diagnosis: Optional[str] = None,
        result_category: Optional[str] = None,
        malignant: Optional[bool] = None,
        severity: Optional[PathologySeverity] = None,
        raw_severity: Any = None,
        report_documented_date: Optional[str] = None,
        validation_issues: Tuple[object, ...] = (),
    ) -> None:
        super().__init__()
        self.source = _optional_source(source)
        self.diagnosis = diagnosis
        self.result_category = result_category
        self.malignant = malignant
        self.severity = _severity_value(severity)
        self.raw_severity = raw_severity
        self.report_documented_date = report_documented_date
        self.validation_issues = tuple(validation_issues)
        if any(
            getattr(issue, "source", self.source) != self.source
            for issue in self.validation_issues
        ):
            raise ValueError("Pathology diagnosis issues must reference its source")
        represented_values = (
            self.diagnosis,
            self.result_category,
            self.malignant,
            self.severity,
            self.raw_severity,
            self.report_documented_date,
        )
        if all(value is None for value in represented_values) and not self.validation_issues:
            raise ValueError("PathologyDiagnosis requires represented diagnosis evidence")
        self._finish_initialization()

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "source": self.source,
            "diagnosis": self.diagnosis,
            "result_category": self.result_category,
            "malignant": self.malignant,
            "severity": self.severity,
            "raw_severity": self.raw_severity,
            "report_documented_date": self.report_documented_date,
            "validation_issues": self.validation_issues,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


class Pathology(MutableEntity):
    """A mutable pathology bundle for one procedure or explicit pathology record.

    ``identity`` is supplied by the caller or adapter and is never derived from
    a physical row, a report date or the diagnosis payload. The EMBED adapter
    uses ``(patient_id, record_id)`` for explicitly keyed records and
    ``("procedure", ProcedureIdentity)`` for pathology carried on MagView
    procedure rows. Descriptor order and duplicate values are retained.

    Parameters
    ----------
    identity : Optional[Hashable], optional
        Explicit hashable semantic key. When None, ``patient_id`` and
        ``record_id`` must both be supplied and form the key. Default: None.
    diagnosis : Optional[str], optional
        Reported diagnosis text; None means absent. No diagnosis is inferred.
        Default: None.
    result_category : Optional[str], optional
        Reported result category; None means absent. Default: None.
    malignant : Optional[bool], optional
        Reported malignancy flag; None means unknown, not False. Default: None.
    severity : Optional[PathologySeverity], optional
        Reported EMBED severity on the 0–5 scale; invalid numeric facts are
        retained for validate. Default: None.
    raw_severity : Any, optional
        Unnormalized source severity retained for comparison; None means absent.
        Default: None.
    report_documented_date : Optional[str], optional
        Date the report was documented, conventionally ISO YYYY-MM-DD; not a
        diagnosis/event date. Default: None.
    descriptors : Iterable[Any], optional
        Ordered descriptor occurrences, copied into a list. Duplicates and order
        are preserved; no event IDs are inferred. Default: ().
    source : Optional[SourceValue], optional
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events. Default: None.
    metadata : Optional[Mapping[str, Any]], optional
        Consumer metadata, shallow-copied into a mutable dict. Nested values
        remain shared. Default: None.
    payload : Optional[Mapping[str, Any]], optional
        Additional supplied payload, shallow-copied into a dict; no inferred
        clinical meaning. Default: None.
    patient_id, record_id : str or None, optional, keyword-only
        Explicit patient-scoped record key used when identity is None; the
        identity becomes ``(patient_id, record_id)``. Both default None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.

    Examples
    --------
    >>> from embed_data_model import Pathology
    >>> Pathology(patient_id="P1", record_id="report1").identity
    ('P1', 'report1')

    Raises
    ------
    TypeError
        No usable identity, an unhashable identity or unsupported source value."""

    __key_fields__ = ("identity",)

    identity: Hashable
    """Semantic identity used for graph membership; use rekey for a registered entity."""
    diagnosis: Optional[str]
    """Reported diagnosis text; None means absent. No diagnosis is inferred."""
    result_category: Optional[str]
    """Reported result category; None means absent."""
    malignant: Optional[bool]
    """Reported malignancy flag; None means unknown, not False."""
    raw_severity: Any
    """Unnormalized source severity retained for comparison; None means absent."""
    report_documented_date: Optional[str]
    """Date the report was documented, conventionally ISO YYYY-MM-DD; not a
    diagnosis/event date.
    """

    def __init__(
        self,
        identity: Optional[Hashable] = None,
        diagnosis: Optional[str] = None,
        result_category: Optional[str] = None,
        malignant: Optional[bool] = None,
        severity: Optional[PathologySeverity] = None,
        raw_severity: Any = None,
        report_documented_date: Optional[str] = None,
        descriptors: Iterable[Any] = (),
        source: Optional[SourceValue] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        patient_id: Optional[str] = None,
        record_id: Optional[Hashable] = None,
    ) -> None:
        super().__init__()
        if identity is None:
            if patient_id is None or record_id is None:
                raise TypeError(
                    "Pathology requires an identity or both patient_id and record_id"
                )
            identity = (patient_id, record_id)
        try:
            hash(identity)
        except TypeError as exc:
            raise TypeError("Pathology identity must be hashable") from exc
        self.identity = identity
        self.diagnosis = diagnosis
        self.result_category = result_category
        self.malignant = malignant
        self.severity = _severity_value(severity)
        self.raw_severity = raw_severity
        self.report_documented_date = report_documented_date
        self._descriptors = list(descriptors)
        self.source = _optional_source(source)
        self._metadata = dict(metadata or {})
        self._payload = dict(payload or {})
        self._finish_initialization()

    @property
    def descriptors(self) -> Tuple[Any, ...]:
        """Reported descriptors in stored order; container behavior follows the return
        type and values are not deep-copied.
        """

        return tuple(self._descriptors)

    @descriptors.setter
    def descriptors(self, values: Iterable[Any]) -> None:
        """Reported descriptors in stored order; container behavior follows the return
        type and values are not deep-copied.
        """

        self._descriptors = list(values)

    @property
    def metadata(self) -> Dict[str, Any]:
        """Mutable consumer metadata dictionary. Assignment shallow-copies the mapping;
        nested values remain shared.
        """

        return self._metadata

    @metadata.setter
    def metadata(self, values: Mapping[str, Any]) -> None:
        """Mutable consumer metadata dictionary. Assignment shallow-copies the mapping;
        nested values remain shared.
        """

        self._metadata = dict(values)

    @property
    def payload(self) -> Dict[str, Any]:
        """Supplied payload mapping; assignment shallow-copies the mapping and does not
        interpret its contents.
        """

        return self._payload

    @payload.setter
    def payload(self, values: Mapping[str, Any]) -> None:
        """Supplied payload mapping; assignment shallow-copies the mapping and does not
        interpret its contents.
        """

        self._payload = dict(values)

    def add_descriptor(self, descriptor: Any) -> Any:
        """Append descriptor without deduplicating and return the same value.
        Descriptor order represents source slots, not clinical chronology.
        """

        self._descriptors.append(descriptor)
        return descriptor

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "diagnosis": self.diagnosis,
            "result_category": self.result_category,
            "malignant": self.malignant,
            "severity": self.severity,
            "raw_severity": self.raw_severity,
            "report_documented_date": self.report_documented_date,
            "descriptors": self.descriptors,
            "source": self.source,
            "metadata": self._metadata,
            "payload": self._payload,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


class CancerRegistryEntry(MutableEntity):
    """Patient-scoped registry data that may be assigned to several exams.

    Parameters
    ----------
    patient_id : str
        Patient identifier. Non-empty text; source patient claims and assigned
        exam ownership are separate facts.
    registry_id : str
        Non-empty registry identifier scoped to patient_id.
    payload : Optional[Mapping[str, Any]], optional
        Additional supplied payload, shallow-copied into a dict; no inferred
        clinical meaning. Default: None.
    metadata : Optional[Mapping[str, Any]], optional
        Consumer metadata, shallow-copied into a mutable dict. Nested values
        remain shared. Default: None.
    source : Optional[SourceValue], optional
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.

    Raises
    ------
    ValueError
        Blank patient or registry ID.
    TypeError
        Unsupported source value or non-mapping payload/metadata."""

    __key_fields__ = ("patient_id", "registry_id")

    def __init__(
        self,
        patient_id: str,
        registry_id: str,
        payload: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        source: Optional[SourceValue] = None,
    ) -> None:
        super().__init__()
        self.patient_id = _required_text(patient_id, "patient_id")
        self.registry_id = _required_text(registry_id, "registry_id")
        self._payload = dict(payload or {})
        self._metadata = dict(metadata or {})
        self.source = _optional_source(source)
        self._finish_initialization()

    @property
    def identity(self) -> Tuple[str, str]:
        """Semantic identity used for equality of addresses, independent of Python object identity."""

        return self.patient_id, self.registry_id

    @property
    def payload(self) -> Mapping[str, Any]:
        """Supplied payload mapping; assignment shallow-copies the mapping and does not
        interpret its contents.
        """

        return self._payload

    @payload.setter
    def payload(self, values: Mapping[str, Any]) -> None:
        """Supplied payload mapping; assignment shallow-copies the mapping and does not
        interpret its contents.
        """

        self._payload = dict(values)

    @property
    def metadata(self) -> Dict[str, Any]:
        """Mutable consumer metadata dictionary. Assignment shallow-copies the mapping;
        nested values remain shared.
        """

        return self._metadata

    @metadata.setter
    def metadata(self, values: Mapping[str, Any]) -> None:
        """Mutable consumer metadata dictionary. Assignment shallow-copies the mapping;
        nested values remain shared.
        """

        self._metadata = dict(values)

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "registry_id": self.registry_id,
            "payload": self._payload,
            "metadata": self._metadata,
            "source": self.source,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


@dataclass(frozen=True)
class PathologyReference:
    """Non-recursive reference to one pathology diagnosis or observation.

    Attributes
    ----------
    kind : PathologyRecordKind
        Governed kind of referenced object; identity shape depends on the kind.
    source : SourceValue
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events.
    source_slot : Optional[str]
        Non-empty source descriptor slot name; preserves ordered source
        evidence. Default: None.
    """

    kind: PathologyRecordKind
    """Governed kind of referenced object; identity shape depends on the kind."""
    source: SourceValue
    """Optional provenance. SourceRef and SourceLocator identify evidence, not clinical events."""
    source_slot: Optional[str] = None
    """Non-empty source descriptor slot name; preserves ordered source evidence. Default: None."""

    def __post_init__(self) -> None:
        kind = PathologyRecordKind(self.kind)
        object.__setattr__(self, "kind", kind)
        if not isinstance(self.source, (SourceLocator, SourceRef)):
            raise TypeError("source must be a SourceRef or SourceLocator")
        if kind is PathologyRecordKind.OBSERVATION:
            if not isinstance(self.source_slot, str) or not self.source_slot.strip():
                raise ValueError("Observation references require source_slot")
        elif self.source_slot is not None:
            raise ValueError("Diagnosis references do not use source_slot")

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "kind": self.kind.value,
            "source": self.source.to_dict(),
            "source_slot": self.source_slot,
        }


@dataclass(frozen=True)
class PathologyAttributionLink:
    """Attributed edge from pathology evidence to a clinical object.

    Attributes
    ----------
    pathology : PathologyReference
        Non-recursive reference to the pathology evidence being attributed.
    target : ClinicalObjectReference
        Non-recursive clinical target reference; does not own the target object.
    status : AttributionStatus
        Attribution strength/origin; unresolved statuses cannot establish
        resolved links.
    source : SourceValue
        Optional provenance. SourceRef and SourceLocator identify evidence, not
        clinical events.
    """

    pathology: PathologyReference
    """Non-recursive reference to the pathology evidence being attributed."""
    target: ClinicalObjectReference
    """Non-recursive clinical target reference; does not own the target object."""
    status: AttributionStatus
    """Attribution strength/origin; unresolved statuses cannot establish resolved links."""
    source: SourceValue
    """Optional provenance. SourceRef and SourceLocator identify evidence, not clinical events."""

    def __post_init__(self) -> None:
        status = AttributionStatus(self.status)
        if not status.is_resolved_attribution:
            raise ValueError("A resolved pathology link requires attribution status")
        object.__setattr__(self, "status", status)
        if self.source != self.pathology.source:
            raise ValueError("Pathology link provenance must match pathology source")

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "pathology": self.pathology.to_dict(),
            "target": self.target.to_dict(),
            "status": self.status.value,
            "source": self.source.to_dict(),
        }


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _severity_value(value: Any) -> Any:
    """Keep representable severity values for optional validation."""

    if isinstance(value, PathologySeverity):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return value


def _json_value(value: Any) -> Any:
    return plain_value(value)
