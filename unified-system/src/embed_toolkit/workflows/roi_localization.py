"""ROI anatomical localization workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from embed_toolkit.audit.evidence import AuditWarning, Evidence, WarningSeverity
from embed_toolkit.audit.results import LocalizationResult, ResultStatus
from embed_toolkit.core.anatomy import ContinuousAnatomicalPosition, Quadrant
from embed_toolkit.core.primitives import ViewPosition
from embed_toolkit.imaging.landmarks import BreastGeometry
from embed_toolkit.imaging.rois import RegionOfInterest


AxisName = str


@dataclass(frozen=True)
class RoiLocalizer:
    """Localize an image-local ROI centroid in breast anatomical coordinates."""

    expected_axes: Tuple[AxisName, ...] = ("ml", "si", "depth")

    def localize(
        self,
        roi: RegionOfInterest,
        geometry: BreastGeometry,
        *,
        expected_axes: Optional[Iterable[AxisName]] = None,
    ) -> LocalizationResult:
        axes = tuple(expected_axes) if expected_axes is not None else self.expected_axes
        centroid = roi.centroid
        continuous = geometry.continuous_position_for_point(centroid)
        quadrant = continuous.to_quadrant()
        warnings = _warnings_for_axes(axes, continuous, geometry)
        status = ResultStatus.PARTIAL if warnings else ResultStatus.SUCCESS

        return LocalizationResult(
            status=status,
            subject_id=roi.roi_id or "",
            subject_type="roi",
            anatomical_position=_quadrant_payload(quadrant),
            continuous_position=_continuous_payload(continuous),
            evidence=[
                Evidence(
                    kind="roi_geometry",
                    source=roi.source or "roi",
                    payload=_roi_payload(roi, centroid),
                    confidence=roi.confidence,
                ),
                Evidence(
                    kind="breast_geometry",
                    source="breast_geometry",
                    payload=_geometry_payload(geometry),
                ),
            ],
            warnings=warnings,
            metadata={
                "roi_id": roi.roi_id,
                "image_id": roi.image_id,
                "geometry_image_id": geometry.image_id,
                "frame_index": roi.frame_index,
                "frame_indices": list(roi.frame_indices),
                "coordinate_frame_id": continuous.coordinate_frame_id,
                "expected_axes": list(axes),
            },
        )


def _warnings_for_axes(
    expected_axes: Tuple[AxisName, ...],
    position: ContinuousAnatomicalPosition,
    geometry: BreastGeometry,
) -> List[AuditWarning]:
    warnings: List[AuditWarning] = []
    observed = set(position.observable_axes)

    for axis in expected_axes:
        if axis in observed:
            continue
        if axis == "depth":
            warnings.append(_depth_warning(geometry))
        elif axis in {"ml", "si"}:
            warnings.append(_transverse_warning(axis, geometry))
        else:
            warnings.append(
                AuditWarning(
                    code="unknown_axis",
                    message=f"Requested ROI localization axis is unknown: {axis}",
                    severity=WarningSeverity.INFO,
                    payload={"axis": axis, "image_id": geometry.image_id},
                )
            )

    return warnings


def _depth_warning(geometry: BreastGeometry) -> AuditWarning:
    missing = []
    if geometry.nipple is None:
        missing.append("nipple")
    if geometry.posterior_reference is None:
        missing.append("posterior_nipple_line")

    if missing:
        return AuditWarning(
            code="missing_landmark",
            message="ROI depth axis is unobservable because landmarks are missing",
            payload={
                "axis": "depth",
                "missing_landmarks": missing,
                "image_id": geometry.image_id,
            },
        )

    return AuditWarning(
        code="unobservable_axis",
        message="ROI depth axis is unobservable from the available geometry",
        payload={"axis": "depth", "image_id": geometry.image_id},
    )


def _transverse_warning(axis: AxisName, geometry: BreastGeometry) -> AuditWarning:
    missing = []
    if geometry.nipple is None:
        missing.append("nipple")
    if geometry.depth_vector is None:
        missing.append("posterior_nipple_line")

    if missing:
        return AuditWarning(
            code="missing_landmark",
            message=f"ROI {axis} axis is unobservable because landmarks are missing",
            payload={
                "axis": axis,
                "missing_landmarks": missing,
                "image_id": geometry.image_id,
            },
        )

    observable_axis = _view_observable_transverse_axis(geometry.view_position)
    return AuditWarning(
        code="unobservable_axis",
        message=f"ROI {axis} axis is not observable in {geometry.view_position.value} view",
        severity=WarningSeverity.INFO,
        payload={
            "axis": axis,
            "observable_axis": observable_axis,
            "view_position": geometry.view_position.value,
            "image_id": geometry.image_id,
        },
    )


def _view_observable_transverse_axis(view_position: ViewPosition) -> Optional[AxisName]:
    if view_position in {ViewPosition.CC, ViewPosition.XCCL}:
        return "ml"
    if view_position in {ViewPosition.MLO, ViewPosition.ML, ViewPosition.LM}:
        return "si"
    return None


def _quadrant_payload(quadrant: Quadrant) -> dict:
    return {
        "laterality": quadrant.laterality.value,
        "quadrant": {
            "ml": quadrant.ml.value,
            "si": quadrant.si.value,
            "depth": quadrant.depth.value,
        },
    }


def _continuous_payload(position: ContinuousAnatomicalPosition) -> dict:
    return {
        "laterality": position.laterality.value,
        "ml": position.ml_value,
        "si": position.si_value,
        "depth": position.depth_value,
        "observable_axes": list(position.observable_axes),
        "coordinate_frame_id": position.coordinate_frame_id,
    }


def _roi_payload(roi: RegionOfInterest, centroid: Tuple[float, float]) -> dict:
    return {
        "roi_id": roi.roi_id,
        "image_id": roi.image_id,
        "frame_index": roi.frame_index,
        "frame_indices": list(roi.frame_indices),
        "coordinates": list(roi.coordinates),
        "centroid": list(centroid),
        "coordinate_frame_id": roi.coordinate_frame_id,
    }


def _geometry_payload(geometry: BreastGeometry) -> dict:
    return {
        "image_id": geometry.image_id,
        "laterality": geometry.laterality.value,
        "view_position": geometry.view_position.value,
        "image_shape": list(geometry.image_shape)
        if geometry.image_shape is not None
        else None,
        "coordinate_frame_id": geometry.frame_id,
        "has_nipple": geometry.has_nipple,
        "has_posterior_nipple_line": geometry.has_posterior_nipple_line,
    }
