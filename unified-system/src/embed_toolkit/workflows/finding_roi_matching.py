"""Finding-to-ROI matching workflow using localization results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from embed_toolkit.audit.evidence import AuditWarning, Evidence, WarningSeverity
from embed_toolkit.audit.results import (
    LocalizationResult,
    MatchCandidate,
    MatchingResult,
    ResultStatus,
)
from embed_toolkit.core.primitives import Laterality


AxisName = str

_UNKNOWN_AXIS_VALUES = {"", "unknown", "UNKNOWN", None}
_MATCHABLE_SIDES = {Laterality.LEFT, Laterality.RIGHT}


@dataclass(frozen=True)
class FindingRoiMatcher:
    """Assign localized findings to localized ROIs by anatomical agreement."""

    axes: tuple[AxisName, ...] = ("ml", "si", "depth")
    minimum_score: float = 0.0

    def match(
        self,
        findings: Iterable[LocalizationResult],
        rois: Iterable[LocalizationResult],
    ) -> list[MatchingResult]:
        """Return one matching result per finding with a shared unmatched ROI report."""

        finding_positions = [
            _LocalizedSubject.from_result(result, default_subject_type="finding")
            for result in findings
        ]
        roi_positions = [
            _LocalizedSubject.from_result(result, default_subject_type="roi")
            for result in rois
        ]

        candidates_by_finding: dict[str, list[MatchCandidate]] = {}
        viable_pairs: list[_ViablePair] = []
        for finding in finding_positions:
            candidates: list[MatchCandidate] = []
            for roi in roi_positions:
                candidate, viable = self._candidate(finding, roi)
                candidates.append(candidate)
                if viable:
                    viable_pairs.append(
                        _ViablePair(
                            finding_id=finding.subject_id,
                            roi_id=roi.subject_id,
                            score=candidate.score,
                            axis_count=len(candidate.payload.get("scored_axes", [])),
                        )
                    )
            candidates_by_finding[finding.subject_id] = sorted(
                candidates,
                key=lambda item: (
                    -item.score,
                    -len(item.payload.get("scored_axes", [])),
                    item.roi_id,
                ),
            )

        assignments = _assign_one_to_one(viable_pairs)
        assigned_rois = set(assignments.values())
        unmatched_roi_ids = [
            roi.subject_id for roi in sorted(roi_positions, key=lambda item: item.subject_id)
            if roi.subject_id not in assigned_rois
        ]

        return [
            self._result_for_finding(
                finding=finding,
                matched_roi_id=assignments.get(finding.subject_id),
                candidates=candidates_by_finding[finding.subject_id],
                unmatched_roi_ids=unmatched_roi_ids,
            )
            for finding in sorted(finding_positions, key=lambda item: item.subject_id)
        ]

    def _candidate(
        self,
        finding: "_LocalizedSubject",
        roi: "_LocalizedSubject",
    ) -> tuple[MatchCandidate, bool]:
        evidence = [
            Evidence(
                kind="localized_finding",
                source="finding_roi_matcher",
                payload=finding.evidence_payload(),
            ),
            Evidence(
                kind="localized_roi",
                source="finding_roi_matcher",
                payload=roi.evidence_payload(),
            ),
        ]

        side_reason = _side_mismatch_reason(finding.side, roi.side)
        if side_reason is not None:
            return (
                MatchCandidate(
                    roi_id=roi.subject_id,
                    score=0.0,
                    payload={
                        "possible": False,
                        "skipped_reason": side_reason,
                        "finding_laterality": _side_value(finding.side),
                        "roi_laterality": _side_value(roi.side),
                        "scored_axes": [],
                    },
                    evidence=evidence,
                ),
                False,
            )

        axis_scores = []
        for axis in self.axes:
            finding_value = finding.axis_values.get(axis)
            roi_value = roi.axis_values.get(axis)
            if _is_unknown_axis_value(finding_value) or _is_unknown_axis_value(roi_value):
                continue
            axis_scores.append(
                {
                    "axis": axis,
                    "finding_value": finding_value,
                    "roi_value": roi_value,
                    "matched": finding_value == roi_value,
                }
            )

        if not axis_scores:
            return (
                MatchCandidate(
                    roi_id=roi.subject_id,
                    score=0.0,
                    payload={
                        "possible": False,
                        "skipped_reason": "no_comparable_axes",
                        "finding_laterality": _side_value(finding.side),
                        "roi_laterality": _side_value(roi.side),
                        "scored_axes": [],
                        "available_axes": {
                            "finding": sorted(finding.axis_values),
                            "roi": sorted(roi.axis_values),
                        },
                    },
                    evidence=evidence,
                ),
                False,
            )

        score = sum(1 for item in axis_scores if item["matched"]) / len(axis_scores)
        payload = {
            "possible": True,
            "finding_laterality": _side_value(finding.side),
            "roi_laterality": _side_value(roi.side),
            "scored_axes": [item["axis"] for item in axis_scores],
            "axis_scores": axis_scores,
            "matched_axis_count": sum(1 for item in axis_scores if item["matched"]),
            "scored_axis_count": len(axis_scores),
        }
        return (
            MatchCandidate(
                roi_id=roi.subject_id,
                score=score,
                payload=payload,
                evidence=evidence,
            ),
            score > self.minimum_score,
        )

    def _result_for_finding(
        self,
        *,
        finding: "_LocalizedSubject",
        matched_roi_id: Optional[str],
        candidates: list[MatchCandidate],
        unmatched_roi_ids: list[str],
    ) -> MatchingResult:
        warnings = _input_warnings(finding)
        if matched_roi_id is None:
            warnings.append(
                AuditWarning(
                    code="unmatched_finding",
                    message="No ROI was assigned to this finding.",
                    payload={"finding_id": finding.subject_id},
                )
            )
            status = ResultStatus.FAILED
        else:
            candidate = next(item for item in candidates if item.roi_id == matched_roi_id)
            if candidate.score < 1.0:
                warnings.append(
                    AuditWarning(
                        code="partial_axis_match",
                        message="The assigned ROI matched only a subset of scored axes.",
                        severity=WarningSeverity.INFO,
                        payload={
                            "finding_id": finding.subject_id,
                            "roi_id": matched_roi_id,
                            "score": candidate.score,
                            "scored_axes": candidate.payload.get("scored_axes", []),
                        },
                    )
                )
            status = ResultStatus.PARTIAL if warnings else ResultStatus.SUCCESS

        if unmatched_roi_ids:
            warnings.append(
                AuditWarning(
                    code="unmatched_rois",
                    message="One or more localized ROIs were not assigned to a finding.",
                    severity=WarningSeverity.INFO,
                    payload={"roi_ids": unmatched_roi_ids},
                )
            )
            if status is ResultStatus.SUCCESS:
                status = ResultStatus.PARTIAL

        return MatchingResult(
            status=status,
            finding_id=finding.subject_id,
            matched_roi_id=matched_roi_id,
            candidates=candidates,
            unmatched_roi_ids=unmatched_roi_ids,
            evidence=[
                Evidence(
                    kind="one_to_one_assignment",
                    source="finding_roi_matcher",
                    payload={
                        "finding_id": finding.subject_id,
                        "matched_roi_id": matched_roi_id,
                        "candidate_count": len(candidates),
                    },
                )
            ],
            warnings=warnings,
            metadata={
                "workflow": "finding_roi_matching",
                "axes": list(self.axes),
                "minimum_score": self.minimum_score,
            },
        )


@dataclass(frozen=True)
class _LocalizedSubject:
    subject_id: str
    subject_type: str
    side: Laterality
    axis_values: Mapping[AxisName, object]
    status: ResultStatus
    warning_codes: tuple[str, ...]
    anatomical_position: Mapping[str, object]
    continuous_position: Mapping[str, object]

    @classmethod
    def from_result(
        cls,
        result: LocalizationResult,
        *,
        default_subject_type: str,
    ) -> "_LocalizedSubject":
        return cls(
            subject_id=result.subject_id,
            subject_type=result.subject_type or default_subject_type,
            side=_extract_laterality(result),
            axis_values=_extract_axis_values(result),
            status=result.status,
            warning_codes=tuple(warning.code for warning in result.warnings),
            anatomical_position=dict(result.anatomical_position),
            continuous_position=dict(result.continuous_position),
        )

    def evidence_payload(self) -> Mapping[str, object]:
        return {
            "subject_id": self.subject_id,
            "subject_type": self.subject_type,
            "status": self.status.value,
            "laterality": _side_value(self.side),
            "axis_values": dict(self.axis_values),
            "warning_codes": list(self.warning_codes),
        }


@dataclass(frozen=True)
class _ViablePair:
    finding_id: str
    roi_id: str
    score: float
    axis_count: int


def _assign_one_to_one(pairs: Sequence[_ViablePair]) -> dict[str, str]:
    assignments: dict[str, str] = {}
    assigned_rois: set[str] = set()
    for pair in sorted(
        pairs,
        key=lambda item: (-item.score, -item.axis_count, item.finding_id, item.roi_id),
    ):
        if pair.finding_id in assignments or pair.roi_id in assigned_rois:
            continue
        assignments[pair.finding_id] = pair.roi_id
        assigned_rois.add(pair.roi_id)
    return assignments


def _input_warnings(subject: _LocalizedSubject) -> list[AuditWarning]:
    warnings: list[AuditWarning] = []
    if subject.status in {ResultStatus.FAILED, ResultStatus.SKIPPED}:
        warnings.append(
            AuditWarning(
                code="localization_not_matchable",
                message="Finding localization status does not support confident matching.",
                payload={
                    "subject_id": subject.subject_id,
                    "subject_type": subject.subject_type,
                    "status": subject.status.value,
                },
            )
        )
    elif subject.status is ResultStatus.PARTIAL:
        warnings.append(
            AuditWarning(
                code="partial_localization",
                message="Finding localization was partial; matching used available axes only.",
                severity=WarningSeverity.INFO,
                payload={
                    "subject_id": subject.subject_id,
                    "subject_type": subject.subject_type,
                    "warning_codes": list(subject.warning_codes),
                },
            )
        )
    return warnings


def _side_mismatch_reason(
    finding_side: Laterality,
    roi_side: Laterality,
) -> Optional[str]:
    if finding_side in _MATCHABLE_SIDES and roi_side in _MATCHABLE_SIDES:
        if finding_side is not roi_side:
            return "side_mismatch"
    return None


def _extract_laterality(result: LocalizationResult) -> Laterality:
    anatomical = result.anatomical_position
    continuous = result.continuous_position
    quadrant = anatomical.get("quadrant")
    candidates = [
        anatomical.get("laterality"),
        quadrant.get("laterality") if isinstance(quadrant, Mapping) else None,
        continuous.get("laterality"),
    ]
    for value in candidates:
        side = Laterality.coerce(value)
        if side is not Laterality.UNKNOWN:
            return side
    return Laterality.UNKNOWN


def _extract_axis_values(result: LocalizationResult) -> Mapping[AxisName, object]:
    anatomical = result.anatomical_position
    quadrant = anatomical.get("quadrant")
    if not isinstance(quadrant, Mapping):
        return {}

    axis_values = {}
    for axis in ("ml", "si", "depth"):
        value = quadrant.get(axis)
        if not _is_unknown_axis_value(value):
            axis_values[axis] = value
    return axis_values


def _is_unknown_axis_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _UNKNOWN_AXIS_VALUES
    return False


def _side_value(side: Laterality) -> str:
    return side.value
