"""Mutable finding-level imaging interpretation contracts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple, Union

from embed_data_model.core.entity import MutableEntity, serialize_entity
from embed_data_model.core.provenance import AvailabilityState, SourceLocator
from embed_data_model.core.source import SourceRef


SourceValue = Union[SourceLocator, SourceRef]


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_source(source: Optional[object]) -> Optional[SourceValue]:
    if source is not None and not isinstance(source, (SourceLocator, SourceRef)):
        raise TypeError("source must be a SourceRef or SourceLocator")
    return source


class ImagingInterpretation(MutableEntity):
    """Assessment and recommendation documented for one finding.

    Parameters
    ----------
    accession_number : str
        Non-empty exam accession identifying the clinical examination.
    finding_number : str
        Non-empty finding identifier scoped to its accession; not a row ordinal.
    sources : Optional[Iterable[Optional[object]]], optional
        Source evidence in supplied order. None starts an empty collection;
        source adds one item. Default: None.
    assessment : Optional[str], optional
        Reported assessment code/text; None means missing and no category is
        inferred. Default: None.
    assessment_availability : AvailabilityState, optional
        Binding status; assessment must be None unless status is BOUND. Default:
        AvailabilityState.BOUND.
    recommendation : Optional[str], optional
        Reported recommendation; None means missing. Default: None.
    recommendation_availability : AvailabilityState, optional
        Binding status; recommendation must be None unless status is BOUND.
        Default: AvailabilityState.BOUND.
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

    __key_fields__ = ("accession_number", "finding_number")

    assessment: Optional[str]
    """Reported assessment code/text; None means missing and no category is inferred."""
    recommendation: Optional[str]
    """Reported recommendation; None means missing."""

    def __init__(
        self,
        accession_number: str,
        finding_number: str,
        sources: Optional[Iterable[Optional[object]]] = None,
        assessment: Optional[str] = None,
        assessment_availability: AvailabilityState = AvailabilityState.BOUND,
        recommendation: Optional[str] = None,
        recommendation_availability: AvailabilityState = AvailabilityState.BOUND,
        source: Optional[SourceValue] = None,
    ) -> None:
        super().__init__()
        self.accession_number = _required_text(accession_number, "accession_number")
        self.finding_number = _required_text(finding_number, "finding_number")
        source_values: Tuple[Optional[SourceValue], ...]
        if isinstance(sources, (SourceLocator, SourceRef)):
            source_values = (sources,)
        elif sources is None:
            source_values = ()
        else:
            source_values = tuple(_optional_source(value) for value in sources)
        if source is not None:
            source_values = source_values + (_optional_source(source),)
        self._sources = self._validate_sources(source_values)
        self.assessment = assessment
        self.assessment_availability = AvailabilityState(assessment_availability)
        self.recommendation = recommendation
        self.recommendation_availability = AvailabilityState(
            recommendation_availability
        )
        self._validate_availability()
        self._finish_initialization()

    @staticmethod
    def _validate_sources(
        values: Iterable[Optional[object]],
    ) -> Tuple[Optional[SourceValue], ...]:
        sources = tuple(_optional_source(value) for value in values)
        if len(set(sources)) != len(sources):
            raise ValueError("sources must contain unique SourceLocator values")
        return sources

    def _validate_availability(self) -> None:
        for field_name in ("assessment", "recommendation"):
            availability_name = f"{field_name}_availability"
            availability = AvailabilityState(getattr(self, availability_name))
            setattr(self, availability_name, availability)
            if availability is not AvailabilityState.BOUND and getattr(
                self, field_name
            ) is not None:
                raise ValueError(
                    f"{field_name} must be null unless availability is bound"
                )

    @property
    def identity(self) -> Tuple[str, str]:
        """Finding identity governed by this interpretation."""

        return self.accession_number, self.finding_number

    @property
    def sources(self) -> Tuple[Optional[SourceValue], ...]:
        """Tuple of retained source evidence in insertion order.
        """

        return self._sources

    @sources.setter
    def sources(self, values: Iterable[Optional[object]]) -> None:
        """Tuple of retained source evidence in insertion order."""

        self._sources = self._validate_sources(values)

    @property
    def source(self) -> Optional[SourceValue]:
        """Convenience access to the first source, when one is available."""

        return self._sources[0] if self._sources else None

    @source.setter
    def source(self, value: Optional[object]) -> None:
        """Return the first retained source, or None when sources is empty. Assignment
        replaces the entire sources collection with zero or one value.
        """

        self._sources = () if value is None else (self._optional(value),)

    @staticmethod
    def _optional(value: Optional[object]) -> Optional[SourceValue]:
        return _optional_source(value)

    def _to_dict_data(self, state: Any) -> Dict[str, Any]:
        return {
            "finding": {
                "accession_number": self.accession_number,
                "finding_number": self.finding_number,
            },
            "sources": self.sources,
            "assessment": self.assessment,
            "assessment_availability": self.assessment_availability,
            "recommendation": self.recommendation,
            "recommendation_availability": self.recommendation_availability,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a new dictionary representation of the represented fields. Nested
        entity serialization uses semantic references for repeated objects; consumer
        values are not a guaranteed lossless round trip.
        """

        return serialize_entity(self)
