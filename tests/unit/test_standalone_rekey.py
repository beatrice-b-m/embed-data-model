"""Standalone identity changes preserve local tree semantics."""

from __future__ import annotations

from datetime import date

import pytest

from embed_data_model import (
    CancerRegistryEntry,
    DatasetGraph,
    Exam,
    Finding,
    Laterality,
    MammogramImage,
    Patient,
    Procedure,
    ProcedureIdentity,
    RegionOfInterest,
)
from embed_data_model.clinical.attributes import (
    ExamAttributeName,
    ExamAttributeObservation,
    PatientAttributeName,
    PatientAttributeObservation,
)
from embed_data_model.clinical.histories import MedicationHistoryObservation
from embed_data_model.clinical.interpretations import ImagingInterpretation
from embed_data_model.imaging.landmarks import ImageLandmark, LandmarkType


def test_standalone_exam_and_image_rekeys_preserve_tree_objects() -> None:
    class ResearchPatient(Patient):
        pass

    patient = ResearchPatient("P-1")
    patient.research = {"labels": ["source"]}
    exam = patient.add_exam(Exam("A-1"))
    interpretation = ImagingInterpretation("A-1", "1")
    finding = exam.add_finding(
        Finding("A-1", Laterality.LEFT, "1", interpretation=interpretation)
    )
    exam_observation = exam.add_attribute_observation(
        ExamAttributeObservation("A-1", ExamAttributeName.DESCRIPTION, "screening")
    )
    image = exam.add_image(
        MammogramImage(
            "image-1",
            accession_number="A-1",
            landmarks=(ImageLandmark(10, 20, LandmarkType.NIPPLE),),
        )
    )
    landmark = image.landmarks[0]
    roi = image.add_roi(RegionOfInterest((0, 0, 10, 10), "image-1", "0"))

    exam.rekey(accession_number="B-1")

    assert exam.accession_number == "B-1"
    assert finding.accession_number == "B-1"
    assert finding.interpretation is interpretation
    assert interpretation.identity == ("B-1", "1")
    assert exam_observation.accession_number == "B-1"
    assert exam.breast_sides[Laterality.LEFT].accession_number == "B-1"
    assert image.accession_number == "B-1"

    image.update(image_id="image-2")

    assert image.image_id == "image-2"
    assert image.rois == (roi,)
    assert roi.image_id == "image-2"
    assert image.landmarks == (landmark,)
    assert landmark.image_id == "image-2"
    assert patient.research == {"labels": ["source"]}
    assert all(
        item.graph is None
        for item in (patient, exam, finding, interpretation, image, roi, landmark)
    )

    graph = DatasetGraph()
    graph.register(patient)
    assert graph.exam("B-1") is exam
    assert graph.finding("B-1", "1") is finding
    assert graph.image("image-2") is image
    assert graph.roi("image-2", "0") is roi
    assert not graph.unresolved_references


def test_standalone_patient_rekey_updates_owners_and_embedded_context_only() -> None:
    patient_observation = PatientAttributeObservation(
        "P-1", PatientAttributeName.SEX, "F", context_date=date(2020, 1, 1)
    )
    history = MedicationHistoryObservation(
        "P-1", category="hormone", medication="estrogen"
    )
    patient = Patient(
        "P-1",
        attribute_observations=(patient_observation,),
        history_observations=(history,),
    )
    exam = patient.add_exam(Exam("A-1", asserted_patient_ids=("P-1",)))
    finding = exam.add_finding(Finding("A-1", Laterality.LEFT, "1"))
    procedure_identity = ProcedureIdentity(
        "P-1", "2020-01-01", "biopsy", Laterality.LEFT
    )
    procedure = finding.add_procedure(Procedure(procedure_identity))
    registry = exam.add_registry_entry(CancerRegistryEntry("P-1", "registry-1"))
    image = exam.add_image(
        MammogramImage("image-1", accession_number="A-1", patient_id="source-P")
    )

    patient.rekey(patient_id="P-2")

    assert patient.patient_id == "P-2"
    assert exam.patient_id == "P-2"
    assert exam.owner_explicit
    assert exam.asserted_patient_ids == {"P-1"}
    assert patient_observation.patient_id == "P-2"
    assert history.patient_id == "P-2"
    assert image.patient_id == "source-P"
    assert procedure.identity is procedure_identity
    assert procedure.identity.patient_id == "P-1"
    assert registry.identity == ("P-1", "registry-1")
    assert all(
        item.graph is None
        for item in (patient, exam, finding, procedure, registry, image)
    )

    graph = DatasetGraph()
    graph.register(patient)
    assert graph.patient("P-2") is patient
    assert graph.exam("A-1") is exam
    assert graph.procedure(procedure_identity) is procedure
    assert graph.registry_entry("P-1", "registry-1") is registry
    assert not graph.unresolved_references


