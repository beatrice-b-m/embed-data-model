from __future__ import annotations

import pytest

from embed_toolkit.adapters.embed import (
    assemble_clinical_image_graph,
    build_clinical_tables,
    build_image_tables,
    project_finding_image_candidates,
)
from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.config.profile_contracts import (
    INTERNAL_V1C_CONTRACT,
    INTERNAL_V2_CONTRACT,
)
from embed_toolkit.clinical.associations import AttributionStatus
from embed_toolkit.clinical.pathology import PathologySeverity
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition
from embed_toolkit.core.provenance import AvailabilityState, ResolutionState
from embed_toolkit.imaging.roi_provenance import (
    RoiDepthFrameProvenance,
    RoiLocatorKind,
    RoiSourceCountBasis,
)
from profile_contract_support import contract_for_columns


def test_clinical_builder_deduplicates_findings_and_attaches_rows() -> None:
    rows = [
        {
            "empi_anon": "P1",
            "acc_anon": "ACC-1",
            "numfind": 1,
            "side": "L",
            "finding_type": "mass",
            "asses": "4",
            "procedure_id": "BIO-1",
            "procedure_type": "biopsy",
            "procedure_date": "2020-01-01",
            "bside": "L",
            "pathology_id": "PATH-1",
            "pathology_diagnosis": "fibroadenoma",
            "pathology_malignant": "N",
        },
        {
            "empi_anon": "P1",
            "acc_anon": "ACC-1",
            "numfind": 1,
            "side": "L",
            "finding_type": "mass",
            "procedure_id": "LUMP-1",
            "procedure_type": "lumpectomy",
            "procedure_date": "2020-01-02",
            "bside": "L",
            "pathology_id": "PATH-2",
            "pathology_diagnosis": "dcis",
            "pathology_malignant": "Y",
        },
    ]

    tables = build_clinical_tables(rows)

    assert len(tables.patients) == 1
    assert len(tables.exams) == 1
    assert len(tables.findings) == 1
    finding = tables.findings[0]
    assert finding.identity == ("ACC-1", "1")
    assert finding.finding_type == "mass"
    assert finding.interpretation is tables.interpretations[0]
    assert finding.interpretation.assessment == "4"
    assert finding.interpretation.recommendation_availability is (
        AvailabilityState.UNAVAILABLE
    )
    assert [procedure.sources[0].row_ordinal for procedure in tables.procedures] == [
        0,
        1,
    ]
    assert [diagnosis.diagnosis for diagnosis in tables.pathology_diagnoses] == [
        "fibroadenoma",
        "dcis",
    ]
    assert tables.pathology_diagnoses[0].malignant is False
    assert tables.pathology_diagnoses[1].malignant is True
    assert len(tables.finding_procedure_links) == 2
    assert tables.breast_sides[0].laterality is Laterality.LEFT
    assert tables.breast_sides[0].findings == [finding]


def test_internal_v2_defaults_bind_mcp_profile_columns() -> None:
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-1",
                "numfind": 1,
                "side": "L",
                "GENDER_DESC": "Female",
                "studydate_anon": "2020-01-01",
                "desc": "Screening mammography",
                "asses": "N",
                "recc": "R1",
            }
        ],
        source_scope="internal-v2-release",
    )

    assert tables.exams[0].description == "Screening mammography"
    assert tables.interpretations[0].recommendation == "R1"
    patient_sex = tables.patients[0].attribute_observations[0]
    assert patient_sex.value == "Female"
    assert patient_sex.source.source_profile == "internal-v2"


def test_clinical_builder_expands_bilateral_findings_to_breast_sides() -> None:
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-B",
                "numfind": "2",
                "side": "B",
            }
        ]
    )

    assert len(tables.findings) == 1
    assert tables.findings[0].laterality is Laterality.BILATERAL
    assert [side.laterality for side in tables.breast_sides] == [
        Laterality.LEFT,
        Laterality.RIGHT,
    ]
    assert [side.findings[0] for side in tables.breast_sides] == [
        tables.findings[0],
        tables.findings[0],
    ]
    assert tables.procedures == ()


