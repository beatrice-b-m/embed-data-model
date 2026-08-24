from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from embed_toolkit.clinical.cohorts import Cohort
from embed_toolkit.clinical.exams import BreastSide, Exam
from embed_toolkit.clinical.findings import Finding, FindingRecordType
from embed_toolkit.clinical.patients import Patient
from embed_toolkit.clinical.procedures import Procedure, ProcedureIdentity
from embed_toolkit.core.anatomy import (
    AnatomicalPosition,
    ClockFacePosition,
    DepthThird,
    Quadrant,
)
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import (
    ResolutionState,
    SourceLocator,
    SourceOccurrence,
    SourceScopeKind,
)


def test_finding_identity_uses_accession_and_number_with_side_as_attribute() -> None:
    left = Finding("ACC-1", Laterality.LEFT, 1)
    right = Finding("ACC-1", Laterality.RIGHT, 1)

    assert left.identity == ("ACC-1", "1")
    assert right.identity == ("ACC-1", "1")
    assert left.finding_id == "ACC-1:1"
    assert left.identity == right.identity


def test_exam_deduplicates_findings_by_stable_identity() -> None:
    exam = Exam("ACC-1")
    first = exam.add_finding(Finding("ACC-1", "L", 7))
    duplicate = exam.add_finding(Finding("ACC-1", Laterality.LEFT, "7"))

    assert duplicate is first
    assert exam.findings == [first]


def test_exam_flags_conflicting_attributes_for_one_finding_identity() -> None:
    exam = Exam("ACC-1")
    first = exam.add_finding(Finding("ACC-1", "L", 7, finding_type="mass"))
    duplicate = exam.add_finding(Finding("ACC-1", "R", 7, finding_type="calc"))

    assert duplicate is first
    assert [issue["attribute"] for issue in first.validation_issues] == [
        "laterality",
        "finding_type",
    ]
    assert first.metadata["source_row_count"] == 2


def test_negative_nine_remains_a_governed_no_finding_sentinel() -> None:
    finding = Finding("ACC-1", Laterality.BILATERAL, -9)

    assert finding.record_type is FindingRecordType.NO_FINDING_SENTINEL
    assert finding.to_dict()["record_type"] == "no_finding_sentinel"


def test_breast_side_contains_findings_without_attribution_edges() -> None:
    finding = Finding("ACC-2", Laterality.RIGHT, "3")

    side = BreastSide("ACC-2", Laterality.RIGHT)
    side.add_finding(finding)

    assert side.findings == [finding]
    assert not hasattr(side, "procedures")
    assert not hasattr(finding, "procedures")


def test_breast_side_rejects_wrong_side_finding() -> None:
    side = BreastSide("ACC-3", Laterality.LEFT)

    with pytest.raises(ValueError):
        side.add_finding(Finding("ACC-3", Laterality.RIGHT, 1))


def test_procedure_owns_resolved_source_evidence_not_finding_references() -> None:
    identity = ProcedureIdentity(
        patient_id="P1",
        performed_date="2020-01-01",
        procedure_type="biopsy",
        laterality="R",
    )
    source = SourceOccurrence(
        locator=SourceLocator(
            scope="materialization-1",
            scope_kind=SourceScopeKind.MATERIALIZATION,
            source_profile="embed_context_internal",
            source_table="magview",
            row_ordinal=1,
        ),
        raw_values={"procedure_id": "source-only-id"},
        resolution_state=ResolutionState.RESOLVED,
    )
    procedure = Procedure(identity=identity, source_occurrences=[source])

    assert procedure.identity is identity
    assert procedure.source_occurrences == [source]
    assert not hasattr(procedure, "finding_number")
    assert not hasattr(procedure, "finding_references")
    assert procedure.to_dict()["source_occurrences"][0]["raw_values"] == {
        "procedure_id": "source-only-id"
    }


def test_exam_aggregates_side_views_without_procedure_containment() -> None:
    left = Finding("ACC-5", Laterality.LEFT, 1)
    right = Finding("ACC-5", Laterality.RIGHT, 2)

    exam = Exam("ACC-5")
    exam.extend_findings([left, right])

    sides = exam.breast_sides
    assert set(sides) == {Laterality.LEFT, Laterality.RIGHT}
    assert sides[Laterality.LEFT].findings == [left]
    assert sides[Laterality.RIGHT].findings == [right]
    assert not hasattr(exam, "procedures")


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

    plain = cohort.to_dict()

    assert cohort.exams == (exam,)
    assert cohort.findings == (finding,)
    assert plain["patients"][0]["exams"][0]["findings"][0]["finding_number"] == "1"
    assert plain["patients"][0]["exams"][0]["patient_id"] == "P1"
    assert plain["patients"][0]["exams"][0]["findings"][0]["laterality"] == "L"
    assert plain["patients"][0]["exams"][0]["breast_sides"] == [
        {
            "accession_number": "ACC-7",
            "laterality": "L",
            "finding_references": [
                {"accession_number": "ACC-7", "finding_number": "1"}
            ],
            "image_references": [],
        }
    ]
    json.dumps(plain)
