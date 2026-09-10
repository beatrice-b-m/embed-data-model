"""Clinical adapter contracts using synthetic, explicitly mapped registry data."""

from itertools import permutations

import pytest

from embed_data_model.clinical.exams import Exam
from embed_data_model.clinical.findings import Finding
from embed_data_model.clinical.patients import Patient
from embed_data_model.core.graph import DatasetGraph
from embed_data_model.sources.embed.clinical import load_clinical
from embed_data_model.sources.embed.columns import resolve_columns
from embed_data_model.sources.embed.procedures_pathology import (
    normalize_pathology,
    normalize_procedure,
)


def test_normalizers_accept_optional_sources_and_preserve_raw_severity():
    columns = resolve_columns(None)
    procedure, issues = normalize_procedure(clinical_row(), columns["procedures"])
    assert procedure.identity.patient_id == "P"
    assert not issues and not procedure.sources
    diagnosis, descriptors, issues = normalize_pathology(
        {"path1": "ADH", "path_severity": 99}, columns["pathology"]
    )
    assert diagnosis.raw_severity == 99 and diagnosis.severity is None
    assert descriptors[0].descriptor == "ADH"
    assert not issues
    diagnosis, descriptors, issues = normalize_pathology(
        {"path1": "ADH"}, columns["pathology"]
    )
    assert diagnosis is None and len(descriptors) == 1 and not issues


def load(graph, *, mode="refresh", columns=None, **tables):
    issues = []
    load_clinical(
        procedures=tables.get("procedures", []),
        pathology=tables.get("pathology", []),
        magview=tables.get("magview", []),
        registry=tables.get("registry", []),
        graph=graph,
        columns=columns or resolve_columns(None),
        mode=mode,
        issues=issues,
    )
    return issues


def row(**fields):
    return dict(empi_anon="P", acc_anon="A", numfind="1", **fields)


@pytest.mark.parametrize("order", list(permutations(("exam", "assignment", "entry"))))
def test_registry_arrival_orders(order):
    graph = DatasetGraph()
    for step in order:
        if step == "exam":
            if graph.exam("A") is None:
                graph.register(Exam("A"))
        elif step == "assignment":
            load(graph, magview=[row(cancer_outcome_registry_id="7")] * 3)
            assert graph.exam("A").registry_references == {("P", "7")}
        else:
            load(graph, registry=[{"empi_anon": "P", "cancer_registry_id": "7"}])
    assert graph.exam("A").registry_pathology == (
        graph.registry_entry("P", "7"),
    )


def test_registry_patient_scope_sharing_and_source_disagreement():
    graph = DatasetGraph()
    load(
        graph, registry=[{"empi_anon": p, "cancer_registry_id": 7} for p in ("P", "Q")]
    )
    load(
        graph,
        magview=[
            row(cancer_outcome_registry_id=7),
            {"empi_anon": "P", "acc_anon": "B", "cancer_outcome_registry_id": 7},
            {"empi_anon": "Q", "acc_anon": "A", "cancer_outcome_registry_id": 7},
        ],
    )
    assert len(graph.registry_entries) == 2
    assert graph.exam("A").patient_id is None
    assert graph.exam("A").asserted_patient_ids == {"P", "Q"}
    assert len(graph.exam("A").registry_entries) == 2
    assert graph.exam("B").registry_pathology == (
        graph.registry_entry("P", "7"),
    )


def test_collection_refresh_absence_null_and_merge():
    graph = DatasetGraph()
    load(graph, magview=[row(cancer_outcome_registry_id="7", linkedaccession_anon="B")])
    assert graph.unresolved_references
    load(graph, magview=[row()])
    assert graph.exam("A").registry_references == {("P", "7")}
    assert graph.exam("A").linked_accessions == {"B"}
    load(
        graph,
        mode="merge",
        magview=[row(cancer_outcome_registry_id="8", linkedaccession_anon="C")],
    )
    assert graph.exam("A").registry_references == {("P", "7"), ("P", "8")}
    assert graph.exam("A").linked_accessions == {"B", "C"}
    load(
        graph, magview=[row(cancer_outcome_registry_id=None, linkedaccession_anon=None)]
    )
    assert not graph.exam("A").registry_references
    assert not graph.exam("A").linked_accessions


def clinical_row(**fields):
    result = row(
        procdate_anon="2020-01-01",
        type="biopsy",
        bside="L",
        pdate_anon="2020-01-02",
        path1="ADH",
        path2="ADH",
    )
    result.update(fields)
    return result


def test_repeated_narrow_wide_rows_share_descendants_and_preserve_parent():
    graph = DatasetGraph()
    graph.register(Patient("P"))
    graph.register(Exam("A", description="preserve"))
    graph.register(Finding("A", "L", "1"))
    graph.register(Finding("A", "L", "2"))
    first, second = clinical_row(), clinical_row(numfind="2")
    for rows in ([first, second], [second, first]):
        load(graph, magview=rows, procedures=rows, pathology=rows)
        assert len(graph.procedures) == len(graph.pathology) == 1
        assert graph.exam("A").description == "preserve"
        assert len(graph.patient("P").procedures) == 1
        assert len(graph.patient("P").pathologies) == 1
        assert (
            graph.finding("A", "1").procedures[0]
            is graph.finding("A", "2").procedures[0]
        )
        assert [d.descriptor for d in graph.pathology[0].descriptors] == ["ADH", "ADH"]