def test_null_finding_side_is_one_bilateral_finding() -> None:
    tables = build_clinical_tables(
        [{"empi_anon": "P1", "acc_anon": "ACC-B", "numfind": "2"}]
    )

    assert len(tables.findings) == 1
    assert tables.findings[0].laterality is Laterality.BILATERAL
    assert set(tables.exams[0].breast_sides) == {Laterality.LEFT, Laterality.RIGHT}


def test_repeated_finding_conflicts_use_build_policy_and_row_ledger() -> None:
    rows = [
        {
            "empi_anon": "P1",
            "acc_anon": "ACC-1",
            "numfind": 1,
            "side": "L",
            "finding_type": "mass",
        },
        {
            "empi_anon": "P1",
            "acc_anon": "ACC-1",
            "numfind": 1,
            "side": "R",
            "finding_type": "calcification",
        },
    ]

    with pytest.raises(BuildPolicyError) as exc_info:
        build_clinical_tables(rows)
    assert exc_info.value.issue.code == "conflicting_finding_attribute"
    assert exc_info.value.issue.context["attribute"] == "laterality"

    tables = build_clinical_tables(
        rows,
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    assert len(tables.findings) == 1
    assert tables.findings[0].laterality is Laterality.LEFT
    assert tables.findings[0].finding_type == "mass"
    assert tables.findings[0].metadata["source_row_count"] == 2
    assert [issue.context["attribute"] for issue in tables.build_issues] == [
        "laterality",
        "finding_type",
    ]
    assert tables.source_occurrences[1].resolution_state is ResolutionState.UNRESOLVED
    assert tables.source_occurrences[1].issues == tables.build_issues


def test_audit_conflict_retains_value_and_merges_safe_missing_attribute() -> None:
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-1",
                "numfind": 1,
                "side": "L",
            },
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-1",
                "numfind": 1,
                "side": "R",
                "finding_type": "mass",
            },
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    finding = tables.findings[0]
    assert finding.laterality is Laterality.LEFT
    assert finding.finding_type == "mass"
    assert finding.metadata["source_row_count"] == 2
    assert [issue.context["attribute"] for issue in tables.build_issues] == [
        "laterality"
    ]
    assert tables.source_occurrences[1].resolution_state is ResolutionState.UNRESOLVED


def test_procedure_laterality_is_independent_and_null_remains_unknown() -> None:
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-1",
                "numfind": 1,
                "side": "L",
                "procedure_id": "P-R",
                "procedure_date": "2020-01-01",
                "procedure_type": "biopsy",
                "bside": "R",
            },
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-1",
                "numfind": 2,
                "side": "L",
                "procedure_id": "P-U",
            },
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    assert tables.findings[0].laterality is Laterality.LEFT
    assert tables.procedures[0].identity.laterality is Laterality.RIGHT
    assert len(tables.unresolved_procedure_occurrences) == 1
    assert tables.unresolved_procedure_occurrences[0].laterality is Laterality.UNKNOWN


def test_complete_procedures_are_interned_while_pathology_remains_row_grain() -> None:
    base = {
        "empi_anon": "P1",
        "acc_anon": "ACC-1",
        "side": "L",
        "procdate_anon": "2020-01-01",
        "type": "core biopsy",
        "bside": "R",
        "pathology_id": "PATH-1",
        "pathology_diagnosis": "dcis",
    }
    tables = build_clinical_tables(
        [
            {**base, "numfind": 1},
            {**base, "numfind": 1},
            {**base, "numfind": 2},
        ]
    )

    procedure = tables.procedures[0]
    assert len(tables.procedures) == 1
    assert len(procedure.sources) == 3
    assert len(tables.pathology_diagnoses) == 3
    assert [
        (link.accession_number, link.finding_number)
        for link in tables.finding_procedure_links
    ] == [("ACC-1", "1"), ("ACC-1", "1"), ("ACC-1", "2")]


