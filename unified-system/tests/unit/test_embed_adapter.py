from __future__ import annotations

from embed_toolkit.adapters.embed import (
    build_clinical_tables,
    build_image_tables,
    join_findings_to_images,
)
from embed_toolkit.config.columns import EmbedColumnConfig
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition


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
    assert finding.identity == ("ACC-1", Laterality.LEFT, "1")
    assert finding.finding_type == "mass"
    assert finding.assessment == "4"
    assert [procedure.procedure_id for procedure in finding.procedures] == [
        "BIO-1",
        "LUMP-1",
    ]
    assert [event.diagnosis for event in finding.pathology_events] == [
        "fibroadenoma",
        "dcis",
    ]
    assert finding.pathology_events[0].malignant is False
    assert finding.pathology_events[1].malignant is True
    assert tables.breast_sides[0].laterality is Laterality.LEFT
    assert tables.breast_sides[0].findings == [finding]


def test_clinical_builder_expands_bilateral_findings_to_breast_sides() -> None:
    tables = build_clinical_tables(
        [
            {
                "empi_anon": "P1",
                "acc_anon": "ACC-B",
                "numfind": "2",
                "side": "B",
                "procedure_id": "BIO-B",
            }
        ]
    )

    assert [finding.laterality for finding in tables.findings] == [
        Laterality.LEFT,
        Laterality.RIGHT,
    ]
    assert [side.laterality for side in tables.breast_sides] == [
        Laterality.LEFT,
        Laterality.RIGHT,
    ]
    assert [len(finding.procedures) for finding in tables.findings] == [1, 1]


def test_image_builder_constructs_images_and_rois_without_clinical_rows() -> None:
    rows = [
        {
            "image_id": "IMG-L-CC",
            "acc_anon": "ACC-1",
            "ImageLateralityFinal": "L",
            "ViewPosition": "L CC",
            "FinalImageType": "2D",
            "Rows": 2048,
            "Columns": 1536,
            "SOPInstanceUID": "sop-1",
            "PatientOrientation": "['P', 'L']",
            "roi_id": "ROI-1",
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
            "NumberOfFrames": 72,
            "ROI_coords": [(1, 2, 3, 4), (10, 20, 30, 40)],
            "ROI_frames": [12, 15],
        },
    ]

    tables = build_image_tables(rows)

    assert len(tables.images) == 2
    left_image, right_image = tables.images
    assert left_image.laterality is Laterality.LEFT
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
    assert tables.rois[0].source == "synthetic"
    assert tables.rois[0].confidence == 0.8
    assert tables.rois[1].coordinates == (1, 2, 4, 5)
    assert tables.rois[1].frame_index == 12
    assert tables.rois[2].coordinates == (10, 20, 31, 41)
    assert tables.rois[2].frame_index == 15


def test_builders_accept_custom_column_configuration() -> None:
    columns = EmbedColumnConfig(
        patient_id="patient_key",
        accession="accession_key",
        finding_number="finding_key",
        finding_laterality="finding_side",
        finding_assessment="assessment_value",
        image_id="image_key",
        image_laterality="image_side",
        image_view="view_name",
        roi_coords="boxes",
        roi_frames="frames",
    )

    clinical = build_clinical_tables(
        [
            {
                "patient_key": "P-CUSTOM",
                "accession_key": "ACC-CUSTOM",
                "finding_key": 7,
                "finding_side": "R",
                "assessment_value": "3",
            }
        ],
        columns=columns,
    )
    image_tables = build_image_tables(
        [
            {
                "image_key": "IMG-CUSTOM",
                "accession_key": "ACC-CUSTOM",
                "image_side": "R",
                "view_name": "MLO",
                "boxes": [[5, 6, 7, 8]],
                "frames": [4],
            }
        ],
        columns=columns,
    )

    assert clinical.findings[0].identity == ("ACC-CUSTOM", Laterality.RIGHT, "7")
    assert clinical.findings[0].assessment == "3"
    assert image_tables.images[0].image_id == "IMG-CUSTOM"
    assert image_tables.images[0].view_position is ViewPosition.MLO
    assert image_tables.rois[0].coordinates == (5, 6, 8, 9)
    assert image_tables.rois[0].frame_index == 4


def test_side_aware_join_is_explicit_and_respects_accession() -> None:
    clinical = build_clinical_tables(
        [
            {"empi_anon": "P1", "acc_anon": "ACC-1", "numfind": "L", "side": "L"},
            {"empi_anon": "P1", "acc_anon": "ACC-1", "numfind": "R", "side": "R"},
            {"empi_anon": "P1", "acc_anon": "ACC-1", "numfind": "B", "side": "B"},
            {"empi_anon": "P1", "acc_anon": "ACC-1", "numfind": "U"},
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

    joins = join_findings_to_images(clinical.findings, image_tables.images)
    joined_ids = {
        join.finding.finding_id: [image.image_id for image in join.images]
        for join in joins
    }

    assert joined_ids == {
        "ACC-1:L:L": ["ACC1-L"],
        "ACC-1:R:R": ["ACC1-R"],
        "ACC-1:L:B": ["ACC1-L"],
        "ACC-1:R:B": ["ACC1-R"],
        "ACC-1:UNKNOWN:U": ["ACC1-L", "ACC1-R"],
    }