def test_fallback_descriptor_conflict_unresolved_and_refresh_bounded():
    graph = DatasetGraph()
    rows = [clinical_row(), clinical_row(path1="DCIS")]
    for incoming in (rows, list(reversed(rows)), rows):
        issues = load(graph, pathology=incoming)
        assert "ambiguous_pathology_identity" in {i.code for i in issues}
        assert not graph.pathology
        assert sum(len(v) for v in graph.unresolved_records.values()) == 2
    load(graph, pathology=[clinical_row()])
    assert len(graph.pathology) == 1
    assert not graph.unresolved_records


def test_explicit_pathology_id_is_patient_scoped_and_preserves_reference():
    graph = DatasetGraph()
    columns = resolve_columns(None)
    columns["pathology"]["record_id"] = "report_id"
    load(
        graph,
        columns=columns,
        pathology=[
            clinical_row(report_id="R"),
            clinical_row(report_id="R", empi_anon="Q"),
        ],
    )
    assert len(graph.pathology) == 2
    obj = graph.get("pathology", ("P", "R"))
    load(graph, columns=columns, pathology=[clinical_row(report_id="R", path1="new")])
    assert graph.get("pathology", ("P", "R")) is obj
    assert obj.descriptors[0].descriptor == "new"


def test_insufficient_identity_preserves_useful_snapshot():
    graph = DatasetGraph()
    issues = load(graph, procedures=[row(type="biopsy")], pathology=[row(path1="ADH")])
    assert {i.code for i in issues} >= {
        "incomplete_procedure_identity",
        "incomplete_pathology_identity",
    }
    assert not graph.procedures and not graph.pathology
    assert any(
        v[0]["payload"].get("path1") == "ADH" for v in graph.unresolved_records.values()
    )


def test_registry_payload_is_explicit_and_refreshes_only_bound_fields():
    graph = DatasetGraph()
    load(
        graph,
        registry=[{"empi_anon": "P", "cancer_registry_id": "7", "secret": "unused"}],
    )
    obj = graph.registry_entry("P", "7")
    assert dict(obj.payload) == {}
    columns = resolve_columns(None)
    columns["registry"]["diagnosis"] = "dx"
    load(
        graph,
        columns=columns,
        registry=[{"empi_anon": "P", "cancer_registry_id": "7", "dx": "supplied"}],
    )
    assert graph.registry_entry("P", "7") is obj
    assert obj.payload["diagnosis"] == "supplied"
    load(
        graph, columns=columns, registry=[{"empi_anon": "P", "cancer_registry_id": "7"}]
    )
    assert obj.payload["diagnosis"] is None


def test_unbound_collections_preserve_and_mapped_columns_are_used():
    graph = DatasetGraph()
    columns = resolve_columns(None)
    columns["magview"]["registry_assignment"] = "assignment"
    columns["magview"]["linked_accession"] = "link"
    load(graph, columns=columns, magview=[row(assignment="7", link="B")])
    columns["magview"]["registry_assignment"] = None
    columns["magview"]["linked_accession"] = None
    load(graph, columns=columns, magview=[row(assignment=None, link=None)])
    assert graph.exam("A").registry_references == {("P", "7")}
    assert graph.exam("A").linked_accessions == {"B"}


def test_conflicting_refresh_removes_prior_resolved_fallback():
    graph = DatasetGraph()
    load(graph, pathology=[clinical_row()])
    assert len(graph.pathology) == 1
    load(graph, pathology=[clinical_row(), clinical_row(path2="different")])
    assert not graph.pathology
    assert graph.unresolved_records


def test_scalar_conflict_is_unknown_and_unbound_pathology_fields_survive():
    graph = DatasetGraph()
    load(graph, pathology=[clinical_row(pathology_diagnosis="first")])
    obj = graph.pathology[0]
    columns = resolve_columns(None)
    columns["pathology"]["diagnosis"] = None
    load(graph, columns=columns, pathology=[clinical_row()])
    assert obj.diagnosis == "first"
    issues = load(
        graph,
        pathology=[
            clinical_row(pathology_diagnosis="a"),
            clinical_row(pathology_diagnosis="b"),
        ],
    )
    assert obj.diagnosis is None
    assert "conflicting_clinical_values" in {i.code for i in issues}


def test_confirmed_reference_resolves_when_both_endpoints_were_missing():
    graph = DatasetGraph()
    graph.reference("exam", "A", "registry", ("P", "7"), relation="registry")
    assert graph.unresolved_references
    load(graph, registry=[{"empi_anon": "P", "cancer_registry_id": "7"}])
    assert graph.unresolved_references
    graph.register(Exam("A"))
    assert graph.exam("A").registry_pathology == (
        graph.registry_entry("P", "7"),
    )
    assert not graph.unresolved_references


def test_procedure_before_finding_resolves_and_exam_fallback_is_supported():
    graph = DatasetGraph()
    load(graph, procedures=[clinical_row()])
    assert len(graph.procedures) == 1
    graph.register(Finding("A", "L", "1"))
    assert graph.finding("A", "1").procedures[0] is graph.procedures[0]
    load(graph, procedures=[clinical_row(numfind=None, procdate_anon="2021-01-01")])
    assert len(graph.exam("A").procedures) == 2