def test_incomplete_procedures_are_evidence_and_complete_tuples_are_interned() -> None:
    base = {
        "empi_anon": "P1",
        "acc_anon": "ACC-1",
        "numfind": 1,
        "side": "L",
        "type": "biopsy",
        "bside": "L",
    }
    tables = build_clinical_tables(
        [
            base,
            base,
            {**base, "procdate_anon": "2020-01-01"},
            {**base, "procdate_anon": "2020-01-02"},
            {**base, "procdate_anon": "2020-01-01", "type": "excision"},
            {**base, "procdate_anon": "2020-01-01", "bside": "R"},
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    assert len(tables.unresolved_procedure_occurrences) == 2
    assert len(tables.procedures) == 4
    assert len(tables.finding_procedure_links) == 4


@pytest.mark.parametrize("raw", range(6))
def test_valid_pathology_severities_use_governed_type(raw: int) -> None:
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P1",
                "acc_anon": f"ACC-{raw}",
                "numfind": 1,
                "side": "L",
                "procedure_id": f"P-{raw}",
                "procedure_type": "biopsy",
                "procedure_date": "2020-01-01",
                "bside": "L",
                "path_severity": raw,
            }
        ]
    )

    diagnosis = tables.pathology_diagnoses[0]
    assert diagnosis.severity is PathologySeverity(raw)
    assert diagnosis.raw_severity == raw


def test_invalid_pathology_states_support_audit_and_strict_modes() -> None:
    invalid = {
        "empi_anon": "P1",
        "acc_anon": "ACC-6",
        "numfind": 1,
        "side": "L",
        "procedure_id": "P-6",
        "procedure_type": "biopsy",
        "procedure_date": "2020-01-01",
        "bside": "L",
        "path_severity": 6,
        "path1": "KNOWN",
    }
    audited = build_clinical_tables(
        [invalid],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    diagnosis = audited.pathology_diagnoses[0]
    assert diagnosis.severity is None
    assert diagnosis.raw_severity == 6
    assert [item.descriptor for item in audited.pathology_observations] == ["KNOWN"]
    assert diagnosis.validation_issues[0].code == "invalid_pathology_severity"

    with pytest.raises(BuildPolicyError, match="0 through 5"):
        build_clinical_tables([invalid])

    missing = {**invalid, "path_severity": None, "path1": "UNKNOWN_TOKEN"}
    audited_missing = build_clinical_tables(
        [missing],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    missing_diagnosis = audited_missing.pathology_diagnoses[0]
    assert [item.descriptor for item in audited_missing.pathology_observations] == [
        "UNKNOWN_TOKEN"
    ]
    assert missing_diagnosis.validation_issues[0].code == (
        "descriptors_without_severity"
    )
    with pytest.raises(BuildPolicyError, match="require a populated severity"):
        build_clinical_tables([missing])


def test_pathology_descriptors_preserve_order_duplicates_and_custom_prefix() -> None:
    columns = EmbedColumnConfig(pathology_diagnosis_prefix="dx")
    contract = contract_for_columns(INTERNAL_V2_CONTRACT, "custom-v2", columns)
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-1",
                "numfind": 1,
                "side": "L",
                "procedure_id": "P-1",
                "procedure_type": "biopsy",
                "procedure_date": "2020-01-01",
                "bside": "L",
                "path_severity": 2,
                "dx1": "A",
                "dx2": "A",
                "dx3": "UNMAPPED",
            }
        ],
        columns=columns,
        source_profile="custom-v2",
        profile_contract=contract,
    )

    assert tuple(item.descriptor for item in tables.pathology_observations) == (
        "A",
        "A",
        "UNMAPPED",
    )


