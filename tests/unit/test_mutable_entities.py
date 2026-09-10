"""Focused coverage for the bounded mutable clinical entity contract."""

from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest

from embed_data_model.clinical.attributes import (
    ExamAttributeName,
    ExamAttributeObservation,
    PatientAttributeAsOfPolicy,
    PatientAttributeName,
    PatientAttributeObservation,
    PatientObservationTimeBasis,
    UndatedObservationPolicy,
    select_patient_attribute_as_of,
)
from embed_data_model.clinical.exams import Exam
from embed_data_model.clinical.findings import Finding
from embed_data_model.clinical.histories import (
    HistoryTimeEstimate,
    MedicationHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_data_model.clinical.interpretations import ImagingInterpretation
from embed_data_model.clinical.pathology import Pathology, PathologyObservation
from embed_data_model.clinical.patients import Patient
from embed_data_model.clinical.procedures import Procedure, ProcedureIdentity
from embed_data_model.core.graph import DatasetGraph
from embed_data_model.core.primitives import Laterality


def procedure_identity() -> ProcedureIdentity:
    return ProcedureIdentity(
        patient_id="P-1",
        performed_date="2020-01-01",
        procedure_type="biopsy",
        laterality=Laterality.LEFT,
    )


def test_optional_source_observations_are_mutable_standalone() -> None:
    exam_observation = ExamAttributeObservation(
        "ACC-1", ExamAttributeName.DESCRIPTION, None
    )
    exam_observation.update(value="screening")
    assert exam_observation.source is None
    assert exam_observation.to_dict()["value"] == "screening"

    patient_observation = PatientAttributeObservation(
        "P-1", PatientAttributeName.SEX, "F", context_date=date(2020, 1, 1)
    )
    patient_observation.update(value="M")
    assert patient_observation.source is None
    assert patient_observation.value == "M"

    interpretation = ImagingInterpretation("ACC-1", "1")
    interpretation.update(assessment="4")
    assert interpretation.sources == ()
    assert interpretation.to_dict()["assessment"] == "4"


def test_as_of_selection_accepts_source_less_observations() -> None:
    observation = PatientAttributeObservation(
        "P-1",
        PatientAttributeName.BIRTH_YEAR,
        1970,
        context_date=date(2020, 1, 1),
        time_basis=PatientObservationTimeBasis.EXAM_DATE_CONTEXT,
    )
    selected = select_patient_attribute_as_of(
        [observation],
        patient_id="P-1",
        attribute=PatientAttributeName.BIRTH_YEAR,
        policy=PatientAttributeAsOfPolicy(
            as_of_date=date(2021, 1, 1),
            time_basis=PatientObservationTimeBasis.EXAM_DATE_CONTEXT,
            undated=UndatedObservationPolicy.EXCLUDE,
        ),
    )
    assert selected.selected_value == 1970
    assert selected.supporting_sources == (None,)
    assert selected.to_dict()["supporting_sources"] == [None]


def test_history_time_keeps_raw_numeric_values_without_quality_ranges() -> None:
    estimate = HistoryTimeEstimate(age=-4, year=0, month=13.5)

    assert estimate.age == -4
    assert type(estimate.age) is int
    assert estimate.year == 0
    assert estimate.month == 13.5
    assert estimate.to_dict() == {"age": -4, "year": 0, "month": 13.5}


def test_history_records_use_explicit_ids_and_snapshot_replacement() -> None:
    keyed = MedicationHistoryObservation(
        patient_id="P-1",
        category="hormone",
        medication="estrogen",
        record_id="med-1",
    )
    unkeyed = MedicationHistoryObservation(
        patient_id="P-1",
        category="hormone",
        medication="tamoxifen",
    )
    procedure = ProcedureHistoryObservation(
        patient_id="P-1",
        category="breast",
        procedure="biopsy",
    )
    patient = Patient("P-1", history_observations=[keyed, unkeyed, procedure])

    assert keyed.identity == ("P-1", "med-1")
    assert unkeyed.identity == ("P-1", None)
    assert patient.update_history("med-1", medication="progesterone") is keyed
    assert keyed.medication == "progesterone"

    incoming = MedicationHistoryObservation(
        patient_id="P-1",
        category="hormone",
        medication="tamoxifen",
        record_id="med-1",
    )
    patient.set_history_snapshot([incoming, procedure])
    assert patient.medication_history == (keyed,)
    assert keyed.medication == "tamoxifen"

    replacement = MedicationHistoryObservation(
        patient_id="P-1",
        category="hormone",
        medication="raloxifene",
    )
    patient.replace_history("medication", [replacement])
    assert patient.medication_history == (replacement,)
    assert patient.procedure_history == (procedure,)
    patient.replace_history("reported_procedure", [])
    assert patient.procedure_history == ()


def test_history_subclasses_and_nested_values_copy_independently() -> None:
    class LocalMedicationHistory(MedicationHistoryObservation):
        pass

    original = LocalMedicationHistory(
        patient_id="P-1",
        category="hormone",
        medication="estrogen",
        started=HistoryTimeEstimate(age=52),
    )
    copied = deepcopy(original)

    assert isinstance(copied, LocalMedicationHistory)
    assert copied is not original
    assert copied.started is not original.started
    copied.started.age = 99
    assert original.started.age == 52


def test_metadata_and_descriptors_are_editable_dicts() -> None:
    finding = Finding("ACC-1", Laterality.LEFT, 1, descriptors={"shape": "oval"})
    finding.descriptors["margin"] = "circumscribed"
    finding.descriptors = {"shape": "round"}
    assert finding.descriptors == {"shape": "round"}

    procedure = Procedure(procedure_identity(), metadata={"reader": "A"})
    procedure.metadata["reviewed"] = True
    assert procedure.metadata == {"reader": "A", "reviewed": True}

    pathology = Pathology(
        ("P-1", "report-1"),
        diagnosis="reported",
        descriptors=[PathologyObservation("ADH", "slot-1", 1)],
        metadata={"source": "test"},
    )
    pathology.descriptors = tuple(pathology.descriptors) + ("DCIS",)
    pathology.metadata["reviewed"] = True
    assert pathology.descriptors[-1] == "DCIS"
    assert pathology.metadata["reviewed"] is True


def test_registered_identity_fields_require_rekey() -> None:
    graph = DatasetGraph()
    exam = graph.register(Exam("ACC-1"))

    with pytest.raises(AttributeError, match="rekey"):
        exam.accession_number = "ACC-2"

    exam.rekey(accession_number="ACC-2")
    assert graph.exam("ACC-2") is exam

    pathology = graph.register(Pathology(("P-1", "report-1"), diagnosis="x"))
    with pytest.raises(AttributeError, match="rekey"):
        pathology.identity = ("P-1", "report-2")
