from __future__ import annotations

import json
from typing import Tuple

import pytest

from embed_toolkit.core.primitives import ImageModality
from embed_toolkit.core.provenance import (
    SourceLocator,
    SourceScopeKind,
)
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocator,
    RoiLocatorKind,
    RoiSourceCount,
    RoiSourceCountBasis,
    RoiSourceProvenance,
)


def image_locator(scope: str = "embed-v1c-2026-08") -> SourceLocator:
    return SourceLocator(
        scope=scope,
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="internal-v2",
        source_table="images",
        source_key="SOP-123",
    )


def test_synthetic_roi_locator_is_structured_and_scope_sensitive() -> None:
    first = RoiLocator.synthetic(
        image_locator=image_locator("materialization-a"),
        source_ordinal=2,
    )
    second = RoiLocator.synthetic(
        image_locator=image_locator("materialization-b"),
        source_ordinal=2,
    )

    assert first.kind is RoiLocatorKind.SYNTHETIC
    assert first != second
    assert first.to_dict() == {
        "kind": "synthetic",
        "image_locator": {
            "scope": "materialization-a",
            "scope_kind": "materialization",
            "source_profile": "internal-v2",
            "source_table": "images",
            "row_ordinal": None,
            "source_key": "SOP-123",
        },
        "source_value": None,
        "source_ordinal": 2,
    }


def test_source_supplied_roi_value_is_scoped_to_its_image_occurrence() -> None:
    first = RoiLocator.from_source(
        image_locator=image_locator("dataset-a"),
        source_value="ROI-7",
    )
    second = RoiLocator.from_source(
        image_locator=image_locator("dataset-b"),
        source_value="ROI-7",
    )

    assert first.kind is RoiLocatorKind.SOURCE_SUPPLIED
    assert first.source_value == "ROI-7"
    assert first != second


def test_roi_locator_rejects_a_bare_image_identity_string() -> None:
    with pytest.raises(ValueError, match="scoped SourceLocator"):
        RoiLocator.synthetic(
            image_locator="SOP-123",  # type: ignore[arg-type]
            source_ordinal=0,
        )


@pytest.mark.parametrize(
    "locator",
    [
        lambda: RoiLocator(
            RoiLocatorKind.SOURCE_SUPPLIED,
            image_locator(),
        ),
        lambda: RoiLocator(
            RoiLocatorKind.SOURCE_SUPPLIED,
            image_locator(),
            source_value="ROI-1",
            source_ordinal=0,
        ),
        lambda: RoiLocator(
            RoiLocatorKind.SYNTHETIC,
            image_locator(),
            source_value="invented-id",
            source_ordinal=0,
        ),
        lambda: RoiLocator(
            RoiLocatorKind.SYNTHETIC,
            image_locator(),
        ),
    ],
)
def test_roi_locator_kinds_reject_ambiguous_identity_fields(locator: object) -> None:
    with pytest.raises(ValueError):
        locator()  # type: ignore[operator]


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_roi_source_count_must_be_a_positive_integer(value: object) -> None:
    with pytest.raises(ValueError, match="source count"):
        RoiSourceCount(
            value=value,  # type: ignore[arg-type]
            basis=RoiSourceCountBasis.ALIGNED_COORDINATE_COLLECTION,
        )


@pytest.mark.parametrize("modality", [ImageModality.FFDM, ImageModality.S2D])
def test_2d_roi_provenance_has_no_depth_or_frame_semantics(
    modality: ImageModality,
) -> None:
    provenance = RoiSourceProvenance(
        modality=modality,
        source_count=RoiSourceCount(
            1,
            RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE,
        ),
        depth_frame_provenance=RoiDepthFrameProvenance.NOT_APPLICABLE_2D,
    )

    assert provenance.frame_indices == ()
    assert provenance.to_dict()["depth_frame_provenance"] == "not_applicable_2d"


@pytest.mark.parametrize(
    ("depth_provenance", "frame_indices"),
    [
        (RoiDepthFrameProvenance.SOURCE_SUPPLIED, (3, 4)),
        (RoiDepthFrameProvenance.DERIVED, (7,)),
        (RoiDepthFrameProvenance.UNAVAILABLE_DBT, ()),
    ],
)
def test_dbt_roi_provenance_preserves_known_or_unavailable_depth(
    depth_provenance: RoiDepthFrameProvenance,
    frame_indices: Tuple[int, ...],
) -> None:
    provenance = RoiSourceProvenance(
        modality=ImageModality.DBT,
        source_count=RoiSourceCount(
            2,
            RoiSourceCountBasis.ALIGNED_COORDINATE_COLLECTION,
        ),
        depth_frame_provenance=depth_provenance,
        frame_indices=frame_indices,
        derivation_method=(
            "projected_from_annotation_depth"
            if depth_provenance is RoiDepthFrameProvenance.DERIVED
            else None
        ),
    )

    assert provenance.frame_indices == frame_indices


