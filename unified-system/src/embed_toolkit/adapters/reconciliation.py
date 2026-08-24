"""Typed evidence records for clinical/image reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from embed_toolkit.core.provenance import SourceLocator
from embed_toolkit.imaging.images import MammogramImage


class PatientIdentityCheckStatus(str, Enum):
    """Result of comparing populated clinical and image patient identities."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class UnmatchedImageReason(str, Enum):
    """Stable reasons why an image was not attached to a clinical exam."""

    MISSING_ACCESSION = "missing_accession"
    ACCESSION_NOT_IN_CLINICAL_GRAPH = "accession_not_in_clinical_graph"
    PATIENT_IDENTITY_CONFLICT = "patient_identity_conflict"


def _validated_sources(
    image: MammogramImage,
    sources: Tuple[SourceLocator, ...],
) -> Tuple[SourceLocator, ...]:
    if not isinstance(image, MammogramImage):
        raise TypeError("image must be a MammogramImage")
    normalized = tuple(sources)
    if not normalized:
        raise ValueError("sources must contain at least one SourceLocator")
    if any(not isinstance(source, SourceLocator) for source in normalized):
        raise TypeError("sources must contain only SourceLocator values")
    if len(set(normalized)) != len(normalized):
        raise ValueError("sources must contain unique SourceLocator values")
    if normalized != tuple(image.sources):
        raise ValueError("sources must preserve the image source ledger")
    return normalized


@dataclass(frozen=True)
class ExamImageContainmentLink:
    """Evidence-backed attachment of one image to one clinical exam."""

    accession_number: str
    image: MammogramImage
    patient_identity_status: PatientIdentityCheckStatus
    sources: Tuple[SourceLocator, ...]

    def __post_init__(self) -> None:
        validated_sources = _validated_sources(self.image, self.sources)
        if (
            not isinstance(self.accession_number, str)
            or not self.accession_number.strip()
        ):
            raise ValueError("accession_number must be a non-empty string")
        if self.image.accession_number != self.accession_number:
            raise ValueError("image accession_number must match containment accession")
        object.__setattr__(
            self,
            "patient_identity_status",
            PatientIdentityCheckStatus(self.patient_identity_status),
        )
        object.__setattr__(
            self,
            "sources",
            validated_sources,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "image_reference": self.image.image_id,
            "patient_identity_status": self.patient_identity_status.value,
            "sources": [source.to_dict() for source in self.sources],
        }


@dataclass(frozen=True)
class UnmatchedImage:
    """An image excluded from exam containment with an explicit reason."""

    image: MammogramImage
    reason: UnmatchedImageReason
    sources: Tuple[SourceLocator, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", UnmatchedImageReason(self.reason))
        object.__setattr__(
            self,
            "sources",
            _validated_sources(self.image, self.sources),
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "image_reference": self.image.image_id,
            "reason": self.reason.value,
            "sources": [source.to_dict() for source in self.sources],
        }


@dataclass(frozen=True)
class FindingImageCandidate:
    """An evidence-bearing image entry in a finding candidate projection."""

    image: MammogramImage
    patient_identity_status: PatientIdentityCheckStatus
    sources: Tuple[SourceLocator, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "patient_identity_status",
            PatientIdentityCheckStatus(self.patient_identity_status),
        )
        object.__setattr__(
            self,
            "sources",
            _validated_sources(self.image, self.sources),
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "image_reference": self.image.image_id,
            "patient_identity_status": self.patient_identity_status.value,
            "sources": [source.to_dict() for source in self.sources],
        }
