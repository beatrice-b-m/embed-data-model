from __future__ import annotations

import json

import pytest

from embed_toolkit.audit.evidence import Evidence
from embed_toolkit.audit.results import LocalizationResult, MatchingResult, ResultStatus
from embed_toolkit.core.primitives import Laterality, ViewPosition
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark, LandmarkType
from embed_toolkit.imaging.rois import RegionOfInterest
from embed_toolkit.visualization.mammogram import build_mammogram_render_plan


def test_mammogram_render_plan_includes_pixels_roi_and_centroid_layers() -> None:
    image = MammogramImage(
        "img-1",
        Laterality.LEFT,
        ViewPosition.CC,
        [
            SourceLocator(
                scope="visualization-tests",
                scope_kind=SourceScopeKind.MATERIALIZATION,
                source_profile="test",
                source_table="images",
                row_ordinal=0,
            )
        ],
        height=3,
        width=4,
    )
    roi = RegionOfInterest(
        (0, 1, 2, 3),
        roi_id="roi-1",
        image_id="img-1",
        source="synthetic",
        confidence=0.8,
    )

    plan = build_mammogram_render_plan(
        image=image,
        pixels=[[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]],
        rois=[roi],
        title="Synthetic review",
    ).to_dict()

    assert plan["image_id"] == "img-1"
    assert plan["shape"] == [3, 4]
    assert plan["metadata"]["title"] == "Synthetic review"
    assert plan["metadata"]["renderer"] == "serializable_plan"
    assert [layer["type"] for layer in plan["layers"][:3]] == [
        "image_pixels",
        "roi_box",
        "centroid",
    ]
    assert plan["layers"][0]["intensity_range"] == [0.0, 11.0]
    assert plan["layers"][0]["values"][1][2] == 6
    assert plan["layers"][1]["coordinates"] == [0.0, 1.0, 2.0, 3.0]
    assert plan["layers"][2]["point"] == [1.0, 2.0]
    json.dumps(plan)


def test_mammogram_render_plan_adds_landmarks_pnl_and_depth_thirds() -> None:
    geometry = BreastGeometry(
        image_id="img-cc",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        image_shape=(9, 12),
        coordinate_frame_id="aligned-cc",
        nipple=ImageLandmark(4, 10, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(4, 1, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(4, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )

    plan = build_mammogram_render_plan(geometry=geometry).to_dict()
    layers_by_type = {}
    for layer in plan["layers"]:
        layers_by_type.setdefault(layer["type"], []).append(layer)

    assert plan["shape"] == [9, 12]
    assert len(layers_by_type["landmark"]) == 3
    assert layers_by_type["posterior_nipple_line"][0]["points"] == [
        [4, 1],
        [4, 10],
    ]
    assert [layer["boundary"] for layer in layers_by_type["depth_third_boundary"]] == [
        "anterior_middle",
        "middle_posterior",
    ]
    assert layers_by_type["depth_third_boundary"][0]["points"] == [
        [0.0, 7.0],
        [8.0, 7.0],
    ]
    assert layers_by_type["depth_third_boundary"][1]["points"] == [
        [0.0, 4.0],
        [8.0, 4.0],
    ]


def test_mammogram_render_plan_preserves_workflow_expectations_and_match_evidence() -> None:
    finding_expectation = LocalizationResult(
        status=ResultStatus.SUCCESS,
        subject_id="finding-1",
        subject_type="finding",
        anatomical_position={
            "laterality": "left",
            "quadrant": {"ml": "lateral", "si": "unknown", "depth": "middle"},
        },
        evidence=[
            Evidence(
                kind="clinical_location",
                source="magview",
                payload={"field": "loc", "normalized_value": "lateral"},
            )
        ],
    )
    match = MatchingResult(
        status=ResultStatus.SUCCESS,
        finding_id="finding-1",
        matched_roi_id="roi-1",
        metadata={"score": 0.92},
    )

    plan = build_mammogram_render_plan(
        pixels=[[1]],
        finding_expectations=[finding_expectation],
        match_evidence=[match],
        include_pixel_values=False,
    ).to_dict()

    assert "values" not in plan["layers"][0]
    assert plan["layers"][1]["type"] == "finding_expectation"
    assert plan["layers"][1]["payload"]["subject_id"] == "finding-1"
    assert plan["layers"][1]["payload"]["evidence"][0]["payload"] == {
        "field": "loc",
        "normalized_value": "lateral",
    }
    assert plan["layers"][2]["type"] == "match_evidence"
    assert plan["layers"][2]["payload"]["matched_roi_id"] == "roi-1"
    json.dumps(plan)


def test_mammogram_render_plan_omits_depth_thirds_without_image_shape() -> None:
    geometry = BreastGeometry(
        image_id="img-no-shape",
        laterality=Laterality.RIGHT,
        view_position=ViewPosition.MLO,
        nipple=ImageLandmark(10, 10, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(30, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(10, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )

    plan = build_mammogram_render_plan(geometry=geometry).to_dict()

    assert "posterior_nipple_line" in [layer["type"] for layer in plan["layers"]]
    assert "depth_third_boundary" not in [layer["type"] for layer in plan["layers"]]
    assert plan["metadata"]["coordinate_frame_id"] == "img-no-shape"


def test_mammogram_render_plan_rejects_non_2d_pixels() -> None:
    with pytest.raises(TypeError):
        build_mammogram_render_plan(pixels=3)
