"""Pathology descriptor slots and diagnosis evidence."""

import pytest

from embed_data_model.clinical.pathology import PathologyDiagnosis, PathologyObservation


def test_descriptor_occurrences_keep_their_slot_and_repeated_values():
    first = PathologyObservation("ADH", "path1", 1)
    second = PathologyObservation("ADH", "path2", 2)

    assert first.descriptor == second.descriptor
    assert first.identity != second.identity


def test_descriptor_slot_ordinal_is_one_based():
    with pytest.raises(ValueError):
        PathologyObservation("ADH", "path0", 0)


def test_diagnosis_requires_some_represented_evidence():
    with pytest.raises(ValueError):
        PathologyDiagnosis()

    assert PathologyDiagnosis(report_documented_date="2020-01-05").report_documented_date == "2020-01-05"
