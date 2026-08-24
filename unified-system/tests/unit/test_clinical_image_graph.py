from __future__ import annotations

import json
from dataclasses import replace

import pytest

from embed_toolkit.adapters import (
    EmbedClinicalImageGraph,
    ExamImageContainmentLink,
    FindingImageCandidate,
    FindingImageCandidateProjection,
    PatientIdentityCheckStatus,
    UnmatchedImage,
    UnmatchedImageReason,
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
    patient_id: str | None = "P-1",
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
    assert [link.image.image_id for link in graph.containment_links] == [
        "left-cc",
        "right-cc",
    ]
    assert all(
        link.patient_identity_status is PatientIdentityCheckStatus.VERIFIED
        for link in graph.containment_links
    )


def test_missing_and_unknown_accessions_remain_explicitly_unmatched() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [
            image_row("missing-accession", None),
            image_row("unknown-accession", "ACC-2"),
        ]
    )

    graph = assemble_clinical_image_graph(clinical, images)

    assert [unmatched.image for unmatched in graph.unmatched_images] == list(
        images.images
    )
    assert [unmatched.reason for unmatched in graph.unmatched_images] == [
        UnmatchedImageReason.MISSING_ACCESSION,
        UnmatchedImageReason.ACCESSION_NOT_IN_CLINICAL_GRAPH,
    ]
    assert [issue.code for issue in graph.build_issues] == [
        "missing_image_accession_for_assembly"
    ]
    assert graph.build_issues[0].source is images.images[0].source_for(
        "accession_number"
    )
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
        )

    assert exc_info.value.issue.code == (
        "conflicting_clinical_image_patient_identity"
    )
    assert exc_info.value.issue.source == images.images[1].canonical_source
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
    )

    assert [unmatched.image for unmatched in graph.unmatched_images] == list(
        images.images
    )
    assert graph.unmatched_images[0].reason is (
        UnmatchedImageReason.PATIENT_IDENTITY_CONFLICT
    )
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
    assert serialized["unmatched_images"][0]["image_reference"] == "unmatched"
    assert serialized["unmatched_images"][0]["reason"] == (
        "accession_not_in_clinical_graph"
    )
    assert serialized["containment_links"][0]["image_reference"] == "left-cc"
    assert "image" not in serialized["containment_links"][0]
    assert "image" not in serialized["unmatched_images"][0]
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

    assert [candidate.image.image_id for candidate in projection.candidates] == [
        "valid"
    ]
    assert [unmatched.image.image_id for unmatched in graph.unmatched_images] == [
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

    assert [candidate.image.image_id for candidate in projection.candidates] == [
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
    assert projections[0].candidates == ()


def test_candidate_projection_ignores_graph_images_outside_exam_hierarchy() -> None:
    clinical = clinical_tables("ACC-1")
    image = build_image_tables([image_row("not-contained", "ACC-2")]).images[0]
    graph = EmbedClinicalImageGraph(
        exams=clinical.exams,
        images=(image,),
        containment_links=(),
        unmatched_images=(
            UnmatchedImage(
                image=image,
                reason=UnmatchedImageReason.ACCESSION_NOT_IN_CLINICAL_GRAPH,
                sources=tuple(image.sources),
            ),
        ),
        unmatched_exams=clinical.exams,
        build_issues=(),
    )

    projection = project_finding_image_candidates(graph)[0]

    assert projection.candidates == ()


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
        "candidates": [
            {
                "image_reference": "left",
                "patient_identity_status": "verified",
                "sources": [
                    graph.images[0].canonical_source.to_dict(),
                ],
            }
        ],
        "selection_basis": "assembled_exam_unilateral_side_membership",
        "status": "candidate",
    }
    assert "finding" not in serialized
    assert "images" not in serialized
    json.dumps(serialized)


def test_candidate_projection_rejects_invalid_graph_wrapper() -> None:
    with pytest.raises(TypeError, match="graph must be an EmbedClinicalImageGraph"):
        project_finding_image_candidates(object())  # type: ignore[arg-type]


def test_missing_patient_identity_attaches_as_unverified_with_original_source() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [image_row("missing-patient", "ACC-1", patient_id=None)],
    )

    graph = assemble_clinical_image_graph(clinical, images)

    assert clinical.exams[0].images == [images.images[0]]
    assert graph.containment_links[0].patient_identity_status is (
        PatientIdentityCheckStatus.UNVERIFIED
    )
    assert graph.containment_links[0].sources == tuple(images.images[0].sources)
    assert [issue.code for issue in graph.build_issues] == [
        "missing_patient_identity_for_reconciliation"
    ]
    assert graph.build_issues[0].source == images.images[0].canonical_source
    assert graph.build_issues[0].severity.value == "warning"
    assert project_finding_image_candidates(graph)[0].candidates[
        0
    ].patient_identity_status is PatientIdentityCheckStatus.UNVERIFIED


