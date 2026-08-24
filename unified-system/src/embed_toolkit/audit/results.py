"""Serializable workflow result shapes for the unified toolkit."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import math
from typing import Dict, List, Optional, Tuple

from embed_toolkit.audit.evidence import (
    AuditWarning,
    Evidence,
    JsonMapping,
    JsonValue,
    freeze_json_mapping,
    serialize_mapping,
)
from embed_toolkit.imaging.roi_provenance import RoiLocator


def _locator_key(locator: RoiLocator) -> str:
    return json.dumps(locator.to_dict(), sort_keys=True, separators=(",", ":"))


def _normalized_locators(
    values: object,
    field_name: str,
) -> Tuple[RoiLocator, ...]:
    normalized = tuple(values)  # type: ignore[arg-type]
    if any(not isinstance(value, RoiLocator) for value in normalized):
        raise TypeError(f"{field_name} must contain only RoiLocator values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must contain unique RoiLocator values")
    return tuple(sorted(normalized, key=_locator_key))


class ResultStatus(str, Enum):
    """Common status values for workflow results."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class AttributionState(str, Enum):
    """Epistemic state of a finding-to-ROI attribution."""

    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"
    ABSTAINED = "abstained"
    VALIDATED = "validated"


@dataclass(frozen=True)
class ResultAuditMixin:
    """Shared serialization of status, evidence, warnings, and metadata."""

    status: ResultStatus = ResultStatus.SUCCESS
    evidence: List[Evidence] = field(default_factory=list)
    warnings: List[AuditWarning] = field(default_factory=list)
    metadata: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ResultStatus(self.status))
        evidence = tuple(self.evidence)
        warnings = tuple(self.warnings)
        if any(not isinstance(value, Evidence) for value in evidence):
            raise TypeError("evidence must contain only Evidence values")
        if any(not isinstance(value, AuditWarning) for value in warnings):
            raise TypeError("warnings must contain only AuditWarning values")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "metadata", freeze_json_mapping(self.metadata))

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

    def __post_init__(self) -> None:
        ResultAuditMixin.__post_init__(self)
        if not isinstance(self.result_type, str) or not self.result_type.strip():
            raise ValueError("result_type must be a non-empty string")
        object.__setattr__(self, "payload", freeze_json_mapping(self.payload))

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
    roi_locator: Optional[RoiLocator] = None
    anatomical_position: JsonMapping = field(default_factory=dict)
    continuous_position: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        ResultAuditMixin.__post_init__(self)
        is_roi = self.subject_type == "roi"
        if is_roi:
            if not isinstance(self.roi_locator, RoiLocator):
                raise TypeError("ROI localization requires a RoiLocator")
            if self.subject_id:
                raise ValueError("ROI localization cannot use subject_id identity")
        elif self.roi_locator is not None:
            raise ValueError("roi_locator is only valid for ROI localization")
        elif not isinstance(self.subject_id, str) or not self.subject_id.strip():
            raise ValueError("Non-ROI localization requires a subject_id")
        object.__setattr__(
            self, "anatomical_position", freeze_json_mapping(self.anatomical_position)
        )
        object.__setattr__(
            self, "continuous_position", freeze_json_mapping(self.continuous_position)
        )

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        identity: Dict[str, JsonValue]
        if self.roi_locator is not None:
            identity = {"roi_locator": self.roi_locator.to_dict()}
        else:
            identity = {"subject_id": self.subject_id}
        data.update(
            {
                **identity,
                "subject_type": self.subject_type,
                "anatomical_position": serialize_mapping(self.anatomical_position),
                "continuous_position": serialize_mapping(self.continuous_position),
            }
        )
        return data


