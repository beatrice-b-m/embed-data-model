"""Image-local landmarks and breast coordinate-frame facts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional, Tuple

from embed_toolkit.core.primitives import Laterality, ViewPosition


class LandmarkType(Enum):
    """Named image landmarks used by geometry and audit workflows."""

    NIPPLE = "nipple"
    POSTERIOR_NIPPLE_LINE_START = "posterior_nipple_line_start"
    POSTERIOR_NIPPLE_LINE_END = "posterior_nipple_line_end"
    CHEST_WALL = "chest_wall"
    POSTERIOR_BREAST_BOUNDARY = "posterior_breast_boundary"
    OTHER = "other"


@dataclass(frozen=True)
class ImageLandmark:
    """Single image-local landmark with source provenance."""

    y: float
    x: float
    landmark_type: LandmarkType = LandmarkType.OTHER
    image_id: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    provenance: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "landmark_type", LandmarkType(self.landmark_type))
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Landmark confidence must be in [0, 1]")

    @property
    def point(self) -> Tuple[float, float]:
        """Return the image-local point as ``(y, x)``."""

        return self.y, self.x

    def owned_by(self, image_id: str) -> "ImageLandmark":
        """Return a copy associated with an owning image."""

        return replace(self, image_id=image_id)


@dataclass(frozen=True)
class BreastGeometry:
    """Coordinate-frame facts available for one breast image.

    This object intentionally stores observable geometry only. Matching and
    localization workflows can consume these facts, but that logic does not live
    here.
    """

    image_id: str
    laterality: Laterality
    view_position: ViewPosition = ViewPosition.UNKNOWN
    image_shape: Optional[Tuple[int, int]] = None
    coordinate_frame_id: Optional[str] = None
    nipple: Optional[ImageLandmark] = None
    posterior_nipple_line: Optional[Tuple[ImageLandmark, ImageLandmark]] = None
    posterior_boundary: Optional[ImageLandmark] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "laterality", Laterality.coerce(self.laterality))
        object.__setattr__(
            self,
            "view_position",
            ViewPosition.coerce(self.view_position),
        )
        if self.image_shape is not None:
            height, width = self.image_shape
            if height <= 0 or width <= 0:
                raise ValueError("Image shape must be positive")

    @property
    def has_nipple(self) -> bool:
        return self.nipple is not None

    @property
    def has_posterior_nipple_line(self) -> bool:
        return self.posterior_nipple_line is not None

    @property
    def frame_id(self) -> str:
        return self.coordinate_frame_id or self.image_id
