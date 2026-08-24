from __future__ import annotations

import json

import pytest

from embed_toolkit.adapters.embed import build_clinical_tables
from embed_toolkit.clinical.cohorts import Cohort
from embed_toolkit.clinical.exams import Exam
from embed_toolkit.clinical.findings import Finding
from embed_toolkit.clinical.interpretations import ImagingInterpretation
from embed_toolkit.core.build_policy import BuildMode, BuildPolicy, BuildPolicyError
from embed_toolkit.core.primitives import Laterality
from embed_toolkit.core.provenance import (
    AvailabilityState,
    SourceLocator,
    SourceScopeKind,
)


def row(finding_number: str, **values: object) -> dict[str, object]:
    return {
        "empi_anon": "P-1",
        "acc_anon": "ACC-1",
        "numfind": finding_number,
        "side": "L",
        **values,
    }


def source(row_ordinal: int) -> SourceLocator:
    return SourceLocator(
        scope="clinical-materialization",
        scope_kind=SourceScopeKind.MATERIALIZATION,
        source_profile="internal-v2",
        source_table="magview",
        row_ordinal=row_ordinal,
    )


def test_interpretation_construction_distinguishes_absent_and_bound_null() -> None:
    tables = build_clinical_tables(
        [
            row("assessment-null", asses=None),
            row("recommendation-blank", recomm=""),
            row("absent"),
        ],
        source_scope="clinical-materialization",
    )

    assessment, recommendation, absent = tables.findings
    assert assessment.interpretation is tables.interpretations[0]
    assert assessment.interpretation.assessment is None
    assert assessment.interpretation.assessment_availability is AvailabilityState.BOUND
    assert assessment.interpretation.recommendation_availability is (
        AvailabilityState.UNAVAILABLE
    )
    assert recommendation.interpretation is tables.interpretations[1]
    assert recommendation.interpretation.recommendation is None
    assert recommendation.interpretation.recommendation_availability is (
        AvailabilityState.BOUND
    )
    assert recommendation.interpretation.assessment_availability is (
        AvailabilityState.UNAVAILABLE
    )
    assert absent.interpretation is None
    assert len(tables.interpretations) == 2


def test_interpretation_aliases_are_independent() -> None:
    tables = build_clinical_tables(
        [
            row("assessment", assessment="3"),
            row("birads", birads="4"),
            row("recommendation", recommendation="biopsy"),
        ],
        source_scope="clinical-materialization",
    )

    assert [item.assessment for item in tables.interpretations] == ["3", "4", None]
    assert [item.recommendation for item in tables.interpretations] == [
        None,
        None,
        "biopsy",
    ]


def test_repeated_interpretation_rows_fill_values_and_retain_unique_sources() -> None:
    tables = build_clinical_tables(
        [
            row("1", recomm="follow-up"),
            row("1", asses=None),
            row("1", asses="4"),
            row("1", asses="4", recomm="follow-up"),
        ],
        source_scope="clinical-materialization",
    )

    interpretation = tables.interpretations[0]
    assert tables.findings[0].interpretation is interpretation
    assert interpretation.assessment == "4"
    assert interpretation.assessment_availability is AvailabilityState.BOUND
    assert interpretation.recommendation == "follow-up"
    assert interpretation.recommendation_availability is AvailabilityState.BOUND
    assert interpretation.sources == tuple(source(index) for index in range(4))
    assert tables.build_issues == ()


def test_audit_retains_first_conflicting_interpretation_values() -> None:
    tables = build_clinical_tables(
        [
            row("1", asses="4", recomm="follow-up"),
            row("1", asses="5", recomm="biopsy"),
        ],
        build_policy=BuildPolicy(BuildMode.AUDIT),
        source_scope="clinical-materialization",
    )

    interpretation = tables.interpretations[0]
    assert interpretation.assessment == "4"
    assert interpretation.recommendation == "follow-up"
    assert interpretation.sources == (source(0), source(1))
    assert [issue.code for issue in tables.build_issues] == [
        "conflicting_interpretation_attribute",
        "conflicting_interpretation_attribute",
    ]
    assert [issue.context["attribute"] for issue in tables.build_issues] == [
        "assessment",
        "recommendation",
    ]


@pytest.mark.parametrize(
    ("first", "second", "attribute"),
    [
        ({"asses": "4"}, {"asses": "5"}, "assessment"),
        ({"recomm": "follow-up"}, {"recomm": "biopsy"}, "recommendation"),
    ],
)
def test_strict_rejects_conflicting_interpretation_values(
    first: dict[str, str],
    second: dict[str, str],
    attribute: str,
) -> None:
    with pytest.raises(BuildPolicyError) as exc_info:
        build_clinical_tables(
            [row("1", **first), row("1", **second)],
            source_scope="clinical-materialization",
        )

    assert exc_info.value.issue.code == "conflicting_interpretation_attribute"
    assert exc_info.value.issue.context["attribute"] == attribute
    assert exc_info.value.issue.source == source(1)


def test_finding_and_aggregate_serialization_use_interpretation_reference() -> None:
    tables = build_clinical_tables(
        [row("1", asses="4", recomm="follow-up")],
        source_scope="clinical-materialization",
    )

    finding = tables.findings[0]
    finding_plain = finding.to_dict()
    patient_plain = tables.patients[0].to_dict()
    cohort_plain = Cohort("study", patients=list(tables.patients)).to_dict()

    assert finding_plain["interpretation_reference"] == {
        "accession_number": "ACC-1",
        "finding_number": "1",
    }
    assert "assessment" not in finding_plain
    assert "interpretation" not in finding_plain
    assert patient_plain["exams"][0]["findings"][0] == finding_plain
    assert cohort_plain["patients"][0]["exams"][0]["findings"][0] == finding_plain
    assert tables.interpretations[0].identity == ("ACC-1", "1")
    assert tables.interpretations[0].to_dict()["finding"] == {
        "accession_number": "ACC-1",
        "finding_number": "1",
    }
    json.dumps(patient_plain)
    json.dumps(cohort_plain)
    json.dumps(tables.interpretations[0].to_dict())


def test_finding_merge_does_not_reconcile_interpretations() -> None:
    first_interpretation = ImagingInterpretation(
        accession_number="ACC-1",
        finding_number="1",
        sources=(source(0),),
        assessment="4",
    )
    second_interpretation = ImagingInterpretation(
        accession_number="ACC-1",
        finding_number="1",
        sources=(source(1),),
        assessment="5",
    )
    exam = Exam("ACC-1")
    owned = exam.add_finding(
        Finding("ACC-1", Laterality.LEFT, "1", interpretation=first_interpretation)
    )

    merged = exam.add_finding(
        Finding("ACC-1", Laterality.LEFT, "1", interpretation=second_interpretation)
    )

    assert merged is owned
    assert merged.interpretation is first_interpretation


def test_finding_rejects_interpretation_for_another_identity() -> None:
    interpretation = ImagingInterpretation(
        accession_number="ACC-2",
        finding_number="1",
        sources=(source(0),),
    )

    with pytest.raises(ValueError, match="interpretation identity must match"):
        Finding(
            "ACC-1",
            Laterality.LEFT,
            "1",
            interpretation=interpretation,
        )
