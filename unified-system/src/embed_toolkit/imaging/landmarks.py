"""Mutable image landmarks and immutable breast-coordinate facts."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from embed_toolkit.core.anatomy import ContinuousAnatomicalPosition, DepthThird
from embed_toolkit.core.entity import MutableEntity
from embed_toolkit.core.primitives import Laterality, ViewPosition


class LandmarkType(Enum):
    """Named image landmarks used by geometry consumers."""

    NIPPLE = "nipple"
    POSTERIOR_NIPPLE_LINE_START = "posterior_nipple_line_start"
    POSTERIOR_NIPPLE_LINE_END = "posterior_nipple_line_end"
    OTHER = "other"


class ImageLandmark(MutableEntity):
    """One mutable image-local point.

    Coordinates and confidence are retained as supplied numeric facts. Their
    clinical plausibility is a validation concern, so values outside an image
    or outside a confidence range remain representable here.
    """

    y: float
    x: float
    landmark_type: LandmarkType
    image_id: Optional[str]
    source: Optional[str]
    confidence: Optional[float]
    provenance: Optional[str]

    __key_fields__ = ()

    def __init__(
        self,
        y: float,
        x: float,
        landmark_type: LandmarkType = LandmarkType.OTHER,
        image_id: Optional[str] = None,
        source: Optional[str] = None,
        confidence: Optional[float] = None,
        provenance: Optional[str] = None,
    ) -> None:
        super().__init__()
        object.__setattr__(self, "y", float(y))
        object.__setattr__(self, "x", float(x))
        object.__setattr__(self, "landmark_type", LandmarkType(landmark_type))
        object.__setattr__(self, "image_id", image_id)
        object.__setattr__(self, "source", source)
        object.__setattr__(
            self,
            "confidence",
            None if confidence is None else float(confidence),
        )
        object.__setattr__(self, "provenance", provenance)
        self._finish_initialization()

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"y", "x"}:
            value = float(value)
        elif name == "landmark_type":
            value = LandmarkType(value)
        elif name == "confidence" and value is not None:
            value = float(value)
        super().__setattr__(name, value)

    def _children(self) -> Tuple[MutableEntity, ...]:
        return ()

    def _attach_local(self, child: MutableEntity) -> MutableEntity:
        raise TypeError("ImageLandmark does not contain domain children")

    def _detach_local(self, child: MutableEntity) -> MutableEntity:
        raise TypeError("ImageLandmark does not contain domain children")

    def update(self, **fields: Any) -> "ImageLandmark":
        """Update this landmark, delegating ownership handling to the base."""

        prepared: Dict[str, Any] = dict(fields)
        if "y" in prepared:
            prepared["y"] = float(prepared["y"])
        if "x" in prepared:
            prepared["x"] = float(prepared["x"])
        if "landmark_type" in prepared:
            prepared["landmark_type"] = LandmarkType(prepared["landmark_type"])
        if "confidence" in prepared and prepared["confidence"] is not None:
            prepared["confidence"] = float(prepared["confidence"])
        super().update(**prepared)
        return self

    @property
    def point(self) -> Tuple[float, float]:
        """Return the image-local point as ``(y, x)``."""

        return self.y, self.x

    def owned_by(self, image_id: str) -> "ImageLandmark":
        """Return an image-owned copy without sharing graph membership."""

        if self.image_id == image_id:
            return self
        owned = copy.copy(self)
        object.__setattr__(owned, "_graph", None)
        object.__setattr__(owned, "image_id", image_id)
        return owned


@dataclass(frozen=True)
class BreastGeometry:
    """Coordinate-frame facts available for one breast image.

    This object stores observable geometry only. Matching and localization
    workflows consume these facts elsewhere.
    """

    image_id: str
    laterality: Laterality
    view_position: ViewPosition = ViewPosition.UNKNOWN
    image_shape: Optional[Tuple[int, int]] = None
    coordinate_frame_id: Optional[str] = None
    nipple: Optional[ImageLandmark] = None
    posterior_nipple_line: Optional[Tuple[ImageLandmark, ImageLandmark]] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "laterality", Laterality.coerce(self.laterality))
        object.__setattr__(
            self,
            "view_position",
            ViewPosition.coerce(self.view_position),
        )
        if self.image_shape is not None:
            shape = tuple(self.image_shape)
            if len(shape) != 2:
                raise ValueError("image_shape must contain height and width")
            object.__setattr__(self, "image_shape", shape)

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
        """Return the endpoint farthest from the nipple."""

        if self.posterior_nipple_line is None or self.nipple is None:
            return None
        start, end = self.posterior_nipple_line
        nipple = self.nipple
        return max(
            (start, end),
            key=lambda landmark: _distance(nipple.point, landmark.point),
        )

    @property
    def depth_vector(self) -> Optional[Tuple[float, float]]:
        """Return the nipple-to-posterior vector as ``(dy, dx)``."""

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
        """Return distance from nipple to the posterior reference."""

        vector = self.depth_vector
        if vector is None:
            return None
        return math.hypot(vector[0], vector[1])

    def depth_value_for_point(self, point: Tuple[float, float]) -> Optional[float]:
        """Return continuous depth on the toolkit's ``0..2`` scale."""

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
        """Return anterior, middle, or posterior depth for a point."""

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
