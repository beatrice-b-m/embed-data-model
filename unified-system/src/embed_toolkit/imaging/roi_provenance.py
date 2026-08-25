"""Scoped ROI locators and governed source provenance contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from embed_toolkit.core.primitives import ImageModality
from embed_toolkit.core.provenance import SourceLocator


class RoiLocatorKind(str, Enum):
    """Whether an ROI locator came from the source or this materialization."""

    SOURCE_SUPPLIED = "source_supplied"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True)
class RoiLocator:
    """Address one ROI without implying a cross-release source identity.

    Both locator forms are scoped through the source locator for their owning
    image occurrence. A source-supplied value is therefore only an identifier
    within that explicit source boundary. A synthetic locator uses the ROI's
    ordinal in the image occurrence instead of manufacturing a durable string.
    """

    kind: RoiLocatorKind
    image_locator: SourceLocator
    source_value: Optional[str] = None
    source_ordinal: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", RoiLocatorKind(self.kind))
        if not isinstance(self.image_locator, SourceLocator):
            raise ValueError("image_locator must be a scoped SourceLocator")
        if self.kind is RoiLocatorKind.SOURCE_SUPPLIED:
            if not isinstance(self.source_value, str) or not self.source_value.strip():
                raise ValueError(
                    "Source-supplied ROI locators require a non-empty source_value"
                )
            if self.source_ordinal is not None:
                raise ValueError(
                    "Source-supplied ROI locators cannot have a source_ordinal"
                )
            return

        if self.source_value is not None:
            raise ValueError("Synthetic ROI locators cannot have a source_value")
        if (
            isinstance(self.source_ordinal, bool)
            or not isinstance(self.source_ordinal, int)
            or self.source_ordinal < 0
        ):
            raise ValueError(
                "Synthetic ROI locators require a non-negative source_ordinal"
            )

    @classmethod
    def from_source(
        cls,
        *,
        image_locator: SourceLocator,
        source_value: str,
    ) -> "RoiLocator":
        """Build a locator for a value explicitly supplied by the source."""

        return cls(
            kind=RoiLocatorKind.SOURCE_SUPPLIED,
            image_locator=image_locator,
            source_value=source_value,
        )

    @classmethod
    def synthetic(
        cls,
        *,
        image_locator: SourceLocator,
        source_ordinal: int,
    ) -> "RoiLocator":
        """Build a materialization-scoped positional ROI locator."""

        return cls(
            kind=RoiLocatorKind.SYNTHETIC,
            image_locator=image_locator,
            source_ordinal=source_ordinal,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-ready scoped locator."""

        return {
            "kind": self.kind.value,
            "image_locator": self.image_locator.to_dict(),
            "source_value": self.source_value,
            "source_ordinal": self.source_ordinal,
        }


class RoiSourceCountBasis(str, Enum):
    """Evidence establishing the number of ROI occurrences in a source row."""

    SOURCE_DECLARED = "source_declared"
    ALIGNED_COORDINATE_COLLECTION = "aligned_coordinate_collection"
    SINGLE_COORDINATE_OCCURRENCE = "single_coordinate_occurrence"


@dataclass(frozen=True)
class RoiSourceCount:
    """A positive source occurrence count with an explicit evidence basis."""

    value: int
    basis: RoiSourceCountBasis

    def __post_init__(self) -> None:
        object.__setattr__(self, "basis", RoiSourceCountBasis(self.basis))
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise ValueError("ROI source count must be an integer")
        if self.value <= 0:
            raise ValueError("ROI source count must be positive")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-ready count and its evidence basis."""

        return {"value": self.value, "basis": self.basis.value}


class RoiDepthFrameProvenance(str, Enum):
    """Provenance for ROI depth placement expressed through DBT frames."""

    NOT_APPLICABLE_2D = "not_applicable_2d"
    SOURCE_SUPPLIED = "source_supplied"
    DERIVED = "derived"
    UNAVAILABLE_DBT = "unavailable_dbt"
    UNRESOLVED_MODALITY = "unresolved_modality"


@dataclass(frozen=True)
class RoiSourceProvenance:
    """Govern source multiplicity and depth/frame meaning for one ROI.

    FFDM and synthetic-2D ROIs cannot carry DBT frame indices. DBT ROIs may
    carry source-supplied or explicitly derived indices; an empty index set is
    represented as unavailable rather than being treated as a 2D ROI. Unknown
    modality preserves image-local geometry without interpreting frame data.
    """

    modality: ImageModality
    source_count: RoiSourceCount
    depth_frame_provenance: RoiDepthFrameProvenance
    frame_indices: Tuple[int, ...] = ()
    derivation_method: Optional[str] = None

    def __post_init__(self) -> None:
        modality = ImageModality.coerce(self.modality)
        provenance = RoiDepthFrameProvenance(self.depth_frame_provenance)
        if not isinstance(self.source_count, RoiSourceCount):
            raise ValueError("source_count must be a governed RoiSourceCount")
        indices = tuple(self.frame_indices)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in indices
        ):
            raise ValueError("ROI frame indices must be non-negative integers")
        if len(set(indices)) != len(indices):
            raise ValueError("ROI frame indices cannot contain duplicates")
        object.__setattr__(self, "modality", modality)
        object.__setattr__(self, "depth_frame_provenance", provenance)
        object.__setattr__(self, "frame_indices", indices)

        if provenance is RoiDepthFrameProvenance.DERIVED:
            if (
                not isinstance(self.derivation_method, str)
                or not self.derivation_method.strip()
            ):
                raise ValueError(
                    "Derived DBT frame provenance requires a derivation_method"
                )
        elif self.derivation_method is not None:
            raise ValueError(
                "derivation_method is only valid for derived frame provenance"
            )

        if modality is ImageModality.UNKNOWN:
            if provenance is not RoiDepthFrameProvenance.UNRESOLVED_MODALITY:
                raise ValueError(
                    "Unknown-modality ROI provenance must be unresolved_modality"
                )
            if indices:
                raise ValueError(
                    "Unknown-modality ROI provenance cannot interpret frame indices"
                )
            return
        if modality is not ImageModality.DBT:
            if indices:
                raise ValueError("2D ROI provenance cannot contain DBT frame indices")
            if provenance is not RoiDepthFrameProvenance.NOT_APPLICABLE_2D:
                raise ValueError(
                    "2D ROI provenance must be marked not_applicable_2d"
                )
            return

        if provenance is RoiDepthFrameProvenance.NOT_APPLICABLE_2D:
            raise ValueError("DBT ROI provenance cannot be marked as 2D")
        if indices and provenance is RoiDepthFrameProvenance.UNAVAILABLE_DBT:
            raise ValueError(
                "DBT frame provenance cannot be unavailable when indices exist"
            )
        if not indices and provenance is not RoiDepthFrameProvenance.UNAVAILABLE_DBT:
            raise ValueError(
                "DBT ROI provenance without frame indices must be unavailable_dbt"
            )

    def validate_locator(self, locator: RoiLocator) -> None:
        """Validate positional locator bounds against the governed source count."""

        if (
            locator.kind is RoiLocatorKind.SYNTHETIC
            and locator.source_ordinal is not None
            and locator.source_ordinal >= self.source_count.value
        ):
            raise ValueError("Synthetic ROI source_ordinal exceeds source count")

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-ready source and depth/frame provenance."""

        return {
            "modality": self.modality.value,
            "source_count": self.source_count.to_dict(),
            "depth_frame_provenance": self.depth_frame_provenance.value,
            "frame_indices": list(self.frame_indices),
            "derivation_method": self.derivation_method,
        }