def test_null_pathology_without_descriptors_is_unattached() -> None:
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-1",
                "numfind": 1,
                "side": "L",
                "procedure_id": "P-1",
                "procedure_type": "biopsy",
                "procedure_date": "2020-01-01",
                "bside": "L",
                "path_severity": None,
            }
        ]
    )

    assert tables.pathology_observations == ()
    assert tables.pathology_diagnoses == ()


def test_image_builder_constructs_images_and_rois_without_clinical_rows() -> None:
    rows = [
        {
            "image_id": "IMG-L-CC",
            "empi_anon": "P1",
            "acc_anon": "ACC-1",
            "ImageLateralityFinal": "L",
            "ViewPosition": "L CC",
            "FinalImageType": "2D",
            "Rows": 2048,
            "Columns": 1536,
            "SOPInstanceUID": "sop-1",
            "PatientOrientation": "['P', 'L']",
            "y_min": 10,
            "x_min": 20,
            "y_max": 40,
            "x_max": 60,
            "roi_source": "synthetic",
            "roi_confidence": 0.8,
        },
        {
            "image_id": "IMG-R-MLO",
            "acc_anon": "ACC-1",
            "ImageLateralityFinal": "R",
            "ViewPosition": "R MLO",
            "FinalImageType": "DBT",
            "Rows": 3000,
            "Columns": 2500,
            "ImagesInAcquisition": 72,
            "ROI_coords": [(1, 2, 3, 4), (10, 20, 30, 40)],
            "ROI_frames": [12, 15],
        },
    ]

    tables = build_image_tables(rows)

    assert len(tables.images) == 2
    left_image, right_image = tables.images
    assert left_image.laterality is Laterality.LEFT
    assert left_image.patient_id == "P1"
    assert left_image.view_position is ViewPosition.CC
    assert left_image.modality is ImageModality.FFDM
    assert left_image.patient_orientation is not None
    assert left_image.patient_orientation.as_tuple() == ("P", "L")
    assert right_image.laterality is Laterality.RIGHT
    assert right_image.view_position is ViewPosition.MLO
    assert right_image.modality is ImageModality.DBT
    assert right_image.frame_count == 72
    assert [roi.image_id for roi in tables.rois] == [
        "IMG-L-CC",
        "IMG-R-MLO",
        "IMG-R-MLO",
    ]
    assert tables.rois[0].coordinates == (10, 20, 41, 61)
    assert tables.rois[0].source_coordinates == (10, 20, 40, 60)
    assert tables.rois[0].source_coordinate_convention == "inclusive_maxima"
    assert tables.rois[0].annotation_source == "synthetic"
    assert tables.rois[0].locator.kind is RoiLocatorKind.SYNTHETIC
    assert tables.rois[0].locator.source_ordinal == 0
    assert tables.rois[0].source_provenance.source_count.basis is (
        RoiSourceCountBasis.SINGLE_COORDINATE_OCCURRENCE
    )
    assert tables.rois[0].confidence == 0.8
    assert tables.rois[1].coordinates == (1, 2, 4, 5)
    assert tables.rois[1].frame_indices == (12,)
    assert tables.rois[1].source_provenance.depth_frame_provenance is (
        RoiDepthFrameProvenance.SOURCE_SUPPLIED
    )
    assert tables.rois[2].coordinates == (10, 20, 31, 41)
    assert tables.rois[2].frame_indices == (15,)


def test_dbt_roi_frames_preserve_plural_associations_and_validate_count() -> None:
    row = {
        "image_id": "DBT-1",
        "ImageLateralityFinal": "L",
        "FinalImageType": "DBT",
        "ImagesInAcquisition": 21,
        "ROI_coords": [[1, 2, 3, 4], [10, 20, 30, 40]],
        "ROI_frames": [[12, 13], [20]],
    }

    tables = build_image_tables([row])

    assert tables.images[0].frame_count == 21
    assert [roi.frame_indices for roi in tables.rois] == [(12, 13), (20,)]

    with pytest.raises(BuildPolicyError, match="below the DBT frame count"):
        build_image_tables([{**row, "ROI_frames": [[12, 13], [21]]}])


