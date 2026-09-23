"""Reported patient history observations kept on the patient."""

import pytest

from embed_data_model.clinical.histories import (
    HistoryTimeEstimate,
    MedicationHistoryObservation,
    PatientHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_data_model.clinical.patients import Patient
from embed_data_model.core.primitives import Laterality
from embed_data_model.core.source import SourceRef


def source(row: int = 0) -> SourceRef:
    return SourceRef(
        "history-test",
        "HormoneHist",
        row,
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
        source=SourceRef(
            "history-test",
            "ProcHist",
            0,
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
