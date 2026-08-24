from __future__ import annotations

import json

import pytest

from embed_toolkit.audit.evidence import (
    AuditTrail,
    AuditWarning,
    Evidence,
    WarningSeverity,
)
from embed_toolkit.audit.results import (
    LocalizationResult,
    MatchCandidate,
    MatchingResult,
    PatchExtractionResult,
    ResultStatus,
    TransferResult,
    WorkflowResult,
)
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind
from embed_toolkit.imaging.roi_provenance import RoiLocator


def roi_locator(value: str) -> RoiLocator:
    return RoiLocator.from_source(
        image_locator=SourceLocator(
            scope="audit-tests",
            scope_kind=SourceScopeKind.MATERIALIZATION,
            source_profile="test",
            source_table="images",
            source_key=f"image:{value}",
        ),
        source_value=value,
    )


def test_evidence_serializes_and_preserves_payload() -> None:
    evidence = Evidence(
        kind="clock_position",
        source="magview",
        payload={
            "raw_code": "C3",
            "alternates": [{"hour": 3, "rank": 1}],
            "accepted": True,
        },
        confidence=0.8,
        note="clock code normalized",
    )

    serialized = evidence.to_dict()

    assert serialized == {
        "kind": "clock_position",
        "source": "magview",
        "payload": {
            "raw_code": "C3",
            "alternates": [{"hour": 3, "rank": 1}],
            "accepted": True,
        },
        "confidence": 0.8,
        "note": "clock code normalized",
    }
    json.dumps(serialized)


def test_warning_and_audit_trail_serialization() -> None:
    warning = AuditWarning(
        code="missing_landmark",
        message="Posterior landmark unavailable",
        severity=WarningSeverity.INFO,
        payload={"axis": "depth", "image_id": "img-1"},
    )
    trail = AuditTrail(
        evidence=[
            Evidence(kind="roi_box", source="embed", payload={"box": [1, 2, 3, 4]})
        ],
        warnings=[warning],
    )

    serialized = trail.to_dict()

    assert serialized["warnings"] == [
        {
            "code": "missing_landmark",
            "message": "Posterior landmark unavailable",
            "severity": "info",
            "payload": {"axis": "depth", "image_id": "img-1"},
        }
    ]
    assert serialized["evidence"][0]["payload"] == {"box": [1, 2, 3, 4]}
    json.dumps(serialized)


def test_workflow_result_container_serializes_payload_and_audit() -> None:
    result = WorkflowResult(
        status=ResultStatus.SKIPPED,
        result_type="generic_audit_result",
        payload={"ids": ["a", "b"], "summary": {"count": 2}},
        evidence=[Evidence(kind="input", source="workflow", payload={"rows": 2})],
        warnings=[AuditWarning(code="not_run", message="Workflow was skipped")],
        metadata={"reason": "dry_run"},
    )

    serialized = result.to_dict()

    assert serialized["status"] == "skipped"
    assert serialized["result_type"] == "generic_audit_result"
    assert serialized["payload"] == {"ids": ["a", "b"], "summary": {"count": 2}}
    assert serialized["evidence"][0]["payload"] == {"rows": 2}
    assert serialized["metadata"] == {"reason": "dry_run"}
    json.dumps(serialized)


def test_localization_result_shape_serializes_positions() -> None:
    result = LocalizationResult(
        status=ResultStatus.PARTIAL,
        subject_id="finding-1",
        subject_type="finding",
        anatomical_position={
            "laterality": "L",
            "quadrant": {"ml": "lateral", "si": "superior", "depth": "unknown"},
        },
        continuous_position={"ml": 0.75, "observable_axes": ["ml"]},
        evidence=[
            Evidence(kind="location_code", source="magview", payload={"raw": "UOQ"})
        ],
        warnings=[
            AuditWarning(code="partial_position", message="Depth was not available")
        ],
        metadata={"workflow": "localization"},
    )

    serialized = result.to_dict()

    assert serialized["status"] == "partial"
    assert serialized["subject_id"] == "finding-1"
    assert serialized["anatomical_position"]["quadrant"]["depth"] == "unknown"
    assert serialized["continuous_position"] == {"ml": 0.75, "observable_axes": ["ml"]}
    assert serialized["warnings"][0]["code"] == "partial_position"
    json.dumps(serialized)


