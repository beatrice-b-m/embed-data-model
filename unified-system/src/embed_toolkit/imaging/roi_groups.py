"""Lesion-level groups of related image-local ROI observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Tuple

from embed_toolkit.core.primitives import Laterality
from embed_toolkit.imaging.roi_provenance import RoiLocator
from embed_toolkit.imaging.rois import RegionOfInterest


@dataclass(frozen=True)
class RoiGroup:
    """An explicit assertion relating scoped ROI observations."""

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
        if any(not isinstance(roi, RegionOfInterest) for roi in self.rois):
            raise TypeError("rois must contain only RegionOfInterest values")
        if any(not isinstance(roi.locator, RoiLocator) for roi in self.rois):
            raise TypeError("Grouped ROIs require RoiLocator values")
        if len(set(self.roi_locators)) != len(self.roi_locators):
            raise ValueError("ROI group cannot contain duplicate ROI locators")
        if not isinstance(self.grouping_basis, str) or not self.grouping_basis.strip():
            raise ValueError("ROI group grouping_basis is required")

    @property
    def roi_locators(self) -> Tuple[RoiLocator, ...]:
        return tuple(roi.locator for roi in self.rois)

    @property
    def image_ids(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(roi.image_id for roi in self.rois))

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
        encoded = json.dumps(roi.locator.to_dict(), sort_keys=True).encode("utf-8")
        assertion_id = hashlib.sha256(encoded).hexdigest()[:20]
        return cls(
            group_id=f"singleton:{assertion_id}",
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
            "roi_locators": [locator.to_dict() for locator in self.roi_locators],
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
    """Wrap ungrouped ROIs as explicit singleton assertions."""

    return tuple(
        RoiGroup.singleton(
            roi,
            accession_number=accession_number,
            laterality=laterality,
        )
        for roi in rois
    )
