"""Source-neutral patient-reported history observations."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Dict, Optional, Tuple

from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import SourceLocator
from embed_toolkit.core.source import SourceRef


def _optional_text(value: Optional[str], name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class HistoryTimeEstimate:
    """Partial reported timing without manufacturing date precision."""

    age: Optional[float] = None
    year: Optional[int] = None
    month: Optional[int] = None

    def __post_init__(self) -> None:
        if self.age is not None:
            if (
                isinstance(self.age, bool)
                or not isinstance(self.age, Real)
                or self.age < 0
            ):
                raise ValueError("age must be a non-negative number or None")
            object.__setattr__(self, "age", float(self.age))
        if self.year is not None:
            if (
                isinstance(self.year, bool)
                or not isinstance(self.year, int)
                or self.year < 1
            ):
                raise ValueError("year must be a positive integer or None")
        if self.month is not None:
            if (
                isinstance(self.month, bool)
                or not isinstance(self.month, int)
                or not 1 <= self.month <= 12
            ):
                raise ValueError("month must be in 1..12 or None")

    @property
    def is_empty(self) -> bool:
        return self.age is None and self.year is None and self.month is None

    def to_dict(self) -> Dict[str, object]:
        return {"age": self.age, "year": self.year, "month": self.month}


@dataclass(frozen=True)
class PatientHistoryObservation:
    """Base for one patient-reported history item at one physical source row."""

    patient_id: str
    source: object

    def __post_init__(self) -> None:
        if not isinstance(self.patient_id, str) or not self.patient_id.strip():
            raise ValueError("patient_id must be a non-empty string")
        object.__setattr__(self, "patient_id", self.patient_id.strip())
        if not isinstance(self.source, (SourceLocator, SourceRef)):
            raise TypeError("source must be a SourceRef or SourceLocator")

    @property
    def identity(self) -> Tuple[str, object]:
        """Keep repeated reports distinct by physical source occurrence."""

        return self.patient_id, self.source

    def reference_dict(self) -> Dict[str, object]:
        return {
            "patient_id": self.patient_id,
            "source": self.source.to_dict(),
        }

    def to_dict(self) -> Dict[str, object]:
        return self.reference_dict()


@dataclass(frozen=True)
class MedicationHistoryObservation(PatientHistoryObservation):
    """A reported hormone, medication, contraceptive, or treatment exposure."""

    category: str
    medication: str
    context_accession: Optional[str] = None
    continuous: Optional[bool] = None
    current: Optional[bool] = None
    reported_duration: Optional[str] = None
    started: Optional[HistoryTimeEstimate] = None
    stopped: Optional[HistoryTimeEstimate] = None
    comment: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        for attribute in ("category", "medication"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
            object.__setattr__(self, attribute, value.strip())
        for attribute in ("continuous", "current"):
            value = getattr(self, attribute)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{attribute} must be bool or None")
        for attribute in ("started", "stopped"):
            value = getattr(self, attribute)
            if value is not None and not isinstance(value, HistoryTimeEstimate):
                raise TypeError(f"{attribute} must be HistoryTimeEstimate or None")
            if value is not None and value.is_empty:
                object.__setattr__(self, attribute, None)
        for attribute in ("context_accession", "reported_duration", "comment"):
            object.__setattr__(
                self,
                attribute,
                _optional_text(getattr(self, attribute), attribute),
            )

    def to_dict(self) -> Dict[str, object]:
        return {
            **self.reference_dict(),
            "category": self.category,
            "medication": self.medication,
            "context_accession": self.context_accession,
            "continuous": self.continuous,
            "current": self.current,
            "reported_duration": self.reported_duration,
            "started": self.started.to_dict() if self.started is not None else None,
            "stopped": self.stopped.to_dict() if self.stopped is not None else None,
            "comment": self.comment,
        }


@dataclass(frozen=True)
class ProcedureHistoryObservation(PatientHistoryObservation):
    """A reported prior procedure, separate from verified clinical procedures."""

    category: str
    procedure: str
    detail: Optional[str] = None
    context_accession: Optional[str] = None
    laterality: Laterality = Laterality.UNKNOWN
    reported_result: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        for attribute in ("category", "procedure"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
            object.__setattr__(self, attribute, value.strip())
        for attribute in ("detail", "context_accession", "reported_result"):
            object.__setattr__(
                self,
                attribute,
                _optional_text(getattr(self, attribute), attribute),
            )
        object.__setattr__(self, "laterality", Laterality.coerce(self.laterality))

    def to_dict(self) -> Dict[str, object]:
        return {
            **self.reference_dict(),
            "category": self.category,
            "procedure": self.procedure,
            "detail": self.detail,
            "context_accession": self.context_accession,
            "laterality": self.laterality.value,
            "reported_result": self.reported_result,
        }
