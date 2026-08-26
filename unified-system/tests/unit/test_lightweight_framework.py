from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from embed_toolkit import (
    Box,
    DatasetGraph,
    LoadError,
    MammogramImage,
    RegionOfInterest,
    load_embed,
)
from embed_toolkit.adapters.tables import iter_records
from embed_toolkit.clinical.attributes import (
    PatientAttributeAsOfPolicy,
    PatientAttributeName,
    PatientObservationTimeBasis,
    UndatedObservationPolicy,
    select_patient_attribute_as_of,
)
from embed_toolkit.core.source import CanonicalKey, SourceRef
from embed_toolkit.core.primitives import ImageModality, Laterality, ViewPosition


def test_source_keys_are_typed_and_round_trip() -> None:
    refs = [
        SourceRef("scope", "table", True),
        SourceRef("scope", "table", 1),
        SourceRef("scope", "table", 1.0),
        SourceRef("scope", "table", "1"),
        SourceRef("scope", "table", date(2020, 1, 2)),
        SourceRef("scope", "table", datetime(2020, 1, 2, 3, 4)),
        SourceRef("scope", "table", (1, "1")),
    ]

    assert len(set(refs)) == len(refs)
    assert [SourceRef.from_dict(ref.to_dict()) for ref in refs] == refs


def test_dataframe_index_and_numpy_scalars_become_canonical_keys() -> None:
    frame = pd.DataFrame(
        {"empi_anon": ["P-2", "P-4"]},
        index=pd.Index([2, 4], name="original_row"),
    )

    records = list(iter_records(frame))

    assert [record.source_key for record in records] == [
        CanonicalKey("int", 2),
        CanonicalKey("int", 4),
    ]
    assert all(record.issues == () for record in records)


def test_multiindex_is_typed_and_duplicate_index_falls_back_visibly() -> None:
    multi = pd.DataFrame(
        {"empi_anon": ["P-1", "P-2"]},
        index=pd.MultiIndex.from_tuples([("site-a", 1), ("site-b", 2)]),
    )
    duplicate = pd.DataFrame(
        {"empi_anon": ["P-1", "P-2"]},
        index=pd.Index([7, 7]),
    )

    multi_records = list(iter_records(multi))
    duplicate_records = list(iter_records(duplicate))

    assert multi_records[0].source_key == CanonicalKey(
        "tuple",
        (CanonicalKey("string", "site-a"), CanonicalKey("int", 1)),
    )
    assert [record.source_key for record in duplicate_records] == [
        CanonicalKey("int", 0),
        CanonicalKey("int", 1),
    ]
    assert all(
        any(issue.code == "duplicate_source_index" for issue in record.issues)
        for record in duplicate_records
    )


def test_requested_duplicate_or_nullable_keys_are_not_claimed_stable() -> None:
    frame = pd.DataFrame(
        {
            "source_id": pd.Series(["same", "same", pd.NA], dtype="string"),
            "empi_anon": ["P-1", "P-2", "P-3"],
        }
    )

    records = list(iter_records(frame, key="source_id"))

    assert all(record.source_key is None for record in records)
    assert [record.issues[0].code for record in records] == [
        "duplicate_source_key",
        "duplicate_source_key",
        "unusable_source_key",
    ]


def test_patient_and_exam_tables_load_independently() -> None:
    patients = load_embed(
        patients=pd.DataFrame({"empi_anon": [" P-1 "]}, index=[11]),
        source_scope="release-1",
        identity_namespace="embed-2",
    )
    exams = load_embed(
        exams=pd.DataFrame({"acc_anon": [" A-1 "]}, index=[22]),
        source_scope="release-1",
        identity_namespace="embed-2",
    )

    assert [patient.patient_id for patient in patients.graph.patients] == ["P-1"]
    assert patients.graph.exams == ()
    assert [exam.accession_number for exam in exams.graph.exams] == ["A-1"]
    assert exams.graph.patients == ()
    assert patients.issues == exams.issues == ()