def test_standalone_rekey_rewrites_carried_parent_targets() -> None:
    source = DatasetGraph()
    patient = source.register(Patient("P-1"))
    exam = patient.add_exam(Exam("A-1"))
    finding = exam.add_finding(Finding("A-1", Laterality.LEFT, "1"))
    detached = source.pop(exam)

    detached.rekey(accession_number="B-1")

    destination = DatasetGraph()
    destination.register(Patient("P-1"))
    destination.register(detached)
    assert destination.exam("B-1") is detached
    assert destination.finding("B-1", "1") is finding
    assert not destination.unresolved_references


def test_standalone_rekey_rewrites_internal_link_collections() -> None:
    source = DatasetGraph()
    exam = source.register(Exam("A-1"))
    source.set_linked_accessions(exam, ["A-1"])
    detached = source.pop(exam)

    detached.rekey(accession_number="B-1")

    assert detached.linked_accessions == {"B-1"}
    destination = DatasetGraph()
    destination.register(detached)
    assert detached.linked_exams == (detached,)
    assert not destination.unresolved_references


def test_standalone_rekey_preserves_external_link_targets() -> None:
    source = DatasetGraph()
    exam = source.register(Exam("A-1"))
    source.set_linked_accessions(exam, ["external"])
    detached = source.pop(exam)

    detached.rekey(accession_number="B-1")

    assert detached.linked_accessions == {"external"}


def test_standalone_self_link_rekeys_before_first_registration() -> None:
    exam = Exam("A-1", linked_accessions=("A-1",))

    exam.rekey(accession_number="B-1")

    assert exam.linked_accessions == {"B-1"}
    graph = DatasetGraph()
    graph.register(exam)
    assert exam.linked_exams == (exam,)
    assert not graph.unresolved_references


def test_unhashable_subclasses_rekey_after_pop() -> None:
    class UnhashableFinding(Finding):
        __hash__ = None

        def __eq__(self, other: object) -> bool:
            return self is other

    class UnhashableExam(Exam):
        __hash__ = None

        def __eq__(self, other: object) -> bool:
            return self is other

    source = DatasetGraph()
    patient = source.register(Patient("P-1"))
    exam = patient.add_exam(UnhashableExam("A-1"))
    finding = exam.add_finding(UnhashableFinding("A-1", Laterality.LEFT, "1"))
    source.set_linked_accessions(exam, ["A-1"])
    detached = source.pop(exam)

    finding.rekey(finding_number="2")
    detached.rekey(accession_number="B-1")

    destination = DatasetGraph()
    destination.register(Patient("P-1"))
    destination.register(detached)
    assert destination.finding("B-1", "2") is finding
    assert detached.linked_accessions == {"B-1"}
    assert detached.linked_exams == (detached,)
    assert not destination.unresolved_references


def test_standalone_rekey_preflights_reachable_semantic_collisions() -> None:
    patient = Patient("P-1")
    exam = patient.add_exam(Exam("A-1"))
    first = exam.add_finding(Finding("A-1", Laterality.LEFT, "1"))
    second = exam.add_finding(Finding("A-1", Laterality.RIGHT, "2"))
    identity = ProcedureIdentity("P-1", "2020-01-01", "biopsy", Laterality.LEFT)
    first.add_procedure(Procedure(identity))
    second.add_procedure(Procedure(identity))

    with pytest.raises(ValueError, match="collision"):
        exam.rekey(accession_number="B-1")

    assert exam.accession_number == "A-1"
    assert first.accession_number == "A-1"
    assert second.accession_number == "A-1"


def test_standalone_rekey_rejects_owned_descendant_before_mutation() -> None:
    owned = DatasetGraph()
    child = owned.register(Exam("A-1"))
    patient = Patient("P-1")
    patient._attach_local(child)

    with pytest.raises(ValueError, match="graph-owned descendant"):
        patient.rekey(patient_id="P-2")

    assert patient.patient_id == "P-1"
    assert child.patient_id == "P-1"
    assert child.graph is owned
