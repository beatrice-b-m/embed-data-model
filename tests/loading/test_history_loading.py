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