def test_incremental_order_resolves_to_the_same_canonical_objects() -> None:
    graph = DatasetGraph(identity_namespace="embed-2", source_scope="release-1")

    exam_report = load_embed(
        exams=[{"acc_anon": "A-1", "empi_anon": "P-1"}], into=graph
    )
    exam = graph.exam("A-1")
    assert exam is not None
    assert graph.patient("P-1") is None

    patient_report = load_embed(patients=[{"empi_anon": "P-1"}], into=graph)

    patient = graph.patient("P-1")
    assert patient_report.graph is exam_report.graph is graph
    assert patient is not None
    assert patient.exams == [exam]
    assert graph.exam("A-1") is exam


def test_nullable_identifiers_never_manufacture_domain_identity() -> None:
    frame = pd.DataFrame(
        {"empi_anon": pd.Series([pd.NA, float("nan"), "   "], dtype="object")}
    )

    report = load_embed(patients=frame, source_scope="release-1")

    assert report.graph.patients == ()
    assert [issue.code for issue in report.issues] == [
        "missing_patient_id",
        "missing_patient_id",
        "missing_patient_id",
    ]


def test_numeric_identifiers_are_deliberate_and_boolean_ids_are_invalid() -> None:
    report = load_embed(
        patients=pd.DataFrame({"empi_anon": [1.0, True]}),
        source_scope="release-1",
    )

    assert [patient.patient_id for patient in report.graph.patients] == ["1"]
    assert [issue.code for issue in report.issues] == ["invalid_patient_id"]


def test_partial_column_maps_allow_renames_and_optional_unbinding() -> None:
    report = load_embed(
        exams=[{"custom_accession": "A-1", "unused": "ignored"}],
        columns={
            "exams": {
                "accession": "custom_accession",
                "patient_id": None,
                "exam_description": None,
            }
        },
    )

    assert report.graph.exam("A-1") is not None
    assert report.issues == ()


def test_audit_commits_safe_rows_and_strict_rolls_back_invocation() -> None:
    graph = DatasetGraph(source_scope="release-1")
    audit = load_embed(
        patients=[{"empi_anon": "P-1"}, {"empi_anon": pd.NA}],
        into=graph,
    )
    assert graph.patient("P-1") is not None
    assert [issue.code for issue in audit.issues] == ["missing_patient_id"]

    with pytest.raises(LoadError, match="missing_accession"):
        load_embed(
            patients=[{"empi_anon": "P-2"}],
            exams=[{"acc_anon": pd.NA}],
            into=graph,
            source_scope="release-2",
            mode="strict",
        )

    assert graph.patient("P-2") is None
    assert [patient.patient_id for patient in graph.patients] == ["P-1"]


def test_replay_is_idempotent_and_changed_same_address_conflicts() -> None:
    graph = DatasetGraph(source_scope="release-1")
    first = pd.DataFrame({"empi_anon": ["P-1"]}, index=[101])

    load_embed(patients=first, into=graph)
    replay = load_embed(patients=first.copy(), into=graph)
    changed = load_embed(
        patients=pd.DataFrame({"empi_anon": ["P-2"]}, index=[101]),
        into=graph,
    )

    assert replay.issues == ()
    assert [patient.patient_id for patient in graph.patients] == ["P-1"]
    assert [issue.code for issue in changed.issues] == ["source_contribution_conflict"]
    assert graph.issues == changed.issues


def test_issue_replay_is_reported_per_invocation_but_deduplicated_on_graph() -> None:
    graph = DatasetGraph(source_scope="release-1")
    bad = pd.DataFrame({"empi_anon": [pd.NA]}, index=[5])

    first = load_embed(patients=bad, into=graph)
    replay = load_embed(patients=bad.copy(), into=graph)

    assert first.issues == replay.issues
    assert graph.issues == first.issues


def test_distinct_conflicting_observations_leave_exam_field_unresolved() -> None:
    report = load_embed(
        exams=pd.DataFrame(
            {
                "acc_anon": ["A-1", "A-1"],
                "desc": ["screening", "diagnostic"],
            },
            index=[1, 2],
        ),
        source_scope="release-1",
    )

    assert report.graph.exam("A-1").description is None
    assert [issue.code for issue in report.issues] == ["conflicting_exam_field"]


def test_namespace_mismatch_fails_before_consuming_input() -> None:
    graph = DatasetGraph(identity_namespace="release-1")

    def rows():
        raise AssertionError("input must not be consumed")
        yield {}

    with pytest.raises(ValueError, match="identity_namespace"):
        load_embed(patients=rows(), into=graph, identity_namespace="release-2")


