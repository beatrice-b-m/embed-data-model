from __future__ import annotations

import json

import pytest

from embed_toolkit.adapters import (
    EmbedClinicalImageGraph,
    FindingImageCandidateProjection,
    assemble_clinical_image_graph,
    project_finding_image_candidates,
)
from embed_toolkit.adapters.embed import (
    build_clinical_tables,
    build_image_tables,
)
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError
from embed_toolkit.clinical.associations import AttributionStatus
from embed_toolkit.core.primitives import Laterality


def clinical_tables(*accessions: str):
    return build_clinical_tables(
        [
            {
                "empi_anon": "P-1",
                "acc_anon": accession,
                "numfind": "1",
                "side": "L",
            }
            for accession in accessions
        ],
        source_scope="clinical-materialization",
    )


def image_row(
    image_id: str,
    accession: object,
    *,
    patient_id: str = "P-1",
    laterality: str = "L",
) -> dict:
    return {
        "image_id": image_id,
        "empi_anon": patient_id,
        "acc_anon": accession,
        "ImageLateralityFinal": laterality,
        "ViewPosition": "CC",
    }


def test_assembly_attaches_images_to_exam_and_matching_unilateral_side() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [
            image_row("left-cc", "ACC-1"),
            image_row("right-cc", "ACC-1", laterality="R"),
        ]
    )

    graph = assemble_clinical_image_graph(clinical, images)
    exam = graph.exams[0]

    assert isinstance(graph, EmbedClinicalImageGraph)
    assert exam.images == list(images.images)
    assert exam.breast_sides[Laterality.LEFT].images == [images.images[0]]
    assert exam.breast_sides[Laterality.RIGHT].images == [images.images[1]]
    assert graph.unmatched_images == ()
    assert graph.unmatched_exams == ()
    assert graph.build_issues == ()


def test_missing_and_unknown_accessions_remain_explicitly_unmatched() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [
            image_row("missing-accession", None),
            image_row("unknown-accession", "ACC-2"),
        ]
    )

    graph = assemble_clinical_image_graph(clinical, images)

    assert graph.unmatched_images == images.images
    assert graph.unmatched_exams == clinical.exams
    assert clinical.exams[0].images == []


def test_exams_without_matching_images_are_preserved_as_unmatched() -> None:
    clinical = clinical_tables("ACC-1", "ACC-2")
    images = build_image_tables([image_row("left-cc", "ACC-1")])

    graph = assemble_clinical_image_graph(clinical, images)

    assert [exam.accession_number for exam in graph.unmatched_exams] == ["ACC-2"]
    assert graph.exams == clinical.exams


def test_patient_mismatch_is_atomic_under_strict_policy() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [
            image_row("valid", "ACC-1"),
            image_row("mismatch", "ACC-1", patient_id="P-2"),
        ]
    )

    with pytest.raises(BuildPolicyError) as exc_info:
        assemble_clinical_image_graph(
            clinical,
            images,
            source_scope="assembly-1",
        )

    assert exc_info.value.issue.code == (
        "conflicting_clinical_image_patient_identity"
    )
    assert exc_info.value.issue.source.source_key == "mismatch"
    assert clinical.exams[0].images == []


def test_patient_mismatch_audit_is_issue_and_unmatched_image() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [image_row("mismatch", "ACC-1", patient_id="P-2")]
    )

    graph = assemble_clinical_image_graph(
        clinical,
        images,
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="assembly-1",
    )

    assert graph.unmatched_images == images.images
    assert graph.unmatched_exams == clinical.exams
    assert clinical.exams[0].images == []
    assert [issue.code for issue in graph.build_issues] == [
        "conflicting_clinical_image_patient_identity"
    ]
    assert graph.build_issues[0].context["clinical_patient_id"] == "P-1"
    assert graph.build_issues[0].context["image_patient_id"] == "P-2"


def test_repeated_assembly_is_idempotent_and_does_not_duplicate_membership() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables([image_row("left-cc", "ACC-1")])

    first = assemble_clinical_image_graph(clinical, images)
    second = assemble_clinical_image_graph(clinical, images)

    exam = clinical.exams[0]
    assert first.exams[0] is second.exams[0]
    assert exam.images == [images.images[0]]
    assert exam.breast_sides[Laterality.LEFT].images == [images.images[0]]


def test_graph_serialization_owns_images_once_and_membership_uses_references() -> None:
    clinical = clinical_tables("ACC-1", "ACC-2")
    images = build_image_tables(
        [
            image_row("left-cc", "ACC-1"),
            image_row("unmatched", "ACC-3"),
        ]
    )
    graph = assemble_clinical_image_graph(clinical, images)

    serialized = graph.to_dict()

    assert [image["image_id"] for image in serialized["images"]] == [
        "left-cc",
        "unmatched",
    ]
    assert serialized["exams"][0]["image_references"] == ["left-cc"]
    assert serialized["unmatched_image_references"] == ["unmatched"]
    assert serialized["unmatched_exam_references"] == ["ACC-2"]
    assert "images" not in serialized["exams"][0]
    json.dumps(serialized)