@dataclass(frozen=True)
class MatchCandidate:
    """A scored candidate association between a finding and an ROI."""

    candidate_id: str
    score: float
    scored_axis_count: int = 0
    eligible: bool = True
    roi_locators: Tuple[RoiLocator, ...] = field(default_factory=tuple)
    payload: JsonMapping = field(default_factory=dict)
    evidence: List[Evidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("candidate_id must be a non-empty string")
        object.__setattr__(
            self,
            "roi_locators",
            _normalized_locators(self.roi_locators, "roi_locators"),
        )
        if not self.roi_locators:
            raise ValueError("roi_locators must contain at least one locator")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise TypeError("score must be numeric")
        if not math.isfinite(float(self.score)) or not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be finite and in [0, 1]")
        if isinstance(self.scored_axis_count, bool) or not isinstance(
            self.scored_axis_count, int
        ):
            raise TypeError("scored_axis_count must be an integer")
        if self.scored_axis_count < 0:
            raise ValueError("scored_axis_count must be non-negative")
        if not isinstance(self.eligible, bool):
            raise TypeError("eligible must be a bool")
        evidence = tuple(self.evidence)
        if any(not isinstance(value, Evidence) for value in evidence):
            raise TypeError("candidate evidence must contain only Evidence values")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "payload", freeze_json_mapping(self.payload))

    @property
    def rank_key(self) -> tuple[float, int, str]:
        """Return the single deterministic candidate ordering key."""

        return (-self.score, -self.scored_axis_count, self.candidate_id)

    def to_dict(self) -> Dict[str, JsonValue]:
        return {
            "candidate_id": self.candidate_id,
            "score": self.score,
            "scored_axis_count": self.scored_axis_count,
            "eligible": self.eligible,
            "roi_locators": [locator.to_dict() for locator in self.roi_locators],
            "payload": serialize_mapping(self.payload),
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class MatchingResult(ResultAuditMixin):
    """An inferred finding-to-ROI attribution with inspectable alternates."""

    finding_id: str = ""
    matched_roi_locators: Tuple[RoiLocator, ...] = field(default_factory=tuple)
    matched_roi_group_ids: List[str] = field(default_factory=list)
    candidates: List[MatchCandidate] = field(default_factory=list)
    unmatched_roi_locators: Tuple[RoiLocator, ...] = field(default_factory=tuple)
    roi_locators_attributed_to_other_findings: Tuple[RoiLocator, ...] = field(
        default_factory=tuple
    )
    attribution_basis: str = "inferred"
    attribution_state: AttributionState = AttributionState.ABSTAINED
    score: Optional[float] = None
    score_margin: Optional[float] = None
    observed_descriptors: JsonMapping = field(default_factory=dict)
    scored_descriptors: List[str] = field(default_factory=list)
    algorithm_version: str = "finding-roi-inference-v2"
    configuration_version: str = "default-v1"

    def __post_init__(self) -> None:
        ResultAuditMixin.__post_init__(self)
        if not isinstance(self.finding_id, str) or not self.finding_id.strip():
            raise ValueError("finding_id must be a non-empty string")
        matched = _normalized_locators(
            self.matched_roi_locators,
            "matched_roi_locators",
        )
        unmatched = _normalized_locators(
            self.unmatched_roi_locators,
            "unmatched_roi_locators",
        )
        other = _normalized_locators(
            self.roi_locators_attributed_to_other_findings,
            "roi_locators_attributed_to_other_findings",
        )
        if (
            set(matched) & set(unmatched)
            or set(matched) & set(other)
            or set(unmatched) & set(other)
        ):
            raise ValueError(
                "ROI locator coverage categories must be pairwise disjoint"
            )
        object.__setattr__(self, "matched_roi_locators", matched)
        object.__setattr__(self, "unmatched_roi_locators", unmatched)
        object.__setattr__(self, "roi_locators_attributed_to_other_findings", other)
        groups = tuple(self.matched_roi_group_ids)
        if any(not isinstance(value, str) or not value.strip() for value in groups):
            raise ValueError("matched_roi_group_ids must be non-empty strings")
        if len(set(groups)) != len(groups):
            raise ValueError("matched_roi_group_ids must be unique")
        object.__setattr__(self, "matched_roi_group_ids", tuple(sorted(groups)))
        candidates = tuple(self.candidates)
        if any(not isinstance(value, MatchCandidate) for value in candidates):
            raise TypeError("candidates must contain only MatchCandidate values")
        if len({value.candidate_id for value in candidates}) != len(candidates):
            raise ValueError("candidate IDs must be unique")
        represented = set()
        for candidate in candidates:
            overlap = represented.intersection(candidate.roi_locators)
            if overlap:
                raise ValueError("candidate ROI locator memberships must be disjoint")
            represented.update(candidate.roi_locators)
        candidates = tuple(sorted(candidates, key=lambda value: value.rank_key))
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(
            self,
            "attribution_state",
            AttributionState(self.attribution_state),
        )
        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
                raise TypeError("score must be numeric")
            if not math.isfinite(float(self.score)) or not 0.0 <= self.score <= 1.0:
                raise ValueError("score must be finite and in [0, 1]")
        if self.score_margin is not None:
            if isinstance(self.score_margin, bool) or not isinstance(
                self.score_margin, (int, float)
            ):
                raise TypeError("score_margin must be numeric")
            if (
                not math.isfinite(float(self.score_margin))
                or not 0.0 <= self.score_margin <= 1.0
            ):
                raise ValueError("score_margin must be finite and in [0, 1]")
        state = self.attribution_state
        if state in {AttributionState.INFERRED, AttributionState.VALIDATED}:
            if not matched or not groups:
                raise ValueError(
                    "Attributed results require matched ROI locators and groups"
                )
        elif matched or groups:
            raise ValueError("Non-attributed results cannot contain matched ROI values")
        candidate_ids = {candidate.candidate_id for candidate in candidates}
        if not set(groups).issubset(candidate_ids):
            raise ValueError("matched ROI groups must resolve to candidates")
        expected_matched = {
            locator
            for candidate in candidates
            if candidate.candidate_id in groups
            for locator in candidate.roi_locators
        }
        if expected_matched != set(matched):
            raise ValueError(
                "matched ROI locators must match selected candidate groups"
            )
        if set(matched) | set(unmatched) | set(other) != represented:
            raise ValueError("ROI locator coverage must exactly partition candidates")
        selected = [
            candidate for candidate in candidates if candidate.candidate_id in groups
        ]
        eligible = [candidate for candidate in candidates if candidate.eligible]
        expected_margin = (
            eligible[0].score - eligible[1].score if len(eligible) >= 2 else None
        )
        if self.score_margin != expected_margin:
            raise ValueError(
                "score_margin must equal the top-two eligible candidate difference"
            )
        if state in {AttributionState.INFERRED, AttributionState.VALIDATED}:
            selected_score = max(candidate.score for candidate in selected)
            if self.score is None or self.score != selected_score:
                raise ValueError(
                    "Attributed result score must equal its best selected candidate"
                )
        elif state is AttributionState.AMBIGUOUS:
            if len(eligible) < 2 or self.score != eligible[0].score:
                raise ValueError("Ambiguous result score must equal its best candidate")
        elif state is AttributionState.ABSTAINED:
            expected_score = candidates[0].score if candidates else None
            if self.score != expected_score:
                raise ValueError("Abstained result score must equal its best candidate")
        object.__setattr__(
            self,
            "observed_descriptors",
            freeze_json_mapping(self.observed_descriptors),
        )
        object.__setattr__(self, "scored_descriptors", tuple(self.scored_descriptors))

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        data.update(
            {
                "finding_id": self.finding_id,
                "matched_roi_locators": [
                    locator.to_dict() for locator in self.matched_roi_locators
                ],
                "matched_roi_group_ids": list(self.matched_roi_group_ids),
                "candidates": [candidate.to_dict() for candidate in self.candidates],
                "unmatched_roi_locators": [
                    locator.to_dict() for locator in self.unmatched_roi_locators
                ],
                "roi_locators_attributed_to_other_findings": [
                    locator.to_dict()
                    for locator in self.roi_locators_attributed_to_other_findings
                ],
                "attribution_basis": self.attribution_basis,
                "attribution_state": self.attribution_state.value,
                "score": self.score,
                "score_margin": self.score_margin,
                "observed_descriptors": serialize_mapping(self.observed_descriptors),
                "scored_descriptors": list(self.scored_descriptors),
                "algorithm_version": self.algorithm_version,
                "configuration_version": self.configuration_version,
            }
        )
        return data


@dataclass(frozen=True)
class TransferResult(ResultAuditMixin):
    """An ROI transfer result between acquisition or image contexts."""

    source_roi_locator: Optional[RoiLocator] = None
    source_image_id: str = ""
    target_image_id: str = ""
    transferred_roi: JsonMapping = field(default_factory=dict)
    transform: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        ResultAuditMixin.__post_init__(self)
        if not isinstance(self.source_roi_locator, RoiLocator):
            raise TypeError("source_roi_locator must be a RoiLocator")
        for name in ("source_image_id", "target_image_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        transferred = freeze_json_mapping(self.transferred_roi)
        transform = freeze_json_mapping(self.transform)
        has_output = bool(transferred) or bool(transform)
        if self.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL}:
            if not transferred or not transform:
                raise ValueError(
                    "Successful transfers require projection and transform"
                )
            forbidden = {
                "locator",
                "roi_locator",
                "source_roi_locator",
                "target_locator",
                "target_roi_locator",
            }
            if forbidden.intersection(transferred):
                raise ValueError("Transfer projection cannot contain ROI identity")
            if transferred.get("target_image_id") != self.target_image_id:
                raise ValueError(
                    "Transfer projection target_image_id must match result"
                )
            coordinates = transferred.get("coordinates")
            if (
                not isinstance(coordinates, tuple)
                or len(coordinates) != 4
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    for value in coordinates
                )
            ):
                raise ValueError("Transfer projection requires four finite coordinates")
            source_frames = transferred.get("source_frame_indices")
            if not isinstance(source_frames, tuple) or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in source_frames
            ):
                raise ValueError(
                    "Transfer projection requires plural source_frame_indices"
                )
            if "frame_indices" in transferred:
                raise ValueError(
                    "Transfer projection cannot imply target frame indices"
                )
        elif has_output:
            raise ValueError("Skipped or failed transfers cannot contain output")
        object.__setattr__(self, "transferred_roi", transferred)
        object.__setattr__(self, "transform", transform)

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        data.update(
            {
                "source_roi_locator": self.source_roi_locator.to_dict(),
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
    roi_locator: Optional[RoiLocator] = None
    patch_id: str = ""
    bbox: List[float] = field(default_factory=list)
    shape: List[int] = field(default_factory=list)
    patch_payload: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        ResultAuditMixin.__post_init__(self)
        if not isinstance(self.roi_locator, RoiLocator):
            raise TypeError("roi_locator must be a RoiLocator")
        for name in ("image_id", "patch_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        bbox = tuple(self.bbox)
        if bbox and (
            len(bbox) != 4
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in bbox
            )
        ):
            raise ValueError("bbox must contain four finite numeric values")
        shape = tuple(self.shape)
        if shape and (
            len(shape) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in shape
            )
        ):
            raise ValueError("shape must contain two non-negative integers")
        if self.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL} and (
            not bbox or not shape
        ):
            raise ValueError("Successful patch results require bbox and shape")
        object.__setattr__(self, "bbox", bbox)
        object.__setattr__(self, "shape", shape)
        object.__setattr__(
            self, "patch_payload", freeze_json_mapping(self.patch_payload)
        )

    def to_dict(self) -> Dict[str, JsonValue]:
        data = self.audit_dict()
        data.update(
            {
                "image_id": self.image_id,
                "roi_locator": self.roi_locator.to_dict(),
                "patch_id": self.patch_id,
                "bbox": list(self.bbox),
                "shape": list(self.shape),
                "patch_payload": serialize_mapping(self.patch_payload),
            }
        )
        return data
