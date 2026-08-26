"""Acceptance tests for the repository-only patch-extraction recipe."""

from __future__ import annotations

from dataclasses import replace

import pytest

from examples.patch_extraction import PatchExtractor, ResultStatus, extract_patch
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocator,
    RoiSourceCount,
    RoiSourceCountBasis,
    RoiSourceProvenance,
)
from embed_toolkit.imaging.rois import Box, RegionOfInterest


def roi(
    coordinates: tuple[float, float, float, float],
    value: str,
    image_id: str = "img-1",
    *,
    image_source: SourceLocator | None = None,
    frame_indices: tuple[int, ...] = (),
    annotation_source: str | None = None,
    confidence: float | None = None,
) -> RegionOfInterest:
    source = image_source or SourceLocator(
        scope="patch-extraction-tests",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="images",
        source_key=image_id,
    )
    locator = RoiLocator.from_source(image_locator=source, source_value=value)
    modality = ImageModality.DBT if frame_indices else ImageModality.FFDM
    return RegionOfInterest(
        coordinates,
        locator=locator,
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
    )


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
    observed = roi((1, 1, 3, 4), "roi-1")

    result = extract_patch(image, observed)

    assert result.status is ResultStatus.SUCCESS
    assert result.image_id == "img-1"
    assert result.roi_locator == observed.locator
    assert result.bbox == (1.0, 1.0, 3.0, 4.0)
    assert result.shape == (2, 3)
    assert result.patch_payload["data"] == ((11, 12, 13), (21, 22, 23))
    assert result.patch_payload["padding"] == {
        "top": 0,
        "left": 0,
        "bottom": 0,
        "right": 0,
    }
    assert result.warnings == ()


def test_extracts_inclusive_embed_box_at_image_boundary() -> None:
    image = [[row * 100 + column for column in range(260)] for row in range(160)]
    base = roi((0, 0, 1, 1), "boundary")
    observed = RegionOfInterest.from_embed_coordinates(
        (100, 200, 150, 250),
        locator=base.locator,
        image_id=base.image_id,
        source_provenance=base.source_provenance,
        sources=base.sources,
    )

    result = extract_patch(image, observed)

    assert result.shape == (51, 51)
    assert result.patch_payload["data"][0][0] == 10200
    assert result.patch_payload["data"][-1][-1] == 15250

    boundary = RegionOfInterest.from_embed_coordinates(
        (159, 259, 159, 259),
        locator=RoiLocator.from_source(
            image_locator=base.locator.image_locator,
            source_value="last-pixel",
        ),
        image_id=base.image_id,
        source_provenance=base.source_provenance,
        sources=base.sources,
    )
    boundary_result = extract_patch(image, boundary)
    assert boundary_result.shape == (1, 1)
    assert boundary_result.status is ResultStatus.SUCCESS


