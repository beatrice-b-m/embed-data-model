from __future__ import annotations

import json

from embed_toolkit.adapters.embed import build_clinical_tables
from embed_toolkit.clinical.associations import ClinicalObjectKind
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy
from embed_toolkit.core.provenance import ResolutionState


def row(**values: object) -> dict[str, object]:
    return {
        "empi_anon": "P-1",
        "acc_anon": "ACC-1",
        "numfind": "1",
        "side": "L",
        **values,
    }


def test_source_ledger_retains_every_ordinal_and_resolved_rows() -> None:
    repeated = row(asses="4")

    tables = build_clinical_tables(
        [repeated, repeated],
        source_scope="clinical-materialization",
    )

    assert [item.locator.row_ordinal for item in tables.source_occurrences] == [
        0,
        1,
    ]
    assert [item.resolution_state for item in tables.source_occurrences] == [
        ResolutionState.RESOLVED,
        ResolutionState.RESOLVED,
    ]
    assert all(item.raw_values == repeated for item in tables.source_occurrences)
    assert len(tables.patients) == 1
    assert len(tables.exams) == 1
    assert len(tables.findings) == 1
    assert len(tables.interpretations) == 1


def test_incomplete_procedure_marks_row_unresolved_but_keeps_safe_clinical_graph() -> None:
    tables = build_clinical_tables(
        [row(type="core biopsy", bside="L")],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization",
    )

    assert len(tables.patients) == 1
    assert len(tables.exams) == 1
    assert len(tables.findings) == 1
    assert tables.procedures == ()
    assert len(tables.unresolved_procedure_occurrences) == 1
    assert tables.unresolved_procedure_occurrences[0].source == (
        tables.source_occurrences[0].locator
    )
    assert tables.source_occurrences[0].resolution_state is ResolutionState.UNRESOLVED
    assert [issue.code for issue in tables.source_occurrences[0].issues] == [
        "incomplete_procedure_identity"
    ]


def test_missing_finding_keeps_resolved_procedure_and_scoped_pathology_targets() -> None:
    tables = build_clinical_tables(
        [
            row(
                numfind=None,
                procdate_anon="2020-01-02",
                type="core biopsy",
                bside="L",
                path1="ADH",
                path_severity=2,
            )
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization",
    )

    assert tables.findings == ()
    assert len(tables.procedures) == 1
    assert tables.procedures[0].sources == [tables.source_occurrences[0].locator]
    assert tables.finding_procedure_links == ()
    assert tables.source_occurrences[0].resolution_state is ResolutionState.UNRESOLVED
    assert [issue.code for issue in tables.source_occurrences[0].issues] == [
        "missing_finding_identity"
    ]
    assert {link.target.kind for link in tables.pathology_attribution_links} == {
        ClinicalObjectKind.PATIENT,
        ClinicalObjectKind.EXAM,
        ClinicalObjectKind.PROCEDURE,
    }


def test_missing_finding_keeps_incomplete_procedure_evidence_and_both_issues() -> None:
    tables = build_clinical_tables(
        [row(numfind=None, type="core biopsy", bside="L")],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization",
    )

    assert tables.findings == ()
    assert tables.procedures == ()
    assert len(tables.unresolved_procedure_occurrences) == 1
    assert tables.unresolved_procedure_occurrences[0].source == (
        tables.source_occurrences[0].locator
    )
    assert [issue.code for issue in tables.source_occurrences[0].issues] == [
        "missing_finding_identity",
        "incomplete_procedure_identity",
    ]


def test_pathology_anatomy_and_interpretation_issues_share_one_occurrence() -> None:
    tables = build_clinical_tables(
        [
            row(depth="A", asses="4"),
            row(depth="P", asses="5", path_severity=6),
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization",
    )

    assert len(tables.source_occurrences) == 2
    assert tables.source_occurrences[0].resolution_state is ResolutionState.RESOLVED
    second = tables.source_occurrences[1]
    assert second.resolution_state is ResolutionState.UNRESOLVED
    assert [issue.code for issue in second.issues] == [
        "invalid_pathology_severity",
        "conflicting_finding_anatomical_value",
        "conflicting_interpretation_attribute",
    ]
    assert [issue.code for issue in tables.build_issues] == [
        "invalid_pathology_severity",
        "conflicting_finding_anatomical_value",
        "conflicting_interpretation_attribute",
    ]
    assert all(issue.source == second.locator for issue in second.issues)
    assert tables.findings[0].anatomical_position.quadrant.depth.value == "anterior"
    assert tables.interpretations[0].assessment == "4"


def test_warning_only_normalization_row_remains_resolved() -> None:
    tables = build_clinical_tables(
        [row(location="unknown-code")],
        source_scope="clinical-materialization",
    )

    assert tables.findings[0].normalization_warnings
    assert tables.source_occurrences[0].issues == ()
    assert tables.source_occurrences[0].resolution_state is ResolutionState.RESOLVED


def test_result_serializes_raw_row_once_and_domain_objects_use_references() -> None:
    raw = row(
        raw_only_marker="RAW-UNIQUE-MARKER",
        asses="4",
        procdate_anon="2020-01-02",
        type="core biopsy",
        bside="L",
    )
    tables = build_clinical_tables(
        [raw],
        source_scope="clinical-materialization",
    )
    tables.patients[0].metadata["marker"] = "PATIENT-UNIQUE-MARKER"
    tables.exams[0].metadata["marker"] = "EXAM-UNIQUE-MARKER"
    tables.findings[0].metadata["marker"] = "FINDING-UNIQUE-MARKER"

    serialized = tables.to_dict()
    encoded = json.dumps(serialized)

    for marker in (
        "RAW-UNIQUE-MARKER",
        "PATIENT-UNIQUE-MARKER",
        "EXAM-UNIQUE-MARKER",
        "FINDING-UNIQUE-MARKER",
    ):
        assert encoded.count(marker) == 1
    assert serialized["source_occurrences"][0]["raw_values"] == raw
    assert "exams" not in serialized["patients"][0]
    assert serialized["patients"][0]["exam_references"] == ["ACC-1"]
    assert "findings" not in serialized["exams"][0]
    assert "images" not in serialized["exams"][0]
    assert "breast_sides" not in serialized["exams"][0]
    assert serialized["exams"][0]["finding_references"] == [
        {"accession_number": "ACC-1", "finding_number": "1"}
    ]
    assert serialized["exams"][0]["breast_side_references"] == [
        {"accession_number": "ACC-1", "laterality": "L"}
    ]
    assert serialized["exams"][0]["image_references"] == []
    assert serialized["findings"][0]["interpretation_reference"] == {
        "accession_number": "ACC-1",
        "finding_number": "1",
    }
    assert len(serialized["interpretations"]) == 1
    assert serialized["interpretations"][0]["finding"] == {
        "accession_number": "ACC-1",
        "finding_number": "1",
    }
    assert serialized["breast_sides"][0]["finding_references"] == [
        {"accession_number": "ACC-1", "finding_number": "1"}
    ]
    assert serialized["procedures"][0]["sources"] == [
        tables.source_occurrences[0].locator.to_dict()
    ]
    assert "raw_values" not in serialized["procedures"][0]
    assert "raw_source_fields" not in serialized["findings"][0]
    assert not hasattr(tables.findings[0], "raw_source_fields")
