from __future__ import annotations

import pytest

from embed_toolkit.audit.results import ResultStatus
from embed_toolkit.core.primitives import Laterality, ViewPosition
from embed_toolkit.imaging.alignment import Alignment, AlignmentDirection
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark, LandmarkType
from embed_toolkit.imaging.rois import RegionOfInterest
from embed_toolkit.workflows.finding_localization import FindingLocalizer
from embed_toolkit.workflows.finding_roi_matching import FindingRoiMatcher
from embed_toolkit.workflows.roi_localization import RoiLocalizer


def warning_codes(result: object) -> set[str]:
    return {warning.code for warning in result.warnings}


def candidate_for(result: object, roi_id: str) -> object:
    return next(candidate for candidate in result.candidates if candidate.roi_id == roi_id)


def cc_geometry(
    *,
    image_id: str = "left-cc",
    laterality: Laterality = Laterality.LEFT,
) -> BreastGeometry:
    return BreastGeometry(
        image_id=image_id,
        laterality=laterality,
        view_position=ViewPosition.CC,
        image_shape=(120, 120),
        coordinate_frame_id=f"{image_id}-aligned",
        nipple=ImageLandmark(50, 90, LandmarkType.NIPPLE),
        posterior_boundary=ImageLandmark(50, 10, LandmarkType.POSTERIOR_BREAST_BOUNDARY),
    )


def mlo_geometry() -> BreastGeometry:
    return BreastGeometry(
        image_id="left-mlo",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.MLO,
        image_shape=(120, 120),
        coordinate_frame_id="left-mlo-aligned",
        nipple=ImageLandmark(90, 50, LandmarkType.NIPPLE),
        posterior_boundary=ImageLandmark(10, 50, LandmarkType.CHEST_WALL),
    )


def aligned_roi(
    roi_id: str,
    coordinates: tuple[float, float, float, float],
    *,
    image_id: str = "left-cc",
) -> RegionOfInterest:
    return RegionOfInterest(
        coordinates,
        roi_id=roi_id,
        image_id=image_id,
        source="synthetic-parity",
        coordinate_frame_id=f"{image_id}-aligned",
    )


def test_legacy_parity_clock_mapping_is_laterality_aware_before_matching() -> None:
    localizer = FindingLocalizer()

    left = localizer.localize(
        laterality="L",
        clock_code="3",
        depth_code="P",
        subject_id="left-three-o-clock",
    )
    right = localizer.localize(
        laterality="R",
        clock_code="3",
        depth_code="P",
        subject_id="right-three-o-clock",
    )

    assert left.anatomical_position["quadrant"] == {
        "laterality": "L",
        "ml": "lateral",
        "si": "central",
        "depth": "posterior",
    }
    assert right.anatomical_position["quadrant"] == {
        "laterality": "R",
        "ml": "medial",
        "si": "central",
        "depth": "posterior",
    }


def test_legacy_parity_mlo_roi_geometry_maps_view_observable_axis() -> None:
    roi = aligned_roi(
        "roi-left-mlo-superior-posterior",
        (25, 5, 35, 15),
        image_id="left-mlo",
    )

    result = RoiLocalizer(expected_axes=("si", "depth")).localize(roi, mlo_geometry())

    assert result.status is ResultStatus.SUCCESS
    assert result.continuous_position["si"] == pytest.approx(0.5)
    assert result.continuous_position["depth"] == pytest.approx(1.5)
    assert result.continuous_position["observable_axes"] == ["si", "depth"]
    assert result.anatomical_position["quadrant"] == {
        "ml": "unknown",
        "si": "superior",
        "depth": "posterior",
    }


def test_legacy_parity_matching_uses_aligned_roi_geometry_and_reports_unmatched() -> None:
    raw_alignment = Alignment(AlignmentDirection.RIGHT, AlignmentDirection.DOWN)
    raw_box = (15, 85, 25, 95)
    aligned_box = raw_alignment.realign_box(raw_box, height=120, width=120)
    matched_roi = aligned_roi("roi-matched", aligned_box)
    unmatched_roi = aligned_roi("roi-unmatched", (45, 45, 55, 55))
    geometry = cc_geometry()

    finding = FindingLocalizer().localize(
        laterality="L",
        clock_code="3",
        depth_code="P",
        subject_id="finding-left-lateral-posterior",
    )
    roi_results = [
        RoiLocalizer(expected_axes=("ml", "depth")).localize(matched_roi, geometry),
        RoiLocalizer(expected_axes=("ml", "depth")).localize(unmatched_roi, geometry),
    ]

    result = FindingRoiMatcher(axes=("ml", "depth")).match([finding], roi_results)[0]
    matched_candidate = candidate_for(result, "roi-matched")
    unmatched_candidate = candidate_for(result, "roi-unmatched")

    assert aligned_box == (95.0, 25.0, 105.0, 35.0)
    assert result.matched_roi_id == "roi-matched"
    assert result.unmatched_roi_ids == ["roi-unmatched"]
    assert result.status is ResultStatus.PARTIAL
    assert "unmatched_rois" in warning_codes(result)
    assert matched_candidate.score == 1.0
    assert matched_candidate.payload["scored_axes"] == ["ml", "depth"]
    assert unmatched_candidate.score == 0.0
    assert unmatched_candidate.payload["axis_scores"] == [
        {
            "axis": "ml",
            "finding_value": "lateral",
            "roi_value": "central",
            "matched": False,
        },
        {
            "axis": "depth",
            "finding_value": "posterior",
            "roi_value": "middle",
            "matched": False,
        },
    ]
