from __future__ import annotations

from embed_toolkit.audit.results import ResultStatus
from embed_toolkit.core.primitives import Laterality, ViewPosition
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.rois import RegionOfInterest
from embed_toolkit.workflows.patch_extraction import PatchExtractor, extract_patch


class SliceableArray:
    """Small numpy-like array double that supports two-axis slicing."""

    def __init__(self, data: list[list[int]]) -> None:
        self._data = data
        self.shape = (len(data), len(data[0]))

    def __getitem__(self, key: object) -> list[list[int]]:
        row_slice, column_slice = key
        return [row[column_slice] for row in self._data[row_slice]]


def test_extracts_in_bounds_patch_from_nested_sequences() -> None:
    image = [
        [0, 1, 2, 3],
        [10, 11, 12, 13],
        [20, 21, 22, 23],
        [30, 31, 32, 33],
    ]
    roi = RegionOfInterest((1, 1, 3, 4), roi_id="roi-1", image_id="img-1")

    result = extract_patch(image, roi)

    assert result.status is ResultStatus.SUCCESS
    assert result.image_id == "img-1"
    assert result.roi_id == "roi-1"
    assert result.bbox == [1.0, 1.0, 3.0, 4.0]
    assert result.shape == [2, 3]
    assert result.patch_payload["data"] == [[11, 12, 13], [21, 22, 23]]
    assert result.patch_payload["padding"] == {
        "top": 0,
        "left": 0,
        "bottom": 0,
        "right": 0,
    }
    assert result.warnings == []


def test_extracts_out_of_bounds_patch_with_constant_padding() -> None:
    image = [
        [0, 1, 2],
        [10, 11, 12],
        [20, 21, 22],
    ]
    roi = RegionOfInterest((-1, 1, 2, 4), roi_id="roi-pad", image_id="img-1")

    result = PatchExtractor(pad=True, pad_value=-1).extract(image, roi)

    assert result.status is ResultStatus.PARTIAL
    assert result.bbox == [-1.0, 1.0, 2.0, 4.0]
    assert result.shape == [3, 3]
    assert result.patch_payload["data"] == [
        [-1, -1, -1],
        [1, 2, -1],
        [11, 12, -1],
    ]
    assert result.patch_payload["padding"] == {
        "top": 1,
        "left": 0,
        "bottom": 0,
        "right": 1,
    }
    assert result.patch_payload["requested_bbox"] == [-1, 1, 2, 4]
    assert result.patch_payload["clipped_bbox"] == [0, 1, 2, 3]
    assert result.warnings[0].code == "patch_padded"

    fully_outside = PatchExtractor(pad=True, pad_value=-1).extract(
        image,
        RegionOfInterest((5, 5, 7, 7), roi_id="roi-outside", image_id="img-1"),
    )
    assert fully_outside.shape == [2, 2]
    assert fully_outside.patch_payload["data"] == [[-1, -1], [-1, -1]]
    assert fully_outside.patch_payload["padding"] == {
        "top": 0,
        "left": 0,
        "bottom": 2,
        "right": 2,
    }


def test_clips_out_of_bounds_patch_when_padding_is_disabled() -> None:
    image = [
        [0, 1, 2],
        [10, 11, 12],
        [20, 21, 22],
    ]
    roi = RegionOfInterest((-2, -1, 2, 2), roi_id="roi-clip", image_id="img-1")

    result = extract_patch(image, roi, pad=False)

    assert result.status is ResultStatus.PARTIAL
    assert result.bbox == [0.0, 0.0, 2.0, 2.0]
    assert result.shape == [2, 2]
    assert result.patch_payload["data"] == [[0, 1], [10, 11]]
    assert result.patch_payload["padding"] == {
        "top": 0,
        "left": 0,
        "bottom": 0,
        "right": 0,
    }
    assert result.patch_payload["requested_bbox"] == [-2, -1, 2, 2]
    assert result.patch_payload["clipped_bbox"] == [0, 0, 2, 2]
    assert result.warnings[0].code == "patch_clipped"


def test_preserves_metadata_and_supports_numpy_like_slicing() -> None:
    image_data = SliceableArray(
        [
            [0, 1, 2, 3],
            [10, 11, 12, 13],
            [20, 21, 22, 23],
        ]
    )
    image = MammogramImage(
        image_id="img-meta",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        height=3,
        width=4,
        coordinate_frame_id="aligned-left-cc",
    )
    roi = RegionOfInterest(
        (0, 1, 2, 3),
        roi_id="roi-meta",
        image_id="img-meta",
        frame_index=7,
        source="embed",
        confidence=0.91,
    )

    result = extract_patch(
        image_data,
        roi,
        image=image,
        patch_id="patch-meta",
        metadata={"reader": "unit-test"},
    )

    assert result.image_id == "img-meta"
    assert result.patch_id == "patch-meta"
    assert result.patch_payload["data"] == [[1, 2], [11, 12]]
    assert result.metadata == {
        "roi_source": "embed",
        "roi_confidence": 0.91,
        "roi_frame_index": 7,
        "coordinate_frame_id": "aligned-left-cc",
        "reader": "unit-test",
    }
    assert result.evidence[0].payload["image_shape"] == [3, 4]
