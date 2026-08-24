"""Serializable mammogram visualization plans.

The unified toolkit keeps visualization as a consumer of domain objects and
workflow evidence.  This module intentionally returns dependency-light render
plans instead of requiring a plotting backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from embed_toolkit.audit.evidence import (
    JsonValue,
    freeze_json_mapping,
    serialize_mapping,
    serialize_value,
)
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark
from embed_toolkit.imaging.rois import RegionOfInterest


Point = Tuple[float, float]
Layer = Mapping[str, JsonValue]


@dataclass(frozen=True)
class MammogramRenderPlan:
    """A JSON-compatible description of mammogram visual layers."""

    image_id: Optional[str] = None
    shape: Optional[Tuple[int, int]] = None
    layers: Tuple[Layer, ...] = field(default_factory=tuple)
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.image_id is not None and (
            not isinstance(self.image_id, str) or not self.image_id.strip()
        ):
            raise ValueError("image_id must be a non-empty string when supplied")
        if self.shape is not None:
            shape = tuple(self.shape)
            if len(shape) != 2 or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in shape
            ):
                raise ValueError("shape must contain two non-negative integers")
            object.__setattr__(self, "shape", shape)
        object.__setattr__(
            self,
            "layers",
            tuple(freeze_json_mapping(layer) for layer in self.layers),
        )
        object.__setattr__(self, "metadata", freeze_json_mapping(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "kind": "mammogram_render_plan",
            "image_id": self.image_id,
            "shape": list(self.shape) if self.shape is not None else None,
            "layers": [serialize_mapping(layer) for layer in self.layers],
            "metadata": serialize_mapping(self.metadata),
        }


def build_mammogram_render_plan(
    *,
    image: Optional[MammogramImage] = None,
    pixels: Any = None,
    rois: Iterable[RegionOfInterest] = (),
    geometry: Optional[BreastGeometry] = None,
    landmarks: Iterable[ImageLandmark] = (),
    finding_expectations: Iterable[Any] = (),
    match_evidence: Iterable[Any] = (),
    include_pixel_values: bool = True,
    title: Optional[str] = None,
) -> MammogramRenderPlan:
    """Build a serializable plan for reviewing a mammogram and overlays.

    ``finding_expectations`` and ``match_evidence`` accept workflow result
    objects with ``to_dict()``, evidence objects with ``to_dict()``, or plain
    mappings.  The values are copied into annotation layers without adding
    workflow behavior to imaging domain objects.
    """

    inferred_shape = _first_shape(
        _shape_from_pixels(pixels),
        image.image_shape if image is not None else None,
        geometry.image_shape if geometry is not None else None,
    )
    image_id = _first_present(
        image.image_id if image is not None else None,
        geometry.image_id if geometry is not None else None,
    )
    plan_layers: list[dict[str, JsonValue]] = []

    if pixels is not None:
        plan_layers.append(_pixel_layer(pixels, include_values=include_pixel_values))

    for roi in rois:
        plan_layers.append(_roi_box_layer(roi))
        plan_layers.append(_centroid_layer(roi))

    all_landmarks = list(landmarks)
    if image is not None:
        all_landmarks.extend(image.landmarks)
    if geometry is not None:
        all_landmarks.extend(_geometry_landmarks(geometry))
    for landmark in _unique_landmarks(all_landmarks):
        plan_layers.append(_landmark_layer(landmark))

    if geometry is not None:
        plan_layers.extend(_geometry_layers(geometry))

    for expectation in finding_expectations:
        plan_layers.append(
            {
                "type": "finding_expectation",
                "payload": _serializable_payload(expectation),
            }
        )

    for evidence in match_evidence:
        plan_layers.append(
            {
                "type": "match_evidence",
                "payload": _serializable_payload(evidence),
            }
        )

    metadata: dict[str, JsonValue] = {"renderer": "serializable_plan"}
    if title is not None:
        metadata["title"] = title
    if image is not None:
        metadata.update(
            {
                "laterality": image.laterality.value,
                "view_position": image.view_position.value,
                "modality": image.modality.value,
                "frame_count": image.frame_count,
                "coordinate_frame_id": image.coordinate_frame_id,
            }
        )
    elif geometry is not None:
        metadata.update(
            {
                "laterality": geometry.laterality.value,
                "view_position": geometry.view_position.value,
                "coordinate_frame_id": geometry.frame_id,
            }
        )

    return MammogramRenderPlan(
        image_id=image_id,
        shape=inferred_shape,
        layers=tuple(plan_layers),
        metadata=metadata,
    )


def _pixel_layer(pixels: Any, *, include_values: bool) -> dict[str, JsonValue]:
    values = _pixels_to_list(pixels)
    layer: dict[str, JsonValue] = {
        "type": "image_pixels",
        "shape": list(_shape_from_pixel_values(values)),
        "intensity_range": list(_intensity_range(values)),
        "coordinate_order": "yx",
    }
    if include_values:
        layer["values"] = values
    return layer


def _roi_box_layer(roi: RegionOfInterest) -> dict[str, JsonValue]:
    return {
        "type": "roi_box",
        "roi_locator": roi.locator.to_dict(),
        "image_id": roi.image_id,
        "frame_indices": list(roi.frame_indices),
        "coordinates": list(roi.coordinates),
        "coordinate_order": "yxyx",
        "annotation_source": roi.annotation_source,
        "source_provenance": roi.source_provenance.to_dict(),
        "confidence": roi.confidence,
        "coordinate_frame_id": roi.coordinate_frame_id,
    }


def _centroid_layer(roi: RegionOfInterest) -> dict[str, JsonValue]:
    return {
        "type": "centroid",
        "roi_locator": roi.locator.to_dict(),
        "point": list(roi.centroid),
        "coordinate_order": "yx",
    }


def _landmark_layer(landmark: ImageLandmark) -> dict[str, JsonValue]:
    return {
        "type": "landmark",
        "landmark_type": landmark.landmark_type.value,
        "image_id": landmark.image_id,
        "point": [landmark.y, landmark.x],
        "coordinate_order": "yx",
        "source": landmark.source,
        "confidence": landmark.confidence,
        "provenance": landmark.provenance,
    }


def _geometry_layers(geometry: BreastGeometry) -> list[dict[str, JsonValue]]:
    layers: list[dict[str, JsonValue]] = []
    if geometry.posterior_nipple_line is not None:
        start, end = geometry.posterior_nipple_line
        layers.append(
            {
                "type": "posterior_nipple_line",
                "points": [[start.y, start.x], [end.y, end.x]],
                "coordinate_order": "yx",
                "coordinate_frame_id": geometry.frame_id,
            }
        )

    depth_vector = geometry.depth_vector
    if geometry.nipple is None or depth_vector is None or geometry.image_shape is None:
        return layers

    nipple = geometry.nipple
    dy, dx = depth_vector
    for label, fraction in (("anterior_middle", 1 / 3), ("middle_posterior", 2 / 3)):
        point = (nipple.y + dy * fraction, nipple.x + dx * fraction)
        clipped = _clipped_perpendicular_line(
            point=point,
            vector=depth_vector,
            image_shape=geometry.image_shape,
        )
        if clipped is None:
            continue
        layers.append(
            {
                "type": "depth_third_boundary",
                "boundary": label,
                "fraction_to_posterior": fraction,
                "points": [
                    [clipped[0][0], clipped[0][1]],
                    [clipped[1][0], clipped[1][1]],
                ],
                "coordinate_order": "yx",
                "coordinate_frame_id": geometry.frame_id,
            }
        )
    return layers


def _geometry_landmarks(geometry: BreastGeometry) -> tuple[ImageLandmark, ...]:
    landmarks: list[ImageLandmark] = []
    if geometry.nipple is not None:
        landmarks.append(geometry.nipple)
    if geometry.posterior_nipple_line is not None:
        landmarks.extend(geometry.posterior_nipple_line)
    return tuple(landmarks)


def _unique_landmarks(landmarks: Iterable[ImageLandmark]) -> tuple[ImageLandmark, ...]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[ImageLandmark] = []
    for landmark in landmarks:
        key = (
            landmark.image_id,
            landmark.landmark_type.value,
            landmark.y,
            landmark.x,
            landmark.source,
            landmark.provenance,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(landmark)
    return tuple(unique)


def _serializable_payload(value: Any) -> JsonValue:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return serialize_value(value.to_dict())
    if isinstance(value, Mapping):
        return serialize_value(value)
    return serialize_value(value)


def _shape_from_pixels(pixels: Any) -> Optional[Tuple[int, int]]:
    if pixels is None:
        return None
    shape = getattr(pixels, "shape", None)
    if shape is not None and len(shape) >= 2:
        return int(shape[0]), int(shape[1])
    try:
        rows = len(pixels)
        cols = len(pixels[0]) if rows else 0
    except (TypeError, IndexError):
        return None
    if rows > 0 and cols > 0:
        return int(rows), int(cols)
    return None


def _shape_from_pixel_values(values: Sequence[Sequence[Any]]) -> Tuple[int, int]:
    rows = len(values)
    cols = len(values[0]) if rows else 0
    return rows, cols


def _first_shape(*shapes: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    for shape in shapes:
        if shape is not None:
            return shape
    return None


def _first_present(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value:
            return value
    return None


def _pixels_to_list(pixels: Any) -> list[list[JsonValue]]:
    if hasattr(pixels, "tolist") and callable(pixels.tolist):
        values = pixels.tolist()
    else:
        values = pixels
    if not isinstance(values, Sequence):
        raise TypeError("Mammogram pixels must be a two-dimensional sequence")
    return [list(row) for row in values]


def _intensity_range(
    values: Sequence[Sequence[Any]],
) -> Tuple[Optional[float], Optional[float]]:
    flattened = [float(value) for row in values for value in row]
    if not flattened:
        return None, None
    return min(flattened), max(flattened)


def _clipped_perpendicular_line(
    *,
    point: Point,
    vector: Point,
    image_shape: Tuple[int, int],
) -> Optional[Tuple[Point, Point]]:
    height, width = image_shape
    if height <= 0 or width <= 0:
        return None
    dy, dx = vector
    direction = (-dx, dy)
    candidates: list[Point] = []
    for y_edge in (0.0, float(height - 1)):
        if direction[0] != 0.0:
            t = (y_edge - point[0]) / direction[0]
            x = point[1] + t * direction[1]
            if 0.0 <= x <= width - 1:
                candidates.append((y_edge, x))
    for x_edge in (0.0, float(width - 1)):
        if direction[1] != 0.0:
            t = (x_edge - point[1]) / direction[1]
            y = point[0] + t * direction[0]
            if 0.0 <= y <= height - 1:
                candidates.append((y, x_edge))

    unique = _unique_points(candidates)
    if len(unique) < 2:
        return None
    return unique[0], unique[-1]


def _unique_points(points: Iterable[Point]) -> list[Point]:
    unique: list[Point] = []
    for point in points:
        rounded = (round(point[0], 9), round(point[1], 9))
        if any(
            rounded == (round(existing[0], 9), round(existing[1], 9))
            for existing in unique
        ):
            continue
        unique.append(point)
    return unique
