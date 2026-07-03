"""Breast anatomy models that are independent of source-code systems."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Tuple

from embed_toolkit.core.primitives import Laterality


class MedialLateralAxis(Enum):
    MEDIAL = "medial"
    CENTRAL = "central"
    LATERAL = "lateral"
    UNKNOWN = "unknown"


class SuperiorInferiorAxis(Enum):
    INFERIOR = "inferior"
    CENTRAL = "central"
    SUPERIOR = "superior"
    UNKNOWN = "unknown"


class DepthThird(Enum):
    ANTERIOR = "anterior"
    MIDDLE = "middle"
    POSTERIOR = "posterior"
    UNKNOWN = "unknown"


class AnatomicalLocationCategory(Enum):
    """Named locations that should not be forced into quadrant-only anatomy."""

    CENTRAL = "central"
    RETROAREOLAR = "retroareolar"
    SUBAREOLAR = "subareolar"
    AXILLARY_TAIL = "axillary_tail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClockFacePosition:
    """Clock-face breast location using conventional 1 through 12 hours."""

    hour: int

    def __post_init__(self) -> None:
        if self.hour < 1 or self.hour > 12:
            raise ValueError(f"Clock-face hour must be in 1..12: {self.hour!r}")

    @classmethod
    def coerce(cls, value: Any) -> "ClockFacePosition":
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)

        text = str(value).strip().upper()
        match = re.search(r"(?:C)?(1[0-2]|[1-9])(?::?00)?", text)
        if not match:
            raise ValueError(f"Unrecognized clock-face position: {value!r}")
        return cls(int(match.group(1)))

    def to_quadrant(self, laterality: Laterality) -> "Quadrant":
        side = Laterality.coerce(laterality)
        if side not in {Laterality.LEFT, Laterality.RIGHT}:
            raise ValueError(f"Clock-face mapping requires a breast side: {laterality!r}")

        if self.hour in {6, 12}:
            ml = MedialLateralAxis.CENTRAL
        elif self.hour in {1, 2, 3, 4, 5}:
            ml = (
                MedialLateralAxis.LATERAL
                if side is Laterality.LEFT
                else MedialLateralAxis.MEDIAL
            )
        else:
            ml = (
                MedialLateralAxis.MEDIAL
                if side is Laterality.LEFT
                else MedialLateralAxis.LATERAL
            )

        if self.hour in {3, 9}:
            si = SuperiorInferiorAxis.CENTRAL
        elif self.hour in {10, 11, 12, 1, 2}:
            si = SuperiorInferiorAxis.SUPERIOR
        else:
            si = SuperiorInferiorAxis.INFERIOR

        return Quadrant(laterality=side, ml=ml, si=si)


@dataclass(frozen=True)
class Quadrant:
    """Discrete three-axis anatomical position for a breast side."""

    laterality: Laterality
    ml: MedialLateralAxis = MedialLateralAxis.UNKNOWN
    si: SuperiorInferiorAxis = SuperiorInferiorAxis.UNKNOWN
    depth: DepthThird = DepthThird.UNKNOWN

    def __post_init__(self) -> None:
        side = Laterality.coerce(self.laterality)
        object.__setattr__(self, "laterality", side)

    def merge_missing(self, other: "Quadrant") -> "Quadrant":
        if self.laterality is not other.laterality:
            raise ValueError(
                "Cannot merge anatomical positions from different lateralities"
            )
        return Quadrant(
            laterality=self.laterality,
            ml=self.ml if self.ml is not MedialLateralAxis.UNKNOWN else other.ml,
            si=self.si if self.si is not SuperiorInferiorAxis.UNKNOWN else other.si,
            depth=self.depth if self.depth is not DepthThird.UNKNOWN else other.depth,
        )


@dataclass(frozen=True)
class AnatomicalPosition:
    """Clinical anatomical position with optional named and measured fields."""

    laterality: Laterality
    quadrant: Quadrant
    clock_position: Optional[ClockFacePosition] = None
    location_category: Optional[AnatomicalLocationCategory] = None
    distance_from_nipple_cm: Optional[float] = None

    def __post_init__(self) -> None:
        side = Laterality.coerce(self.laterality)
        if side is not self.quadrant.laterality:
            raise ValueError("AnatomicalPosition laterality must match its quadrant")
        object.__setattr__(self, "laterality", side)


@dataclass(frozen=True)
class ContinuousAnatomicalPosition:
    """Continuous anatomical coordinates in a declared breast coordinate frame."""

    laterality: Laterality
    ml_value: Optional[float] = None
    si_value: Optional[float] = None
    depth_value: Optional[float] = None
    coordinate_frame_id: Optional[str] = None

    @property
    def observable_axes(self) -> Tuple[str, ...]:
        axes = []
        if self.ml_value is not None:
            axes.append("ml")
        if self.si_value is not None:
            axes.append("si")
        if self.depth_value is not None:
            axes.append("depth")
        return tuple(axes)

    def to_quadrant(self) -> Quadrant:
        return Quadrant(
            laterality=Laterality.coerce(self.laterality),
            ml=_quantize_ml(self.ml_value),
            si=_quantize_si(self.si_value),
            depth=_quantize_depth(self.depth_value),
        )


def _quantize_ml(value: Optional[float]) -> MedialLateralAxis:
    if value is None:
        return MedialLateralAxis.UNKNOWN
    if value <= -0.5:
        return MedialLateralAxis.MEDIAL
    if value >= 0.5:
        return MedialLateralAxis.LATERAL
    return MedialLateralAxis.CENTRAL


def _quantize_si(value: Optional[float]) -> SuperiorInferiorAxis:
    if value is None:
        return SuperiorInferiorAxis.UNKNOWN
    if value <= -0.5:
        return SuperiorInferiorAxis.INFERIOR
    if value >= 0.5:
        return SuperiorInferiorAxis.SUPERIOR
    return SuperiorInferiorAxis.CENTRAL


def _quantize_depth(value: Optional[float]) -> DepthThird:
    if value is None:
        return DepthThird.UNKNOWN
    if value < 2 / 3:
        return DepthThird.ANTERIOR
    if value < 4 / 3:
        return DepthThird.MIDDLE
    return DepthThird.POSTERIOR

