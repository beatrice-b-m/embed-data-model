"""Mammography image domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from embed_toolkit.core.provenance import SourceLocator
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
    sources: List[SourceLocator]
    modality: ImageModality = ImageModality.UNKNOWN
    height: Optional[int] = None
    width: Optional[int] = None
    frame_count: Optional[int] = None
    accession_number: Optional[str] = None
    patient_id: Optional[str] = None
    study_instance_uid: Optional[str] = None
    series_instance_uid: Optional[str] = None
    sop_instance_uid: Optional[str] = None
    patient_orientation: Optional[PatientOrientation] = None
    coordinate_frame_id: Optional[str] = None
    landmarks: Tuple[ImageLandmark, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.image_id, str) or not self.image_id.strip():
            raise ValueError("image_id must be a non-empty string")
        self.sources = list(self.sources)
        if not self.sources:
            raise ValueError("sources must contain at least one SourceLocator")
        if any(not isinstance(source, SourceLocator) for source in self.sources):
            raise TypeError("sources must contain only SourceLocator values")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("sources must contain unique SourceLocator values")
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
        if (
            self.frame_count is not None
            and self.modality is not ImageModality.DBT
        ):
            raise ValueError("Frame count is only valid for DBT images")
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
    def canonical_source(self) -> SourceLocator:
        """Return the deterministic source locator governing image scope."""

        return self.sources[0]

    def add_source(self, source: SourceLocator) -> SourceLocator:
        if not isinstance(source, SourceLocator):
            raise TypeError("source must be a SourceLocator")
        if source not in self.sources:
            self.sources.append(source)
        return source

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
        )

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-ready non-recursive image representation."""

        return {
            "image_id": self.image_id,
            "sources": [source.to_dict() for source in self.sources],
            "patient_id": self.patient_id,
            "accession_number": self.accession_number,
            "laterality": self.laterality.value,
            "view_position": self.view_position.value,
            "modality": self.modality.value,
            "height": self.height,
            "width": self.width,
            "frame_count": self.frame_count,
            "study_instance_uid": self.study_instance_uid,
            "series_instance_uid": self.series_instance_uid,
            "sop_instance_uid": self.sop_instance_uid,
            "patient_orientation": (
                list(self.patient_orientation.as_tuple())
                if self.patient_orientation is not None
                else None
            ),
            "coordinate_frame_id": self.coordinate_frame_id,
            "landmarks": [
                {
                    "y": landmark.y,
                    "x": landmark.x,
                    "landmark_type": landmark.landmark_type.value,
                    "image_id": landmark.image_id,
                    "source": landmark.source,
                    "confidence": landmark.confidence,
                    "provenance": landmark.provenance,
                }
                for landmark in self.landmarks
            ],
        }
