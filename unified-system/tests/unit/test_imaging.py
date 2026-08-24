from __future__ import annotations

import math

import pytest

from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark, LandmarkType
from embed_toolkit.imaging.rois import RegionOfInterest


def test_mammogram_image_coerces_identity_and_shape() -> None:
    image = MammogramImage(
        image_id="img-1",
        laterality="left",
        view_position="L MLO",
        modality="dbt",
        height=2048,
        width=1536,
        frame_count=72,
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
    assert image.identity == ("img-1", "sop", "series", "study")
    assert image.to_dict()["patient_id"] == "P-1"


def test_landmarks_are_image_owned_and_preserve_provenance() -> None:
    image = MammogramImage("img-1", Laterality.RIGHT, ViewPosition.CC)
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
    roi = RegionOfInterest((10, 20, 30, 50), roi_id="roi-1", image_id="img-1")

    assert roi.y_min == 10
    assert roi.x_min == 20
    assert roi.y_max == 30
    assert roi.x_max == 50
    assert roi.height == 20
    assert roi.width == 30
    assert roi.area == 600
    assert roi.centroid == (20, 35)


def test_embed_roi_factory_normalizes_inclusive_maxima_and_preserves_source() -> None:
    roi = RegionOfInterest.from_embed_coordinates((100, 200, 150, 250))
    pixel = RegionOfInterest.from_embed_coordinates((5, 7, 5, 7))

    assert roi.coordinates == (100, 200, 151, 251)
    assert roi.height == 51
    assert roi.width == 51
    assert roi.area == 2601
    assert roi.source_coordinates == (100, 200, 150, 250)
    assert roi.source_coordinate_convention == "inclusive_maxima"
    assert pixel.coordinates == (5, 7, 6, 8)
    assert pixel.area == 1


def test_roi_resize_and_realign_return_new_roi_and_preserve_dbt_frame() -> None:
    roi = RegionOfInterest(
        (10, 20, 30, 50),
        roi_id="roi-1",
        image_id="dbt-img",
        frame_index=17,
        source="embed",
    )

    resized = roi.resize(scale_y=0.5, scale_x=2.0, image_id="scaled-img")
    realigned = resized.realign(
        offset_y=4,
        offset_x=-10,
        image_id="aligned-img",
        coordinate_frame_id="aligned-frame",
    )

    assert resized.coordinates == (5, 40, 15, 100)
    assert resized.image_id == "scaled-img"
    assert resized.frame_index == 17
    assert resized.source == "embed"
    assert realigned.coordinates == (9, 30, 19, 90)
    assert realigned.image_id == "aligned-img"
    assert realigned.coordinate_frame_id == "aligned-frame"
    assert realigned.frame_index == 17
    assert roi.coordinates == (10, 20, 30, 50)


def test_roi_singular_frame_accessor_only_returns_exactly_one_frame() -> None:
    plural = RegionOfInterest((0, 0, 1, 1), frame_indices=(12, 13))
    singular = RegionOfInterest((0, 0, 1, 1), frame_index=20)

    assert plural.frame_indices == (12, 13)
    assert plural.frame_index is None
    assert singular.frame_indices == (20,)
    assert singular.frame_index == 20


def test_roi_iou_and_containment_ratio() -> None:
    roi = RegionOfInterest((0, 0, 10, 10))
    overlapping = RegionOfInterest((5, 5, 15, 15))
    container = RegionOfInterest((-5, -5, 20, 20))

    assert roi.intersection_area(overlapping) == 25
    assert roi.iou(overlapping) == pytest.approx(25 / 175)
    assert roi.containment_ratio(overlapping) == pytest.approx(0.25)
    assert roi.containment_ratio(container) == 1.0
    assert overlapping.containment_ratio(roi) == pytest.approx(0.25)


def test_roi_center_distance() -> None:
    roi = RegionOfInterest((0, 0, 10, 10))
    other = RegionOfInterest((6, 8, 16, 18))

    assert roi.center_distance(other) == pytest.approx(10.0)
    assert roi.center_distance(roi) == 0.0
    assert math.isclose(other.center_distance(roi), roi.center_distance(other))


def test_roi_validation_rejects_invalid_geometry_and_metadata() -> None:
    with pytest.raises(ValueError):
        RegionOfInterest((10, 0, 5, 10))
    with pytest.raises(ValueError):
        RegionOfInterest((0, 0, 1, 1), frame_index=-1)
    with pytest.raises(ValueError):
        RegionOfInterest((0, 0, 1, 1), frame_indices=(0, -1))
    with pytest.raises(ValueError):
        RegionOfInterest((0, 0, 1, 1), confidence=1.5)