def test_missing_clinical_patient_identity_is_also_unverified() -> None:
    clinical = clinical_tables("ACC-1")
    clinical.exams[0].patient_id = None
    images = build_image_tables([image_row("left", "ACC-1")])

    graph = assemble_clinical_image_graph(clinical, images)

    assert graph.containment_links[0].patient_identity_status is (
        PatientIdentityCheckStatus.UNVERIFIED
    )
    assert [issue.code for issue in graph.build_issues] == [
        "missing_patient_identity_for_reconciliation"
    ]


@pytest.mark.parametrize("laterality", ["B", "unknown-code"])
def test_non_unilateral_image_attaches_only_to_exam_with_warning(
    laterality: str,
) -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [image_row("not-unilateral", "ACC-1", laterality=laterality)]
    )

    graph = assemble_clinical_image_graph(clinical, images)

    assert clinical.exams[0].images == [images.images[0]]
    assert all(
        images.images[0] not in side.images
        for side in clinical.exams[0].breast_sides.values()
    )
    assert graph.containment_links[0].image is images.images[0]
    assert [issue.code for issue in graph.build_issues] == [
        "unresolved_image_laterality_for_side_containment"
    ]
    assert graph.build_issues[0].source == images.images[0].canonical_source


def test_candidate_entries_preserve_the_full_image_source_ledger() -> None:
    clinical = clinical_tables("ACC-1")
    row = image_row("left", "ACC-1")
    images = build_image_tables(
        [row, dict(row)],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="image-materialization",
    )

    graph = assemble_clinical_image_graph(clinical, images)
    candidate = project_finding_image_candidates(graph)[0].candidates[0]

    assert isinstance(candidate, FindingImageCandidate)
    assert len(candidate.sources) == 2
    assert candidate.sources == tuple(images.images[0].sources)
    assert graph.containment_links[0].sources == candidate.sources


def test_reconciliation_contracts_reject_mismatched_or_duplicate_evidence() -> None:
    image = build_image_tables([image_row("left", "ACC-1")]).images[0]
    source = image.canonical_source

    with pytest.raises(ValueError, match="must match containment accession"):
        ExamImageContainmentLink(
            accession_number="ACC-2",
            image=image,
            patient_identity_status=PatientIdentityCheckStatus.VERIFIED,
            sources=(source,),
        )
    with pytest.raises(ValueError, match="unique SourceLocator"):
        UnmatchedImage(
            image=image,
            reason=UnmatchedImageReason.ACCESSION_NOT_IN_CLINICAL_GRAPH,
            sources=(source, source),
        )
    with pytest.raises(ValueError):
        FindingImageCandidate(
            image=image,
            patient_identity_status="not-a-status",  # type: ignore[arg-type]
            sources=(source,),
        )


def test_second_assembly_replaces_changed_and_empty_image_membership() -> None:
    clinical = clinical_tables("ACC-1")
    first_images = build_image_tables([image_row("first", "ACC-1")])
    second_images = build_image_tables(
        [image_row("second", "ACC-1", laterality="R")]
    )

    assemble_clinical_image_graph(clinical, first_images)
    second = assemble_clinical_image_graph(clinical, second_images)

    exam = clinical.exams[0]
    assert exam.images == [second_images.images[0]]
    assert exam.breast_sides[Laterality.LEFT].images == []
    assert exam.breast_sides[Laterality.RIGHT].images == [second_images.images[0]]
    assert [link.image.image_id for link in second.containment_links] == ["second"]

    empty = assemble_clinical_image_graph(clinical, build_image_tables([]))

    assert exam.images == []
    assert all(side.images == [] for side in exam.breast_sides.values())
    assert empty.containment_links == ()
    assert empty.unmatched_exams == (exam,)


def test_strict_reassembly_failure_preserves_prior_hierarchy_atomically() -> None:
    clinical = clinical_tables("ACC-1")
    prior = build_image_tables([image_row("prior", "ACC-1")])
    assemble_clinical_image_graph(clinical, prior)
    failing = build_image_tables(
        [image_row("mismatch", "ACC-1", patient_id="P-2")]
    )

    with pytest.raises(BuildPolicyError):
        assemble_clinical_image_graph(clinical, failing)

    exam = clinical.exams[0]
    assert exam.images == [prior.images[0]]
    assert exam.breast_sides[Laterality.LEFT].images == [prior.images[0]]


