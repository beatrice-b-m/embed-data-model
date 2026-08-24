from __future__ import annotations

import json

import pytest

from embed_toolkit.adapters.embed import build_clinical_tables, build_image_tables
from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.core.primitives import Laterality, ViewPosition
from embed_toolkit.imaging.images import MammogramImage


def image(
    image_id: str,
    laterality: Laterality,
    *,
    accession: str = "ACC-1",
) -> MammogramImage:
    return MammogramImage(
        image_id=image_id,
        laterality=laterality,
        view_position=ViewPosition.CC,
        accession_number=accession,
        patient_id="P-1",
    )


def test_exam_sides_are_persistent_accession_scoped_children() -> None:
    exam = Exam("ACC-1", patient_id="P-1")

    first = exam.ensure_side(Laterality.LEFT)
    second = exam.ensure_side(Laterality.LEFT)

    assert first is second
    assert first.identity == ("ACC-1", Laterality.LEFT)
    assert exam.breast_sides == {Laterality.LEFT: first}


def test_bilateral_finding_projects_to_both_unilateral_children() -> None:
    exam = Exam("ACC-1")
    finding = exam.add_finding(Finding("ACC-1", Laterality.BILATERAL, "1"))

    assert set(exam.breast_sides) == {Laterality.LEFT, Laterality.RIGHT}
    assert exam.breast_sides[Laterality.LEFT].findings == [finding]
    assert exam.breast_sides[Laterality.RIGHT].findings == [finding]
    assert all(
        side.laterality.is_unilateral for side in exam.breast_sides.values()
    )


def test_image_can_create_side_without_finding_and_unknown_stays_exam_only() -> None:
    exam = Exam("ACC-1")
    right = image("right-cc", Laterality.RIGHT)
    unknown = image("unknown", Laterality.UNKNOWN)

    exam.add_image(right)
    exam.add_image(unknown)

    assert exam.images == [right, unknown]
    assert set(exam.breast_sides) == {Laterality.RIGHT}
    assert exam.breast_sides[Laterality.RIGHT].findings == []
    assert exam.breast_sides[Laterality.RIGHT].images == [right]
    assert all(unknown not in side.images for side in exam.breast_sides.values())


def test_exam_image_containment_validates_accession_and_deduplicates_identity() -> None:
    exam = Exam("ACC-1")
    first = image("left-cc", Laterality.LEFT)
    duplicate = image("left-cc", Laterality.LEFT)

    assert exam.add_image(first) is first
    assert exam.add_image(first) is first
    assert exam.add_image(duplicate) is first
    assert exam.images == [first]
    assert exam.breast_sides[Laterality.LEFT].images == [first]

    with pytest.raises(ValueError, match="accession_number must match Exam"):
        exam.add_image(image("other", Laterality.LEFT, accession="ACC-2"))


def test_exam_serialization_owns_objects_once_and_sides_use_references() -> None:
    exam = Exam("ACC-1", patient_id="P-1")
    finding = exam.add_finding(Finding("ACC-1", Laterality.BILATERAL, "1"))
    left_image = exam.add_image(image("left-cc", Laterality.LEFT))

    serialized = exam.to_dict()

    assert len(serialized["findings"]) == 1
    assert len(serialized["images"]) == 1
    assert serialized["breast_sides"] == [
        {
            "accession_number": "ACC-1",
            "laterality": "L",
            "finding_references": [
                {"accession_number": "ACC-1", "finding_number": "1"}
            ],
            "image_references": ["left-cc"],
        },
        {
            "accession_number": "ACC-1",
            "laterality": "R",
            "finding_references": [
                {"accession_number": "ACC-1", "finding_number": "1"}
            ],
            "image_references": [],
        },
    ]
    assert finding is exam.breast_sides[Laterality.LEFT].findings[0]
    assert left_image is exam.breast_sides[Laterality.LEFT].images[0]
    json.dumps(serialized)


def test_table_builders_create_persistent_sides_and_bind_image_patient() -> None:
    clinical = build_clinical_tables(
        [{"empi_anon": "P-1", "acc_anon": "ACC-1", "numfind": "1"}],
        source_scope="clinical-1",
    )
    images = build_image_tables(
        [
            {
                "image_id": "left-cc",
                "empi_anon": "P-1",
                "acc_anon": "ACC-1",
                "ImageLateralityFinal": "L",
                "ViewPosition": "CC",
            }
        ]
    )

    exam = clinical.exams[0]
    assert exam.breast_sides[Laterality.LEFT] is exam.breast_sides[Laterality.LEFT]
    assert set(exam.breast_sides) == {Laterality.LEFT, Laterality.RIGHT}
    assert images.images[0].patient_id == "P-1"
    assert exam.images == []
