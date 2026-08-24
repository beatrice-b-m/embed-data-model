"""Lesion-level groups of related image-local ROI observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Tuple

from embed_toolkit.core.primitives import Laterality
from embed_toolkit.imaging.rois import RegionOfInterest


@dataclass(frozen=True)
class RoiGroup:
    """Related raw boxes that may depict one lesion across views or frames.

    Group membership is an explicit evidence assertion; this object does not
    infer that boxes belong together merely because their geometry overlaps.
    """

    group_id: str
    accession_number: str
    laterality: Laterality
    rois: Tuple[RegionOfInterest, ...]
    grouping_basis: str = "explicit"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "laterality", Laterality.coerce(self.laterality))
        object.__setattr__(self, "rois", tuple(self.rois))
        if not self.group_id:
            raise ValueError("ROI group_id is required")
        if not self.accession_number:
            raise ValueError("ROI group accession_number is required")
        if not self.laterality.is_unilateral:
            raise ValueError("ROI group laterality must be LEFT or RIGHT")
        if not self.rois:
            raise ValueError("ROI group must contain at least one ROI")
        if any(roi.roi_id is None for roi in self.rois):
            raise ValueError("Grouped ROIs require stable roi_id values")
        if len(set(self.roi_ids)) != len(self.roi_ids):
            raise ValueError("ROI group cannot contain duplicate roi_id values")

    @property
    def roi_ids(self) -> Tuple[str, ...]:
        return tuple(roi.roi_id for roi in self.rois if roi.roi_id is not None)

    @property
    def image_ids(self) -> Tuple[str, ...]:
        return tuple(
            dict.fromkeys(roi.image_id for roi in self.rois if roi.image_id is not None)
        )

    @property
    def frame_indices(self) -> Tuple[int, ...]:
        return tuple(dict.fromkeys(frame for roi in self.rois for frame in roi.frame_indices))

    @classmethod
    def singleton(
        cls,
        roi: RegionOfInterest,
        *,
        accession_number: str,
        laterality: Laterality,
    ) -> "RoiGroup":
        if roi.roi_id is None:
            raise ValueError("Singleton ROI groups require a stable roi_id")
        return cls(
            group_id=f"group:{roi.roi_id}",
            accession_number=accession_number,
            laterality=laterality,
            rois=(roi,),
            grouping_basis="singleton",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "accession_number": self.accession_number,
            "laterality": self.laterality.value,
            "roi_ids": list(self.roi_ids),
            "image_ids": list(self.image_ids),
            "frame_indices": list(self.frame_indices),
            "grouping_basis": self.grouping_basis,
            "metadata": dict(self.metadata),
        }


def singleton_roi_groups(
    rois: Iterable[RegionOfInterest],
    *,
    accession_number: str,
    laterality: Laterality,
) -> Tuple[RoiGroup, ...]:
    """Wrap ungrouped ROIs without inventing cross-view relationships."""

    return tuple(
        RoiGroup.singleton(
            roi,
            accession_number=accession_number,
            laterality=laterality,
        )
        for roi in rois
    )
