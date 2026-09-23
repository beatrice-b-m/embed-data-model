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


def test_codes_compare_after_trimming_and_uppercasing():
    report = load_embed(
        magview=[
            magview_row(side="L", asses="b", recc="ra"),
            magview_row(side="L", asses="B ", recc=" RA"),
        ]
    )

    interpretation = report.graph.finding("A1", "1").interpretation
    assert (interpretation.assessment, interpretation.recommendation) == ("B", "RA")
    assert not report.issues


def test_procedure_type_and_pathology_codes_are_normalized():
    procedure_row = magview_row(
        side="L", bside="L", procdate_anon="2020-01-02", type="core", path1=" idc"
    )
    graph = load_embed(
        magview=[procedure_row, dict(procedure_row, numfind=2, type="CORE ")]
    ).graph

    (procedure,) = graph.procedures
    assert procedure.identity.procedure_type == "CORE"
    assert {finding.finding_number for finding in graph.findings if procedure in finding.procedures} == {"1", "2"}
