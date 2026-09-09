"""Focused W1 contract tests for standalone mutable imaging objects."""

import pytest

from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark, LandmarkType
from embed_toolkit.imaging.rois import Box, RegionOfInterest


def test_image_has_standalone_defaults_and_separate_source_identity() -> None:
    image = MammogramImage(
        "toolkit-image",
        source_sop_instance_uid="source-sop",
        source_paths={"/one/image.dcm", "/relocated/image.dcm"},
        derived_from="source-image",
    )

    assert image.identity == "toolkit-image"
    assert image.laterality is Laterality.UNKNOWN
    assert image.view_position is ViewPosition.UNKNOWN
    assert image.modality is ImageModality.UNKNOWN
    assert image.source_sop_instance_uid == "source-sop"
    assert image.source_paths == {"/one/image.dcm", "/relocated/image.dcm"}
    assert image.derived_from == "source-image"
    assert image.rois == ()


def test_image_update_and_subclass_attributes_are_in_place() -> None:
    class ReviewedImage(MammogramImage):
        pass

    image = ReviewedImage("image")
    image.reviewer = "reader-1"
    reference = image

    image.update(
        laterality=Laterality.LEFT,
        view_position=ViewPosition.MLO,
        reviewer="reader-2",
    )

    assert image is reference
    assert image.laterality is Laterality.LEFT
    assert image.view_position is ViewPosition.MLO
    assert image.reviewer == "reader-2"


def test_roi_identity_is_explicit_and_image_view_is_read_only() -> None:
    image = MammogramImage("image")
    roi = RegionOfInterest(
        coordinates=Box(10, 20, 30, 50),
        image_id="image",
        roi_key="collection-0",
        source_path="/image.dcm",
        collection_position=0,
    )

    assert image.add_roi(roi) is roi
    assert image.rois == (roi,)
    assert roi.identity == ("image", "collection-0")
    assert roi.source_path == "/image.dcm"
    assert roi.collection_position == 0
    assert image._children() == (roi,)

    with pytest.raises(AttributeError):
        image.rois.append(roi)  # type: ignore[attr-defined]


def test_roi_updates_in_place_and_preserves_raw_quality_facts() -> None:
    roi = RegionOfInterest(
        (10, 20, 5, 4),
        "image",
        "roi-0",
        confidence=1.5,
        source_frame_indices=(-1, -1),
        frame_provenance="derived",
    )
    reference = roi

    roi.update(coordinates=(11, 21, 6, 5), confidence=-0.25)

    assert roi is reference
    assert roi.coordinates == (11.0, 21.0, 6.0, 5.0)
    assert roi.height == -5.0
    assert roi.width == -16.0
    assert roi.confidence == -0.25
    assert roi.frame_indices == (-1, -1)


def test_coordinate_arity_remains_a_representation_check() -> None:
    with pytest.raises(ValueError, match="four values"):
        RegionOfInterest((1, 2, 3), "image", "roi-0")

    assert Box(10, 20, 5, 4).as_tuple() == (10.0, 20.0, 5.0, 4.0)


def test_landmarks_are_mutable_embedded_values_and_geometry_math_survives() -> None:
    image = MammogramImage("image", laterality=Laterality.LEFT, view_position=ViewPosition.MLO)
    nipple = ImageLandmark(
        20,
        60,
        LandmarkType.NIPPLE,
        confidence=1.25,
    )
    posterior = ImageLandmark(20, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_START)
    endpoint = ImageLandmark(20, 60, LandmarkType.POSTERIOR_NIPPLE_LINE_END)

    owned = image.add_landmark(nipple)
    owned.update(y=25, confidence=-1.0)
    geometry = image.breast_geometry(
        nipple=owned,
        posterior_nipple_line=(posterior, endpoint),
    )

    assert owned is image.landmarks[0]
    assert owned.y == 25.0
    assert owned.confidence == -1.0
    assert isinstance(geometry, BreastGeometry)
    assert geometry.posterior_distance == pytest.approx((50 ** 2 + 5 ** 2) ** 0.5)
    assert geometry.depth_value_for_point((22.5, 35)) == pytest.approx(1.0)


def test_roi_add_delegates_to_an_owning_graph() -> None:
    class RecordingGraph:
        def __init__(self) -> None:
            self.calls = []

        def attach(self, parent: MammogramImage, child: RegionOfInterest) -> RegionOfInterest:
            self.calls.append((parent, child))
            parent._attach_local(child)
            return child

    image = MammogramImage("image")
    graph = RecordingGraph()
    image._set_graph(graph)  # type: ignore[arg-type]
    roi = RegionOfInterest((0, 0, 1, 1), "image", "roi-0")

    assert image.add_roi(roi) is roi
    assert graph.calls == [(image, roi)]
    assert image.rois == (roi,)