def test_graph_root_collections_are_read_only_views() -> None:
    report = load_embed(patients=[{"empi_anon": "P-1"}])

    assert isinstance(report.graph.patients, tuple)
    with pytest.raises(AttributeError):
        report.graph.patients.append(report.graph.patients[0])


def test_finding_table_loads_alone_and_establishes_exam_ownership() -> None:
    report = load_embed(
        findings=pd.DataFrame(
            {
                "acc_anon": ["A-1", "A-1"],
                "numfind": [1, 2],
                "side": ["L", "B"],
                "asses": ["4", "2"],
                "recc": ["biopsy", "routine"],
            },
            index=[31, 32],
        ),
        source_scope="release-1",
    )

    exam = report.graph.exam("A-1")
    assert exam is not None
    assert report.graph.patients == ()
    assert exam.findings == list(report.graph.findings)
    assert [
        finding.finding_number
        for finding in exam.breast_sides[Laterality.LEFT].findings
    ] == [
        "1",
        "2",
    ]
    assert [
        finding.finding_number
        for finding in exam.breast_sides[Laterality.RIGHT].findings
    ] == [
        "2"
    ]
    assert report.graph.finding("A-1", "1").interpretation.assessment == "4"
    assert report.issues == ()


def test_finding_identity_does_not_depend_on_side_or_interpretation() -> None:
    report = load_embed(
        findings=[{"acc_anon": "A-1", "numfind": "7"}],
        columns={
            "findings": {
                "laterality": None,
                "assessment": None,
                "recommendation": None,
            }
        },
    )

    finding = report.graph.finding("A-1", "7")
    assert finding is not None
    assert finding.laterality.value == "UNKNOWN"
    assert finding.interpretation is None
    assert report.issues == ()


def test_finding_conflicts_are_order_independent_and_leave_field_unresolved() -> None:
    report = load_embed(
        findings=pd.DataFrame(
            {
                "acc_anon": ["A-1", "A-1"],
                "numfind": [1, 1],
                "side": ["L", "R"],
            },
            index=[1, 2],
        ),
        source_scope="release-1",
    )

    finding = report.graph.finding("A-1", "1")
    assert finding.laterality.value == "UNKNOWN"
    assert [issue.code for issue in report.issues] == ["conflicting_finding_field"]
    assert report.graph.exam("A-1").breast_sides == {}


def test_finding_load_enriches_existing_canonical_exam_and_patient() -> None:
    graph = DatasetGraph(source_scope="release-1")
    load_embed(
        patients=[{"empi_anon": "P-1"}],
        exams=[{"acc_anon": "A-1", "empi_anon": "P-1"}],
        into=graph,
    )
    exam = graph.exam("A-1")

    load_embed(
        findings=[{"acc_anon": "A-1", "numfind": "1", "side": "R"}],
        into=graph,
    )

    assert graph.exam("A-1") is exam
    assert graph.patient("P-1").exams == [exam]
    assert exam.findings == [graph.finding("A-1", "1")]


def test_image_table_loads_alone_without_manufacturing_clinical_nodes() -> None:
    report = load_embed(
        images=pd.DataFrame(
            {
                "anon_dicom_path": ["images/1.dcm"],
                "empi_anon": ["P-1"],
                "acc_anon": ["A-1"],
                "ImageLateralityFinal": ["L"],
                "ViewPosition": ["CC"],
                "Modality": ["DBT"],
                "Rows": [2048],
                "Columns": [1664],
                "ImagesInAcquisition": [50],
            },
            index=[91],
        ),
        source_scope="release-1",
    )

    image = report.graph.image("images/1.dcm")
    assert image is not None
    assert image.modality is ImageModality.DBT
    assert image.image_shape == (2048, 1664)
    assert report.graph.patients == report.graph.exams == ()
    assert {
        (reference.target_kind, reference.target_id, reference.reason)
        for reference in report.graph.unresolved_references
    } == {
        ("patient", "P-1", "missing_target"),
        ("exam", "A-1", "missing_target"),
    }


