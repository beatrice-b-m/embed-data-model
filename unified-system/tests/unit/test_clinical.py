from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from embed_toolkit.clinical.cohorts import Cohort
from embed_toolkit.clinical.exams import BreastSide, Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.clinical.procedures import PathologyEvent, Procedure
from embed_toolkit.core.anatomy import (
    AnatomicalPosition,
    ClockFacePosition,
    DepthThird,
    Quadrant,
)
from embed_toolkit.core.primitives import Laterality


def test_finding_identity_includes_accession_side_and_number() -> None:
    left = Finding("ACC-1", Laterality.LEFT, 1)
    right = Finding("ACC-1", Laterality.RIGHT, 1)

    assert left.identity == ("ACC-1", Laterality.LEFT, "1")
    assert right.identity == ("ACC-1", Laterality.RIGHT, "1")
    assert left.finding_id == "ACC-1:L:1"
    assert left.identity != right.identity


def test_exam_deduplicates_findings_by_stable_identity() -> None:
    exam = Exam("ACC-1")
    first = exam.add_finding(Finding("ACC-1", "L", 7))
    duplicate = exam.add_finding(Finding("ACC-1", Laterality.LEFT, "7"))

    assert duplicate is first
    assert exam.findings == [first]


def test_breast_side_aggregates_findings_procedures_and_pathology() -> None:
    finding = Finding("ACC-2", Laterality.RIGHT, "3")
    procedure = finding.add_procedure(Procedure(procedure_id="P1", procedure_type="biopsy"))
    pathology = procedure.add_pathology_event(
        PathologyEvent(pathology_id="PATH-1", diagnosis="benign")
    )

    side = BreastSide(Laterality.RIGHT)
    side.add_finding(finding)

    assert side.findings == [finding]
    assert side.procedures == (procedure,)
    assert side.pathology_events == (pathology,)


def test_breast_side_rejects_wrong_side_finding() -> None:
    side = BreastSide(Laterality.LEFT)

    with pytest.raises(ValueError):
        side.add_finding(Finding("ACC-3", Laterality.RIGHT, 1))


def test_procedure_rows_attach_to_finding_without_replacing_each_other() -> None:
    finding = Finding("ACC-4", Laterality.LEFT, "2")
    first = finding.add_procedure(Procedure(procedure_id="BIOPSY"))
    second = finding.add_procedure(Procedure(procedure_id="SURGERY"))

    assert finding.procedures == [first, second]
    assert first.accession_number == "ACC-4"
    assert first.laterality is Laterality.LEFT
    assert first.finding_number == "2"


def test_exam_aggregates_side_views_procedures_and_pathology() -> None:
    left = Finding("ACC-5", Laterality.LEFT, 1)
    left_procedure = left.add_procedure(Procedure(procedure_id="LP"))
    left_pathology = left_procedure.add_pathology_event(PathologyEvent(diagnosis="dcis"))
    right = Finding("ACC-5", Laterality.RIGHT, 1)
    right_procedure = right.add_procedure(Procedure(procedure_id="RP"))

    exam = Exam("ACC-5")
    exam.extend_findings([left, right])

    sides = exam.breast_sides
    assert set(sides) == {Laterality.LEFT, Laterality.RIGHT}
    assert sides[Laterality.LEFT].findings == [left]
    assert sides[Laterality.RIGHT].findings == [right]
    assert exam.procedures == (left_procedure, right_procedure)
    assert exam.pathology_events == (left_pathology,)


def test_finding_preserves_source_fields_anatomy_descriptors_and_warnings() -> None:
    position = AnatomicalPosition(
        laterality=Laterality.LEFT,
        quadrant=Quadrant(Laterality.LEFT, depth=DepthThird.POSTERIOR),
        clock_position=ClockFacePosition(2),
        distance_from_nipple_cm=4.5,
    )

    finding = Finding(
        accession_number="ACC-6",
        laterality="left",
        finding_number=9,
        anatomical_position=position,
        raw_source_fields={"numfind": 9, "loc": "C2"},
        source_location_codes={"loc": "C2"},
        source_depth_codes={"depth": "P"},
        descriptors={"mass": {"shape": "oval"}},
        normalization_warnings=["unknown margin code X"],
    )

    serialized = asdict(finding)
    plain = finding.to_dict()

    assert serialized["raw_source_fields"] == {"numfind": 9, "loc": "C2"}
    assert serialized["source_location_codes"] == {"loc": "C2"}
    assert serialized["source_depth_codes"] == {"depth": "P"}
    assert serialized["descriptors"] == {"mass": {"shape": "oval"}}
    assert serialized["normalization_warnings"] == ["unknown margin code X"]
    assert serialized["anatomical_position"]["distance_from_nipple_cm"] == 4.5
    assert plain["laterality"] == "L"
    assert plain["anatomical_position"]["clock_position"]["hour"] == 2
    json.dumps(plain)


def test_patient_and_cohort_aggregate_serialization_friendly_dataclasses() -> None:
    finding = Finding("ACC-7", Laterality.LEFT, 1)
    exam = Exam("ACC-7")
    exam.add_finding(finding)
    patient = Patient("P1")
    patient.add_exam(exam)
    cohort = Cohort("training")
    cohort.add_patient(patient)

    serialized = asdict(cohort)
    plain = cohort.to_dict()

    assert cohort.exams == (exam,)
    assert cohort.findings == (finding,)
    assert serialized["patients"][0]["exams"][0]["findings"][0]["finding_number"] == "1"
    assert serialized["patients"][0]["exams"][0]["patient_id"] == "P1"
    assert plain["patients"][0]["exams"][0]["findings"][0]["laterality"] == "L"
    json.dumps(plain)
