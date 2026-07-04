"""Image-local regions of interest and intrinsic ROI geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional, Tuple


CoordinateBox = Tuple[float, float, float, float]


@dataclass(frozen=True)
class RegionOfInterest:
    """Image-local ROI box in EMBED ``[y_min, x_min, y_max, x_max]`` order."""

    coordinates: CoordinateBox
    roi_id: Optional[str] = None
    image_id: Optional[str] = None
    frame_index: Optional[int] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    coordinate_frame_id: Optional[str] = None

    def __post_init__(self) -> None:
        if len(self.coordinates) != 4:
            raise ValueError("ROI coordinates must contain four values")
        y_min, x_min, y_max, x_max = tuple(float(value) for value in self.coordinates)
        if y_max < y_min or x_max < x_min:
            raise ValueError("ROI max coordinates must be greater than min coordinates")
        if self.frame_index is not None and self.frame_index < 0:
            raise ValueError("DBT frame index must be non-negative")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("ROI confidence must be in [0, 1]")
        object.__setattr__(self, "coordinates", (y_min, x_min, y_max, x_max))

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
        """Return the ROI center in ``(y, x)`` order."""

        return (self.y_min + self.y_max) / 2.0, (self.x_min + self.x_max) / 2.0

    def resize(
        self,
        *,
        scale_y: float,
        scale_x: float,
        image_id: Optional[str] = None,
        coordinate_frame_id: Optional[str] = None,
    ) -> "RegionOfInterest":
        """Scale the ROI coordinates from the image origin."""

        if scale_y <= 0 or scale_x <= 0:
            raise ValueError("Resize scales must be positive")
        return replace(
            self,
            coordinates=(
                self.y_min * scale_y,
                self.x_min * scale_x,
                self.y_max * scale_y,
                self.x_max * scale_x,
            ),
            image_id=self.image_id if image_id is None else image_id,
            coordinate_frame_id=self.coordinate_frame_id
            if coordinate_frame_id is None
            else coordinate_frame_id,
        )

    def realign(
        self,
        *,
        offset_y: float = 0.0,
        offset_x: float = 0.0,
        scale_y: float = 1.0,
        scale_x: float = 1.0,
        image_id: Optional[str] = None,
        coordinate_frame_id: Optional[str] = None,
    ) -> "RegionOfInterest":
        """Apply scale then translation to move the ROI into another frame."""

        if scale_y <= 0 or scale_x <= 0:
            raise ValueError("Realignment scales must be positive")
        return replace(
            self,
            coordinates=(
                self.y_min * scale_y + offset_y,
                self.x_min * scale_x + offset_x,
                self.y_max * scale_y + offset_y,
                self.x_max * scale_x + offset_x,
            ),
            image_id=self.image_id if image_id is None else image_id,
            coordinate_frame_id=self.coordinate_frame_id
            if coordinate_frame_id is None
            else coordinate_frame_id,
        )

    def intersection_area(self, other: "RegionOfInterest") -> float:
        y_overlap = max(0.0, min(self.y_max, other.y_max) - max(self.y_min, other.y_min))
        x_overlap = max(0.0, min(self.x_max, other.x_max) - max(self.x_min, other.x_min))
        return y_overlap * x_overlap

    def iou(self, other: "RegionOfInterest") -> float:
        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        if union == 0.0:
            return 0.0
        return intersection / union

    def containment_ratio(self, container: "RegionOfInterest") -> float:
        """Return the fraction of this ROI area contained by ``container``."""

        if self.area == 0.0:
            return 0.0
        return self.intersection_area(container) / self.area

    def center_distance(self, other: "RegionOfInterest") -> float:
        self_y, self_x = self.centroid
        other_y, other_x = other.centroid
        return math.hypot(self_y - other_y, self_x - other_x)