def test_later_duplicate_fills_drive_graph_decisions_and_issue_sources() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [
            image_row(
                "filled",
                None,
                patient_id=None,
                laterality="unknown-code",
            ),
            image_row("filled", "ACC-1", patient_id="P-1", laterality="B"),
        ],
        source_scope="image-materialization",
    )
    row_one = images.source_occurrences[1].locator

    graph = assemble_clinical_image_graph(clinical, images)

    assert images.images[0].source_for("accession_number") is row_one
    assert images.images[0].source_for("patient_id") is row_one
    assert images.images[0].source_for("laterality") is row_one
    assert graph.containment_links[0].patient_identity_status is (
        PatientIdentityCheckStatus.VERIFIED
    )
    assert graph.build_issues[0].code == (
        "unresolved_image_laterality_for_side_containment"
    )
    assert graph.build_issues[0].source is row_one


def test_later_patient_fill_conflict_uses_the_supporting_row_locator() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables(
        [
            image_row("filled-patient", "ACC-1", patient_id=None),
            image_row("filled-patient", "ACC-1", patient_id="P-2"),
        ],
        source_scope="image-materialization",
    )

    with pytest.raises(BuildPolicyError) as exc_info:
        assemble_clinical_image_graph(clinical, images)

    assert exc_info.value.issue.code == (
        "conflicting_clinical_image_patient_identity"
    )
    assert exc_info.value.issue.source is images.source_occurrences[1].locator


def test_graph_rejects_duplicate_unclassified_and_multiply_classified_images() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables([image_row("left", "ACC-1")])
    image = images.images[0]
    graph = assemble_clinical_image_graph(clinical, images)

    with pytest.raises(ValueError, match="image_id values must be unique"):
        EmbedClinicalImageGraph(
            exams=graph.exams,
            images=(image, image),
            containment_links=graph.containment_links,
            unmatched_images=(),
            unmatched_exams=(),
            build_issues=(),
        )
    with pytest.raises(ValueError, match="classified exactly once"):
        EmbedClinicalImageGraph(
            exams=graph.exams,
            images=(image,),
            containment_links=(),
            unmatched_images=(),
            unmatched_exams=(),
            build_issues=(),
        )
    with pytest.raises(ValueError, match="classifications must be disjoint"):
        EmbedClinicalImageGraph(
            exams=graph.exams,
            images=(image,),
            containment_links=graph.containment_links,
            unmatched_images=(
                UnmatchedImage(
                    image=image,
                    reason=UnmatchedImageReason.ACCESSION_NOT_IN_CLINICAL_GRAPH,
                    sources=tuple(image.sources),
                ),
            ),
            unmatched_exams=(),
            build_issues=(),
        )


def test_graph_rejects_wrong_image_object_accession_and_stale_hierarchy() -> None:
    clinical = clinical_tables("ACC-1")
    images = build_image_tables([image_row("left", "ACC-1")])
    graph = assemble_clinical_image_graph(clinical, images)
    image = images.images[0]
    copied = replace(image)
    copied_link = ExamImageContainmentLink(
        accession_number="ACC-1",
        image=copied,
        patient_identity_status=PatientIdentityCheckStatus.VERIFIED,
        sources=tuple(copied.sources),
    )

    with pytest.raises(ValueError, match="exact graph-owned image"):
        EmbedClinicalImageGraph(
            exams=graph.exams,
            images=(image,),
            containment_links=(copied_link,),
            unmatched_images=(),
            unmatched_exams=(),
            build_issues=(),
        )

    inconsistent_status = ExamImageContainmentLink(
        accession_number="ACC-1",
        image=image,
        patient_identity_status=PatientIdentityCheckStatus.UNVERIFIED,
        sources=tuple(image.sources),
    )
    with pytest.raises(ValueError, match="identity status is inconsistent"):
        EmbedClinicalImageGraph(
            exams=graph.exams,
            images=graph.images,
            containment_links=(inconsistent_status,),
            unmatched_images=(),
            unmatched_exams=(),
            build_issues=(),
        )

    wrong_accession = replace(image, accession_number="ACC-2")
    wrong_link = ExamImageContainmentLink(
        accession_number="ACC-2",
        image=wrong_accession,
        patient_identity_status=PatientIdentityCheckStatus.VERIFIED,
        sources=tuple(wrong_accession.sources),
    )
    with pytest.raises(ValueError, match="accession must resolve"):
        EmbedClinicalImageGraph(
            exams=graph.exams,
            images=(wrong_accession,),
            containment_links=(wrong_link,),
            unmatched_images=(),
            unmatched_exams=(),
            build_issues=(),
        )

    clinical.exams[0].images.clear()
    clinical.exams[0].breast_sides[Laterality.LEFT].images.clear()
    with pytest.raises(ValueError, match="exam image hierarchy"):
        EmbedClinicalImageGraph(
            exams=graph.exams,
            images=graph.images,
            containment_links=graph.containment_links,
            unmatched_images=(),
            unmatched_exams=(),
            build_issues=(),
        )


