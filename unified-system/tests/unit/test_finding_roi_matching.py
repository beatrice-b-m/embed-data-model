from __future__ import annotations

import json

import pytest

from embed_toolkit.audit.results import (
    AttributionState,
    LocalizationResult,
    ResultStatus,
)
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.roi_provenance import RoiLocator
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
    locator = roi_locator(subject_id) if subject_type == "roi" else None
    return LocalizationResult(
        status=status,
        subject_id="" if locator is not None else subject_id,
        subject_type=subject_type,
        roi_locator=locator,
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


def roi_locator(value: str) -> RoiLocator:
    return RoiLocator.from_source(
        image_locator=SourceLocator(
            scope="finding-roi-tests",
            scope_kind=SourceScopeKind.MATERIALIZATION,
            source_profile="test",
            source_table="images",
            source_key=f"image:{value}",
        ),
        source_value=value,
    )


def warning_codes(result: object) -> set[str]:
    return {warning.code for warning in result.warnings}


def candidate_for(result: object, locator: RoiLocator) -> object:
    return next(
        candidate
        for candidate in result.candidates
        if locator in candidate.roi_locators
    )


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

    result = FindingRoiMatcher().match(
        [finding], [roi], accession_number="ACC-1", breast_side="L"
    )[0]
    serialized = result.to_dict()

    assert result.status is ResultStatus.SUCCESS
    assert result.finding_id == "finding-1"
    assert result.matched_roi_locators == (roi_locator("roi-1"),)
    assert result.attribution_state is AttributionState.INFERRED
    assert serialized["candidates"][0]["score"] == 1.0
    assert serialized["candidates"][0]["payload"]["scored_axes"] == [
        "ml",
        "si",
        "depth",
    ]
    assert serialized["evidence"][0]["kind"] == "inferred_roi_group_attribution"
    json.dumps(serialized)


def test_exact_side_mismatch_is_not_assignable_but_remains_inspectable() -> None:
    finding = localized("finding-left", "finding", "L", ml="lateral")
    roi = localized("roi-right", "roi", "R", ml="lateral")

    with pytest.raises(ValueError, match="breast-side scope"):
        FindingRoiMatcher().match(
            [finding], [roi], accession_number="ACC-1", breast_side="L"
        )


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

    result = FindingRoiMatcher().match(
        [finding], [roi], accession_number="ACC-1", breast_side="R"
    )[0]
    candidate = result.candidates[0]

    assert result.matched_roi_locators == (roi_locator("roi-partial"),)
    assert result.status is ResultStatus.SUCCESS
    assert candidate.score == 1.0
    assert candidate.payload["scored_axes"] == ("ml",)
    assert candidate.payload["axis_scores"] == (
        {
            "axis": "ml",
            "finding_value": "medial",
            "roi_value": "medial",
            "matched": True,
        },
    )
    assert "partial_localization" in warning_codes(result)


def test_one_to_one_assignment_keeps_best_pair_and_reports_unmatched_finding() -> None:
    findings = [
        localized("finding-a", "finding", "L", ml="lateral", si="superior"),
        localized("finding-b", "finding", "L", ml="lateral", si="inferior"),
    ]
    rois = [
        localized("roi-1", "roi", "L", ml="lateral", si="superior"),
    ]

    results = FindingRoiMatcher().match(
        findings, rois, accession_number="ACC-1", breast_side="L"
    )

    assert [result.finding_id for result in results] == ["finding-a", "finding-b"]
    assert results[0].matched_roi_locators == (roi_locator("roi-1"),)
    assert results[0].status is ResultStatus.SUCCESS
    assert results[1].matched_roi_locators == ()
    assert results[1].status is ResultStatus.SUCCESS
    assert results[1].attribution_state is AttributionState.ABSTAINED
    assert "attribution_abstained" in warning_codes(results[1])


def test_unmatched_rois_are_reported_after_assignment() -> None:
    finding = localized("finding-1", "finding", "R", depth="anterior")
    rois = [
        localized("roi-a", "roi", "R", depth="anterior"),
        localized("roi-b", "roi", "R", depth="posterior"),
    ]

    result = FindingRoiMatcher().match(
        [finding], rois, accession_number="ACC-1", breast_side="R"
    )[0]

    assert result.matched_roi_locators == (roi_locator("roi-a"),)
    assert result.unmatched_roi_locators == (roi_locator("roi-b"),)
    assert result.status is ResultStatus.SUCCESS
    assert "unmatched_rois" in warning_codes(result)


def test_singleton_policy_associates_all_compatible_rois() -> None:
    finding = localized("finding-1", "finding", "L", ml="central")
    rois = [
        localized("roi-b", "roi", "L", ml="central"),
        localized("roi-a", "roi", "L", ml="central"),
    ]

    result = FindingRoiMatcher().match(
        [finding], rois, accession_number="ACC-1", breast_side="L"
    )[0]

    assert result.matched_roi_locators == (
        roi_locator("roi-a"),
        roi_locator("roi-b"),
    )
    assert all(
        candidate.candidate_id.startswith("singleton:")
        for candidate in result.candidates
    )


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

    with pytest.raises(ValueError, match="breast-side scope"):
        FindingRoiMatcher().match(
            [finding], rois, accession_number="ACC-1", breast_side="L"
        )


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

    results = FindingRoiMatcher().match(
        findings, rois, accession_number="ACC-1", breast_side="R"
    )

    assert [result.finding_id for result in results] == [
        "finding-lower",
        "finding-upper",
    ]
    assert [result.matched_roi_locators for result in results] == [
        (roi_locator("roi-lower"),),
        (roi_locator("roi-upper"),),
    ]
    assert [result.unmatched_roi_locators for result in results] == [
        (roi_locator("roi-extra"),),
        (roi_locator("roi-extra"),),
    ]
    assert [result.roi_locators_attributed_to_other_findings for result in results] == [
        (roi_locator("roi-upper"),),
        (roi_locator("roi-lower"),),
    ]
    assert all(result.status is ResultStatus.SUCCESS for result in results)
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

    result = FindingRoiMatcher().match(
        [finding], rois, accession_number="ACC-1", breast_side="L"
    )[0]
    scored = candidate_for(result, roi_locator("roi-cc-observable"))
    unscored = candidate_for(result, roi_locator("roi-no-overlap"))

    assert result.matched_roi_locators == (roi_locator("roi-cc-observable"),)
    assert scored.score == 0.5
    assert scored.payload["possible"] is True
    assert scored.payload["scored_axes"] == ("ml", "depth")
    assert scored.payload["matched_axis_count"] == 1
    assert scored.scored_axis_count == 2
    assert unscored.payload["possible"] is False
    assert unscored.payload["skipped_reason"] == "no_comparable_axes"


def test_matching_rejects_duplicate_finding_and_roi_identities() -> None:
    finding = localized("finding-1", "finding", "L", ml="lateral")
    observed = localized("roi-1", "roi", "L", ml="lateral")
    matcher = FindingRoiMatcher()

    with pytest.raises(ValueError, match="subject IDs must be unique"):
        matcher.match(
            [finding, finding],
            [observed],
            accession_number="ACC-1",
            breast_side="L",
        )
    with pytest.raises(ValueError, match="locators must be unique"):
        matcher.match(
            [finding],
            [observed, observed],
            accession_number="ACC-1",
            breast_side="L",
        )


def test_matching_is_deterministic_under_reversed_input_order() -> None:
    findings = [
        localized("finding-b", "finding", "R", si="inferior"),
        localized("finding-a", "finding", "R", si="superior"),
    ]
    rois = [
        localized("roi-b", "roi", "R", si="inferior"),
        localized("roi-a", "roi", "R", si="superior"),
    ]
    matcher = FindingRoiMatcher()

    forward = matcher.match(
        findings,
        rois,
        accession_number="ACC-1",
        breast_side="R",
    )
    reversed_inputs = matcher.match(
        reversed(findings),
        reversed(rois),
        accession_number="ACC-1",
        breast_side="R",
    )

    assert [result.to_dict() for result in forward] == [
        result.to_dict() for result in reversed_inputs
    ]


def test_equal_scores_rank_by_typed_scored_axis_count() -> None:
    finding = localized(
        "finding-1",
        "finding",
        "L",
        ml="lateral",
        si="superior",
    )
    one_axis = localized("roi-one", "roi", "L", ml="lateral")
    two_axes = localized(
        "roi-two",
        "roi",
        "L",
        ml="lateral",
        si="superior",
    )
    matcher = FindingRoiMatcher()

    forward = matcher.match(
        [finding],
        [one_axis, two_axes],
        accession_number="ACC-1",
        breast_side="L",
    )[0]
    reverse = matcher.match(
        [finding],
        [two_axes, one_axis],
        accession_number="ACC-1",
        breast_side="L",
    )[0]

    assert [candidate.scored_axis_count for candidate in forward.candidates] == [2, 1]
    assert [candidate.candidate_id for candidate in forward.candidates] == [
        candidate.candidate_id for candidate in reverse.candidates
    ]
    assert forward.to_dict() == reverse.to_dict()
