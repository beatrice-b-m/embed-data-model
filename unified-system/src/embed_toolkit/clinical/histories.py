"""Mutable patient-reported history observations.

History rows without an explicit ``record_id`` are snapshots of one patient
history collection. Their source location is provenance and never becomes a
clinical event identity.
"""

from __future__ import annotations

from numbers import Real
from typing import Any, Dict, Optional, Tuple, Union

from embed_toolkit.core.entity import MutableEntity, serialize_entity
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import SourceLocator
from embed_toolkit.core.source import SourceRef


SourceValue = Union[SourceLocator, SourceRef]


def _optional_text(value: Optional[str], name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    value = value.strip()
    return value or None


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_source(source: Optional[object]) -> Optional[SourceValue]:
    if source is not None and not isinstance(source, (SourceLocator, SourceRef)):
        raise TypeError("source must be a SourceRef or SourceLocator")
    return source


def _source_dict(source: Optional[SourceValue]) -> Optional[Dict[str, object]]:
    return None if source is None else source.to_dict()


def _record_id(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("record_id must be a non-empty value when supplied")
    return normalized


def _raw_number(value: Optional[float], name: str) -> Optional[float]:
    """Retain numeric history facts without imposing clinical ranges."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be numeric or None")
    return value


class HistoryTimeEstimate(MutableEntity):
    """Partial reported timing with raw numeric components."""

    def __init__(
        self,
        age: Optional[float] = None,
        year: Optional[float] = None,
        month: Optional[float] = None,
    ) -> None:
        super().__init__()
        self.age = _raw_number(age, "age")
        self.year = _raw_number(year, "year")
        self.month = _raw_number(month, "month")
        self._finish_initialization()

    @property
    def is_empty(self) -> bool:
        return self.age is None and self.year is None and self.month is None

    def _to_dict_data(self, state: Any) -> Dict[str, object]:
        return {"age": self.age, "year": self.year, "month": self.month}

    def to_dict(self) -> Dict[str, object]:
        return serialize_entity(self)


class PatientHistoryObservation(MutableEntity):
    """Base for a patient-reported fact or an explicitly keyed record."""

    __key_fields__ = ("patient_id", "record_id")

    def __init__(
        self,
        patient_id: str,
        source: Optional[object] = None,
        record_id: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.patient_id = _required_text(patient_id, "patient_id")
        self.source = _optional_source(source)
        self.record_id = _record_id(record_id)

    @property
    def identity(self) -> Tuple[str, Optional[str]]:
        """Use only a supplied record ID; source rows do not identify events."""

        return self.patient_id, self.record_id

    def reference_dict(self) -> Dict[str, object]:
        return {
            "patient_id": self.patient_id,
            "record_id": self.record_id,
            "source": _source_dict(self.source),
        }

    def _to_dict_data(self, state: Any) -> Dict[str, object]:
        return self.reference_dict()

    def to_dict(self) -> Dict[str, object]:
        return serialize_entity(self)


class MedicationHistoryObservation(PatientHistoryObservation):
    """A reported hormone, medication, contraceptive, or treatment exposure."""

    def __init__(
        self,
        patient_id: str,
        source: Optional[object] = None,
        category: str = "",
        medication: str = "",
        context_accession: Optional[str] = None,
        continuous: Optional[bool] = None,
        current: Optional[bool] = None,
        reported_duration: Optional[str] = None,
        started: Optional[HistoryTimeEstimate] = None,
        stopped: Optional[HistoryTimeEstimate] = None,
        comment: Optional[str] = None,
        record_id: Optional[object] = None,
    ) -> None:
        super().__init__(patient_id, source, record_id)
        self.category = _required_text(category, "category")
        self.medication = _required_text(medication, "medication")
        for attribute, value in (
            ("continuous", continuous),
            ("current", current),
        ):
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{attribute} must be bool or None")
        self.context_accession = _optional_text(
            context_accession, "context_accession"
        )
        self.continuous = continuous
        self.current = current
        self.reported_duration = _optional_text(
            reported_duration, "reported_duration"
        )
        self.started = _optional_time(started, "started")
        self.stopped = _optional_time(stopped, "stopped")
        self.comment = _optional_text(comment, "comment")
        self._finish_initialization()

    def _to_dict_data(self, state: Any) -> Dict[str, object]:
        return {
            **self.reference_dict(),
            "category": self.category,
            "medication": self.medication,
            "context_accession": self.context_accession,
            "continuous": self.continuous,
            "current": self.current,
            "reported_duration": self.reported_duration,
            "started": self.started,
            "stopped": self.stopped,
            "comment": self.comment,
        }

    def to_dict(self) -> Dict[str, object]:
        return serialize_entity(self)


class ProcedureHistoryObservation(PatientHistoryObservation):
    """A reported prior procedure, separate from verified procedures."""

    def __init__(
        self,
        patient_id: str,
        source: Optional[object] = None,
        category: str = "",
        procedure: str = "",
        detail: Optional[str] = None,
        context_accession: Optional[str] = None,
        laterality: Laterality = Laterality.UNKNOWN,
        reported_result: Optional[str] = None,
        record_id: Optional[object] = None,
    ) -> None:
        super().__init__(patient_id, source, record_id)
        self.category = _required_text(category, "category")
        self.procedure = _required_text(procedure, "procedure")
        self.detail = _optional_text(detail, "detail")
        self.context_accession = _optional_text(
            context_accession, "context_accession"
        )
        self.laterality = Laterality.coerce(laterality)
        self.reported_result = _optional_text(reported_result, "reported_result")
        self._finish_initialization()

    def _to_dict_data(self, state: Any) -> Dict[str, object]:
        return {
            **self.reference_dict(),
            "category": self.category,
            "procedure": self.procedure,
            "detail": self.detail,
            "context_accession": self.context_accession,
            "laterality": self.laterality.value,
            "reported_result": self.reported_result,
        }

    def to_dict(self) -> Dict[str, object]:
        return serialize_entity(self)


def _optional_time(
    value: Optional[HistoryTimeEstimate],
    name: str,
) -> Optional[HistoryTimeEstimate]:
    if value is not None and not isinstance(value, HistoryTimeEstimate):
        raise TypeError(f"{name} must be HistoryTimeEstimate or None")
    if value is not None and value.is_empty:
        return None
    return value
