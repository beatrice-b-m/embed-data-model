"""Membership contract: identity, local updates, and owning movement."""
import pytest

from embed_toolkit import DatasetGraph, Exam, Finding, MammogramImage, Patient, RegionOfInterest
from embed_toolkit.clinical.procedures import Procedure, ProcedureIdentity
from embed_toolkit.core.primitives import Laterality


def tree():
    patient = Patient("P")
    exam = patient.add_exam(Exam("A"))
    finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))
    image = exam.add_image(MammogramImage("I", accession_number="A"))
    roi = image.add_roi(RegionOfInterest((0, 0, 10, 10), "I", "0"))
    return patient, exam, finding, image, roi


def test_register_mutate_rekey_and_pop_preserve_exclusive_references():
    patient, exam, finding, image, roi = tree()
    graph = DatasetGraph()
    graph.register(patient)
    assert graph.register(patient) is patient
    exam.add_finding(Finding("A", Laterality.RIGHT, "2"))
    assert graph.finding("A", "2") is exam.findings[1]
    graph.update(exam, description="reviewed")
    assert exam.description == "reviewed"
    graph.rekey(image, image_id="processed")
    assert graph.image("I") is None
    assert graph.roi("processed", "0") is roi
    assert roi.image_id == "processed"
    detached = graph.pop(exam)
    assert detached is exam and image.graph is None
    assert not patient.exams and graph.exam("A") is None
    other = DatasetGraph()
    other.register(detached)
    assert other.finding("A", "1") is finding
    assert other.roi("processed", "0") is roi


def test_collision_is_checked_before_cross_graph_movement():
    source, target = DatasetGraph(), DatasetGraph()
    patient = source.register(Patient("P"))
    target.register(Patient("P"))
    with pytest.raises(ValueError, match="collision"):
        target.register(patient)
    assert patient.graph is source and source.patient("P") is patient


def test_claim_conflicts_are_order_independent_and_resolvable():
    for claims in (("P", "Q"), ("Q", "P")):
        graph = DatasetGraph()
        graph.register(Patient("P"))
        graph.register(Patient("Q"))
        exam = graph.register(Exam("A"))
        for claim in claims:
            graph.claim_patient(exam, [claim])
        assert exam.patient_id is None
        assert not graph.patient("P").exams and not graph.patient("Q").exams
        image = graph.register(MammogramImage("I", accession_number="A", patient_id="Q"))
        assert exam.images == (image,)
        graph.assign_patient(exam, "P")
        graph.claim_patient(exam, ["Q"])
        assert graph.patient("P").exams == (exam,)
        assert image.patient_id == "Q" and exam.asserted_patient_ids == {"P", "Q"}


def test_pending_parents_resolve_without_global_scan():
    graph = DatasetGraph()
    image = graph.register(MammogramImage("I", accession_number="A"))
    assert graph.unresolved_references
    exam = graph.register(Exam("A", patient_id="P"))
    patient = graph.register(Patient("P"))
    assert patient.exams == (exam,) and exam.images == (image,)
    assert not graph.unresolved_references
    before = dict(graph.operation_counts)
    graph.update(exam, description="new")
    assert graph.operation_counts["resolved"] == before["resolved"]


def test_shared_procedure_copies_only_at_extraction_boundary():
    graph = DatasetGraph()
    patient = Patient("P")
    first = patient.add_exam(Exam("A"))
    second = patient.add_exam(Exam("B"))
    proc = Procedure(ProcedureIdentity("P", "2020-01-01", "biopsy", Laterality.LEFT))
    first.add_procedure(proc)
    second.add_procedure(proc)
    proc.metadata["nested"] = {"values": [1]}
    graph.register(patient)
    extracted = graph.pop(first)
    assert second.procedures == (proc,)
    copied = extracted.procedures[0]
    assert copied is not proc and copied.identity == proc.identity
    copied.metadata["nested"]["values"].append(2)
    assert proc.metadata["nested"]["values"] == [1]
    assert copied.graph is None and proc.graph is graph


def test_link_cycles_remain_references_across_movement():
    graph = DatasetGraph()
    a = graph.register(Exam("A"))
    b = graph.register(Exam("B"))
    graph.set_linked_accessions(a, ["B"])
    assert b in a.linked_exams and a in b.linked_exams
    other = DatasetGraph()
    other.register(a)
    assert b.graph is graph and a.graph is other
    assert not a.linked_exams and not b.linked_exams
    assert a.linked_accessions == {"B"}
    other.register(b)
    assert b in a.linked_exams and a in b.linked_exams
    other.to_dict()