def test_clinical_load_resolves_image_edges_onto_same_canonical_graph() -> None:
    graph = DatasetGraph(source_scope="release-1")
    load_embed(
        images=[
            {
                "anon_dicom_path": "images/1.dcm",
                "empi_anon": "P-1",
                "acc_anon": "A-1",
                "ImageLateralityFinal": "R",
                "ViewPosition": "MLO",
            }
        ],
        into=graph,
    )
    image = graph.image("images/1.dcm")

    load_embed(
        patients=[{"empi_anon": "P-1"}],
        exams=[{"acc_anon": "A-1", "empi_anon": "P-1"}],
        into=graph,
    )

    exam = graph.exam("A-1")
    assert graph.image("images/1.dcm") is image
    assert exam.images == [image]
    assert exam.breast_sides[Laterality.RIGHT].images == [image]
    assert graph.patient("P-1").exams == [exam]
    assert graph.unresolved_references == ()


def test_image_patient_conflict_remains_unresolved_and_unattached() -> None:
    report = load_embed(
        patients=[{"empi_anon": "P-1"}, {"empi_anon": "P-2"}],
        exams=[{"acc_anon": "A-1", "empi_anon": "P-1"}],
        images=[
            {
                "anon_dicom_path": "images/1.dcm",
                "acc_anon": "A-1",
                "empi_anon": "P-2",
            }
        ],
        source_keys={
            "patients": lambda row: row["empi_anon"],
        },
    )

    assert report.graph.exam("A-1").images == []
    assert [reference.reason for reference in report.graph.unresolved_references] == [
        "conflicting_patient"
    ]


def test_manual_image_construction_does_not_require_audit_provenance() -> None:
    image = MammogramImage(
        image_id="manual-1",
        laterality=Laterality.LEFT,
        view_position=ViewPosition.CC,
    )

    assert image.sources == []
    with pytest.raises(ValueError, match="no source evidence"):
        _ = image.canonical_source


def test_roi_table_loads_alone_with_image_scoped_identity() -> None:
    report = load_embed(
        rois=pd.DataFrame(
            {
                "anon_dicom_path": ["images/1.dcm"],
                "ROI_coords": ["[10, 20, 19, 29]"],
                "ROI_frames": ["[4, 5]"],
            },
            index=[44],
        ),
        source_scope="release-1",
    )

    roi = report.graph.rois[0]
    assert roi.image_id == "images/1.dcm"
    assert roi.coordinates == (10.0, 20.0, 20.0, 30.0)
    assert roi.source_coordinates == (10.0, 20.0, 19.0, 29.0)
    assert roi.frame_indices == (4, 5)
    assert report.graph.images == ()
    assert [reference.target_kind for reference in report.graph.unresolved_references] == [
        "image"
    ]


def test_later_image_load_resolves_roi_without_replacing_canonical_roi() -> None:
    graph = DatasetGraph(source_scope="release-1")
    load_embed(
        rois=[
            {
                "anon_dicom_path": "images/1.dcm",
                "roi_id": "box-1",
                "ROI_coords": [1, 2, 3, 4],
            }
        ],
        columns={"rois": {"roi_key": "roi_id"}},
        into=graph,
    )
    roi = graph.roi("images/1.dcm", "box-1")

    load_embed(
        images=[{"anon_dicom_path": "images/1.dcm"}],
        into=graph,
    )

    image = graph.image("images/1.dcm")
    assert graph.roi("images/1.dcm", "box-1") is roi
    assert image.rois == [roi]
    assert graph.unresolved_references == ()


def test_conflicting_roi_geometry_is_visible_without_resolved_convenience() -> None:
    report = load_embed(
        rois=pd.DataFrame(
            {
                "anon_dicom_path": ["images/1.dcm", "images/1.dcm"],
                "roi_id": ["box-1", "box-1"],
                "ROI_coords": [[1, 2, 3, 4], [10, 20, 30, 40]],
            },
            index=[1, 2],
        ),
        columns={"rois": {"roi_key": "roi_id"}},
        source_scope="release-1",
    )

    assert report.graph.roi("images/1.dcm", "box-1") is None
    assert "conflicting_roi_field" in [issue.code for issue in report.issues]
    assert any(
        reference.reason == "conflicting_values"
        for reference in report.graph.unresolved_references
    )