def test_graph_normalizes_tuples_and_rejects_untyped_ledgers() -> None:
    graph = assemble_clinical_image_graph(
        clinical_tables("ACC-1"),
        build_image_tables([image_row("left", "ACC-1")]),
    )
    normalized = EmbedClinicalImageGraph(
        exams=list(graph.exams),  # type: ignore[arg-type]
        images=list(graph.images),  # type: ignore[arg-type]
        containment_links=list(graph.containment_links),  # type: ignore[arg-type]
        unmatched_images=[],  # type: ignore[arg-type]
        unmatched_exams=[],  # type: ignore[arg-type]
        build_issues=[],  # type: ignore[arg-type]
    )
    assert isinstance(normalized.exams, tuple)
    assert isinstance(normalized.containment_links, tuple)

    with pytest.raises(TypeError, match="build_issues must contain only BuildIssue"):
        EmbedClinicalImageGraph(
            exams=graph.exams,
            images=graph.images,
            containment_links=graph.containment_links,
            unmatched_images=(),
            unmatched_exams=(),
            build_issues=(object(),),  # type: ignore[arg-type]
        )


def test_graph_rejects_semantically_impossible_unmatched_reasons() -> None:
    clinical = clinical_tables("ACC-1")

    populated = build_image_tables([image_row("populated", "ACC-2")]).images[0]
    with pytest.raises(ValueError, match="MISSING_ACCESSION requires"):
        EmbedClinicalImageGraph(
            exams=clinical.exams,
            images=(populated,),
            containment_links=(),
            unmatched_images=(
                UnmatchedImage(
                    image=populated,
                    reason=UnmatchedImageReason.MISSING_ACCESSION,
                    sources=tuple(populated.sources),
                ),
            ),
            unmatched_exams=clinical.exams,
            build_issues=(),
        )

    missing = build_image_tables([image_row("missing", None)]).images[0]
    with pytest.raises(ValueError, match="ACCESSION_NOT_IN_CLINICAL_GRAPH requires"):
        EmbedClinicalImageGraph(
            exams=clinical.exams,
            images=(missing,),
            containment_links=(),
            unmatched_images=(
                UnmatchedImage(
                    image=missing,
                    reason=UnmatchedImageReason.ACCESSION_NOT_IN_CLINICAL_GRAPH,
                    sources=tuple(missing.sources),
                ),
            ),
            unmatched_exams=clinical.exams,
            build_issues=(),
        )

    same_patient = build_image_tables([image_row("same", "ACC-1")]).images[0]
    with pytest.raises(ValueError, match="PATIENT_IDENTITY_CONFLICT requires"):
        EmbedClinicalImageGraph(
            exams=clinical.exams,
            images=(same_patient,),
            containment_links=(),
            unmatched_images=(
                UnmatchedImage(
                    image=same_patient,
                    reason=UnmatchedImageReason.PATIENT_IDENTITY_CONFLICT,
                    sources=tuple(same_patient.sources),
                ),
            ),
            unmatched_exams=clinical.exams,
            build_issues=(),
        )


def test_candidate_projection_rejects_malformed_direct_candidates() -> None:
    graph = assemble_clinical_image_graph(
        clinical_tables("ACC-1"),
        build_image_tables([image_row("left", "ACC-1")]),
    )
    projection = project_finding_image_candidates(graph)[0]
    finding = projection.finding
    candidate = projection.candidates[0]

    with pytest.raises(ValueError, match="unique image IDs"):
        FindingImageCandidateProjection(
            finding=finding,
            candidates=(candidate, candidate),
        )

    wrong_accession_image = replace(candidate.image, accession_number="ACC-2")
    wrong_accession = FindingImageCandidate(
        image=wrong_accession_image,
        patient_identity_status=PatientIdentityCheckStatus.VERIFIED,
        sources=tuple(wrong_accession_image.sources),
    )
    with pytest.raises(ValueError, match="accession must match"):
        FindingImageCandidateProjection(
            finding=finding,
            candidates=(wrong_accession,),
        )

    wrong_side_image = replace(candidate.image, laterality=Laterality.RIGHT)
    wrong_side = FindingImageCandidate(
        image=wrong_side_image,
        patient_identity_status=PatientIdentityCheckStatus.VERIFIED,
        sources=tuple(wrong_side_image.sources),
    )
    with pytest.raises(ValueError, match="unilateral and compatible"):
        FindingImageCandidateProjection(
            finding=finding,
            candidates=(wrong_side,),
        )
