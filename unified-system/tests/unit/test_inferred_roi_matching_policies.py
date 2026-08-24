from __future__ import annotations

import pytest

from embed_toolkit.audit.results import (
    AttributionState,
    LocalizationResult,
    ResultStatus,
)
from embed_toolkit.core.primitives import ImageModality
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.roi_groups import RoiGroup
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocator,
    RoiSourceCount,
    RoiSourceCountBasis,
    RoiSourceProvenance,
)
from embed_toolkit.imaging.rois import RegionOfInterest
from embed_toolkit.workflows.finding_roi_matching import FindingRoiMatcher


def localized(
    subject_id: str,
    subject_type: str,
    side: str,
    *,
    ml: str = "unknown",
    si: str = "unknown",
    depth: str = "unknown",
    accession_number: str = "ACC-1",
) -> LocalizationResult:
    locator = roi_locator(subject_id) if subject_type == "roi" else None
    return LocalizationResult(
        subject_id="" if locator is not None else subject_id,
        subject_type=subject_type,
        roi_locator=locator,
        anatomical_position={
            "laterality": side,
            "quadrant": {
                "laterality": side,
                "ml": ml,
                "si": si,
                "depth": depth,
            },
        },
        metadata={"accession_number": accession_number},
    )


def roi_locator(value: str) -> RoiLocator:
    return RoiLocator.from_source(
        image_locator=SourceLocator(
            scope="inferred-matching-tests",
            scope_kind=SourceScopeKind.MATERIALIZATION,
            source_profile="test",
            source_table="images",
            source_key=f"image:{value}",
        ),
        source_value=value,
    )


def domain_roi(
    value: str, image_id: str, coordinates: tuple[int, int, int, int]
) -> RegionOfInterest:
    locator = roi_locator(value)
    return RegionOfInterest(
        coordinates,
        locator=locator,
        image_id=image_id,
        source_provenance=RoiSourceProvenance(
            modality=ImageModality.FFDM,
            source_count=RoiSourceCount(
                1,
                RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE,
            ),
            depth_frame_provenance=RoiDepthFrameProvenance.NOT_APPLICABLE_2D,
        ),
        sources=(locator.image_locator,),
    )


def test_singleton_finding_accepts_all_compatible_groups_and_roi_locators() -> None:
    finding = localized("finding-1", "finding", "L", ml="lateral", depth="posterior")
    rois = [
        localized("roi-cc", "roi", "L", ml="lateral", depth="posterior"),
        localized("roi-mlo", "roi", "L", ml="lateral", depth="posterior"),
        localized("roi-extra", "roi", "L", ml="lateral", depth="posterior"),
    ]
    group = RoiGroup(
        group_id="lesion-cross-view",
        accession_number="ACC-1",
        laterality="L",
        rois=(
            domain_roi("roi-cc", "img-cc", (0, 0, 1, 1)),
            domain_roi("roi-mlo", "img-mlo", (1, 1, 2, 2)),
        ),
        grouping_basis="reviewed_cross_view",
    )

    result = FindingRoiMatcher().match(
        [finding],
        rois,
        accession_number="ACC-1",
        breast_side="L",
        roi_groups=[group],
    )[0]

    assert result.status is ResultStatus.SUCCESS
    assert result.attribution_state is AttributionState.INFERRED
    assert result.attribution_basis == "inferred"
    assert "lesion-cross-view" in result.matched_roi_group_ids
    assert result.matched_roi_locators == tuple(
        sorted(
            (
                roi_locator("roi-extra"),
                roi_locator("roi-cc"),
                roi_locator("roi-mlo"),
            ),
            key=lambda locator: str(locator.to_dict()),
        )
    )
    assert result.unmatched_roi_locators == ()
    assert result.algorithm_version == "finding-roi-inference-v2"