def test_manual_box_and_roi_do_not_require_source_provenance() -> None:
    box = Box(1, 2, 11, 22)
    roi = RegionOfInterest(
        coordinates=box,
        image_id="manual-image",
        roi_key="manual-roi",
    )

    assert roi.identity == ("manual-image", "manual-roi")
    assert roi.coordinates == box.as_tuple()
    assert roi.sources == ()
    assert roi.area == 200.0


def test_auxiliary_histories_load_onto_one_canonical_patient() -> None:
    report = load_embed(
        hormone_history=pd.DataFrame(
            {
                "empi_anon": ["P-1"],
                "type": ["H"],
                "code": ["ESTRO"],
                "current": ["Y"],
                "first_age": [42],
            },
            index=[101],
        ),
        procedure_history=pd.DataFrame(
            {
                "empi_anon": ["P-1"],
                "type": ["B"],
                "pcode": ["SB"],
                "side": ["L"],
                "result": ["BEN"],
            },
            index=[202],
        ),
        source_scope="release-1",
    )

    patient = report.graph.patient("P-1")
    assert patient is not None
    assert len(report.graph.histories) == 2
    assert tuple(patient.history_observations) == report.graph.histories
    assert patient.medication_history[0].medication == "estrogen"
    assert patient.medication_history[0].started.age == 42.0
    assert patient.procedure_history[0].detail == "stereotactic_core_biopsy"
    assert patient.procedure_history[0].reported_result == "benign"
    assert report.issues == ()


def test_history_then_exam_enriches_same_patient_identity() -> None:
    graph = DatasetGraph(source_scope="release-1")
    load_embed(
        procedure_history=[
            {"empi_anon": "P-1", "type": "B", "pcode": "L"}
        ],
        into=graph,
    )
    patient = graph.patient("P-1")

    load_embed(
        exams=[{"acc_anon": "A-1", "empi_anon": "P-1"}],
        into=graph,
    )

    assert graph.patient("P-1") is patient
    assert patient.exams == [graph.exam("A-1")]
    assert len(patient.history_observations) == 1


def test_invalid_history_child_rolls_back_safe_parent_in_strict_mode() -> None:
    graph = DatasetGraph(source_scope="release-1")

    with pytest.raises(LoadError, match="incomplete_medication_history_identity"):
        load_embed(
            hormone_history=[{"empi_anon": "P-1", "type": "H"}],
            into=graph,
            mode="strict",
        )

    assert graph.patient("P-1") is None
    assert graph.histories == ()


def test_audit_history_retains_safe_patient_when_child_is_incomplete() -> None:
    report = load_embed(
        hormone_history=[{"empi_anon": "P-1", "type": "H"}],
    )

    assert report.graph.patient("P-1") is not None
    assert report.graph.histories == ()
    assert [issue.code for issue in report.issues] == [
        "incomplete_medication_history_identity"
    ]


def test_verified_procedure_table_uses_governed_identity_and_patient() -> None:
    report = load_embed(
        procedures=pd.DataFrame(
            {
                "empi_anon": ["P-1", "P-1"],
                "procdate_anon": ["2020-01-02", "2020-01-02"],
                "type": ["biopsy", "biopsy"],
                "bside": ["L", "L"],
            },
            index=[11, 12],
        ),
        source_scope="release-1",
    )

    assert report.graph.patient("P-1") is not None
    assert len(report.graph.procedures) == 1
    procedure = report.graph.procedures[0]
    assert procedure.identity.patient_id == "P-1"
    assert procedure.identity.laterality is Laterality.LEFT
    assert len(procedure.sources) == 2
    assert report.issues == ()


def test_incomplete_procedure_keeps_safe_patient_only_in_audit_mode() -> None:
    report = load_embed(procedures=[{"empi_anon": "P-1", "type": "biopsy"}])

    assert report.graph.patient("P-1") is not None
    assert report.graph.procedures == ()
    assert [issue.code for issue in report.issues] == [
        "incomplete_procedure_identity"
    ]