def test_graph_serialization_uses_canonical_breast_side_order() -> None:
    clinical = build_clinical_tables(
        [
            {
                "empi_anon": "P-1",
                "acc_anon": "ACC-1",
                "numfind": "1",
                "side": "R",
            },
            {
                "empi_anon": "P-1",
                "acc_anon": "ACC-1",
                "numfind": "2",
                "side": "L",
            },
        ],
        source_scope="clinical-materialization",
    )

    assert list(clinical.exams[0].breast_sides) == [
        Laterality.RIGHT,
        Laterality.LEFT,
    ]

    serialized = assemble_clinical_image_graph(
        clinical,
        build_image_tables([]),
    ).to_dict()

    assert [
        side["laterality"] for side in serialized["exams"][0]["breast_sides"]
    ] == ["L", "R"]


@pytest.mark.parametrize(
    ("clinical", "image_tables", "message"),
    [
        (object(), build_image_tables([]), "clinical must be an EmbedClinicalTables"),
        (clinical_tables("ACC-1"), object(), "image_tables must be an EmbedImageTables"),
    ],
)
def test_assembly_rejects_invalid_table_wrappers(
    clinical: object,
    image_tables: object,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        assemble_clinical_image_graph(clinical, image_tables)  # type: ignore[arg-type]


def test_candidate_projection_excludes_mismatched_and_unmatched_images() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [
            image_row("valid", "ACC-1"),
            image_row("patient-mismatch", "ACC-1", patient_id="P-2"),
            image_row("unmatched-accession", "ACC-2"),
        ]
    )
    graph = assemble_clinical_image_graph(
        clinical,
        images,
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    projection = project_finding_image_candidates(graph)[0]

    assert [image.image_id for image in projection.candidate_images] == ["valid"]
    assert [image.image_id for image in graph.unmatched_images] == [
        "patient-mismatch",
        "unmatched-accession",
    ]


def test_bilateral_candidate_projection_unions_sides_without_duplicates() -> None:
    clinical = build_clinical_tables(
        [
            {
                "empi_anon": "P-1",
                "acc_anon": "ACC-1",
                "numfind": "1",
                "side": "B",
            }
        ],
        source_scope="clinical-materialization",
    )
    images = build_image_tables(
        [
            image_row("left", "ACC-1", laterality="L"),
            image_row("right", "ACC-1", laterality="R"),
        ]
    )
    graph = assemble_clinical_image_graph(clinical, images)
    graph.exams[0].breast_sides[Laterality.LEFT].images.append(images.images[0])

    projection = project_finding_image_candidates(graph)[0]

    assert [image.image_id for image in projection.candidate_images] == [
        "left",
        "right",
    ]


def test_unknown_laterality_preserves_empty_candidate_projection() -> None:
    clinical = build_clinical_tables(
        [
            {
                "empi_anon": "P-1",
                "acc_anon": "ACC-1",
                "numfind": "1",
                "side": "unknown-code",
            }
        ],
        source_scope="clinical-materialization",
    )
    graph = assemble_clinical_image_graph(
        clinical,
        build_image_tables([image_row("left", "ACC-1")]),
    )

    projections = project_finding_image_candidates(graph)

    assert len(projections) == 1
    assert projections[0].candidate_images == ()


def test_candidate_projection_ignores_graph_images_outside_exam_hierarchy() -> None:
    clinical = clinical_tables("ACC-1")
    image = build_image_tables([image_row("not-contained", "ACC-1")]).images[0]
    graph = EmbedClinicalImageGraph(
        exams=clinical.exams,
        images=(image,),
        unmatched_images=(image,),
        unmatched_exams=clinical.exams,
        build_issues=(),
    )

    projection = project_finding_image_candidates(graph)[0]

    assert projection.candidate_images == ()


def test_candidate_projection_serialization_is_reference_based_and_explicit() -> None:
    graph = assemble_clinical_image_graph(
        clinical_tables("ACC-1"),
        build_image_tables([image_row("left", "ACC-1")]),
    )

    projection = project_finding_image_candidates(graph)[0]
    serialized = projection.to_dict()

    assert isinstance(projection, FindingImageCandidateProjection)
    assert projection.status is AttributionStatus.CANDIDATE
    assert serialized == {
        "finding_reference": {
            "accession_number": "ACC-1",
            "finding_number": "1",
        },
        "candidate_image_references": ["left"],
        "selection_basis": "assembled_exam_unilateral_side_membership",
        "status": "candidate",
    }
    assert "finding" not in serialized
    assert "images" not in serialized
    json.dumps(serialized)


def test_candidate_projection_rejects_invalid_graph_wrapper() -> None:
    with pytest.raises(TypeError, match="graph must be an EmbedClinicalImageGraph"):
        project_finding_image_candidates(object())  # type: ignore[arg-type]
