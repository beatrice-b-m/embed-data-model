"""Regression coverage for the mutable graph review findings."""

import pytest

from embed_toolkit import CancerRegistryEntry, DatasetGraph, Exam, MammogramImage, Patient


def test_source_sop_collision_is_preflighted_for_update() -> None:
    graph = DatasetGraph()
    first = graph.register(MammogramImage("I", source_sop_instance_uid="S1"))
    second = graph.register(MammogramImage("J", source_sop_instance_uid="S2"))

    with pytest.raises(ValueError, match="Source SOP collision"):
        first.update(source_sop_instance_uid="S2")

    assert first.source_sop_instance_uid == "S1"
    assert graph.source_image("S1") is first
    assert graph.source_image("S2") is second


def test_source_sop_collision_is_preflighted_for_mixed_rekey() -> None:
    graph = DatasetGraph()
    first = graph.register(MammogramImage("I", source_sop_instance_uid="S1"))
    second = graph.register(MammogramImage("J", source_sop_instance_uid="S2"))

    with pytest.raises(ValueError, match="Source SOP collision"):
        graph.rekey(
            first,
            image_id="renamed",
            source_sop_instance_uid="S2",
        )

    assert first.image_id == "I"
    assert first.source_sop_instance_uid == "S1"
    assert graph.image("I") is first
    assert graph.image("renamed") is None
    assert graph.source_image("S1") is first
    assert graph.source_image("S2") is second


def test_derivative_cannot_become_original_with_an_owned_source_sop() -> None:
    graph = DatasetGraph()
    original = graph.register(MammogramImage("original", source_sop_instance_uid="S"))
    derivative = graph.register(
        MammogramImage("derivative", source_sop_instance_uid="S", derived_from="original")
    )

    with pytest.raises(ValueError, match="Source SOP collision"):
        derivative.update(derived_from=None)

    assert derivative.derived_from == "original"
    assert graph.source_image("S") is original


def test_one_sided_link_rekey_removes_old_reverse_entry() -> None:
    graph = DatasetGraph()
    source = graph.register(Exam("A"))
    target = graph.register(Exam("B"))
    graph.set_linked_accessions(source, ["B"])

    source.rekey(accession_number="C")

    assert target.linked_exams == (source,)
    graph.set_linked_accessions(source, [])
    assert not target.linked_exams


def test_self_link_rekey_moves_both_reference_endpoints() -> None:
    graph = DatasetGraph()
    exam = graph.register(Exam("A"))
    graph.set_linked_accessions(exam, ["A"])

    exam.rekey(accession_number="B")

    assert exam.linked_accessions == {"B"}
    assert exam.linked_exams == (exam,)
    graph.set_linked_accessions(exam, [])
    assert not exam.linked_exams


def test_pop_carries_incoming_link_until_source_is_registered() -> None:
    source = DatasetGraph()
    source_exam = source.register(Exam("A"))
    moved_exam = source.register(Exam("B"))
    source.set_linked_accessions(source_exam, ["B"])

    destination = DatasetGraph()
    destination.register(source.pop(moved_exam))

    assert destination.unresolved_references
    assert not destination.exam("B").linked_exams
    destination.register(Exam("A"))
    assert destination.exam("A").linked_exams == (moved_exam,)
    assert moved_exam.linked_exams == (destination.exam("A"),)


def test_pop_carries_incoming_registry_reference_until_source_is_registered() -> None:
    source = DatasetGraph()
    source_exam = source.register(Exam("A"))
    entry = source.register(CancerRegistryEntry("P", "1"))
    source.set_registry_assignments(source_exam, [("P", "1")])

    destination = DatasetGraph()
    destination.register(source.pop(entry))

    assert destination.unresolved_references
    destination.register(Exam("A"))
    assert destination.exam("A").registry_entries == (entry,)


def test_pop_incoming_link_targets_current_key_after_standalone_rekey() -> None:
    source = DatasetGraph()
    source_exam = source.register(Exam("A"))
    moved_exam = source.register(Exam("B"))
    source.set_linked_accessions(source_exam, ["B"])

    moved_exam = source.pop(moved_exam)
    moved_exam.rekey(accession_number="C")
    destination = DatasetGraph()
    destination.register(moved_exam)
    destination.register(Exam("A"))

    assert destination.exam("A").linked_exams == (moved_exam,)
    assert moved_exam.linked_exams == (destination.exam("A"),)


def test_pop_does_not_carry_internal_link_as_crossing_reference() -> None:
    source = DatasetGraph()
    patient = source.register(Patient("P"))
    first = patient.add_exam(Exam("A"))
    patient.add_exam(Exam("B"))
    source.set_linked_accessions(first, ["B"])

    destination = DatasetGraph()
    destination.register(source.pop(patient))

    assert not destination.unresolved_references
    assert destination.exam("A").linked_exams == (destination.exam("B"),)
    assert destination.exam("B").linked_exams == (destination.exam("A"),)


def test_register_preserves_explicit_exam_owner_without_new_source_claim() -> None:
    patient = Patient("P")
    exam = patient.add_exam(Exam("A"))
    patient.rekey(patient_id="Q")

    graph = DatasetGraph()
    graph.register(patient)

    assert exam.patient_id == "Q"
    assert exam.asserted_patient_ids == {"P"}
    assert graph.patient("Q").exams == (exam,)
    assert not graph.unresolved_references


def test_registered_patient_rekey_preserves_source_scoped_child_identities() -> None:
    patient = Patient("P")
    exam = patient.add_exam(Exam("A", asserted_patient_ids=("P",)))
    image = exam.add_image(MammogramImage("I", accession_number="A", patient_id="P"))
    entry = exam.add_registry_entry(CancerRegistryEntry("P", "R"))

    graph = DatasetGraph()
    graph.register(patient)
    graph.rekey(patient, patient_id="Q")

    assert exam.patient_id == "Q"
    assert exam.owner_explicit
    assert exam.asserted_patient_ids == {"P"}
    assert image.patient_id == "P"
    assert entry.identity == ("P", "R")

    moved = graph.pop(patient)
    destination = DatasetGraph()
    destination.register(moved)
    assert destination.exam("A").asserted_patient_ids == {"P"}
    assert destination.exam("A").patient_id == "Q"
    assert destination.image("I").patient_id == "P"
    assert destination.registry_entry("P", "R") is entry
    assert not destination.unresolved_references


def test_register_canonicalizes_internal_link_targets_after_member_rekey() -> None:
    source = DatasetGraph()
    patient = source.register(Patient("P"))
    first = patient.add_exam(Exam("A"))
    second = patient.add_exam(Exam("B"))
    source.set_linked_accessions(first, ["B"])

    detached = source.pop(patient)
    second.rekey(accession_number="C")

    destination = DatasetGraph()
    destination.register(detached)

    assert first.linked_accessions == {"C"}
    assert first.linked_exams == (second,)
    assert not destination.unresolved_references


def test_register_canonicalizes_internal_registry_targets_after_member_rekey() -> None:
    source = DatasetGraph()
    patient = source.register(Patient("P"))
    exam = patient.add_exam(Exam("A"))
    entry = exam.add_registry_entry(CancerRegistryEntry("P", "1"))
    source.set_registry_assignments(exam, [("P", "1")])

    detached = source.pop(patient)
    entry.rekey(registry_id="2")

    destination = DatasetGraph()
    destination.register(detached)

    assert exam.registry_references == {("P", "2")}
    assert exam.registry_entries == (entry,)
    assert destination.registry_entry("P", "2") is entry
    assert not destination.unresolved_references