def test_matching_result_shape_preserves_candidates_and_unmatched_rois() -> None:
    matched = roi_locator("roi-1")
    unmatched = roi_locator("roi-2")
    candidate = MatchCandidate(
        candidate_id="group-1",
        score=0.92,
        roi_locators=(matched,),
        payload={"distance": 0.08, "matched_axes": ["ml", "si"]},
        evidence=[
            Evidence(kind="nearest_neighbor", source="matcher", payload={"rank": 1})
        ],
    )
    alternate = MatchCandidate(
        candidate_id="group-2",
        score=0.5,
        roi_locators=(unmatched,),
    )
    result = MatchingResult(
        finding_id="finding-1",
        matched_roi_locators=(matched,),
        matched_roi_group_ids=("group-1",),
        candidates=[candidate, alternate],
        unmatched_roi_locators=(unmatched,),
        attribution_state="inferred",
        score=0.92,
        score_margin=0.92 - 0.5,
    )

    serialized = result.to_dict()

    assert serialized["finding_id"] == "finding-1"
    assert serialized["matched_roi_locators"] == [matched.to_dict()]
    assert serialized["candidates"][0]["payload"] == {
        "distance": 0.08,
        "matched_axes": ["ml", "si"],
    }
    assert serialized["unmatched_roi_locators"] == [unmatched.to_dict()]
    json.dumps(serialized)


def test_transfer_result_shape_serializes_roi_and_transform_payloads() -> None:
    locator = roi_locator("roi-1")
    result = TransferResult(
        source_roi_locator=locator,
        source_image_id="img-2d",
        target_image_id="img-s2d",
        transferred_roi={
            "target_image_id": "img-s2d",
            "coordinates": [10.0, 20.0, 30.0, 40.0],
            "source_frame_indices": [12],
        },
        transform={"scale": [1.1, 0.9], "translation": [2.0, -1.0]},
        warnings=[
            AuditWarning(
                code="approximate_transfer",
                message="Image spacing differed between source and target",
            )
        ],
    )

    serialized = result.to_dict()

    assert serialized["source_roi_locator"] == locator.to_dict()
    assert serialized["transferred_roi"]["coordinates"] == [
        10.0,
        20.0,
        30.0,
        40.0,
    ]
    assert serialized["transform"]["scale"] == [1.1, 0.9]
    assert serialized["warnings"][0]["code"] == "approximate_transfer"
    json.dumps(serialized)


def test_patch_extraction_result_shape_serializes_geometry_and_payload() -> None:
    locator = roi_locator("roi-1")
    result = PatchExtractionResult(
        image_id="img-1",
        roi_locator=locator,
        patch_id="patch-1",
        bbox=[5.0, 7.0, 25.0, 37.0],
        shape=[20, 30],
        patch_payload={"path": "patches/patch-1.npy", "padding": {"top": 2, "left": 0}},
        evidence=[
            Evidence(
                kind="padding", source="patch_extractor", payload={"mode": "constant"}
            )
        ],
    )

    serialized = result.to_dict()

    assert serialized["bbox"] == [5.0, 7.0, 25.0, 37.0]
    assert serialized["shape"] == [20, 30]
    assert serialized["patch_payload"]["padding"] == {"top": 2, "left": 0}
    assert serialized["evidence"][0]["payload"] == {"mode": "constant"}
    json.dumps(serialized)


def test_matching_result_rejects_duplicate_or_overlapping_locators() -> None:
    locator = roi_locator("roi-1")
    with pytest.raises(ValueError, match="unique"):
        MatchingResult(
            finding_id="finding-1",
            matched_roi_locators=(locator, locator),
        )
    with pytest.raises(ValueError, match="disjoint"):
        MatchingResult(
            finding_id="finding-1",
            matched_roi_locators=(locator,),
            unmatched_roi_locators=(locator,),
        )


