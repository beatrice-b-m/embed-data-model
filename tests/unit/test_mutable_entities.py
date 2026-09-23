"""Focused coverage for the bounded mutable clinical entity contract."""

from __future__ import annotations


import pytest

from embed_data_model.clinical.attributes import (
    ExamAttributeName,
    ExamAttributeObservation,
)
from embed_data_model.clinical.exams import Exam
from embed_data_model.clinical.findings import Finding
from embed_data_model.clinical.interpretations import ImagingInterpretation
from embed_data_model.clinical.pathology import Pathology, PathologyObservation
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

    interpretation = ImagingInterpretation()
    interpretation.update(assessment="4")
    assert interpretation.sources == ()
    assert interpretation.to_dict()["assessment"] == "4"


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
