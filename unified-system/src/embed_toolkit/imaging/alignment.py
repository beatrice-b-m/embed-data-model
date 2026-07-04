"""Local image alignment semantics for mammography coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional, Sequence, Tuple, Union

from embed_toolkit.core.primitives import (
    FovHorizontalFlip,
    FovRotation,
    Laterality,
    OrientationDirection,
    PatientOrientation,
    ViewPosition,
)


CoordinateBox = Tuple[float, float, float, float]
Point = Tuple[float, float]


class AlignmentDirection(Enum):
    """Direction encoded by increasing image x or y coordinates."""

    RIGHT = "right"
    LEFT = "left"
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"

    @property
    def opposite(self) -> "AlignmentDirection":
        opposites = {
            AlignmentDirection.RIGHT: AlignmentDirection.LEFT,
            AlignmentDirection.LEFT: AlignmentDirection.RIGHT,
            AlignmentDirection.UP: AlignmentDirection.DOWN,
            AlignmentDirection.DOWN: AlignmentDirection.UP,
        }
        return opposites.get(self, AlignmentDirection.UNKNOWN)


@dataclass(frozen=True)
class Alignment:
    """Image-axis alignment with helpers for flip-only realignment.

    The canonical toolkit frame follows the legacy matching convention:
    increasing x points leftward across the image and increasing y points
    upward. Realignment supports horizontal and vertical flips; rotations are
    intentionally rejected because they change coordinate order and image shape.
    """

    x: AlignmentDirection = AlignmentDirection.LEFT
    y: AlignmentDirection = AlignmentDirection.UP

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", AlignmentDirection(self.x))
        object.__setattr__(self, "y", AlignmentDirection(self.y))

    @classmethod
    def reference(cls) -> "Alignment":
        """Return the canonical alignment used by local geometry workflows."""

        return cls(AlignmentDirection.LEFT, AlignmentDirection.UP)

    @classmethod
    def from_orientation(
        cls,
        orientation: Union[PatientOrientation, str, Iterable[Union[str, OrientationDirection]]],
        laterality: Union[str, Laterality],
        view_position: Union[str, ViewPosition],
    ) -> "Alignment":
        """Infer alignment from DICOM patient orientation, side, and view."""

        parsed_orientation = PatientOrientation.coerce(orientation)
        side = Laterality.coerce(laterality)
        view = ViewPosition.coerce(view_position)
        return cls(
            x=_direction_to_alignment(side, view, parsed_orientation.row),
            y=_direction_to_alignment(side, view, parsed_orientation.column),
        )

    @classmethod
    def from_fov(
        cls,
        rotation: Union[str, float, FovRotation],
        horizontal_flip: Union[str, FovHorizontalFlip],
        laterality: Union[str, Laterality],
    ) -> "Alignment":
        """Infer alignment from EMBED field-of-view transform metadata."""

        parsed_rotation = FovRotation.coerce(rotation)
        parsed_flip = FovHorizontalFlip.coerce(horizontal_flip)
        side = Laterality.coerce(laterality)

        mapping = {
            (Laterality.LEFT, FovRotation.FULL, FovHorizontalFlip.YES): cls(
                AlignmentDirection.RIGHT, AlignmentDirection.UP
            ),
            (Laterality.LEFT, FovRotation.FULL, FovHorizontalFlip.NO): cls(
                AlignmentDirection.LEFT, AlignmentDirection.UP
            ),
            (Laterality.LEFT, FovRotation.NONE, FovHorizontalFlip.YES): cls(
                AlignmentDirection.LEFT, AlignmentDirection.DOWN
            ),
            (Laterality.LEFT, FovRotation.NONE, FovHorizontalFlip.NO): cls(
                AlignmentDirection.RIGHT, AlignmentDirection.DOWN
            ),
            (Laterality.RIGHT, FovRotation.FULL, FovHorizontalFlip.YES): cls(
                AlignmentDirection.RIGHT, AlignmentDirection.DOWN
            ),
            (Laterality.RIGHT, FovRotation.FULL, FovHorizontalFlip.NO): cls(
                AlignmentDirection.LEFT, AlignmentDirection.DOWN
            ),
            (Laterality.RIGHT, FovRotation.NONE, FovHorizontalFlip.YES): cls(
                AlignmentDirection.LEFT, AlignmentDirection.UP
            ),
            (Laterality.RIGHT, FovRotation.NONE, FovHorizontalFlip.NO): cls(
                AlignmentDirection.RIGHT, AlignmentDirection.UP
            ),
        }
        return mapping.get(
            (side, parsed_rotation, parsed_flip),
            cls(AlignmentDirection.UNKNOWN, AlignmentDirection.UNKNOWN),
        )

    @property
    def is_reference(self) -> bool:
        return self == self.reference()

    def realign_point(
        self,
        point: Point,
        *,
        height: float,
        width: float,
        target_alignment: Optional["Alignment"] = None,
    ) -> Point:
        """Flip an image-local ``(y, x)`` point into ``target_alignment``."""

        target = self._prepare_target(target_alignment)
        y, x = float(point[0]), float(point[1])
        if _flip_required(self.x, target.x):
            x = width - x
        if _flip_required(self.y, target.y):
            y = height - y
        return y, x

    def realign_box(
        self,
        coordinates: CoordinateBox,
        *,
        height: float,
        width: float,
        target_alignment: Optional["Alignment"] = None,
    ) -> CoordinateBox:
        """Flip an EMBED ``(y_min, x_min, y_max, x_max)`` box."""

        target = self._prepare_target(target_alignment)
        y_min, x_min, y_max, x_max = (float(value) for value in coordinates)
        if _flip_required(self.x, target.x):
            x_min, x_max = width - x_max, width - x_min
        if _flip_required(self.y, target.y):
            y_min, y_max = height - y_max, height - y_min
        return y_min, x_min, y_max, x_max

    def realign_boxes(
        self,
        boxes: Iterable[CoordinateBox],
        *,
        height: float,
        width: float,
        target_alignment: Optional["Alignment"] = None,
    ) -> Tuple[CoordinateBox, ...]:
        """Flip multiple EMBED boxes into ``target_alignment``."""

        return tuple(
            self.realign_box(
                box,
                height=height,
                width=width,
                target_alignment=target_alignment,
            )
            for box in boxes
        )

    def realign_image(
        self,
        image: Any,
        target_alignment: Optional["Alignment"] = None,
    ) -> Any:
        """Flip an image array or nested sequence into ``target_alignment``."""

        target = self._prepare_target(target_alignment)
        output = image
        if _flip_required(self.x, target.x):
            output = _flip_horizontal(output)
        if _flip_required(self.y, target.y):
            output = _flip_vertical(output)
        return output

    def _prepare_target(self, target_alignment: Optional["Alignment"]) -> "Alignment":
        target = target_alignment or self.reference()
        if _axis_is_vertical(self.x) or _axis_is_horizontal(self.y):
            raise NotImplementedError("Alignment realignment only supports flips")
        if _axis_is_vertical(target.x) or _axis_is_horizontal(target.y):
            raise NotImplementedError("Alignment realignment only supports flips")
        if target.x is AlignmentDirection.UNKNOWN or target.y is AlignmentDirection.UNKNOWN:
            raise ValueError("Target alignment must be known")
        return target


def _direction_to_alignment(
    laterality: Laterality,
    view_position: ViewPosition,
    direction: OrientationDirection,
) -> AlignmentDirection:
    if direction is OrientationDirection.P:
        return AlignmentDirection.RIGHT
    if direction is OrientationDirection.A:
        return AlignmentDirection.LEFT

    if view_position in {ViewPosition.CC, ViewPosition.XCCL}:
        if laterality is Laterality.LEFT:
            if direction is OrientationDirection.L:
                return AlignmentDirection.DOWN
            if direction is OrientationDirection.R:
                return AlignmentDirection.UP
        if laterality is Laterality.RIGHT:
            if direction is OrientationDirection.L:
                return AlignmentDirection.UP
            if direction is OrientationDirection.R:
                return AlignmentDirection.DOWN

    if view_position is ViewPosition.MLO:
        if laterality is Laterality.LEFT:
            if direction is OrientationDirection.FR:
                return AlignmentDirection.UP
            if direction is OrientationDirection.HL:
                return AlignmentDirection.DOWN
        if laterality is Laterality.RIGHT:
            if direction is OrientationDirection.FL:
                return AlignmentDirection.UP
            if direction is OrientationDirection.HR:
                return AlignmentDirection.DOWN

    if view_position in {ViewPosition.ML, ViewPosition.LM}:
        if direction is OrientationDirection.F:
            return AlignmentDirection.UP
        if direction is OrientationDirection.H:
            return AlignmentDirection.DOWN

    return AlignmentDirection.UNKNOWN


def _axis_is_vertical(direction: AlignmentDirection) -> bool:
    return direction in {AlignmentDirection.UP, AlignmentDirection.DOWN}


def _axis_is_horizontal(direction: AlignmentDirection) -> bool:
    return direction in {AlignmentDirection.LEFT, AlignmentDirection.RIGHT}


def _flip_required(
    source: AlignmentDirection,
    target: AlignmentDirection,
) -> bool:
    return source is not AlignmentDirection.UNKNOWN and source is target.opposite


def _flip_horizontal(image: Any) -> Any:
    try:
        return image[..., ::-1]
    except TypeError:
        return tuple(_reverse_sequence(row) for row in image)


def _flip_vertical(image: Any) -> Any:
    try:
        return image[..., ::-1, :]
    except TypeError:
        return _reverse_sequence(image)


def _reverse_sequence(values: Sequence[Any]) -> Sequence[Any]:
    reversed_values = values[::-1]
    if isinstance(values, tuple):
        return tuple(reversed_values)
    if isinstance(values, list):
        return list(reversed_values)
    return reversed_values
