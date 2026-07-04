"""Mammography image domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional, Tuple

from embed_toolkit.core.primitives import (
    ImageModality,
    Laterality,
    PatientOrientation,
    ViewPosition,
)
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark


@dataclass
class MammogramImage:
    """Image metadata and image-owned landmarks for one mammography object."""

    image_id: str
    laterality: Laterality
    view_position: ViewPosition
    modality: ImageModality = ImageModality.UNKNOWN
    height: Optional[int] = None
    width: Optional[int] = None
    frame_count: Optional[int] = None
    accession_number: Optional[str] = None
    study_instance_uid: Optional[str] = None
    series_instance_uid: Optional[str] = None
    sop_instance_uid: Optional[str] = None
    patient_orientation: Optional[PatientOrientation] = None
    coordinate_frame_id: Optional[str] = None
    landmarks: Tuple[ImageLandmark, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.laterality = Laterality.coerce(self.laterality)
        self.view_position = ViewPosition.coerce(self.view_position)
        self.modality = ImageModality.coerce(self.modality)
        if self.patient_orientation is not None:
            self.patient_orientation = PatientOrientation.coerce(
                self.patient_orientation
            )
        if self.height is not None and self.height <= 0:
            raise ValueError("Image height must be positive")
        if self.width is not None and self.width <= 0:
            raise ValueError("Image width must be positive")
        if self.frame_count is not None and self.frame_count <= 0:
            raise ValueError("Frame count must be positive")
        self.landmarks = tuple(
            landmark
            if landmark.image_id == self.image_id
            else landmark.owned_by(self.image_id)
            for landmark in self.landmarks
        )

    @property
    def identity(self) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        """Return stable image identity fields from most local to study scope."""

        return (
            self.image_id,
            self.sop_instance_uid,
            self.series_instance_uid,
            self.study_instance_uid,
        )

    @property
    def image_shape(self) -> Optional[Tuple[int, int]]:
        if self.height is None or self.width is None:
            return None
        return self.height, self.width

    @property
    def is_dbt(self) -> bool:
        return self.modality is ImageModality.DBT

    def add_landmark(self, landmark: ImageLandmark) -> ImageLandmark:
        """Attach a landmark to this image and return the owned copy."""

        owned = landmark.owned_by(self.image_id)
        self.landmarks = (*self.landmarks, owned)
        return owned

    def with_landmark(self, landmark: ImageLandmark) -> "MammogramImage":
        """Return a copy with an additional image-owned landmark."""

        owned = landmark.owned_by(self.image_id)
        return replace(self, landmarks=(*self.landmarks, owned))

    def breast_geometry(
        self,
        *,
        nipple: Optional[ImageLandmark] = None,
        posterior_nipple_line: Optional[Tuple[ImageLandmark, ImageLandmark]] = None,
        posterior_boundary: Optional[ImageLandmark] = None,
    ) -> BreastGeometry:
        """Build a coordinate-frame fact object for this image."""

        return BreastGeometry(
            image_id=self.image_id,
            laterality=self.laterality,
            view_position=self.view_position,
            image_shape=self.image_shape,
            coordinate_frame_id=self.coordinate_frame_id,
            nipple=nipple.owned_by(self.image_id) if nipple is not None else None,
            posterior_nipple_line=(
                posterior_nipple_line[0].owned_by(self.image_id),
                posterior_nipple_line[1].owned_by(self.image_id),
            )
            if posterior_nipple_line is not None
            else None,
            posterior_boundary=posterior_boundary.owned_by(self.image_id)
            if posterior_boundary is not None
            else None,
        )