def test_dbt_roi_depth_derivation_flags_preserve_per_roi_provenance() -> None:
    row = {
        "image_id": "DBT-DERIVATION",
        "FinalImageType": "3D",
        "ImagesInAcquisition": 30,
        "ROI_coords": [[1, 2, 3, 4], [10, 20, 30, 40]],
        "ROI_frames": [[12, 13], [20]],
        "ROI_depth_derived": [True, False],
    }

    tables = build_image_tables([row])

    derived, supplied = tables.rois
    assert derived.source_provenance.depth_frame_provenance is (
        RoiDepthFrameProvenance.DERIVED
    )
    assert (
        derived.source_provenance.derivation_method
        == "internal-v2-roi-depth-derivation"
    )
    assert supplied.source_provenance.depth_frame_provenance is (
        RoiDepthFrameProvenance.SOURCE_SUPPLIED
    )
    assert supplied.source_provenance.derivation_method is None


@pytest.mark.parametrize(
    ("flags", "issue_code"),
    [
        ([True], "misaligned_roi_depth_derivation_flags"),
        ([True, 0], "invalid_roi_depth_derivation_flags"),
    ],
)
def test_roi_depth_derivation_flags_validate_alignment_and_boolean_values(
    flags: list[object],
    issue_code: str,
) -> None:
    row = {
        "image_id": "DBT-DERIVATION-INVALID",
        "FinalImageType": "3D",
        "ROI_coords": [[1, 2, 3, 4], [10, 20, 30, 40]],
        "ROI_frames": [[12], [20]],
        "ROI_depth_derived": flags,
    }

    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables([row])
    assert exc_info.value.issue.code == issue_code

    audited = build_image_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    assert audited.rois == ()
    assert audited.build_issues[0].code == issue_code


