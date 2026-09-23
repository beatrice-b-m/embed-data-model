"""Source-attributed observations of exam facts and patient attributes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Optional, Tuple

from embed_data_model.core.entity import MutableEntity, serialize_entity
from embed_data_model.core.source import SourceRef, optional_source




class ExamAttributeName(str, Enum):
    """Governed invariant attributes reconciled across exam source rows.

    Members
    -------
    EXAM_DATE='exam_date', DESCRIPTION='description'.
    """

    EXAM_DATE = "exam_date"
    DESCRIPTION = "description"


def _source_dict(source: Optional[SourceRef]) -> Optional[dict[str, object]]:
    return None if source is None else source.to_dict()


class ExamAttributeObservation(MutableEntity):
    """One source-attributed observation of an invariant exam fact.

    Parameters
    ----------
    accession_number : str
        Non-empty exam accession identifying the clinical examination.
    attribute : ExamAttributeName
        Governed attribute name identifying which fact the observation
        represents.
    value : Optional[str]
        Reported value, including explicit None; missing values are not silently
        filled.
    source : Optional[SourceRef], optional
        Optional SourceRef locating the source row; evidence, not a
        clinical event. Default: None.

    Notes
    -----
    Scalar fields are mutable. Constructor parameters describe the initial public
    fields; collection properties document their views. Use update/rekey to keep
    registered identities and relationships coherent. Construction checks basic
    representation; validate performs optional quality checks. No files are owned.
    """

    __key_fields__ = ("accession_number", "attribute", "source")

    value: Optional[str]
    """Reported value, including explicit None; missing values are not silently filled."""

    def __init__(
        self,
        accession_number: str,
        attribute: ExamAttributeName,
        value: Optional[str],
        source: Optional[SourceRef] = None,
    ) -> None:
        super().__init__()
        if not isinstance(accession_number, str) or not accession_number.strip():
            raise ValueError("accession_number must be a non-empty string")
        self.accession_number = accession_number.strip()
        self.attribute = ExamAttributeName(attribute)
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise TypeError("exam attribute value must be a string or None")
            value = value.strip()
        self.value = value
        self.source = optional_source(source)
        self._finish_initialization()

    @property
    def identity(self) -> Tuple[str, ExamAttributeName, Optional[SourceRef]]:
        """Semantic identity used for equality of addresses, independent of Python object identity."""

        return self.accession_number, self.attribute, self.source

    def reference_dict(self) -> dict[str, object]:
        """Return a new non-recursive reference dictionary with identity and source
        evidence; this does not serialize the full observation.
        """

        return {
            "accession_number": self.accession_number,
            "attribute": self.attribute.value,
            "source": _source_dict(self.source),
        }

    def _to_dict_data(self, state: Any) -> dict[str, object]:
        return {**self.reference_dict(), "value": self.value}

    def to_dict(self) -> dict[str, object]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)


@dataclass(frozen=True)
class PatientAttributeObservation:
    """One reported value of a patient attribute in one exam context.

    Patient attributes such as sex repeat on every exam row and may change over
    time or disagree because of data quality. Each observation keeps the value
    reported in one context so a consumer can choose a value as of an explicit
    date, without leaking later information into an earlier analysis.

    Attributes
    ----------
    attribute : str
        Attribute name, such as ``"sex"``.
    value : Any
        Reported value; None records an explicitly supplied null.
    accession_number : str or None, optional
        Exam accession whose row reported the value. Default None.
    context_date : datetime.date or None, optional
        Date of that exam context (the exam date), not necessarily when the
        attribute became true. Default None means undated.

    Examples
    --------
    >>> from datetime import date
    >>> PatientAttributeObservation("sex", "F", "A1", date(2020, 1, 2)).context
    ('sex', 'A1', datetime.date(2020, 1, 2))
    """

    attribute: str
    """Attribute name, such as ``"sex"``."""
    value: Any
    """Reported value; None records an explicitly supplied null."""
    accession_number: Optional[str] = None
    """Exam accession whose row reported the value."""
    context_date: Optional[date] = None
    """Date of the exam context; None means undated."""

    def __post_init__(self) -> None:
        if not isinstance(self.attribute, str) or not self.attribute.strip():
            raise ValueError("attribute must be a non-empty string")
        if self.context_date is not None and type(self.context_date) is not date:
            raise TypeError("context_date must be a datetime.date or None")

    @property
    def context(self) -> Tuple[str, Optional[str], Optional[date]]:
        """Return ``(attribute, accession_number, context_date)``.

        A patient keeps at most one observation per context; adding another
        with the same context replaces it.
        """

        return self.attribute, self.accession_number, self.context_date
