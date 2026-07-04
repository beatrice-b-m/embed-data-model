"""Image-local landmarks and breast coordinate-frame facts."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional, Tuple

from embed_toolkit.core.anatomy import (
    ContinuousAnatomicalPosition,
    DepthThird,
)
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

    @property
    def posterior_reference(self) -> Optional[ImageLandmark]:
        """Best available posterior reference for depth measurements."""

        if self.posterior_boundary is not None:
            return self.posterior_boundary
        if self.posterior_nipple_line is None or self.nipple is None:
            return None
        start, end = self.posterior_nipple_line
        return max(
            (start, end),
            key=lambda landmark: _distance(self.nipple.point, landmark.point),
        )

    @property
    def depth_vector(self) -> Optional[Tuple[float, float]]:
        """Return the nipple-to-posterior vector as ``(dy, dx)`` if observable."""

        if self.nipple is None:
            return None
        posterior = self.posterior_reference
        if posterior is None:
            return None
        dy = posterior.y - self.nipple.y
        dx = posterior.x - self.nipple.x
        if dy == 0.0 and dx == 0.0:
            return None
        return dy, dx

    @property
    def posterior_distance(self) -> Optional[float]:
        """Distance from nipple to the posterior reference along the PNL."""

        vector = self.depth_vector
        if vector is None:
            return None
        return math.hypot(vector[0], vector[1])

    def depth_value_for_point(self, point: Tuple[float, float]) -> Optional[float]:
        """Return continuous depth in the toolkit ``0..2`` third scale.

        A value near 0 is nipple/anterior, 1 is the middle third, and values at
        or above 4/3 quantize to posterior. ``None`` means depth is not
        observable from the available landmarks.
        """

        if self.nipple is None:
            return None
        vector = self.depth_vector
        if vector is None:
            return None
        dy, dx = vector
        squared_length = dy * dy + dx * dx
        if squared_length == 0.0:
            return None
        point_dy = float(point[0]) - self.nipple.y
        point_dx = float(point[1]) - self.nipple.x
        fraction_to_posterior = (point_dy * dy + point_dx * dx) / squared_length
        return fraction_to_posterior * 2.0

    def depth_third_for_point(self, point: Tuple[float, float]) -> DepthThird:
        """Return anterior/middle/posterior depth for an image-local point."""

        depth_value = self.depth_value_for_point(point)
        if depth_value is None:
            return DepthThird.UNKNOWN
        if depth_value < 2 / 3:
            return DepthThird.ANTERIOR
        if depth_value < 4 / 3:
            return DepthThird.MIDDLE
        return DepthThird.POSTERIOR

    def continuous_position_for_point(
        self,
        point: Tuple[float, float],
    ) -> ContinuousAnatomicalPosition:
        """Project an image-local point into observable anatomical axes."""

        depth_value = self.depth_value_for_point(point)
        transverse_value = self._transverse_value_for_point(point)
        ml_value: Optional[float] = None
        si_value: Optional[float] = None

        if self.view_position in {ViewPosition.CC, ViewPosition.XCCL}:
            ml_value = transverse_value
        elif self.view_position in {ViewPosition.MLO, ViewPosition.ML, ViewPosition.LM}:
            si_value = transverse_value

        return ContinuousAnatomicalPosition(
            laterality=self.laterality,
            ml_value=ml_value,
            si_value=si_value,
            depth_value=depth_value,
            coordinate_frame_id=self.frame_id,
        )

    def _transverse_value_for_point(
        self,
        point: Tuple[float, float],
    ) -> Optional[float]:
        if self.nipple is None:
            return None
        vector = self.depth_vector
        distance = self.posterior_distance
        if vector is None or distance is None or distance == 0.0:
            return None
        dy, dx = vector
        point_dy = float(point[0]) - self.nipple.y
        point_dx = float(point[1]) - self.nipple.x
        signed_distance = (point_dy * -dx + point_dx * dy) / distance
        return signed_distance / distance


def _distance(
    first: Tuple[float, float],
    second: Tuple[float, float],
) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])