def test_multifinding_policy_ranks_groups_deterministically() -> None:
    findings = [
        localized("finding-lower", "finding", "R", si="inferior", depth="anterior"),
        localized("finding-upper", "finding", "R", si="superior", depth="posterior"),
    ]
    rois = [
        localized("roi-upper", "roi", "R", si="superior", depth="posterior"),
        localized("roi-lower", "roi", "R", si="inferior", depth="anterior"),
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
    assert all(
        result.attribution_state is AttributionState.INFERRED for result in results
    )
    assert all(result.score == 1.0 for result in results)


def test_tied_multifinding_candidates_are_ambiguous_not_ground_truth() -> None:
    findings = [
        localized("finding-a", "finding", "L", ml="lateral"),
        localized("finding-b", "finding", "L", ml="lateral"),
    ]
    rois = [
        localized("roi-a", "roi", "L", ml="lateral"),
        localized("roi-b", "roi", "L", ml="lateral"),
    ]

    results = FindingRoiMatcher(minimum_margin=0.1).match(
        findings, rois, accession_number="ACC-1", breast_side="L"
    )

    assert all(result.status is ResultStatus.SUCCESS for result in results)
    assert all(
        result.attribution_state is AttributionState.AMBIGUOUS for result in results
    )
    assert all(result.matched_roi_locators == () for result in results)
    assert all(result.score_margin == 0.0 for result in results)
    assert all(
        result.attribution_state is not AttributionState.VALIDATED for result in results
    )


def test_weak_evidence_abstains_while_retaining_axis_evidence() -> None:
    finding = localized(
        "finding-1",
        "finding",
        "L",
        ml="lateral",
        depth="posterior",
    )
    roi = localized(
        "roi-1",
        "roi",
        "L",
        ml="lateral",
        depth="anterior",
    )

    result = FindingRoiMatcher(minimum_score=0.75).match(
        [finding], [roi], accession_number="ACC-1", breast_side="L"
    )[0]

    assert result.status is ResultStatus.SUCCESS
    assert result.attribution_state is AttributionState.ABSTAINED
    assert result.matched_roi_locators == ()
    assert result.score == 0.5
    assert result.observed_descriptors == {"ml": "lateral", "depth": "posterior"}
    assert result.scored_descriptors == ("ml", "depth")
    assert result.candidates[0].payload["axis_scores"][1] == {
        "axis": "depth",
        "finding_value": "posterior",
        "roi_value": "anterior",
        "matched": False,
    }


def test_matching_rejects_unscoped_or_cross_scoped_inputs() -> None:
    finding = localized("finding-1", "finding", "L", ml="lateral")
    roi = localized("roi-1", "roi", "L", ml="lateral", accession_number="ACC-2")
    matcher = FindingRoiMatcher()

    with pytest.raises(ValueError, match="accession_number"):
        matcher.match([finding], [roi], accession_number="", breast_side="L")
    with pytest.raises(ValueError, match="unilateral"):
        matcher.match([finding], [roi], accession_number="ACC-1", breast_side="B")
    with pytest.raises(ValueError, match="accession scope"):
        matcher.match([finding], [roi], accession_number="ACC-1", breast_side="L")


def test_matching_serializes_only_plural_structured_roi_locators() -> None:
    singular = localized("finding-1", "finding", "R", depth="posterior")
    one = localized("roi-1", "roi", "R", depth="posterior")
    two = localized("roi-2", "roi", "R", depth="posterior")
    matcher = FindingRoiMatcher()

    singular_result = matcher.match(
        [singular], [one], accession_number="ACC-1", breast_side="R"
    )[0]
    plural_result = matcher.match(
        [singular], [one, two], accession_number="ACC-1", breast_side="R"
    )[0]

    assert singular_result.to_dict()["matched_roi_locators"] == [
        roi_locator("roi-1").to_dict()
    ]
    assert plural_result.to_dict()["matched_roi_locators"] == [
        locator.to_dict() for locator in plural_result.matched_roi_locators
    ]


def test_matching_rejects_duplicate_group_ids() -> None:
    finding = localized("finding-1", "finding", "L", ml="lateral")
    rois = [
        localized("roi-a", "roi", "L", ml="lateral"),
        localized("roi-b", "roi", "L", ml="lateral"),
    ]
    groups = [
        RoiGroup(
            group_id="duplicate",
            accession_number="ACC-1",
            laterality="L",
            rois=(domain_roi("roi-a", "img-a", (0, 0, 1, 1)),),
        ),
        RoiGroup(
            group_id="duplicate",
            accession_number="ACC-1",
            laterality="L",
            rois=(domain_roi("roi-b", "img-b", (0, 0, 1, 1)),),
        ),
    ]

    with pytest.raises(ValueError, match="group IDs must be unique"):
        FindingRoiMatcher().match(
            [finding],
            rois,
            accession_number="ACC-1",
            breast_side="L",
            roi_groups=groups,
        )
