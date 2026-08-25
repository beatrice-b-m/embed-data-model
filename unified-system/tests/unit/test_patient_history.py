from __future__ import annotations

import pytest

from embed_toolkit.clinical.histories import (
    HistoryTimeEstimate,
    MedicationHistoryObservation,
    PatientHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import SourceLocator, SourceScopeKind


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
    with pytest.raises(ValueError, match="1..12"):
        HistoryTimeEstimate(month=13)


def test_patient_owns_extensible_source_identified_history() -> None:
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


def test_history_source_identity_cannot_change_meaning() -> None:
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

    with pytest.raises(ValueError, match="cannot represent different"):
        patient.add_history_observation(conflicting)
    with pytest.raises(ValueError, match="must match Patient"):
        patient.add_history_observation(
            PatientHistoryObservation(patient_id="P-2", source=source(2))
        )
