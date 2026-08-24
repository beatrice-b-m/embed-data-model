from __future__ import annotations

import json

import pytest

from embed_toolkit.audit.results import ResultStatus
from embed_toolkit.core.anatomy import (
    DepthThird,
    MedialLateralAxis,
    SuperiorInferiorAxis,
)
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark, LandmarkType
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocator,
    RoiSourceCount,
    RoiSourceCountBasis,
    RoiSourceProvenance,
)
from embed_toolkit.imaging.rois import RegionOfInterest
from embed_toolkit.workflows.roi_localization import RoiLocalizer


def roi(
    coordinates: tuple[float, float, float, float],
    value: str,
    image_id: str,
    *,
    frame_indices: tuple[int, ...] = (),
    annotation_source: str | None = None,
    confidence: float | None = None,
    coordinate_frame_id: str | None = None,
) -> RegionOfInterest:
    source = SourceLocator(
        scope="roi-localization-tests",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="images",
        source_key=image_id,
    )
    modality = ImageModality.DBT if frame_indices else ImageModality.FFDM
    return RegionOfInterest(
        coordinates,
        locator=RoiLocator.from_source(
            image_locator=source,
            source_value=value,
        ),
        image_id=image_id,
        source_provenance=RoiSourceProvenance(
            modality=modality,
            source_count=RoiSourceCount(
                1,
                RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE,
            ),
            depth_frame_provenance=(
                RoiDepthFrameProvenance.SOURCE_SUPPLIED
                if frame_indices
                else RoiDepthFrameProvenance.NOT_APPLICABLE_2D
            ),
            frame_indices=frame_indices,
        ),
        sources=(source,),
        annotation_source=annotation_source,
        confidence=confidence,
        coordinate_frame_id=coordinate_frame_id,
    )


def test_roi_localizer_projects_centroid_to_continuous_and_discrete_position() -> None:
    observed = roi(
        (45, 45, 55, 55),
        "roi-1",
        "img-cc",
        annotation_source="embed",
        confidence=0.9,
    )
    geometry = BreastGeometry(
        image_id="img-cc",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        coordinate_frame_id="aligned-left-cc",
        nipple=ImageLandmark(50, 90, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(50, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(50, 90, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )

    result = RoiLocalizer(expected_axes=("ml", "depth")).localize(observed, geometry)
    serialized = result.to_dict()

    assert result.status is ResultStatus.SUCCESS
    assert serialized["roi_locator"] == observed.locator.to_dict()
    assert "subject_id" not in serialized
    assert serialized["continuous_position"]["ml"] == pytest.approx(0.0)
    assert serialized["continuous_position"]["depth"] == pytest.approx(1.0)
    assert serialized["continuous_position"]["observable_axes"] == ["ml", "depth"]
    assert serialized["anatomical_position"]["quadrant"] == {
        "ml": MedialLateralAxis.CENTRAL.value,
        "si": SuperiorInferiorAxis.UNKNOWN.value,
        "depth": DepthThird.MIDDLE.value,
    }
    assert serialized["evidence"][0]["payload"]["centroid"] == [50.0, 50.0]
    assert (
        serialized["evidence"][1]["payload"]["coordinate_frame_id"] == "aligned-left-cc"
    )
    json.dumps(serialized)


def test_roi_localizer_returns_partial_result_when_nipple_and_depth_are_missing() -> (
    None
):
    observed = roi((10, 20, 30, 40), "roi-2", "img-missing")
    geometry = BreastGeometry(
        image_id="img-missing",
        laterality=Laterality.RIGHT,
        view_position=ViewPosition.MLO,
    )

    result = RoiLocalizer().localize(observed, geometry)
    serialized = result.to_dict()

    assert result.status is ResultStatus.PARTIAL
    assert serialized["continuous_position"]["observable_axes"] == []
    assert serialized["anatomical_position"]["quadrant"] == {
        "ml": "unknown",
        "si": "unknown",
        "depth": "unknown",
    }
    assert [warning["payload"]["axis"] for warning in serialized["warnings"]] == [
        "ml",
        "si",
        "depth",
    ]
    for warning in serialized["warnings"]:
        assert warning["code"] == "missing_landmark"
        assert "nipple" in warning["payload"]["missing_landmarks"]


def test_roi_localizer_names_si_unobservable_for_cc_view() -> None:
    observed = roi((45, 45, 55, 55), "roi-cc", "img-cc")
    geometry = BreastGeometry(
        image_id="img-cc",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        nipple=ImageLandmark(50, 90, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(50, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(50, 90, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )

    result = RoiLocalizer().localize(observed, geometry)
    serialized = result.to_dict()

    assert result.status is ResultStatus.PARTIAL
    assert serialized["continuous_position"]["observable_axes"] == ["ml", "depth"]
    assert len(serialized["warnings"]) == 1
    assert serialized["warnings"][0]["code"] == "unobservable_axis"
    assert serialized["warnings"][0]["payload"] == {
        "axis": "si",
        "observable_axis": "ml",
        "view_position": "CC",
        "image_id": "img-cc",
    }


def test_roi_localizer_names_ml_unobservable_for_mlo_view() -> None:
    observed = roi((40, 30, 60, 50), "roi-mlo", "img-mlo")
    geometry = BreastGeometry(
        image_id="img-mlo",
        laterality=Laterality.RIGHT,
        view_position=ViewPosition.MLO,
        nipple=ImageLandmark(20, 20, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(80, 20, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(20, 20, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )

    result = RoiLocalizer().localize(observed, geometry)
    serialized = result.to_dict()

    assert result.status is ResultStatus.PARTIAL
    assert serialized["continuous_position"]["si"] == pytest.approx(1 / 3)
    assert serialized["continuous_position"]["depth"] == pytest.approx(1.0)
    assert serialized["continuous_position"]["observable_axes"] == ["si", "depth"]
    assert serialized["anatomical_position"]["quadrant"]["si"] == "central"
    assert serialized["warnings"][0]["payload"] == {
        "axis": "ml",
        "observable_axis": "si",
        "view_position": "MLO",
        "image_id": "img-mlo",
    }


def test_roi_localizer_preserves_dbt_frame_in_metadata_and_evidence() -> None:
    observed = roi(
        (40, 45, 60, 55),
        "roi-dbt",
        "dbt-img",
        frame_indices=(23,),
        annotation_source="embed-roi-csv",
        coordinate_frame_id="dbt-frame-23",
    )
    geometry = BreastGeometry(
        image_id="dbt-img",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        coordinate_frame_id="aligned-dbt",
        nipple=ImageLandmark(50, 90, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(50, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(50, 90, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )

    serialized = (
        RoiLocalizer(expected_axes=("ml", "depth"))
        .localize(observed, geometry)
        .to_dict()
    )

    assert serialized["metadata"]["frame_indices"] == [23]
    assert serialized["metadata"]["image_id"] == "dbt-img"
    assert serialized["metadata"]["coordinate_frame_id"] == "aligned-dbt"
    assert serialized["evidence"][0]["source"] == "embed-roi-csv"
    assert serialized["evidence"][0]["payload"]["frame_indices"] == [23]
    assert serialized["evidence"][0]["payload"]["coordinate_frame_id"] == "dbt-frame-23"
    json.dumps(serialized)
