"""Image-local regions of interest and intrinsic ROI geometry."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from embed_data_model.core.entity import MutableEntity


CoordinateBox = Tuple[float, float, float, float]


@dataclass(frozen=True)
class Box:
    """Immutable half-open image geometry.

    A box keeps four numeric coordinates in ``[y_min, x_min, y_stop,
    x_stop]`` order.  Bounds and ordering are inspected by optional
    validation; construction preserves those raw facts.
    """

    y_min: float
    x_min: float
    y_stop: float
    x_stop: float

    def __post_init__(self) -> None:
        for attribute, value in zip(
            ("y_min", "x_min", "y_stop", "x_stop"),
            _numeric_box((self.y_min, self.x_min, self.y_stop, self.x_stop)),
        ):
            object.__setattr__(self, attribute, value)

    def as_tuple(self) -> CoordinateBox:
        return self.y_min, self.x_min, self.y_stop, self.x_stop


class RegionOfInterest(MutableEntity):
    """One mutable, image-local ROI.

    ``(image_id, roi_key)`` is the toolkit identity.  Source location fields
    are optional lookup aliases and do not participate in identity.
    """

    coordinates: CoordinateBox
    image_id: str
    roi_key: str
    source_path: Optional[str]
    collection_position: Optional[int]
    annotation_source: Optional[str]
    confidence: Optional[float]
    coordinate_frame_id: Optional[str]
    source_coordinates: Optional[CoordinateBox]
    source_coordinate_convention: Optional[str]
    source_frame_indices: Tuple[int, ...]
    frame_provenance: Optional[str]
    frame_derivation_method: Optional[str]
    metadata: Dict[str, Any]

    __key_fields__ = ("image_id", "roi_key")

    def __init__(
        self,
        coordinates: Union[CoordinateBox, Box],
        image_id: str,
        roi_key: str,
        *,
        source_path: Optional[str] = None,
        collection_position: Optional[int] = None,
        annotation_source: Optional[str] = None,
        confidence: Optional[float] = None,
        coordinate_frame_id: Optional[str] = None,
        source_coordinates: Optional[CoordinateBox] = None,
        source_coordinate_convention: Optional[str] = None,
        source_frame_indices: Tuple[int, ...] = (),
        frame_provenance: Optional[str] = None,
        frame_derivation_method: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__()
        _require_image_id(image_id)
        _require_roi_key(roi_key)
        object.__setattr__(self, "coordinates", _numeric_box(coordinates))
        object.__setattr__(self, "image_id", image_id)
        object.__setattr__(self, "roi_key", roi_key)
        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "collection_position", collection_position)
        object.__setattr__(self, "annotation_source", annotation_source)
        object.__setattr__(
            self,
            "confidence",
            None if confidence is None else float(confidence),
        )
        object.__setattr__(self, "coordinate_frame_id", coordinate_frame_id)
        object.__setattr__(
            self,
            "source_coordinates",
            None
            if source_coordinates is None
            else _numeric_box(source_coordinates),
        )
        object.__setattr__(
            self,
            "source_coordinate_convention",
            source_coordinate_convention,
        )
        object.__setattr__(
            self,
            "source_frame_indices",
            tuple(source_frame_indices),
        )
        object.__setattr__(self, "frame_provenance", frame_provenance)
        object.__setattr__(self, "frame_derivation_method", frame_derivation_method)
        object.__setattr__(self, "metadata", dict(metadata or {}))
        self._finish_initialization()

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "coordinates":
            value = _numeric_box(value)
        elif name == "source_coordinates" and value is not None:
            value = _numeric_box(value)
        elif name == "source_frame_indices" and value is not None:
            value = tuple(value)
        elif name == "confidence" and value is not None:
            value = float(value)
        super().__setattr__(name, value)

    def _children(self) -> Tuple[MutableEntity, ...]:
        return ()

    def _attach_local(self, child: MutableEntity) -> MutableEntity:
        raise TypeError("RegionOfInterest does not contain domain children")

    def _detach_local(self, child: MutableEntity) -> MutableEntity:
        raise TypeError("RegionOfInterest does not contain domain children")

    def update(self, **fields: Any) -> "RegionOfInterest":
        """Update this ROI while preserving graph delegation."""

        prepared: Dict[str, Any] = dict(fields)
        if "coordinates" in prepared:
            prepared["coordinates"] = _numeric_box(prepared["coordinates"])
        if "source_coordinates" in prepared and prepared["source_coordinates"] is not None:
            prepared["source_coordinates"] = _numeric_box(
                prepared["source_coordinates"]
            )
        if "source_frame_indices" in prepared and prepared["source_frame_indices"] is not None:
            prepared["source_frame_indices"] = tuple(prepared["source_frame_indices"])
        if "confidence" in prepared and prepared["confidence"] is not None:
            prepared["confidence"] = float(prepared["confidence"])
        super().update(**prepared)
        return self

    @classmethod
    def from_embed_coordinates(
        cls,
        coordinates: CoordinateBox,
        **metadata: Any,
    ) -> "RegionOfInterest":
        """Convert EMBED inclusive maxima to canonical exclusive stops."""

        y_min, x_min, y_max, x_max = _numeric_box(coordinates)
        return cls(
            coordinates=(y_min, x_min, y_max + 1.0, x_max + 1.0),
            source_coordinates=(y_min, x_min, y_max, x_max),
            source_coordinate_convention="inclusive_maxima",
            **metadata,
        )

    @property
    def frame_indices(self) -> Tuple[int, ...]:
        """Return supplied frame facts without inferring depth."""

        return self.source_frame_indices

    @property
    def identity(self) -> Tuple[str, str]:
        return self.image_id, self.roi_key

    @property
    def y_min(self) -> float:
        return _numeric_box(self.coordinates)[0]

    @property
    def x_min(self) -> float:
        return _numeric_box(self.coordinates)[1]

    @property
    def y_max(self) -> float:
        return _numeric_box(self.coordinates)[2]

    @property
    def x_max(self) -> float:
        return _numeric_box(self.coordinates)[3]

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
        roi_key: Optional[str] = None,
        coordinate_frame_id: Optional[str] = None,
    ) -> "RegionOfInterest":
        """Return a geometry-scaled standalone copy."""

        return self._geometry_copy(
            coordinates=(
                self.y_min * float(scale_y),
                self.x_min * float(scale_x),
                self.y_max * float(scale_y),
                self.x_max * float(scale_x),
            ),
            image_id=image_id,
            roi_key=roi_key,
            coordinate_frame_id=coordinate_frame_id,
        )

    def realign(
        self,
        *,
        offset_y: float = 0.0,
        offset_x: float = 0.0,
        scale_y: float = 1.0,
        scale_x: float = 1.0,
        image_id: Optional[str] = None,
        roi_key: Optional[str] = None,
        coordinate_frame_id: Optional[str] = None,
    ) -> "RegionOfInterest":
        """Return a scaled and translated standalone copy."""

        return self._geometry_copy(
            coordinates=(
                self.y_min * float(scale_y) + float(offset_y),
                self.x_min * float(scale_x) + float(offset_x),
                self.y_max * float(scale_y) + float(offset_y),
                self.x_max * float(scale_x) + float(offset_x),
            ),
            image_id=image_id,
            roi_key=roi_key,
            coordinate_frame_id=coordinate_frame_id,
        )

    def _geometry_copy(
        self,
        *,
        coordinates: CoordinateBox,
        image_id: Optional[str],
        roi_key: Optional[str],
        coordinate_frame_id: Optional[str],
    ) -> "RegionOfInterest":
        clone = copy.copy(self)
        object.__setattr__(clone, "_graph", None)
        object.__setattr__(clone, "coordinates", _numeric_box(coordinates))
        if image_id is not None:
            _require_image_id(image_id)
            object.__setattr__(clone, "image_id", image_id)
        if roi_key is not None:
            _require_roi_key(roi_key)
            object.__setattr__(clone, "roi_key", roi_key)
        if coordinate_frame_id is not None:
            object.__setattr__(clone, "coordinate_frame_id", coordinate_frame_id)
        return clone

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

    def _to_dict_data(self, state: Any = None) -> Dict[str, Any]:
        return {
            "roi_key": self.roi_key,
            "image_id": self.image_id,
            "source_path": self.source_path,
            "collection_position": self.collection_position,
            "coordinates": list(_numeric_box(self.coordinates)),
            "annotation_source": self.annotation_source,
            "confidence": self.confidence,
            "coordinate_frame_id": self.coordinate_frame_id,
            "source_coordinates": (
                list(_numeric_box(self.source_coordinates))
                if self.source_coordinates is not None
                else None
            ),
            "source_coordinate_convention": self.source_coordinate_convention,
            "frame_indices": list(self.frame_indices),
            "frame_provenance": self.frame_provenance,
            "frame_derivation_method": self.frame_derivation_method,
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a flat JSON-ready ROI representation."""

        return self._to_dict_data()


def _numeric_box(value: Union[CoordinateBox, Box, Any]) -> CoordinateBox:
    if isinstance(value, Box):
        values = value.as_tuple()
    else:
        try:
            values = tuple(value)
        except TypeError as exc:
            raise TypeError("ROI coordinates must be an iterable of four numbers") from exc
    if len(values) != 4:
        raise ValueError("ROI coordinates must contain four values")
    try:
        return tuple(float(item) for item in values)  # type: ignore[return-value]
    except (TypeError, ValueError) as exc:
        raise TypeError("ROI coordinates must contain numeric values") from exc


def _require_image_id(image_id: str) -> None:
    if not isinstance(image_id, str) or not image_id.strip():
        raise ValueError("image_id must be a non-empty string")


def _require_roi_key(roi_key: str) -> None:
    if not isinstance(roi_key, str) or not roi_key.strip():
        raise ValueError("roi_key must be an explicit non-empty string")
