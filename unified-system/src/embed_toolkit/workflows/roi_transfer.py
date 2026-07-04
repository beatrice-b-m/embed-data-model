"""ROI transfer between related mammography acquisitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from embed_toolkit.audit.evidence import AuditWarning, Evidence, WarningSeverity
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
    same_breast: bool
    same_view: bool
    related: bool
    evidence: Dict[str, object]

    @classmethod
    def from_images(
        cls,
        source_image: MammogramImage,
        target_image: MammogramImage,
        *,
        related: Optional[bool] = None,
    ) -> "AcquisitionRelationship":
        """Infer transfer relationship facts from two image metadata records."""

        same_breast = _same_unilateral_breast(source_image, target_image)
        same_view = _same_known_view(source_image, target_image)
        inferred_related = _has_shared_acquisition_context(source_image, target_image)
        if related is None:
            related = inferred_related or (same_breast and same_view)

        return cls(
            source_kind=AcquisitionKind.from_modality(source_image.modality),
            target_kind=AcquisitionKind.from_modality(target_image.modality),
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
                "shared_context": inferred_related,
            },
        )

    @property
    def same_breast_same_view(self) -> bool:
        return self.same_breast and self.same_view

    @property
    def can_transfer(self) -> bool:
        return self.related and self.same_breast_same_view

    @property
    def is_cross_modality(self) -> bool:
        return self.source_kind != self.target_kind


def transfer_roi(
    roi: RegionOfInterest,
    source_image: MammogramImage,
    target_image: MammogramImage,
    *,
    relationship: Optional[AcquisitionRelationship] = None,
    preserve_dbt_frame: bool = True,
) -> TransferResult:
    """Transfer an ROI to a related same-breast, same-view target image.

    The transform is origin-relative scaling from source image dimensions to
    target image dimensions. Ordinary incompatibility returns a skipped or failed
    ``TransferResult`` with structured warnings instead of raising.
    """

    relationship = relationship or AcquisitionRelationship.from_images(
        source_image, target_image
    )
    evidence = [
        Evidence(
            kind="acquisition_relationship",
            source="roi_transfer",
            payload=relationship.evidence,
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
                    message="ROI transfer requires related same-breast same-view images",
                    severity=WarningSeverity.WARNING,
                    payload={
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
    transferred = roi.realign(
        scale_y=scale_y,
        scale_x=scale_x,
        image_id=target_image.image_id,
        coordinate_frame_id=target_image.coordinate_frame_id,
    )
    if not preserve_dbt_frame:
        transferred = RegionOfInterest(
            coordinates=transferred.coordinates,
            roi_id=transferred.roi_id,
            image_id=transferred.image_id,
            source=transferred.source,
            confidence=transferred.confidence,
            coordinate_frame_id=transferred.coordinate_frame_id,
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
                    "preserved_frame_index": transferred.frame_index,
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
            "preserve_dbt_frame": preserve_dbt_frame,
        },
        evidence=evidence,
        warnings=warnings,
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


def _roi_payload(roi: RegionOfInterest) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "coordinates": list(roi.coordinates),
        "roi_id": roi.roi_id,
        "image_id": roi.image_id,
    }
    if roi.frame_index is not None:
        payload["frame_index"] = roi.frame_index
    if roi.source is not None:
        payload["source"] = roi.source
    if roi.confidence is not None:
        payload["confidence"] = roi.confidence
    if roi.coordinate_frame_id is not None:
        payload["coordinate_frame_id"] = roi.coordinate_frame_id
    return payload


def _result(
    roi: RegionOfInterest,
    source_image: MammogramImage,
    target_image: MammogramImage,
    *,
    status: ResultStatus,
    evidence: list[Evidence],
    warnings: list[AuditWarning],
    transferred: Optional[RegionOfInterest] = None,
    transform: Optional[Dict[str, object]] = None,
) -> TransferResult:
    return TransferResult(
        status=status,
        source_roi_id=roi.roi_id or "",
        source_image_id=source_image.image_id,
        target_image_id=target_image.image_id,
        transferred_roi=_roi_payload(transferred) if transferred is not None else {},
        transform=transform or {},
        evidence=evidence,
        warnings=warnings,
    )
