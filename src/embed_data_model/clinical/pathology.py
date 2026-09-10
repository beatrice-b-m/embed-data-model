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
    """Governed EMBED pathology severities without inferred labels."""

    SEVERITY_0 = 0
    SEVERITY_1 = 1
    SEVERITY_2 = 2
    SEVERITY_3 = 3
    SEVERITY_4 = 4
    SEVERITY_5 = 5


class PathologyRecordKind(str, Enum):
    """Addressable pathology grains represented by attribution links."""

    OBSERVATION = "observation"
    DIAGNOSIS = "diagnosis"


class PathologyObservation(MutableEntity):
    """One mutable descriptor occurrence in an ordered source slot."""

    def __init__(
        self,
        descriptor: str,
        source_slot: str,
        source_ordinal: int,
        source: Optional[object] = None,
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
        return self.source_slot, self.source_ordinal

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "descriptor": self.descriptor,
            "source_slot": self.source_slot,
            "source_ordinal": self.source_ordinal,
            "source": self.source,
        }

    def to_dict(self) -> Dict[str, Any]:
        return serialize_entity(self)


class PathologyDiagnosis(MutableEntity):
    """Mutable diagnosis evidence with an explicit documentation date."""

    def __init__(
        self,
        source: Optional[object] = None,
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
        return serialize_entity(self)


class Pathology(MutableEntity):
    """A mutable pathology report bundle at one semantic attachment grain.

    ``identity`` is deliberately supplied by the adapter.  It should be a
    hashable patient-scoped record ID or the documented attachment/date
    fallback; this class never invents an identity from a physical row or
    diagnosis payload.  Descriptor order and duplicate values are retained.
    """

    __key_fields__ = ("identity",)

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
        source: Optional[object] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        payload: Optional[Mapping[str, Any]] = None,
        **identity_parts: Any,
    ) -> None:
        super().__init__()
        if identity is None:
            identity = _fallback_pathology_identity(identity_parts)
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
        return tuple(self._descriptors)

    @descriptors.setter
    def descriptors(self, values: Iterable[Any]) -> None:
        self._descriptors = list(values)

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    @metadata.setter
    def metadata(self, values: Mapping[str, Any]) -> None:
        self._metadata = dict(values)

    @property
    def payload(self) -> Dict[str, Any]:
        return self._payload

    @payload.setter
    def payload(self, values: Mapping[str, Any]) -> None:
        self._payload = dict(values)

    def add_descriptor(self, descriptor: Any) -> Any:
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
        return serialize_entity(self)


class CancerRegistryEntry(MutableEntity):
    """Patient-scoped registry data that may be assigned to several exams."""

    __key_fields__ = ("patient_id", "registry_id")

    def __init__(
        self,
        patient_id: str,
        registry_id: str,
        payload: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        source: Optional[object] = None,
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
        return self.patient_id, self.registry_id

    @property
    def payload(self) -> Mapping[str, Any]:
        return self._payload

    @payload.setter
    def payload(self, values: Mapping[str, Any]) -> None:
        self._payload = dict(values)

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    @metadata.setter
    def metadata(self, values: Mapping[str, Any]) -> None:
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
        return serialize_entity(self)


@dataclass(frozen=True)
class PathologyReference:
    """Non-recursive reference to one pathology diagnosis or observation."""

    kind: PathologyRecordKind
    source: SourceValue
    source_slot: Optional[str] = None

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
        return {
            "kind": self.kind.value,
            "source": self.source.to_dict(),
            "source_slot": self.source_slot,
        }


@dataclass(frozen=True)
class PathologyAttributionLink:
    """Attributed edge from pathology evidence to a clinical object."""

    pathology: PathologyReference
    target: ClinicalObjectReference
    status: AttributionStatus
    source: SourceValue

    def __post_init__(self) -> None:
        status = AttributionStatus(self.status)
        if not status.is_resolved_attribution:
            raise ValueError("A resolved pathology link requires attribution status")
        object.__setattr__(self, "status", status)
        if self.source != self.pathology.source:
            raise ValueError("Pathology link provenance must match pathology source")

    def to_dict(self) -> Dict[str, Any]:
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


def _fallback_pathology_identity(parts: Mapping[str, Any]) -> Hashable:
    """Build only documented fallback identities supplied by an adapter."""

    record_id = parts.get("record_id")
    patient_id = parts.get("patient_id")
    if record_id is not None and patient_id is not None:
        return patient_id, record_id
    attachment = parts.get("attachment_identity")
    report_date = parts.get("report_documented_date")
    if attachment is not None and report_date is not None:
        try:
            hash(attachment)
        except TypeError as exc:
            raise TypeError("attachment_identity must be hashable") from exc
        return attachment, report_date
    raise TypeError(
        "Pathology requires a hashable identity or patient_id/record_id "
        "or attachment_identity/report_documented_date"
    )


def _json_value(value: Any) -> Any:
    return plain_value(value)
