from __future__ import annotations

import pytest

from embed_toolkit.adapters.embed import build_clinical_tables
from embed_toolkit.clinical.associations import AttributionStatus
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError
from embed_toolkit.core.primitives import Laterality


def base_row() -> dict:
    return {
        "empi_anon": "P-1",
        "acc_anon": "ACC-1",
        "numfind": "1",
        "side": "L",
    }


def test_strict_policy_rejects_populated_incomplete_procedure_surface() -> None:
    row = {**base_row(), "procedure_id": "SOURCE-PROC-1"}

    with pytest.raises(BuildPolicyError) as exc_info:
        build_clinical_tables([row], source_scope="materialization-1")

    assert exc_info.value.issue.code == "incomplete_procedure_identity"
    assert exc_info.value.issue.context["missing_identity_fields"] == [
        "performed_date",
        "procedure_type",
        "laterality",
    ]


def test_audit_retains_incomplete_procedure_without_resolved_multiplicity() -> None:
    row = {**base_row(), "type": "core biopsy", "bside": "L"}

    tables = build_clinical_tables(
        [row, row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="materialization-1",
    )

    assert len(tables.findings) == 1
    assert tables.procedures == ()
    assert tables.finding_procedure_links == ()
    assert len(tables.unresolved_procedure_occurrences) == 2
    assert len(tables.unresolved_occurrences) == 2
    assert len(tables.build_issues) == 2
    assert [
        item.occurrence.locator.row_ordinal
        for item in tables.unresolved_procedure_occurrences
    ] == [0, 1]
    assert all(
        item.missing_identity_fields == ("performed_date",)
        for item in tables.unresolved_procedure_occurrences
    )


def test_complete_procedure_is_shared_by_explicit_finding_links() -> None:
    procedure_values = {
        "procdate_anon": "2020-01-02",
        "type": "core biopsy",
        "bside": "R",
    }
    tables = build_clinical_tables(
        [
            {**base_row(), **procedure_values, "procedure_id": "SOURCE-A"},
            {
                **base_row(),
                **procedure_values,
                "numfind": "2",
                "procedure_id": "SOURCE-B",
            },
        ],
        source_scope="materialization-1",
    )

    assert len(tables.procedures) == 1
    procedure = tables.procedures[0]
    assert procedure.identity.patient_id == "P-1"
    assert procedure.identity.performed_date == "2020-01-02"
    assert procedure.identity.procedure_type == "core biopsy"
    assert procedure.identity.laterality is Laterality.RIGHT
    assert [
        occurrence.raw_values["procedure_id"]
        for occurrence in procedure.source_occurrences
    ] == ["SOURCE-A", "SOURCE-B"]
    assert [link.finding_number for link in tables.finding_procedure_links] == [
        "1",
        "2",
    ]
    assert all(
        link.procedure == procedure.identity
        and link.status is AttributionStatus.SOURCE_COLOCATED
        for link in tables.finding_procedure_links
    )
    assert all(not hasattr(finding, "procedures") for finding in tables.findings)


def test_source_procedure_id_is_not_part_of_governed_identity() -> None:
    complete = {
        **base_row(),
        "procdate_anon": "2020-01-02",
        "type": "core biopsy",
        "bside": "L",
    }
    without_source_id = build_clinical_tables(
        [complete],
        source_scope="materialization-1",
    )
    with_source_id = build_clinical_tables(
        [{**complete, "procedure_id": "LOCAL-ONLY"}],
        source_scope="materialization-1",
    )

    assert without_source_id.procedures[0].identity == with_source_id.procedures[0].identity
    assert "procedure_id" not in without_source_id.procedures[0].identity.to_dict()


def test_absent_procedure_surface_creates_no_procedure_evidence() -> None:
    tables = build_clinical_tables([base_row()], source_scope="materialization-1")

    assert tables.procedures == ()
    assert tables.finding_procedure_links == ()
    assert tables.unresolved_procedure_occurrences == ()
    assert tables.unresolved_occurrences == ()
    assert tables.build_issues == ()
