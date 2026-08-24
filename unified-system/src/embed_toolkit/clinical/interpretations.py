"""Finding-level imaging interpretation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from embed_toolkit.core.provenance import AvailabilityState, SourceLocator


@dataclass(frozen=True)
class ImagingInterpretation:
    """Assessment and recommendation documented for one finding."""

    accession_number: str
    finding_number: str
    source: SourceLocator
    assessment: Optional[str] = None
    assessment_availability: AvailabilityState = AvailabilityState.BOUND
    recommendation: Optional[str] = None
    recommendation_availability: AvailabilityState = AvailabilityState.BOUND

    def __post_init__(self) -> None:
        for attribute in ("accession_number", "finding_number"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        for field_name in ("assessment", "recommendation"):
            availability_name = f"{field_name}_availability"
            availability = AvailabilityState(getattr(self, availability_name))
            object.__setattr__(self, availability_name, availability)
            if availability is not AvailabilityState.BOUND and getattr(
                self, field_name
            ) is not None:
                raise ValueError(
                    f"{field_name} must be null unless availability is bound"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding": {
                "accession_number": self.accession_number,
                "finding_number": self.finding_number,
            },
            "source": self.source.to_dict(),
            "assessment": self.assessment,
            "assessment_availability": self.assessment_availability.value,
            "recommendation": self.recommendation,
            "recommendation_availability": self.recommendation_availability.value,
        }
