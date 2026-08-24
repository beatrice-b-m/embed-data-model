"""Scoped finding-to-ROI-group inference using anatomical localization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from embed_toolkit.audit.evidence import AuditWarning, Evidence, WarningSeverity
from embed_toolkit.audit.results import (
    AttributionState,
    LocalizationResult,
    MatchCandidate,
    MatchingResult,
    ResultStatus,
)
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.imaging.roi_groups import RoiGroup


AxisName = str
_UNKNOWN_AXIS_VALUES = {"", "unknown", "UNKNOWN", None}


@dataclass(frozen=True)
class FindingRoiMatcher:
    """Infer finding attribution to lesion-level ROI groups within one scope."""

    axes: tuple[AxisName, ...] = ("ml", "si", "depth")
    minimum_score: float = 0.5
    minimum_margin: float = 0.1
    algorithm_version: str = "finding-roi-inference-v2"
    configuration_version: str = "default-v1"

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_score <= 1.0:
            raise ValueError("minimum_score must be in [0, 1]")
        if not 0.0 <= self.minimum_margin <= 1.0:
            raise ValueError("minimum_margin must be in [0, 1]")

    def match(
        self,
        findings: Iterable[LocalizationResult],
        rois: Iterable[LocalizationResult],
        *,
        accession_number: str,
        breast_side: Laterality,
        roi_groups: Optional[Iterable[RoiGroup]] = None,
    ) -> list[MatchingResult]:
        """Infer attributions within exactly one accession and unilateral side."""

        side = Laterality.coerce(breast_side)
        if not accession_number:
            raise ValueError("Matching requires one accession_number scope")
        if not side.is_unilateral:
            raise ValueError("Matching requires one unilateral breast_side scope")

        finding_positions = sorted(
            (
                _LocalizedSubject.from_result(item, default_subject_type="finding")
                for item in findings
            ),
            key=lambda item: item.subject_id,
        )
        roi_positions = {
            item.subject_id: item
            for item in (
                _LocalizedSubject.from_result(result, default_subject_type="roi")
                for result in rois
            )
        }
        _validate_subject_scope(finding_positions, accession_number, side)
        _validate_subject_scope(roi_positions.values(), accession_number, side)
        groups = _resolve_groups(
            roi_positions,
            roi_groups,
            accession_number=accession_number,
            breast_side=side,
        )

        candidates_by_finding = {
            finding.subject_id: sorted(
                (self._group_candidate(finding, group, roi_positions) for group in groups),
                key=_candidate_rank,
            )
            for finding in finding_positions
        }
        decisions = (
            self._singleton_decisions(finding_positions, candidates_by_finding)
            if len(finding_positions) == 1
            else self._multifinding_decisions(finding_positions, candidates_by_finding)
        )
        attributed_roi_ids = {
            roi_id
            for decision in decisions.values()
            for roi_id in decision.matched_roi_ids
        }
        unmatched_roi_ids = sorted(set(roi_positions) - attributed_roi_ids)

        return [
            self._result_for_finding(
                finding,
                candidates_by_finding[finding.subject_id],
                decisions[finding.subject_id],
                unmatched_roi_ids,
                accession_number,
                side,
            )
            for finding in finding_positions
        ]

    def _group_candidate(
        self,
        finding: "_LocalizedSubject",
        group: "_Group",
        roi_positions: Mapping[str, "_LocalizedSubject"],
    ) -> MatchCandidate:
        member_scores = [
            _score_axes(finding, roi_positions[roi_id], self.axes)
            for roi_id in group.roi_ids
        ]
        scored = [item for item in member_scores if item is not None]
        if not scored:
            return MatchCandidate(
                roi_id=group.group_id,
                score=0.0,
                payload={
                    "possible": False,
                    "skipped_reason": "no_comparable_axes",
                    "roi_group_id": group.group_id,
                    "roi_ids": list(group.roi_ids),
                    "scored_axes": [],
                },
                evidence=_candidate_evidence(finding, group, roi_positions),
            )

        best = sorted(
            scored,
            key=lambda item: (-item.score, -len(item.axis_scores), item.roi_id),
        )[0]
        return MatchCandidate(
            roi_id=group.group_id,
            score=best.score,
            payload={
                "possible": True,
                "roi_group_id": group.group_id,
                "roi_ids": list(group.roi_ids),
                "representative_roi_id": best.roi_id,
                "scored_axes": [item["axis"] for item in best.axis_scores],
                "axis_scores": list(best.axis_scores),
                "matched_axis_count": sum(
                    1 for item in best.axis_scores if item["matched"]
                ),
                "scored_axis_count": len(best.axis_scores),
            },
            evidence=_candidate_evidence(finding, group, roi_positions),
        )

    def _singleton_decisions(
        self,
        findings: list["_LocalizedSubject"],
        candidates_by_finding: Mapping[str, list[MatchCandidate]],
    ) -> dict[str, "_Decision"]:
        if not findings:
            return {}
        finding = findings[0]
        candidates = candidates_by_finding[finding.subject_id]
        accepted = [candidate for candidate in candidates if self._accepted(candidate)]
        if not accepted:
            return {finding.subject_id: _abstained_decision(candidates)}
        return {
            finding.subject_id: _Decision(
                state=AttributionState.INFERRED,
                matched_group_ids=tuple(item.roi_id for item in accepted),
                matched_roi_ids=tuple(
                    roi_id
                    for item in accepted
                    for roi_id in item.payload.get("roi_ids", [])
                ),
                score=accepted[0].score,
                margin=_score_margin(candidates),
            )
        }

    def _multifinding_decisions(
        self,
        findings: list["_LocalizedSubject"],
        candidates_by_finding: Mapping[str, list[MatchCandidate]],
    ) -> dict[str, "_Decision"]:
        decisions: dict[str, _Decision] = {}
        proposals: list[tuple[float, int, str, MatchCandidate, Optional[float]]] = []
        for finding in findings:
            candidates = candidates_by_finding[finding.subject_id]
            viable = [candidate for candidate in candidates if self._accepted(candidate)]
            if not viable:
                decisions[finding.subject_id] = _abstained_decision(candidates)
                continue
            margin = _score_margin(viable)
            if len(viable) > 1 and margin is not None and margin < self.minimum_margin:
                decisions[finding.subject_id] = _Decision(
                    state=AttributionState.AMBIGUOUS,
                    score=viable[0].score,
                    margin=margin,
                )
                continue
            top = viable[0]
            proposals.append(
                (
                    -top.score,
                    -len(top.payload.get("scored_axes", [])),
                    finding.subject_id,
                    top,
                    margin,
                )
            )

        claimed_groups: set[str] = set()
        for _, _, finding_id, candidate, margin in sorted(proposals):
            if candidate.roi_id in claimed_groups:
                decisions[finding_id] = _Decision(
                    state=AttributionState.ABSTAINED,
                    score=candidate.score,
                    margin=margin,
                    conflict_group_id=candidate.roi_id,
                )
                continue
            claimed_groups.add(candidate.roi_id)
            decisions[finding_id] = _Decision(
                state=AttributionState.INFERRED,
                matched_group_ids=(candidate.roi_id,),
                matched_roi_ids=tuple(candidate.payload.get("roi_ids", [])),
                score=candidate.score,
                margin=margin,
            )
        return decisions

    def _accepted(self, candidate: MatchCandidate) -> bool:
        return bool(candidate.payload.get("possible")) and candidate.score >= self.minimum_score

    def _result_for_finding(
        self,
        finding: "_LocalizedSubject",
        candidates: list[MatchCandidate],
        decision: "_Decision",
        unmatched_roi_ids: list[str],
        accession_number: str,
        breast_side: Laterality,
    ) -> MatchingResult:
        warnings = _input_warnings(finding)
        if decision.state is AttributionState.AMBIGUOUS:
            warnings.append(
                AuditWarning(
                    code="ambiguous_attribution",
                    message="Top ROI-group candidates were not separated by the configured margin.",
                    payload={"score_margin": decision.margin},
                )
            )
        elif decision.state is AttributionState.ABSTAINED:
            warnings.append(
                AuditWarning(
                    code="attribution_abstained",
                    message="The inference policy did not accept an ROI attribution.",
                    payload={"conflict_group_id": decision.conflict_group_id},
                )
            )
        if unmatched_roi_ids:
            warnings.append(
                AuditWarning(
                    code="unmatched_rois",
                    message="One or more scoped ROIs were not attributed.",
                    severity=WarningSeverity.INFO,
                    payload={"roi_ids": unmatched_roi_ids},
                )
            )

        observed = dict(finding.axis_values)
        scored_axes = (
            list(candidates[0].payload.get("scored_axes", [])) if candidates else []
        )
        return MatchingResult(
            status=ResultStatus.SUCCESS,
            finding_id=finding.subject_id,
            matched_roi_ids=list(decision.matched_roi_ids),
            matched_roi_group_ids=list(decision.matched_group_ids),
            candidates=candidates,
            unmatched_roi_ids=unmatched_roi_ids,
            attribution_state=decision.state,
            score=decision.score,
            score_margin=decision.margin,
            observed_descriptors=observed,
            scored_descriptors=scored_axes,
            algorithm_version=self.algorithm_version,
            configuration_version=self.configuration_version,
            evidence=[
                Evidence(
                    kind="inferred_roi_group_attribution",
                    source=self.algorithm_version,
                    payload={
                        "accession_number": accession_number,
                        "breast_side": breast_side.value,
                        "finding_id": finding.subject_id,
                        "matched_roi_group_ids": list(decision.matched_group_ids),
                        "matched_roi_ids": list(decision.matched_roi_ids),
                    },
                )
            ],
            warnings=warnings,
            metadata={
                "workflow": "finding_roi_matching",
                "accession_number": accession_number,
                "breast_side": breast_side.value,
                "axes": list(self.axes),
                "minimum_score": self.minimum_score,
                "minimum_margin": self.minimum_margin,
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
    metadata: Mapping[str, object]

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
            metadata=dict(result.metadata),
        )

    def evidence_payload(self) -> Mapping[str, object]:
        return {
            "subject_id": self.subject_id,
            "subject_type": self.subject_type,
            "status": self.status.value,
            "laterality": self.side.value,
            "axis_values": dict(self.axis_values),
            "warning_codes": list(self.warning_codes),
        }


@dataclass(frozen=True)
class _Group:
    group_id: str
    roi_ids: tuple[str, ...]
    grouping_basis: str


@dataclass(frozen=True)
class _AxisScore:
    roi_id: str
    score: float
    axis_scores: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class _Decision:
    state: AttributionState
    matched_group_ids: tuple[str, ...] = ()
    matched_roi_ids: tuple[str, ...] = ()
    score: Optional[float] = None
    margin: Optional[float] = None
    conflict_group_id: Optional[str] = None


def _resolve_groups(
    roi_positions: Mapping[str, _LocalizedSubject],
    roi_groups: Optional[Iterable[RoiGroup]],
    *,
    accession_number: str,
    breast_side: Laterality,
) -> list[_Group]:
    if roi_groups is None:
        return [
            _Group(f"group:{roi_id}", (roi_id,), "singleton")
            for roi_id in sorted(roi_positions)
        ]
    groups = []
    represented: set[str] = set()
    for group in roi_groups:
        if group.accession_number != accession_number or group.laterality is not breast_side:
            raise ValueError("ROI group is outside the requested accession-side scope")
        missing = set(group.roi_ids) - set(roi_positions)
        if missing:
            raise ValueError(f"ROI group references unlocalized ROIs: {sorted(missing)}")
        overlap = represented.intersection(group.roi_ids)
        if overlap:
            raise ValueError(f"ROIs cannot belong to multiple groups: {sorted(overlap)}")
        represented.update(group.roi_ids)
        groups.append(_Group(group.group_id, group.roi_ids, group.grouping_basis))
    for roi_id in sorted(set(roi_positions) - represented):
        groups.append(_Group(f"group:{roi_id}", (roi_id,), "singleton"))
    return sorted(groups, key=lambda item: item.group_id)


def _validate_subject_scope(
    subjects: Iterable[_LocalizedSubject],
    accession_number: str,
    breast_side: Laterality,
) -> None:
    for subject in subjects:
        metadata_accession = subject.metadata.get("accession_number")
        if metadata_accession is not None and metadata_accession != accession_number:
            raise ValueError(f"Subject {subject.subject_id} is outside accession scope")
        if subject.side.is_unilateral and subject.side is not breast_side:
            raise ValueError(f"Subject {subject.subject_id} is outside breast-side scope")


def _score_axes(
    finding: _LocalizedSubject,
    roi: _LocalizedSubject,
    axes: tuple[AxisName, ...],
) -> Optional[_AxisScore]:
    axis_scores = []
    for axis in axes:
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
        return None
    score = sum(1 for item in axis_scores if item["matched"]) / len(axis_scores)
    return _AxisScore(roi.subject_id, score, tuple(axis_scores))


def _candidate_evidence(
    finding: _LocalizedSubject,
    group: _Group,
    roi_positions: Mapping[str, _LocalizedSubject],
) -> list[Evidence]:
    return [
        Evidence(
            kind="localized_finding",
            source="finding_roi_matcher",
            payload=finding.evidence_payload(),
        ),
        Evidence(
            kind="localized_roi_group",
            source="finding_roi_matcher",
            payload={
                "roi_group_id": group.group_id,
                "roi_ids": list(group.roi_ids),
                "grouping_basis": group.grouping_basis,
                "members": [
                    roi_positions[roi_id].evidence_payload() for roi_id in group.roi_ids
                ],
            },
        ),
    ]


def _candidate_rank(candidate: MatchCandidate) -> tuple[float, int, str]:
    return (
        -candidate.score,
        -len(candidate.payload.get("scored_axes", [])),
        candidate.roi_id,
    )


def _score_margin(candidates: list[MatchCandidate]) -> Optional[float]:
    possible = [item for item in candidates if item.payload.get("possible")]
    if len(possible) < 2:
        return None
    return possible[0].score - possible[1].score


def _abstained_decision(candidates: list[MatchCandidate]) -> _Decision:
    return _Decision(
        state=AttributionState.ABSTAINED,
        score=candidates[0].score if candidates else None,
        margin=_score_margin(candidates),
    )


def _input_warnings(subject: _LocalizedSubject) -> list[AuditWarning]:
    if subject.status in {ResultStatus.FAILED, ResultStatus.SKIPPED}:
        return [
            AuditWarning(
                code="localization_not_matchable",
                message="Finding localization status limits attribution evidence.",
                payload={"status": subject.status.value},
            )
        ]
    if subject.status is ResultStatus.PARTIAL:
        return [
            AuditWarning(
                code="partial_localization",
                message="Inference used only observable localization axes.",
                severity=WarningSeverity.INFO,
                payload={"warning_codes": list(subject.warning_codes)},
            )
        ]
    return []


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
    quadrant = result.anatomical_position.get("quadrant")
    if not isinstance(quadrant, Mapping):
        return {}
    return {
        axis: value
        for axis in ("ml", "si", "depth")
        if not _is_unknown_axis_value(value := quadrant.get(axis))
    }


def _is_unknown_axis_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _UNKNOWN_AXIS_VALUES
    return False
