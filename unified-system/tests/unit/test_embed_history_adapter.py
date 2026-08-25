from __future__ import annotations

import pytest

from embed_toolkit.adapters.embed_history import build_patient_history_tables
from embed_toolkit.core.build_policy import BuildPolicy, BuildPolicyError
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import ResolutionState


def test_reference_rows_map_to_patient_owned_history_without_false_precision() -> None:
    tables = build_patient_history_tables(
        source_scope="history-materialization",
        hormone_rows=[
            {
                "empi_anon": 1,
                "acc_anon": 101,
                "type": " H ",
                "code": " C ",
                "continuous": "Y",
                "current": "U",
                "duration": 36,
                "first_age": "52",
                "mfirst": "3",
                "yfirst": "2018",
                "last_age": "not recorded",
                "mlast": "",
                "ylast": "2021",
                "comment": " self-reported ",
            }
        ],
        procedure_rows=[
            {
                "empi_anon": 1,
                "acc_anon": 102,
                "type": "B",
                "pcode": "SB",
                "result": "BEN",
                "side": "L",
                "unreviewed_date_field": "circa 2010",
            }
        ],
    )

    medication = tables.medication_history[0]
    procedure = tables.procedure_history[0]
    assert medication.category == "hormone"
    assert medication.medication == "estrogen_and_progesterone"
    assert medication.current is None
    assert medication.reported_duration == "36"
    assert medication.started.to_dict() == {
        "age": 52.0,
        "year": 2018,
        "month": 3,
    }
    assert medication.stopped.to_dict() == {
        "age": None,
        "year": 2021,
        "month": None,
    }
    assert procedure.procedure == "biopsy"
    assert procedure.detail == "stereotactic_core_biopsy"
    assert procedure.reported_result == "benign"
    assert procedure.laterality is Laterality.LEFT
    assert tables.patients[0].history_observations == [medication, procedure]
    assert tables.source_occurrences[1].raw_values["unreviewed_date_field"] == (
        "circa 2010"
    )
    assert [issue.code for issue in tables.build_issues] == [
        "invalid_history_time_component"
    ]


def test_code_meaning_is_category_scoped_and_unknown_values_are_preserved() -> None:
    tables = build_patient_history_tables(
        source_scope="history-materialization",
        hormone_rows=[
            {"empi_anon": "P-1", "type": "H", "code": "C"},
            {"empi_anon": "P-2", "type": "O", "code": "C"},
            {"empi_anon": "P-3", "type": "H", "code": "future-code"},
        ],
        procedure_rows=[
            {"empi_anon": "P-4", "type": "B", "pcode": "HYST"},
        ],
    )

    assert [item.medication for item in tables.medication_history] == [
        "estrogen_and_progesterone",
        "combined_oral_contraceptive",
        "FUTURE-CODE",
    ]
    assert tables.procedure_history[0].procedure == "HYST"
    assert [issue.code for issue in tables.build_issues] == [
        "unknown_medication_history_code",
        "unknown_procedure_history_code",
    ]
    assert all(
        item.resolution_state is ResolutionState.RESOLVED
        for item in tables.source_occurrences
    )


def test_missing_identity_is_audited_or_rejected_by_explicit_policy() -> None:
    row = {"empi_anon": None, "type": "G", "pcode": "HYST"}

    audited = build_patient_history_tables(
        source_scope="history-materialization",
        procedure_rows=[row],
    )
    assert audited.procedure_history == ()
    assert audited.source_occurrences[0].resolution_state is ResolutionState.UNRESOLVED
    assert audited.build_issues[0].code == "incomplete_procedure_history_identity"

    with pytest.raises(BuildPolicyError) as exc_info:
        build_patient_history_tables(
            source_scope="history-materialization",
            procedure_rows=[row],
            build_policy=BuildPolicy.strict(),
        )
    assert exc_info.value.issue.code == "incomplete_procedure_history_identity"


def test_accession_is_context_not_history_identity_or_required_event_date() -> None:
    tables = build_patient_history_tables(
        source_scope="history-materialization",
        hormone_rows=[
            {"empi_anon": "P-1", "acc_anon": 999, "type": "T", "code": "ET"},
            {"empi_anon": "P-1", "type": "T", "code": "ET"},
        ],
    )

    assert [item.context_accession for item in tables.medication_history] == [
        "999",
        None,
    ]
    assert tables.medication_history[0].identity != tables.medication_history[1].identity
    assert tables.build_issues == ()
