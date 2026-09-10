"""Synthetic review diagnostics for revision 15fd8b7; no private data.

Run from unified-system:
    .venv/bin/python -c 'import runpy; runpy.run_path(
        "../docs/archive/scaffold-assessment-probes-2026-09-09.py", run_name="__main__")'

Print observed behavior rather than asserting bugs as desired behavior. This is
an assessment artifact, not the package regression suite. Performance figures
are diagnostic single runs and will vary by machine.
"""

import json
from time import perf_counter

import pandas as pd
from embed_toolkit import DatasetGraph, Exam, SourceRef, load_embed
from embed_toolkit.clinical.associations import AssociationLink, AttributionStatus
from examples.patch_extraction import extract_patch


def emit(name, **data):
    print(json.dumps({"probe": name, **data}, default=str, sort_keys=True))


def main():
    graph = load_embed(
        patients=[{"empi_anon": "P"}],
        exams=[{"acc_anon": "A", "empi_anon": "P"}],
        source_scope="mutation",
    ).graph
    graph.patient("P").add_exam(Exam("UNINDEXED"))
    emit(
        "public_mutation",
        patient_exams=[exam.accession_number for exam in graph.patient("P").exams],
        graph_exams=[exam.accession_number for exam in graph.exams],
    )

    frame = pd.DataFrame({"empi_anon": ["P0", "P1", "P2", "P3"]})
    graph = DatasetGraph(source_scope="slice")
    load_embed(patients=frame.iloc[:2], into=graph)
    report = load_embed(patients=frame.iloc[2:], into=graph)
    emit(
        "range_index_chunks",
        second_index=list(frame.iloc[2:].index),
        patients=[patient.patient_id for patient in graph.patients],
        issues=[issue.code for issue in report.issues],
    )

    row = {
        "anon_dicom_path": "/old/1.2.3.dcm",
        "acc_anon": "A",
        "empi_anon": "P",
        "ImageLateralityFinal": "L",
        "FinalImageType": "3D",
        "Modality": "MG",
        "Rows": 100,
        "Columns": 100,
        "ImagesInAcquisition": 3,
        "ROI_coords": "[[1,2,3,4]]",
        "ROI_frames": "[[7]]",
        "ROI_depth_derived": "[False]",
        "num_ROI": 1,
        "acquisition_group_id": "GROUP",
        "PatientOrientation": "['P','F']",
    }
    graph = load_embed(images=[row], source_scope="metadata").graph
    emit(
        "metadata_projection",
        images=len(graph.images),
        rois=len(graph.rois),
        image_id=graph.images[0].image_id,
        sop_instance_uid=graph.images[0].sop_instance_uid,
        orientation=graph.images[0].patient_orientation,
        has_acquisition_group=hasattr(graph.images[0], "acquisition_group_id"),
    )
    report = load_embed(rois=[row], into=graph)
    emit(
        "out_of_range_frame",
        frames=graph.rois[0].frame_indices,
        frame_count=graph.images[0].frame_count,
        issues=[issue.code for issue in report.issues],
    )
    load_embed(
        images=[{**row, "anon_dicom_path": "/new/1.2.3.dcm"}],
        source_scope="relocated",
        into=graph,
    )
    emit("relocated_image", images=len(graph.images))

    graph = DatasetGraph(source_scope="roi-scope")
    for scope, coordinates in [
        ("annotations-A", "[[1,2,3,4]]"),
        ("annotations-B", "[[5,6,7,8]]"),
    ]:
        report = load_embed(
            rois=[{"anon_dicom_path": "I", "ROI_coords": coordinates}],
            source_scope=scope,
            into=graph,
        )
    emit(
        "roi_scope_collision",
        rois=len(graph.rois),
        issues=[issue.code for issue in report.issues],
        unresolved=graph.unresolved_references,
    )

    graph = DatasetGraph()
    with graph.transaction() as transaction:
        transaction.upsert_roi(
            "I", "R", SourceRef("s", "r", 0), coordinates=(1, 2, 3, 4)
        )
    previous = graph.roi("I", "R")
    with graph.transaction() as transaction:
        transaction.upsert_roi(
            "I", "R", SourceRef("s", "r", 1),
            coordinates=(1, 2, 3, 4), annotation_source="review",
        )
    emit(
        "roi_reference_replacement",
        same_object=previous is graph.roi("I", "R"),
        previous_annotation=previous.annotation_source,
        current_annotation=graph.roi("I", "R").annotation_source,
    )

    graph = load_embed(
        patients=[{"empi_anon": "P1"}, {"empi_anon": "P2"}],
        exams=[{"acc_anon": "A", "empi_anon": "P1"}],
        source_scope="ownership",
    ).graph
    report = load_embed(
        procedures=[{
            "empi_anon": "P2", "acc_anon": "A",
            "procdate_anon": "2020-01-01", "type": "BIOPSY", "bside": "L",
        }],
        into=graph,
    )
    emit(
        "cross_patient_procedure_link",
        links=[link.to_dict() for link in graph.links],
        issues=[issue.code for issue in report.issues],
    )
    source = SourceRef("s", "links", 1)
    with graph.transaction() as transaction:
        transaction.add_link(
            AssociationLink(
                "image", ("MISSING",), "exam", ("A",),
                AttributionStatus.INFERRED, source,
            ),
            source,
        )
    emit(
        "missing_source_link",
        retained=any(link.source_identity == ("MISSING",) for link in graph.links),
    )

    for mode in ["strict", "audit"]:
        graph = DatasetGraph()
        with graph.transaction() as transaction:
            transaction.upsert_roi(
                "I", "R", SourceRef("s", "r", 0), coordinates=(1, 2, 3, 4)
            )
        try:
            with graph.transaction(mode=mode) as transaction:
                transaction.upsert_patient("NEW", SourceRef("s", "p", 0))
                transaction.upsert_roi(
                    "I", "R", SourceRef("s", "r", 1),
                    coordinates=(1, 2, 3, 4), frame_provenance="derived",
                )
        except ValueError as error:
            emit(
                "commit_failure", mode=mode, error=str(error),
                patient_retained=graph.patient("NEW") is not None,
            )

    graph = load_embed(
        exams=[{"acc_anon": "A", "empi_anon": "ABSENT"}],
        source_scope="missing-parent",
    ).graph
    emit("missing_exam_patient", unresolved=graph.unresolved_references)

    row = {"anon_dicom_path": "I", "ROI_coords": "[[0,0,1,1]]"}
    graph = load_embed(images=[row], rois=[row], source_scope="patch").graph
    try:
        extract_patch([[1, 2], [3, 4]], graph.rois[0], image=graph.images[0])
    except (AttributeError, ValueError) as error:
        emit("graph_patch_consumer", error_type=type(error).__name__, error=str(error))

    graph = load_embed(images=[{"anon_dicom_path": "I"}], source_scope="a").graph
    load_embed(images=[{"anon_dicom_path": "I", "Rows": 12}], source_scope="z", into=graph)
    emit(
        "attribute_source",
        height=graph.image("I").height,
        reported_scope=graph.image("I").source_for("height").source_scope,
        actual_scope="z",
    )

    for count in [250, 500, 1000, 2000]:
        patients = [{"empi_anon": f"P{i}"} for i in range(count)]
        exams = [{"empi_anon": f"P{i}", "acc_anon": f"A{i}"} for i in range(count)]
        start = perf_counter()
        load_embed(patients=patients)
        patient_seconds = perf_counter() - start
        start = perf_counter()
        load_embed(patients=patients, exams=exams)
        emit(
            "scale", rows_per_table=count,
            patient_seconds=round(patient_seconds, 6),
            patient_exam_seconds=round(perf_counter() - start, 6),
        )


if __name__ == "__main__":
    main()
