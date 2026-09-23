"""Mutable patient-reported history observations.

History rows without an explicit ``record_id`` are snapshots of one patient
history collection. Their source location is provenance and never becomes a
clinical event identity.
"""

from __future__ import annotations

from numbers import Real
from typing import Any, Dict, Optional, Tuple

from embed_data_model.core.entity import MutableEntity, serialize_entity
from embed_data_model.core.primitives import Laterality
from embed_data_model.core.source import SourceRef, optional_source




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


def _source_dict(source: Optional[SourceRef]) -> Optional[Dict[str, object]]:
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
    """Partial reported timing with raw numeric components.

    Parameters
    ----------
    age : Optional[float], optional
        Reported age in years; None means absent. Numeric values are retained
        for optional plausibility checks. Default: None.
    year : Optional[float], optional
        Reported calendar year; None means absent, without imputation. Default:
        None.
    month : Optional[float], optional
        Reported month number (normally 1–12); None means absent. Range checked
        by validate. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.
    """

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
        """True when age, year and month are all None; zero is a supplied value."""

        return self.age is None and self.year is None and self.month is None

    def _to_dict_data(self, state: Any) -> Dict[str, object]:
        return {"age": self.age, "year": self.year, "month": self.month}

    def to_dict(self) -> Dict[str, object]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


class PatientHistoryObservation(MutableEntity):
    """Base for a patient-reported fact or an explicitly keyed record.

    Parameters
    ----------
    patient_id : str
        Patient identifier. Non-empty text; source patient claims and assigned
        exam ownership are separate facts.
    source : Optional[SourceRef], optional
        Optional SourceRef locating the source row; evidence, not a
        clinical event. Default: None.
    record_id : Optional[object], optional
        Explicit patient-scoped record ID, converted to stripped text when
        supplied. None represents an unkeyed reported fact. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.
    """

    __key_fields__ = ("patient_id", "record_id")

    def __init__(
        self,
        patient_id: str,
        source: Optional[SourceRef] = None,
        record_id: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.patient_id = _required_text(patient_id, "patient_id")
        self.source = optional_source(source)
        self.record_id = _record_id(record_id)

    @property
    def identity(self) -> Tuple[str, Optional[str]]:
        """Use only a supplied record ID; source rows do not identify events."""

        return self.patient_id, self.record_id

    def reference_dict(self) -> Dict[str, object]:
        """Return a new non-recursive reference dictionary with identity and source
        evidence; this does not serialize the full observation.
        """

        return {
            "patient_id": self.patient_id,
            "record_id": self.record_id,
            "source": _source_dict(self.source),
        }

    def _to_dict_data(self, state: Any) -> Dict[str, object]:
        return self.reference_dict()

    def to_dict(self) -> Dict[str, object]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


class MedicationHistoryObservation(PatientHistoryObservation):
    """A reported hormone, medication, contraceptive, or treatment exposure.

    Parameters
    ----------
    patient_id : str
        Patient identifier. Non-empty text; source patient claims and assigned
        exam ownership are separate facts.
    source : Optional[SourceRef], optional
        Optional SourceRef locating the source row; evidence, not a
        clinical event. Default: None.
    category : str, optional
        Non-empty reported category. Although the default is empty, callers must
        supply a non-empty value. Default: ''.
    medication : str, optional
        Non-empty reported medication code/name. The empty default is rejected.
        Default: ''.
    context_accession : Optional[str], optional
        Exam context in which the history was reported; not proof the event
        occurred at that exam. Default: None.
    continuous : Optional[bool], optional
        Whether continuous exposure was reported; None means unknown. Default:
        None.
    current : Optional[bool], optional
        Whether current exposure was reported; None means unknown. Default:
        None.
    reported_duration : Optional[str], optional
        Raw duration text; no units or numeric duration are inferred. Default:
        None.
    started : Optional[HistoryTimeEstimate], optional
        Optional partial reported start timing, retained by reference; an empty
        estimate becomes None. Default: None.
    stopped : Optional[HistoryTimeEstimate], optional
        Optional partial reported stop timing, retained by reference; an empty
        estimate becomes None. Default: None.
    comment : Optional[str], optional
        Optional source comment; blank text normalizes to None. Default: None.
    record_id : Optional[object], optional
        Explicit patient-scoped record ID, converted to stripped text when
        supplied. None represents an unkeyed reported fact. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.
    """

    continuous: Optional[bool]
    """Whether continuous exposure was reported; None means unknown."""
    current: Optional[bool]
    """Whether current exposure was reported; None means unknown."""

    def __init__(
        self,
        patient_id: str,
        source: Optional[SourceRef] = None,
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
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


class ProcedureHistoryObservation(PatientHistoryObservation):
    """A reported prior procedure, separate from verified procedures.

    Parameters
    ----------
    patient_id : str
        Patient identifier. Non-empty text; source patient claims and assigned
        exam ownership are separate facts.
    source : Optional[SourceRef], optional
        Optional SourceRef locating the source row; evidence, not a
        clinical event. Default: None.
    category : str, optional
        Non-empty reported category. Although the default is empty, callers must
        supply a non-empty value. Default: ''.
    procedure : str, optional
        Non-empty reported procedure code/name. The empty default is rejected.
        Default: ''.
    detail : Optional[str], optional
        Optional reported procedure detail; blank text normalizes to None.
        Default: None.
    context_accession : Optional[str], optional
        Exam context in which the history was reported; not proof the event
        occurred at that exam. Default: None.
    laterality : Laterality, optional
        Breast side. Coercible values are normalized; unknown values become
        UNKNOWN where coercion is supported. Default: Laterality.UNKNOWN.
    reported_result : Optional[str], optional
        Optional reported prior procedure result; blank text normalizes to None.
        Default: None.
    record_id : Optional[object], optional
        Explicit patient-scoped record ID, converted to stripped text when
        supplied. None represents an unkeyed reported fact. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.
    """

    def __init__(
        self,
        patient_id: str,
        source: Optional[SourceRef] = None,
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
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

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
