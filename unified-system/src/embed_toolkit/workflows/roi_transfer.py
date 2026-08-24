"""ROI transfer between related mammography acquisitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping, Optional, Tuple

from embed_toolkit.audit.evidence import (
    AuditWarning,
    Evidence,
    WarningSeverity,
    freeze_json_mapping,
    serialize_mapping,
)
from embed_toolkit.audit.results import ResultStatus, TransferResult
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.imaging.images import MammogramImage
from embed_toolkit.imaging.rois import RegionOfInterest


class AcquisitionKind(str, Enum):
    """Acquisition categories supported by ROI transfer."""

    FFDM = "ffdm"
    DBT = "dbt"
    SYNTHETIC_2D = "synthetic_2d"
    UNKNOWN = "unknown"

    @classmethod
    def from_modality(cls, modality: ImageModality) -> "AcquisitionKind":
        parsed = ImageModality.coerce(modality)
        if parsed is ImageModality.FFDM:
            return cls.FFDM
        if parsed is ImageModality.DBT:
            return cls.DBT
        if parsed is ImageModality.S2D:
            return cls.SYNTHETIC_2D
        return cls.UNKNOWN


@dataclass(frozen=True)
class AcquisitionRelationship:
    """Relationship facts used to decide whether an ROI can be transferred."""

    source_kind: AcquisitionKind
    target_kind: AcquisitionKind
    same_patient: bool
    same_breast: bool
    same_view: bool
    related: bool
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", AcquisitionKind(self.source_kind))
        object.__setattr__(self, "target_kind", AcquisitionKind(self.target_kind))
        for name in ("same_patient", "same_breast", "same_view", "related"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")
        object.__setattr__(self, "evidence", freeze_json_mapping(self.evidence))

    def to_dict(self) -> Dict[str, object]:
        """Return a fresh strict-JSON representation of the relationship facts."""

        return {
            "source_kind": self.source_kind.value,
            "target_kind": self.target_kind.value,
            "same_patient": self.same_patient,
            "same_breast": self.same_breast,
            "same_view": self.same_view,
            "related": self.related,
            "evidence": serialize_mapping(self.evidence),
        }

    @classmethod
    def from_images(
        cls,
        source_image: MammogramImage,
        target_image: MammogramImage,
        *,
        related: Optional[bool] = None,
    ) -> "AcquisitionRelationship":
        """Infer transfer relationship facts from two image metadata records."""

        same_patient = _same_populated_patient(source_image, target_image)
        same_breast = _same_unilateral_breast(source_image, target_image)
        same_view = _same_known_view(source_image, target_image)
        shared_context = _has_shared_acquisition_context(source_image, target_image)
        if related is not None and not isinstance(related, bool):
            raise TypeError("related must be a bool")
        if related is None:
            related = shared_context

        return cls(
            source_kind=AcquisitionKind.from_modality(source_image.modality),
            target_kind=AcquisitionKind.from_modality(target_image.modality),
            same_patient=same_patient,
            same_breast=same_breast,
            same_view=same_view,
            related=bool(related),
            evidence={
                "source_modality": source_image.modality.value,
                "target_modality": target_image.modality.value,
                "source_laterality": source_image.laterality.value,
                "target_laterality": target_image.laterality.value,
                "source_view": source_image.view_position.value,
                "target_view": target_image.view_position.value,
                "same_patient": same_patient,
                "shared_acquisition_context": shared_context,
            },
        )

    @property
    def same_breast_same_view(self) -> bool:
        return self.same_breast and self.same_view

    @property
    def can_transfer(self) -> bool:
        return self.related and self.same_patient and self.same_breast_same_view

    @property
    def is_cross_modality(self) -> bool:
        return self.source_kind != self.target_kind


def transfer_roi(
    roi: RegionOfInterest,
    source_image: MammogramImage,
    target_image: MammogramImage,
    *,
    relationship: Optional[AcquisitionRelationship] = None,
    retain_source_frame_evidence: bool = True,
) -> TransferResult:
    """Transfer an ROI to a related same-breast, same-view target image.

    The transform is origin-relative scaling from source image dimensions to
    target image dimensions. Ordinary incompatibility returns a skipped or failed
    ``TransferResult`` with structured warnings instead of raising.
    """

    if not isinstance(roi, RegionOfInterest):
        raise TypeError("roi must be a RegionOfInterest")
    if not isinstance(retain_source_frame_evidence, bool):
        raise TypeError("retain_source_frame_evidence must be a bool")
    if roi.image_id != source_image.image_id:
        raise ValueError("ROI image_id must match the source image")
    if roi.locator.image_locator not in source_image.sources:
        raise ValueError("ROI locator scope must occur in the source image ledger")
    if any(source not in source_image.sources for source in roi.sources):
        raise ValueError("ROI sources must occur in the source image ledger")
    if roi.source_provenance.modality is not source_image.modality:
        raise ValueError("ROI source provenance modality must match the source image")
    if source_image.frame_count is not None and any(
        index >= source_image.frame_count for index in roi.frame_indices
    ):
        raise ValueError("ROI frame indices exceed the source image frame count")

    observed_relationship = AcquisitionRelationship.from_images(
        source_image,
        target_image,
    )
    if relationship is not None and (
        relationship.source_kind is not observed_relationship.source_kind
        or relationship.target_kind is not observed_relationship.target_kind
        or relationship.same_patient != observed_relationship.same_patient
        or relationship.same_breast != observed_relationship.same_breast
        or relationship.same_view != observed_relationship.same_view
    ):
        raise ValueError("Supplied acquisition relationship contradicts image facts")
    relationship = relationship or observed_relationship
    evidence = [
        Evidence(
            kind="acquisition_relationship",
            source="roi_transfer",
            payload={
                **observed_relationship.evidence,
                "related": relationship.related,
            },
        )
    ]

    if not relationship.can_transfer:
        return _result(
            roi,
            source_image,
            target_image,
            status=ResultStatus.SKIPPED,
            evidence=evidence,
            warnings=[
                AuditWarning(
                    code="incompatible_transfer",
                    message=(
                        "ROI transfer requires the same patient and related "
                        "same-breast same-view images"
                    ),
                    severity=WarningSeverity.WARNING,
                    payload={
                        "same_patient": relationship.same_patient,
                        "same_breast": relationship.same_breast,
                        "same_view": relationship.same_view,
                        "related": relationship.related,
                    },
                )
            ],
        )

    if source_image.image_shape is None or target_image.image_shape is None:
        return _result(
            roi,
            source_image,
            target_image,
            status=ResultStatus.FAILED,
            evidence=evidence,
            warnings=[
                AuditWarning(
                    code="missing_image_dimensions",
                    message="Source and target image dimensions are required for ROI transfer",
                    severity=WarningSeverity.ERROR,
                    payload={
                        "source_shape": source_image.image_shape,
                        "target_shape": target_image.image_shape,
                    },
                )
            ],
        )

    source_height, source_width = source_image.image_shape
    target_height, target_width = target_image.image_shape
    scale_y = target_height / source_height
    scale_x = target_width / source_width
    transferred_coordinates = (
        roi.y_min * scale_y,
        roi.x_min * scale_x,
        roi.y_max * scale_y,
        roi.x_max * scale_x,
    )
    source_frame_indices = roi.frame_indices if retain_source_frame_evidence else ()
    transferred = _projection_payload(
        roi,
        target_image,
        transferred_coordinates,
        source_frame_indices,
    )

    warnings = []
    if relationship.is_cross_modality or source_image.is_dbt or target_image.is_dbt:
        warnings.append(
            AuditWarning(
                code="approximate_transfer",
                message="Transfer used relative image scaling across acquisition contexts",
                severity=WarningSeverity.INFO,
                payload={
                    "source_kind": relationship.source_kind.value,
                    "target_kind": relationship.target_kind.value,
                    "retained_source_frame_indices": list(source_frame_indices),
                },
            )
        )

    return _result(
        roi,
        source_image,
        target_image,
        status=ResultStatus.SUCCESS,
        transferred=transferred,
        transform={
            "scale": [scale_y, scale_x],
            "translation": [0.0, 0.0],
            "source_shape": [source_height, source_width],
            "target_shape": [target_height, target_width],
            "retain_source_frame_evidence": retain_source_frame_evidence,
        },
        evidence=evidence,
        warnings=warnings,
    )


def _same_populated_patient(
    source_image: MammogramImage,
    target_image: MammogramImage,
) -> bool:
    source_patient = source_image.patient_id
    target_patient = target_image.patient_id
    return bool(
        isinstance(source_patient, str)
        and source_patient.strip()
        and isinstance(target_patient, str)
        and target_patient.strip()
        and source_patient == target_patient
    )


def _same_unilateral_breast(
    source_image: MammogramImage,
    target_image: MammogramImage,
) -> bool:
    return (
        source_image.laterality is target_image.laterality
        and source_image.laterality in {Laterality.LEFT, Laterality.RIGHT}
    )


def _same_known_view(
    source_image: MammogramImage,
    target_image: MammogramImage,
) -> bool:
    return (
        source_image.view_position is target_image.view_position
        and source_image.view_position is not ViewPosition.UNKNOWN
    )


def _has_shared_acquisition_context(
    source_image: MammogramImage,
    target_image: MammogramImage,
) -> bool:
    pairs: Tuple[Tuple[Optional[str], Optional[str]], ...] = (
        (source_image.accession_number, target_image.accession_number),
        (source_image.study_instance_uid, target_image.study_instance_uid),
        (source_image.series_instance_uid, target_image.series_instance_uid),
    )
    return any(source == target for source, target in pairs if source and target)


def _projection_payload(
    roi: RegionOfInterest,
    target_image: MammogramImage,
    coordinates: Tuple[float, float, float, float],
    source_frame_indices: Tuple[int, ...],
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "target_image_id": target_image.image_id,
        "coordinates": list(coordinates),
        "source_frame_indices": list(source_frame_indices),
        "source_provenance": roi.source_provenance.to_dict(),
        "source_references": [source.to_dict() for source in roi.sources],
        "annotation_source": roi.annotation_source,
        "coordinate_frame_id": target_image.coordinate_frame_id,
    }
    if roi.confidence is not None:
        payload["confidence"] = roi.confidence
    return payload


def _result(
    roi: RegionOfInterest,
    source_image: MammogramImage,
    target_image: MammogramImage,
    *,
    status: ResultStatus,
    evidence: list[Evidence],
    warnings: list[AuditWarning],
    transferred: Optional[Dict[str, object]] = None,
    transform: Optional[Dict[str, object]] = None,
) -> TransferResult:
    return TransferResult(
        status=status,
        source_roi_locator=roi.locator,
        source_image_id=source_image.image_id,
        target_image_id=target_image.image_id,
        transferred_roi=transferred or {},
        transform=transform or {},
        evidence=evidence,
        warnings=warnings,
    )