def test_audit_payloads_are_deeply_frozen_and_serialize_fresh_copies() -> None:
    original = {
        "z": [{"value": 1}],
        "a": ResultStatus.SUCCESS,
    }
    evidence = Evidence(kind="input", source="test", payload=original)
    original["z"][0]["value"] = 99

    assert tuple(evidence.payload) == ("a", "z")
    assert evidence.payload["a"] == "success"
    assert evidence.payload["z"][0]["value"] == 1
    with pytest.raises(TypeError):
        evidence.payload["new"] = "value"  # type: ignore[index]

    serialized = evidence.to_dict()
    serialized["payload"]["z"][0]["value"] = 2
    assert evidence.to_dict()["payload"]["z"][0]["value"] == 1
    json.dumps(evidence.to_dict(), allow_nan=False)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_audit_payloads_reject_nonfinite_numbers(invalid: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        Evidence(kind="input", source="test", payload={"value": invalid})
    with pytest.raises(ValueError, match="finite"):
        WorkflowResult(
            result_type="invalid",
            metadata={"value": invalid},
        )


def test_audit_payloads_reject_non_string_keys_and_order_deterministically() -> None:
    with pytest.raises(TypeError, match="keys must be strings"):
        AuditWarning(
            code="invalid",
            message="invalid payload",
            payload={1: "collision"},  # type: ignore[dict-item]
        )

    forward = Evidence(
        kind="input",
        source="test",
        payload={"b": {"d": 4, "c": 3}, "a": 1},
    )
    reverse = Evidence(
        kind="input",
        source="test",
        payload={"a": 1, "b": {"c": 3, "d": 4}},
    )
    assert forward.to_dict() == reverse.to_dict()
    assert list(forward.to_dict()["payload"]) == ["a", "b"]


def test_matching_candidate_rank_and_state_coherence_are_typed() -> None:
    one = roi_locator("one-axis")
    two = roi_locator("two-axes")
    candidates = (
        MatchCandidate("one", 0.8, scored_axis_count=1, roi_locators=(one,)),
        MatchCandidate("two", 0.8, scored_axis_count=2, roi_locators=(two,)),
    )
    result = MatchingResult(
        finding_id="finding-1",
        candidates=candidates,
        unmatched_roi_locators=(one, two),
        attribution_state="abstained",
        score=0.8,
        score_margin=0.0,
    )

    assert [candidate.candidate_id for candidate in result.candidates] == ["two", "one"]
    with pytest.raises(ValueError, match="top-two eligible"):
        MatchingResult(
            finding_id="finding-1",
            candidates=candidates,
            unmatched_roi_locators=(one, two),
            attribution_state="abstained",
            score=0.8,
        )
    with pytest.raises(TypeError, match="eligible"):
        MatchCandidate(
            "invalid",
            0.8,
            eligible=1,  # type: ignore[arg-type]
            roi_locators=(one,),
        )
    with pytest.raises(ValueError, match="best selected candidate"):
        MatchingResult(
            finding_id="finding-1",
            candidates=candidates,
            matched_roi_group_ids=("two",),
            matched_roi_locators=(two,),
            unmatched_roi_locators=(one,),
            attribution_state="inferred",
            score=0.7,
            score_margin=0.0,
        )

    ineligible = MatchCandidate(
        "ineligible",
        0.7,
        eligible=False,
        roi_locators=(one,),
    )
    one_eligible = MatchCandidate("eligible", 0.6, roi_locators=(two,))
    without_margin = MatchingResult(
        finding_id="finding-2",
        candidates=(ineligible, one_eligible),
        unmatched_roi_locators=(one, two),
        attribution_state="abstained",
        score=0.7,
    )
    assert without_margin.score_margin is None


def test_transfer_result_rejects_malformed_state_and_projection() -> None:
    locator = roi_locator("transfer")
    valid_projection = {
        "target_image_id": "target",
        "coordinates": [1.0, 2.0, 3.0, 4.0],
        "source_frame_indices": [],
    }

    with pytest.raises(ValueError, match="require projection"):
        TransferResult(
            source_roi_locator=locator,
            source_image_id="source",
            target_image_id="target",
        )
    with pytest.raises(ValueError, match="cannot contain output"):
        TransferResult(
            status=ResultStatus.SKIPPED,
            source_roi_locator=locator,
            source_image_id="source",
            target_image_id="target",
            transferred_roi=valid_projection,
            transform={"scale": [1.0, 1.0]},
        )
    for malformed in (
        {**valid_projection, "target_image_id": "other"},
        {**valid_projection, "roi_locator": locator.to_dict()},
        {**valid_projection, "coordinates": [1.0, 2.0, 3.0]},
        {**valid_projection, "frame_indices": [1]},
    ):
        with pytest.raises(ValueError):
            TransferResult(
                source_roi_locator=locator,
                source_image_id="source",
                target_image_id="target",
                transferred_roi=malformed,
                transform={"scale": [1.0, 1.0]},
            )
