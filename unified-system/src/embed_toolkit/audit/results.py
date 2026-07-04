"""Serializable workflow result shapes for the unified toolkit."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional

from embed_toolkit.audit.evidence import (
    AuditWarning,
    Evidence,
    JsonMapping,
    JsonValue,
    serialize_mapping,
)


class ResultStatus(str, Enum):
    """Common status values for workflow results."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ResultAuditMixin:
    """Shared serialization of status, evidence, warnings, and metadata."""

    status: ResultStatus = ResultStatus.SUCCESS
    evidence: List[Evidence] = field(default_factory=list)
    warnings: List[AuditWarning] = field(default_factory=list)
    metadata: JsonMapping = field(default_factory=dict)

    def audit_dict(self) -> Dict[str, JsonValue]:
        return {
            "status": self.status.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "metadata": serialize_mapping(self.metadata),
        }


@dataclass(frozen=True)
class WorkflowResult(ResultAuditMixin):
    """A reusable result container for workflow outputs without a fixed schema."""

    result_type: str = ""
    payload: JsonMapping = field(default_factory=dict)

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        data.update(
            {
                "result_type": self.result_type,
                "payload": serialize_mapping(self.payload),
            }
        )
        return data


@dataclass(frozen=True)
class LocalizationResult(ResultAuditMixin):
    """An anatomical localization result for a finding, ROI, or image region."""

    subject_id: str = ""
    subject_type: str = ""
    anatomical_position: JsonMapping = field(default_factory=dict)
    continuous_position: JsonMapping = field(default_factory=dict)

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        data.update(
            {
                "subject_id": self.subject_id,
                "subject_type": self.subject_type,
                "anatomical_position": serialize_mapping(self.anatomical_position),
                "continuous_position": serialize_mapping(self.continuous_position),
            }
        )
        return data


@dataclass(frozen=True)
class MatchCandidate:
    """A scored candidate association between a finding and an ROI."""

    roi_id: str
    score: float
    payload: JsonMapping = field(default_factory=dict)
    evidence: List[Evidence] = field(default_factory=list)

    def to_dict(self) -> Dict[str, JsonValue]:
        return {
            "roi_id": self.roi_id,
            "score": self.score,
            "payload": serialize_mapping(self.payload),
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class MatchingResult(ResultAuditMixin):
    """A finding-to-ROI matching result that keeps alternates inspectable."""

    finding_id: str = ""
    matched_roi_id: Optional[str] = None
    candidates: List[MatchCandidate] = field(default_factory=list)
    unmatched_roi_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        data.update(
            {
                "finding_id": self.finding_id,
                "matched_roi_id": self.matched_roi_id,
                "candidates": [candidate.to_dict() for candidate in self.candidates],
                "unmatched_roi_ids": list(self.unmatched_roi_ids),
            }
        )
        return data


@dataclass(frozen=True)
class TransferResult(ResultAuditMixin):
    """An ROI transfer result between acquisition or image contexts."""

    source_roi_id: str = ""
    source_image_id: str = ""
    target_image_id: str = ""
    transferred_roi: JsonMapping = field(default_factory=dict)
    transform: JsonMapping = field(default_factory=dict)

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        data.update(
            {
                "source_roi_id": self.source_roi_id,
                "source_image_id": self.source_image_id,
                "target_image_id": self.target_image_id,
                "transferred_roi": serialize_mapping(self.transferred_roi),
                "transform": serialize_mapping(self.transform),
            }
        )
        return data


@dataclass(frozen=True)
class PatchExtractionResult(ResultAuditMixin):
    """A patch extraction result with image-local geometry and storage metadata."""

    image_id: str = ""
    roi_id: str = ""
    patch_id: str = ""
    bbox: List[float] = field(default_factory=list)
    shape: List[int] = field(default_factory=list)
    patch_payload: JsonMapping = field(default_factory=dict)

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        data.update(
            {
                "image_id": self.image_id,
                "roi_id": self.roi_id,
                "patch_id": self.patch_id,
                "bbox": list(self.bbox),
                "shape": list(self.shape),
                "patch_payload": serialize_mapping(self.patch_payload),
            }
        )
        return data
