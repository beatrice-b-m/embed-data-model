from __future__ import annotations

import pytest

from embed_toolkit.adapters.embed import build_clinical_tables
from embed_toolkit.clinical.associations import ClinicalObjectKind
from embed_toolkit.clinical.pathology import PathologySeverity
from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError


def clinical_row() -> dict:
    return {
        "empi_anon": "P-1",
        "acc_anon": "ACC-1",
        "numfind": "1",
        "side": "L",
    }


def test_pathology_only_row_survives_unresolved_clinical_identity_in_audit() -> None:
    row = {
        "path1": "ADH",
        "path2": "ADH",
        "path_severity": 2,
        "pdate_anon": "2020-01-05",
    }

    tables = build_clinical_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )

    assert [item.descriptor for item in tables.pathology_observations] == [
        "ADH",
        "ADH",
    ]
    assert [item.source_slot for item in tables.pathology_observations] == [
        "path1",
        "path2",
    ]
    assert [item.source_ordinal for item in tables.pathology_observations] == [1, 2]
    diagnosis = tables.pathology_diagnoses[0]
    assert diagnosis.severity is PathologySeverity.SEVERITY_2
    assert diagnosis.report_documented_date == "2020-01-05"
    assert tables.pathology_attribution_links == ()
    assert tables.patients == ()
    assert tables.findings == ()


def test_pathology_links_only_to_resolved_colocated_grains() -> None:
    row = {
        **clinical_row(),
        "procdate_anon": "2020-01-02",
        "type": "core biopsy",
        "bside": "L",
        "path1": "DCIS",
        "path_severity": 1,
    }

    tables = build_clinical_tables([row], source_scope="materialization-1")

    assert len(tables.pathology_observations) == 1
    assert len(tables.pathology_diagnoses) == 1
    assert len(tables.pathology_attribution_links) == 8
    target_kinds = [
        link.target.kind for link in tables.pathology_attribution_links
    ]
    assert target_kinds.count(ClinicalObjectKind.PATIENT) == 2
    assert target_kinds.count(ClinicalObjectKind.EXAM) == 2
    assert target_kinds.count(ClinicalObjectKind.FINDING) == 2
    assert target_kinds.count(ClinicalObjectKind.PROCEDURE) == 2


def test_incomplete_procedure_does_not_block_pathology_or_gain_attribution() -> None:
    row = {
        **clinical_row(),
        "type": "core biopsy",
        "pathology_diagnosis": "benign",
    }

    tables = build_clinical_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )

    assert tables.procedures == ()
    assert len(tables.unresolved_procedure_occurrences) == 1
    assert [item.diagnosis for item in tables.pathology_diagnoses] == ["benign"]
    assert {
        link.target.kind for link in tables.pathology_attribution_links
    } == {
        ClinicalObjectKind.PATIENT,
        ClinicalObjectKind.EXAM,
        ClinicalObjectKind.FINDING,
    }


def test_missing_finding_allows_only_patient_and_exam_pathology_links() -> None:
    row = {
        **clinical_row(),
        "numfind": None,
        "pathology_diagnosis": "benign",
    }

    tables = build_clinical_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )

    assert len(tables.patients) == 1
    assert len(tables.exams) == 1
    assert tables.findings == ()
    assert {
        link.target.kind for link in tables.pathology_attribution_links
    } == {ClinicalObjectKind.PATIENT, ClinicalObjectKind.EXAM}


@pytest.mark.parametrize(
    "raw_severity",
    [6, -1, 2.5, "not-a-code", True, False],
)
def test_invalid_severity_uses_shared_build_policy(raw_severity: object) -> None:
    row = {**clinical_row(), "path_severity": raw_severity}

    with pytest.raises(BuildPolicyError, match="integer from 0 through 5"):
        build_clinical_tables([row], source_scope="materialization-1")

    audited = build_clinical_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )
    diagnosis = audited.pathology_diagnoses[0]
    assert diagnosis.severity is None
    assert diagnosis.raw_severity == raw_severity
    assert diagnosis.validation_issues[0].code == "invalid_pathology_severity"
    assert audited.build_issues[0] is diagnosis.validation_issues[0]