def test_pathology_only_preserves_row_diagnosis_and_slot_observations() -> None:
    report = load_embed(
        pathology=pd.DataFrame(
            {
                "pathology_diagnosis": ["invasive ductal carcinoma"],
                "pathology_result_category": ["malignant"],
                "pathology_malignant": ["Y"],
                "path_severity": [5],
                "pdate_anon": ["2020-02-03"],
                "path1": ["ductal carcinoma"],
                "path2": ["necrosis"],
            },
            index=[501],
        ),
        source_scope="release-1",
    )

    assert report.graph.patients == report.graph.exams == ()
    diagnosis = report.graph.pathology_diagnoses[0]
    assert diagnosis.diagnosis == "invasive ductal carcinoma"
    assert diagnosis.severity == 5
    assert diagnosis.report_documented_date == "2020-02-03"
    assert [item.source_slot for item in report.graph.pathology_observations] == [
        "path1",
        "path2",
    ]
    assert report.issues == ()


def test_pathology_severity_failure_keeps_evidence_in_audit_and_rolls_back_strict() -> None:
    row = {"path_severity": 99, "path1": "descriptor"}
    audit = load_embed(pathology=[row])

    assert len(audit.graph.pathology_diagnoses) == 1
    assert len(audit.graph.pathology_observations) == 1
    assert audit.graph.pathology_diagnoses[0].severity is None
    assert [issue.code for issue in audit.issues] == ["invalid_pathology_severity"]

    graph = DatasetGraph()
    with pytest.raises(LoadError, match="invalid_pathology_severity"):
        load_embed(pathology=[row], into=graph, mode="strict")
    assert graph.pathology_diagnoses == ()
    assert graph.pathology_observations == ()


def test_equal_pathology_descriptors_from_distinct_rows_remain_distinct_evidence() -> None:
    report = load_embed(
        pathology=pd.DataFrame(
            {"path_severity": [1, 1], "path1": ["benign", "benign"]},
            index=[1, 2],
        ),
        source_scope="release-1",
    )

    assert len(report.graph.pathology_diagnoses) == 2
    assert len(report.graph.pathology_observations) == 2
    assert (
        report.graph.pathology_observations[0].source
        != report.graph.pathology_observations[1].source
    )


def test_procedure_links_resolve_to_existing_exam_and_finding() -> None:
    report = load_embed(
        patients=[{"empi_anon": "P-1"}],
        exams=[{"acc_anon": "A-1", "empi_anon": "P-1"}],
        findings=[{"acc_anon": "A-1", "numfind": "1", "side": "L"}],
        procedures=[
            {
                "empi_anon": "P-1",
                "procdate_anon": "2020-01-02",
                "type": "biopsy",
                "bside": "L",
                "acc_anon": "A-1",
                "numfind": "1",
            }
        ],
    )

    assert {
        (link.source_kind, link.target_kind) for link in report.graph.links
    } == {
        ("procedure", "patient"),
        ("procedure", "exam"),
        ("procedure", "breast_side"),
        ("procedure", "finding"),
    }
    assert report.graph.unresolved_references == ()


def test_pathology_attribution_resolves_incrementally_without_losing_evidence() -> None:
    graph = DatasetGraph(source_scope="release-1")
    load_embed(
        pathology=[
            {
                "empi_anon": "P-1",
                "acc_anon": "A-1",
                "numfind": "1",
                "bside": "R",
                "path_severity": 4,
                "path1": "carcinoma",
            }
        ],
        into=graph,
    )
    diagnosis = graph.pathology_diagnoses[0]
    observation = graph.pathology_observations[0]

    assert graph.links == ()
    assert {
        reference.target_kind for reference in graph.unresolved_references
    } == {"patient", "exam", "breast_side", "finding"}

    load_embed(
        patients=[{"empi_anon": "P-1"}],
        exams=[{"acc_anon": "A-1", "empi_anon": "P-1"}],
        findings=[{"acc_anon": "A-1", "numfind": "1", "side": "R"}],
        into=graph,
    )

    assert graph.pathology_diagnoses[0] is diagnosis
    assert graph.pathology_observations[0] is observation
    assert len(graph.links) == 8
    assert graph.unresolved_references == ()


