"""Executable public-API journeys for the installed toolkit wheel."""

from __future__ import annotations

from pathlib import Path

import embed_toolkit
from embed_toolkit import Box, DatasetGraph, RegionOfInterest, SourceRef, load_embed
from examples.patch_extraction import extract_patch


def run() -> None:
    package_path = Path(embed_toolkit.__file__).resolve()
    assert "site-packages" in package_path.as_posix()

    patients = [{"empi_anon": "P-1"}, {"empi_anon": "P-2"}]
    patient_only = load_embed(
        patients=[patients[1]],
        source_scope="journey-patient",
        identity_namespace="release-2",
    )
    assert [patient.patient_id for patient in patient_only.graph.patients] == ["P-2"]

    exam_only = load_embed(
        exams=[{"acc_anon": "A-standalone"}],
        source_scope="journey-exam",
        identity_namespace="release-2",
    )
    assert exam_only.graph.exam("A-standalone") is not None

    exams = [
        {"acc_anon": "A-1", "empi_anon": "P-1"},
        {"acc_anon": "A-2", "empi_anon": "P-2"},
    ]
    images = [
        {
            "anon_dicom_path": "IMG-1",
            "empi_anon": "P-1",
            "acc_anon": "A-1",
            "ImageLateralityFinal": "L",
            "ViewPosition": "CC",
            "Modality": "MG",
        },
        {
            "anon_dicom_path": "IMG-2",
            "empi_anon": "P-2",
            "acc_anon": "A-2",
            "ImageLateralityFinal": "R",
            "ViewPosition": "MLO",
            "Modality": "MG",
        },
    ]
    rois = [{"anon_dicom_path": "IMG-2", "ROI_coords": [[1, 1, 2, 3]]}]
    combined = load_embed(
        patients=[patients[1]],
        exams=[exams[1]],
        images=[images[1]],
        rois=rois,
        source_scope="journey-combined",
        identity_namespace="release-2",
    )
    patient = combined.graph.patient("P-2")
    exam = combined.graph.exam("A-2")
    image = combined.graph.image("IMG-2")
    assert patient is not None and patient.exams == [exam]
    assert exam is not None and exam.images == [image]
    assert image is not None and image.rois == list(combined.graph.rois)

    manual_roi = RegionOfInterest(
        Box(0, 0, 2, 2),
        image_id="manual-image",
        roi_key="manual-roi",
    )
    patch = extract_patch([[1, 2], [3, 4]], manual_roi)
    assert patch.patch_payload["data"] == ((1, 2), (3, 4))

    issues = load_embed(
        exams=[{"acc_anon": " "}],
        source_scope="journey-issues",
    ).issues
    assert [issue.code for issue in issues] == ["missing_accession"]

    extension_graph = DatasetGraph(identity_namespace="registry")
    with extension_graph.transaction(mode="strict") as transaction:
        transaction.upsert_patient(
            "R-1",
            SourceRef("registry-2026", "patients", "row-1"),
        )
    assert extension_graph.patient("R-1") is not None


if __name__ == "__main__":
    run()
