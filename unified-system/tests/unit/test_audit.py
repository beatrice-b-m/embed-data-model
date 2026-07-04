from __future__ import annotations

import json

from embed_toolkit.audit.evidence import AuditTrail, AuditWarning, Evidence, WarningSeverity
from embed_toolkit.audit.results import (
    LocalizationResult,
    MatchCandidate,
    MatchingResult,
    PatchExtractionResult,
    ResultStatus,
    TransferResult,
    WorkflowResult,
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
        evidence=[Evidence(kind="roi_box", source="embed", payload={"box": [1, 2, 3, 4]})],
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
        evidence=[Evidence(kind="location_code", source="magview", payload={"raw": "UOQ"})],
        warnings=[AuditWarning(code="partial_position", message="Depth was not available")],
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
    candidate = MatchCandidate(
        roi_id="roi-1",
        score=0.92,
        payload={"distance": 0.08, "matched_axes": ["ml", "si"]},
        evidence=[Evidence(kind="nearest_neighbor", source="matcher", payload={"rank": 1})],
    )
    result = MatchingResult(
        finding_id="finding-1",
        matched_roi_id="roi-1",
        candidates=[candidate],
        unmatched_roi_ids=["roi-2"],
    )

    serialized = result.to_dict()

    assert serialized["finding_id"] == "finding-1"
    assert serialized["matched_roi_id"] == "roi-1"
    assert serialized["candidates"][0]["payload"] == {
        "distance": 0.08,
        "matched_axes": ["ml", "si"],
    }
    assert serialized["unmatched_roi_ids"] == ["roi-2"]
    json.dumps(serialized)


def test_transfer_result_shape_serializes_roi_and_transform_payloads() -> None:
    result = TransferResult(
        source_roi_id="roi-1",
        source_image_id="img-2d",
        target_image_id="img-s2d",
        transferred_roi={"box": [10.0, 20.0, 30.0, 40.0], "frame": 12},
        transform={"scale": [1.1, 0.9], "translation": [2.0, -1.0]},
        warnings=[
            AuditWarning(
                code="approximate_transfer",
                message="Image spacing differed between source and target",
            )
        ],
    )

    serialized = result.to_dict()

    assert serialized["source_roi_id"] == "roi-1"
    assert serialized["transferred_roi"]["box"] == [10.0, 20.0, 30.0, 40.0]
    assert serialized["transform"]["scale"] == [1.1, 0.9]
    assert serialized["warnings"][0]["code"] == "approximate_transfer"
    json.dumps(serialized)


def test_patch_extraction_result_shape_serializes_geometry_and_payload() -> None:
    result = PatchExtractionResult(
        image_id="img-1",
        roi_id="roi-1",
        patch_id="patch-1",
        bbox=[5.0, 7.0, 25.0, 37.0],
        shape=[20, 30],
        patch_payload={"path": "patches/patch-1.npy", "padding": {"top": 2, "left": 0}},
        evidence=[Evidence(kind="padding", source="patch_extractor", payload={"mode": "constant"})],
    )

    serialized = result.to_dict()

    assert serialized["bbox"] == [5.0, 7.0, 25.0, 37.0]
    assert serialized["shape"] == [20, 30]
    assert serialized["patch_payload"]["padding"] == {"top": 2, "left": 0}
    assert serialized["evidence"][0]["payload"] == {"mode": "constant"}
    json.dumps(serialized)
