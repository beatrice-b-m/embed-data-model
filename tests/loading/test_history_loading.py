"""Reported patient history tables."""

import pytest

from embed_data_model import load_embed


def reported_results(result):
    report = load_embed(procedure_history=[{"empi_anon": "P1", "type": "B", "pcode": "1", "result": result}])
    history = report.graph.patient("P1").procedure_history
    return [item.reported_result for item in history], {issue.code for issue in report.issues}


def test_none_means_no_reported_result_and_is_kept_distinct_from_blank():
    none_results, _ = reported_results("NONE")
    blank_results, _ = reported_results("")

    assert none_results == ["no_reported_result"]
    assert blank_results == [None]


@pytest.mark.parametrize("code, meaning", [("BEN", "benign"), ("id", "invasive_ductal_carcinoma")])
def test_known_result_codes_are_decoded(code, meaning):
    results, issues = reported_results(code)

    assert results == [meaning]
    assert not issues


def test_combined_result_token_is_kept_whole_and_reported():
    results, issues = reported_results("FA,SF")

    assert results == ["FA,SF"]
    assert "unknown_procedure_history_result" in issues


def test_unkeyed_history_refresh_and_merge_require_explicit_event_identity():
    rows = [{"empi_anon":"P", "type":"H", "code":"E", "first_age":-5}]
    graph = load_embed(hormone_history=rows * 2).graph
    patient = graph.patient("P")
    assert len(patient.medication_history) == 2
    assert patient.medication_history[0].started.age == -5
    old = patient.medication_history
    report = load_embed(hormone_history=rows, into=graph, mode="merge")
    assert patient.medication_history == old
    assert any(i.code == "history_merge_requires_record_id" for i in report.issues)
    load_embed(hormone_history=rows, into=graph)
    assert len(patient.medication_history) == 1
    patient.replace_history("medication", [])
    assert not patient.medication_history


def test_explicit_history_key_refresh_preserves_reference_and_custom_values():
    columns = {"hormone_history":{"record_id":"record"}}
    rows = [{"empi_anon":"P", "type":"H", "code":"E", "record":"1", "comment":"old"}]
    graph = load_embed(hormone_history=rows, columns=columns).graph
    history = graph.patient("P").medication_history[0]
    history.project = {"keep":True}
    rows[0]["comment"] = "new"
    load_embed(hormone_history=rows, columns=columns, into=graph)
    assert graph.patient("P").medication_history == (history,)
    assert history.comment == "new" and history.project == {"keep":True}
