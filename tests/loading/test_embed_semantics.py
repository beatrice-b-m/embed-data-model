"""EMBED source semantics that the loader must honour.

Each test encodes one reviewed meaning of an EMBED column or code, using
synthetic rows only.
"""

import pytest

from embed_data_model import Laterality, load_embed


def magview_row(**fields):
    row = {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1}
    row.update(fields)
    return row


@pytest.mark.parametrize("side", [None, "B"])
def test_null_or_b_finding_side_is_bilateral_and_projects_to_both_sides(side):
    graph = load_embed(magview=[magview_row(side=side)]).graph

    finding = graph.finding("A1", "1")
    exam = graph.exam("A1")
    assert finding.laterality is Laterality.BILATERAL
    assert exam.breast_sides[Laterality.LEFT].findings == (finding,)
    assert exam.breast_sides[Laterality.RIGHT].findings == (finding,)


def test_finding_side_absent_from_every_row_stays_unknown():
    graph = load_embed(magview=[magview_row()]).graph

    finding = graph.finding("A1", "1")
    assert finding.laterality is Laterality.UNKNOWN
    assert not graph.exam("A1").breast_sides


def test_merge_applies_a_null_finding_side_as_bilateral():
    graph = load_embed(magview=[magview_row()]).graph
    load_embed(magview=[magview_row(side=None)], into=graph, mode="merge")

    assert graph.finding("A1", "1").laterality is Laterality.BILATERAL
