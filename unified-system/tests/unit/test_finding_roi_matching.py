from __future__ import annotations

import json

from embed_toolkit.audit.results import LocalizationResult, ResultStatus
from embed_toolkit.workflows.finding_roi_matching import FindingRoiMatcher


def localized(
    subject_id: str,
    subject_type: str,
    laterality: str,
    *,
    ml: str = "unknown",
    si: str = "unknown",
    depth: str = "unknown",
    status: ResultStatus = ResultStatus.SUCCESS,
) -> LocalizationResult:
    return LocalizationResult(
        status=status,
        subject_id=subject_id,
        subject_type=subject_type,
        anatomical_position={
            "laterality": laterality,
            "quadrant": {
                "laterality": laterality,
                "ml": ml,
                "si": si,
                "depth": depth,
            },
        },
    )


def warning_codes(result: object) -> set[str]:
    return {warning.code for warning in result.warnings}


def candidate_for(result: object, roi_id: str) -> object:
    return next(candidate for candidate in result.candidates if candidate.roi_id == roi_id)


def test_same_side_matching_scores_axes_and_returns_structured_result() -> None:
    finding = localized(
        "finding-1",
        "finding",
        "L",
        ml="lateral",
        si="superior",
        depth="posterior",
    )
    roi = localized(
        "roi-1",
        "roi",
        "L",
        ml="lateral",
        si="superior",
        depth="posterior",
    )

    result = FindingRoiMatcher().match([finding], [roi])[0]
    serialized = result.to_dict()

    assert result.status is ResultStatus.SUCCESS
    assert result.finding_id == "finding-1"
    assert result.matched_roi_id == "roi-1"
    assert serialized["candidates"][0]["score"] == 1.0
    assert serialized["candidates"][0]["payload"]["scored_axes"] == ["ml", "si", "depth"]
    assert serialized["evidence"][0]["kind"] == "one_to_one_assignment"
    json.dumps(serialized)


def test_exact_side_mismatch_is_not_assignable_but_remains_inspectable() -> None:
    finding = localized("finding-left", "finding", "L", ml="lateral")
    roi = localized("roi-right", "roi", "R", ml="lateral")

    result = FindingRoiMatcher().match([finding], [roi])[0]
    candidate = result.candidates[0]

    assert result.status is ResultStatus.FAILED
    assert result.matched_roi_id is None
    assert result.unmatched_roi_ids == ["roi-right"]
    assert candidate.score == 0.0
    assert candidate.payload["possible"] is False
    assert candidate.payload["skipped_reason"] == "side_mismatch"
    assert "unmatched_finding" in warning_codes(result)


def test_partial_axis_scoring_uses_only_axes_available_on_both_inputs() -> None:
    finding = localized(
        "finding-partial",
        "finding",
        "R",
        ml="medial",
        si="superior",
        depth="unknown",
        status=ResultStatus.PARTIAL,
    )
    roi = localized(
        "roi-partial",
        "roi",
        "R",
        ml="medial",
        si="unknown",
        depth="posterior",
    )

    result = FindingRoiMatcher().match([finding], [roi])[0]
    candidate = result.candidates[0]

    assert result.matched_roi_id == "roi-partial"
    assert result.status is ResultStatus.PARTIAL
    assert candidate.score == 1.0
    assert candidate.payload["scored_axes"] == ["ml"]
    assert candidate.payload["axis_scores"] == [
        {
            "axis": "ml",
            "finding_value": "medial",
            "roi_value": "medial",
            "matched": True,
        }
    ]
    assert "partial_localization" in warning_codes(result)


def test_one_to_one_assignment_keeps_best_pair_and_reports_unmatched_finding() -> None:
    findings = [
        localized("finding-a", "finding", "L", ml="lateral", si="superior"),
        localized("finding-b", "finding", "L", ml="lateral", si="inferior"),
    ]
    rois = [
        localized("roi-1", "roi", "L", ml="lateral", si="superior"),
    ]

    results = FindingRoiMatcher().match(findings, rois)

    assert [result.finding_id for result in results] == ["finding-a", "finding-b"]
    assert results[0].matched_roi_id == "roi-1"
    assert results[0].status is ResultStatus.SUCCESS
    assert results[1].matched_roi_id is None
    assert results[1].status is ResultStatus.FAILED
    assert "unmatched_finding" in warning_codes(results[1])


