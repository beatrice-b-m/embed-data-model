from __future__ import annotations

import pytest

from embed_toolkit.adapters.embed import (
    build_clinical_tables,
    build_image_tables,
    join_findings_to_images,
)
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
        posterior_nipple_line=(
            ImageLandmark(50, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(50, 90, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )


def mlo_geometry() -> BreastGeometry:
    return BreastGeometry(
        image_id="left-mlo",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.MLO,
        image_shape=(120, 120),
        coordinate_frame_id="left-mlo-aligned",
        nipple=ImageLandmark(90, 50, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(10, 50, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(90, 50, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
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


def test_legacy_parity_bilateral_and_missing_side_expand_for_image_join() -> None:
    clinical = build_clinical_tables(
        [
            {"empi_anon": "P1", "acc_anon": "ACC-EXPAND", "numfind": "B", "side": "B"},
            {"empi_anon": "P1", "acc_anon": "ACC-EXPAND", "numfind": "U"},
        ]
    )
    images = build_image_tables(
        [
            {
                "image_id": "left-cc",
                "acc_anon": "ACC-EXPAND",
                "ImageLateralityFinal": "L",
                "ViewPosition": "CC",
            },
            {
                "image_id": "right-cc",
                "acc_anon": "ACC-EXPAND",
                "ImageLateralityFinal": "R",
                "ViewPosition": "CC",
            },
            {
                "image_id": "other-left-cc",
                "acc_anon": "ACC-OTHER",
                "ImageLateralityFinal": "L",
                "ViewPosition": "CC",
            },
        ]
    )

    joins = join_findings_to_images(clinical.findings, images.images)
    joined_image_ids = {
        join.finding.finding_id: [image.image_id for image in join.images]
        for join in joins
    }

    assert [finding.laterality for finding in clinical.findings] == [
        Laterality.LEFT,
        Laterality.RIGHT,
        Laterality.UNKNOWN,
    ]
    assert joined_image_ids == {
        "ACC-EXPAND:L:B": ["left-cc"],
        "ACC-EXPAND:R:B": ["right-cc"],
        "ACC-EXPAND:UNKNOWN:U": ["left-cc", "right-cc"],
    }


def test_legacy_parity_localization_preserves_source_evidence() -> None:
    result = FindingLocalizer(source="magview-parity").localize(
        laterality="L",
        raw_source_fields={"loc_code": "L", "depth_code": "P", "clock": "3"},
        subject_id="finding-source-evidence",
    )

    assert result.status is ResultStatus.SUCCESS
    assert result.metadata["source"] == "magview-parity"
    assert result.metadata["preferred_source"] == "magview-parity"
    assert [
        (item.kind, item.source, item.payload["field"], item.payload["raw_value"])
        for item in result.evidence
    ] == [
        ("depth", "magview-parity", "depth_code", "P"),
        ("clock", "magview-parity", "clock_code", "3"),
        ("location", "magview-parity", "location_code", "L"),
    ]


def test_legacy_parity_roi_localization_preserves_geometry_evidence() -> None:
    roi = RegionOfInterest(
        (75, 85, 85, 95),
        roi_id="roi-source-evidence",
        image_id="left-cc",
        frame_index=7,
        source="roi-table",
        confidence=0.75,
        coordinate_frame_id="left-cc-aligned",
    )

    result = RoiLocalizer(expected_axes=("ml", "depth")).localize(roi, cc_geometry())

    roi_evidence = result.evidence[0]
    geometry_evidence = result.evidence[1]
    assert result.status is ResultStatus.SUCCESS
    assert result.metadata["frame_index"] == 7
    assert roi_evidence.kind == "roi_geometry"
    assert roi_evidence.source == "roi-table"
    assert roi_evidence.confidence == 0.75
    assert roi_evidence.payload == {
        "roi_id": "roi-source-evidence",
        "image_id": "left-cc",
        "frame_index": 7,
        "coordinates": [75, 85, 85, 95],
        "centroid": [80.0, 90.0],
        "coordinate_frame_id": "left-cc-aligned",
    }
    assert geometry_evidence.kind == "breast_geometry"
    assert geometry_evidence.payload["coordinate_frame_id"] == "left-cc-aligned"


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
