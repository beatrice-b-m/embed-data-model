"""Regression coverage for the mutable graph review findings."""

import pytest

from embed_toolkit import DatasetGraph, Exam, MammogramImage


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