def test_unmatched_rois_are_reported_after_assignment() -> None:
    finding = localized("finding-1", "finding", "R", depth="anterior")
    rois = [
        localized("roi-a", "roi", "R", depth="anterior"),
        localized("roi-b", "roi", "R", depth="posterior"),
    ]

    result = FindingRoiMatcher().match([finding], rois)[0]

    assert result.matched_roi_id == "roi-a"
    assert result.unmatched_roi_ids == ["roi-b"]
    assert result.status is ResultStatus.PARTIAL
    assert "unmatched_rois" in warning_codes(result)


def test_deterministic_tie_breaking_prefers_lower_roi_id() -> None:
    finding = localized("finding-1", "finding", "L", ml="central")
    rois = [
        localized("roi-b", "roi", "L", ml="central"),
        localized("roi-a", "roi", "L", ml="central"),
    ]

    result = FindingRoiMatcher().match([finding], rois)[0]

    assert result.matched_roi_id == "roi-a"
    assert [candidate.roi_id for candidate in result.candidates] == ["roi-a", "roi-b"]


def test_legacy_parity_side_mismatch_cannot_win_over_same_side_candidate() -> None:
    finding = localized(
        "finding-left",
        "finding",
        "L",
        ml="lateral",
        si="superior",
        depth="posterior",
    )
    rois = [
        localized(
            "roi-right-perfect-location",
            "roi",
            "R",
            ml="lateral",
            si="superior",
            depth="posterior",
        ),
        localized(
            "roi-left-partial-location",
            "roi",
            "L",
            ml="lateral",
            si="inferior",
            depth="posterior",
        ),
    ]

    result = FindingRoiMatcher().match([finding], rois)[0]
    side_mismatch = candidate_for(result, "roi-right-perfect-location")
    same_side = candidate_for(result, "roi-left-partial-location")

    assert result.matched_roi_id == "roi-left-partial-location"
    assert result.unmatched_roi_ids == ["roi-right-perfect-location"]
    assert same_side.payload["possible"] is True
    assert same_side.score == 2 / 3
    assert side_mismatch.score == 0.0
    assert side_mismatch.payload["possible"] is False
    assert side_mismatch.payload["skipped_reason"] == "side_mismatch"


def test_legacy_parity_one_to_one_assignment_reports_unclaimed_rois_globally() -> None:
    findings = [
        localized("finding-upper", "finding", "R", si="superior", depth="posterior"),
        localized("finding-lower", "finding", "R", si="inferior", depth="anterior"),
    ]
    rois = [
        localized("roi-upper", "roi", "R", si="superior", depth="posterior"),
        localized("roi-lower", "roi", "R", si="inferior", depth="anterior"),
        localized("roi-extra", "roi", "R", si="central", depth="middle"),
    ]

    results = FindingRoiMatcher().match(findings, rois)

    assert [result.finding_id for result in results] == [
        "finding-lower",
        "finding-upper",
    ]
    assert [result.matched_roi_id for result in results] == ["roi-lower", "roi-upper"]
    assert [result.unmatched_roi_ids for result in results] == [
        ["roi-extra"],
        ["roi-extra"],
    ]
    assert all(result.status is ResultStatus.PARTIAL for result in results)
    assert all("unmatched_rois" in warning_codes(result) for result in results)


def test_legacy_parity_scoring_does_not_require_every_anatomical_axis() -> None:
    finding = localized(
        "finding-cc-observable",
        "finding",
        "L",
        ml="medial",
        si="superior",
        depth="middle",
    )
    rois = [
        localized(
            "roi-cc-observable",
            "roi",
            "L",
            ml="medial",
            si="unknown",
            depth="posterior",
        ),
        localized(
            "roi-no-overlap",
            "roi",
            "L",
            ml="unknown",
            si="unknown",
            depth="unknown",
        ),
    ]

    result = FindingRoiMatcher().match([finding], rois)[0]
    scored = candidate_for(result, "roi-cc-observable")
    unscored = candidate_for(result, "roi-no-overlap")

    assert result.matched_roi_id == "roi-cc-observable"
    assert scored.score == 0.5
    assert scored.payload["possible"] is True
    assert scored.payload["scored_axes"] == ["ml", "depth"]
    assert scored.payload["matched_axis_count"] == 1
    assert scored.payload["scored_axis_count"] == 2
    assert unscored.payload["possible"] is False
    assert unscored.payload["skipped_reason"] == "no_comparable_axes"
