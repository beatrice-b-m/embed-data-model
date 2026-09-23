"""Finding-level imaging interpretation: assessment and recommendation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

from embed_data_model.core.entity import MutableEntity, serialize_entity
from embed_data_model.core.source import SourceRef, optional_source


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


class ImagingInterpretation(MutableEntity):
    """Assessment and recommendation documented for one finding.

    Parameters
    ----------
    accession_number : str
        Non-empty exam accession identifying the clinical examination.
    finding_number : str
        Non-empty finding identifier scoped to its accession; not a row ordinal.
    sources : Optional[Iterable[SourceRef]], optional
        Distinct source rows supporting the interpretation, in supplied order.
        Default: None (no sources).
    assessment : Optional[str], optional
        Reported assessment code; None means missing and no category is
        inferred. Default: None.
    recommendation : Optional[str], optional
        Reported recommendation code string; None means missing. Default: None.

    Notes
    -----
    An assessment or recommendation is never a tissue diagnosis. Scalar fields
    are mutable; the loader refreshes them in place so consumer attributes on
    the object survive reloads.
    """

    __key_fields__ = ("accession_number", "finding_number")

    assessment: Optional[str]
    """Reported assessment code; None means missing and no category is inferred."""
    recommendation: Optional[str]
    """Reported recommendation code string; None means missing."""

    def __init__(
        self,
        accession_number: str,
        finding_number: str,
        sources: Optional[Iterable[SourceRef]] = None,
        assessment: Optional[str] = None,
        recommendation: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.accession_number = _required_text(accession_number, "accession_number")
        self.finding_number = _required_text(finding_number, "finding_number")
        self._sources = self._validate_sources(sources or ())
        self.assessment = assessment
        self.recommendation = recommendation
        self._finish_initialization()

    @staticmethod
    def _validate_sources(values: Iterable[Optional[object]]) -> Tuple[SourceRef, ...]:
        sources = tuple(value for value in (optional_source(item) for item in values) if value is not None)
        if len(set(sources)) != len(sources):
            raise ValueError("sources must be distinct")
        return sources

    @property
    def identity(self) -> Tuple[str, str]:
        """Finding identity ``(accession_number, finding_number)``."""

        return self.accession_number, self.finding_number

    @property
    def sources(self) -> Tuple[SourceRef, ...]:
        """Source rows supporting the interpretation, in insertion order."""

        return self._sources

    @sources.setter
    def sources(self, values: Iterable[SourceRef]) -> None:
        self._sources = self._validate_sources(values)

    @property
    def source(self) -> Optional[SourceRef]:
        """The first source row, or None when there is none."""

        return self._sources[0] if self._sources else None

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "finding": {
                "accession_number": self.accession_number,
                "finding_number": self.finding_number,
            },
            "sources": self.sources,
            "assessment": self.assessment,
            "recommendation": self.recommendation,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible dictionary of the interpretation fields."""

        return serialize_entity(self)
