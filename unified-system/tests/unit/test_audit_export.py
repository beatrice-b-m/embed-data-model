from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from embed_toolkit.audit.evidence import AuditWarning, Evidence
from embed_toolkit.audit.export import export_result, export_results, summarize_results
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
            scope="audit-export-tests",
            scope_kind=SourceScopeKind.MATERIALIZATION,
            source_profile="test",
            source_table="images",
            source_key=f"image:{value}",
        ),
        source_value=value,
    )


@dataclass(frozen=True)
class CustomResult:
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return self.payload


def test_export_result_object_preserves_audit_links() -> None:
    result = LocalizationResult(
        status=ResultStatus.PARTIAL,
        subject_id="finding-1",
        subject_type="finding",
        anatomical_position={"quadrant": "UOQ"},
        evidence=[
            Evidence(
                kind="clock_position",
                source="magview",
                payload={"raw_code": "C10", "source_row_id": "row-7"},
            )
        ],
        warnings=[
            AuditWarning(
                code="missing_depth",
                message="Depth unavailable",
                payload={"evidence_id": "row-7"},
            )
        ],
        metadata={"workflow": "finding_localization"},
    )

    exported = export_result(result)

    assert list(exported) == [
        "anatomical_position",
        "continuous_position",
        "evidence",
        "metadata",
        "status",
        "subject_id",
        "subject_type",
        "warnings",
    ]
    assert exported["evidence"][0]["payload"] == {
        "raw_code": "C10",
        "source_row_id": "row-7",
    }
    assert exported["warnings"][0]["payload"] == {"evidence_id": "row-7"}
    json.dumps(exported)


def test_export_results_handles_mixed_workflow_collection() -> None:
    locator = roi_locator("roi-1")
    matching = MatchingResult(
        status=ResultStatus.SUCCESS,
        finding_id="finding-1",
        matched_roi_locators=(locator,),
        matched_roi_group_ids=("group-1",),
        candidates=(
            MatchCandidate(
                candidate_id="group-1",
                score=0.93,
                roi_locators=(locator,),
            ),
        ),
        attribution_state="inferred",
        score=0.93,
        evidence=[Evidence(kind="score", source="matcher", payload={"value": 0.93})],
    )
    transfer = TransferResult(
        status=ResultStatus.SUCCESS,
        source_roi_locator=locator,
        source_image_id="img-a",
        target_image_id="img-b",
        transferred_roi={
            "target_image_id": "img-b",
            "coordinates": (1, 2, 3, 4),
            "source_frame_indices": (),
        },
        transform={"scale": (1, 1)},
    )
    patch = PatchExtractionResult(
        status=ResultStatus.FAILED,
        image_id="img-b",
        roi_locator=locator,
        patch_id="patch-1",
        warnings=[
            AuditWarning(code="out_of_bounds", message="Patch exceeded image bounds")
        ],
    )
    generic = WorkflowResult(
        status=ResultStatus.SKIPPED,
        result_type="review_step",
        payload={"reason": "manual_review_required"},
    )

    exported = export_results([matching, transfer, patch, generic])

    assert exported["count"] == 4
    assert exported["summary"] == {
        "total": 4,
        "statuses": {"failed": 1, "skipped": 1, "success": 2},
        "result_types": {"review_step": 1},
        "evidence_count": 1,
        "warning_count": 1,
    }
    assert exported["results"][1]["transferred_roi"]["coordinates"] == [1, 2, 3, 4]
    assert exported["results"][3]["payload"] == {"reason": "manual_review_required"}
    json.dumps(exported)


def test_export_plain_mapping_and_custom_to_dict_result() -> None:
    mapping_export = export_result(
        {
            "z": "last",
            "a": {"b": 2, "a": 1},
            "evidence": [{"source": "manual", "payload": {"row": 2}}],
        }
    )
    custom_export = export_result(
        CustomResult(
            {"status": ResultStatus.SUCCESS, "payload": {"axes": ("ml", "si")}}
        )
    )

    assert list(mapping_export) == ["a", "evidence", "z"]
    assert list(mapping_export["a"]) == ["a", "b"]
    assert custom_export == {"payload": {"axes": ["ml", "si"]}, "status": "success"}
    json.dumps({"mapping": mapping_export, "custom": custom_export})


def test_summarize_results_is_deterministic() -> None:
    summary = summarize_results(
        [
            {"status": "success", "result_type": "transfer", "warnings": [1]},
            {"status": "failed", "result_type": "matching", "evidence": [1, 2]},
            {"status": "success", "result_type": "matching", "warnings": [1]},
        ]
    )

    assert summary == {
        "total": 3,
        "statuses": {"failed": 1, "success": 2},
        "result_types": {"matching": 2, "transfer": 1},
        "evidence_count": 2,
        "warning_count": 2,
    }


def test_export_rejects_unsupported_values() -> None:
    with pytest.raises(TypeError, match="Unsupported audit export value"):
        export_result(object())

    with pytest.raises(TypeError, match="Result to_dict\\(\\) must return a mapping"):
        export_result(CustomResult(["not", "a", "mapping"]))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="non-string sequences"):
        export_results("not-a-result-collection")

    with pytest.raises(TypeError, match="Unsupported serializable value"):
        export_result({"bad": object()})
