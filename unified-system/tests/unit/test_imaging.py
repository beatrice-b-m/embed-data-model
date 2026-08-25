from __future__ import annotations

import math
from dataclasses import replace
from typing import Optional

import pytest

from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark, LandmarkType
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocator,
    RoiSourceCount,
    RoiSourceCountBasis,
    RoiSourceProvenance,
)
from embed_toolkit.imaging.rois import RegionOfInterest


def source() -> SourceLocator:
    return SourceLocator(
        scope="imaging-tests",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="images",
        row_ordinal=0,
    )


def roi(
    coordinates: tuple[float, float, float, float],
    *,
    image_id: str = "img-1",
    source_value: str = "roi-1",
    frame_indices: tuple[int, ...] = (),
    annotation_source: Optional[str] = None,
    confidence: Optional[float] = None,
) -> RegionOfInterest:
    image_source = source()
    modality = ImageModality.DBT if frame_indices else ImageModality.FFDM
    provenance = RoiSourceProvenance(
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
    )
    return RegionOfInterest(
        coordinates,
        locator=RoiLocator.from_source(
            image_locator=image_source,
            source_value=source_value,
        ),
        image_id=image_id,
        source_provenance=provenance,
        sources=(image_source,),
        annotation_source=annotation_source,
        confidence=confidence,
    )


def test_mammogram_image_coerces_identity_and_shape() -> None:
    image = MammogramImage(
        image_id="img-1",
        laterality="left",
        view_position="L MLO",
        sources=[source()],
        modality="dbt",
        height=2048,
        width=1536,
        frame_count=72,
        source_modality=" MG ",
        derived_image_type="3D",
        patient_id="P-1",
        study_instance_uid="study",
        series_instance_uid="series",
        sop_instance_uid="sop",
    )

    assert image.laterality is Laterality.LEFT
    assert image.view_position is ViewPosition.MLO
    assert image.modality is ImageModality.DBT
    assert image.is_dbt
    assert image.image_shape == (2048, 1536)
    assert image.source_modality == "MG"
    assert image.derived_image_type == "3D"
    assert image.to_dict()["derived_image_type"] == "3D"
    assert image.identity == ("img-1", "sop", "series", "study")
    assert image.to_dict()["patient_id"] == "P-1"


def test_landmarks_are_image_owned_and_preserve_provenance() -> None:
    image = MammogramImage(
        "img-1",
        Laterality.RIGHT,
        ViewPosition.CC,
        [source()],
    )
    landmark = ImageLandmark(
        y=12.5,
        x=40.0,
        landmark_type=LandmarkType.NIPPLE,
        image_id="source-image",
        source="model",
        confidence=0.75,
        provenance="run-42",
    )

    owned = image.add_landmark(landmark)

    assert owned.image_id == "img-1"
    assert owned.source == "model"
    assert owned.confidence == 0.75
    assert owned.provenance == "run-42"
    assert image.landmarks == (owned,)
    assert landmark.image_id == "source-image"


def test_breast_geometry_holds_coordinate_frame_facts_without_matching() -> None:
    image = MammogramImage(
        "img-1",
        Laterality.LEFT,
        ViewPosition.MLO,
        [source()],
        height=100,
        width=80,
        coordinate_frame_id="aligned-left-mlo",
    )
    nipple = ImageLandmark(20, 60, LandmarkType.NIPPLE, source="manual")
    p1 = ImageLandmark(20, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_START)
    p2 = ImageLandmark(20, 60, LandmarkType.POSTERIOR_NIPPLE_LINE_END)

    geometry = image.breast_geometry(
        nipple=nipple,
        posterior_nipple_line=(p1, p2),
    )

    assert isinstance(geometry, BreastGeometry)
    assert geometry.frame_id == "aligned-left-mlo"
    assert geometry.image_shape == (100, 80)
    assert geometry.has_nipple
    assert geometry.has_posterior_nipple_line
    assert geometry.nipple is not None
    assert geometry.nipple.image_id == "img-1"


def test_roi_uses_canonical_half_open_yxyx_geometry() -> None:
    observed = roi((10, 20, 30, 50))

    assert observed.y_min == 10
    assert observed.x_min == 20
    assert observed.y_max == 30
    assert observed.x_max == 50
    assert observed.height == 20
    assert observed.width == 30
    assert observed.area == 600
    assert observed.centroid == (20, 35)


