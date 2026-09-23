"""Refresh and merge semantics across separate load_embed calls."""

import pandas as pd

from embed_data_model import DatasetGraph, load_embed


def test_partial_magview_load_keeps_patient_and_exam_fields_it_does_not_supply():
    graph = DatasetGraph()
    load_embed(
        patients=[{"empi_anon": "P1", "GENDER_DESC": "F"}],
        exams=[{"acc_anon": "A1", "empi_anon": "P1", "desc": "screen", "studydate_anon": "2020-01-01"}],
        into=graph,
    )
    load_embed(
        magview=[{"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L", "asses": "N"}],
        into=graph,
    )

    exam = graph.exam("A1")
    assert (exam.exam_date, exam.description) == ("2020-01-01", "screen")
    assert graph.patient("P1").sex == "F"
    assert graph.finding("A1", "1").interpretation.assessment == "N"


def test_refresh_clears_a_field_whose_column_is_supplied_as_null():
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "screen"}]).graph
    load_embed(exams=[{"acc_anon": "A1", "desc": None}], into=graph)

    assert graph.exam("A1").description is None


def test_dataframe_nan_counts_as_a_supplied_null():
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "screen", "studydate_anon": "2020-01-01"}]).graph
    frame = pd.DataFrame([{"acc_anon": "A1", "desc": float("nan"), "studydate_anon": "2021-02-03"}])
    load_embed(exams=frame, into=graph)

    exam = graph.exam("A1")
    assert exam.description is None
    assert exam.exam_date == "2021-02-03"


def test_partial_image_row_keeps_metadata_it_does_not_supply():
    path = "cohort1/P1/S1/SE1/U1.dcm"
    graph = load_embed(
        images=[{"anon_dicom_path": path, "acc_anon": "A1", "ViewPosition": "CC", "Rows": 100, "Columns": 80}]
    ).graph
    load_embed(images=[{"anon_dicom_path": path, "ImageLateralityFinal": "R"}], into=graph)

    (image,) = graph.images
    assert image.view_position.value == "CC"
    assert (image.height, image.width) == (100, 80)
    assert image.laterality.value == "R"
