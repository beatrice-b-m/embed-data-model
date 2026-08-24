from __future__ import annotations

import pytest

from embed_toolkit.core.primitives import Laterality
from embed_toolkit.imaging.roi_groups import RoiGroup, singleton_roi_groups
from embed_toolkit.imaging.rois import RegionOfInterest


def test_roi_group_represents_cross_view_and_multiframe_lesion_evidence() -> None:
    cc = RegionOfInterest(
        (1, 2, 4, 5),
        roi_id="roi-cc",
        image_id="img-cc",
        frame_indices=(12, 13),
    )
    mlo = RegionOfInterest(
        (10, 20, 30, 40),
        roi_id="roi-mlo",
        image_id="img-mlo",
        frame_indices=(13, 20),
    )

    group = RoiGroup(
        group_id="lesion-1",
        accession_number="ACC-1",
        laterality="L",
        rois=(cc, mlo),
        grouping_basis="reviewed_cross_view",
    )

    assert group.roi_ids == ("roi-cc", "roi-mlo")
    assert group.image_ids == ("img-cc", "img-mlo")
    assert group.frame_indices == (12, 13, 20)
    assert group.to_dict()["laterality"] == "L"


def test_singleton_groups_preserve_raw_roi_identity_without_inference() -> None:
    rois = (
        RegionOfInterest((0, 0, 1, 1), roi_id="a"),
        RegionOfInterest((1, 1, 2, 2), roi_id="b"),
    )

    groups = singleton_roi_groups(
        rois,
        accession_number="ACC-1",
        laterality=Laterality.RIGHT,
    )

    assert [group.group_id for group in groups] == ["group:a", "group:b"]
    assert [group.roi_ids for group in groups] == [("a",), ("b",)]
    assert all(group.grouping_basis == "singleton" for group in groups)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"rois": ()}, "at least one"),
        ({"laterality": Laterality.BILATERAL}, "LEFT or RIGHT"),
        (
            {
                "rois": (
                    RegionOfInterest((0, 0, 1, 1), roi_id="same"),
                    RegionOfInterest((1, 1, 2, 2), roi_id="same"),
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
        "rois": (RegionOfInterest((0, 0, 1, 1), roi_id="roi-1"),),
    }

    with pytest.raises(ValueError, match=message):
        RoiGroup(**{**defaults, **kwargs})
