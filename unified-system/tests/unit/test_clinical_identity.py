from __future__ import annotations

import pytest

from embed_toolkit.adapters.embed import build_clinical_tables
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError
from embed_toolkit.core.provenance import SourceScopeKind


@pytest.mark.parametrize(
    ("row", "expected_code"),
    [
        (
            {"empi_anon": None, "acc_anon": "ACC-1", "numfind": "1"},
            "missing_patient_identity",
        ),
        (
            {"empi_anon": "P-1", "acc_anon": " ", "numfind": "1"},
            "missing_accession_identity",
        ),
        (
            {"empi_anon": "P-1", "acc_anon": "ACC-1", "numfind": ""},
            "missing_finding_identity",
        ),
    ],
)
def test_strict_policy_rejects_blank_clinical_identity(
    row: dict,
    expected_code: str,
) -> None:
    with pytest.raises(BuildPolicyError) as exc_info:
        build_clinical_tables(
            [row],
            source_scope="clinical-release-1",
            source_scope_kind=SourceScopeKind.DATASET,
        )

    assert exc_info.value.issue.code == expected_code
    assert exc_info.value.issue.source.to_dict() == {
        "scope": "clinical-release-1",
        "scope_kind": "dataset",
        "source_profile": "internal-v2",
        "source_table": "magview",
        "row_ordinal": 0,
        "source_key": None,
    }


def test_audit_policy_retains_distinct_rows_without_synthetic_objects() -> None:
    unsafe = {
        "empi_anon": None,
        "acc_anon": "ACC-1",
        "numfind": "1",
        "procdate_anon": "2020-01-02",
        "type": "core biopsy",
        "bside": "L",
    }

    tables = build_clinical_tables(
        [unsafe, unsafe],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization-1",
    )

    assert tables.patients == ()
    assert tables.exams == ()
    assert tables.findings == ()
    assert tables.breast_sides == ()
    assert len(tables.source_occurrences) == 2
    assert len(tables.build_issues) == 2
    assert tables.source_occurrences[0].raw_values == unsafe
    assert tables.source_occurrences[1].raw_values == unsafe
    assert [
        occurrence.locator.row_ordinal
        for occurrence in tables.source_occurrences
    ] == [0, 1]
    assert (
        tables.source_occurrences[0].locator
        != tables.source_occurrences[1].locator
    )
    assert all(patient.patient_id != "UNKNOWN_PATIENT" for patient in tables.patients)


def test_missing_finding_identity_still_resolves_standalone_procedure() -> None:
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P-1",
                "acc_anon": "ACC-1",
                "numfind": None,
                "procdate_anon": "2020-01-02",
                "type": "core biopsy",
                "bside": "L",
            }
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization-1",
    )

    assert [patient.patient_id for patient in tables.patients] == ["P-1"]
    assert [exam.accession_number for exam in tables.exams] == ["ACC-1"]
    assert tables.findings == ()
    assert tables.breast_sides == ()
    assert tables.patients[0].exams == [tables.exams[0]]
    assert len(tables.procedures) == 1
    assert tables.procedures[0].sources == [tables.source_occurrences[0].locator]
    assert tables.finding_procedure_links == ()
    assert [issue.code for issue in tables.build_issues] == [
        "missing_finding_identity"
    ]


def test_repeated_missing_findings_reuse_parent_and_retain_row_occurrences() -> None:
    row = {"empi_anon": "P-1", "acc_anon": "ACC-1", "numfind": None}

    tables = build_clinical_tables(
        [row, row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization-1",
    )

    assert len(tables.patients) == 1
    assert len(tables.exams) == 1
    assert tables.findings == ()
    assert tables.breast_sides == ()
    assert len(tables.source_occurrences) == 2
    assert [
        occurrence.locator.row_ordinal
        for occurrence in tables.source_occurrences
    ] == [0, 1]
    assert (
        tables.source_occurrences[0].locator
        != tables.source_occurrences[1].locator
    )


def test_governed_negative_nine_finding_identity_is_preserved() -> None:
    tables = build_clinical_tables(
        [{"empi_anon": "P-1", "acc_anon": "ACC-1", "numfind": "-9"}],
        source_scope="clinical-release-1",
    )

    assert tables.findings[0].finding_number == "-9"
    assert (
        tables.findings[0].record_type.value
        == "synthetic_contralateral_negative"
    )
    assert len(tables.source_occurrences) == 1
    assert tables.source_occurrences[0].resolution_state.value == "resolved"
    assert tables.build_issues == ()


def test_accession_patient_conflict_uses_build_policy() -> None:
    rows = [
        {"empi_anon": "P-1", "acc_anon": "ACC-1", "numfind": "1"},
        {"empi_anon": "P-2", "acc_anon": "ACC-1", "numfind": "2"},
    ]

    with pytest.raises(BuildPolicyError) as exc_info:
        build_clinical_tables(rows, source_scope="clinical-release-1")

    assert exc_info.value.issue.code == "conflicting_accession_patient_identity"

    audited = build_clinical_tables(
        rows,
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-release-1",
    )
    assert [patient.patient_id for patient in audited.patients] == ["P-1"]
    assert [finding.finding_number for finding in audited.findings] == ["1"]
    assert len(audited.source_occurrences) == 2
    assert audited.source_occurrences[1].resolution_state.value == "unresolved"
    issue = audited.build_issues[0]
    assert issue.code == "conflicting_accession_patient_identity"
    assert issue.context == {
        "accession_number": "ACC-1",
        "retained_patient_id": "P-1",
        "observed_patient_id": "P-2",
    }


def test_default_scope_is_explicitly_ephemeral_materialization_provenance() -> None:
    tables = build_clinical_tables(
        [{"empi_anon": None, "acc_anon": "ACC-1", "numfind": "1"}],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    locator = tables.source_occurrences[0].locator
    assert locator.scope_kind is SourceScopeKind.MATERIALIZATION
    assert locator.scope.startswith("in-memory:")


def test_dataset_scope_cannot_be_implicitly_generated() -> None:
    with pytest.raises(ValueError, match="must be supplied explicitly"):
        build_clinical_tables([], source_scope_kind=SourceScopeKind.DATASET)
