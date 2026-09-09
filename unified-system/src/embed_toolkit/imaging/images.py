"""Mutable mammography image domain objects."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, Mapping, Optional, Set, Tuple, TYPE_CHECKING

from embed_toolkit.core.entity import MutableEntity
from embed_toolkit.core.primitives import (
    ImageModality,
    Laterality,
    PatientOrientation,
    ViewPosition,
)
from embed_toolkit.imaging.landmarks import BreastGeometry, ImageLandmark

if TYPE_CHECKING:
    from embed_toolkit.imaging.rois import RegionOfInterest


class MammogramImage(MutableEntity):
    """Mutable metadata for one mammography image.

    ``image_id`` is the toolkit identity.  Original source identity and
    source locations are optional aliases, and derivative identity is explicit
    through ``derived_from``.  No source path parsing occurs in this class.
    """

    __key_fields__ = ("image_id",)

    def __init__(
        self,
        image_id: str,
        laterality: Laterality = Laterality.UNKNOWN,
        view_position: ViewPosition = ViewPosition.UNKNOWN,
        source_paths: Optional[Iterable[str]] = None,
        *,
        modality: ImageModality = ImageModality.UNKNOWN,
        source_sop_instance_uid: Optional[str] = None,
        derived_from: Optional[Any] = None,
        source_modality: Optional[str] = None,
        derived_image_type: Optional[str] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
        frame_count: Optional[int] = None,
        accession_number: Optional[str] = None,
        patient_id: Optional[str] = None,
        study_instance_uid: Optional[str] = None,
        series_instance_uid: Optional[str] = None,
        patient_orientation: Optional[PatientOrientation] = None,
        coordinate_frame_id: Optional[str] = None,
        landmarks: Iterable[ImageLandmark] = (),
        rois: Iterable["RegionOfInterest"] = (),
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__()
        _require_image_id(image_id)
        object.__setattr__(self, "image_id", image_id)
        object.__setattr__(self, "laterality", Laterality.coerce(laterality))
        object.__setattr__(self, "view_position", ViewPosition.coerce(view_position))
        object.__setattr__(self, "modality", ImageModality.coerce(modality))
        object.__setattr__(self, "source_sop_instance_uid", source_sop_instance_uid)
        object.__setattr__(self, "source_paths", _source_path_set(source_paths))
        object.__setattr__(self, "derived_from", derived_from)
        object.__setattr__(self, "source_modality", source_modality)
        object.__setattr__(self, "derived_image_type", derived_image_type)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "frame_count", frame_count)
        object.__setattr__(self, "accession_number", accession_number)
        object.__setattr__(self, "patient_id", patient_id)
        object.__setattr__(self, "study_instance_uid", study_instance_uid)
        object.__setattr__(self, "series_instance_uid", series_instance_uid)
        object.__setattr__(
            self,
            "patient_orientation",
            None
            if patient_orientation is None
            else PatientOrientation.coerce(patient_orientation),
        )
        object.__setattr__(self, "coordinate_frame_id", coordinate_frame_id)
        object.__setattr__(self, "_landmarks", ())
        object.__setattr__(self, "_rois", [])
        object.__setattr__(self, "metadata", dict(metadata or {}))
        for landmark in landmarks:
            self.add_landmark(landmark)
        for roi in rois:
            self._attach_local(roi)
        self._finish_initialization()

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "image_id":
            _require_image_id(value)
        elif name == "laterality":
            value = Laterality.coerce(value)
        elif name == "view_position":
            value = ViewPosition.coerce(value)
        elif name == "modality":
            value = ImageModality.coerce(value)
        elif name == "patient_orientation" and value is not None:
            value = PatientOrientation.coerce(value)
        elif name == "source_paths":
            value = _source_path_set(value)
        elif name == "metadata":
            value = dict(value or {})
        super().__setattr__(name, value)

    @property
    def identity(self) -> str:
        """Return the mutable toolkit identity."""

        return self.image_id

    @property
    def source_path(self) -> Optional[str]:
        """Return a deterministic source alias when one is available."""

        return min(self.source_paths) if self.source_paths else None

    @property
    def landmarks(self) -> Tuple[ImageLandmark, ...]:
        """Return image-embedded landmarks as a read-only view."""

        return self._landmarks

    @property
    def rois(self) -> Tuple["RegionOfInterest", ...]:
        """Return image-owned ROIs as a read-only view."""

        return tuple(self._rois)

    def _children(self) -> Tuple[MutableEntity, ...]:
        """Return direct domain containment children.

        Landmarks are embedded mutable values and remain local to the image;
        ROI objects are graph containment children.
        """

        return tuple(self._rois)

    def _attach_local(self, child: MutableEntity) -> MutableEntity:
        from embed_toolkit.imaging.rois import RegionOfInterest

        if not isinstance(child, RegionOfInterest):
            raise TypeError("MammogramImage can contain RegionOfInterest children")
        if child.image_id != self.image_id:
            raise ValueError("ROI image_id must match MammogramImage")
        for existing in self._rois:
            if existing is child:
                return child
            if existing.identity == child.identity:
                raise ValueError("ROI identity is already attached to MammogramImage")
        self._rois.append(child)
        return child

    def _detach_local(self, child: MutableEntity) -> MutableEntity:
        for index, existing in enumerate(self._rois):
            if existing is child:
                del self._rois[index]
                return child
        raise ValueError("ROI is not attached to MammogramImage")

    def add_landmark(self, landmark: ImageLandmark) -> ImageLandmark:
        """Embed a mutable landmark value on this image."""

        if not isinstance(landmark, ImageLandmark):
            raise TypeError("landmark must be an ImageLandmark")
        owned = landmark.owned_by(self.image_id)
        object.__setattr__(self, "_landmarks", (*self._landmarks, owned))
        return owned

    def add_roi(self, roi: "RegionOfInterest") -> "RegionOfInterest":
        """Attach an ROI locally or delegate membership to the owning graph."""

        if roi.image_id != self.image_id:
            raise ValueError("ROI image_id must match MammogramImage")
        for existing in self._rois:
            if existing is roi:
                return roi
            if existing.identity == roi.identity:
                raise ValueError("ROI identity is already attached to MammogramImage")
        if self.graph is not None:
            result = self.graph.attach(self, roi)
            return roi if result is None else result
        return self._attach_local(roi)

    def with_landmark(self, landmark: ImageLandmark) -> "MammogramImage":
        """Return a standalone shallow image copy with one more landmark."""

        copied = copy.copy(self)
        object.__setattr__(copied, "_graph", None)
        object.__setattr__(copied, "_rois", list(self._rois))
        object.__setattr__(copied, "_landmarks", tuple(self._landmarks))
        copied.add_landmark(landmark)
        return copied

    @property
    def image_shape(self) -> Optional[Tuple[int, int]]:
        if self.height is None or self.width is None:
            return None
        return self.height, self.width

    @property
    def is_dbt(self) -> bool:
        return self.modality is ImageModality.DBT

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

    def _to_dict_data(self, state: Any = None) -> Dict[str, object]:
        return {
            "image_id": self.image_id,
            "identity": self.identity,
            "source_sop_instance_uid": self.source_sop_instance_uid,
            "source_paths": sorted(self.source_paths),
            "derived_from": self.derived_from,
            "patient_id": self.patient_id,
            "accession_number": self.accession_number,
            "laterality": self.laterality.value,
            "view_position": self.view_position.value,
            "modality": self.modality.value,
            "source_modality": self.source_modality,
            "derived_image_type": self.derived_image_type,
            "height": self.height,
            "width": self.width,
            "frame_count": self.frame_count,
            "study_instance_uid": self.study_instance_uid,
            "series_instance_uid": self.series_instance_uid,
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
            "roi_references": [roi.identity for roi in self.rois],
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-ready non-recursive image representation."""

        return self._to_dict_data()


def _require_image_id(image_id: str) -> None:
    if not isinstance(image_id, str) or not image_id.strip():
        raise ValueError("image_id must be a non-empty string")


def _source_path_set(paths: Optional[Iterable[str]]) -> Set[str]:
    if paths is None:
        return set()
    if isinstance(paths, str):
        return {paths}
    result = set(paths)
    if any(not isinstance(path, str) for path in result):
        raise TypeError("source_paths must contain strings")
    return result