@pytest.mark.parametrize(
    ("modality", "depth_provenance", "frame_indices"),
    [
        (
            ImageModality.FFDM,
            RoiDepthFrameProvenance.SOURCE_SUPPLIED,
            (1,),
        ),
        (
            ImageModality.S2D,
            RoiDepthFrameProvenance.UNAVAILABLE_DBT,
            (),
        ),
        (
            ImageModality.DBT,
            RoiDepthFrameProvenance.NOT_APPLICABLE_2D,
            (),
        ),
        (
            ImageModality.DBT,
            RoiDepthFrameProvenance.UNAVAILABLE_DBT,
            (2,),
        ),
        (
            ImageModality.DBT,
            RoiDepthFrameProvenance.SOURCE_SUPPLIED,
            (),
        ),
    ],
)
def test_roi_source_provenance_rejects_invalid_2d_dbt_combinations(
    modality: ImageModality,
    depth_provenance: RoiDepthFrameProvenance,
    frame_indices: Tuple[int, ...],
) -> None:
    with pytest.raises(ValueError):
        RoiSourceProvenance(
            modality=modality,
            source_count=RoiSourceCount(
                1,
                RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE,
            ),
            depth_frame_provenance=depth_provenance,
            frame_indices=frame_indices,
        )


def test_synthetic_ordinal_is_validated_against_source_count() -> None:
    provenance = RoiSourceProvenance(
        modality=ImageModality.DBT,
        source_count=RoiSourceCount(
            2,
            RoiSourceCountBasis.ALIGNED_COORDINATE_COLLECTION,
        ),
        depth_frame_provenance=RoiDepthFrameProvenance.UNAVAILABLE_DBT,
    )

    provenance.validate_locator(
        RoiLocator.synthetic(image_locator=image_locator(), source_ordinal=1)
    )
    with pytest.raises(ValueError, match="exceeds source count"):
        provenance.validate_locator(
            RoiLocator.synthetic(image_locator=image_locator(), source_ordinal=2)
        )


def test_derived_dbt_frames_require_named_derivation_provenance() -> None:
    with pytest.raises(ValueError, match="derivation_method"):
        RoiSourceProvenance(
            modality=ImageModality.DBT,
            source_count=RoiSourceCount(
                1,
                RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE,
            ),
            depth_frame_provenance=RoiDepthFrameProvenance.DERIVED,
            frame_indices=(4,),
        )


def test_unknown_modality_requires_unresolved_uninterpreted_provenance() -> None:
    provenance = RoiSourceProvenance(
        modality=ImageModality.UNKNOWN,
        source_count=RoiSourceCount(
            1,
            RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE,
        ),
        depth_frame_provenance=RoiDepthFrameProvenance.UNRESOLVED_MODALITY,
    )

    assert provenance.frame_indices == ()
    with pytest.raises(ValueError, match="cannot interpret frame indices"):
        RoiSourceProvenance(
            modality=ImageModality.UNKNOWN,
            source_count=provenance.source_count,
            depth_frame_provenance=RoiDepthFrameProvenance.UNRESOLVED_MODALITY,
            frame_indices=(2,),
        )


def test_roi_provenance_serialization_is_json_ready() -> None:
    provenance = RoiSourceProvenance(
        modality=ImageModality.DBT,
        source_count=RoiSourceCount(
            3,
            RoiSourceCountBasis.SOURCE_DECLARED,
        ),
        depth_frame_provenance=RoiDepthFrameProvenance.SOURCE_SUPPLIED,
        frame_indices=(1, 2),
    )

    serialized = provenance.to_dict()
    assert serialized == {
        "modality": "3D",
        "source_count": {"value": 3, "basis": "source_declared"},
        "depth_frame_provenance": "source_supplied",
        "frame_indices": [1, 2],
        "derivation_method": None,
    }
    assert json.loads(json.dumps(serialized)) == serialized
