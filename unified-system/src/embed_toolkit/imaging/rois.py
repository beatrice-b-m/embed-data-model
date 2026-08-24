"""Image-local regions of interest and intrinsic ROI geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional, Tuple

from embed_toolkit.core.provenance import SourceLocator
from embed_toolkit.imaging.roi_provenance import RoiLocator, RoiSourceProvenance


CoordinateBox = Tuple[float, float, float, float]


@dataclass(frozen=True)
class RegionOfInterest:
    """One scoped ROI observation on exactly one image.

    Geometry uses canonical half-open ``[y_min, x_min, y_stop, x_stop]``
    edges. Identity is always the structured, release-scoped ``locator``;
    neither ``image_id`` nor a generated string is an ROI identity.
    """

    coordinates: CoordinateBox
    locator: RoiLocator
    image_id: str
    source_provenance: RoiSourceProvenance
    sources: Tuple[SourceLocator, ...]
    annotation_source: Optional[str] = None
    confidence: Optional[float] = None
    coordinate_frame_id: Optional[str] = None
    source_coordinates: Optional[CoordinateBox] = None
    source_coordinate_convention: Optional[str] = None

    @classmethod
    def from_embed_coordinates(
        cls,
        coordinates: CoordinateBox,
        **metadata: object,
    ) -> "RegionOfInterest":
        """Normalize EMBED inclusive maxima to canonical exclusive stops."""

        y_min, x_min, y_max, x_max = tuple(float(value) for value in coordinates)
        if y_max < y_min or x_max < x_min:
            raise ValueError("EMBED ROI maxima must not precede minimum coordinates")
        return cls(
            coordinates=(y_min, x_min, y_max + 1.0, x_max + 1.0),
            source_coordinates=(y_min, x_min, y_max, x_max),
            source_coordinate_convention="inclusive_maxima",
            **metadata,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.locator, RoiLocator):
            raise TypeError("locator must be a RoiLocator")
        if not isinstance(self.image_id, str) or not self.image_id.strip():
            raise ValueError("image_id must be a non-empty string")
        if not isinstance(self.source_provenance, RoiSourceProvenance):
            raise TypeError("source_provenance must be a RoiSourceProvenance")
        self.source_provenance.validate_locator(self.locator)

        sources = tuple(self.sources)
        if not sources:
            raise ValueError("sources must contain at least one SourceLocator")
        if any(not isinstance(source, SourceLocator) for source in sources):
            raise TypeError("sources must contain only SourceLocator values")
        if len(set(sources)) != len(sources):
            raise ValueError("sources must contain unique SourceLocator values")
        locator_source = self.locator.image_locator
        if locator_source not in sources:
            raise ValueError("locator image scope must occur in ROI sources")

        if len(self.coordinates) != 4:
            raise ValueError("ROI coordinates must contain four values")
        y_min, x_min, y_stop, x_stop = tuple(float(value) for value in self.coordinates)
        if not all(math.isfinite(value) for value in (y_min, x_min, y_stop, x_stop)):
            raise ValueError("ROI coordinates must be finite")
        if y_stop < y_min or x_stop < x_min:
            raise ValueError("ROI stop coordinates must be greater than min coordinates")
        if self.confidence is not None:
            confidence = float(self.confidence)
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError("ROI confidence must be finite and in [0, 1]")
            object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "coordinates", (y_min, x_min, y_stop, x_stop))
        object.__setattr__(self, "sources", sources)
        if self.source_coordinates is not None:
            source_coordinates = tuple(
                float(value) for value in self.source_coordinates
            )
            if len(source_coordinates) != 4 or not all(
                math.isfinite(value) for value in source_coordinates
            ):
                raise ValueError("source_coordinates must contain four finite values")
            object.__setattr__(self, "source_coordinates", source_coordinates)

    @property
    def frame_indices(self) -> Tuple[int, ...]:
        """Return governed DBT depth placement from source provenance."""

        return self.source_provenance.frame_indices

    def with_source(self, source: SourceLocator) -> "RegionOfInterest":
        """Return this ROI with an additional physical evidence occurrence."""

        if not isinstance(source, SourceLocator):
            raise TypeError("source must be a SourceLocator")
        if source in self.sources:
            return self
        return replace(self, sources=(*self.sources, source))

    @property
    def y_min(self) -> float:
        return self.coordinates[0]

    @property
    def x_min(self) -> float:
        return self.coordinates[1]

    @property
    def y_max(self) -> float:
        return self.coordinates[2]

    @property
    def x_max(self) -> float:
        return self.coordinates[3]

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def area(self) -> float:
        return self.height * self.width

    @property
    def centroid(self) -> Tuple[float, float]:
        return (self.y_min + self.y_max) / 2.0, (self.x_min + self.x_max) / 2.0

    def resize(
        self,
        *,
        scale_y: float,
        scale_x: float,
        image_id: Optional[str] = None,
        locator: Optional[RoiLocator] = None,
        source_provenance: Optional[RoiSourceProvenance] = None,
        sources: Optional[Tuple[SourceLocator, ...]] = None,
        coordinate_frame_id: Optional[str] = None,
    ) -> "RegionOfInterest":
        """Scale geometry, requiring governed scope for image reassignment."""

        if scale_y <= 0 or scale_x <= 0:
            raise ValueError("Resize scales must be positive")
        ownership = self._resolved_ownership(
            image_id=image_id,
            locator=locator,
            source_provenance=source_provenance,
            sources=sources,
        )
        resolved_coordinate_frame_id = self._resolved_coordinate_frame_id(
            image_id=ownership["image_id"],
            coordinate_frame_id=coordinate_frame_id,
        )
        return replace(
            self,
            coordinates=(
                self.y_min * scale_y,
                self.x_min * scale_x,
                self.y_max * scale_y,
                self.x_max * scale_x,
            ),
            coordinate_frame_id=resolved_coordinate_frame_id,
            **ownership,
        )

    def realign(
        self,
        *,
        offset_y: float = 0.0,
        offset_x: float = 0.0,
        scale_y: float = 1.0,
        scale_x: float = 1.0,
        image_id: Optional[str] = None,
        locator: Optional[RoiLocator] = None,
        source_provenance: Optional[RoiSourceProvenance] = None,
        sources: Optional[Tuple[SourceLocator, ...]] = None,
        coordinate_frame_id: Optional[str] = None,
    ) -> "RegionOfInterest":
        """Scale and translate, requiring governed scope for reassignment."""

        if scale_y <= 0 or scale_x <= 0:
            raise ValueError("Realignment scales must be positive")
        ownership = self._resolved_ownership(
            image_id=image_id,
            locator=locator,
            source_provenance=source_provenance,
            sources=sources,
        )
        resolved_coordinate_frame_id = self._resolved_coordinate_frame_id(
            image_id=ownership["image_id"],
            coordinate_frame_id=coordinate_frame_id,
        )
        return replace(
            self,
            coordinates=(
                self.y_min * scale_y + offset_y,
                self.x_min * scale_x + offset_x,
                self.y_max * scale_y + offset_y,
                self.x_max * scale_x + offset_x,
            ),
            coordinate_frame_id=resolved_coordinate_frame_id,
            **ownership,
        )

    def _resolved_ownership(
        self,
        *,
        image_id: Optional[str],
        locator: Optional[RoiLocator],
        source_provenance: Optional[RoiSourceProvenance],
        sources: Optional[Tuple[SourceLocator, ...]],
    ) -> Dict[str, object]:
        resolved_image_id = self.image_id if image_id is None else image_id
        changes_image = resolved_image_id != self.image_id
        supplied_scope = any(
            value is not None for value in (locator, source_provenance, sources)
        )
        if changes_image and not all(
            value is not None for value in (locator, source_provenance, sources)
        ):
            raise ValueError(
                "Changing ROI image ownership requires locator, provenance, and sources"
            )
        if not changes_image and supplied_scope:
            raise ValueError(
                "Governed ownership replacements require a different image_id"
            )
        return {
            "image_id": resolved_image_id,
            "locator": self.locator if locator is None else locator,
            "source_provenance": (
                self.source_provenance
                if source_provenance is None
                else source_provenance
            ),
            "sources": self.sources if sources is None else sources,
        }

    def _resolved_coordinate_frame_id(
        self,
        *,
        image_id: object,
        coordinate_frame_id: Optional[str],
    ) -> Optional[str]:
        if coordinate_frame_id is not None:
            return coordinate_frame_id
        if image_id != self.image_id:
            return None
        return self.coordinate_frame_id

    def intersection_area(self, other: "RegionOfInterest") -> float:
        y_overlap = max(0.0, min(self.y_max, other.y_max) - max(self.y_min, other.y_min))
        x_overlap = max(0.0, min(self.x_max, other.x_max) - max(self.x_min, other.x_min))
        return y_overlap * x_overlap

    def iou(self, other: "RegionOfInterest") -> float:
        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        return 0.0 if union == 0.0 else intersection / union

    def containment_ratio(self, container: "RegionOfInterest") -> float:
        if self.area == 0.0:
            return 0.0
        return self.intersection_area(container) / self.area

    def center_distance(self, other: "RegionOfInterest") -> float:
        self_y, self_x = self.centroid
        other_y, other_x = other.centroid
        return math.hypot(self_y - other_y, self_x - other_x)

    def to_dict(self) -> Dict[str, Any]:
        """Return a flat JSON-ready ROI representation."""

        return {
            "locator": self.locator.to_dict(),
            "image_id": self.image_id,
            "source_provenance": self.source_provenance.to_dict(),
            "source_references": [source.to_dict() for source in self.sources],
            "coordinates": list(self.coordinates),
            "annotation_source": self.annotation_source,
            "confidence": self.confidence,
            "coordinate_frame_id": self.coordinate_frame_id,
            "source_coordinates": (
                list(self.source_coordinates)
                if self.source_coordinates is not None
                else None
            ),
            "source_coordinate_convention": self.source_coordinate_convention,
        }
