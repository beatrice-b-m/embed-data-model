from __future__ import annotations

import pytest

from embed_toolkit.core.anatomy import DepthThird
from embed_toolkit.core.primitives import Laterality, ViewPosition
from embed_toolkit.imaging.alignment import Alignment, AlignmentDirection
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark, LandmarkType


def test_alignment_realigns_boxes_with_horizontal_and_vertical_flips() -> None:
    alignment = Alignment(AlignmentDirection.RIGHT, AlignmentDirection.DOWN)

    box = alignment.realign_box((10, 20, 30, 70), height=100, width=200)
    point = alignment.realign_point((15, 25), height=100, width=200)

    assert box == (70, 130, 90, 180)
    assert point == (85, 175)


def test_alignment_realigns_box_list_to_explicit_target() -> None:
    source = Alignment.reference()
    target = Alignment(AlignmentDirection.RIGHT, AlignmentDirection.DOWN)

    boxes = source.realign_boxes(
        [(0, 0, 10, 20), (40, 50, 60, 90)],
        height=100,
        width=200,
        target_alignment=target,
    )

    assert boxes == ((90, 180, 100, 200), (40, 110, 60, 150))


def test_alignment_flips_nested_sequence_images() -> None:
    image = [[1, 2, 3], [4, 5, 6]]
    alignment = Alignment(AlignmentDirection.RIGHT, AlignmentDirection.DOWN)

    realigned = alignment.realign_image(image)

    assert realigned == ([6, 5, 4], [3, 2, 1])


def test_alignment_from_orientation_and_fov_match_reference_flips() -> None:
    orientation_alignment = Alignment.from_orientation(
        ("P", "R"),
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
    )
    fov_alignment = Alignment.from_fov(
        rotation=180.0,
        horizontal_flip="NO",
        laterality=Laterality.RIGHT,
    )

    assert orientation_alignment == Alignment(
        AlignmentDirection.RIGHT,
        AlignmentDirection.UP,
    )
    assert fov_alignment == Alignment(
        AlignmentDirection.LEFT,
        AlignmentDirection.DOWN,
    )


def test_alignment_rejects_rotated_targets() -> None:
    with pytest.raises(NotImplementedError):
        Alignment.reference().realign_box(
            (0, 0, 1, 1),
            height=10,
            width=10,
            target_alignment=Alignment(AlignmentDirection.UP, AlignmentDirection.LEFT),
        )


def test_alignment_rejects_rotated_sources() -> None:
    with pytest.raises(NotImplementedError):
        Alignment(AlignmentDirection.UP, AlignmentDirection.LEFT).realign_box(
            (0, 0, 1, 1),
            height=10,
            width=10,
        )


def test_breast_geometry_depth_thirds_from_nipple_and_posterior_line() -> None:
    geometry = BreastGeometry(
        image_id="img-1",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        nipple=ImageLandmark(50, 90, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(50, 10, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(50, 90, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )

    assert geometry.depth_third_for_point((50, 80)) is DepthThird.ANTERIOR
    assert geometry.depth_third_for_point((50, 50)) is DepthThird.MIDDLE
    assert geometry.depth_third_for_point((50, 20)) is DepthThird.POSTERIOR
    assert geometry.depth_value_for_point((50, 50)) == pytest.approx(1.0)


def test_breast_geometry_uses_farthest_pnl_endpoint_for_depth() -> None:
    geometry = BreastGeometry(
        image_id="img-1",
        laterality=Laterality.RIGHT,
        view_position=ViewPosition.MLO,
        coordinate_frame_id="aligned-img-1",
        nipple=ImageLandmark(20, 20, LandmarkType.NIPPLE),
        posterior_nipple_line=(
            ImageLandmark(80, 20, LandmarkType.POSTERIOR_NIPPLE_LINE_START),
            ImageLandmark(20, 20, LandmarkType.POSTERIOR_NIPPLE_LINE_END),
        ),
    )

    position = geometry.continuous_position_for_point((50, 35))

    assert geometry.posterior_reference == geometry.posterior_nipple_line[0]
    assert position.depth_value == pytest.approx(1.0)
    assert position.si_value == pytest.approx(0.25)
    assert position.ml_value is None
    assert position.coordinate_frame_id == "aligned-img-1"


def test_breast_geometry_returns_partial_position_without_posterior_landmarks() -> None:
    geometry = BreastGeometry(
        image_id="img-1",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        nipple=ImageLandmark(30, 40, LandmarkType.NIPPLE),
    )

    position = geometry.continuous_position_for_point((30, 10))

    assert geometry.posterior_reference is None
    assert geometry.depth_third_for_point((30, 10)) is DepthThird.UNKNOWN
    assert position.observable_axes == ()
    assert position.to_quadrant().depth is DepthThird.UNKNOWN
