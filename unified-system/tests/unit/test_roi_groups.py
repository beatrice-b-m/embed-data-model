from __future__ import annotations

import json

import pytest

from embed_toolkit.core.primitives import ImageModality, Laterality
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.roi_groups import RoiGroup, singleton_roi_groups
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocator,
    RoiSourceCount,
    RoiSourceCountBasis,
    RoiSourceProvenance,
)
from embed_toolkit.imaging.rois import RegionOfInterest


def roi(
    source_value: str,
    image_id: str,
    coordinates: tuple[float, float, float, float],
    frame_indices: tuple[int, ...] = (),
) -> RegionOfInterest:
    image_source = SourceLocator(
        scope="roi-group-tests",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="images",
        source_key=image_id,
    )
    modality = ImageModality.DBT if frame_indices else ImageModality.FFDM
    return RegionOfInterest(
        coordinates,
        locator=RoiLocator.from_source(
            image_locator=image_source,
            source_value=source_value,
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
        sources=(image_source,),
    )


def test_roi_group_represents_cross_view_and_multiframe_lesion_evidence() -> None:
    cc = roi("roi-cc", "img-cc", (1, 2, 4, 5), (12, 13))
    mlo = roi("roi-mlo", "img-mlo", (10, 20, 30, 40), (13, 20))

    group = RoiGroup(
        group_id="lesion-1",
        accession_number="ACC-1",
        laterality="L",
        rois=(cc, mlo),
        grouping_basis="reviewed_cross_view",
    )

    assert group.roi_locators == (cc.locator, mlo.locator)
    assert group.image_ids == ("img-cc", "img-mlo")
    assert group.frame_indices == (12, 13, 20)
    assert group.to_dict()["roi_locators"] == [
        cc.locator.to_dict(),
        mlo.locator.to_dict(),
    ]
    json.dumps(group.to_dict())


def test_singleton_groups_use_assertion_ids_not_bare_roi_values() -> None:
    rois = (
        roi("a", "image-a", (0, 0, 1, 1)),
        roi("b", "image-b", (1, 1, 2, 2)),
    )

    groups = singleton_roi_groups(
        rois,
        accession_number="ACC-1",
        laterality=Laterality.RIGHT,
    )

    assert all(group.group_id.startswith("singleton:") for group in groups)
    assert [group.group_id for group in groups] != ["singleton:a", "singleton:b"]
    assert [group.roi_locators for group in groups] == [
        (rois[0].locator,),
        (rois[1].locator,),
    ]
    assert all(group.grouping_basis == "singleton" for group in groups)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"rois": ()}, "at least one"),
        ({"laterality": Laterality.BILATERAL}, "LEFT or RIGHT"),
        (
            {
                "rois": (
                    roi("same", "same-image", (0, 0, 1, 1)),
                    roi("same", "same-image", (1, 1, 2, 2)),
                )
            },
            "duplicate",
        ),
    ],
)
def test_roi_group_rejects_ambiguous_scope(kwargs: dict, message: str) -> None:
    defaults = {
        "group_id": "group-1",
        "accession_number": "ACC-1",
        "laterality": Laterality.LEFT,
        "rois": (roi("roi-1", "image-1", (0, 0, 1, 1)),),
    }

    with pytest.raises(ValueError, match=message):
        RoiGroup(**{**defaults, **kwargs})


def test_roi_group_rejects_non_roi_members_before_locator_access() -> None:
    class LocatorImpostor:
        locator = roi("impostor", "image-1", (0, 0, 1, 1)).locator

    with pytest.raises(TypeError, match="RegionOfInterest"):
        RoiGroup(
            group_id="group-1",
            accession_number="ACC-1",
            laterality=Laterality.LEFT,
            rois=(LocatorImpostor(),),  # type: ignore[arg-type]
        )
