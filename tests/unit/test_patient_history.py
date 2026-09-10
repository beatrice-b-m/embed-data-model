from __future__ import annotations

import pytest

from embed_data_model.clinical.histories import (
    HistoryTimeEstimate,
    MedicationHistoryObservation,
    PatientHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_data_model.clinical.patients import Patient
from embed_data_model.core.primitives import Laterality
from embed_data_model.core.provenance import SourceLocator, SourceScopeKind


def source(row: int = 0) -> SourceLocator:
    return SourceLocator(
        scope="history-test",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="test",
        source_table="HormoneHist",
        row_ordinal=row,
    )


def test_partial_history_time_preserves_source_precision() -> None:
    estimate = HistoryTimeEstimate(age=52, year=2018, month=3)

    assert estimate.to_dict() == {"age": 52.0, "year": 2018, "month": 3}
    assert HistoryTimeEstimate(month=7).to_dict()["year"] is None
    from embed_data_model.core.validation import validate
    assert not validate(HistoryTimeEstimate(month=13)).valid


def test_patient_owns_extensible_reported_history() -> None:
    medication = MedicationHistoryObservation(
        patient_id="P-1",
        source=source(),
        category="hormone",
        medication="estrogen",
        context_accession="ACC-1",
        current=True,
        reported_duration="36",
        started=HistoryTimeEstimate(age=52, year=2018, month=3),
    )
    procedure = ProcedureHistoryObservation(
        patient_id="P-1",
        source=SourceLocator(
            scope="history-test",
            scope_kind=SourceScopeKind.MATERIALIZATION,
            source_profile="test",
            source_table="ProcHist",
            row_ordinal=0,
        ),
        category="breast",
        procedure="biopsy",
        detail="stereotactic_core_biopsy",
        laterality="L",
        reported_result="benign",
    )
    patient = Patient("P-1", history_observations=[medication, procedure])

    assert patient.medication_history == (medication,)
    assert patient.procedure_history == (procedure,)
    assert procedure.laterality is Laterality.LEFT
    assert patient.add_history_observation(medication) is medication
    assert patient.to_dict()["history_observations"] == [
        medication.to_dict(),
        procedure.to_dict(),
    ]


def test_history_source_is_optional_diagnostic_not_event_identity() -> None:
    patient = Patient("P-1")
    first = MedicationHistoryObservation(
        patient_id="P-1",
        source=source(),
        category="hormone",
        medication="estrogen",
    )
    conflicting = MedicationHistoryObservation(
        patient_id="P-1",
        source=source(),
        category="hormone",
        medication="progesterone",
    )
    patient.add_history_observation(first)

    patient.add_history_observation(conflicting)
    assert patient.medication_history == (first, conflicting)
    first.update(medication="updated")
    assert patient.medication_history[0].medication == "updated"
    with pytest.raises(ValueError, match="must match Patient"):
        patient.add_history_observation(
            PatientHistoryObservation(patient_id="P-2", source=source(2))
        )


def test_unkeyed_history_refresh_and_merge_require_explicit_event_identity():
    from embed_data_model import load_embed
    rows = [{"empi_anon":"P", "type":"H", "code":"E", "first_age":-5}]
    graph = load_embed(hormone_history=rows * 2).graph
    patient = graph.patient("P")
    assert len(patient.medication_history) == 2
    assert patient.medication_history[0].started.age == -5
    old = patient.medication_history
    report = load_embed(hormone_history=rows, into=graph, mode="merge")
    assert patient.medication_history == old
    assert any(i.code == "history_merge_requires_record_id" for i in report.issues)
    load_embed(hormone_history=rows, into=graph)
    assert len(patient.medication_history) == 1
    patient.replace_history("medication", [])
    assert not patient.medication_history


def test_explicit_history_key_refresh_preserves_reference_and_custom_values():
    from embed_data_model import load_embed
    columns = {"hormone_history":{"record_id":"record"}}
    rows = [{"empi_anon":"P", "type":"H", "code":"E", "record":"1", "comment":"old"}]
    graph = load_embed(hormone_history=rows, columns=columns).graph
    history = graph.patient("P").medication_history[0]
    history.project = {"keep":True}
    rows[0]["comment"] = "new"
    load_embed(hormone_history=rows, columns=columns, into=graph)
    assert graph.patient("P").medication_history == (history,)
    assert history.comment == "new" and history.project == {"keep":True}