def test_extracts_out_of_bounds_patch_with_constant_padding() -> None:
    image = [
        [0, 1, 2],
        [10, 11, 12],
        [20, 21, 22],
    ]
    observed = roi((-1, 1, 2, 4), "roi-pad")

    result = PatchExtractor(pad=True, pad_value=-1).extract(image, observed)

    assert result.status is ResultStatus.PARTIAL
    assert result.bbox == (-1.0, 1.0, 2.0, 4.0)
    assert result.shape == (3, 3)
    assert result.patch_payload["data"] == (
        (-1, -1, -1),
        (1, 2, -1),
        (11, 12, -1),
    )
    assert result.patch_payload["padding"] == {
        "top": 1,
        "left": 0,
        "bottom": 0,
        "right": 1,
    }
    assert result.patch_payload["requested_bbox"] == (-1, 1, 2, 4)
    assert result.patch_payload["clipped_bbox"] == (0, 1, 2, 3)
    assert result.warnings[0].code == "patch_padded"

    fully_outside = PatchExtractor(pad=True, pad_value=-1).extract(
        image,
        roi((5, 5, 7, 7), "roi-outside"),
    )
    assert fully_outside.shape == (2, 2)
    assert fully_outside.patch_payload["data"] == ((-1, -1), (-1, -1))
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
    observed = roi((-2, -1, 2, 2), "roi-clip")

    result = extract_patch(image, observed, pad=False)

    assert result.status is ResultStatus.PARTIAL
    assert result.bbox == (0.0, 0.0, 2.0, 2.0)
    assert result.shape == (2, 2)
    assert result.patch_payload["data"] == ((0, 1), (10, 11))
    assert result.patch_payload["padding"] == {
        "top": 0,
        "left": 0,
        "bottom": 0,
        "right": 0,
    }
    assert result.patch_payload["requested_bbox"] == (-2, -1, 2, 2)
    assert result.patch_payload["clipped_bbox"] == (0, 0, 2, 2)
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
        sources=[
            SourceLocator(
                scope="patch-extraction-tests",
                scope_kind=SourceScopeKind.MATERIALIZATION,
                source_profile="test",
                source_table="images",
                source_key="img-meta",
            )
        ],
        height=3,
        width=4,
        coordinate_frame_id="aligned-left-cc",
    )
    observed = roi(
        (0, 1, 2, 3),
        "roi-meta",
        "img-meta",
        image_source=image.canonical_source,
        frame_indices=(7,),
        annotation_source="embed",
        confidence=0.91,
    )

    result = extract_patch(
        image_data,
        observed,
        image=image,
        patch_id="patch-meta",
        metadata={"reader": "unit-test"},
    )

    assert result.image_id == "img-meta"
    assert result.patch_id == "patch-meta"
    assert result.patch_payload["data"] == ((1, 2), (11, 12))
    assert result.metadata["annotation_source"] == "embed"
    assert result.metadata["confidence"] == 0.91
    assert result.metadata["frame_indices"] == (7,)
    assert (
        result.metadata["source_provenance"]["modality"]
        == observed.source_provenance.modality.value
    )
    assert result.metadata["source_references"][0]["source_key"] == "img-meta"
    assert result.metadata["coordinate_frame_id"] == "aligned-left-cc"
    assert result.metadata["reader"] == "unit-test"
    assert result.evidence[0].payload["image_shape"] == (3, 4)


def test_patch_identity_and_governed_metadata_are_locator_derived() -> None:
    observed = roi(
        (0, 0, 1, 1),
        "governed-metadata",
        annotation_source="embed",
    )

    first = extract_patch(
        [[1]],
        observed,
        metadata={
            "annotation_source": "contradictory",
            "frame_indices": [999],
            "custom": "retained",
        },
    )
    second = extract_patch([[1]], observed)

    assert first.patch_id == second.patch_id
    assert first.patch_id.startswith("patch:")
    assert first.metadata["annotation_source"] == "embed"
    assert first.metadata["frame_indices"] == ()
    assert first.metadata["custom"] == "retained"


def test_patch_accepts_manual_roi_identity() -> None:
    observed = RegionOfInterest(
        Box(0, 0, 1, 1),
        image_id="manual-image",
        roi_key="manual-roi",
    )

    result = extract_patch([[1]], observed)

    assert result.roi_locator is None
    assert result.roi_key == "manual-roi"
    assert result.patch_id.startswith("patch:")


def test_patch_accepts_noncanonical_source_ledger_locator() -> None:
    image = MammogramImage(
        image_id="multi-source",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        sources=[
            SourceLocator(
                scope="patch-extraction-tests",
                scope_kind=SourceScopeKind.MATERIALIZATION,
                source_profile="test",
                source_table="images",
                source_key="row-1",
            ),
            SourceLocator(
                scope="patch-extraction-tests",
                scope_kind=SourceScopeKind.MATERIALIZATION,
                source_profile="test",
                source_table="images",
                source_key="row-2",
            ),
        ],
    )
    observed = roi(
        (0, 0, 1, 1),
        "row-2-roi",
        image_id=image.image_id,
        image_source=image.sources[1],
    )

    result = extract_patch([[1]], observed, image=image)

    assert result.roi_locator.image_locator == image.sources[1]


def test_patch_rejects_roi_source_outside_image_ledger() -> None:
    image = MammogramImage(
        image_id="scoped",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
        sources=[
            SourceLocator(
                scope="patch-extraction-tests",
                scope_kind=SourceScopeKind.MATERIALIZATION,
                source_profile="test",
                source_table="images",
                source_key="image-row",
            )
        ],
    )
    outsider = SourceLocator(
        scope="patch-extraction-tests",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="images",
        source_key="outsider",
    )
    observed = roi(
        (0, 0, 1, 1),
        "outsider-roi",
        image_id=image.image_id,
        image_source=image.canonical_source,
    )
    observed = replace(observed, sources=(*observed.sources, outsider))

    with pytest.raises(ValueError, match="ROI sources"):
        extract_patch([[1]], observed, image=image)