def test_wide_magview_projects_supported_grains_through_one_graph() -> None:
    report = load_embed(
        magview=pd.DataFrame(
            {
                "row_id": ["mv-1"],
                "empi_anon": ["P-1"],
                "acc_anon": ["A-1"],
                "numfind": ["1"],
                "side": ["L"],
                "asses": ["4"],
                "recc": ["biopsy"],
                "procdate_anon": ["2020-01-02"],
                "type": ["biopsy"],
                "bside": ["L"],
                "path_severity": [4],
                "path1": ["carcinoma"],
            }
        ),
        source_keys={"magview": "row_id"},
        source_scope="release-1",
    )

    patient = report.graph.patient("P-1")
    exam = report.graph.exam("A-1")
    finding = report.graph.finding("A-1", "1")
    assert patient.exams == [exam]
    assert exam.findings == [finding]
    assert finding.interpretation.assessment == "4"
    assert len(report.graph.procedures) == 1
    assert len(report.graph.pathology_diagnoses) == 1
    assert len(report.graph.pathology_observations) == 1
    assert all(
        source.source_table == "magview"
        for source in (
            *finding.interpretation.sources,
            *report.graph.procedures[0].sources,
        )
    )
    assert report.issues == ()


def test_wide_magview_does_not_require_child_grains_or_reiterate_input() -> None:
    def rows():
        yield {"empi_anon": "P-1", "acc_anon": "A-1"}
        yield {"empi_anon": "P-2"}

    report = load_embed(magview=rows(), source_scope="release-1")

    assert [patient.patient_id for patient in report.graph.patients] == ["P-1", "P-2"]
    assert [exam.accession_number for exam in report.graph.exams] == ["A-1"]
    assert report.graph.findings == ()
    assert report.graph.procedures == ()
    assert report.graph.pathology_diagnoses == ()
    assert report.issues == ()


def test_explicit_and_wide_tables_contribute_distinct_source_evidence() -> None:
    report = load_embed(
        findings=[
            {"acc_anon": "A-1", "numfind": "1", "side": "R", "asses": "3"}
        ],
        magview=[
            {"acc_anon": "A-1", "numfind": "1", "side": "R", "asses": "3"}
        ],
        source_scope="release-1",
    )

    finding = report.graph.finding("A-1", "1")
    assert {source.source_table for source in finding.interpretation.sources} == {
        "findings",
        "magview",
    }
    assert report.issues == ()


def test_patient_attributes_preserve_source_and_temporal_context() -> None:
    report = load_embed(
        patients=pd.DataFrame(
            {
                "empi_anon": ["P-1", "P-1"],
                "GENDER_DESC": ["F", "F"],
                "birth_year": ["1970", 1970.0],
                "studydate_anon": ["20200102", "2021-03-04"],
            },
            index=[1, 2],
        ),
        source_scope="release-1",
    )

    patient = report.graph.patient("P-1")
    assert len(patient.attribute_observations) == 4
    assert patient.attribute_observations == list(
        report.graph.patient_attribute_observations
    )
    selected = select_patient_attribute_as_of(
        patient.attribute_observations,
        patient_id="P-1",
        attribute=PatientAttributeName.BIRTH_YEAR,
        policy=PatientAttributeAsOfPolicy(
            as_of_date=date(2021, 12, 31),
            time_basis=PatientObservationTimeBasis.EXAM_DATE_CONTEXT,
            undated=UndatedObservationPolicy.REJECT,
        ),
    )
    assert selected.selected_value == 1970
    assert selected.selected_context_date == date(2021, 3, 4)
    assert report.issues == ()


def test_invalid_patient_attribute_does_not_erase_safe_patient_in_audit() -> None:
    report = load_embed(
        patients=[
            {
                "empi_anon": "P-1",
                "birth_year": "1970.5",
                "studydate_anon": "not-a-date",
            }
        ]
    )

    assert report.graph.patient("P-1") is not None
    assert report.graph.patient_attribute_observations == ()
    assert [issue.code for issue in report.issues] == [
        "invalid_patient_attribute_value"
    ]


def test_patient_attribute_error_rolls_back_patient_in_strict_mode() -> None:
    graph = DatasetGraph()
    with pytest.raises(LoadError, match="invalid_patient_attribute_value"):
        load_embed(
            patients=[{"empi_anon": "P-1", "birth_year": True}],
            into=graph,
            mode="strict",
        )
    assert graph.patient("P-1") is None