def test_derived_depth_without_frames_is_audited_without_false_provenance() -> None:
    row = {
        "image_id": "DBT-DERIVATION-NO-FRAMES",
        "FinalImageType": "3D",
        "ROI_coords": [[1, 2, 3, 4]],
        "ROI_depth_derived": [True],
    }

    audited = build_image_tables(
        [row],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    assert len(audited.rois) == 1
    assert audited.rois[0].source_provenance.depth_frame_provenance is (
        RoiDepthFrameProvenance.UNAVAILABLE_DBT
    )
    assert audited.rois[0].source_provenance.derivation_method is None
    assert audited.build_issues[0].code == (
        "derived_roi_depth_without_interpretable_frames"
    )


@pytest.mark.parametrize(
    ("derived_type", "expected_modality"),
    [
        ("2D", ImageModality.FFDM),
        ("3D", ImageModality.DBT),
        ("cview", ImageModality.S2D),
        ("ROI_SS", ImageModality.UNKNOWN),
        ("ROI_SSC", ImageModality.UNKNOWN),
        ("other", ImageModality.UNKNOWN),
        ("future-pipeline-type", ImageModality.UNKNOWN),
    ],
)
def test_image_builder_preserves_open_derived_image_type(
    derived_type: str,
    expected_modality: ImageModality,
) -> None:
    tables = build_image_tables(
        [
            {
                "image_id": f"image-{derived_type}",
                "Modality": "MG",
                "FinalImageType": derived_type,
            }
        ]
    )

    image = tables.images[0]
    assert image.source_modality == "MG"
    assert image.derived_image_type == derived_type
    assert image.modality is expected_modality
    assert image.to_dict()["source_modality"] == "MG"
    assert image.to_dict()["derived_image_type"] == derived_type


def test_roi_frame_collections_follow_strict_and_audit_policy() -> None:
    dbt_row = {
        "image_id": "DBT-1",
        "FinalImageType": "DBT",
        "ROI_coords": [[1, 2, 3, 4], [10, 20, 30, 40]],
    }
    with pytest.raises(BuildPolicyError, match="align exactly"):
        build_image_tables([{**dbt_row, "ROI_frames": [[12, 13]]}])

    empty = build_image_tables([{**dbt_row, "ROI_frames": [[], []]}])
    assert [roi.frame_indices for roi in empty.rois] == [(), ()]
    assert all(
        roi.source_provenance.depth_frame_provenance
        is RoiDepthFrameProvenance.UNAVAILABLE_DBT
        for roi in empty.rois
    )

    two_d_row = {
        "image_id": "2D-1",
        "FinalImageType": "2D",
        "ImagesInAcquisition": 99,
        "ROI_coords": [[1, 2, 3, 4]],
        "ROI_frames": [[7, 8]],
    }
    with pytest.raises(BuildPolicyError, match="cannot carry DBT frame"):
        build_image_tables([two_d_row])
    two_d = build_image_tables(
        [
            two_d_row
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    assert two_d.images[0].frame_count is None
    assert two_d.rois[0].frame_indices == ()
    assert two_d.build_issues[0].code == "frames_on_2d_roi"


@pytest.mark.parametrize(
    ("values", "issue_code"),
    [
        ({"ROI_coords": [1, 2, 0, 4]}, "invalid_roi_coordinates"),
        (
            {
                "FinalImageType": "DBT",
                "ROI_coords": [[1, 2, 3, 4], [5, 6, 7, 8]],
                "ROI_frames": [[2]],
            },
            "misaligned_roi_frames",
        ),
        (
            {
                "FinalImageType": "DBT",
                "ImagesInAcquisition": 3,
                "ROI_coords": [[1, 2, 3, 4]],
                "ROI_frames": [[3]],
            },
            "roi_frame_out_of_range",
        ),
        ({"FinalImageType": "unknown", "ROI_coords": [1, 2, 3, 4]}, "unknown_roi_image_modality"),
    ],
)
def test_fatal_roi_errors_omit_row_rois_in_audit(
    values: dict[str, object],
    issue_code: str,
) -> None:
    row = {"image_id": "IMG-ERROR", "ImageLateralityFinal": "L", **values}

    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables([row], source_scope="roi-errors")
    assert exc_info.value.issue.code == issue_code

    audited = build_image_tables(
        [row],
        source_scope="roi-errors",
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    assert len(audited.images) == 1
    assert audited.rois == ()
    assert audited.source_occurrences[0].resolution_state is ResolutionState.UNRESOLVED
    assert audited.build_issues[0].code == issue_code


def test_multiple_roi_confidence_recovers_with_synthetic_locators_in_audit() -> None:
    row = {
        "image_id": "IMG-RECOVER",
        "FinalImageType": "2D",
        "ROI_coords": [[1, 2, 3, 4], [5, 6, 7, 8]],
        "roi_confidence": 2.0,
    }
    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables([row], source_scope="roi-recovery")
    assert exc_info.value.issue.code == "invalid_roi_confidence"

    audited = build_image_tables(
        [row],
        source_scope="roi-recovery",
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )

    assert [issue.code for issue in audited.build_issues] == ["invalid_roi_confidence"]
    assert [roi.locator.kind for roi in audited.rois] == [
        RoiLocatorKind.SYNTHETIC,
        RoiLocatorKind.SYNTHETIC,
    ]
    assert [roi.locator.source_ordinal for roi in audited.rois] == [0, 1]
    assert all(roi.confidence is None for roi in audited.rois)
    assert all(
        roi.source_provenance.source_count.value == 2 for roi in audited.rois
    )
    assert all(
        roi.source_provenance.source_count.basis
        is RoiSourceCountBasis.ALIGNED_COORDINATE_COLLECTION
        for roi in audited.rois
    )


def test_invalid_roi_confidence_strict_error_and_audit_recovery() -> None:
    row = {
        "image_id": "IMG-CONFIDENCE",
        "FinalImageType": "2D",
        "ROI_coords": [1, 2, 3, 4],
        "roi_confidence": float("nan"),
    }
    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables([row], source_scope="roi-confidence")
    assert exc_info.value.issue.code == "invalid_roi_confidence"

    audited = build_image_tables(
        [row],
        source_scope="roi-confidence",
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    assert len(audited.rois) == 1
    assert audited.rois[0].confidence is None
    assert audited.source_occurrences[0].resolution_state is ResolutionState.UNRESOLVED


def test_duplicate_synthetic_roi_locator_deduplicates_and_governs_conflicts() -> None:
    equal = {
        "image_id": "IMG-DUP",
        "FinalImageType": "2D",
        "ROI_coords": [1, 2, 3, 4],
    }
    deduplicated = build_image_tables(
        [equal, equal],
        source_scope="roi-duplicates",
    )
    assert len(deduplicated.rois) == 1
    assert len(deduplicated.rois[0].sources) == 2

    conflicting = {**equal, "ROI_coords": [10, 20, 30, 40]}
    with pytest.raises(BuildPolicyError) as exc_info:
        build_image_tables(
            [equal, conflicting],
            source_scope="roi-duplicates",
        )
    assert exc_info.value.issue.code == "conflicting_roi_locator"

    audited = build_image_tables(
        [equal, conflicting],
        source_scope="roi-duplicates",
        build_policy=BuildPolicy(BuildMode.AUDIT),
    )
    assert len(audited.rois) == 1
    assert audited.rois[0].coordinates == (1, 2, 4, 5)
    assert audited.source_occurrences[1].resolution_state is ResolutionState.UNRESOLVED


def test_roi_projection_uses_final_reconciled_image_modality() -> None:
    tables = build_image_tables(
        [
            {
                "image_id": "IMG-LATE-MODALITY",
                "FinalImageType": "unknown",
                "ROI_coords": [1, 2, 3, 4],
            },
            {
                "image_id": "IMG-LATE-MODALITY",
                "FinalImageType": "2D",
            },
        ],
        source_scope="late-image-modality",
    )

    assert tables.images[0].modality is ImageModality.FFDM
    assert len(tables.images[0].sources) == 2
    assert len(tables.rois) == 1
    assert tables.rois[0].source_provenance.modality is ImageModality.FFDM
    assert tables.source_occurrences[0].resolution_state is ResolutionState.RESOLVED


def test_strict_duplicate_roi_failure_does_not_mutate_inputs_or_later_builds() -> None:
    first = {
        "image_id": "IMG-ATOMIC-ROI",
        "FinalImageType": "2D",
        "ROI_coords": [1, 2, 3, 4],
    }
    conflicting = {**first, "ROI_coords": [10, 20, 30, 40]}
    original_first = {**first, "ROI_coords": list(first["ROI_coords"])}
    original_conflicting = {
        **conflicting,
        "ROI_coords": list(conflicting["ROI_coords"]),
    }

    with pytest.raises(BuildPolicyError, match="conflicting_roi_locator"):
        build_image_tables(
            [first, conflicting],
            source_scope="strict-roi-atomicity",
        )

    assert first == original_first
    assert conflicting == original_conflicting
    rebuilt = build_image_tables(
        [first],
        source_scope="strict-roi-atomicity-retry",
    )
    assert len(rebuilt.images[0].sources) == 1
    assert len(rebuilt.rois) == 1


def test_equal_geometry_with_distinct_synthetic_locators_remains_distinct() -> None:
    tables = build_image_tables(
        [
            {
                "image_id": "IMG-DISTINCT",
                "FinalImageType": "2D",
                "ROI_coords": [[1, 2, 3, 4], [1, 2, 3, 4]],
            }
        ],
        source_scope="roi-distinct",
    )

    assert len(tables.rois) == 2
    assert tables.rois[0].locator != tables.rois[1].locator
    assert tables.rois[0].coordinates == tables.rois[1].coordinates


def test_builders_accept_custom_column_configuration() -> None:
    columns = EmbedColumnConfig(
        patient_id="patient_key",
        accession="accession_key",
        finding_number="finding_key",
        finding_laterality="finding_side",
        finding_assessment="assessment_value",
        finding_recommendation="recommendation_value",
        image_id="image_key",
        image_laterality="image_side",
        image_view="view_name",
        roi_coords="boxes",
        roi_frames="frames",
    )

    clinical_contract = contract_for_columns(
        INTERNAL_V2_CONTRACT,
        "custom-clinical",
        columns,
    )
    image_contract = contract_for_columns(
        INTERNAL_V1C_CONTRACT,
        "custom-image",
        columns,
    )
    clinical = build_clinical_tables(
        [
            {
                "patient_key": "P-CUSTOM",
                "accession_key": "ACC-CUSTOM",
                "finding_key": 7,
                "finding_side": "R",
                "assessment_value": "3",
                "recommendation_value": "short follow-up",
            }
        ],
        columns=columns,
        source_profile="custom-clinical",
        profile_contract=clinical_contract,
    )
    image_tables = build_image_tables(
        [
            {
                "image_key": "IMG-CUSTOM",
                "accession_key": "ACC-CUSTOM",
                "image_side": "R",
                "view_name": "MLO",
                "FinalImageType": "DBT",
                "boxes": [[5, 6, 7, 8]],
                "frames": [4],
            }
        ],
        columns=columns,
        source_profile="custom-image",
        profile_contract=image_contract,
    )

    assert clinical.findings[0].identity == ("ACC-CUSTOM", "7")
    assert clinical.findings[0].interpretation is clinical.interpretations[0]
    assert clinical.interpretations[0].assessment == "3"
    assert clinical.interpretations[0].recommendation == "short follow-up"
    assert image_tables.images[0].image_id == "IMG-CUSTOM"
    assert image_tables.images[0].view_position is ViewPosition.MLO
    assert image_tables.rois[0].coordinates == (5, 6, 8, 9)
    assert image_tables.rois[0].frame_indices == (4,)


def test_candidate_projection_is_explicit_and_uses_assembled_hierarchy() -> None:
    clinical = build_clinical_tables(
        [
            {"empi_anon": "P1", "acc_anon": "ACC-1", "numfind": "L", "side": "L"},
            {"empi_anon": "P1", "acc_anon": "ACC-1", "numfind": "R", "side": "R"},
            {"empi_anon": "P1", "acc_anon": "ACC-1", "numfind": "B", "side": "B"},
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-1",
                "numfind": "U",
                "side": "unknown-code",
            },
        ]
    )
    image_tables = build_image_tables(
        [
            {
                "image_id": "ACC1-L",
                "acc_anon": "ACC-1",
                "ImageLateralityFinal": "L",
                "ViewPosition": "CC",
            },
            {
                "image_id": "ACC1-R",
                "acc_anon": "ACC-1",
                "ImageLateralityFinal": "R",
                "ViewPosition": "CC",
            },
            {
                "image_id": "ACC2-L",
                "acc_anon": "ACC-2",
                "ImageLateralityFinal": "L",
                "ViewPosition": "CC",
            },
        ]
    )

    graph = assemble_clinical_image_graph(clinical, image_tables)
    projections = project_finding_image_candidates(graph)
    candidate_ids = {
        projection.finding.finding_id: [
            candidate.image.image_id for candidate in projection.candidates
        ]
        for projection in projections
    }

    assert candidate_ids == {
        "ACC-1:L": ["ACC1-L"],
        "ACC-1:R": ["ACC1-R"],
        "ACC-1:B": ["ACC1-L", "ACC1-R"],
        "ACC-1:U": [],
    }
    assert all(
        projection.status is AttributionStatus.CANDIDATE
        for projection in projections
    )