def test_one_physical_occurrence_merges_pathology_and_procedure_issues() -> None:
    row = {
        **clinical_row(),
        "type": "core biopsy",
        "path_severity": 6,
    }

    tables = build_clinical_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )

    assert len(tables.unresolved_occurrences) == 1
    assert [
        issue.code for issue in tables.unresolved_occurrences[0].issues
    ] == ["invalid_pathology_severity", "incomplete_procedure_identity"]
    assert [issue.code for issue in tables.build_issues] == [
        "invalid_pathology_severity",
        "incomplete_procedure_identity",
    ]
    assert len(tables.unresolved_procedure_occurrences) == 1
    assert [
        issue.code
        for issue in tables.unresolved_procedure_occurrences[0].occurrence.issues
    ] == ["incomplete_procedure_identity"]


def test_one_physical_occurrence_merges_pathology_and_finding_issues() -> None:
    row = {
        **clinical_row(),
        "numfind": None,
        "path_severity": 6,
    }

    tables = build_clinical_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )

    assert len(tables.unresolved_occurrences) == 1
    assert [
        issue.code for issue in tables.unresolved_occurrences[0].issues
    ] == ["invalid_pathology_severity", "missing_finding_identity"]
    assert [issue.code for issue in tables.build_issues] == [
        "invalid_pathology_severity",
        "missing_finding_identity",
    ]


def test_repeated_invalid_physical_rows_keep_distinct_locators() -> None:
    row = {**clinical_row(), "path_severity": True}

    tables = build_clinical_tables(
        [row, row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )

    assert len(tables.unresolved_occurrences) == 2
    assert [item.locator.row_ordinal for item in tables.unresolved_occurrences] == [
        0,
        1,
    ]


def test_descriptors_without_severity_preserve_observations_and_unknown_state() -> None:
    row = {**clinical_row(), "path1": "UNMAPPED"}

    with pytest.raises(BuildPolicyError, match="require a populated severity"):
        build_clinical_tables([row], source_scope="materialization-1")

    audited = build_clinical_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )
    assert [item.descriptor for item in audited.pathology_observations] == [
        "UNMAPPED"
    ]
    diagnosis = audited.pathology_diagnoses[0]
    assert diagnosis.severity is None
    assert diagnosis.raw_severity is None


def test_procedure_and_pathology_dates_never_fill_each_other() -> None:
    complete = {
        **clinical_row(),
        "procdate_anon": "2020-01-02",
        "type": "core biopsy",
        "bside": "L",
        "pathology_diagnosis": "benign",
        "pdate_anon": "2020-01-05",
    }
    tables = build_clinical_tables([complete], source_scope="materialization-1")

    assert tables.procedures[0].identity.performed_date == "2020-01-02"
    assert tables.pathology_diagnoses[0].report_documented_date == "2020-01-05"

    procedure_only = build_clinical_tables(
        [{key: value for key, value in complete.items() if key != "pdate_anon"}],
        source_scope="materialization-2",
    )
    assert procedure_only.pathology_diagnoses[0].report_documented_date is None

    pathology_only = build_clinical_tables(
        [
            {
                **clinical_row(),
                "pathology_diagnosis": "benign",
                "pdate_anon": "2020-01-05",
            }
        ],
        source_scope="materialization-3",
    )
    assert pathology_only.procedures == ()
    assert pathology_only.pathology_diagnoses[0].report_documented_date == (
        "2020-01-05"
    )


def test_custom_pathology_report_date_column_is_bound_by_meaning() -> None:
    columns = EmbedColumnConfig(pathology_report_date="report_recorded_on")
    tables = build_clinical_tables(
        [
            {
                **clinical_row(),
                "pathology_diagnosis": "benign",
                "report_recorded_on": "2020-03-04",
            }
        ],
        columns=columns,
        source_scope="materialization-1",
    )

    assert tables.pathology_diagnoses[0].report_documented_date == "2020-03-04"