def test_embed_roi_factory_normalizes_inclusive_maxima_and_preserves_source() -> None:
    base = roi((0, 0, 1, 1))
    observed = RegionOfInterest.from_embed_coordinates(
        (100, 200, 150, 250),
        locator=base.locator,
        image_id=base.image_id,
        source_provenance=base.source_provenance,
        sources=base.sources,
    )
    pixel = RegionOfInterest.from_embed_coordinates(
        (5, 7, 5, 7),
        locator=base.locator,
        image_id=base.image_id,
        source_provenance=base.source_provenance,
        sources=base.sources,
    )

    assert observed.coordinates == (100, 200, 151, 251)
    assert observed.height == 51
    assert observed.width == 51
    assert observed.area == 2601
    assert observed.source_coordinates == (100, 200, 150, 250)
    assert observed.source_coordinate_convention == "inclusive_maxima"
    assert pixel.coordinates == (5, 7, 6, 8)
    assert pixel.area == 1


def test_roi_resize_and_realign_require_governed_image_scope_changes() -> None:
    observed = replace(roi(
        (10, 20, 30, 50),
        image_id="dbt-img",
        frame_indices=(17,),
        annotation_source="embed",
    ), coordinate_frame_id="original-frame")

    resized = observed.resize(scale_y=0.5, scale_x=2.0)
    realigned = resized.realign(
        offset_y=4,
        offset_x=-10,
        coordinate_frame_id="aligned-frame",
    )

    assert resized.coordinates == (5, 40, 15, 100)
    assert resized.image_id == "dbt-img"
    assert resized.frame_indices == (17,)
    assert resized.annotation_source == "embed"
    assert realigned.coordinates == (9, 30, 19, 90)
    assert realigned.image_id == "dbt-img"
    assert realigned.coordinate_frame_id == "aligned-frame"
    assert realigned.frame_indices == (17,)
    assert observed.coordinates == (10, 20, 30, 50)

    with pytest.raises(ValueError, match="requires locator"):
        observed.resize(scale_y=1, scale_x=1, image_id="other-image")

    target_source = replace(source(), row_ordinal=1)
    ownership = {
        "image_id": "other-image",
        "locator": RoiLocator.from_source(
            image_locator=target_source,
            source_value="roi-1",
        ),
        "source_provenance": observed.source_provenance,
        "sources": (target_source,),
    }
    reassigned = observed.resize(scale_y=1, scale_x=1, **ownership)
    explicitly_reframed = observed.realign(
        **ownership,
        coordinate_frame_id="other-frame",
    )

    assert reassigned.coordinate_frame_id is None
    assert explicitly_reframed.coordinate_frame_id == "other-frame"


def test_roi_frame_indices_project_from_governed_provenance() -> None:
    plural = roi((0, 0, 1, 1), frame_indices=(12, 13))

    assert plural.frame_indices == (12, 13)
    assert plural.to_dict()["source_provenance"]["frame_indices"] == [12, 13]


def test_roi_iou_and_containment_ratio() -> None:
    observed = roi((0, 0, 10, 10), source_value="observed")
    overlapping = roi((5, 5, 15, 15), source_value="overlap")
    container = roi((-5, -5, 20, 20), source_value="container")

    assert observed.intersection_area(overlapping) == 25
    assert observed.iou(overlapping) == pytest.approx(25 / 175)
    assert observed.containment_ratio(overlapping) == pytest.approx(0.25)
    assert observed.containment_ratio(container) == 1.0
    assert overlapping.containment_ratio(observed) == pytest.approx(0.25)


def test_roi_center_distance() -> None:
    observed = roi((0, 0, 10, 10), source_value="observed")
    other = roi((6, 8, 16, 18), source_value="other")

    assert observed.center_distance(other) == pytest.approx(10.0)
    assert observed.center_distance(observed) == 0.0
    assert math.isclose(
        other.center_distance(observed), observed.center_distance(other)
    )


def test_roi_validation_rejects_invalid_geometry_and_metadata() -> None:
    with pytest.raises(ValueError):
        roi((10, 0, 5, 10))
    with pytest.raises(ValueError):
        roi((0, 0, 1, 1), confidence=1.5)
