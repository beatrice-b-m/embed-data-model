from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from embed_toolkit import DatasetGraph, LoadError, load_embed
from embed_toolkit.adapters.tables import iter_records
from embed_toolkit.core.source import CanonicalKey, SourceRef


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
